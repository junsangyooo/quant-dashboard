"""The AI runner when things go wrong (audit 2026-10-10: E1 E2 E3 E10 E11).

Fixed by tests: which CLI is run and with what environment; a missing CLI is a source down (no
attempt, nothing red); any error is recorded on its task and never blocks the next one; network
blinks wait, corrupt downloads give up after three, faults give up at once; the calls are kept
before the code that follows them, and a kept answer is applied again instead of asking again;
the runner's heartbeat.
"""

from __future__ import annotations

import http.client
import os
import sqlite3
import stat
import zlib
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from autotrade.ai import cli as cli_module
from autotrade.ai import flows
from autotrade.ai.cli import ClaudeCli, CliCall, child_env, find_claude
from autotrade.ai.prompts import load
from autotrade.ai.runner import MAX_SOURCE_TRIES, classify, run_ai
from autotrade.db import ai_repo, repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Market
from autotrade.engine.todos import retry_ai
from autotrade.jobs.tasks import JobContext
from autotrade.market.filings import FilingSourceError, SourceUnreachableError

from .ai_fakes import ScriptedRunner, sell
from .fakes import World
from .phase2 import pick_of
from .test_ai import AT, OCEAN, filing, prices, shock_task, task

# ── which CLI, and its environment ──────────────────────────────────────────────────────────


def _exe(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_find_claude_looks_where_cron_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The real nvm pattern, under a home of the test's own (conftest hides the laptop's CLI).
    monkeypatch.setattr(cli_module, "NVM_GLOB", ".nvm/versions/node/*/bin/claude")
    home, nowhere = tmp_path / "home", str(tmp_path / "empty-bin")
    wrapper = tmp_path / "usr-local-bin" / "claude"
    # Nothing anywhere: a source down, with where it looked.
    none = find_claude(None, {"PATH": nowhere}, home=home, system=wrapper)
    assert none.path is None
    assert none.error is not None
    assert "AUTOTRADE_CLAUDE_BIN" not in none.error
    assert str(wrapper) in none.error
    # The newest nvm install by version (v24 after v9, not by letters), its folder first on PATH.
    for version in ("v9.11.2", "v24.14.1", "v20.3.0"):
        _exe(home / ".nvm" / "versions" / "node" / version / "bin" / "claude")
    nvm = find_claude(None, {"PATH": nowhere}, home=home, system=wrapper)
    newest = home / ".nvm" / "versions" / "node" / "v24.14.1" / "bin"
    assert (nvm.path, nvm.path_prefix) == (str(newest / "claude"), str(newest))
    # The server's wrapper beats nvm; PATH beats the wrapper; the setting beats them all.
    _exe(wrapper)
    assert find_claude(None, {"PATH": nowhere}, home=home, system=wrapper).path == str(wrapper)
    on_path = _exe(tmp_path / "bin" / "claude")
    env = {"PATH": str(on_path.parent)}
    assert find_claude(None, env, home=home, system=wrapper).path == str(on_path)
    mine = _exe(tmp_path / "mine" / "claude-dev")
    assert find_claude(str(mine), env, home=home, system=wrapper).path == str(mine)
    # A setting that points nowhere falls through (and says so).
    gone = find_claude(str(tmp_path / "gone"), {"PATH": nowhere}, home=tmp_path, system=wrapper)
    assert gone.path == str(wrapper)
    assert gone.tried[0] == f"AUTOTRADE_CLAUDE_BIN={tmp_path / 'gone'}"


