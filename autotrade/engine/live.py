"""The live ledger against the Toss account (autotrade/PHASE3.md 2.5-2.7).

The account is the truth. This module holds what the engine does with what the tick's Toss sync
recorded (broker_status, broker_snapshots, broker_orders); it never calls Toss:

- start_live: the live ledger starts from the account shown in the preview the owner approved
  (its cash, and the rule's instruments it holds, at their price then: no gain at the start).
- reconcile: before every plan (and whenever the account is quiet), the ledger is matched with
  the snapshot. What the broker did for our orders is booked first (late fills); then the
  account's fills the engine did not send (the owner's trades in the app, PHASE3.md 2.5) and
  the cash they do not explain: the owner's conversion (won and dollars in opposite directions
  at about the market rate), a dividend the ledger is owed (its net, within the rounding of the
  tax), a conversion that came with a deposit or a withdrawal in the same five minutes, a
  deposit, a withdrawal. All of it is worked out first and booked in time order: money that
  came in before an app buy it paid for, the fills, then the rest (_book_in_order). Last, the
  rule's holdings must equal the broker's. Anything that does not fit is a mismatch: nothing
  is written (savepoint), a red manual to-do shows it and no plan is made until it is fixed or
  `adopt-broker` accepts the broker's numbers. An order more than one of the account's orders
  could be waits for the owner's word (settle_ambiguous).
- preview: the first orders the rule would send for the account as it is, for the mode screen;
  the hash and total are kept so that turning live on can tell a changed preview (인계 13).
  Like the check, it plans per currency (D47), sizes buys as the send pays them (the limit
  price and the fee) and leaves out the owner's money of the day of the next check (D48); it
  carries the conversion that would bring the mix to the targets. Its first check is the first
  one live runs once turned on (first_live_check).
- turn_on / turn_off: the mode switch's database side (the web service runs it; the cancels at
  the broker are the tick's, as requests).
- link_check and live_todos: what the mode and health screens show of the Toss link.
"""

from __future__ import annotations

import hashlib
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal
from typing import Any

from autotrade.broker.toss import TossExecutor, buy_unit, fee_rate, fill_of
from autotrade.broker.toss_api import BrokerHolding, BrokerOrder
from autotrade.config import Config
from autotrade.db import ai_repo, live_repo, repo
from autotrade.db.connection import dumps
from autotrade.db.live_repo import AccountSnapshot, NewExternalFill
from autotrade.db.models import DividendRow, FillRow
from autotrade.domain.currency_mix import CurrencyMix, FxSuggestion, suggest
from autotrade.domain.dividends import HeldFill, after_tax, tax_slack
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
from autotrade.domain.planner import FxDirection, Plan, PlanInput, PlanItem, Side, plan_per_currency
from autotrade.domain.stages import StageSpec, schedule, stage_specs
from autotrade.engine import runner, sleeves
from autotrade.engine.bootstrap import MODE
from autotrade.engine.common import (
    CONVERSION,
    capped,
    load_rule,
    new_money_of_rule,
    new_money_waiting,
    refresh_cash_parts,
    slotter_for,
    withdraw_wait_amounts,
)
from autotrade.engine.dividends import (
    dividend_ref,
    session_of,
    shares_before_ex_date,
    tax_rate,
)
from autotrade.engine.live_discovery import OWNER_SOLD
from autotrade.engine.status import first_check_after, next_check_at
from autotrade.market.calendar import KRX, NYSE, CalendarRangeError
from autotrade.market.service import latest_close, market_freshness, rate_freshness
from autotrade.market.types import FxQuote
from autotrade.rules.discovery import RULE_ID as AI_RULE
from autotrade.rules.index_half import RULE_ID
from autotrade.timeutil import KST, et_date, from_iso, kst_date, require_aware, to_iso

LIVE = "live"
MODE_CHANGED_AT = "mode.changed_at"
RECONCILE_JOB = "reconcile"
DIVIDEND_WINDOW_BEFORE = timedelta(days=21)  # a dividend paid this long ago may still arrive
DIVIDEND_WINDOW_AFTER = timedelta(days=3)  # an estimated pay date can be early
WITHDRAW_TRADING_DAYS = 2  # 인계 5: settlement date + 2 business days
KEY_EXPIRY_WARN_DAYS = 14


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
    conn: sqlite3.Connection,
    cfg: Config,
    snap: AccountSnapshot | None,
    at: datetime,
    max_age: timedelta | None = None,
) -> str | None:
    """Why the account cannot be read as the truth right now (None = it can). `max_age` is how
    old the snapshot may be (default cfg.broker_max_age; the reconciliation passes sync_max_age,
    which allows the slow night cadence)."""
    if snap is None:
        return "no-snapshot"
    if at - snap.confirmed_at > (cfg.broker_max_age if max_age is None else max_age):
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
    max_age: timedelta | None = None,
) -> ReconcileResult:
    """Match the live ledger with the account. The caller owns the transaction; on a mismatch
    nothing is written but the status (savepoint). `max_age`: how old the snapshot may be, by
    default the tick's cadence (sync_max_age); the check passes the strict broker_max_age."""
    require_aware(at)
    start = repo.start_event(conn, LIVE)
    if start is None:
        return ReconcileResult("skipped", "not-started")
    snap = snapshot or live_repo.latest_snapshot(conn)
    reason = busy_reason(conn, cfg, snap, at, max_age or sync_max_age(cfg, at))
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
            # The closed orders the next snapshot reads start at the last match
            # (jobs/live_tasks.py Sync._closed_since): a busy or mismatched pass booked nothing.
            matched_at=at if result.state == "match" else status.matched_at,
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
    """Explain the account's cash, then book all of it in the order the account saw it.

    The owner's fills in the app are known (the closed orders); what they do not explain of each
    currency's change is worked out on the cash they leave: his conversion, a dividend, a deposit
    or a withdrawal. So an app buy paid with money that came in the same window explains that
    money, not a cash shortfall. Nothing is written until all of it is known (_book_in_order)."""
    result = ReconcileResult("match", snapshot_id=snap.snapshot_id)
    opening = repo.load_state(conn, LIVE).cash
    try:
        late = book_late_fills(conn, cfg, at)
    except LedgerError as exc:
        # A fill of ours the rule's records cannot pay (engine/runner.py execute_stage): nothing
        # is sent until the owner looks and adopt-broker books it (it covers the rule).
        raise _MismatchError("rule-cash", {"why": str(exc)}) from exc
    result.booked.extend(late)
    ours = [repo.fill_of_order(conn, int(b["late_fill"])) for b in late]
    own = ledger_instrument_ids(conn)
    trades = _new_external_trades(conn, snap, _fills_floor(conn, started_at))
    state = repo.load_state(conn, LIVE)
    residual = {
        c: snap.cash_of(c)
        - state.cash_of(c)
        - sum((_cash_effect(o) for o in trades if o.currency is c), ZERO)
        for c in Currency
    }
    moves: list[_Move] = []
    residual = _explain_conversion(conn, cfg, at, residual, moves)
    for currency in Currency:
        if residual[currency] > 0:
            residual[currency] = _explain_dividend(
                conn, cfg, at, currency, residual[currency], started_at, trades, moves
            )
    # A dividend may have hidden a conversion; then a conversion that came with a deposit or a
    # withdrawal in the same five minutes.
    residual = _explain_conversion(conn, cfg, at, residual, moves)
    residual = _explain_mixed(conn, at, snap, residual, moves)
    for currency in Currency:
        amount = residual[currency]
        if amount > 0:
            moves.append(
                _Move(CashFlowKind.DEPOSIT, currency, amount, {"reason": "unexplained-in"})
            )
        elif amount < 0:
            moves.append(
                _Move(
                    CashFlowKind.WITHDRAWAL,
                    currency,
                    -amount,
                    {"reason": "unexplained-out"},
                    consume_waits=True,
                )
            )
    late_fills = [f for f in ours if f is not None and f.kind == "trade"]
    _book_in_order(conn, cfg, at, snap, opening, late_fills, trades, moves, own, result)
    _check_positions(conn, snap, own)
    refresh_cash_parts(conn, LIVE, at)
    return result


