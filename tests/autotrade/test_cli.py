"""python -m autotrade.jobs: commands, output and exit codes (fake sources, temp database)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from autotrade.jobs.cli import build_parser, main

from .fakes import KR, US, World
from .helpers import kst


def run(argv: list[str], world: World, db: Path) -> tuple[int, dict[str, Any]]:
    lines: list[str] = []
    env = {"AUTOTRADE_PAPER_START_DATE": "2026-07-01"}
    code = main([*argv, "--db", str(db)], sources=world.sources(), env=env, out=lines.append)
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
