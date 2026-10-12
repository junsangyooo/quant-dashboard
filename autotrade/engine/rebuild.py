"""Rebuild a ledger from its records and compare it with the stored one (ops notes 불변식).

The records are the cash-flow events (start, deposit, withdrawal, dividend), the fills, and for
the live ledger the fills and conversions the engine did not send (external_fills, 'ledger'
ones: the owner's trades of the rule's instruments in the Toss app). They are folded in time
order with the same pure functions the engine used; the result must equal the positions and
cash tables to the won. A live ledger starts from the account it adopted (the start event's
'opening': its cash and positions, PHASE3.md 2.6).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

from autotrade.db import live_repo, repo
from autotrade.db.live_repo import ExternalFill
from autotrade.db.models import EventRow, FillRow
from autotrade.domain.instruments import Currency
from autotrade.domain.ledger import (
    CashFlowKind,
    FxFill,
    LedgerState,
    Position,
    TradeFill,
    apply_cash_flow,
    apply_fx,
    apply_trade,
    opening_state,
    same_to_the_won,
)
from autotrade.domain.planner import FxDirection, Side

# At the same instant: money in, then fills, then money out.
_ORDER = {"start": 0, "deposit": 0, "dividend": 0, "fill": 1, "ext": 1, "withdrawal": 2}


def _key(stamp: datetime, kind: str, seq: int) -> tuple[datetime, int, int]:
    return stamp, _ORDER[kind], seq


def opening_of(ev: EventRow) -> LedgerState | None:
    """The state a live start adopted (None for a start of cash alone)."""
    opening = ev.payload.get("opening")
    if not isinstance(opening, dict) or ev.amount is None:
        return None
    cash = {Currency(str(k)): Decimal(str(v)) for k, v in (opening.get("cash") or {}).items()}
    positions: dict[str, Position] = {}
    for p in opening.get("positions") or []:
        iid = str(p["instrument_id"])
        positions[iid] = Position(
            iid,
            Currency(str(p["currency"])),
            int(p["qty"]),
            Decimal(str(p["cost_native"])),
            Decimal(str(p["cost_krw"])),
        )
    return opening_state(cash, positions, ev.amount)


def adopted_of(ev: EventRow) -> LedgerState | None:
    """The state `adopt-broker` set (the live ledger made equal to the account)."""
    adopt = ev.payload.get("adopt")
    data = adopt.get("state") if isinstance(adopt, dict) else None
    if not isinstance(data, dict):
        return None
    positions: dict[str, Position] = {}
    for p in data.get("positions") or []:
        iid = str(p["instrument_id"])
        positions[iid] = Position(
            iid,
            Currency(str(p["currency"])),
            int(p["qty"]),
            Decimal(str(p["cost_native"])),
            Decimal(str(p["cost_krw"])),
        )
    return LedgerState(
        cash={Currency(str(k)): Decimal(str(v)) for k, v in (data.get("cash") or {}).items()},
        positions=positions,
        realized_krw=Decimal(str(data["realized_krw"])),
        fees_krw=Decimal(str(data["fees_krw"])),
        contributions_krw=Decimal(str(data["contributions_krw"])),
        income_krw=Decimal(str(data["income_krw"])),
    )


def _apply_event(state: LedgerState, ev: EventRow) -> LedgerState:
    if ev.amount is None:
        raise ValueError(f"event {ev.event_id} has no amount")
    if ev.kind == "start":
        opened = opening_of(ev)
        if opened is not None:
            return opened
    adopted = adopted_of(ev)
    if adopted is not None:
        return adopted
    rate = ev.payload.get("krw_rate")
    return apply_cash_flow(
        state,
        CashFlowKind(ev.kind),
        ev.amount,
        ev.currency or Currency.KRW,
        None if rate is None else Decimal(str(rate)),
    )


def _apply_fill(state: LedgerState, fill: FillRow) -> LedgerState:
    if fill.kind == "fx":
        if fill.fx_direction is None or fill.received is None or fill.krw_rate is None:
            raise ValueError(f"fill {fill.fill_id}: incomplete conversion")
        return apply_fx(
            state, FxFill(FxDirection(fill.fx_direction), fill.gross, fill.received, fill.krw_rate)
        )
    if fill.instrument_id is None or fill.qty is None or fill.price is None:
        raise ValueError(f"fill {fill.fill_id}: incomplete trade")
    return apply_trade(state, fill.trade())


def external_trade(ext: ExternalFill) -> TradeFill:
    if ext.instrument_id is None or ext.qty is None or ext.qty <= 0:
        raise ValueError(f"external fill {ext.ext_id}: incomplete trade")
    return TradeFill(
        instrument_id=ext.instrument_id,
        currency=ext.currency,
        side=Side(ext.side),
        qty=ext.qty,
        price=ext.gross / ext.qty,
        fee=ext.fee,
        krw_rate=ext.krw_rate,
        gross_amount=ext.gross,
    )


def external_fx(ext: ExternalFill) -> FxFill:
    if ext.received is None or ext.krw_rate is None:
        raise ValueError(f"external fill {ext.ext_id}: incomplete conversion")
    return FxFill(FxDirection(ext.side), ext.gross, ext.received, ext.krw_rate)


def _apply_external(state: LedgerState, ext: ExternalFill) -> LedgerState:
    if ext.kind == "fx":
        return apply_fx(state, external_fx(ext))
    return apply_trade(state, external_trade(ext))


Record = EventRow | FillRow | ExternalFill


def rebuild_state(conn: sqlite3.Connection, ledger_id: str) -> LedgerState:
    items: list[tuple[tuple[datetime, int, int], Record]] = []
    for ev in repo.events_of_ledger(conn, ledger_id, list(repo.CASH_FLOW_KINDS)):
        items.append((_key(ev.occurred_at, ev.kind, ev.event_id), ev))
    for fill in repo.fills_of_ledger(conn, ledger_id):
        items.append((_key(fill.filled_at, "fill", fill.fill_id), fill))
    for ext in live_repo.externals_of(conn, ledger_id, "ledger"):
        items.append((_key(ext.filled_at, "ext", ext.ext_id), ext))
    items.sort(key=lambda pair: pair[0])
    state = LedgerState()
    for _, item in items:
        if isinstance(item, EventRow):
            state = _apply_event(state, item)
        elif isinstance(item, FillRow):
            state = _apply_fill(state, item)
        else:
            state = _apply_external(state, item)
    return state


def verify_ledger(conn: sqlite3.Connection, ledger_id: str) -> list[str]:
    """Differences between the rebuilt and the stored ledger (empty = identical to the won)."""
    rebuilt = rebuild_state(conn, ledger_id)
    stored = repo.load_state(conn, ledger_id)
    problems = same_to_the_won(rebuilt, stored)
    for name in ("realized_krw", "fees_krw", "contributions_krw", "income_krw"):
        a, b = getattr(rebuilt, name), getattr(stored, name)
        if a != b:
            problems.append(f"{name}: {a} != {b}")
    return problems