def _fills_floor(conn: sqlite3.Connection, started_at: datetime) -> datetime:
    """The time before which the owner's fills are in the ledger already: the live start, or the
    account the owner last adopted (adopt_broker books its holdings and cash as read then, app
    fills included). The closed orders are read from the last match (jobs/live_tasks.py
    Sync._closed_since), which an adoption does not move: without this, the fills it took in
    were booked again and the ledger never matched."""
    adopted = [
        ev.occurred_at
        for ev in repo.events_of_ledger(conn, LIVE, ["deposit", "withdrawal"])
        if ev.payload.get("source") == "adopt-broker"
    ]
    return max([started_at, *adopted])


def _new_external_trades(
    conn: sqlite3.Connection, snap: AccountSnapshot, since: datetime
) -> list[BrokerOrder]:
    """The account's fills the engine did not send and the ledger has not booked, in time
    order: the owner's, in the app or WTS, after `since` (_fills_floor)."""
    ours = live_repo.our_broker_ids(conn)
    seen = live_repo.external_broker_ids(conn, LIVE)
    out = [
        o
        for o in snap.closed_orders
        if o.filled_qty > 0
        and o.order_id not in ours
        and o.order_id not in seen
        and o.filled_at is not None
        and o.filled_at > since  # earlier: part of the account the ledger started or adopted
    ]
    return sorted(out, key=lambda o: (o.filled_at or since, o.order_id))


def _trade_amounts(order: BrokerOrder) -> tuple[Decimal, Decimal] | None:
    """(gross, fee) of a fill as the broker reported it; None without an amount."""
    gross = order.filled_amount
    if gross is None and order.avg_price is not None:
        gross = order.avg_price * order.filled_qty
    if gross is None or gross <= 0:
        return None
    return gross, (order.commission or ZERO) + (order.tax or ZERO)


def _cash_effect(order: BrokerOrder) -> Decimal:
    """What a fill did to the cash of its currency: a buy paid gross + fee, a sale brought
    gross - fee (0 without an amount: booking it is a mismatch anyway)."""
    amounts = _trade_amounts(order)
    if amounts is None:
        return ZERO
    gross, fee = amounts
    return -(gross + fee) if order.side == "BUY" else gross - fee


@dataclass
class _Move:
    """Money the reconciliation found: a deposit, a withdrawal, a dividend or one side of the
    owner's conversion. Worked out before anything is written, then booked in time order with
    the owner's fills (_book_in_order)."""

    kind: CashFlowKind  # DEPOSIT | WITHDRAWAL | DIVIDEND
    currency: Currency
    amount: Decimal
    extra: dict[str, Any] = field(default_factory=dict)  # the event's payload
    rate: Decimal | None = None  # a dollar amount's won rate (None: the rate when it is booked)
    consume_waits: bool = False  # a withdrawal takes the cash that waited for it first
    due: DueDividend | None = None  # the dividend it is
    conversion: dict[str, Any] | None = None  # the owner's conversion it is a side of (its log)

    @property
    def money_in(self) -> bool:
        return self.kind is not CashFlowKind.WITHDRAWAL


def _book_in_order(
    conn: sqlite3.Connection,
    cfg: Config,
    at: datetime,
    snap: AccountSnapshot,
    opening: Mapping[Currency, Decimal],
    late_fills: list[FillRow],
    trades: list[BrokerOrder],
    moves: list[_Move],
    own: set[str],
    result: ReconcileResult,
) -> None:
    """Book the owner's fills and the money that explains the rest, as the account saw them:
    each fill at its time; money that came in, just before the first fill the cash could not
    pay without it (dated that fill's time: he deposited or converted to pay for an app buy);
    the rest of the money in, and all money out, at the snapshot that showed it, after the
    fills (money out may be the proceeds of an app sale). So the ledger's cash never goes below
    zero on the way, and the rebuild, which folds the records in time order with money in before
    fills at the same instant (engine/rebuild.py), takes the same steps: the cash is followed
    in time order from before this pass, our late fills (booked already, `late_fills`) at their
    own times. Money dated before the snapshot keeps the snapshot's day as its event date: D48
    holds the owner's money from the day the account showed it (engine/common.py
    new_money_waiting)."""
    seen = snap.taken_at
    day = kst_date(seen)
    balance = {c: opening.get(c, ZERO) for c in Currency}
    steps: list[tuple[datetime, int, Currency, Decimal, BrokerOrder | None]] = [
        (
            f.filled_at,
            0,
            f.currency,
            -(f.gross + f.fee) if f.side == "buy" else f.gross - f.fee,
            None,
        )
        for f in late_fills
    ]
    steps += [(t.filled_at or seen, 1, t.currency, _cash_effect(t), t) for t in trades]
    steps.sort(key=lambda s: (s[0], s[1]))
    waiting = [m for m in moves if m.money_in]
    before: list[tuple[datetime, BrokerOrder | None, list[_Move]]] = []
    for when, _, currency, effect, trade in steps:
        funds: list[_Move] = []
        while balance[currency] + effect < 0:
            funding = next((m for m in waiting if m.currency is currency), None)
            if funding is None:
                break  # booking it finds the cash short: a mismatch (or a rebuild that fails)
            waiting.remove(funding)
            funds.append(funding)
            balance[currency] += funding.amount
        balance[currency] += effect
        before.append((when, trade, funds))
    early = {id(m) for _, _, ms in before for m in ms}
    for when, trade, funds in before:  # our late fills are booked: their money first
        if trade is None:
            for move in funds:
                _book_move(conn, cfg, at, move, when, day, result)
    for when, trade, funds in before:
        if trade is not None:
            for move in funds:
                _book_move(conn, cfg, at, move, when, day, result)
            result.booked.append(_book_external_trade(conn, cfg, at, trade, own, snap))
    for move in moves:
        if id(move) not in early:
            _book_move(conn, cfg, at, move, seen, day, result)


