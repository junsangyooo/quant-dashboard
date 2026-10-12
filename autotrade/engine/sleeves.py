"""Rules sharing one ledger (PHASE2.md §1 규칙 몫).

The base rule ('지수 반반') owns whatever no other rule owns. Every other rule keeps a sleeve inside
the ledger: its own positions, cash and totals. The ledger stays the account's truth; the sleeves
are bookkeeping that the same records rebuild (verify_sleeves): the sleeve's share of each inflow
(sleeve_flows) and the fills of the rule's own plans.

Money moves between rules only as it comes in, by the target shares of that day:
- the start amount and deposits are split by the shares (each part rounded down to the won or
  cent; the base rule keeps the rest), withdrawals likewise;
- a dividend goes to the rules that held the shares before the ex-date, in proportion.
Nothing moves automatically afterwards: the parts may drift from their targets (taxes and costs;
an open question in PHASE2.md). A rule's orders only spend and sell what its own part holds.

Each rule keeps its own cost basis (audit E8). Quantities, cash and the money totals add up, so
the base rule's are the ledger's minus the sleeves'. Average costs do not: the ledger pools one
average over both rules' shares of the same ETF (as a broker shows it), so the base rule's cost
and realized gains come from its own fills (own_book), the same arithmetic a sleeve uses. When
the AI rule sells shares it parked in KOSPI200, '지수 반반''s cost and realized gains do not move.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import ROUND_FLOOR, Decimal

from autotrade.db import ai_repo, repo
from autotrade.db.models import FillRow
from autotrade.domain.dividends import HeldFill, qty_before_ex_date
from autotrade.domain.instruments import Currency, Market
from autotrade.domain.ledger import (
    CashFlowKind,
    FxFill,
    LedgerError,
    LedgerState,
    Position,
    TradeFill,
    apply_cash_flow,
    apply_fx,
    apply_trade,
    same_to_the_won,
)
from autotrade.domain.money import CENT, WON, ZERO, usd_in_krw
from autotrade.domain.planner import FxDirection
from autotrade.timeutil import et_date, kst_date

BASE_RULE = "index_half"
HUNDRED = Decimal(100)


def sleeve_rule_ids(conn: sqlite3.Connection, ledger_id: str) -> list[str]:
    """Rules other than the base rule with a share or a sleeve in this ledger."""
    ids = {r for r, pct in ai_repo.shares(conn, ledger_id).items() if pct > 0}
    ids |= set(ai_repo.sleeve_rules(conn, ledger_id))
    ids.discard(BASE_RULE)
    return sorted(ids)


def subtract(a: LedgerState, b: LedgerState) -> LedgerState:
    cash = {c: a.cash_of(c) - b.cash_of(c) for c in Currency}
    short = [c.value for c, v in cash.items() if v < 0]
    if short:
        raise LedgerError(f"sleeves hold more {', '.join(short)} cash than the ledger")
    positions: dict[str, Position] = {}
    for iid, pa in a.positions.items():
        pb = b.positions.get(iid)
        if pb is None:
            positions[iid] = pa
            continue
        qty = pa.qty - pb.qty
        if qty < 0:
            raise LedgerError(f"{iid}: a sleeve holds {pb.qty}, the ledger only {pa.qty}")
        if qty > 0:
            positions[iid] = Position(
                iid, pa.currency, qty, pa.cost_native - pb.cost_native, pa.cost_krw - pb.cost_krw
            )
    missing = set(b.positions) - set(a.positions)
    if missing:
        raise LedgerError(f"sleeve holds what the ledger does not: {sorted(missing)}")
    return LedgerState(
        cash=cash,
        positions=positions,
        realized_krw=a.realized_krw - b.realized_krw,
        fees_krw=a.fees_krw - b.fees_krw,
        contributions_krw=a.contributions_krw - b.contributions_krw,
        income_krw=a.income_krw - b.income_krw,
    )


@dataclass(frozen=True)
class OwnBook:
    """A rule's positions and realized gains from its own trade fills (its own average cost)."""

    positions: dict[str, Position]
    realized_krw: Decimal
    gaps: frozenset[str]  # instruments whose history the fills do not cover


def own_book(fills: Iterable[FillRow]) -> OwnBook:
    """Fold trade fills with the ledger's own arithmetic (cash is not the point here). A sale of
    shares the fills never bought (a ledger seeded mid-way) marks that instrument a gap."""
    state = LedgerState(cash=dict.fromkeys(Currency, Decimal("1e18")))
    gaps: set[str] = set()
    for fill in fills:
        if fill.kind != "trade" or fill.instrument_id is None or fill.qty is None:
            continue
        if fill.price is None or fill.instrument_id in gaps:
            continue
        trade = fill.trade()
        try:
            state = apply_trade(state, trade)
        except LedgerError:
            gaps.add(fill.instrument_id)
    return OwnBook(dict(state.positions), state.realized_krw, frozenset(gaps))