def test_the_cli_child_gets_no_billing_route_and_no_credential(tmp_path: Path) -> None:
    source = {
        "HOME": "/home/ubuntu",
        "PATH": "/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "CLAUDE_CONFIG_DIR": "/home/ubuntu/.claude",
        "ANTHROPIC_API_KEY": "sk-paid",
        "ANTHROPIC_BASE_URL": "https://elsewhere",
        "ANTHROPIC_AUTH_TOKEN": "t",
        "CLAUDE_CODE_USE_BEDROCK": "1",
        "CLAUDE_CODE_USE_VERTEX": "1",
        "CLAUDE_CODE_OAUTH_TOKEN": "o",
        "AWS_SECRET_ACCESS_KEY": "a",
        "AWS_PROFILE": "p",
        "GOOGLE_APPLICATION_CREDENTIALS": "/x.json",
        "AZURE_CLIENT_SECRET": "z",
        "DART_API_KEY": "dart",
        "AUTOTRADE_SECRETS_ENV": "/home/ubuntu/dotclaude/secrets/.env",
        "AUTOTRADE_AI_CALLS": "1",
        "TOSS_CLIENT_SECRET": "toss",
        "KRX_PW": "pw",
        "GITHUB_TOKEN": "gh",
        "DB_PASSWORD": "pw",
        "SSH_AUTH_SOCK": "/tmp/agent",
    }
    assert child_env(source, "/home/ubuntu/.nvm/versions/node/v24.14.1/bin") == {
        "HOME": "/home/ubuntu",
        "PATH": "/home/ubuntu/.nvm/versions/node/v24.14.1/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "CLAUDE_CONFIG_DIR": "/home/ubuntu/.claude",
        "SSH_AUTH_SOCK": "/tmp/agent",
    }
    runner = ScriptedRunner()
    runner.add("sell", sell("유지"))
    cli = ClaudeCli("/x/claude", tmp_path / "cwd", runner=runner, environ=source)
    call = load("sell_confirm")
    cli.run(CliCall("s", "질문\x00", call.system, call.schema, "sonnet"))
    sent = runner.calls[0]
    assert set(sent["env"]) == {"HOME", "PATH", "LANG", "CLAUDE_CONFIG_DIR", "SSH_AUTH_SOCK"}
    assert sent["cmd"][2] == "질문"  # a NUL would make exec fail
    assert (sent["encoding"], sent["errors"]) == ("utf-8", "replace")


# ── a missing CLI is a source down ──────────────────────────────────────────────────────────


def _run(
    ctx: JobContext, cli: ClaudeCli, at: Any = AT, max_tasks: int = 20, **changes: Any
) -> dict[str, Any]:
    cfg = replace(ctx.cfg, ai_calls_enabled=True, **changes)
    return run_ai(ctx.conn, cfg, ctx.sources, cli, lambda: at, max_tasks)


def test_a_missing_cli_spends_no_attempt(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World, tmp_path: Path
) -> None:
    prices(world, "042660.KS", "069500.KS")
    tid = shock_task(p2conn)
    missing = ClaudeCli(None, tmp_path / "cwd", missing="claude CLI not found (tried PATH)")
    report = _run(p2ctx, missing)
    assert (report["result"], report["due"]) == ("cli-missing", 1)
    waiting = ai_repo.get_task(p2conn, tid)
    assert (waiting.status, waiting.attempts) == ("pending", 0)
    beat = ai_repo.runner_state(p2conn)
    assert beat is not None
    assert (beat.enabled, beat.cli, beat.cli_missing_since, beat.result) == (
        True,
        None,
        AT,
        "cli-missing",
    )
    assert beat.cli_error == "claude CLI not found (tried PATH)"
    # Still missing an hour later: since when stays.
    _run(p2ctx, missing, AT + timedelta(hours=1))
    still = ai_repo.runner_state(p2conn)
    assert still is not None
    assert still.cli_missing_since == AT
    # The CLI vanishes during a run (it was found when the run began): no attempt, no call
    # recorded, and the run stops (every task needs the CLI).
    shock_task(p2conn, "sc2")

    def vanished(cmd: list[str], **kw: Any) -> Any:
        raise FileNotFoundError(2, "No such file or directory", cmd[0])

    gone = ClaudeCli("/usr/local/bin/claude", tmp_path / "cwd", runner=vanished)
    report = _run(p2ctx, gone, AT + timedelta(hours=2))
    assert report["result"] == "cli-missing"
    assert [t["status"] for t in report["tasks"]] == ["cli-missing"]  # the second is not taken
    assert [(t.status, t.attempts) for t in ai_repo.tasks_of(p2conn, kind="sell-confirm")] == [
        ("pending", 0),
        ("pending", 0),
    ]
    assert ai_repo.last_calls(p2conn) == []
    beat = ai_repo.runner_state(p2conn)
    assert beat is not None
    assert beat.cli is None
    assert beat.cli_error is not None
    assert "FileNotFoundError" in beat.cli_error
    # Back: the tasks are asked and the 'missing since' is cleared.
    runner = ScriptedRunner()
    runner.add("sell", *[sell("유지")] * 4)
    back = ClaudeCli("/usr/local/bin/claude", tmp_path / "cwd", runner=runner)
    assert _run(p2ctx, back, AT + timedelta(hours=3))["result"] == "ok"
    beat = ai_repo.runner_state(p2conn)
    assert beat is not None
    assert (beat.cli, beat.cli_missing_since) == ("/usr/local/bin/claude", None)