def _book_move(
    conn: sqlite3.Connection,
    cfg: Config,
    at: datetime,
    move: _Move,
    when: datetime,
    day: date,
    result: ReconcileResult,
) -> None:
    if move.due is not None:
        _book_dividend(conn, cfg, at, move, move.due, when, day, result)
        return
    event_id = _flow(
        conn,
        at,
        move.kind,
        move.amount,
        move.currency,
        move.extra,
        rate=move.rate,
        occurred_at=when,
        event_day=day,
        parts=None if move.conversion is None else _conversion_parts(conn, move),
    )
    if move.consume_waits:
        _consume_withdraw_waits(conn, move.currency, move.amount, at)
    if move.conversion is not None:
        if not move.conversion["event_ids"]:
            result.booked.append(move.conversion)
        move.conversion["event_ids"].append(event_id)
        if move.kind is CashFlowKind.WITHDRAWAL:
            _cap_withdraw_waits(conn, move.currency, when, at)
        return
    key = "withdrawal" if move.kind is CashFlowKind.WITHDRAWAL else "deposit"
    result.booked.append(
        {key: str(move.amount), "currency": move.currency.value, "event_id": event_id}
    )


def _conversion_parts(conn: sqlite3.Connection, move: _Move) -> dict[str, Decimal] | None:
    """The rules' parts of one side of the owner's conversion (None: the ledger has no sleeve).
    Each rule gives of the currency he paid what sleeves.withdrawal_parts takes (worked out once,
    on the side booked first, with that currency's cash before the conversion) and gets the same
    proportion of the currency he got: a conversion moves no money between the rules."""
    log = move.conversion
    assert log is not None
    if not sleeves.sleeve_rule_ids(conn, LIVE):
        return None
    direction = FxDirection(log["conversion"])
    source, target = Decimal(str(log["from"])), Decimal(str(log["to"]))
    kept = log.get("sleeves")
    if kept is None:
        cash = repo.load_state(conn, LIVE).cash_of(direction.source)
        try:
            taken = sleeves.withdrawal_parts(conn, LIVE, source, direction.source, cash)
        except LedgerError as exc:
            raise _MismatchError(
                "sleeves", {"conversion": direction.value, "why": str(exc)}
            ) from exc
        kept = {r: str(v) for r, v in taken.items()}
        log["sleeves"] = kept
    given = {r: Decimal(v) for r, v in kept.items()}
    if move.kind is CashFlowKind.WITHDRAWAL:
        return given
    unit = _unit(direction.target)
    return {r: (target * v / source).quantize(unit, rounding=ROUND_FLOOR) for r, v in given.items()}


def book_late_fills(
    conn: sqlite3.Connection, cfg: Config, at: datetime, *, cover: bool = False
) -> list[dict[str, Any]]:
    """Fills the broker reported for our orders that the ledger has not booked: after the plan
    was closed (live off, a resolved to-do), or before the stage runner got to them. An order
    that ended with nothing filled and whose plan is closed is marked cancelled."""
    out: list[dict[str, Any]] = []
    for row in live_repo.broker_orders_of(conn, LIVE, ["done"]):
        order = repo.get_order(conn, row.order_id)
        filled = fill_of(row)
        if filled is not None:
            booked = runner.book_fill(
                conn, cfg, LIVE, order, filled, TossExecutor.name, at, cover=cover
            )
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
    snap: AccountSnapshot | None = None,
) -> dict[str, Any]:
    """A fill the engine did not send (the owner's, in the app or WTS).

    With rules sharing the ledger (3단계 몫, D49), whose shares he traded decides where it goes:
    - the index rule's ETFs (069500, SPYM): '지수 반반''s; a sale beyond what it holds comes
      out of the other rules' parts that hold the ETF (their share of the sale);
    - another company the ledger holds (a '3년 발굴' pick): his buy is his, outside the ledger
      (money out, shares outside: the rule never buys while he holds some, discovery_plan
      outside_held); his sale is his own shares first (what the account still holds beyond
      the ledger after the reconciliation's trades), then the rule's (its part sells; a pick
      left with none is closed, OWNER_SOLD, and not taken back while the paper judgment stays
      the same, live_discovery.follow);
    - anything else: outside the ledger.
    A part nobody holds is a mismatch (nothing written, a red to-do)."""
    when = order.filled_at or at
    qty = order.filled_qty
    amounts = _trade_amounts(order)
    if amounts is None:
        raise _MismatchError("external-fill", {"order": order.order_id, "why": "no amount"})
    gross, fee = amounts
    currency = order.currency
    rate = _rate(conn, when, at) if currency is Currency.USD else None
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
    if iid not in own:
        return _book_outside(conn, at, order, side, gross, fee, rate, when, base, first=True)
    if qty != qty.to_integral_value():
        raise _MismatchError("fractional", {"instrument_id": iid, "qty": str(qty)})
    q = int(qty)
    index = iid in rule_instruments(conn)
    rules = sleeves.sleeve_rule_ids(conn, LIVE)
    if side is Side.BUY:
        if rules and not index:
            return _book_outside(conn, at, order, side, gross, fee, rate, when, base, first=True)
        parts: list[tuple[str | None, int]] = [(None, q)]
    else:
        parts = []
        left = q
        if rules and not index:
            ledger_qty = repo.load_state(conn, LIVE).qty_of(iid)
            final = ZERO
            if snap is not None:
                final = sum((h.qty for h in snap.holdings if h.instrument_id == iid), ZERO)
            from_ledger = min(q, max(0, ledger_qty - int(final)))
            if q - from_ledger > 0:
                parts.append(("outside", q - from_ledger))
            left = from_ledger
        holders: list[tuple[str | None, int]] = [
            (None, sleeves.base_view(conn, LIVE).qty_of(iid) if rules else q)
        ]
        holders += [(r, ai_repo.load_sleeve(conn, LIVE, r).qty_of(iid)) for r in rules]
        for rule_id, held in holders:
            take = min(left, held)
            if take > 0:
                parts.append((rule_id, take))
                left -= take
        if left > 0:
            raise _MismatchError(
                "sleeves", {"instrument_id": iid, "why": f"{left} sold shares nobody holds"}
            )
    out: list[dict[str, Any]] = []
    gross_left, fee_left, qty_left = gross, fee, q
    unit = _unit(currency)
    for n, (rule_id, part_qty) in enumerate(parts):
        last = n == len(parts) - 1
        part_gross = gross_left if last else (gross * part_qty / q).quantize(unit)
        part_fee = fee_left if last else (fee * part_qty / q).quantize(unit)
        gross_left, fee_left, qty_left = (
            gross_left - part_gross,
            fee_left - part_fee,
            qty_left - part_qty,
        )
        if rule_id == "outside":
            out.append(
                _book_outside(
                    conn, at, order, side, part_gross, part_fee, rate, when, {}, first=n == 0
                )
            )
            continue
        out.append(
            _book_ledger_part(
                conn,
                at,
                order,
                iid,
                side,
                part_qty,
                part_gross,
                part_fee,
                rate,
                when,
                rule_id,
                first=n == 0,
            )
        )
    if len(out) == 1:
        return {**base, **out[0]}
    return {**base, "parts": out}