def with_own_costs(rest: LedgerState, book: OwnBook) -> LedgerState:
    """The ledger-minus-sleeves state with the rule's own cost basis and realized gains. Where
    the fills do not account for every share (a ledger seeded mid-way), the subtraction stays."""
    positions: dict[str, Position] = {}
    whole = not book.gaps
    for iid, pos in rest.positions.items():
        mine = book.positions.get(iid)
        if iid in book.gaps or mine is None or mine.qty != pos.qty:
            positions[iid] = pos
            whole = False
            continue
        positions[iid] = Position(iid, pos.currency, pos.qty, mine.cost_native, mine.cost_krw)
    if any(iid not in rest.positions for iid in book.positions):
        whole = False
    return replace(
        rest,
        positions=positions,
        realized_krw=book.realized_krw if whole else rest.realized_krw,
    )


def base_view(conn: sqlite3.Connection, ledger_id: str) -> LedgerState:
    """The base rule's part: the ledger minus every sleeve, with its own cost basis."""
    state = repo.load_state(conn, ledger_id)
    rules = sleeve_rule_ids(conn, ledger_id)
    if not rules:
        return state  # the ledger is the base rule's alone
    for rule_id in rules:
        state = subtract(state, ai_repo.load_sleeve(conn, ledger_id, rule_id))
    return with_own_costs(state, own_book(repo.fills_of_rule(conn, ledger_id, BASE_RULE)))


def view(conn: sqlite3.Connection, ledger_id: str, rule_id: str) -> LedgerState:
    if rule_id == BASE_RULE:
        return base_view(conn, ledger_id)
    return ai_repo.load_sleeve(conn, ledger_id, rule_id)


def _floor(amount: Decimal, currency: Currency) -> Decimal:
    return amount.quantize(WON if currency is Currency.KRW else CENT, rounding=ROUND_FLOOR)


def split_inflow(
    conn: sqlite3.Connection,
    ledger_id: str,
    kind: CashFlowKind,
    amount: Decimal,
    currency: Currency,
    krw_rate: Decimal | None,
    event_id: int | None,
    at: datetime,
) -> dict[str, Decimal]:
    """Give each sleeve its share of a start, deposit or withdrawal. Returns the parts."""
    if kind is CashFlowKind.DIVIDEND:
        raise ValueError("dividends follow the shares held, see split_dividend")
    parts: dict[str, Decimal] = {}
    shares = ai_repo.shares(conn, ledger_id)
    for rule_id in sleeve_rule_ids(conn, ledger_id):
        pct = shares.get(rule_id, ZERO)
        part = _floor(amount * pct / HUNDRED, currency)
        if part <= 0:
            continue
        state = apply_cash_flow(
            ai_repo.load_sleeve(conn, ledger_id, rule_id), kind, part, currency, krw_rate
        )
        ai_repo.save_sleeve(conn, ledger_id, rule_id, state, at)
        ai_repo.insert_sleeve_flow(
            conn,
            ledger_id=ledger_id,
            rule_id=rule_id,
            event_id=event_id,
            kind=kind.value,
            amount=part,
            currency=currency,
            krw_rate=krw_rate,
            occurred_at=at,
        )
        parts[rule_id] = part
    return parts


def _session(market: Market, at: datetime) -> date:
    return et_date(at) if market is Market.US else kst_date(at)


def split_dividend(
    conn: sqlite3.Connection,
    ledger_id: str,
    instrument_id: str,
    ex_date: date,
    ledger_qty: int,
    net: Decimal,
    currency: Currency,
    krw_rate: Decimal | None,
    event_id: int | None,
    at: datetime,
) -> dict[str, Decimal]:
    """Give each sleeve the part of a booked dividend its shares earned. Returns the parts."""
    if ledger_qty <= 0:
        return {}
    inst = repo.get_instrument(conn, instrument_id)
    parts: dict[str, Decimal] = {}
    for rule_id in sleeve_rule_ids(conn, ledger_id):
        state = ai_repo.load_sleeve(conn, ledger_id, rule_id)
        fills = [
            HeldFill(_session(inst.market, f.filled_at), f.qty if f.side == "buy" else -f.qty)
            for f in repo.fills_of_rule(conn, ledger_id, rule_id)
            if f.instrument_id == instrument_id and f.qty
        ]
        held = qty_before_ex_date(state.qty_of(instrument_id), fills, ex_date)
        if held <= 0:
            continue
        part = _floor(net * held / ledger_qty, currency)
        if part <= 0:
            continue
        state = apply_cash_flow(state, CashFlowKind.DIVIDEND, part, currency, krw_rate)
        ai_repo.save_sleeve(conn, ledger_id, rule_id, state, at)
        ai_repo.insert_sleeve_flow(
            conn,
            ledger_id=ledger_id,
            rule_id=rule_id,
            event_id=event_id,
            kind="dividend",
            amount=part,
            currency=currency,
            krw_rate=krw_rate,
            occurred_at=at,
        )
        parts[rule_id] = part
    return parts


