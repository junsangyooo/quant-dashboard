"""python -m autotrade.jobs tick: what runs when, and how late (autotrade/jobs/schedule.py)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from autotrade.config import Config
from autotrade.db import repo
from autotrade.db.connection import connect, transaction
from autotrade.engine.bootstrap import bootstrap, start_date_key
from autotrade.jobs import cli
from autotrade.jobs import tick as tick_module
from autotrade.jobs.backup import backup_path
from autotrade.jobs.lock import job_lock, lock_path
from autotrade.jobs.schedule import (
    backup_due,
    check_due,
    dividends_due,
    retry_due,
    snapshot_due,
    snapshot_window,
)
from autotrade.market.service import MarketSources
from autotrade.timeutil import KST

from .fakes import KR, US, World
from .helpers import kst
from .test_engine_first_day import first_day_world

ENV = {"AUTOTRADE_PAPER_START_DATE": "2026-07-01"}


def tick(
    world: World, db: Path, when: str, ledger: str = "paper"
) -> tuple[int, list[dict[str, Any]]]:
    lines: list[str] = []
    code = cli.main(
        ["tick", "--at", when, "--db", str(db), "--ledger", ledger],
        sources=world.sources(),
        env=ENV,
        out=lines.append,
    )
    return code, [json.loads(line) for line in lines]


def tasks(lines: list[dict[str, Any]]) -> list[tuple[str, str, str]]:
    return [(x["task"], x.get("why", ""), x["result"]) for x in lines]


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "data" / "autotrade.db"


def test_the_first_day_on_time(world: World, db: Path) -> None:
    first_day_world(world)
    assert tick(world, db, "2026-07-01T07:55") == (0, [])
    assert tick(world, db, "2026-07-01T08:00") == (0, [])  # dividends wait for the start
    code, lines = tick(world, db, "2026-07-01T08:30")
    assert (code, tasks(lines)) == (0, [("check", "on-time", "rebalance")])
    line = lines[0]
    assert line["at"] == "2026-07-01T08:30:00+09:00"
    assert (line["ledger"], line["plan_id"]) == ("paper", 1)
    assert "details" not in line  # the log keeps a summary; the run row keeps the rest
    _, lines = tick(world, db, "2026-07-01T08:35")
    assert tasks(lines) == [("dividends", "late", "nothing-due")]
    assert tick(world, db, "2026-07-01T08:40") == (0, [])
    _, lines = tick(world, db, "2026-07-01T09:05")
    assert tasks(lines) == [("stages", "1 due", "done")]
    assert lines[0]["stages"] == [{"plan_id": 1, "kind": "buy", "market": "KR", "status": "done"}]
    _, lines = tick(world, db, "2026-07-01T09:10")
    assert tasks(lines) == [("stages", "1 due", "done")]
    assert tick(world, db, "2026-07-01T09:30") == (0, [])  # the check went through: no retry
    _, lines = tick(world, db, "2026-07-01T16:00")
    assert tasks(lines) == [("snapshot", "on-time", "ok"), ("backup", "after-snapshot", "ok")]
    assert lines[0]["total_krw"] == "10005258"  # §4
    assert backup_path(db.parent / "backup" / "autotrade", date(2026, 7, 1)).exists()
    assert tick(world, db, "2026-07-01T16:05") == (0, [])
    _, lines = tick(world, db, "2026-07-01T22:30")  # US daylight time: the NYSE opens at 22:30
    assert tasks(lines) == [("stages", "1 due", "done")]
    assert tick(world, db, "2026-07-01T22:35") == (0, [])


def test_server_back_at_0847_runs_the_check_late(world: World, db: Path) -> None:
    first_day_world(world)
    _, lines = tick(world, db, "2026-07-01T08:47")
    assert tasks(lines) == [("check", "late", "rebalance")]
    conn = connect(db)
    try:
        [run] = repo.runs_on(conn, "paper", "check", date(2026, 7, 1))
        assert run.started_at.astimezone(KST) == kst("2026-07-01 08:47")
        [kr_stage, *_] = sorted(repo.pending_stages(conn, "paper"), key=lambda s: s.due_at)
        assert kr_stage.due_at.astimezone(KST) == kst("2026-07-01 09:05")  # plans as usual
    finally:
        conn.close()
    assert tasks(tick(world, db, "2026-07-01T08:50")[1]) == [("dividends", "late", "nothing-due")]


def test_a_missed_morning_runs_the_check_once_as_the_retry(world: World, db: Path) -> None:
    first_day_world(world)
    world.rate(kst("2026-07-01 10:15"), "1391.8")
    _, lines = tick(world, db, "2026-07-01T10:15")
    assert tasks(lines) == [("retry", "missed-check", "rebalance")]
    # The KR buy and the conversion moved to the next slot after the check (10:15 + 5 min).
    _, lines = tick(world, db, "2026-07-01T10:20")
    assert tasks(lines) == [("dividends", "late", "nothing-due"), ("stages", "2 due", "done")]
    assert tick(world, db, "2026-07-01T10:25") == (0, [])


def test_after_1530_the_day_has_no_check(world: World, db: Path) -> None:
    first_day_world(world)
    _, lines = tick(world, db, "2026-07-01T15:35")
    assert [x["task"] for x in lines] == []  # not started, so no snapshot either
    conn = connect(db)
    try:
        assert repo.runs_on(conn, "paper", "check", date(2026, 7, 1)) == []
    finally:
        conn.close()


def test_a_failed_check_is_retried_at_0930_once(world: World, db: Path) -> None:
    world.fail_bars.update({KR, US})
    world.fail_fx = True
    code, lines = tick(world, db, "2026-07-01T08:30")
    assert (code, tasks(lines)) == (1, [("check", "on-time", "failed")])
    _, lines = tick(world, db, "2026-07-01T09:00")  # the failed check still started the ledger
    assert tasks(lines) == [("dividends", "late", "nothing-due")]
    code, lines = tick(world, db, "2026-07-01T09:30")
    assert (code, tasks(lines)) == (1, [("retry", "retry", "todo")])  # '직접 할 일'
    assert tick(world, db, "2026-07-01T09:35") == (0, [])  # the final attempt ran once
    assert tick(world, db, "2026-07-01T11:00") == (0, [])


def test_retry_after_a_late_failed_check(world: World, db: Path) -> None:
    world.fail_bars.update({KR, US})
    world.fail_fx = True
    tick(world, db, "2026-07-01T09:25")  # failed; its retry is 09:30
    world.fail_bars.clear()
    world.fail_fx = False
    first_day_world(world)
    _, lines = tick(world, db, "2026-07-01T09:40")  # the 09:30 tick was missed
    assert [x for x in tasks(lines) if x[0] == "retry"] == [("retry", "retry", "rebalance")]


def test_snapshot_windows_follow_the_calendars(cfg: Config) -> None:
    # US daylight time: the NYSE opens 22:30 KST, so a late snapshot may run until then.
    assert snapshot_window(cfg, date(2026, 10, 7)) == (
        kst("2026-10-07 16:00"),
        kst("2026-10-07 22:30"),
    )
    # Winter time: 23:30.
    assert snapshot_window(cfg, date(2026, 11, 10))[1] == kst("2026-11-10 23:30")
    # Thanksgiving: no US session that evening, so until midnight.
    assert snapshot_window(cfg, date(2026, 11, 26))[1] == kst("2026-11-27 00:00")
    # 수능: KRX closes 16:30, so the day's close is there at 16:50.
    assert snapshot_window(cfg, date(2026, 11, 19))[0] == kst("2026-11-19 16:50")
    # 한글날 (KRX closed): 16:00 as usual.
    assert snapshot_window(cfg, date(2026, 10, 9))[0] == kst("2026-10-09 16:00")


def started(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        repo.insert_event(
            conn,
            ledger_id="paper",
            kind="start",
            event_date=date(2026, 7, 1),
            occurred_at=kst("2026-07-01 08:30"),
            amount=None,
        )


def test_snapshot_due_and_its_retry(conn: sqlite3.Connection, cfg: Config) -> None:
    started(conn)
    assert snapshot_due(conn, cfg, "paper", kst("2026-10-07 15:59")) is None
    due = snapshot_due(conn, cfg, "paper", kst("2026-10-07 16:00"))
    assert due is not None
    assert due.why == "on-time"
    late = snapshot_due(conn, cfg, "paper", kst("2026-10-07 22:25"))
    assert late is not None
    assert late.why == "late"
    assert snapshot_due(conn, cfg, "paper", kst("2026-10-07 22:30")) is None  # the NYSE opened
    assert snapshot_due(conn, cfg, "paper", kst("2026-10-10 16:00")) is None  # Saturday
    assert snapshot_due(conn, cfg, "paper", kst("2026-11-19 16:30")) is None  # 수능
    assert snapshot_due(conn, cfg, "paper", kst("2026-11-19 16:50")) is not None
    with transaction(conn):
        run_id = repo.insert_run(
            conn, "paper", "snapshot", date(2026, 10, 7), kst("2026-10-07 16:00")
        )
        repo.finish_run(
            conn,
            run_id,
            ended_at=kst("2026-10-07 16:00"),
            duration_ms=1,
            result="failed",
            error="no KRW/USD rate stored",
            details={},
        )
    assert snapshot_due(conn, cfg, "paper", kst("2026-10-07 16:05")) is None  # waits 30 min
    retry = snapshot_due(conn, cfg, "paper", kst("2026-10-07 16:30"))
    assert retry is not None
    assert retry.why == "retry"
    # While the snapshot may still come, the backup waits; once its window closed, it goes.
    backups = cfg.db_path.parent / "b"
    assert backup_due(conn, cfg, ["paper"], backups, kst("2026-10-07 16:30")) is None
    after = backup_due(conn, cfg, ["paper"], backups, kst("2026-10-07 22:30"))
    assert after is not None
    assert after.why == "after-snapshot"
    weekend = backup_due(conn, cfg, ["paper"], backups, kst("2026-10-10 16:00"))
    assert weekend is not None
    assert weekend.why == "daily"
    assert backup_due(conn, cfg, ["paper"], backups, kst("2026-10-10 15:59")) is None


def test_a_failed_snapshot_is_retried_after_30_minutes(world: World, db: Path) -> None:
    first_day_world(world)
    world.rates.clear()
    world.rate(kst("2026-07-01 08:25"), "1392.0")
    world.rate(kst("2026-07-01 09:10"), "1392.0")
    for t in ("08:30", "08:35", "09:05", "09:10"):
        tick(world, db, f"2026-07-01T{t}")
    conn = connect(db)
    try:  # no rate stored at all for 16:00 -> the valuation has none to use
        conn.execute("DELETE FROM fx_rates")
    finally:
        conn.close()
    world.rates.clear()
    world.fail_fx = True
    code, lines = tick(world, db, "2026-07-01T16:00")
    assert (code, tasks(lines)) == (1, [("snapshot", "on-time", "failed")])
    assert tick(world, db, "2026-07-01T16:05") == (0, [])  # neither snapshot nor backup
    world.fail_fx = False
    world.rate(kst("2026-07-01 16:00"), "1391.5")
    _, lines = tick(world, db, "2026-07-01T16:30")
    assert tasks(lines) == [("snapshot", "retry", "ok"), ("backup", "after-snapshot", "ok")]


def test_dividends_once_a_day_and_after_a_failure_an_hour_later(world: World, db: Path) -> None:
    first_day_world(world)
    tick(world, db, "2026-07-01T08:30")
    world.fail_dividends = True
    _, lines = tick(world, db, "2026-07-01T08:35")
    assert tasks(lines) == [("dividends", "late", "failed")]
    assert tick(world, db, "2026-07-01T08:40") == (0, [])
    world.fail_dividends = False
    for t in ("09:05", "09:10"):
        tick(world, db, f"2026-07-01T{t}")
    assert tick(world, db, "2026-07-01T09:30") == (0, [])  # 55 minutes later
    _, lines = tick(world, db, "2026-07-01T09:40")
    assert tasks(lines) == [("dividends", "retry", "nothing-due")]
    assert tick(world, db, "2026-07-01T10:40") == (0, [])  # done for the day
    tick(world, db, "2026-07-01T22:30")
    _, lines = tick(world, db, "2026-07-02T08:00")
    assert tasks(lines) == [("dividends", "on-time", "nothing-due")]


def test_dividends_due_rules(conn: sqlite3.Connection) -> None:
    assert dividends_due(conn, "paper", kst("2026-07-01 08:30")) is None  # not started
    started(conn)
    assert dividends_due(conn, "paper", kst("2026-07-01 07:59")) is None
    assert dividends_due(conn, "paper", kst("2026-07-04 09:00")) is None  # Saturday
    due = dividends_due(conn, "paper", kst("2026-07-01 08:00"))
    assert due is not None
    assert due.why == "on-time"


def test_a_stage_waiting_on_a_rescheduled_one_is_not_due(world: World, db: Path) -> None:
    first_day_world(world)
    world.remove_bar(KR, "2026-07-01")  # today's open never comes
    tick(world, db, "2026-07-01T08:30")
    tick(world, db, "2026-07-01T08:35")
    world.fail_bars.add(KR)
    _, lines = tick(world, db, "2026-07-01T09:05")
    assert tasks(lines) == [("stages", "1 due", "failed")]  # the KR buy moves to 7/2 09:05
    # The conversion does not wait on the KR buy, so it still runs; then nothing is due.
    _, lines = tick(world, db, "2026-07-01T09:10")
    assert tasks(lines) == [("stages", "1 due", "done")]
    assert tick(world, db, "2026-07-01T09:15") == (0, [])
    assert tick(world, db, "2026-07-01T12:00") == (0, [])


def test_before_the_start_date_nothing_runs(world: World, db: Path) -> None:
    first_day_world(world)
    conn = connect(db)
    try:
        bootstrap(conn, Config(db_path=db), kst("2026-06-30 12:00"))
        with transaction(conn):
            repo.set_setting(conn, start_date_key("paper"), "2026-07-06", kst("2026-06-30 12:00"))
    finally:
        conn.close()
    for t in ("08:30", "09:30", "16:00"):
        _, lines = tick(world, db, f"2026-07-01T{t}")
        assert [x["task"] for x in lines] in ([], ["backup"])
    conn = connect(db)
    try:
        assert retry_due(conn, Config(db_path=db), "paper", kst("2026-07-01 10:00")) is None
        assert check_due(conn, Config(db_path=db), "paper", kst("2026-07-01 08:30")) is None
    finally:
        conn.close()


def test_weekends_only_back_up(world: World, db: Path) -> None:
    first_day_world(world)
    assert tick(world, db, "2026-07-04T08:30") == (0, [])
    _, lines = tick(world, db, "2026-07-04T16:00")
    assert tasks(lines) == [("backup", "daily", "ok")]
    assert tick(world, db, "2026-07-04T16:05") == (0, [])


def test_a_busy_lock_skips_the_tick(world: World, db: Path) -> None:
    with job_lock(lock_path(db)) as held:
        assert held
        code, lines = tick(world, db, "2026-07-01T08:30")
    assert code == 0
    assert [(x["job"], x["result"]) for x in lines] == [("tick", "busy")]


def test_a_manual_command_waits_for_the_lock_then_gives_up(
    world: World, db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "LOCK_WAIT_S", 0.3)
    out: list[str] = []
    with job_lock(lock_path(db)):
        code = cli.main(
            ["check", "--at", "2026-07-01T08:30", "--db", str(db)],
            sources=world.sources(),
            env=ENV,
            out=out.append,
        )
    assert code == cli.EXIT_BUSY
    assert json.loads(out[0])["result"] == "busy"
    # Read-only commands do not take the lock.
    with job_lock(lock_path(db)):
        out.clear()
        assert (
            cli.main(["todos", "--db", str(db)], sources=world.sources(), env=ENV, out=out.append)
            == 0
        )


def test_a_broken_task_is_logged_and_the_tick_goes_on(
    world: World, db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_day_world(world)

    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("disk full")

    monkeypatch.setattr(tick_module, "check_job", boom)
    code, lines = tick(world, db, "2026-07-04T16:00")  # Saturday: backup only
    assert code == 0
    code, lines = tick(world, db, "2026-07-01T08:30")
    assert code == 1
    assert lines == [
        {
            "at": "2026-07-01T08:30:00+09:00",
            "task": "check",
            "ledger": "paper",
            "why": "on-time",
            "result": "failed",
            "error": "RuntimeError: disk full",
        }
    ]


def test_a_ledger_without_an_executor_cannot_tick(
    world: World, db: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, lines = tick(world, db, "2026-07-01T08:30", ledger="live")
    assert (code, lines) == (2, [])
    assert "ledger-blocked" in capsys.readouterr().err


def test_the_crontab_block(tmp_path: Path) -> None:
    text = (Path(__file__).resolve().parents[2] / "deploy" / "autotrade.cron").read_text()
    [line] = [x for x in text.splitlines() if x and not x.startswith("#")]
    assert line.startswith("*/5 * * * * cd /home/ubuntu/portfolio-dashboard && flock -n ")
    assert ".venv/bin/python -m autotrade.jobs tick" in line
    assert line.endswith(">> data/logs/autotrade-jobs.log 2>&1")
    assert "%" not in line  # cron would cut the line at an unescaped %
    assert "UTC" in text


def test_without_a_dividend_source_the_tick_skips_dividends(world: World, db: Path) -> None:
    first_day_world(world)
    full = world.sources()
    lines: list[str] = []
    for when in ("2026-07-01T08:30", "2026-07-01T08:35"):
        cli.main(
            ["tick", "--at", when, "--db", str(db)],
            sources=MarketSources(kr=full.kr, us=full.us, fx=full.fx),
            env=ENV,
            out=lines.append,
        )
    assert [json.loads(x)["task"] for x in lines] == ["check"]