def _book_ledger_part(
    conn: sqlite3.Connection,
    at: datetime,
    order: BrokerOrder,
    iid: str,
    side: Side,
    qty: int,
    gross: Decimal,
    fee: Decimal,
    rate: Decimal | None,
    when: datetime,
    rule_id: str | None,
    *,
    first: bool,
) -> dict[str, Any]:
    """The part of his trade that is the ledger's: '지수 반반''s (rule_id None) or a rule's."""
    currency = order.currency
    fee_krw = fee if rate is None else usd_in_krw(fee, rate)
    trade = TradeFill(iid, currency, side, qty, gross / qty, fee, rate, gross)
    try:
        state = apply_trade(repo.load_state(conn, LIVE), trade)
    except LedgerError as exc:
        raise _MismatchError("external-fill", {"instrument_id": iid, "why": str(exc)}) from exc
    out: dict[str, Any] = {"qty": qty, "rule_id": rule_id}
    if rule_id is not None:
        part = apply_trade(ai_repo.load_sleeve(conn, LIVE, rule_id), trade)
        ai_repo.save_sleeve(conn, LIVE, rule_id, part, at)
        if part.qty_of(iid) == 0:
            pick = ai_repo.open_pick(conn, LIVE, rule_id, iid)
            if pick is not None and pick.status == "held":
                ai_repo.update_pick(
                    conn,
                    pick.pick_id,
                    at,
                    status="sold",
                    closed_on=kst_date(when),
                    closed_reason=OWNER_SOLD,
                    decision=None,
                )
                out["pick_closed"] = pick.pick_id
    # '지수 반반''s part must fit in what it holds (the other parts moved by their own records).
    rest = state
    try:
        for other in sleeves.sleeve_rule_ids(conn, LIVE):
            rest = sleeves.subtract(rest, ai_repo.load_sleeve(conn, LIVE, other))
    except LedgerError as exc:
        raise _MismatchError("sleeves", {"instrument_id": iid, "why": str(exc)}) from exc
    repo.save_state(conn, LIVE, state, at)
    live_repo.insert_external(
        conn,
        NewExternalFill(
            ledger_id=LIVE,
            broker_order_id=order.order_id if first else None,
            kind="trade",
            treatment="ledger",
            instrument_id=iid,
            symbol=order.symbol,
            name=None,
            side=side.value,
            currency=currency,
            qty=qty,
            gross=gross,
            fee=fee,
            fee_krw=fee_krw,
            krw_rate=rate,
            received=None,
            filled_at=when,
            settlement_date=order.settlement_date,
            rule_id=rule_id,
        ),
        at,
    )
    if side is Side.SELL and rule_id is None:
        until = withdraw_until(order.settlement_date, kst_date(when))
        repo.add_withdraw_wait(conn, LIVE, currency, gross - fee, until, at)
        out["withdraw_wait_until"] = until.isoformat()
    return out


def _book_outside(
    conn: sqlite3.Connection,
    at: datetime,
    order: BrokerOrder,
    side: Side,
    gross: Decimal,
    fee: Decimal,
    rate: Decimal | None,
    when: datetime,
    base: dict[str, Any],
    *,
    first: bool,
) -> dict[str, Any]:
    """His trade outside the ledger: the money leaves the ledger for that holding, or comes back
    from it (and waits for a withdrawal)."""
    currency = order.currency
    iid = order.instrument_id
    fee_krw = fee if rate is None else usd_in_krw(fee, rate)
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
            broker_order_id=order.order_id if first else None,
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
    event_day: date | None = None,
    parts: dict[str, Decimal] | None = None,
) -> int:
    """A deposit or withdrawal the account shows (an event, as the screens list them), in its
    own currency, at the best-known time the money moved (`occurred_at`: the fill's time for a
    trade in the app, else the account snapshot that first showed it), on `event_day` (by default
    that time's KST date); booked at `at`."""
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
        event_date=event_day or kst_date(when),
        occurred_at=when,
        amount=amount,
        currency=currency,
        payload=payload,
        booked_at=at,
    )
    try:
        # The rules' shares of it (`parts`: a side of the owner's conversion, _conversion_parts).
        sleeves.split_inflow(conn, LIVE, kind, amount, currency, rate, event_id, at, parts)
    except LedgerError as exc:
        raise _MismatchError(
            "sleeves", {"currency": currency.value, "amount": str(amount), "why": str(exc)}
        ) from exc
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


def _cap_withdraw_waits(
    conn: sqlite3.Connection, currency: Currency, when: datetime, at: datetime
) -> None:
    """After the owner converted money out of `currency`: the cash that waits there for a
    withdrawal is at most the currency's cash left beyond the owner's new money of the day that
    is still held back (D48). Proceeds of an app sale he converted instead of withdrawing stop
    waiting (D47's way to move money from 한국 to 미국 without adding any); proceeds he did not
    touch keep waiting when he converts other money. The earliest waits go first, as for a
    withdrawal (_consume_withdraw_waits)."""
    cash = repo.load_state(conn, LIVE).cash_of(currency)
    fresh = new_money_waiting(conn, LIVE, when).get(currency, ZERO)
    cap = max(ZERO, cash - fresh)
    waiting = sum(
        (w.amount for w in repo.withdraw_waits(conn, LIVE) if w.currency is currency), ZERO
    )
    if waiting > cap:
        _consume_withdraw_waits(conn, currency, waiting - cap, at)