def apply_trade_fill(
    conn: sqlite3.Connection, ledger_id: str, rule_id: str, fill: TradeFill, at: datetime
) -> None:
    if rule_id == BASE_RULE:
        return
    state = apply_trade(ai_repo.load_sleeve(conn, ledger_id, rule_id), fill)
    ai_repo.save_sleeve(conn, ledger_id, rule_id, state, at)


def apply_fx_fill(
    conn: sqlite3.Connection, ledger_id: str, rule_id: str, fill: FxFill, at: datetime
) -> None:
    if rule_id == BASE_RULE:
        return
    state = apply_fx(ai_repo.load_sleeve(conn, ledger_id, rule_id), fill)
    ai_repo.save_sleeve(conn, ledger_id, rule_id, state, at)


def sleeve_value_krw(state: LedgerState, prices_krw: dict[str, Decimal], rate: Decimal) -> Decimal:
    """Cash (dollars at the rate) plus positions at won unit prices."""
    total = state.cash_of(Currency.KRW) + usd_in_krw(state.cash_of(Currency.USD), rate)
    for iid, pos in state.positions.items():
        total += prices_krw.get(iid, ZERO) * pos.qty
    return total


# ── rebuild (the invariant) ───────────────────────────────────────────────────────────────


def rebuild_sleeve(conn: sqlite3.Connection, ledger_id: str, rule_id: str) -> LedgerState:
    """Fold the sleeve's inflows and the fills of its rule's plans, in time order."""
    items: list[tuple[datetime, int, int, object]] = []
    for flow in ai_repo.sleeve_flows(conn, ledger_id, rule_id):
        order = 2 if flow.kind == "withdrawal" else 0
        items.append((flow.occurred_at, order, flow.flow_id, flow))
    for fill in repo.fills_of_rule(conn, ledger_id, rule_id):
        items.append((fill.filled_at, 1, fill.fill_id, fill))
    items.sort(key=lambda x: (x[0], x[1], x[2]))
    state = LedgerState()
    for _, _, _, item in items:
        if isinstance(item, ai_repo.SleeveFlowRow):
            state = apply_cash_flow(
                state, CashFlowKind(item.kind), item.amount, item.currency, item.krw_rate
            )
            continue
        assert isinstance(item, FillRow)
        if item.kind == "fx":
            if item.fx_direction is None or item.received is None or item.krw_rate is None:
                raise ValueError(f"fill {item.fill_id}: incomplete conversion")
            state = apply_fx(
                state,
                FxFill(FxDirection(item.fx_direction), item.gross, item.received, item.krw_rate),
            )
            continue
        if item.instrument_id is None or item.qty is None or item.price is None:
            raise ValueError(f"fill {item.fill_id}: incomplete trade")
        state = apply_trade(state, item.trade())
    return state


def verify_sleeves(conn: sqlite3.Connection, ledger_id: str) -> list[str]:
    """Differences between rebuilt and stored sleeves (empty = identical to the won), and
    between the base rule's own fills and the ledger minus the sleeves (share counts)."""
    problems: list[str] = []
    rules = ai_repo.sleeve_rules(conn, ledger_id)
    for rule_id in rules:
        rebuilt = rebuild_sleeve(conn, ledger_id, rule_id)
        stored = ai_repo.load_sleeve(conn, ledger_id, rule_id)
        problems += [f"{rule_id}: {p}" for p in same_to_the_won(rebuilt, stored)]
        for name in ("realized_krw", "fees_krw", "contributions_krw", "income_krw"):
            a, b = getattr(rebuilt, name), getattr(stored, name)
            if a != b:
                problems.append(f"{rule_id} {name}: {a} != {b}")
    if rules:
        rest = repo.load_state(conn, ledger_id)
        for rule_id in rules:
            rest = subtract(rest, ai_repo.load_sleeve(conn, ledger_id, rule_id))
        book = own_book(repo.fills_of_rule(conn, ledger_id, BASE_RULE))
        for iid in sorted(set(rest.positions) | set(book.positions) | book.gaps):
            own = book.positions[iid].qty if iid in book.positions else 0
            if iid in book.gaps or own != rest.qty_of(iid):
                problems.append(
                    f"{BASE_RULE} {iid}: own fills hold {own}, the ledger minus the sleeves"
                    f" {rest.qty_of(iid)}"
                )
    return problems