def test_the_heartbeat_says_what_the_runner_is_doing(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World, tmp_path: Path
) -> None:
    prices(world, "042660.KS", "069500.KS")
    tid = shock_task(p2conn)
    off = ClaudeCli("claude", tmp_path / "cwd", runner=ScriptedRunner())
    run_ai(p2conn, p2ctx.cfg, p2ctx.sources, off, lambda: AT)  # the gate is off
    beat = ai_repo.runner_state(p2conn)
    assert beat is not None
    assert (beat.enabled, beat.result, beat.dart_key, beat.ended_at) == (
        False,
        "disabled",
        False,
        AT,
    )
    seen: list[ai_repo.RunnerRow | None] = []

    def watching(cmd: list[str]) -> dict[str, Any]:
        seen.append(ai_repo.runner_state(p2conn))  # what the screens read during the call
        return sell("유지")

    runner = ScriptedRunner()
    runner.add("sell", watching, watching)
    on = ClaudeCli("claude", tmp_path / "cwd", runner=runner)
    at = AT + timedelta(minutes=5)
    _run(p2ctx, on, at, dart_api_key="k")
    during = seen[0]
    assert during is not None
    assert (during.enabled, during.task_id, during.task_kind, during.task_started_at) == (
        True,
        tid,
        "sell-confirm",
        at,
    )
    assert (during.ended_at, during.dart_key) == (None, True)
    after = ai_repo.runner_state(p2conn)
    assert after is not None
    assert (after.task_id, after.ended_at, after.result) == (None, at, "ok")


# ── any error is recorded on its task, and the next task goes on ───────────────────────────


def test_classify() -> None:
    assert classify(flows.RetryLaterError("down")) == "outage"
    assert classify(flows.SourceAnswerError("corrupt")) == "unusable"
    assert classify(zlib.error("invalid stored block lengths")) == "unusable"
    assert classify(http.client.IncompleteRead(b"half")) == "outage"
    assert classify(ConnectionResetError("reset")) == "outage"
    assert classify(sqlite3.OperationalError("database is locked")) == "outage"
    assert classify(sqlite3.OperationalError("no such column: x")) == "fault"
    assert classify(KeyError("x")) == "fault"
    assert classify(ValueError("prompt is over 120000 bytes")) == "fault"
    assert classify(repo.NotFoundError("pick 9")) == "fault"