def _conversion(
    direction: FxDirection, source: Decimal, target: Decimal, rate: Decimal, basis: str
) -> list[_Move]:
    """The owner's conversion in the Toss app: money moving between his two accounts. A
    withdrawal from the currency he paid and a deposit into the one he got, at `rate` (so the
    ledger's P&L moves as for a paper conversion), marked as a conversion: the accounts read it
    as a transfer (api/views/accounts.py), the whole ledger's views do not list it, and D48
    counts the money it brought as new (engine/common.py). Booking the withdrawal caps the cash
    that waits for a withdrawal in that currency (_cap_withdraw_waits)."""
    extra: dict[str, Any] = {
        "reason": CONVERSION,
        "direction": direction.value,
        "from": source,
        "to": target,
        "rate": rate,
        "rate_basis": basis,  # 'balances': what the account showed; 'market': assumed
    }
    log: dict[str, Any] = {
        "conversion": direction.value,
        "from": str(source),
        "to": str(target),
        "event_ids": [],
    }
    return [
        _Move(
            CashFlowKind.WITHDRAWAL,
            direction.source,
            source,
            extra,
            rate=rate if direction.source is Currency.USD else None,
            conversion=log,
        ),
        _Move(
            CashFlowKind.DEPOSIT,
            direction.target,
            target,
            extra,
            rate=rate if direction.target is Currency.USD else None,
            conversion=log,
        ),
    ]


def _explain_conversion(
    conn: sqlite3.Connection,
    cfg: Config,
    at: datetime,
    residual: dict[Currency, Decimal],
    moves: list[_Move],
) -> dict[Currency, Decimal]:
    """Won and dollars that moved in opposite directions at about the market rate (within
    `live_fx_tolerance`): the owner converted in the app. Booked at the rate the balances show
    (what he paid for what he got: the spread is a real cost, it stays in the P&L). Live plans
    never convert (D47), so every conversion is the owner's (_conversion).

    A deposit or a withdrawal small enough to hide inside the band in the same five minutes
    reads as part of the rate here; the balances cannot tell the two apart. This reading keeps
    the P&L exact in the case that happens (a conversion on its own, with the spread it cost);
    the other reading would turn every spread into a made-up withdrawal."""
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
    moves.extend(_conversion(direction, source, target, rate, "balances"))
    return {Currency.KRW: ZERO, Currency.USD: ZERO}


def _explain_mixed(
    conn: sqlite3.Connection,
    at: datetime,
    snap: AccountSnapshot,
    residual: dict[Currency, Decimal],
    moves: list[_Move],
) -> dict[Currency, Decimal]:
    """Won and dollars that both moved, but not as one conversion: in the same direction (he
    deposited 3,000,000원 and converted 1,000,000원 of it: won +2,000,000, dollars +$718), or at
    a rate no market gave (he deposited 1,000,000원 and converted 3,000,000원). The owner moves
    money in won and gets dollars only by converting, so the dollar change is his conversion
    and the won left over his deposit or withdrawal.

    Only the balances are known, so the conversion's own rate is not: it is booked at the market
    rate. That reading keeps the ledger's P&L exact for what can be known: the conversion moves
    no P&L, and the money in (won deposited, dollars at the market rate) is the same as two
    deposits would have made it, to the won. Only the spread of that one conversion is out of
    sight (it was paid inside the deposit). The deposit comes before the conversion, the
    withdrawal after it, so the cash never goes below zero on the way."""
    krw, usd = residual[Currency.KRW], residual[Currency.USD]
    if krw == 0 or usd == 0:
        return residual
    rate = _rate(conn, snap.taken_at, at)
    won = usd_in_krw(abs(usd), rate)
    if usd > 0:
        direction, source, target = FxDirection.KRW_TO_USD, won, usd
        rest = krw + won  # the won that came in beyond what the conversion took
    else:
        direction, source, target = FxDirection.USD_TO_KRW, -usd, won
        rest = krw - won
    if rest > 0:
        moves.append(
            _Move(
                CashFlowKind.DEPOSIT,
                Currency.KRW,
                rest,
                {"reason": "unexplained-in", "with": CONVERSION},
            )
        )
    moves.extend(_conversion(direction, source, target, rate, "market"))
    if rest < 0:
        moves.append(
            _Move(
                CashFlowKind.WITHDRAWAL,
                Currency.KRW,
                -rest,
                {"reason": "unexplained-out", "with": CONVERSION},
                consume_waits=True,
            )
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
    conn: sqlite3.Connection,
    cfg: Config,
    at: datetime,
    started: date,
    pending: Sequence[BrokerOrder] = (),
) -> list[DueDividend]:
    """Dividends the live ledger is owed around now and has not booked (from the dividend data
    the paper ledger's job downloads; Toss reports none). `pending`: the owner's app fills of
    this reconciliation, not booked yet: they count for the shares held before the ex-date."""
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
        unbooked = [
            HeldFill(
                session_of(inst, o.filled_at),
                int(o.filled_qty) if o.side == "BUY" else -int(o.filled_qty),
            )
            for o in pending
            if o.instrument_id == inst.instrument_id
            and o.filled_at is not None
            and o.filled_qty == o.filled_qty.to_integral_value()
        ]
        qty = shares_before_ex_date(conn, LIVE, inst, div.ex_date, unbooked)
        if qty <= 0:
            continue
        amounts = after_tax(div.per_share, qty, inst.currency, tax_rate(cfg, inst.market))
        if amounts.net > 0:
            out.append(DueDividend(div, inst, qty, amounts.gross, amounts.net))
    return out


def _explain_dividend(
    conn: sqlite3.Connection,
    cfg: Config,
    at: datetime,
    currency: Currency,
    amount: Decimal,
    started_at: datetime,
    pending: Sequence[BrokerOrder],
    moves: list[_Move],
) -> Decimal:
    """Unexplained cash of `currency` that is a dividend the ledger is owed: the amount the
    broker paid (its tax is what counts), when it lies within the rounding of the tax of the
    expected net (tax_slack: the broker cuts each part of the tax its own way). Never a sum far
    from it: a deposit made while a dividend is due stays a deposit, and a dividend is never
    taken for more than its net (the old reading took up to the gross of any amount above half
    the net, and the real dividend became a deposit later). A dividend whose tax differs by more
    (a Korean ETF's taxable base below its distribution) reads as a deposit: the cash is right,
    only the income is counted as money in. Returns what is left."""
    for due in due_dividends(conn, cfg, at, kst_date(started_at), pending):
        if due.inst.currency is not currency:
            continue
        if abs(amount - due.net) <= tax_slack(currency):
            moves.append(_Move(CashFlowKind.DIVIDEND, currency, amount, due=due))
            return ZERO
    return amount


def _book_dividend(
    conn: sqlite3.Connection,
    cfg: Config,
    at: datetime,
    move: _Move,
    due: DueDividend,
    when: datetime,
    day: date,
    result: ReconcileResult,
) -> None:
    """Book a dividend the account paid: its amount is the broker's, dated when the account
    showed it."""
    currency, booked = move.currency, move.amount
    rate = _rate(conn, when, at) if currency is Currency.USD else None
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
        event_date=day,
        occurred_at=when,
        rule_id=RULE_ID if due.inst.instrument_id in rule_ids else None,
        amount=booked,
        currency=currency,
        ref=dividend_ref(due.inst.instrument_id, due.div.ex_date),
        payload=payload,
        booked_at=at,
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


