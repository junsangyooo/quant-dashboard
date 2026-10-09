"""Helpers for the phase-2 tests: a started paper ledger shared 80/20 with '3년 발굴'."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import date
from decimal import Decimal

from autotrade.db import ai_repo, repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Market
from autotrade.jobs.tasks import JobContext, check_job
from autotrade.rules.discovery import RULE_ID

from .fakes import KR, US, World
from .helpers import kst

BENCH = {Market.KR: "069500.KS", Market.US: "SPY"}


def start_paper(ctx: JobContext, world: World) -> None:
    """The first day (7/1): the paper ledger starts and the rule's sleeve gets its 20%."""
    world.bar(KR, "2026-06-30", close="32000", open_="31900")
    world.bar(US, "2026-06-30", close="66.00", open_="65.80")
    world.rate(kst("2026-07-01 08:25"), "1392.0")
    world.rate(kst("2026-07-01 09:10"), "1392.0")
    world.bar(KR, "2026-07-01", close="32050", open_="32000")
    world.bar(US, "2026-07-01", close="66.20", open_="66.00")
    assert check_job(ctx, "paper", kst("2026-07-01 08:30"))["result"] == "rebalance"


def flat_world(
    conn: sqlite3.Connection,
    world: World,
    end: str,
    start: str = "2026-07-01",
    overrides: dict[str, Callable[[int, date], Decimal | str]] | None = None,
) -> None:
    """Adjusted closes at 100 for every pick of the rule and both indexes, unless overridden."""
    overrides = overrides or {}
    symbols = {BENCH[Market.KR]: Market.KR, BENCH[Market.US]: Market.US}
    for pick in ai_repo.picks_of(conn, "paper", RULE_ID):
        inst = repo.get_instrument(conn, pick.instrument_id)
        symbols[inst.yahoo_symbol] = inst.market
    for symbol, market in symbols.items():
        world.series(symbol, market, start, end, overrides.get(symbol, "100"))


def pick_of(conn: sqlite3.Connection, instrument_id: str) -> ai_repo.PickRow:
    pick = ai_repo.open_pick(conn, "paper", RULE_ID, instrument_id)
    assert pick is not None
    return pick


def put_metric(
    conn: sqlite3.Connection,
    instrument_id: str,
    metric: str,
    period: str,
    value: str,
    unit: str,
    at: str = "2026-10-12 08:00",
) -> None:
    with transaction(conn):
        ai_repo.upsert_metric_value(
            conn,
            instrument_id=instrument_id,
            metric=metric,
            period=period,
            value=Decimal(value),
            unit=unit,
            filing_id=None,
            quote=None,
            source="test",
            call_id=None,
            at=kst(at),
        )
