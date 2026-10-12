"""The live ledger against the Toss account (autotrade/PHASE3.md 2.5-2.7).

The account is the truth. This module holds what the engine does with what the tick's Toss sync
recorded (broker_status, broker_snapshots, broker_orders); it never calls Toss:

- start_live: the live ledger starts from the account shown in the preview the owner approved
  (its cash, and the rule's instruments it holds, at their price then: no gain at the start).
- reconcile: before every plan (and whenever the account is quiet), the ledger is matched with
  the snapshot. What the broker did for our orders is booked first (late fills); then the
  account's fills the engine did not send (the owner's trades in the app, PHASE3.md 2.5); then
  the cash nothing explains: a conversion (won and dollars in opposite directions at the market
  rate), a dividend the ledger is owed, a deposit, a withdrawal. Last, the rule's holdings must
  equal the broker's. Anything that does not fit is a mismatch: nothing is written (savepoint),
  a red manual to-do shows it and no plan is made until it is fixed or `adopt-broker` accepts
  the broker's numbers.
- preview: the first orders the rule would send for the account as it is, for the mode screen;
  the hash and total are kept so that turning live on can tell a changed preview (인계 13).
- turn_on / turn_off: the mode switch's database side (the web service runs it; the cancels at
  the broker are the tick's, as requests).
- link_check and live_todos: what the mode and health screens show of the Toss link.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from autotrade.broker.base import FxFilled
from autotrade.broker.toss import TossExecutor, fill_of
from autotrade.broker.toss_api import BrokerHolding, BrokerOrder
from autotrade.config import Config
from autotrade.db import ai_repo, live_repo, repo
from autotrade.db.connection import dumps
from autotrade.db.live_repo import AccountSnapshot, NewExternalFill
from autotrade.db.models import DividendRow, OrderRow
from autotrade.domain.dividends import after_tax
from autotrade.domain.instruments import Currency, Instrument
from autotrade.domain.ledger import (
    CashFlowKind,
    LedgerError,
    Position,
    TradeFill,
    apply_cash_flow,
    apply_trade,
    opening_state,
)
from autotrade.domain.money import CENT, WON, ZERO, round_won, usd_in_krw
from autotrade.domain.planner import FxDirection, Plan, PlanInput, PlanItem, Side, plan_rule
from autotrade.domain.stages import StageSpec, schedule, stage_specs
from autotrade.engine import runner, sleeves
from autotrade.engine.bootstrap import MODE
from autotrade.engine.common import (
    load_rule,
    refresh_cash_parts,
    slotter_for,
    withdraw_wait_amounts,
)
from autotrade.engine.dividends import dividend_ref, shares_before_ex_date, tax_rate
from autotrade.engine.status import next_check_at
from autotrade.market.calendar import KRX
from autotrade.market.service import latest_close, market_freshness, rate_freshness
from autotrade.market.types import FxQuote
from autotrade.rules.index_half import RULE_ID
from autotrade.timeutil import kst_date, require_aware, to_iso

LIVE = "live"
MODE_CHANGED_AT = "mode.changed_at"
RECONCILE_JOB = "reconcile"
DIVIDEND_WINDOW_BEFORE = timedelta(days=21)  # a dividend paid this long ago may still arrive
DIVIDEND_WINDOW_AFTER = timedelta(days=3)  # an estimated pay date can be early
DIVIDEND_MIN_SHARE = Decimal("0.5")  # cash of at least half the expected net is that dividend
WITHDRAW_TRADING_DAYS = 2  # 인계 5: settlement date + 2 business days
KEY_EXPIRY_WARN_DAYS = 14
# The payload reason of the two events a conversion no plan asked for makes (api/views/accounts.py
# reads them as a transfer between the accounts, not money in or out).
CONVERSION = "conversion"


# ── the start ────────────────────────────────────────────────────────────────────────────


class LiveStartError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


def rule_instruments(conn: sqlite3.Connection) -> dict[str, Instrument]:
    rule, instruments = load_rule(conn, RULE_ID)
    return {iid: instruments[iid] for iid in rule.instrument_ids}


def _unit(currency: Currency) -> Decimal:
    return WON if currency is Currency.KRW else CENT


@dataclass(frozen=True)
class Opening:
    cash: dict[Currency, Decimal]
    positions: dict[str, Position]
    contributions_krw: Decimal
    rate: Decimal | None
    outside: list[BrokerHolding]

    def by_currency(self) -> dict[Currency, Decimal]:
        """The start in each currency: its cash and its holdings at their start value (won for
        한국 계좌, dollars for 미국 계좌: api/views/accounts.py)."""
        out = dict(self.cash)
        for p in self.positions.values():
            out[p.currency] = out.get(p.currency, ZERO) + p.cost_native
        return out


def opening_from(
    snapshot: AccountSnapshot, instruments: dict[str, Instrument], rate: Decimal | None
) -> Opening:
    """What a live ledger started now would hold: the cash, and the rule's instruments at their
    price in the snapshot (cost = value: the ledger starts at no gain)."""
    positions: dict[str, Position] = {}
    outside: list[BrokerHolding] = []
    total = snapshot.cash_of(Currency.KRW)
    usd_cash = snapshot.cash_of(Currency.USD)
    needs_rate = usd_cash > 0
    for h in snapshot.holdings:
        inst = instruments.get(h.instrument_id)
        if inst is None:
            outside.append(h)
            continue
        if h.qty != h.qty.to_integral_value():
            raise LiveStartError("fractional", f"{h.instrument_id}: {h.qty} shares")
        qty = int(h.qty)
        if qty <= 0:
            continue
        price = h.last_price if h.last_price > 0 else h.avg_price
        if price <= 0:
            raise LiveStartError("no-price", f"{h.instrument_id}: no price")
        cost = (price * qty).quantize(_unit(inst.currency), rounding=ROUND_HALF_UP)
        if inst.currency is Currency.USD:
            needs_rate = True
            if rate is None:
                raise LiveStartError("no-rate", "no exchange rate to value dollars")
            cost_krw = usd_in_krw(cost, rate)
        else:
            cost_krw = cost
        positions[inst.instrument_id] = Position(
            inst.instrument_id, inst.currency, qty, cost, cost_krw
        )
        total += cost_krw
    if needs_rate and rate is None:
        raise LiveStartError("no-rate", "no exchange rate to value dollars")
    if usd_cash > 0 and rate is not None:
        total += usd_in_krw(usd_cash, rate)
    if total <= 0:
        raise LiveStartError("empty", "the account holds no cash and none of the rule's shares")
    cash = {Currency.KRW: snapshot.cash_of(Currency.KRW), Currency.USD: usd_cash}
    return Opening(cash, positions, total, rate, outside)


def start_live(
    conn: sqlite3.Connection, cfg: Config, snapshot: AccountSnapshot, at: datetime
) -> int:
    """Start the live ledger from the account in `snapshot` (PHASE3.md 2.6). The caller owns the
    transaction. The start is as of the snapshot's time: anything after it is the next
    reconciliation's."""
    require_aware(at)
    if repo.start_event(conn, LIVE) is not None:
        raise LiveStartError("started", "the live ledger has started already")
    quote = repo.fx_at(conn, snapshot.taken_at) or repo.fx_at(conn, at)
    opening = opening_from(snapshot, rule_instruments(conn), None if quote is None else quote.rate)
    state = opening_state(opening.cash, opening.positions, opening.contributions_krw)
    as_of = snapshot.taken_at
    repo.save_state(conn, LIVE, state, at)
    payload: dict[str, Any] = {
        "amount": opening.contributions_krw,
        "opening": {
            "cash": {c.value: v for c, v in opening.cash.items()},
            "positions": [
                {
                    "instrument_id": p.instrument_id,
                    "currency": p.currency.value,
                    "qty": p.qty,
                    "cost_native": p.cost_native,
                    "cost_krw": p.cost_krw,
                }
                for p in opening.positions.values()
            ],
        },
        "outside": [h.to_json() for h in opening.outside],
        "snapshot_id": snapshot.snapshot_id,
        "turned_on_at": at,
        "source": "broker",
    }
    if opening.rate is not None:
        payload["krw_rate"] = opening.rate
    split = opening.by_currency()
    if split.get(Currency.USD, ZERO) > 0:
        # The start is in won (the ledger's start amount); the accounts need what each currency
        # brought: 한국 계좌 its won, 미국 계좌 its dollars (api/views/accounts.py Accounts.flows).
        payload["by_currency"] = {c.value: split.get(c, ZERO) for c in Currency}
    event_id = repo.insert_event(
        conn,
        ledger_id=LIVE,
        kind="start",
        event_date=kst_date(as_of),
        occurred_at=as_of,
        amount=opening.contributions_krw,
        currency=Currency.KRW,
        payload=payload,
    )
    # The rules' shares of the cash (the live AI share is 0: nothing moves today).
    for currency, amount in opening.cash.items():
        if amount > 0:
            sleeves.split_inflow(
                conn,
                LIVE,
                CashFlowKind.START,
                amount,
                currency,
                opening.rate if currency is Currency.USD else None,
                event_id,
                as_of,
            )
    repo.mark_ledger_started(conn, LIVE, kst_date(as_of), opening.contributions_krw, at)
    refresh_cash_parts(conn, LIVE, at)
    return event_id