def _check_positions(conn: sqlite3.Connection, snap: AccountSnapshot, own: set[str]) -> None:
    """The ledger's shares are the account's. Of a company that is not the index rule's ETF,
    the account may hold more: the owner's own shares, outside the ledger (_book_external_trade);
    never fewer."""
    state = repo.load_state(conn, LIVE)
    broker = {h.instrument_id: h.qty for h in snap.holdings}
    index = set(rule_instruments(conn))
    off: list[dict[str, str]] = []
    for iid in sorted(own | set(state.positions)):
        ledger_qty = Decimal(state.qty_of(iid))
        broker_qty = broker.get(iid, ZERO)
        if iid not in index and broker_qty > ledger_qty and sleeves.sleeve_rule_ids(conn, LIVE):
            continue  # his own shares beside the rule's
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
    ledger's gains so far stay as they were. Our own fills the ledger has not booked yet are
    booked first, as the trades they are: the account holds them, and the reconciliation that
    follows would book them again on top of the adopted numbers (a mismatch past any adoption;
    the reconciliation that would have booked them rolled back on the mismatch). The caller owns
    the transaction."""
    snap = live_repo.latest_snapshot(conn)
    reason = busy_reason(conn, cfg, snap, at)
    if reason is not None or snap is None:
        return {"result": "busy", "reason": reason or "no-snapshot"}
    if repo.start_event(conn, LIVE) is None:
        return {"result": "not-started"}
    conn.execute("SAVEPOINT live_adopt")

    def refused(reason: str) -> dict[str, Any]:
        # A refusal writes nothing, our late fills booked below included: the reconciliation
        # books them once the account matches.
        conn.execute("ROLLBACK TO live_adopt")
        conn.execute("RELEASE live_adopt")
        return {"result": "refused", "reason": reason}

    try:
        late = book_late_fills(conn, cfg, at, cover=True)
    except LedgerError as exc:
        # The ledger's cash cannot pay a fill it planned (money it never booked paid for it).
        return refused(f"late fill: {exc}")
    rate = _rate_or_none(conn, at)
    state = repo.load_state(conn, LIVE)
    own = ledger_instrument_ids(conn)
    broker = {h.instrument_id: h for h in snap.holdings}
    instruments = {iid: repo.get_instrument(conn, iid) for iid in own}
    changes: list[dict[str, Any]] = []
    positions = dict(state.positions)
    value_in = ZERO
    by_currency = dict.fromkeys(Currency, ZERO)  # money in per account, in its currency
    index = set(rule_instruments(conn))
    shared = bool(sleeves.sleeve_rule_ids(conn, LIVE))
    for iid in sorted(own):
        inst = instruments[iid]
        held = broker.get(iid)
        broker_qty = ZERO if held is None else held.qty
        if broker_qty != broker_qty.to_integral_value():
            return refused(f"fractional {iid} {broker_qty}")
        new_qty = int(broker_qty)
        old = positions.get(iid)
        old_qty = 0 if old is None else old.qty
        if iid not in index and new_qty > old_qty and shared:
            continue  # the owner's own shares of a pick stay outside (_check_positions)
        if new_qty == old_qty:
            continue
        price = None if held is None or held.last_price <= 0 else held.last_price
        if price is None:
            close = latest_close(conn, cfg, inst, at)
            if close is None:
                return refused(f"no price for {iid}")
            price = close.price
        delta = new_qty - old_qty
        value = (price * abs(delta)).quantize(_unit(inst.currency), rounding=ROUND_HALF_UP)
        value_krw = value
        if inst.currency is Currency.USD:
            if rate is None:
                return refused("no rate")
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
                return refused("no rate")
            diff_krw = usd_in_krw(diff, rate)
        value_in += diff_krw
        by_currency[currency] += diff
        cash_changes[currency.value] = str(diff)
    if not changes and not cash_changes:
        # Booking our late fills may have been all it took.
        conn.execute("RELEASE live_adopt")
        return {"result": "nothing-to-adopt", **({"lateFills": late} if late else {})}
    adopted = type(state)(
        cash=new_cash,
        positions=positions,
        realized_krw=state.realized_krw,
        fees_krw=state.fees_krw,
        contributions_krw=state.contributions_krw + value_in,
        income_krw=state.income_krw,
    )
    # The other rules' parts stay as their records have them (engine/sleeves.py): the account
    # must still hold them, or '지수 반반' would hold less than nothing.
    rest = adopted
    try:
        for rule_id in sleeves.sleeve_rule_ids(conn, LIVE):
            rest = sleeves.subtract(rest, ai_repo.load_sleeve(conn, LIVE, rule_id))
    except LedgerError as exc:
        return refused(f"sleeves: {exc}")
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
        booked_at=at,
    )
    refresh_cash_parts(conn, LIVE, at)
    conn.execute("RELEASE live_adopt")
    out = {"result": "adopted", "event_id": event_id, "positions": changes, "cash": cash_changes}
    return {**out, "lateFills": late} if late else out


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
    # What the plan leaves out: the owner's money of the next check's day (D48, a ledger that
    # has started), and the conversion that would bring the mix to the targets (D47).
    new_money: dict[Currency, Decimal] = field(default_factory=dict)
    new_money_from: datetime | None = None  # the check that uses it
    suggestion: FxSuggestion | None = None
    # The check that plans the first orders: the first weekday check after now. Turned on now,
    # live runs no check before it (first_live_check); the hash binds it.
    first_check: datetime | None = None


@dataclass(frozen=True)
class NotComputable:
    at: datetime
    cause: str  # 'stale' | 'other'
    detail: str


def buy_units(
    conn: sqlite3.Connection, cfg: Config, prices: Mapping[str, Decimal]
) -> dict[str, Decimal]:
    """What one share of a live buy of each instrument in `prices` takes at most at its plan
    price: the limit the send caps it at (on the tick) plus Toss's fee (broker/toss.py buy_unit).
    The live plans (the check, the preview, '3년 발굴') size their buys with it:
    PlanItem.buy_unit, discovery Holding.buy_unit."""
    status = live_repo.get_status(conn)
    commissions = {} if status is None else status.commissions
    out: dict[str, Decimal] = {}
    for iid, price in prices.items():
        inst = repo.get_instrument(conn, iid)
        if price is not None and price > 0:
            rate = fee_rate(cfg, commissions, inst)
            out[iid] = buy_unit(inst, price, cfg.live_limit_slippage, rate)
    return out


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
    check_at = next_check_at(cfg, at)
    new_money: dict[Currency, Decimal] = {}
    others: Plan | None = None  # the AI rule's first orders, at the first start
    if started:
        state = sleeves.base_view(conn, LIVE)
        held = withdraw_wait_amounts(repo.cash_parts(conn, LIVE))
        cash = {c: max(state.cash_of(c) - held.get(c, ZERO), ZERO) for c in Currency}
        plan_cash = cash
        qty = {iid: state.qty_of(iid) for iid in instruments}
        outside = [h for h in snap.holdings if h.instrument_id not in ledger_instrument_ids(conn)]
        # D48: what the owner brought on the day of that check waits for the one after it.
        new_money = capped(new_money_of_rule(conn, LIVE, sleeves.BASE_RULE, check_at), cash)
    else:
        try:
            opening = opening_from(snap, instruments, rate)
        except LiveStartError as exc:
            return NotComputable(at, "other", f"{exc.code}: {exc}")
        cash = dict(opening.cash)
        # The start gives the other rules their shares of the cash (start_live): '지수 반반''s
        # first orders spend the rest (its holdings at the start are its own), and '3년 발굴''s
        # first orders, planned the same way the tick will (engine/discovery_plan.py), are shown
        # with them. (Imported here: the discovery planner imports this module.)
        from autotrade.engine import discovery_plan

        plan_cash = dict(cash)
        ai_cash = dict.fromkeys(Currency, ZERO)
        for currency, amount in opening.cash.items():
            if amount > 0:
                for rule_id, part in sleeves.share_parts(conn, LIVE, amount, currency).items():
                    plan_cash[currency] -= part
                    if rule_id == AI_RULE:
                        ai_cash[currency] += part
        if any(v > 0 for v in ai_cash.values()):
            others = discovery_plan.first_plan(conn, cfg, LIVE, at, ai_cash)
        qty = {
            iid: opening.positions[iid].qty if iid in opening.positions else 0
            for iid in instruments
        }
        outside = opening.outside
    caps = buy_units(conn, cfg, {iid: c.price for iid, c in closes.items() if c is not None})
    items: list[PlanItem] = []
    for iid in rule.instrument_ids:
        close = closes[iid]
        assert close is not None  # checked above
        items.append(
            PlanItem(
                instruments[iid], rule.target_of(iid), qty[iid], close.price, buy_unit=caps.get(iid)
            )
        )
    plan = plan_per_currency(
        PlanInput(
            items=tuple(items),
            threshold=rule.threshold,
            fx_rate=rate,
            free_krw=plan_cash[Currency.KRW] - new_money.get(Currency.KRW, ZERO),
            free_usd=plan_cash[Currency.USD] - new_money.get(Currency.USD, ZERO),
            fees=cfg.fees,
            fx_step_krw=cfg.fx_step_krw,
        )
    )
    if others is not None and others.has_orders:
        # Shown and compared as one list: the orders of both rules go out at the same times.
        plan = replace(plan, sells=plan.sells + others.sells, buys=plan.buys + others.buys)
    specs = stage_specs(plan)
    due = schedule(specs, check_at, slotter_for(cfg))
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
    signature = "|".join(sorted(p.rsplit(":", 1)[0] for p in parts))
    material = {
        "current": [
            (label, None if inst is None else inst.instrument_id, str(krw))
            for label, inst, krw in current
        ],
        "orders": sorted(parts),
        "snapshot": snap.snapshot_id,
        "first_check": to_iso(check_at),
    }
    digest = hashlib.sha256(dumps(material).encode()).hexdigest()[:16]
    outside_rows = [(h, _holding_krw(h, rate)) for h in outside]
    targets = [
        (instruments[iid], (rule.target_of(iid) * _rule_share(conn)).quantize(Decimal("0.1")))
        for iid in rule.instrument_ids
    ]
    mix = CurrencyMix(
        kr_krw=sum((krw for label, i, krw in current if _of(label, i) is Currency.KRW), ZERO),
        us_krw=sum((krw for label, i, krw in current if _of(label, i) is Currency.USD), ZERO),
        target_kr=sum(
            (
                rule.target_of(iid)
                for iid in rule.instrument_ids
                if instruments[iid].currency is Currency.KRW
            ),
            ZERO,
        ),
    )
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
        new_money=new_money,
        new_money_from=first_check_after(cfg, kst_date(check_at)),
        suggestion=suggest(mix, rule.threshold, rate, cfg.fx_step_krw),
        first_check=check_at,
    )


def _of(label: str, inst: Instrument | None) -> Currency:
    """The currency of a preview's current row: a holding's, or the cash row's."""
    if inst is not None:
        return inst.currency
    return Currency.USD if label == "usd-cash" else Currency.KRW


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
            payload={
                **payload,
                "account_krw": str(data.account_krw),
                "first_check": None if data.first_check is None else to_iso(data.first_check),
            },
        ),
    )
    live_repo.prune_previews(conn, data.computed_at - timedelta(days=2))


