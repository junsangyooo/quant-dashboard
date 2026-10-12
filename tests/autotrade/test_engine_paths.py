"""Less common engine paths: US over target, a sell retried the next day, baseline carry-over,
deposits in the baseline, and the snapshot/check/rebuild error paths."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from decimal import Decimal

import pytest

from autotrade.db import repo
from autotrade.db.connection import transaction
from autotrade.db.models import EventRow, FillRow
from autotrade.domain.instruments import Currency
from autotrade.domain.ledger import CashFlowKind, LedgerState, apply_cash_flow
from autotrade.engine import rebuild
from autotrade.engine.check import CheckFailedError, run_check
from autotrade.engine.rebuild import verify_ledger
from autotrade.jobs.tasks import JobContext, check_job, snapshot_job, stage_job
from autotrade.market.service import FetchErrors
from autotrade.timeutil import KST, UTC

from .fakes import KR, US, World
from .helpers import kst, seed_ledger

D = Decimal


def test_us_over_target_sells_us_converts_and_buys_korea(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_ledger(
        conn,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("0"),
        usd=D("0"),
        positions={KR: (100, D("3000000"), D("3000000")), US: (40, D("2640"), D("3670000"))},
    )
    world.bar(KR, "2026-10-06", close="30000")
    world.bar(US, "2026-10-06", close="66.00")
    world.rate(kst("2026-10-07 08:25"), "1390.0")
    report = check_job(ctx, "paper", kst("2026-10-07 08:30"))
    assert report["result"] == "rebalance"
    stages = repo.stages_of(conn, report["plan_id"])
    assert [(s.kind, s.market, s.due_at.astimezone(KST)) for s in stages] == [
        ("sell", "US", kst("2026-10-07 22:30")),
        ("fx", "FX", kst("2026-10-08 09:10")),
        ("buy", "KR", kst("2026-10-08 09:15")),
    ]
    world.bar(US, "2026-10-07", close="66.10", open_="66.00")
    world.rate(kst("2026-10-07 22:30"), "1391.0")
    assert stage_job(ctx, "paper", kst("2026-10-07 22:30"))["result"] == "done"
    sell = repo.fills_of_ledger(conn, "paper")[0]
    assert (sell.qty, sell.gross, sell.fee) == (3, D("198.00"), D("0.20"))
    assert sell.krw_rate == D("1391.0")  # no conversion in the plan yet: the rate at the fill
    world.rate(kst("2026-10-08 09:10"), "1390.0")
    world.bar(KR, "2026-10-08", close="30100", open_="30000")
    assert stage_job(ctx, "paper", kst("2026-10-08 09:15"))["result"] == "done"
    _, fx, buy = repo.fills_of_ledger(conn, "paper")
    assert (fx.fx_direction, fx.gross, fx.received) == ("usd_to_krw", D("194.97"), D("271008"))
    assert (buy.instrument_id, buy.qty, buy.filled_at.astimezone(KST)) == (
        KR,
        9,
        kst("2026-10-08 09:15"),
    )
    assert repo.get_plan(conn, report["plan_id"]).status == "done"


def test_a_sell_retried_next_day_moves_the_stages_after_it(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_ledger(
        conn,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("47675"),
        usd=D("1.66"),
        positions={KR: (120, D("3840576"), D("3840576")), US: (46, D("3033.03"), D("4221675"))},
    )
    world.bar(KR, "2026-10-06", close="36360")
    world.bar(US, "2026-10-06", close="62.40")
    world.rate(kst("2026-10-07 08:25"), "1380.6")
    plan_id = check_job(ctx, "paper", kst("2026-10-07 08:30"))["plan_id"]
    world.fail_bars.add(KR)
    assert stage_job(ctx, "paper", kst("2026-10-07 09:05"))["result"] == "failed"
    assert repo.get_plan(conn, plan_id).status == "partial-failed"

    world.fail_bars.clear()
    world.bar(KR, "2026-10-08", close="36500", open_="36400")
    world.rate(kst("2026-10-08 09:10"), "1381.0")
    assert stage_job(ctx, "paper", kst("2026-10-08 09:05"))["result"] == "done"
    # The plan is back in progress, and the conversion and the US buy moved a day.
    assert repo.get_plan(conn, plan_id).status == "in-progress"
    stages = {s.kind: s for s in repo.stages_of(conn, plan_id)}
    assert stages["fx"].due_at.astimezone(KST) == kst("2026-10-08 09:10")
    assert stages["buy"].due_at.astimezone(KST) == kst("2026-10-08 22:30")
    assert stage_job(ctx, "paper", kst("2026-10-08 09:10"))["result"] == "done"
    sell, fx = repo.fills_of_ledger(conn, "paper")
    assert (sell.price, sell.filled_at.astimezone(KST)) == (D("36400"), kst("2026-10-08 09:05"))
    assert fx.krw_rate == D("1381.0")


def test_baseline_carries_over_and_follows_deposits(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    world.bar(KR, "2026-06-30", close="32000")
    world.bar(US, "2026-06-30", close="66.00")
    world.rate(kst("2026-07-01 08:25"), "1392.0")
    world.rate(kst("2026-07-01 09:10"), "1392.0")
    world.bar(KR, "2026-07-01", close="32000", open_="32000")
    world.bar(US, "2026-07-01", close="66.00", open_="66.00")
    check_job(ctx, "paper", kst("2026-07-01 08:30"))
    for t in ("09:05", "09:10", "22:30"):
        stage_job(ctx, "paper", kst(f"2026-07-01 {t}"))
    world.bar(KR, "2026-07-02", close="32000")
    world.bar(US, "2026-07-02", close="66.00")
    world.rate(kst("2026-07-02 16:00"), "1392.0")
    first = snapshot_job(ctx, "paper", kst("2026-07-02 16:00"))
    assert first["baseline_krw"] == D("10000000")  # prices unchanged since the start

    # A deposit of 1,000,000 won on 7/6 (phase 4 brings real deposits; recorded directly here).
    at = kst("2026-07-06 12:00")
    with transaction(conn):
        state = apply_cash_flow(repo.load_state(conn, "paper"), CashFlowKind.DEPOSIT, D("1000000"))
        repo.save_state(conn, "paper", state, at)
        repo.insert_event(
            conn,
            ledger_id="paper",
            kind="deposit",
            event_date=date(2026, 7, 6),
            occurred_at=at,
            amount=D("1000000"),
            currency=Currency.KRW,
        )
    world.bar(KR, "2026-07-03", close="32000")
    world.bar(KR, "2026-07-06", close="32000")
    world.rate(kst("2026-07-06 16:00"), "1392.0")
    later = snapshot_job(ctx, "paper", kst("2026-07-06 16:00"))
    assert later["baseline_krw"] == D("11000000")  # deposits are added to the baseline too
    assert later["pnl_krw"] == later["total_krw"] - D("11000000")
    assert verify_ledger(conn, "paper") == []


def test_snapshot_without_start_prices_has_no_baseline(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_ledger(
        conn,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("10000000"),
        usd=D("0"),
        positions={},
    )
    world.bar(KR, "2026-10-07", close="36250")
    world.bar(US, "2026-10-06", close="62.40")
    world.rate(kst("2026-10-07 16:00"), "1382.4")
    report = snapshot_job(ctx, "paper", kst("2026-10-07 16:00"))
    assert report["result"] == "ok"
    assert report["baseline_krw"] is None  # 7/1 opens were never stored
    assert report["total_krw"] == D("10000000")


def test_snapshot_fails_when_a_held_instrument_has_no_close(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_ledger(
        conn,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("0"),
        usd=D("0"),
        positions={US: (40, D("2640"), D("3670000"))},
    )
    world.bar(KR, "2026-10-07", close="36250")
    world.rate(kst("2026-10-07 16:00"), "1382.4")
    report = snapshot_job(ctx, "paper", kst("2026-10-07 16:00"))
    assert report["result"] == "failed"
    assert report["error"] == "no close for held US:SPYM"


def test_check_edge_cases(ctx: JobContext, conn: sqlite3.Connection, world: World) -> None:
    # Saturday: the engine function itself refuses too.
    with transaction(conn):
        assert run_check(conn, ctx.cfg, "paper", kst("2026-07-04 08:30")).result == "weekend"
    # A first check that fails after 09:30 has no retry left: '직접 할 일' at once.
    world.fail_bars.update({KR, US})
    world.fail_fx = True
    late = check_job(ctx, "paper", kst("2026-07-01 09:45"))
    assert late["result"] == "todo"
    # No start amount configured: a configuration error, raised (the job records it as a crash).
    with transaction(conn):  # the live ledger's check waits for the live mode
        assert run_check(conn, ctx.cfg, "live", kst("2026-07-01 10:00")).result == "not-live"
    with transaction(conn):
        repo.set_setting(conn, "mode", "live", kst("2026-07-01 10:00"))
    with pytest.raises(CheckFailedError, match="no start amount"), transaction(conn):
        run_check(conn, ctx.cfg, "live", kst("2026-07-01 10:00"), fetch=FetchErrors())


def test_rebuild_rejects_incomplete_records() -> None:
    stamp = datetime(2026, 7, 1, tzinfo=UTC)
    event = EventRow(
        1, "paper", "deposit", date(2026, 7, 1), stamp, None, None, None, None, None, {}
    )
    with pytest.raises(ValueError, match="no amount"):
        rebuild._apply_event(LedgerState(), event)
    fx = FillRow(
        1,
        1,
        "paper",
        "fx",
        None,
        "fx",
        None,
        Currency.KRW,
        None,
        None,
        D("1"),
        D("0"),
        D("0"),
        None,
        None,
        stamp,
        "s",
        "paper",
    )
    with pytest.raises(ValueError, match="incomplete conversion"):
        rebuild._apply_fill(LedgerState(), fx)
    trade = FillRow(
        2,
        2,
        "paper",
        "trade",
        None,
        "buy",
        None,
        Currency.KRW,
        1,
        D("1"),
        D("1"),
        D("0"),
        D("0"),
        None,
        None,
        stamp,
        "s",
        "paper",
    )
    with pytest.raises(ValueError, match="incomplete trade"):
        rebuild._apply_fill(LedgerState(), trade)


def test_start_cash_stays_new_until_a_check_judges_it(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    # 7/1: no fresh US close yet -> '시세 대기'; the start amount is still '첫 확인 때 매수'.
    world.bar(KR, "2026-06-30", close="32000")
    world.rate(kst("2026-07-01 08:25"), "1392.0")
    assert check_job(ctx, "paper", kst("2026-07-01 08:30"))["result"] == "quote-wait"
    [part] = repo.cash_parts(conn, "paper")
    assert (part.purpose.value, part.amount) == ("new", D("10000000"))
    # 7/2: data is there; the start amount is invested by the start plan.
    world.bar(KR, "2026-07-01", close="32000")
    world.bar(US, "2026-06-30", close="66.00")
    world.bar(US, "2026-07-01", close="66.00")
    world.rate(kst("2026-07-02 08:25"), "1392.0")
    report = check_job(ctx, "paper", kst("2026-07-02 08:30"))
    assert report["result"] == "rebalance"
    assert repo.get_plan(conn, report["plan_id"]).reason == "start"
    assert {p.purpose.value for p in repo.cash_parts(conn, "paper")} == {"buy_wait"}


def test_a_manual_stage_releases_the_stages_after_it(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_ledger(
        conn,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("47675"),
        usd=D("1.66"),
        positions={KR: (120, D("3840576"), D("3840576")), US: (46, D("3033.03"), D("4221675"))},
    )
    world.bar(KR, "2026-10-06", close="36360")
    world.bar(US, "2026-10-06", close="62.40")
    world.rate(kst("2026-10-07 08:25"), "1380.6")
    plan_id = check_job(ctx, "paper", kst("2026-10-07 08:30"))["plan_id"]
    world.fail_bars.add(KR)
    stage_job(ctx, "paper", kst("2026-10-07 09:05"))
    assert stage_job(ctx, "paper", kst("2026-10-08 09:05"))["result"] == "failed"
    stages = repo.stages_of(conn, plan_id)
    assert [(s.kind, s.status) for s in stages] == [
        ("sell", "todo"),
        ("fx", "todo"),
        ("buy", "todo"),
    ]
    assert stages[1].last_error == "waits on stage 1"
    assert repo.pending_orders(conn, "paper") == []
    assert {o.status for o in repo.orders_of_ledger(conn, "paper")} == {"failed", "cancelled"}
    # Nothing is marked as waiting to buy any more.
    assert {p.purpose.value for p in repo.cash_parts(conn, "paper")} == {"sub_share"}
