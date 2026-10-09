"""Rebuild a ledger from its records and compare it with the stored one (ops notes 불변식).

The records are the cash-flow events (start, deposit, withdrawal, dividend) and the fills. They are
folded in time order with the same pure functions the engine used; the result must equal the
positions and cash tables to the won.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from decimal import Decimal

from autotrade.db import repo
from autotrade.db.models import EventRow, FillRow
from autotrade.domain.instruments import Currency
from autotrade.domain.ledger import (
    CashFlowKind,
    FxFill,
    LedgerState,
    TradeFill,
    apply_cash_flow,
    apply_fx,
    apply_trade,
    same_to_the_won,
)
from autotrade.domain.planner import FxDirection, Side

# At the same instant: money in, then fills, then money out.
_ORDER = {"start": 0, "deposit": 0, "dividend": 0, "fill": 1, "withdrawal": 2}


def _key(stamp: datetime, kind: str, seq: int) -> tuple[datetime, int, int]:
    return stamp, _ORDER[kind], seq


def _apply_event(state: LedgerState, ev: EventRow) -> LedgerState:
    if ev.amount is None:
        raise ValueError(f"event {ev.event_id} has no amount")
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
    return apply_trade(
        state,
        TradeFill(
            instrument_id=fill.instrument_id,
            currency=fill.currency,
            side=Side(fill.side),
            qty=fill.qty,
            price=fill.price,
            fee=fill.fee,
            krw_rate=fill.krw_rate,
        ),
    )


def rebuild_state(conn: sqlite3.Connection, ledger_id: str) -> LedgerState:
    items: list[tuple[tuple[datetime, int, int], EventRow | FillRow]] = []
    for ev in repo.events_of_ledger(conn, ledger_id, list(repo.CASH_FLOW_KINDS)):
        items.append((_key(ev.occurred_at, ev.kind, ev.event_id), ev))
    for fill in repo.fills_of_ledger(conn, ledger_id):
        items.append((_key(fill.filled_at, "fill", fill.fill_id), fill))
    items.sort(key=lambda pair: pair[0])
    state = LedgerState()
    for _, item in items:
        state = (
            _apply_event(state, item) if isinstance(item, EventRow) else _apply_fill(state, item)
        )
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