def preview_changed(stored: live_repo.StoredPreview | None, fresh: PreviewData) -> bool:
    """인계 13: turning live on recomputes the preview and stops when its amounts moved by 1% or
    more, it orders something else, or its first check is another one (the owner saw the first
    orders go out at that check's times: shown before 08:30, approved after it, they go the next
    morning). Without orders the account's value is compared."""
    if stored is None:
        return True
    if stored.hash == fresh.hash:
        return False
    first = None if fresh.first_check is None else to_iso(fresh.first_check)
    if stored.signature != fresh.signature or stored.payload.get("first_check") != first:
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


def first_live_check(conn: sqlite3.Connection, cfg: Config) -> datetime | None:
    """The first check of the live period: the first weekday check time strictly after the
    latest 'live-on' (engine/status.py next_check_at), the one the approved preview showed
    (PreviewData.first_check). No live check or retry runs before it: turned on, or on again,
    after the day's check time, live waits for the next weekday's 08:30 instead of planning
    within minutes as a missed check. None while live was never turned on."""
    periods = live_periods(conn)
    return None if not periods else next_check_at(cfg, periods[-1][0])


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
    # maintenance | error | old | not-tradable | conflict | conditional | mismatch | never
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
    if status.ok_at is None or at - status.ok_at > sync_max_age(cfg, at):
        return no("old")
    if status.revoked:
        return no("conflict")
    if any(v != "ok" for v in status.tradable.values()) or not status.tradable:
        return no("not-tradable")
    if status.conditional:
        # An armed 조건주문 on the account (the old quant's, the app's) places an order of its
        # own when triggered: live is not turned on while one is open (cancel it in the Toss
        # app). While live, the reconciliation books what it fills as the owner's trade.
        return no("conditional")
    if repo.start_event(conn, LIVE) is not None and status.reconcile_state == "mismatch":
        return no("mismatch")
    if days_left is not None and days_left < 0:
        return no("expired")
    return LinkCheck(True, None, status.ok_at, status.account_tail, expires, days_left)


