"""The live ledger's jobs: the Toss sync, the reconciliation, and the server's read-only check
(autotrade/PHASE3.md 2.3, 2.5, 5).

The sync is the only code that calls Toss for the engine. It runs in the tick (cron), never in
the web service (sandboxed: no network, no secrets). Each step is network first, then a short
transaction of its own, like the market downloads (autotrade/jobs/tasks.py); an order's intent is
committed before the order leaves, so a crash in between is found and resolved the next time:

  1. read our open orders at the broker (fills, ends: a PARTIAL_FILLED order is over only once
     the CLOSED list has it or it carries a cancel time, Sync.finished)
  2. resolve orders whose sending was cut off: within 9 minutes the same client order id is sent
     again (Toss returns the first order), later the account's orders are searched for it
  3. cancel what must not stay open: cancel requests ('live off', resolve), any open order of
     ours while the mode is not live, a day order still open after its session
  4. send the orders whose stage is due (only with both keys, and never on a mismatch)
  5. once a day: the rule's instruments tradable, the commission rates
  6. a snapshot of the account: cash (buying power), holdings, the closed orders since the last
     reconciliation that matched; 'quiet' when no order was open anywhere while it was read;
     then the account's open 조건주문 (armed, they place orders of their own: live is not
     turned on while one is open)
  7. the link's status (the mode and health screens read it)

Without AUTOTRADE_LIVE_ORDERS=1 nothing is called: the status says 'off' and that is all.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from autotrade.broker.base import NOTHING_TO_BUY
from autotrade.broker.toss import (
    LIVE,
    client_order_id,
    env_live,
    fee_rate,
    limit_price,
    permit_for,
)
from autotrade.broker.toss_api import (
    OPEN_OR_CLOSED,
    REQUEST_RECORDS,
    BrokerOrder,
    ConditionalOrder,
    LivePermit,
    OrderRequest,
    TossApiError,
    TossClient,
    TossError,
    TossNotConfiguredError,
    TossUnreachableError,
    Transport,
    link_state,
    read_credentials,
    urllib_transport,
)
from autotrade.config import Config
from autotrade.db import live_repo, repo
from autotrade.db.connection import transaction
from autotrade.db.live_repo import BrokerOrderRow, BrokerStatus
from autotrade.db.models import OrderRow, StageRow
from autotrade.domain.instruments import Currency, Instrument, Market
from autotrade.domain.money import ZERO, usd_in_krw
from autotrade.domain.planner import Side
from autotrade.engine import live, runner, sleeves
from autotrade.engine.common import new_money_waiting, withdraw_wait_amounts
from autotrade.market.calendar import CalendarRangeError, calendar_for
from autotrade.timeutil import KST, et_date, from_iso, kst_date, require_aware

SNAPSHOT_KEEP = timedelta(days=7)
SESSION_GRACE = timedelta(minutes=30)  # a day order still open this long after its session
FILLED_AFTER_READ = timedelta(seconds=2)


def make_client(cfg: Config, transport: Transport | None = None) -> TossClient:
    creds = read_credentials(cfg.secrets_env)
    if creds is None:
        raise TossNotConfiguredError("TOSS_CLIENT_ID / TOSS_CLIENT_SECRET not in the secrets file")
    return TossClient(creds, cfg.toss_dir, transport=transport or urllib_transport)


# ── the sync ─────────────────────────────────────────────────────────────────────────────


class Sync:
    """One run of the Toss sync. `now` is the wall clock (orders carry real times)."""

    def __init__(
        self,
        conn: Any,
        cfg: Config,
        client: TossClient,
        at: datetime,
        now: Callable[[], datetime],
    ) -> None:
        self.conn = conn
        self.cfg = cfg
        self.client = client
        self.at = at
        self.now = now
        self.changes: list[dict[str, Any]] = []
        self.errors: list[str] = []
        self.conditional: list[ConditionalOrder] | None = None  # step 6, None until read
        self._closed: dict[tuple[str, date], set[str]] = {}  # CLOSED ids by (symbol, day)

    # 1. read our open orders
    def poll(self) -> None:
        for row in live_repo.broker_orders_of(self.conn, LIVE, ["sent"]):
            if row.broker_order_id is None:  # pragma: no cover — 'sent' always has the id
                continue
            try:
                view = self.client.order(row.broker_order_id)
                self._record_view(row, view)
            except TossApiError as exc:
                self.errors.append(f"poll {row.order_id}: {exc}")

    def finished(self, view: BrokerOrder) -> bool:
        """Whether the broker is done with an order: its own record says so (a terminal status,
        a cancel time), or it is PARTIAL_FILLED and the CLOSED list has it (the status is in both
        lists, openapi.json 1.2.24: a partly filled order whose rest lapsed may keep it). An
        order the OPEN list holds as PARTIAL_FILLED still trades."""
        if view.terminal:
            return True
        if view.status != OPEN_OR_CLOSED or view.ordered_at is None:
            return False
        day = kst_date(view.ordered_at)
        key = (view.symbol, day)
        if key not in self._closed:
            closed = self.client.orders(
                "CLOSED", symbol=view.symbol, start=day, end=day + timedelta(days=1)
            )
            self._closed[key] = {o.order_id for o in closed}
        return view.order_id in self._closed[key]

    def _record_view(self, row: BrokerOrderRow, view: BrokerOrder) -> bool:
        """Record what the broker says of `row` now; returns whether the order is over."""
        over = self.finished(view)
        if (
            row.state == ("done" if over else "sent")
            and row.status == view.status
            and row.filled_qty == view.filled_qty
            and row.broker_order_id == view.order_id
        ):
            return over
        with transaction(self.conn):
            live_repo.record_broker_view(self.conn, row.order_id, view, self.now(), finished=over)
        self.changes.append(
            {"order_id": row.order_id, "status": view.status, "filled": str(view.filled_qty)}
        )
        return over

    # 2. orders whose sending was cut off
    def recover(self) -> None:
        for row in live_repo.broker_orders_of(self.conn, LIVE, ["sending", "unknown"]):
            if row.error_code == "ambiguous":
                continue  # a person checks the app (health screen)
            request = row.request
            if request is None or row.sent_at is None:
                with transaction(self.conn):
                    live_repo.record_not_sent(
                        self.conn,
                        order_id=row.order_id,
                        ledger_id=LIVE,
                        client_order_id=row.client_order_id,
                        code="lost",
                        detail="no request kept",
                        at=self.now(),
                    )
                continue
            age = self.now() - row.sent_at
            if age < self.cfg.resend_window:
                with transaction(self.conn):
                    permit = permit_for(self.conn, self.cfg, LIVE, self.now())
                if permit is not None:
                    self._submit(row.order_id, request, permit, resend=True)
                    continue
            self._search(row, request, final=age >= self.cfg.resend_window)

    def _search(self, row: BrokerOrderRow, request: OrderRequest, *, final: bool) -> None:
        """After the resend window the same id would be a new order: look for the first one."""
        assert row.sent_at is not None
        sent = row.sent_at
        try:
            found = self.client.orders("OPEN", symbol=request.symbol)
            closed = self.client.orders(
                "CLOSED",
                symbol=request.symbol,
                start=kst_date(sent),
                end=kst_date(sent) + timedelta(days=1),
            )
        except TossError as exc:
            self.errors.append(f"search {row.order_id}: {exc}")
            return
        closed_ids = {o.order_id for o in closed}
        found += closed
        ours = live_repo.our_broker_ids(self.conn)
        matches = [
            o
            for o in found
            if o.order_id not in ours
            and o.side == request.side
            and o.quantity == request.quantity
            and (o.price is None or o.price == request.price)
            and o.ordered_at is not None
            and sent - timedelta(minutes=2) <= o.ordered_at <= sent + timedelta(minutes=12)
        ]
        unique = {o.order_id: o for o in matches}
        with transaction(self.conn):
            if len(unique) == 1:
                view = next(iter(unique.values()))
                over = view.terminal or view.order_id in closed_ids
                live_repo.mark_sent(self.conn, row.order_id, view.order_id, self.now())
                live_repo.record_broker_view(
                    self.conn, row.order_id, view, self.now(), finished=over
                )
                self.changes.append({"order_id": row.order_id, "found": view.order_id})
            elif len(unique) > 1:
                # A person tells which is ours (`resolve broker-mismatch:order:<id> --pick`):
                # keep what each looked like, and from which list it came.
                candidates = [
                    {"order": o.to_json(), "closed": o.order_id in closed_ids}
                    for o in sorted(unique.values(), key=lambda o: o.order_id)
                ]
                live_repo.mark_unknown(
                    self.conn,
                    row.order_id,
                    "ambiguous",
                    f"{len(unique)} orders match; check the Toss app",
                    self.now(),
                    candidates,
                )
                self.changes.append({"order_id": row.order_id, "ambiguous": len(unique)})
            elif final:
                live_repo.record_not_sent(
                    self.conn,
                    order_id=row.order_id,
                    ledger_id=LIVE,
                    client_order_id=row.client_order_id,
                    code="lost",
                    detail="never reached the broker",
                    at=self.now(),
                    request=request,
                )
                self.changes.append({"order_id": row.order_id, "lost": True})

    # 3. cancellations
    def cancels(self) -> None:
        mode = live.mode_of(self.conn)
        # A cancel asked for an order that has ended meanwhile (it filled, Toss ended it):
        # nothing is left to cancel.
        for row in live_repo.broker_orders_of(self.conn, LIVE, ["done", "rejected", "not-sent"]):
            if row.cancel_state in ("requested", "failed"):
                with transaction(self.conn):
                    live_repo.record_cancel(self.conn, row.order_id, "done", None, self.now())
        for row in live_repo.broker_orders_of(self.conn, LIVE, ["sent"]):
            wanted = (
                row.cancel_state in ("requested", "failed")
                or mode != LIVE
                or self._past_session(row)
            )
            if not wanted or row.broker_order_id is None:
                continue
            with transaction(self.conn):
                permit = permit_for(self.conn, self.cfg, LIVE, self.now(), purpose="cancel")
                if permit is not None and row.cancel_state is None:
                    live_repo.request_cancel(self.conn, row.order_id, self.now())
            if permit is None:
                continue
            outcome = "done"
            try:
                self.client.cancel_order(permit, row.broker_order_id)
            except TossApiError as exc:
                if exc.code == "already-processing":
                    continue
                if exc.code not in (
                    "already-filled",
                    "already-canceled",
                    "already-rejected",
                    "already-modified",
                ):
                    outcome = "failed"
                    with transaction(self.conn):
                        live_repo.record_cancel(
                            self.conn, row.order_id, "failed", str(exc), self.now()
                        )
                    self.changes.append({"order_id": row.order_id, "cancel": "failed"})
                    continue
            except TossUnreachableError as exc:
                with transaction(self.conn):
                    live_repo.record_cancel(self.conn, row.order_id, "failed", str(exc), self.now())
                self.changes.append({"order_id": row.order_id, "cancel": "failed"})
                continue
            try:
                over = self._record_view(row, self.client.order(row.broker_order_id))
            except TossError as exc:
                self.errors.append(f"after cancel {row.order_id}: {exc}")
                outcome = "requested"
            else:
                if not over:
                    outcome = "requested"  # PENDING_CANCEL: read again next time
            with transaction(self.conn):
                live_repo.record_cancel(self.conn, row.order_id, outcome, None, self.now())
            self.changes.append({"order_id": row.order_id, "cancel": outcome})

    def _past_session(self, row: BrokerOrderRow) -> bool:
        request = row.request
        if request is None or row.sent_at is None:
            return False
        market = Market.US if request.currency is Currency.USD else Market.KR
        cal = calendar_for(market)
        day = et_date(row.sent_at) if market is Market.US else kst_date(row.sent_at)
        try:
            if not cal.is_trading_day(day):
                day = cal.next_trading_day(day)
            close = cal.session_close(day)
        except CalendarRangeError:
            return False
        return self.now() > close + SESSION_GRACE

    # 4. sending
    def send_due(self) -> None:
        if live.mode_of(self.conn) != LIVE or repo.start_event(self.conn, LIVE) is None:
            return
        status = live_repo.get_status(self.conn)
        if status is not None and status.reconcile_state == "mismatch":
            return  # never trade on an account that does not match (PHASE3.md 2.5)
        if not permit_for(self.conn, self.cfg, LIVE, self.now()):
            return
        for stage in runner.eligible_stages(self.conn, LIVE, self.at):
            for order in repo.orders_of_stage(self.conn, stage.stage_id, ["pending"]):
                if order.side == "fx" or order.instrument_id is None:
                    continue  # live plans never convert (D47): nothing to send
                row = live_repo.get_broker_order(self.conn, order.order_id)
                if row is not None and not self._send_again(row):
                    continue
                self._send_one(stage, order, row)

    def _send_again(self, row: BrokerOrderRow) -> bool:
        if row.state != "not-sent" or row.error_code not in ("order-hours-closed", "link"):
            return False
        return row.retry_after is None or row.retry_after <= self.now()

    def _send_one(self, stage: StageRow, order: OrderRow, row: BrokerOrderRow | None) -> None:
        assert order.instrument_id is not None
        assert order.qty is not None
        inst = repo.get_instrument(self.conn, order.instrument_id)
        side = Side(order.side)
        try:
            quote = self.client.prices([inst.ticker]).get(inst.ticker)
        except TossError as exc:
            self.errors.append(f"price {inst.ticker}: {exc}")
            return
        if quote is None:
            self.errors.append(f"price {inst.ticker}: none")
            return
        limit = limit_price(inst, side, quote.price, self.cfg.live_limit_slippage)
        plan = repo.get_plan(self.conn, order.plan_id)
        try:
            qty, code = self._quantity(plan.rule_id, inst, side, order.qty, limit)
        except TossError as exc:
            self.errors.append(f"quantity {inst.ticker}: {exc}")
            return
        # A fresh id after an attempt the broker refused (its key may replay the refusal).
        key = order.idem_key if row is None else f"{order.idem_key}:{self.now().isoformat()}"
        request = OrderRequest(
            client_order_id(key), inst.ticker, side.value.upper(), qty, limit, inst.currency
        )
        if code is None and self._value_krw(inst, qty, limit) >= self.cfg.live_max_order_krw:
            code = "over-limit"
        if code is not None:
            with transaction(self.conn):
                live_repo.record_not_sent(
                    self.conn,
                    order_id=order.order_id,
                    ledger_id=LIVE,
                    client_order_id=request.client_order_id,
                    code=code,
                    detail=f"planned {order.qty}, could send {qty}",
                    at=self.now(),
                    request=request,
                )
            self.changes.append({"order_id": order.order_id, "not_sent": code})
            return
        with transaction(self.conn):
            permit = permit_for(self.conn, self.cfg, LIVE, self.now())
            if permit is not None:
                live_repo.insert_intent(
                    self.conn,
                    order_id=order.order_id,
                    ledger_id=LIVE,
                    request=request,
                    at=self.now(),
                )
        if permit is None:
            return  # the mode changed meanwhile: nothing was written, nothing leaves
        self._submit(order.order_id, request, permit, resend=False)

    def _quantity(
        self, rule_id: str, inst: Instrument, side: Side, planned: int, limit: Decimal
    ) -> tuple[int, str | None]:
        """Whole shares that can go: a buy within the rule's cash (not the cash waiting for a
        withdrawal, nor the owner's money of today, D48) and the broker's buying power at the
        limit price with the commission (none: NOTHING_TO_BUY, the order ends and its cash waits
        for the next check); a sell within the rule's shares and the broker's sellable
        quantity."""
        view = sleeves.view(self.conn, LIVE, rule_id)
        if side is Side.BUY:
            held = (
                withdraw_wait_amounts(repo.cash_parts(self.conn, LIVE))
                if rule_id == sleeves.BASE_RULE
                else {}
            )
            new_money = new_money_waiting(self.conn, LIVE, self.now())
            ledger_cash = (
                view.cash_of(inst.currency)
                - held.get(inst.currency, ZERO)
                - new_money.get(inst.currency, ZERO)
            )
            power = self.client.buying_power(inst.currency)
            cash = min(power, ledger_cash)
            unit = limit * (1 + fee_rate(self.cfg, self._commissions(), inst))
            affordable = (
                0 if cash <= 0 else int((cash / unit).to_integral_value(rounding=ROUND_FLOOR))
            )
            qty = min(planned, affordable)
            return qty, None if qty > 0 else NOTHING_TO_BUY
        sellable = self.client.sellable_quantity(inst.ticker)
        whole = int(sellable.to_integral_value(rounding=ROUND_FLOOR))
        qty = min(planned, view.qty_of(inst.instrument_id), whole)
        return qty, None if qty > 0 else "nothing-to-sell"

    def _commissions(self) -> dict[str, Decimal]:
        status = live_repo.get_status(self.conn)
        return {} if status is None else status.commissions

    def _value_krw(self, inst: Instrument, qty: int, price: Decimal) -> Decimal:
        value = price * qty
        if inst.currency is Currency.KRW:
            return value
        quote = repo.fx_at(self.conn, self.now())
        rate = quote.rate if quote is not None else Decimal(2000)  # high on purpose: err safe
        return usd_in_krw(value, rate)

    def _submit(
        self, order_id: int, request: OrderRequest, permit: LivePermit, *, resend: bool
    ) -> None:
        try:
            broker_id, _ = self.client.create_order(permit, request)
        except TossUnreachableError as exc:
            with transaction(self.conn):
                live_repo.mark_unknown(self.conn, order_id, "unreachable", str(exc), self.now())
            self.changes.append({"order_id": order_id, "sent": "unknown"})
            return
        except TossApiError as exc:
            self._refused(order_id, request, exc)
            return
        with transaction(self.conn):
            live_repo.mark_sent(self.conn, order_id, broker_id, self.now())
        self.changes.append(
            {
                "order_id": order_id,
                "sent": broker_id,
                "qty": request.quantity,
                "price": str(request.price),
                "resend": resend,
            }
        )
        try:  # a marketable limit usually fills at once: read it now rather than next tick
            view = self.client.order(broker_id)
            row = live_repo.get_broker_order(self.conn, order_id)
            if row is not None:
                self._record_view(row, view)
        except TossError:
            return

    def _refused(self, order_id: int, request: OrderRequest, exc: TossApiError) -> None:
        code = exc.code
        with transaction(self.conn):
            if code == "request-in-progress" or exc.status >= 500 or exc.status == 429:
                live_repo.mark_unknown(self.conn, order_id, code, str(exc), self.now())
                outcome = "unknown"
            elif code == "order-hours-closed":
                retry_after = _when(exc.data.get("retryAfterAt"))
                live_repo.record_not_sent(
                    self.conn,
                    order_id=order_id,
                    ledger_id=LIVE,
                    client_order_id=request.client_order_id,
                    code=code,
                    detail=exc.message,
                    at=self.now(),
                    request=request,
                    retry_after=retry_after,
                )
                outcome = "order-hours-closed"
            elif exc.status in (401, 403) or link_state(exc) in ("ip", "auth"):
                live_repo.record_not_sent(
                    self.conn,
                    order_id=order_id,
                    ledger_id=LIVE,
                    client_order_id=request.client_order_id,
                    code="link",
                    detail=str(exc),
                    at=self.now(),
                    request=request,
                )
                outcome = "link"
            else:
                live_repo.mark_rejected(
                    self.conn, order_id, code, exc.message or str(exc), self.now()
                )
                outcome = "rejected"
        self.changes.append({"order_id": order_id, "refused": code, "outcome": outcome})

    # 5. once a day
    def daily(
        self, before: BrokerStatus | None
    ) -> tuple[dict[str, str], dict[str, Decimal], datetime | None]:
        instruments = live.rule_instruments(self.conn)
        if (
            before is not None
            and before.tradable_at is not None
            and kst_date(before.tradable_at) == kst_date(self.now())
            and set(before.tradable) == set(instruments)
        ):
            return before.tradable, before.commissions, before.tradable_at
        infos = self.client.stocks([i.ticker for i in instruments.values()])
        tradable: dict[str, str] = {}
        for iid, inst in instruments.items():
            info = infos.get(inst.ticker)
            if info is None:
                tradable[iid] = "not-found"
            elif info.currency is not inst.currency:
                tradable[iid] = "currency"
            elif info.status != "ACTIVE":
                tradable[iid] = "inactive"
            elif info.liquidation:
                tradable[iid] = "liquidation"
            elif info.suspended:
                tradable[iid] = "suspended"
            else:
                tradable[iid] = "ok"
        return tradable, self.client.commissions(kst_date(self.now())), self.now()

    # 6. the account
    def snapshot(self) -> tuple[int, bool]:
        # Our orders already read as finished filled before these balances were read.
        known = {
            r.broker_order_id
            for r in live_repo.broker_orders_of(self.conn, LIVE, ["done"])
            if r.broker_order_id is not None
        }
        open_before = self.client.orders("OPEN")
        holdings = self.client.holdings()
        read_at = self.now()
        cash = {c: self.client.buying_power(c) for c in Currency}
        closed = self.client.orders("CLOSED", start=self._closed_since())
        open_after = self.client.orders("OPEN")
        # A refused cancel or change is a record of its own; the order it was about keeps its
        # fills (openapi.json OrderStatus): never a trade of the account.
        filled = [o for o in closed if o.filled_qty > 0 and o.status not in REQUEST_RECORDS]
        # A fill the balances may not include yet (it ended as they were read): look again.
        late = any(
            o.order_id not in known
            and o.filled_at is not None
            and o.filled_at >= read_at - FILLED_AFTER_READ
            for o in filled
        )
        quiet = not open_before and not open_after and not late
        ours = live_repo.our_broker_ids(self.conn)
        theirs = [o for o in filled if o.order_id not in ours]
        with transaction(self.conn):
            snapshot_id = live_repo.record_snapshot(
                self.conn, read_at, cash, holdings, theirs, quiet
            )
            live_repo.prune_snapshots(self.conn, read_at - SNAPSHOT_KEEP)
        return snapshot_id, quiet

    def conditional_orders(self) -> None:
        """Armed 조건주문 (the old quant's, the app's) place orders of their own: turning live on
        waits until none is open (engine/live.py link_check). Read after the account's snapshot
        is stored, so a failure here (the link's state, like any read) never costs the snapshot
        the reconciliation needs."""
        self.conditional = self.client.conditional_orders("OPEN")

    def _closed_since(self) -> date:
        """The closed orders the reconciliation still needs: since the last one that matched
        (a day earlier, orders are dated in KST), or since the live ledger's start; today before
        a start. Not since the last attempt: one that found the account busy or not matching
        booked nothing, and days of them (the first key out of cron, Toss unreachable, an order
        open) must not let the owner's app fills drop out of the list."""
        today = kst_date(self.now())
        status = live_repo.get_status(self.conn)
        start = repo.start_event(self.conn, LIVE)
        if status is not None and status.matched_at is not None and start is not None:
            return max(kst_date(status.matched_at), start.event_date) - timedelta(days=1)
        if start is not None:
            return start.event_date - timedelta(days=1)
        return today


def _when(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return from_iso(str(value))
    except ValueError:
        return None


def _off_status(
    conn: Any,
    cfg: Config,
    before: BrokerStatus | None,
    at: datetime,
    state: str,
    detail: str | None,
) -> bool:
    """Record a link that is not up. Returns whether it changed (to log it once)."""
    status = BrokerStatus(
        state=state,
        env_live=cfg.live_orders and env_live(),
        checked_at=at,
        ok_at=None if before is None else before.ok_at,
        account_seq=None if before is None else before.account_seq,
        account_tail=None if before is None else before.account_tail,
        tradable={} if before is None else before.tradable,
        tradable_at=None if before is None else before.tradable_at,
        commissions={} if before is None else before.commissions,
        revoked=0,
        key_expires=cfg.toss_key_expires,
        detail=detail,
        reconcile_state=None if before is None else before.reconcile_state,
        reconciled_at=None if before is None else before.reconciled_at,
        reconcile_detail={} if before is None else before.reconcile_detail,
        matched_at=None if before is None else before.matched_at,
        conditional=None if before is None else before.conditional,
    )
    with transaction(conn):
        live_repo.save_status(conn, status, at)
    if before is None:
        return state != "off"  # a link never asked for is no news
    return before.state != state or before.env_live != status.env_live


def broker_job(
    conn: Any,
    cfg: Config,
    at: datetime,
    *,
    transport: Transport | None = None,
    now: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """The tick's Toss sync (module docstring). 'quiet' when nothing changed."""
    require_aware(at)
    wall = now or (lambda: at)
    base: dict[str, Any] = {"job": "broker", "ledger": LIVE, "at": at}
    before = live_repo.get_status(conn)
    if not cfg.live_orders or not env_live():
        changed = _off_status(conn, cfg, before, at, "off", "AUTOTRADE_LIVE_ORDERS is not 1")
        return {**base, "result": "off" if changed else "quiet"}
    try:
        client = make_client(cfg, transport)
        client.sleep = sleep
        client.limiter.sleep = sleep
        seq, tail = client.account()
    except TossError as exc:
        state = link_state(exc)
        changed = _off_status(conn, cfg, before, at, state, str(exc))
        return {**base, "result": state if changed else "quiet", "error": str(exc)}
    sync = Sync(conn, cfg, client, at, wall)
    state, detail = "ok", None
    # What a step that fails leaves: the last known daily facts, no snapshot.
    tradable = {} if before is None else before.tradable
    commissions = {} if before is None else before.commissions
    tradable_at = None if before is None else before.tradable_at
    snapshot_id: int | None = None
    quiet = False
    try:
        sync.poll()
        sync.recover()
        sync.cancels()
        sync.send_due()
        tradable, commissions, tradable_at = sync.daily(before)
        snapshot_id, quiet = sync.snapshot()
        sync.conditional_orders()
    except TossError as exc:
        state, detail = link_state(exc), str(exc)
    ok = state == "ok"
    latest = live_repo.get_status(conn)  # the reconciliation may have written meanwhile
    status = BrokerStatus(
        state=state,
        env_live=True,
        checked_at=wall(),
        ok_at=wall() if ok else (None if before is None else before.ok_at),
        account_seq=seq,
        account_tail=tail,
        tradable=tradable,
        tradable_at=tradable_at,
        commissions=commissions,
        revoked=client.revoked,
        revoked_at=wall() if client.revoked else (None if before is None else before.revoked_at),
        key_expires=cfg.toss_key_expires,
        detail=detail if detail else ("; ".join(sync.errors)[:400] or None),
        reconcile_state=None if latest is None else latest.reconcile_state,
        reconciled_at=None if latest is None else latest.reconciled_at,
        reconcile_detail={} if latest is None else latest.reconcile_detail,
        matched_at=None if latest is None else latest.matched_at,
        conditional=[c.to_json() for c in sync.conditional]
        if sync.conditional is not None
        else (None if before is None else before.conditional),
    )
    with transaction(conn):
        live_repo.save_status(conn, status, at)
    noteworthy = (
        sync.changes
        or sync.errors
        or not ok
        or client.revoked
        or before is None
        or before.state != state
        or (status.conditional or []) != (before.conditional or [])
    )
    out: dict[str, Any] = {
        **base,
        "result": ("synced" if ok else state) if noteworthy else "quiet",
        "changes": sync.changes,
        "snapshot_id": snapshot_id,
        "quiet_account": quiet,
    }
    if sync.errors or detail:
        out["error"] = detail or "; ".join(sync.errors)[:400]
    if client.revoked:
        out["token_revoked"] = client.revoked
    return out


def reconcile_job(conn: Any, cfg: Config, at: datetime, *, dry_run: bool = False) -> dict[str, Any]:
    """Match the live ledger with the latest snapshot (engine/live.py). Logged when it booked
    something or found a mismatch."""
    require_aware(at)
    before = live_repo.get_status(conn)
    with transaction(conn, rollback=dry_run):
        result = live.reconcile(conn, cfg, at)
    base: dict[str, Any] = {"job": "reconcile", "ledger": LIVE, "at": at}
    changed = before is None or before.reconcile_state != result.state
    if result.state == "busy" or (result.state == "match" and not result.booked and not changed):
        return {**base, "result": "quiet", "state": result.state, "reason": result.reason}
    return {
        **base,
        "result": result.state,
        "reason": result.reason,
        "booked": result.booked,
        "detail": result.detail,
    }


# ── the server's read-only check (PHASE3.md 5) ───────────────────────────────────────────


def toss_check(
    cfg: Config, conn: Any, *, transport: Transport | None = None, today: date | None = None
) -> dict[str, Any]:
    """Read the account once and print what the engine would rely on. Reads only: there is no
    order or cancel call in it. Secrets and tokens are never printed. `today` (KST) picks the
    commission rows in force (default: the wall clock's day)."""
    out: dict[str, Any] = {"job": "toss-check", "result": "ok"}
    day = today or datetime.now(KST).date()
    try:
        client = make_client(cfg, transport)
        client.token()
        out["token"] = "ok"
        seq, tail = client.account(force=True)
        out["account"] = {"seq": seq, "tail": tail, "type": "BROKERAGE"}
        out["cash"] = {c.value: str(client.buying_power(c)) for c in Currency}
        out["holdings"] = [
            {"id": h.instrument_id, "name": h.name, "qty": str(h.qty)} for h in client.holdings()
        ]
        out["openOrders"] = len(client.orders("OPEN"))
        # Armed 조건주문 do not show as open orders until they fire (the old quant's, the app's):
        # each must be cancelled in the Toss app before live is turned on (PHASE3.md 4).
        conditional = client.conditional_orders("OPEN")
        out["conditionalOrders"] = len(conditional)
        if conditional:
            out["conditional"] = [
                {"symbol": c.symbol, "market": c.market, "type": c.type, "status": c.status}
                for c in conditional
            ]
        out["commissions"] = {k: str(v) for k, v in client.commissions(day).items()}
        instruments = live.rule_instruments(conn)
        infos = client.stocks([i.ticker for i in instruments.values()])
        quotes = client.prices([i.ticker for i in instruments.values()])
        out["instruments"] = {}
        for iid, inst in instruments.items():
            info = infos.get(inst.ticker)
            quote = quotes.get(inst.ticker)
            out["instruments"][iid] = (
                {"found": False}
                if info is None
                else {
                    "name": info.name,
                    "market": info.market,
                    "status": info.status,
                    "securityType": info.security_type,
                    "currency": info.currency.value,
                    "tradable": info.tradable and info.currency is inst.currency,
                    "price": None if quote is None else str(quote.price),
                }
            )
        out["calendar"] = {
            "KR": client.market_calendar("KR").get("today"),
            "US": client.market_calendar("US").get("today"),
        }
        fx = client.exchange_rate()
        out["fx"] = {"rate": str(fx.rate), "midRate": str(fx.mid_rate)}
        if client.revoked:
            out["tokenRevoked"] = client.revoked
    except TossError as exc:
        out["result"] = "failed"
        out["cause"] = link_state(exc)
        out["error"] = str(exc)
    return out