# ── the reconciliation ───────────────────────────────────────────────────────────────────


class _MismatchError(Exception):
    def __init__(self, reason: str, detail: dict[str, Any]) -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


class _BusyError(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass
class ReconcileResult:
    state: str  # 'match' | 'mismatch' | 'busy' | 'skipped'
    reason: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    booked: list[dict[str, Any]] = field(default_factory=list)  # what it wrote, for the log
    snapshot_id: int | None = None

    @property
    def ok(self) -> bool:
        return self.state == "match"


def busy_reason(
    conn: sqlite3.Connection, cfg: Config, snap: AccountSnapshot | None, at: datetime
) -> str | None:
    """Why the account cannot be read as the truth right now (None = it can)."""
    if snap is None:
        return "no-snapshot"
    if at - snap.confirmed_at > cfg.broker_max_age:
        return "old-snapshot"
    if not snap.quiet:
        return "orders-open"
    if live_repo.broker_orders_of(conn, LIVE, live_repo.OPEN_STATES):
        return "orders-in-flight"
    return None


def reconcile(
    conn: sqlite3.Connection,
    cfg: Config,
    at: datetime,
    *,
    snapshot: AccountSnapshot | None = None,
) -> ReconcileResult:
    """Match the live ledger with the account. The caller owns the transaction; on a mismatch
    nothing is written but the status (savepoint)."""
    require_aware(at)
    start = repo.start_event(conn, LIVE)
    if start is None:
        return ReconcileResult("skipped", "not-started")
    snap = snapshot or live_repo.latest_snapshot(conn)
    reason = busy_reason(conn, cfg, snap, at)
    if reason is not None or snap is None:
        result = ReconcileResult("busy", reason or "no-snapshot")
        _record(conn, at, result)
        return result
    conn.execute("SAVEPOINT live_reconcile")
    try:
        result = _reconcile_body(conn, cfg, at, snap, start.occurred_at)
    except _MismatchError as exc:
        conn.execute("ROLLBACK TO live_reconcile")
        conn.execute("RELEASE live_reconcile")
        result = ReconcileResult("mismatch", exc.reason, exc.detail, snapshot_id=snap.snapshot_id)
    except _BusyError as exc:
        conn.execute("ROLLBACK TO live_reconcile")
        conn.execute("RELEASE live_reconcile")
        result = ReconcileResult("busy", exc.reason, snapshot_id=snap.snapshot_id)
    else:
        conn.execute("RELEASE live_reconcile")
    _record(conn, at, result)
    return result


def _record(conn: sqlite3.Connection, at: datetime, result: ReconcileResult) -> None:
    status = live_repo.get_status(conn)
    if status is not None:
        status = replace(
            status,
            reconcile_state=result.state if result.state != "skipped" else None,
            reconciled_at=at,
            reconcile_detail={"reason": result.reason, **result.detail},
        )
        live_repo.save_status(conn, status, at)
    if result.state != "busy" or result.reason not in ("orders-open", "orders-in-flight"):
        ai_repo.insert_job_run(
            conn,
            job=RECONCILE_JOB,
            ledger_id=LIVE,
            run_date=kst_date(at),
            started_at=at,
            ended_at=at,
            result=result.state,
            error=result.reason if result.state in ("mismatch", "busy") else None,
            details={
                "snapshot_id": result.snapshot_id,
                "booked": result.booked,
                **result.detail,
            },
        )


def ledger_instrument_ids(conn: sqlite3.Connection) -> set[str]:
    """The live ledger's own instruments: the rule's, and whatever it holds."""
    out = set(rule_instruments(conn))
    out |= set(repo.load_state(conn, LIVE).positions)
    return out


def _reconcile_body(
    conn: sqlite3.Connection,
    cfg: Config,
    at: datetime,
    snap: AccountSnapshot,
    started_at: datetime,
) -> ReconcileResult:
    result = ReconcileResult("match", snapshot_id=snap.snapshot_id)
    result.booked.extend(book_late_fills(conn, cfg, at))
    own = ledger_instrument_ids(conn)
    ours = live_repo.our_broker_ids(conn)
    seen = live_repo.external_broker_ids(conn, LIVE)
    closed = sorted(
        (o for o in snap.closed_orders if o.filled_at is not None and o.filled_qty > 0),
        key=lambda o: (o.filled_at or at, o.order_id),
    )
    for order in closed:
        if order.order_id in ours or order.order_id in seen:
            continue
        if order.filled_at is None or order.filled_at <= started_at:
            continue  # part of the account the ledger started from
        result.booked.append(_book_external_trade(conn, cfg, at, order, own))
    state = repo.load_state(conn, LIVE)
    residual = {c: snap.cash_of(c) - state.cash_of(c) for c in Currency}
    residual = _book_conversion(conn, cfg, at, snap, residual, result)
    seen_at = snap.taken_at  # the best-known time the money arrived or left
    for currency in Currency:
        amount = residual[currency]
        if amount > 0:
            amount = _book_dividends(conn, cfg, at, currency, amount, started_at, result, seen_at)
        if amount > 0:
            event_id = _flow(
                conn,
                at,
                CashFlowKind.DEPOSIT,
                amount,
                currency,
                {"reason": "unexplained-in"},
                occurred_at=seen_at,
            )
            result.booked.append(
                {"deposit": str(amount), "currency": currency.value, "event_id": event_id}
            )
        elif amount < 0:
            event_id = _flow(
                conn,
                at,
                CashFlowKind.WITHDRAWAL,
                -amount,
                currency,
                {"reason": "unexplained-out"},
                occurred_at=seen_at,
            )
            _consume_withdraw_waits(conn, currency, -amount, at)
            result.booked.append(
                {"withdrawal": str(-amount), "currency": currency.value, "event_id": event_id}
            )
    _check_positions(conn, snap, own)
    refresh_cash_parts(conn, LIVE, at)
    return result


def book_late_fills(conn: sqlite3.Connection, cfg: Config, at: datetime) -> list[dict[str, Any]]:
    """Fills the broker reported for our orders that the ledger has not booked: after the plan
    was closed (live off, a resolved to-do), or before the stage runner got to them. An order
    that ended with nothing filled and whose plan is closed is marked cancelled."""
    out: list[dict[str, Any]] = []
    for row in live_repo.broker_orders_of(conn, LIVE, ["done"]):
        order = repo.get_order(conn, row.order_id)
        filled = fill_of(row)
        if filled is not None:
            booked = runner.book_fill(conn, cfg, LIVE, order, filled, TossExecutor.name, at)
            if booked is not None:
                out.append({"late_fill": order.order_id, "qty": filled.qty})
            continue
        if order.status == "pending" and repo.get_plan(conn, order.plan_id).status not in (
            repo.OPEN_PLAN_STATUSES
        ):
            repo.cancel_order(conn, order.order_id)
    return out


def withdraw_until(settlement: date | None, filled: date) -> date:
    """인계 5: proceeds of a sale in the app wait until the settlement date + 2 business days
    (Korean trading days; without a settlement date, T+2 from the fill)."""
    d = settlement
    if d is None:
        d = filled
        for _ in range(2):
            d = KRX.next_trading_day(d)
    for _ in range(WITHDRAW_TRADING_DAYS):
        d = KRX.next_trading_day(d)
    return d


def _rate(conn: sqlite3.Connection, when: datetime, at: datetime) -> Decimal:
    quote = repo.fx_at(conn, when) or repo.fx_at(conn, at)
    if quote is None:
        raise _BusyError("no-rate")
    return quote.rate


def _book_external_trade(
    conn: sqlite3.Connection,
    cfg: Config,
    at: datetime,
    order: BrokerOrder,
    own: set[str],
) -> dict[str, Any]:
    """A fill the engine did not send (the owner's, in the app or WTS)."""
    when = order.filled_at or at
    qty = order.filled_qty
    gross = order.filled_amount
    if gross is None and order.avg_price is not None:
        gross = order.avg_price * qty
    if gross is None or gross <= 0:
        raise _MismatchError("external-fill", {"order": order.order_id, "why": "no amount"})
    fee = (order.commission or ZERO) + (order.tax or ZERO)
    currency = order.currency
    rate = _rate(conn, when, at) if currency is Currency.USD else None
    fee_krw = fee if rate is None else usd_in_krw(fee, rate)
    side = Side.BUY if order.side == "BUY" else Side.SELL
    iid = order.instrument_id
    base: dict[str, Any] = {
        "external": order.order_id,
        "instrument_id": iid,
        "side": side.value,
        "qty": str(qty),
        "gross": str(gross),
        "fee": str(fee),
    }
    if iid in own:
        if qty != qty.to_integral_value():
            raise _MismatchError("fractional", {"instrument_id": iid, "qty": str(qty)})
        if sleeves.sleeve_rule_ids(conn, LIVE):
            raise _MismatchError("sleeves", {"instrument_id": iid})
        trade = TradeFill(iid, currency, side, int(qty), gross / qty, fee, rate, gross)
        try:
            state = apply_trade(repo.load_state(conn, LIVE), trade)
        except LedgerError as exc:
            raise _MismatchError("external-fill", {"instrument_id": iid, "why": str(exc)}) from exc
        repo.save_state(conn, LIVE, state, at)
        live_repo.insert_external(
            conn,
            NewExternalFill(
                ledger_id=LIVE,
                broker_order_id=order.order_id,
                kind="trade",
                treatment="ledger",
                instrument_id=iid,
                symbol=order.symbol,
                name=None,
                side=side.value,
                currency=currency,
                qty=int(qty),
                gross=gross,
                fee=fee,
                fee_krw=fee_krw,
                krw_rate=rate,
                received=None,
                filled_at=when,
                settlement_date=order.settlement_date,
            ),
            at,
        )
        if side is Side.SELL:
            until = withdraw_until(order.settlement_date, kst_date(when))
            repo.add_withdraw_wait(conn, LIVE, currency, gross - fee, until, at)
            base["withdraw_wait_until"] = until.isoformat()
        return base
    # Outside the rules: the money leaves the ledger for that holding, or comes back from it.
    if side is Side.BUY:
        event_id = _flow(
            conn,
            at,
            CashFlowKind.WITHDRAWAL,
            gross + fee,
            currency,
            {"reason": "outside-buy", "instrument_id": iid, "broker_order_id": order.order_id},
            rate=rate,
            occurred_at=when,
        )
        _consume_withdraw_waits(conn, currency, gross + fee, at)
    else:
        event_id = _flow(
            conn,
            at,
            CashFlowKind.DEPOSIT,
            gross - fee,
            currency,
            {"reason": "outside-sell", "instrument_id": iid, "broker_order_id": order.order_id},
            rate=rate,
            occurred_at=when,
        )
        until = withdraw_until(order.settlement_date, kst_date(when))
        repo.add_withdraw_wait(conn, LIVE, currency, gross - fee, until, at)
        base["withdraw_wait_until"] = until.isoformat()
    live_repo.insert_external(
        conn,
        NewExternalFill(
            ledger_id=LIVE,
            broker_order_id=order.order_id,
            kind="trade",
            treatment="outside",
            instrument_id=iid,
            symbol=order.symbol,
            name=None,
            side=side.value,
            currency=currency,
            qty=None,
            gross=gross,
            fee=fee,
            fee_krw=fee_krw,
            krw_rate=rate,
            received=None,
            filled_at=when,
            settlement_date=order.settlement_date,
            event_id=event_id,
        ),
        at,
    )
    base["outside"] = True
    base["event_id"] = event_id
    return base


def _flow(
    conn: sqlite3.Connection,
    at: datetime,
    kind: CashFlowKind,
    amount: Decimal,
    currency: Currency,
    extra: dict[str, Any],
    *,
    rate: Decimal | None = None,
    occurred_at: datetime | None = None,
) -> int:
    """A deposit or withdrawal the account shows (an event, as the screens list them), in its
    own currency, at the best-known time the money moved (`occurred_at`: the fill's time for a
    trade in the app, else the account snapshot that first showed it); booked at `at`."""
    when = occurred_at or at
    if currency is Currency.USD and rate is None:
        rate = _rate(conn, when, at)
    try:
        state = apply_cash_flow(repo.load_state(conn, LIVE), kind, amount, currency, rate)
    except LedgerError as exc:
        raise _MismatchError(
            "cash", {"currency": currency.value, "amount": str(amount), "why": str(exc)}
        ) from exc
    repo.save_state(conn, LIVE, state, at)
    payload: dict[str, Any] = {"source": "broker", "amount": amount, **extra}
    if rate is not None:
        payload["krw_rate"] = rate
        payload["amount_krw"] = usd_in_krw(amount, rate)
    event_id = repo.insert_event(
        conn,
        ledger_id=LIVE,
        kind=kind.value,
        event_date=kst_date(when),
        occurred_at=when,
        amount=amount,
        currency=currency,
        payload=payload,
    )
    sleeves.split_inflow(conn, LIVE, kind, amount, currency, rate, event_id, at)
    return event_id


def _consume_withdraw_waits(
    conn: sqlite3.Connection, currency: Currency, amount: Decimal, at: datetime
) -> None:
    """A withdrawal takes the cash that waited for it first (인계 14: a net withdrawal)."""
    left = amount
    rows = conn.execute(
        "SELECT pending_id, amount FROM pending_cash WHERE ledger_id = ? AND currency = ?"
        " AND purpose = 'withdraw_wait' ORDER BY until_date, pending_id",
        (LIVE, currency.value),
    ).fetchall()
    for row in rows:
        if left <= 0:
            break
        have = Decimal(str(row["amount"]))
        take = min(have, left)
        left -= take
        if take == have:
            conn.execute("DELETE FROM pending_cash WHERE pending_id = ?", (int(row["pending_id"]),))
        else:
            conn.execute(
                "UPDATE pending_cash SET amount = ?, updated_at = ? WHERE pending_id = ?",
                (str(have - take), to_iso(at), int(row["pending_id"])),
            )


def _pending_fx_order(conn: sqlite3.Connection, direction: FxDirection) -> OrderRow | None:
    for order in repo.pending_orders(conn, LIVE):
        if order.side != "fx" or order.fx_direction != direction.value:
            continue
        if repo.get_plan(conn, order.plan_id).status in repo.OPEN_PLAN_STATUSES:
            return order
    return None


def _book_conversion(
    conn: sqlite3.Connection,
    cfg: Config,
    at: datetime,
    snap: AccountSnapshot,
    residual: dict[Currency, Decimal],
    result: ReconcileResult,
) -> dict[Currency, Decimal]:
    """Won and dollars that moved in opposite directions at about the market rate: the owner
    converted in the app (PHASE3.md 2.4). The conversion the plan waits for gets it as its fill
    (an fx fill of its fx order, executed at the snapshot that showed it: exactly a paper
    conversion). One no plan asked for is the owner's money moving between the two accounts:
    a withdrawal from the source currency and a deposit into the target one, at the rate it
    was made (so the ledger's P&L moves as for a fill), marked as a conversion (a fill needs an
    order of a plan, and Toss's API never converts for an order of ours, PHASE3.md 1.1)."""
    krw, usd = residual[Currency.KRW], residual[Currency.USD]
    if not ((krw < 0 < usd) or (usd < 0 < krw)):
        return residual
    quote = repo.fx_at(conn, at)
    if quote is None:
        return residual
    implied = abs(krw) / abs(usd)
    if abs(implied / quote.rate - 1) > cfg.live_fx_tolerance:
        return residual
    rate = implied.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if krw < 0:
        direction, source, target = FxDirection.KRW_TO_USD, -krw, usd
    else:
        direction, source, target = FxDirection.USD_TO_KRW, -usd, krw
    order = _pending_fx_order(conn, direction)
    when = snap.taken_at
    if order is not None:
        runner.book_fill(
            conn,
            cfg,
            LIVE,
            order,
            FxFilled(source, target, rate, "owner:balances", filled_at=when),
            TossExecutor.name,
            at,
        )
        result.booked.append(
            {
                "conversion": direction.value,
                "from": str(source),
                "to": str(target),
                "order_id": order.order_id,
            }
        )
    else:
        extra: dict[str, Any] = {
            "reason": CONVERSION,
            "direction": direction.value,
            "from": source,
            "to": target,
            "rate": rate,
        }
        out_id = _flow(
            conn,
            at,
            CashFlowKind.WITHDRAWAL,
            source,
            direction.source,
            extra,
            rate=rate if direction.source is Currency.USD else None,
            occurred_at=when,
        )
        in_id = _flow(
            conn,
            at,
            CashFlowKind.DEPOSIT,
            target,
            direction.target,
            extra,
            rate=rate if direction.target is Currency.USD else None,
            occurred_at=when,
        )
        result.booked.append(
            {
                "conversion": direction.value,
                "from": str(source),
                "to": str(target),
                "event_ids": [out_id, in_id],
            }
        )
    return {Currency.KRW: ZERO, Currency.USD: ZERO}


@dataclass(frozen=True)
class DueDividend:
    div: DividendRow
    inst: Instrument
    qty: int
    gross: Decimal
    net: Decimal


def due_dividends(
    conn: sqlite3.Connection, cfg: Config, at: datetime, started: date
) -> list[DueDividend]:
    """Dividends the live ledger is owed around now and has not booked (from the dividend data
    the paper ledger's job downloads; Toss reports none)."""
    today = kst_date(at)
    held = {**rule_instruments(conn)}
    for iid in repo.load_state(conn, LIVE).positions:
        held.setdefault(iid, repo.get_instrument(conn, iid))
    out: list[DueDividend] = []
    rows = repo.dividends_paid(
        conn, sorted(held), today - DIVIDEND_WINDOW_BEFORE, today + DIVIDEND_WINDOW_AFTER
    )
    for div in rows:
        if div.ex_date <= started:
            continue
        if repo.event_by_ref(conn, LIVE, dividend_ref(div.instrument_id, div.ex_date)):
            continue
        inst = held[div.instrument_id]
        qty = shares_before_ex_date(conn, LIVE, inst, div.ex_date)
        if qty <= 0:
            continue
        amounts = after_tax(div.per_share, qty, inst.currency, tax_rate(cfg, inst.market))
        if amounts.net > 0:
            out.append(DueDividend(div, inst, qty, amounts.gross, amounts.net))
    return out


def _book_dividends(
    conn: sqlite3.Connection,
    cfg: Config,
    at: datetime,
    currency: Currency,
    amount: Decimal,
    started_at: datetime,
    result: ReconcileResult,
    seen: datetime,
) -> Decimal:
    """Unexplained cash of `currency` that a dividend the ledger is owed explains. The broker's
    amount is what counts (taxes withheld differ from the 15.4% estimate on Korean ETFs); the
    estimate only tells a dividend from a deposit. Dated `seen`, the snapshot that showed it.
    Returns what is left."""
    left = amount
    for due in due_dividends(conn, cfg, at, kst_date(started_at)):
        if due.inst.currency is not currency or left <= 0:
            continue
        if left < due.net * DIVIDEND_MIN_SHARE:
            continue
        booked = min(left, due.gross)
        rate = _rate(conn, seen, at) if currency is Currency.USD else None
        state = apply_cash_flow(
            repo.load_state(conn, LIVE), CashFlowKind.DIVIDEND, booked, currency, rate
        )
        repo.save_state(conn, LIVE, state, at)
        rule_ids = set(rule_instruments(conn))
        payload: dict[str, Any] = {
            "source": "broker",
            "instrument_id": due.inst.instrument_id,
            "ex_date": due.div.ex_date,
            "pay_date": due.div.pay_date,
            "per_share": due.div.per_share,
            "qty": due.qty,
            "expected_gross": due.gross,
            "expected_net": due.net,
            "net": booked,
            "amount_krw": booked if rate is None else usd_in_krw(booked, rate),
        }
        if rate is not None:
            payload["krw_rate"] = rate
        event_id = repo.insert_event(
            conn,
            ledger_id=LIVE,
            kind="dividend",
            event_date=kst_date(seen),
            occurred_at=seen,
            rule_id=RULE_ID if due.inst.instrument_id in rule_ids else None,
            amount=booked,
            currency=currency,
            ref=dividend_ref(due.inst.instrument_id, due.div.ex_date),
            payload=payload,
        )
        sleeves.split_dividend(
            conn,
            LIVE,
            due.inst.instrument_id,
            due.div.ex_date,
            due.qty,
            booked,
            currency,
            rate,
            event_id,
            at,
        )
        result.booked.append({"dividend": str(booked), "instrument_id": due.inst.instrument_id})
        left -= booked
    return left


def _check_positions(conn: sqlite3.Connection, snap: AccountSnapshot, own: set[str]) -> None:
    state = repo.load_state(conn, LIVE)
    broker = {h.instrument_id: h.qty for h in snap.holdings}
    off: list[dict[str, str]] = []
    for iid in sorted(own | set(state.positions)):
        ledger_qty = Decimal(state.qty_of(iid))
        broker_qty = broker.get(iid, ZERO)
        if ledger_qty != broker_qty:
            off.append({"instrument_id": iid, "ledger": str(ledger_qty), "broker": str(broker_qty)})
    if off:
        raise _MismatchError("positions", {"positions": off})


# ── adopting the broker's numbers ────────────────────────────────────────────────────────


def adopt_broker(
    conn: sqlite3.Connection, cfg: Config, at: datetime, note: str | None
) -> dict[str, Any]:
    """`python -m autotrade.jobs adopt-broker`: after a mismatch the owner checked (a split, a
    trade the API does not list, shares moved in), set the rule's holdings and the cash to the
    account's. Each difference is booked at today's price as money in or out (no gain), so the
    ledger's gains so far stay as they were. The caller owns the transaction."""
    snap = live_repo.latest_snapshot(conn)
    reason = busy_reason(conn, cfg, snap, at)
    if reason is not None or snap is None:
        return {"result": "busy", "reason": reason or "no-snapshot"}
    if repo.start_event(conn, LIVE) is None:
        return {"result": "not-started"}
    rate = _rate_or_none(conn, at)
    state = repo.load_state(conn, LIVE)
    own = ledger_instrument_ids(conn)
    broker = {h.instrument_id: h for h in snap.holdings}
    instruments = {iid: repo.get_instrument(conn, iid) for iid in own}
    changes: list[dict[str, Any]] = []
    positions = dict(state.positions)
    value_in = ZERO
    by_currency = dict.fromkeys(Currency, ZERO)  # money in per account, in its currency
    for iid in sorted(own):
        inst = instruments[iid]
        held = broker.get(iid)
        broker_qty = ZERO if held is None else held.qty
        if broker_qty != broker_qty.to_integral_value():
            return {"result": "refused", "reason": f"fractional {iid} {broker_qty}"}
        new_qty = int(broker_qty)
        old = positions.get(iid)
        old_qty = 0 if old is None else old.qty
        if new_qty == old_qty:
            continue
        price = None if held is None or held.last_price <= 0 else held.last_price
        if price is None:
            close = latest_close(conn, cfg, inst, at)
            if close is None:
                return {"result": "refused", "reason": f"no price for {iid}"}
            price = close.price
        delta = new_qty - old_qty
        value = (price * abs(delta)).quantize(_unit(inst.currency), rounding=ROUND_HALF_UP)
        value_krw = value
        if inst.currency is Currency.USD:
            if rate is None:
                return {"result": "refused", "reason": "no rate"}
            value_krw = usd_in_krw(value, rate)
        if new_qty == 0:
            positions.pop(iid, None)
        elif old is None or delta > 0:
            base = old or Position(iid, inst.currency, 0, ZERO, ZERO)
            positions[iid] = Position(
                iid, inst.currency, new_qty, base.cost_native + value, base.cost_krw + value_krw
            )
        else:
            keep = Decimal(new_qty) / Decimal(old_qty)
            positions[iid] = Position(
                iid,
                inst.currency,
                new_qty,
                old.cost_native * keep,
                round_won(old.cost_krw * keep),
            )
        value_in += value_krw if delta > 0 else -value_krw
        by_currency[inst.currency] += value if delta > 0 else -value
        changes.append({"instrument_id": iid, "from": old_qty, "to": new_qty, "krw": value_krw})
    cash_changes: dict[str, str] = {}
    new_cash = dict(state.cash)
    for currency in Currency:
        diff = snap.cash_of(currency) - state.cash_of(currency)
        if diff == 0:
            continue
        new_cash[currency] = snap.cash_of(currency)
        diff_krw = diff
        if currency is Currency.USD:
            if rate is None:
                return {"result": "refused", "reason": "no rate"}
            diff_krw = usd_in_krw(diff, rate)
        value_in += diff_krw
        by_currency[currency] += diff
        cash_changes[currency.value] = str(diff)
    if not changes and not cash_changes:
        return {"result": "nothing-to-adopt"}
    adopted = type(state)(
        cash=new_cash,
        positions=positions,
        realized_krw=state.realized_krw,
        fees_krw=state.fees_krw,
        contributions_krw=state.contributions_krw + value_in,
        income_krw=state.income_krw,
    )
    repo.save_state(conn, LIVE, adopted, at)
    kind = "deposit" if value_in >= 0 else "withdrawal"
    payload: dict[str, Any] = {
        "source": "adopt-broker",
        "adopt": {
            "positions": changes,
            "cash": cash_changes,
            "state": _state_json(adopted),
        },
        "note": note,
        "snapshot_id": snap.snapshot_id,
    }
    if by_currency[Currency.USD] != 0:
        # The event is the net won; the accounts need each currency's own (signed) amount.
        payload["by_currency"] = {c.value: v for c, v in by_currency.items()}
    event_id = repo.insert_event(
        conn,
        ledger_id=LIVE,
        kind=kind,
        event_date=kst_date(snap.taken_at),
        occurred_at=snap.taken_at,
        amount=abs(value_in),
        currency=Currency.KRW,
        payload=payload,
    )
    refresh_cash_parts(conn, LIVE, at)
    return {"result": "adopted", "event_id": event_id, "positions": changes, "cash": cash_changes}


def _rate_or_none(conn: sqlite3.Connection, at: datetime) -> Decimal | None:
    quote = repo.fx_at(conn, at)
    return None if quote is None else quote.rate


def _state_json(state: Any) -> dict[str, Any]:
    return {
        "cash": {c.value: v for c, v in state.cash.items()},
        "positions": [
            {
                "instrument_id": p.instrument_id,
                "currency": p.currency.value,
                "qty": p.qty,
                "cost_native": p.cost_native,
                "cost_krw": p.cost_krw,
            }
            for p in state.positions.values()
        ],
        "realized_krw": state.realized_krw,
        "fees_krw": state.fees_krw,
        "contributions_krw": state.contributions_krw,
        "income_krw": state.income_krw,
    }


# ── the preview ──────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PreviewData:
    computed_at: datetime
    snapshot: AccountSnapshot
    rate: FxQuote
    plan: Plan
    specs: list[StageSpec]
    due: dict[int, datetime]
    instruments: dict[str, Instrument]
    current: list[tuple[str, Instrument | None, Decimal]]  # (label, instrument, krw)
    outside: list[tuple[BrokerHolding, Decimal]]  # (holding, approx krw)
    targets: list[tuple[Instrument, Decimal]]  # (instrument, % of the whole)
    price_at: datetime | None
    total_krw: Decimal  # the first orders' amounts in won (what turning on compares)
    account_krw: Decimal  # what the account holds in won
    signature: str
    hash: str


@dataclass(frozen=True)
class NotComputable:
    at: datetime
    cause: str  # 'stale' | 'other'
    detail: str


def _order_krw(amount: Decimal, currency: Currency, rate: Decimal) -> Decimal:
    return amount if currency is Currency.KRW else usd_in_krw(amount, rate)


def preview_data(
    conn: sqlite3.Connection, cfg: Config, at: datetime
) -> PreviewData | NotComputable:
    """The first orders for the account as it is (PHASE3.md 2.7): the live ledger itself when it
    has started (live turned on again), else the account in the latest snapshot."""
    snap = live_repo.latest_snapshot(conn)
    if snap is None or at - snap.confirmed_at > cfg.broker_max_age or not snap.quiet:
        return NotComputable(at, "other", "no fresh, quiet account snapshot")
    instruments = rule_instruments(conn)
    rule, _ = load_rule(conn, RULE_ID)
    markets = sorted({i.market for i in instruments.values()}, key=lambda m: m.value)
    for m in markets:
        fresh = market_freshness(
            conn, cfg, m, [i for i in instruments.values() if i.market is m], at
        )
        if not fresh.usable:
            return NotComputable(at, "stale", f"{m.value} quotes")
    fx_fresh, quote = rate_freshness(conn, cfg, at)
    if quote is None or not fx_fresh.usable:
        return NotComputable(at, "stale", "fx")
    closes = {iid: latest_close(conn, cfg, inst, at) for iid, inst in instruments.items()}
    if any(c is None for c in closes.values()):
        return NotComputable(at, "stale", "closes")
    rate = quote.rate
    started = repo.start_event(conn, LIVE) is not None
    if started:
        state = sleeves.base_view(conn, LIVE)
        held = withdraw_wait_amounts(repo.cash_parts(conn, LIVE))
        cash = {c: max(state.cash_of(c) - held.get(c, ZERO), ZERO) for c in Currency}
        qty = {iid: state.qty_of(iid) for iid in instruments}
        outside = [h for h in snap.holdings if h.instrument_id not in ledger_instrument_ids(conn)]
    else:
        try:
            opening = opening_from(snap, instruments, rate)
        except LiveStartError as exc:
            return NotComputable(at, "other", f"{exc.code}: {exc}")
        cash = opening.cash
        qty = {
            iid: opening.positions[iid].qty if iid in opening.positions else 0
            for iid in instruments
        }
        outside = opening.outside
    items: list[PlanItem] = []
    for iid in rule.instrument_ids:
        close = closes[iid]
        assert close is not None  # checked above
        items.append(PlanItem(instruments[iid], rule.target_of(iid), qty[iid], close.price))
    plan = plan_rule(
        PlanInput(
            items=tuple(items),
            threshold=rule.threshold,
            fx_rate=rate,
            free_krw=cash[Currency.KRW],
            free_usd=cash[Currency.USD],
            fees=cfg.fees,
            fx_step_krw=cfg.fx_step_krw,
            net_free_cash=True,
        )
    )
    specs = stage_specs(plan)
    due = schedule(specs, next_check_at(cfg, at), slotter_for(cfg))
    current: list[tuple[str, Instrument | None, Decimal]] = []
    if cash[Currency.KRW] > 0:
        current.append(("krw-cash", None, cash[Currency.KRW]))
    if cash[Currency.USD] > 0:
        current.append(("usd-cash", None, usd_in_krw(cash[Currency.USD], rate)))
    for iid in rule.instrument_ids:
        if qty[iid] > 0:
            close = closes[iid]
            assert close is not None
            value = close.price * qty[iid]
            current.append(
                ("holding", instruments[iid], _order_krw(value, instruments[iid].currency, rate))
            )
    account_krw = sum((krw for _, _, krw in current), ZERO)
    total = ZERO
    parts: list[str] = []
    for o in (*plan.sells, *plan.buys):
        total += _order_krw(o.est_gross, o.currency, rate)
        parts.append(f"{o.side.value}:{o.instrument.instrument_id}:{o.qty}")
    if plan.fx is not None:
        total += _order_krw(plan.fx.from_amount, plan.fx.direction.source, rate)
        parts.append(f"fx:{plan.fx.direction.value}:{plan.fx.from_amount}")
    signature = "|".join(sorted(p.rsplit(":", 1)[0] for p in parts))
    material = {
        "current": [
            (label, None if inst is None else inst.instrument_id, str(krw))
            for label, inst, krw in current
        ],
        "orders": sorted(parts),
        "snapshot": snap.snapshot_id,
    }
    digest = hashlib.sha256(dumps(material).encode()).hexdigest()[:16]
    outside_rows = [(h, _holding_krw(h, rate)) for h in outside]
    targets = [
        (instruments[iid], (rule.target_of(iid) * _rule_share(conn)).quantize(Decimal("0.1")))
        for iid in rule.instrument_ids
    ]
    return PreviewData(
        computed_at=at,
        snapshot=snap,
        rate=quote,
        plan=plan,
        specs=specs,
        due=due,
        instruments=instruments,
        current=current,
        outside=outside_rows,
        targets=targets,
        price_at=_price_time(conn),
        total_krw=total,
        account_krw=account_krw,
        signature=signature,
        hash=digest,
    )


def _holding_krw(h: BrokerHolding, rate: Decimal) -> Decimal:
    value = h.qty * (h.last_price if h.last_price > 0 else h.avg_price)
    return round_won(value) if h.currency is Currency.KRW else usd_in_krw(value, rate)


def _rule_share(conn: sqlite3.Connection) -> Decimal:
    shares = ai_repo.shares(conn, LIVE)
    return shares.get(RULE_ID, Decimal(100))


def _price_time(conn: sqlite3.Connection) -> datetime | None:
    times = [
        row.fetched_at
        for series in ("kr-quotes", "us-quotes")
        if (row := repo.get_freshness(conn, series)) is not None and row.fetched_at is not None
    ]
    return min(times) if times else None


def store_preview(conn: sqlite3.Connection, data: PreviewData, payload: dict[str, Any]) -> None:
    live_repo.save_preview(
        conn,
        live_repo.StoredPreview(
            hash=data.hash,
            computed_at=data.computed_at,
            snapshot_id=data.snapshot.snapshot_id,
            total_krw=data.total_krw,
            signature=data.signature,
            payload={**payload, "account_krw": str(data.account_krw)},
        ),
    )
    live_repo.prune_previews(conn, data.computed_at - timedelta(days=2))


def preview_changed(stored: live_repo.StoredPreview | None, fresh: PreviewData) -> bool:
    """인계 13: turning live on recomputes the preview and stops when its amounts moved by 1% or
    more (or it orders something else). Without orders the account's value is compared."""
    if stored is None:
        return True
    if stored.hash == fresh.hash:
        return False
    if stored.signature != fresh.signature:
        return True
    old, new = stored.total_krw, fresh.total_krw
    if old <= 0:
        old = Decimal(str(stored.payload.get("account_krw") or "0"))
        new = fresh.account_krw
    if old <= 0:
        return new > 0
    return abs(new - old) / old >= Decimal("0.01")


# ── the switch ───────────────────────────────────────────────────────────────────────────


def mode_of(conn: sqlite3.Connection) -> str:
    return repo.get_setting(conn, MODE) or "paper"


def turn_on(conn: sqlite3.Connection, cfg: Config, at: datetime, data: PreviewData) -> int | None:
    """The mode becomes 'live' (the caller checked the PIN, the checks and the preview).
    Returns the start event when the live ledger starts now. The caller owns the transaction."""
    repo.set_setting(conn, MODE, LIVE, at)
    repo.set_setting(conn, MODE_CHANGED_AT, to_iso(at), at)
    started: int | None = None
    if repo.start_event(conn, LIVE) is None:
        started = start_live(conn, cfg, data.snapshot, at)
    repo.insert_event(
        conn,
        ledger_id=LIVE,
        kind="live-on",
        event_date=kst_date(at),
        occurred_at=at,
        payload={
            "preview": data.hash,
            "snapshot_id": data.snapshot.snapshot_id,
            "start_event": started,
        },
    )
    return started


@dataclass(frozen=True)
class TurnOff:
    changed: bool
    cancelled: list[int]  # orders that never left: cancelled in the database
    cancel_requested: list[int]  # orders at the broker: the next tick cancels them


def turn_off(conn: sqlite3.Connection, at: datetime) -> TurnOff:
    """The mode becomes 'paper' (인계 7: a session and a confirmation, no PIN). The live plans
    close; what they had not sent is cancelled; what is at the broker gets a cancel request the
    tick carries out (the web service cannot reach Toss). The caller owns the transaction."""
    if mode_of(conn) != LIVE:
        return TurnOff(False, [], [])
    repo.set_setting(conn, MODE, "paper", at)
    repo.set_setting(conn, MODE_CHANGED_AT, to_iso(at), at)
    cancelled: list[int] = []
    requested: list[int] = []
    for plan in repo.open_plans(conn, LIVE):
        for order in repo.orders_of_plan(conn, plan.plan_id):
            if order.status != "pending":
                continue
            row = live_repo.get_broker_order(conn, order.order_id)
            if row is not None and row.open:
                live_repo.request_cancel(conn, order.order_id, at)
                requested.append(order.order_id)
            else:
                repo.cancel_order(conn, order.order_id)
                cancelled.append(order.order_id)
        for stage in repo.stages_of(conn, plan.plan_id):
            if stage.status in ("pending", "failed"):
                repo.update_stage(conn, stage.stage_id, status="todo", last_error="live off")
        repo.set_plan_status(conn, plan.plan_id, "resolved", at)
        event = repo.event_of_plan(conn, plan.plan_id)
        if event is not None:
            payload = dict(event.payload)
            payload.update({"resolved_at": at, "resolved_by": "live-off"})
            repo.update_event(conn, event.event_id, at, status="resolved", payload=payload)
    for row in live_repo.broker_orders_of(conn, LIVE, live_repo.OPEN_STATES):
        if row.order_id not in requested:
            live_repo.request_cancel(conn, row.order_id, at)
            requested.append(row.order_id)
    repo.insert_event(
        conn,
        ledger_id=LIVE,
        kind="live-off",
        event_date=kst_date(at),
        occurred_at=at,
        payload={"cancelled": cancelled, "cancel_requested": requested},
    )
    if repo.start_event(conn, LIVE) is not None:
        refresh_cash_parts(conn, LIVE, at)
    return TurnOff(True, cancelled, requested)


def retry_cancels(conn: sqlite3.Connection, at: datetime) -> list[int]:
    """'취소 다시 시도': failed cancellations are asked again (the tick carries them out)."""
    out: list[int] = []
    for row in live_repo.cancel_rows(conn, LIVE, ["failed"]):
        live_repo.request_cancel(conn, row.order_id, at)
        out.append(row.order_id)
    return out


def live_periods(conn: sqlite3.Connection) -> list[tuple[datetime, datetime | None]]:
    """(on, off) pairs of the live mode, oldest first; the last off is None while it is on."""
    periods: list[tuple[datetime, datetime | None]] = []
    on: datetime | None = None
    for ev in repo.events_of_ledger(conn, LIVE, ["live-on", "live-off"]):
        if ev.kind == "live-on" and on is None:
            on = ev.occurred_at
        elif ev.kind == "live-off" and on is not None:
            periods.append((on, ev.occurred_at))
            on = None
    if on is not None:
        periods.append((on, None))
    return periods


# ── the link, for the screens ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LinkCheck:
    ok: bool
    cause: str | None  # why not: env-off | no-key | auth | ip | account | unreachable |
    # maintenance | error | old | not-tradable | conflict | mismatch | never
    checked_at: datetime | None
    account_tail: str | None
    key_expires: date | None
    days_left: int | None


def link_check(conn: sqlite3.Connection, cfg: Config, at: datetime) -> LinkCheck:
    """Whether the tick's last look at Toss lets live orders go (PHASE3.md 2.7)."""
    status = live_repo.get_status(conn)
    if status is None:
        return LinkCheck(False, "never", None, None, None, None)
    expires = status.key_expires
    days_left = None if expires is None else (expires - kst_date(at)).days

    def no(cause: str) -> LinkCheck:
        return LinkCheck(False, cause, status.checked_at, status.account_tail, expires, days_left)

    if not status.env_live or status.state == "off":
        return no("env-off")
    if status.state != "ok":
        return no(status.state)
    if status.ok_at is None or at - status.ok_at > cfg.broker_max_age:
        return no("old")
    if status.revoked:
        return no("conflict")
    if any(v != "ok" for v in status.tradable.values()) or not status.tradable:
        return no("not-tradable")
    if repo.start_event(conn, LIVE) is not None and status.reconcile_state == "mismatch":
        return no("mismatch")
    if days_left is not None and days_left < 0:
        return no("expired")
    return LinkCheck(True, None, status.ok_at, status.account_tail, expires, days_left)


@dataclass(frozen=True)
class FxTodo:
    order: OrderRow
    direction: FxDirection
    by: datetime | None  # the time of the buy that waits for it


def fx_todos(conn: sqlite3.Connection, at: datetime) -> list[FxTodo]:
    """Conversions the owner has to make in the app: live fx orders whose stage is due."""
    out: list[FxTodo] = []
    for order in repo.pending_orders(conn, LIVE):
        if order.side != "fx" or order.fx_direction is None:
            continue
        if repo.get_plan(conn, order.plan_id).status not in repo.OPEN_PLAN_STATUSES:
            continue
        stage = repo.get_stage(conn, order.stage_id)
        if stage.due_at > at or stage.status != "pending":
            continue
        later = [
            s.due_at
            for s in repo.stages_of(conn, order.plan_id)
            if stage.seq in s.depends_on and s.status == "pending"
        ]
        out.append(FxTodo(order, FxDirection(order.fx_direction), min(later) if later else None))
    return out


def cancel_failed(conn: sqlite3.Connection) -> list[live_repo.BrokerOrderRow]:
    return [r for r in live_repo.cancel_rows(conn, LIVE, ["failed"]) if r.open]


def cancel_pending(conn: sqlite3.Connection) -> list[live_repo.BrokerOrderRow]:
    return [r for r in live_repo.cancel_rows(conn, LIVE, ["requested"]) if r.open]


def unknown_orders(conn: sqlite3.Connection) -> list[live_repo.BrokerOrderRow]:
    """Orders whose fate at the broker could not be told apart (two candidates): a person
    checks the Toss app."""
    return [
        r
        for r in live_repo.broker_orders_of(conn, LIVE, ["unknown"])
        if r.error_code == "ambiguous"
    ]


def relevant(conn: sqlite3.Connection) -> bool:
    """Whether the screens show anything of the live link: it was ever checked with the key,
    the ledger started, or the mode is live."""
    status = live_repo.get_status(conn)
    return (
        mode_of(conn) == LIVE
        or repo.start_event(conn, LIVE) is not None
        or (status is not None and status.env_live)
    )