def cancel_failed(conn: sqlite3.Connection) -> list[live_repo.BrokerOrderRow]:
    return [r for r in live_repo.cancel_rows(conn, LIVE, ["failed"]) if r.open]


def cancel_pending(conn: sqlite3.Connection) -> list[live_repo.BrokerOrderRow]:
    return [r for r in live_repo.cancel_rows(conn, LIVE, ["requested"]) if r.open]


# ── the sync's cadence ───────────────────────────────────────────────────────────────────
#
# The tick looks at Toss every 5 minutes while a market is open or anything of ours is moving,
# and every cfg.broker_sync_slow (30 minutes) otherwise: nights, weekends and holidays with no
# order of ours at Toss, no cancel to carry out, no mode change or turn-on preview just now.
# The sync is the only code that calls Toss (jobs/live_tasks.py); this decides only how often.

# The mode screen asked for a turn-on preview (GET /api/mode): the preview needs an account
# snapshot within cfg.broker_max_age, so the tick looks every 5 minutes for a while after.
SYNC_WANTED_AT = "broker.sync_wanted_at"
# From here to midnight KST the tick looks every time: money the account shows on day D is
# used from the next weekday (D48), so a deposit made late in the evening is still seen, and
# dated, the day it arrived, as with the 5-minute look. Half an hour: six looks, so a few
# minutes of Toss not answering do not move a late deposit to the next day.
DAY_END = time(23, 30)
# Half a tick: a sync due every 30 minutes runs on the tick near the 30-minute mark, not the one
# after it (the last look's time is when the previous sync finished).
SYNC_TOLERANCE = timedelta(minutes=2, seconds=30)


def markets_closed(at: datetime) -> bool:
    """Both regular sessions (KRX in KST, NYSE in ET) are closed at `at`: their calendars'
    weekends, holidays and hours. Outside the calendars' years it says False (look every tick)."""
    try:
        for cal, day in ((KRX, kst_date(at)), (NYSE, et_date(at))):
            if cal.is_trading_day(day) and cal.session_open(day) <= at < cal.session_close(day):
                return False
    except CalendarRangeError:
        return False
    return True


def sync_max_age(cfg: Config, at: datetime) -> timedelta:
    """How old the tick's last look at Toss (its link check, its account snapshot and the
    reconciliation of it) may be at `at` and still be current. cfg.broker_max_age while the
    tick looks every 5 minutes; broker_max_age + broker_sync_slow while both markets are closed
    and for broker_max_age after one opens (the first 5-minute looks then catch up), so the
    slower night cadence never reads as late on the screens. The turn-on preview keeps the
    strict broker_max_age (preview_data), with a fresh look asked for by the mode screen."""
    if markets_closed(at) or markets_closed(at - cfg.broker_max_age):
        return cfg.broker_max_age + cfg.broker_sync_slow
    return cfg.broker_max_age


def request_sync(conn: sqlite3.Connection, at: datetime) -> None:
    """The mode screen showed (or tried to show) a turn-on preview: look at Toss every tick for
    the next cfg.broker_sync_slow, so the preview and the turn-on find a fresh snapshot within a
    tick even at night. The caller owns the transaction."""
    repo.set_setting(conn, SYNC_WANTED_AT, to_iso(at), at)


def _setting_time(conn: sqlite3.Connection, key: str) -> datetime | None:
    value = repo.get_setting(conn, key)
    if not value:
        return None
    try:
        return from_iso(value)
    except ValueError:
        return None


def fast_sync_reason(conn: sqlite3.Connection, cfg: Config, at: datetime) -> str | None:
    """Why the tick looks at Toss on this tick, whatever the last look's time; None when the
    slow cadence applies (every cfg.broker_sync_slow). The tick adds one more reason: a live
    task (stages, check, retry, snapshot) due on the same tick (jobs/tick.py)."""
    if not markets_closed(at):
        return "market-open"
    if at.astimezone(KST).time() >= DAY_END:
        return "day-end"
    if live_repo.broker_orders_of(conn, LIVE, live_repo.OPEN_STATES):
        return "orders"  # at Toss, or its sending was cut off (resent within 9 minutes)
    if live_repo.cancel_rows(conn, LIVE, ["requested", "failed"]):
        return "cancel"  # live off, a resolve, or a cancel to try again
    changed = _setting_time(conn, MODE_CHANGED_AT)
    if changed is not None and at - changed < cfg.broker_sync_slow:
        return "mode-changed"
    wanted = _setting_time(conn, SYNC_WANTED_AT)
    if wanted is not None and at - wanted < cfg.broker_sync_slow:
        return "preview"
    return None


def settle_ambiguous(
    conn: sqlite3.Connection, row: live_repo.BrokerOrderRow, pick: str | None, at: datetime
) -> str:
    """An order whose sending was cut off and that more than one of the account's orders could
    be, settled with what the owner saw in the Toss app (engine/todos.py, `resolve
    broker-mismatch:order:<id> --pick`): `pick`, the candidate that is ours, or None, none is.

    - Ours is `pick`: the order is that one ('sent' with its id, or 'done' when the search saw
      it over); the next sync reads it and its fill is booked as usual (by the stage, or as a
      late fill when its plan was closed meanwhile).
    - None is ours: our order never reached Toss ('not-sent', lost). Its stage fails and is sent
      again the next trading day like any order that did not go; when its plan was closed
      meanwhile (live off), the order is cancelled.
    Either way the other candidates are the owner's: the reconciliation books what they filled.
    The row stops keeping the account busy, and a cancel asked for it meanwhile (live off) is
    carried out on the chosen order by the next tick, or has nothing left to cancel. The caller
    owns the transaction. Returns what it became: the order id, or 'none'."""
    if pick is None:
        live_repo.record_not_sent(
            conn,
            order_id=row.order_id,
            ledger_id=LIVE,
            client_order_id=row.client_order_id,
            code="lost",
            detail="the owner checked the Toss app: none of the candidates is ours",
            at=at,
            request=row.request,
        )
        if row.cancel_state in ("requested", "failed"):
            live_repo.record_cancel(conn, row.order_id, "done", None, at)
        order = repo.get_order(conn, row.order_id)
        plan = repo.get_plan(conn, order.plan_id)
        if order.status == "pending" and plan.status not in repo.OPEN_PLAN_STATUSES:
            repo.cancel_order(conn, order.order_id)
        return "none"
    found = [c for c in row.candidates if str(c.get("order", {}).get("order_id")) == pick]
    if not found:
        raise ValueError(f"{pick} is not a candidate of order {row.order_id}")
    view = BrokerOrder.from_json(found[0]["order"])
    live_repo.mark_sent(conn, row.order_id, view.order_id, at)
    over = view.terminal or bool(found[0].get("closed"))
    live_repo.record_broker_view(conn, row.order_id, view, at, finished=over)
    return view.order_id


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
