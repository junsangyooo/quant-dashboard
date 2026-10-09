"""Helpers shared by the autotrade tests."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time
from decimal import Decimal

from autotrade.db import repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency
from autotrade.domain.ledger import LedgerState, Position
from autotrade.timeutil import KST

# Phase-1 tests reproduce the example table with '지수 반반' alone (§4: 100% of the ledger).
PHASE1_SHARES = {
    "paper": {"index_half": Decimal(100), "discovery_3y": Decimal(0)},
    "live": {"index_half": Decimal(100), "discovery_3y": Decimal(0)},
}
PHASE1_ENV = {"AUTOTRADE_PAPER_SHARES": "index_half=100,discovery_3y=0"}


def kst(text: str) -> datetime:
    """'2026-10-07 08:30' -> aware KST datetime."""
    return datetime.fromisoformat(text).replace(tzinfo=KST)


def seed_ledger(
    conn: sqlite3.Connection,
    *,
    start: date,
    start_amount: Decimal,
    krw: Decimal,
    usd: Decimal,
    positions: dict[str, tuple[int, Decimal, Decimal]],
) -> None:
    """Put the paper ledger in a given state (qty, cost_native, cost_krw per instrument).

    Used for mid-history scenarios (8/21, 10/07); the rebuild invariant is tested on ledgers that
    the engine built from the start.
    """
    at = datetime.combine(start, time(8, 30), KST)
    with transaction(conn):
        state = LedgerState(
            cash={Currency.KRW: krw, Currency.USD: usd},
            positions={
                iid: Position(
                    iid, Currency.KRW if iid.startswith("KR:") else Currency.USD, q, cn, ck
                )
                for iid, (q, cn, ck) in positions.items()
            },
            contributions_krw=start_amount,
        )
        repo.save_state(conn, "paper", state, at)
        repo.insert_event(
            conn,
            ledger_id="paper",
            kind="start",
            event_date=start,
            occurred_at=at,
            amount=start_amount,
            currency=Currency.KRW,
            status="done",
        )
        repo.mark_ledger_started(conn, "paper", start, start_amount, at)
        # A completed check before the scenario, so leftover cash counts as sub-share cash.
        run_id = repo.insert_run(conn, "paper", "check", start, at)
        repo.finish_run(
            conn, run_id, ended_at=at, duration_ms=1, result="in-range", error=None, details={}
        )
