"""python -m autotrade.jobs: commands, output and exit codes (fake sources, temp database)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autotrade.jobs.cli import build_parser, main

from .fakes import KR, US, World
from .helpers import PHASE1_ENV, kst

ENV = {"AUTOTRADE_PAPER_START_DATE": "2026-07-01", **PHASE1_ENV}


def run(argv: list[str], world: World, db: Path) -> tuple[int, dict[str, Any]]:
    """The command on `db`, migrated first when it is new (only `migrate` makes a schema)."""
    lines: list[str] = []
    if not db.exists():
        assert main(["migrate", "--db", str(db)], env=ENV, out=lines.append) == 0
        lines.clear()
    code = main([*argv, "--db", str(db)], sources=world.sources(), env=ENV, out=lines.append)
    return code, json.loads(lines[0]) if lines else {}


def first_day(world: World) -> None:
    world.bar(KR, "2026-06-30", close="32000")
    world.bar(US, "2026-06-30", close="66.00")
    world.rate(kst("2026-07-01 08:25"), "1392.0")
    world.rate(kst("2026-07-01 09:10"), "1392.0")
    world.bar(KR, "2026-07-01", close="32050", open_="32000")


def test_check_stage_status(tmp_path: Path, world: World) -> None:
    first_day(world)
    db = tmp_path / "data" / "autotrade.db"
    code, out = run(["check", "--ledger", "paper", "--at", "2026-07-01T08:30"], world, db)
    assert code == 0
    assert out["result"] == "rebalance"
    assert out["at"] == "2026-07-01T08:30:00+09:00"  # times are printed in KST
    code, out = run(["stage", "--at", "2026-07-01T09:10"], world, db)
    assert (code, out["result"]) == (0, "done")
    code, out = run(["status", "--at", "2026-07-01T09:30"], world, db)
    assert code == 0
    assert out["rule_status"] == "in-progress"
    assert out["mode"] == "paper"
    assert out["ledger_check"] == []
    assert out["open_plans"][0]["stages"][2]["due_at"] == "2026-07-01T22:30:00+09:00"
    code, out = run(["retry", "--at", "2026-07-01T09:30"], world, db)
    assert (code, out["result"]) == (0, "not-needed")
    world.rate(kst("2026-07-01 16:00"), "1391.5")
    code, out = run(["snapshot", "--at", "2026-07-01T16:00"], world, db)
    assert (code, out["result"], out["total_krw"]) == (0, "ok", "10005258")  # §4


def test_dry_run_flag(tmp_path: Path, world: World) -> None:
    first_day(world)
    db = tmp_path / "autotrade.db"
    code, out = run(["check", "--dry-run", "--at", "2026-07-01T08:30"], world, db)
    assert (code, out["result"], out["dry_run"]) == (0, "rebalance", True)
    code, out = run(["status", "--at", "2026-07-01T08:31"], world, db)
    assert out["open_plans"] == []


def test_failure_exit_code(tmp_path: Path, world: World) -> None:
    world.fail_bars.update({KR, US})
    world.fail_fx = True
    code, out = run(["check", "--at", "2026-07-01T08:30"], world, tmp_path / "a.db")
    assert code == 1
    assert out["result"] == "failed"


def test_live_ledger_is_refused(
    tmp_path: Path, world: World, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = run(
        ["check", "--ledger", "live", "--at", "2026-07-01T08:30"], world, tmp_path / "b.db"
    )
    assert code == 2
    assert out == {}
    assert "ledger-blocked" in capsys.readouterr().err


def test_clock_defaults_to_now(tmp_path: Path, world: World) -> None:
    lines: list[str] = []
    assert main(["migrate", "--db", str(tmp_path / "c.db")], env={}, out=lines.append) == 0
    lines.clear()
    code = main(
        ["check", "--db", str(tmp_path / "c.db")],
        sources=world.sources(),
        env={},
        now=lambda: kst("2026-07-04 08:30"),  # a Saturday
        out=lines.append,
    )
    assert code == 0
    assert json.loads(lines[0])["result"] == "weekend"


def test_parser_rejects_unknown_commands() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["trade"])


def test_ops_commands(tmp_path: Path, world: World) -> None:
    first_day(world)
    db = tmp_path / "data" / "autotrade.db"
    run(["check", "--at", "2026-07-01T08:30"], world, db)
    code, out = run(["dividends", "--at", "2026-07-01T08:35"], world, db)
    assert (code, out["job"], out["result"]) == (0, "dividends", "nothing-due")
    code, out = run(["backup", "--at", "2026-07-01T16:00"], world, db)
    assert (code, out["result"]) == (0, "ok")
    assert out["path"].endswith("data/backup/autotrade/autotrade-2026-07-01.db")
    code, out = run(["todos", "--at", "2026-07-01T16:01"], world, db)
    assert (code, out["todos"]) == (0, [])
    code, out = run(["resolve", "--at", "2026-07-01T16:02"], world, db)
    assert (code, out["result"]) == (1, "bad-id")
    code, out = run(
        ["resolve", "order-failed:1", "--note", "x", "--at", "2026-07-01T16:03"], world, db
    )
    assert (code, out["result"]) == (1, "not-a-todo")
    # The morning's stages never ran: the next tick catches them up (filled at 7/1's open).
    code, out = run(["tick", "--at", "2026-07-01T16:05"], world, db)
    assert (code, out["task"], out["why"], out["result"]) == (0, "stages", "2 due", "done")


def test_only_resolve_takes_an_argument(tmp_path: Path, world: World) -> None:
    with pytest.raises(SystemExit):
        run(["check", "extra", "--at", "2026-07-01T08:30"], world, tmp_path / "x.db")