def test_a_fault_gives_up_at_once_and_blocks_nothing(
    p2ctx: JobContext,
    p2conn: sqlite3.Connection,
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prices(world, "042660.KS", "069500.KS")
    fid = filing(p2conn, OCEAN, "R7", "분기보고서 (2026.09)")
    world.texts["R7"] = "영업이익 2,100억원"
    broken = task(p2conn, "extract", None, "extract:R7", "filing", fid)
    behind = shock_task(p2conn)  # a sale's confirmation queued behind the broken task

    def missing_row(env: Any, t: ai_repo.TaskRow) -> Any:
        raise repo.NotFoundError("filing 999")

    monkeypatch.setitem(
        flows.FLOWS, "extract", replace(flows.FLOWS["extract"], prepare=missing_row)
    )
    runner = ScriptedRunner()
    runner.add("sell", sell("반증"), sell("반증"))
    report = _run(p2ctx, ClaudeCli("claude", tmp_path / "cwd", runner=runner))
    assert [(t["kind"], t["status"]) for t in report["tasks"]] == [
        ("extract", "gave-up"),
        ("sell-confirm", "done"),  # it went on
    ]
    assert report["result"] == "failed"
    stuck = ai_repo.get_task(p2conn, broken)
    assert (stuck.status, stuck.attempts) == ("failed", 3)  # waits for a person now
    assert stuck.last_error is not None
    assert stuck.last_error.startswith("prepare: NotFoundError: filing 999 (test_ai_runner.py:")
    assert "Traceback" in capsys.readouterr().err  # in the runner's log
    assert pick_of(p2conn, OCEAN).decision == "sell"
    assert ai_repo.get_task(p2conn, behind).status == "done"
    # Nothing more happens to it on its own.
    assert (
        _run(p2ctx, ClaudeCli("claude", tmp_path / "cwd", runner=runner), AT + timedelta(hours=2))[
            "result"
        ]
        == "nothing-due"
    )


def test_a_cut_connection_waits_and_a_corrupt_download_gives_up_after_three(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World, tmp_path: Path
) -> None:
    fid = filing(p2conn, OCEAN, "R8", "분기보고서 (2026.09)")
    tid = task(p2conn, "extract", None, "extract:R8", "filing", fid)
    cli = ClaudeCli("claude", tmp_path / "cwd", runner=ScriptedRunner())
    # The text download is cut mid-answer (the network): wait an hour, no attempt, no try.
    world.text_errors["R8"] = SourceUnreachableError("IncompleteRead: 1024 bytes read")
    assert [t["status"] for t in _run(p2ctx, cli)["tasks"]] == ["later"]
    waiting = ai_repo.get_task(p2conn, tid)
    assert (waiting.status, waiting.attempts, waiting.source_tries) == ("pending", 0, 0)
    assert waiting.not_before == AT + timedelta(hours=1)
    # The zip arrives broken: a source try each time, and the third gives the filing up.
    world.text_errors["R8"] = FilingSourceError("DART document R8: error: invalid block type")
    for n in range(1, MAX_SOURCE_TRIES + 1):
        report = _run(p2ctx, cli, AT + timedelta(hours=n))
        assert report["tasks"][0]["status"] == ("later" if n < MAX_SOURCE_TRIES else "gave-up")
        assert ai_repo.get_task(p2conn, tid).source_tries == n
    done = ai_repo.get_task(p2conn, tid)
    assert (done.status, done.attempts) == ("failed", 3)
    assert done.last_error is not None
    assert done.last_error.startswith("gave up after 3 unusable downloads")
    assert ai_repo.get_filing(p2conn, fid).status == "failed"
    assert ai_repo.last_calls(p2conn) == []  # no model was asked
    # A person asks again (after fixing the cause): the tries start over.
    del world.text_errors["R8"]
    world.texts["R8"] = "영업이익 2,100억원"
    with transaction(p2conn):
        retry_ai(p2conn, "paper", f"ai-cli:failed:{tid}", AT + timedelta(hours=5), "다시")
    runner = ScriptedRunner()
    runner.add("extract", {"metrics": [], "notes": "없음"})
    cli = ClaudeCli("claude", tmp_path / "cwd", runner=runner)
    assert _run(p2ctx, cli, AT + timedelta(hours=5))["tasks"][0]["status"] == "done"
    assert ai_repo.get_filing(p2conn, fid).status == "done"


# ── the calls are kept before what follows them; a kept answer is applied again ─────────────


def _discovery(conn: sqlite3.Connection, month: str = "2026-12") -> int:
    return task(
        conn, "discovery", None, f"discovery:paper:{month}", "discovery", detail={"month": month}
    )


ANSWER: dict[str, Any] = {
    "macro": "금리 인하",
    "flows": [],
    "picks": [],
    "candidates": [],
}


def test_a_crash_after_the_calls_keeps_the_answer_and_its_tokens(
    p2ctx: JobContext,
    p2conn: sqlite3.Connection,
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tid = _discovery(p2conn)
    world.series("069500.KS", Market.KR, "2026-11-01", "2026-11-30", "110000")
    world.series("SPY", Market.US, "2026-11-01", "2026-11-30", "800")
    original = flows.FLOWS["discovery"]

    def broken_after(*args: Any) -> None:
        raise AttributeError("'NoneType' object has no attribute 'last'")

    monkeypatch.setitem(flows.FLOWS, "discovery", replace(original, after=broken_after))
    runner = ScriptedRunner()
    runner.add("discovery", ANSWER)  # one answer only: asking twice would fail the test
    at = AT
    report = _run(p2ctx, ClaudeCli("claude", tmp_path / "cwd", runner=runner), at)
    assert [(t["status"], t["calls"], t["tokens"]) for t in report["tasks"]] == [
        ("gave-up", 1, 4400)
    ]
    assert report["month_tokens"] == 4400  # the Opus call is counted, whatever came after
    kept = ai_repo.get_task(p2conn, tid)
    [call] = ai_repo.calls_of_task(p2conn, tid)
    assert (kept.status, kept.answer_calls) == ("failed", [call.call_id])
    assert kept.last_error is not None
    assert kept.last_error.startswith("after: AttributeError")
    # The code is fixed and the owner asks again: the kept answer is applied, not asked again.
    monkeypatch.setitem(flows.FLOWS, "discovery", original)
    with transaction(p2conn):
        out = retry_ai(p2conn, "paper", str(tid), at + timedelta(days=1))
    assert out["kept_answer"] is True
    report = _run(
        p2ctx, ClaudeCli("claude", tmp_path / "cwd", runner=runner), at + timedelta(days=1)
    )
    assert [(t["status"], t["calls"], t["tokens"], t["reused"]) for t in report["tasks"]] == [
        ("done", 0, 0, True)
    ]
    done = ai_repo.get_task(p2conn, tid)
    assert done.result is not None
    assert (done.status, done.answer_calls, done.result["applied_again"]) == (
        "done",
        None,
        [call.call_id],
    )
    assert len(ai_repo.calls_of_task(p2conn, tid)) == 1
    event = repo.event_by_ref(p2conn, "paper", "discovery:2026-12")
    assert event is not None
    assert event.payload["tokens"] == 4400  # the judgment's own cost


def test_an_outage_after_the_calls_waits_and_applies_the_kept_answer(
    p2ctx: JobContext,
    p2conn: sqlite3.Connection,
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prices(world, "042660.KS", "069500.KS")
    tid = shock_task(p2conn)
    original = flows.FLOWS["sell-confirm"]
    blinks = iter([sqlite3.OperationalError("database is locked")])

    def apply_once_locked(*args: Any) -> dict[str, Any]:
        for exc in blinks:
            raise exc
        return original.apply(*args)

    monkeypatch.setitem(flows.FLOWS, "sell-confirm", replace(original, apply=apply_once_locked))
    runner = ScriptedRunner()
    runner.add("sell", sell("반증"), sell("반증"))
    report = _run(p2ctx, ClaudeCli("claude", tmp_path / "cwd", runner=runner))
    assert report["tasks"][0]["status"] == "later"
    waiting = ai_repo.get_task(p2conn, tid)
    assert (waiting.status, waiting.attempts) == ("pending", 0)  # the status it had before
    assert waiting.answer_calls is not None
    report = _run(
        p2ctx, ClaudeCli("claude", tmp_path / "cwd", runner=runner), AT + timedelta(hours=1)
    )
    assert [(t["status"], t["reused"]) for t in report["tasks"]] == [("done", True)]
    assert pick_of(p2conn, OCEAN).decision == "sell"
    assert len(ai_repo.calls_of_task(p2conn, tid)) == 2  # asked once


def test_an_unusable_answer_is_asked_again(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World, tmp_path: Path
) -> None:
    prices(world, "042660.KS", "069500.KS")
    tid = shock_task(p2conn)
    runner = ScriptedRunner()
    bad = {**sell("유지"), "verdict": "모르겠다"}
    runner.add("sell", bad, bad, sell("유지"), sell("유지"))
    first = _run(p2ctx, ClaudeCli("claude", tmp_path / "cwd", runner=runner))
    assert first["tasks"][0]["status"] == "failed"
    dropped = ai_repo.get_task(p2conn, tid)
    assert (dropped.attempts, dropped.answer_calls) == (1, None)
    second = _run(
        p2ctx, ClaudeCli("claude", tmp_path / "cwd", runner=runner), AT + timedelta(minutes=5)
    )
    assert [(t["status"], t["calls"], t["reused"]) for t in second["tasks"]] == [("done", 2, False)]
    assert len(ai_repo.calls_of_task(p2conn, tid)) == 4


def test_the_end_to_end_runner_finds_no_cli_without_the_setting(
    p2ctx: JobContext, p2conn: sqlite3.Connection, p2cfg: Any, world: World
) -> None:
    """The real CLI is never reachable from the tests (conftest); the job reports it missing."""
    from autotrade.jobs.cli import main

    shock_task(p2conn)
    out: list[str] = []
    env = {"AUTOTRADE_DB": str(p2cfg.db_path), "AUTOTRADE_AI_CALLS": "1"}
    assert (
        main(["ai", "--at", "2026-10-13T10:00"], sources=world.sources(), env=env, out=out.append)
        == 0
    )
    assert '"result":"cli-missing"' in out[0]
    assert '"due":1' in out[0]
    beat = ai_repo.runner_state(p2conn)
    assert beat is not None
    assert beat.cli is None
    assert os.environ.get("AUTOTRADE_CLAUDE_BIN") is None


def test_a_working_folder_that_cannot_be_made_is_a_cli_that_cannot_start(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World, tmp_path: Path
) -> None:
    prices(world, "042660.KS", "069500.KS")
    tid = shock_task(p2conn)
    blocker = tmp_path / "data"
    blocker.write_text("a file where the folder should be")
    report = _run(p2ctx, ClaudeCli("claude", blocker / "ai-cwd", runner=ScriptedRunner()))
    assert [t["status"] for t in report["tasks"]] == ["cli-missing"]
    waiting = ai_repo.get_task(p2conn, tid)
    assert (waiting.status, waiting.attempts) == ("pending", 0)
    assert ai_repo.last_calls(p2conn) == []


def test_a_broken_cli_wrapper_is_recorded_like_any_fault(
    p2ctx: JobContext,
    p2conn: sqlite3.Connection,
    world: World,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prices(world, "042660.KS", "069500.KS")
    tid = shock_task(p2conn)

    def broken(cmd: list[str], **kw: Any) -> Any:
        raise RuntimeError("the wrapper itself broke")

    report = _run(p2ctx, ClaudeCli("claude", tmp_path / "cwd", runner=broken))
    assert [t["status"] for t in report["tasks"]] == ["gave-up"]
    stuck = ai_repo.get_task(p2conn, tid)
    assert (stuck.status, stuck.attempts) == ("failed", 3)
    assert stuck.last_error is not None
    assert stuck.last_error.startswith("call: RuntimeError: the wrapper itself broke")
    assert "Traceback" in capsys.readouterr().err


def test_a_kept_answer_can_be_dropped_to_ask_again(
    p2ctx: JobContext,
    p2conn: sqlite3.Connection,
    world: World,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An answer the code can never apply (a shape no check caught): the owner asks afresh."""
    prices(world, "042660.KS", "069500.KS")
    tid = shock_task(p2conn)
    original = flows.FLOWS["sell-confirm"]

    def cannot_apply(*args: Any) -> dict[str, Any]:
        raise TypeError("unhashable type: 'list'")

    monkeypatch.setitem(flows.FLOWS, "sell-confirm", replace(original, apply=cannot_apply))
    runner = ScriptedRunner()
    runner.add("sell", sell("유지"), sell("유지"))
    _run(p2ctx, ClaudeCli("claude", tmp_path / "cwd", runner=runner))
    assert ai_repo.get_task(p2conn, tid).answer_calls is not None
    monkeypatch.setitem(flows.FLOWS, "sell-confirm", original)
    with transaction(p2conn):
        out = retry_ai(p2conn, "paper", str(tid), AT + timedelta(hours=1), ask_again=True)
    assert out["kept_answer"] is False
    assert ai_repo.get_task(p2conn, tid).answer_calls is None
    runner.add("sell", sell("반증"), sell("반증"))
    report = _run(
        p2ctx, ClaudeCli("claude", tmp_path / "cwd", runner=runner), AT + timedelta(hours=1)
    )
    assert [(t["status"], t["calls"], t["reused"]) for t in report["tasks"]] == [("done", 2, False)]
    assert pick_of(p2conn, OCEAN).decision == "sell"
    from autotrade.jobs.cli import main

    with pytest.raises(SystemExit):
        main(["resolve", "x", "--ask-again"], env={})
