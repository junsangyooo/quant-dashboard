"""Check failure, the 09:30 retry and '직접 할 일' (인계 11); dry runs; crashes."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from autotrade.db import repo
from autotrade.engine import check as engine_check
from autotrade.jobs import tasks
from autotrade.jobs.tasks import JobContext, check_job, snapshot_job, stage_job
from autotrade.timeutil import KST

from .fakes import KR, US, World
from .helpers import kst, seed_ledger

D = Decimal


def seed(conn: sqlite3.Connection, world: World) -> None:
    seed_ledger(
        conn,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("47675"),
        usd=D("1.66"),
        positions={KR: (120, D("3840576"), D("3840576")), US: (46, D("3033.03"), D("4221675"))},
    )
    world.bar(KR, "2026-10-06", close="36360", open_="36300")
    world.rate(kst("2026-10-07 08:25"), "1380.6")


def test_failed_check_is_retried_at_0930_and_recovers(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed(conn, world)
    world.fail_bars.add(US)  # '시세 응답 없음' and no stored US close to fall back on
    failed = check_job(ctx, "paper", kst("2026-10-07 08:30"))
    assert failed["result"] == "failed"
    assert failed["error"].startswith("no-quote: US")
    event = repo.check_failure_event(conn, "paper", date(2026, 10, 7))
    assert event is not None
    assert event.status == "retry"
    assert event.payload["retry_at"] == "2026-10-07T00:30:00+00:00"  # 09:30 KST
    run = repo.runs_on(conn, "paper", "check", date(2026, 10, 7))[0]
    assert (run.result, run.attempt) == ("failed", 1)
    assert run.duration_ms is not None

    world.fail_bars.clear()
    world.bar(US, "2026-10-06", close="62.40", open_="62.10")
    retried = check_job(ctx, "paper", kst("2026-10-07 09:30"), retry=True)
    assert retried["result"] == "rebalance"
    assert retried["details"]["attempt"] == 2
    event = repo.check_failure_event(conn, "paper", date(2026, 10, 7))
    assert event is not None
    assert event.status == "recovered"
    # A plan made at 09:30 starts five minutes later, not at 09:05.
    stages = repo.stages_of(conn, retried["plan_id"])
    assert stages[0].due_at.astimezone(KST) == kst("2026-10-07 09:35")
    # Nothing left to retry.
    assert check_job(ctx, "paper", kst("2026-10-07 09:31"), retry=True)["result"] == "not-needed"


def test_two_failures_make_a_manual_action(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed(conn, world)
    world.fail_bars.add(US)
    check_job(ctx, "paper", kst("2026-10-07 08:30"))
    again = check_job(ctx, "paper", kst("2026-10-07 09:30"), retry=True)
    assert again["result"] == "todo"  # '두 번 실패하면 직접 할 일'
    event = repo.check_failure_event(conn, "paper", date(2026, 10, 7))
    assert event is not None
    assert event.status == "todo"
    assert event.payload["attempts"] == 2
    assert repo.orders_of_ledger(conn, "paper") == []
    status = tasks.status_job(ctx, "paper", kst("2026-10-07 10:00"))
    assert any("check_failed" in t for t in status["todo"])


def test_retry_runs_the_check_when_0830_never_ran(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed(conn, world)
    world.bar(US, "2026-10-06", close="62.40", open_="62.10")
    report = check_job(ctx, "paper", kst("2026-10-07 09:30"), retry=True)
    assert report["result"] == "rebalance"


def test_a_failing_rate_download_fails_the_check(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed(conn, world)
    world.bar(US, "2026-10-06", close="62.40")
    world.rates.clear()
    world.fail_fx = True
    report = check_job(ctx, "paper", kst("2026-10-07 08:30"))
    assert report["result"] == "failed"
    assert "FX" in report["error"]
    fresh = repo.get_freshness(conn, "fx")
    assert fresh is not None
    assert fresh.error is not None


def test_dry_run_leaves_no_trace(ctx: JobContext, conn: sqlite3.Connection, world: World) -> None:
    seed(conn, world)
    world.bar(US, "2026-10-06", close="62.40")
    report = check_job(ctx, "paper", kst("2026-10-07 08:30"), dry_run=True)
    assert report["result"] == "rebalance"
    assert report["dry_run"] is True
    assert repo.orders_of_ledger(conn, "paper") == []
    assert repo.runs_on(conn, "paper", "check", date(2026, 10, 7)) == []
    # The downloaded prices stay cached; they are not ledger state.
    assert repo.get_bar(conn, US, date(2026, 10, 6)) is not None
    # A real run afterwards, then a dry stage run that executes nothing for good.
    check_job(ctx, "paper", kst("2026-10-07 08:30"))
    world.bar(KR, "2026-10-07", close="36250", open_="36380")
    dry_stage = stage_job(ctx, "paper", kst("2026-10-07 09:05"), dry_run=True)
    assert dry_stage["result"] == "done"
    assert repo.fills_of_ledger(conn, "paper") == []
    dry_snap = snapshot_job(ctx, "paper", kst("2026-10-07 16:00"), dry_run=True)
    assert dry_snap["result"] == "ok"
    assert repo.get_snapshot(conn, "paper", date(2026, 10, 7)) is None


def test_an_unexpected_error_is_recorded(
    ctx: JobContext, conn: sqlite3.Connection, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(conn, world)
    world.bar(US, "2026-10-06", close="62.40")

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("disk full")

    original = engine_check.run_check
    monkeypatch.setattr(tasks, "run_check", boom)
    report = check_job(ctx, "paper", kst("2026-10-07 08:30"))
    assert report["result"] == "failed"
    assert report["error"] == "RuntimeError: disk full"
    [run] = repo.runs_on(conn, "paper", "check", date(2026, 10, 7))
    assert (run.result, run.error, run.details) == (
        "failed",
        "RuntimeError: disk full",
        {"crash": True},
    )
    with pytest.raises(RuntimeError):
        check_job(ctx, "paper", kst("2026-10-07 08:30"), dry_run=True)

    # run_check works again (monkeypatch.undo() would also lift the network block); now the
    # stage runner breaks.
    monkeypatch.setattr(tasks, "run_check", original)
    check_job(ctx, "paper", kst("2026-10-07 08:31"))
    monkeypatch.setattr(tasks, "run_due_stages", boom)
    report = stage_job(ctx, "paper", kst("2026-10-07 09:05"))
    assert report["result"] == "failed"
    with pytest.raises(RuntimeError):
        stage_job(ctx, "paper", kst("2026-10-07 09:05"), dry_run=True)


def test_snapshot_without_a_rate_fails_and_is_recorded(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed(conn, world)
    world.rates.clear()
    report = snapshot_job(ctx, "paper", kst("2026-10-07 16:00"))
    assert report["result"] == "failed"
    assert report["error"] == "no KRW/USD rate stored"
    [run] = repo.runs_on(conn, "paper", "snapshot", date(2026, 10, 7))
    assert run.result == "failed"


def test_snapshot_marks_stale_series(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed(conn, world)
    world.bar(US, "2026-10-02", close="62.10")
    world.rate(kst("2026-10-07 16:00"), "1382.4")
    report = snapshot_job(ctx, "paper", kst("2026-10-07 16:10"))
    assert report["result"] == "ok"
    assert set(report["stale"]) == {"kr-quotes", "us-quotes"}
    assert str(report["us_close_date"]) == "2026-10-02"  # '미국 시세 10/02 기준'


def test_an_unexpected_snapshot_error_is_recorded(
    ctx: JobContext, conn: sqlite3.Connection, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed(conn, world)

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("bad row")

    monkeypatch.setattr(tasks, "take_snapshot", boom)
    report = snapshot_job(ctx, "paper", kst("2026-10-07 16:00"))
    assert (report["result"], report["error"]) == ("failed", "RuntimeError: bad row")
    [run] = repo.runs_on(conn, "paper", "snapshot", date(2026, 10, 7))
    assert run.details == {"crash": True}
    with pytest.raises(RuntimeError):
        snapshot_job(ctx, "paper", kst("2026-10-07 16:00"), dry_run=True)
