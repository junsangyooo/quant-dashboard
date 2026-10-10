"""Fixes of the audit of 2026-10-10 that are not the AI runner's (see test_ai_runner.py):
E4 the AI 'to do's, E6 a company the filing source does not know, E7 switch costs, E11 private
database files, E12 migrations only through `migrate` and the pre-deploy copy, and the filing
downloads behind E2."""

from __future__ import annotations

import http.client
import io
import json
import os
import sqlite3
import stat
import zipfile
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from autotrade.ai import flows
from autotrade.db import ai_repo, repo
from autotrade.db.connection import connect, transaction
from autotrade.db.migrations import LATEST_VERSION, V1, V2, V3, V4, _statements, stored_version
from autotrade.domain.instruments import Currency, Instrument, Kind, Market
from autotrade.domain.ledger import LedgerState, Position
from autotrade.engine.todos import TodoError, open_todos, resolve, retry_ai
from autotrade.jobs import cli
from autotrade.jobs.ai_tasks import watch_job
from autotrade.jobs.backup import PREDEPLOY_KEEP
from autotrade.jobs.lock import ai_lock_path, job_lock, lock_path
from autotrade.jobs.tasks import JobContext
from autotrade.market import filings as fl
from autotrade.market.filings import CompanyNotFoundError, DartFilingSource, FilingInfo
from autotrade.market.research import YahooValuationSource
from autotrade.rules.discovery import RULE_ID

from .ai_fakes import ScriptedRunner
from .fakes import World
from .helpers import PHASE1_ENV, kst
from .phase2 import flat_world, pick_of
from .test_ai import AT, HANWHA, OCEAN, candidate, prices, run, shock_task, task

D = Decimal


# ── E12: only `migrate` changes the schema; the pre-deploy copy ─────────────────────────────


def _cli(argv: list[str], db: Path, env: dict[str, str] | None = None) -> tuple[int, list[str]]:
    lines: list[str] = []
    code = cli.main([*argv, "--db", str(db)], env=env or dict(PHASE1_ENV), out=lines.append)
    return code, lines


def _at_version(path: Path, version: int) -> None:
    conn = connect(path)
    try:
        conn.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL,"
            " applied_at TEXT NOT NULL)"
        )
        for v, sql in ((1, V1), (2, V2), (3, V3), (4, V4))[:version]:
            if v in (4,):
                conn.execute("PRAGMA foreign_keys=OFF")
            with transaction(conn):
                for statement in _statements(sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, 'old', '2026-10-09T00:00:00+00:00')",
                    (v,),
                )
            conn.execute("PRAGMA foreign_keys=ON")
    finally:
        conn.close()


def test_every_job_but_migrate_refuses_another_schema(tmp_path: Path) -> None:
    db = tmp_path / "data" / "autotrade.db"
    for command in ("tick", "ai", "check", "status", "todos", "stage", "watch"):
        code, lines = _cli([command, "--at", "2026-10-13T08:30"], db)
        assert code == cli.EXIT_SCHEMA
        assert [json.loads(x) for x in lines] == [
            {"job": command, "result": "schema-mismatch", "stored": 0, "code": LATEST_VERSION}
        ]
        assert not db.exists()  # a job never creates the database
    old = tmp_path / "old.db"
    _at_version(old, 4)
    code, lines = _cli(["tick", "--at", "2026-10-13T08:30"], old)
    assert (code, json.loads(lines[0])["stored"]) == (cli.EXIT_SCHEMA, 4)
    conn = connect(old)
    try:
        assert stored_version(conn) == 4  # untouched: no job migrated it
    finally:
        conn.close()
    # migrate brings it up and writes the fixed rows (rules, instruments, the seed picks).
    code, lines = _cli(["migrate"], old)
    assert (code, json.loads(lines[0])["schema"]) == (0, LATEST_VERSION)
    conn = connect(old)
    try:
        assert stored_version(conn) == LATEST_VERSION
        assert repo.get_rule(conn, RULE_ID).name == "3년 발굴"
        assert len(ai_repo.picks_of(conn, "paper", RULE_ID)) == 15
        # A schema newer than the code (a rollback): refused too.
        with transaction(conn):
            conn.execute(
                "INSERT INTO schema_migrations VALUES (?, 'future', '2027-01-01T00:00:00+00:00')",
                (LATEST_VERSION + 1,),
            )
    finally:
        conn.close()
    code, lines = _cli(["ai"], old)
    assert json.loads(lines[0]) == {
        "job": "ai",
        "result": "schema-mismatch",
        "stored": LATEST_VERSION + 1,
        "code": LATEST_VERSION,
    }
    assert code == cli.EXIT_SCHEMA


def test_migrate_waits_for_the_tick_and_the_ai_runner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No tick or AI run may write halfway through a schema change: migrate holds both locks,
    and when either stays busy it changes nothing (deploy.sh stops before the restart)."""
    monkeypatch.setattr(cli, "LOCK_WAIT_S", 0.3)
    monkeypatch.setattr(cli, "MIGRATE_AI_WAIT_S", 0.3)
    db = tmp_path / "autotrade.db"
    _at_version(db, 4)
    for held, name in ((lock_path(db), "jobs"), (ai_lock_path(db), "ai")):
        with job_lock(held) as got:
            assert got
            code, lines = _cli(["migrate"], db)
        assert code == cli.EXIT_BUSY
        assert (json.loads(lines[0])["result"], json.loads(lines[0])["lock"]) == ("busy", name)
        conn = connect(db)
        try:
            assert stored_version(conn) == 4  # untouched
        finally:
            conn.close()
    code, lines = _cli(["migrate"], db)
    assert (code, json.loads(lines[0])["result"]) == (0, "ok")
    conn = connect(db)
    try:
        assert stored_version(conn) == LATEST_VERSION
    finally:
        conn.close()
    # A tick that comes while migrate runs skips its turn (the tick never waits for the lock).
    with job_lock(lock_path(db)):
        assert json.loads(_cli(["tick"], db)[1][0])["result"] == "busy"


def test_the_database_files_are_private(tmp_path: Path) -> None:
    previous = os.umask(0o002)  # the server's
    try:
        db = tmp_path / "data" / "autotrade.db"
        assert _cli(["migrate"], db)[0] == 0
        conn = connect(db)  # kept open: the -wal and -shm files stay while it is
        try:
            with transaction(conn):
                repo.set_setting(conn, "x", "1", AT)
            for name in ("autotrade.db", "autotrade.db-wal", "autotrade.db-shm"):
                assert stat.S_IMODE((db.parent / name).stat().st_mode) == 0o600, name
            # A database made before the rule (0664) is tightened by the next migrate.
            for name in ("autotrade.db", "autotrade.db-wal"):
                (db.parent / name).chmod(0o664)
            _code, lines = _cli(["migrate"], db)
            assert json.loads(lines[0])["secured"] == ["autotrade.db", "autotrade.db-wal"]
            assert stat.S_IMODE(db.stat().st_mode) == 0o600
        finally:
            conn.close()
    finally:
        os.umask(previous)


def test_the_predeploy_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "data" / "autotrade.db"
    code, lines = _cli(["backup", "--predeploy"], db)
    assert (code, [json.loads(x) for x in lines]) == (
        0,
        [{"job": "backup", "result": "no-database"}],
    )
    assert not db.exists()
    _at_version(db, 4)  # before `migrate`: an older schema is copied as it is
    folder = db.parent / "backup" / "autotrade"
    folder.mkdir(parents=True)
    for day in range(1, 8):
        (folder / f"autotrade-2026-10-0{day}.db").write_bytes(b"")  # seven daily copies
    for n in range(PREDEPLOY_KEEP):
        (folder / f"autotrade-predeploy-2026100{n}-010000.db").write_bytes(b"")
    code, lines = _cli(["backup", "--predeploy", "--at", "2026-10-10T15:04:05+00:00"], db)
    assert code == 0
    assert "\n" not in lines[0]  # one line for deploy.sh
    report = json.loads(lines[0])
    target = folder / "autotrade-predeploy-20261010-150405.db"
    assert (report["result"], report["path"]) == ("ok", str(target))
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert report["removed"] == ["autotrade-predeploy-20261000-010000.db"]  # five newest kept
    assert len([p for p in folder.iterdir() if p.name.startswith("autotrade-2026")]) == 7
    copy = sqlite3.connect(target)
    try:
        assert copy.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 4
    finally:
        copy.close()
    # The pre-deploy copy never migrates and takes no lock: a running tick does not stop it.
    with job_lock(lock_path(db)):
        assert _cli(["backup", "--predeploy", "--at", "2026-10-10T15:05:00+00:00"], db)[0] == 0
    # A copy that cannot be made fails the deploy (non-zero).
    monkeypatch.setattr(cli, "run_predeploy_backup", _disk_full)
    code, lines = _cli(["backup", "--predeploy"], db)
    assert (code, json.loads(lines[0])["result"]) == (1, "failed")
    with pytest.raises(SystemExit):
        cli.main(["check", "--predeploy", "--db", str(db)], env={})
    # The daily backup copies any schema too, and a missing database is no failure.
    assert json.loads(_cli(["backup"], tmp_path / "none.db")[1][0])["result"] == "no-database"


def _disk_full(*args: Any, **kwargs: Any) -> Any:
    raise OSError(28, "No space left on device")


# ── E4: the AI 'to do's ─────────────────────────────────────────────────────────────────────


def _stuck(conn: sqlite3.Connection, task_id: int, times: int = 3) -> None:
    with transaction(conn):
        for _ in range(times):
            ai_repo.finish_task(conn, task_id, AT, status="failed", error="exit 1: 401 login")


def test_a_stuck_ai_task_is_a_todo_to_retry_or_give_up(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World, tmp_path: Path
) -> None:
    prices(world, "042660.KS", "069500.KS")
    tid = shock_task(p2conn)
    _stuck(p2conn, tid, 2)
    assert open_todos(p2conn, "paper") == []  # an attempt is left
    with pytest.raises(TodoError, match="not an open manual action"), transaction(p2conn):
        resolve(p2conn, "paper", f"ai-cli:failed:{tid}", AT)
    _stuck(p2conn, tid, 1)
    [todo] = open_todos(p2conn, "paper", 3)
    assert (todo.todo_id, todo.kind) == (f"ai-cli:failed:{tid}", "ai-cli:failed")
    assert (todo.facts["task_kind"], todo.facts["attempts"], todo.facts["instrument_id"]) == (
        "sell-confirm",
        3,
        OCEAN,
    )
    # A stuck confirmation blocks no new one: the next shock asks again (E4).
    flat_world(
        p2conn,
        world,
        "2026-10-14",
        start="2026-08-01",
        overrides={"042660.KS": lambda i, d: "80" if d >= date(2026, 10, 13) else "100"},
    )
    report = watch_job(p2ctx, "paper", kst("2026-10-14 08:40"))
    assert [(t["kind"], t["pick"]) for t in report["tasks"]] == [("sell-confirm", OCEAN)]
    # The CLI lists it with the web's id, asks it again, or gives it up.
    db = p2ctx.cfg.db_path
    env = {"AUTOTRADE_PAPER_START_DATE": "2026-07-01"}
    code, lines = _cli(["todos", "--at", "2026-10-14T10:00"], db, env)
    listed = json.loads("".join(lines))["todos"]
    assert [t["id"] for t in listed] == [f"ai-cli:failed:{tid}"]
    code, lines = _cli(["ai-retry", f"ai-cli:failed:{tid}", "--note", "로그인 고침"], db, env)
    retried = json.loads("".join(lines))
    assert (code, retried["result"], retried["task_id"]) == (0, "retried", tid)
    again = ai_repo.get_task(p2conn, tid)
    assert (again.status, again.attempts) == ("pending", 0)
    event = repo.events_of_ledger(p2conn, "paper", ["todo-resolved"])[-1]
    assert (event.payload["action"], event.payload["note"], event.payload["closed"]) == (
        "retry",
        "로그인 고침",
        [f"ai-cli:failed:{tid}"],
    )
    code, lines = _cli(["ai-retry", str(tid)], db, env)  # it is pending now
    assert (code, json.loads("".join(lines))["result"]) == (1, "not-a-todo")
    _stuck(p2conn, tid)
    code, lines = _cli(["resolve", f"ai-cli:failed:{tid}", "--note", "판단 안 함"], db, env)
    closed = json.loads("".join(lines))
    assert (code, closed["result"], closed["closed"]) == (0, "resolved", [f"ai-cli:failed:{tid}"])
    gone = ai_repo.get_task(p2conn, tid)
    assert gone.result is not None
    assert (gone.status, gone.result["cancelled_by"], gone.last_error) == (
        "cancelled",
        "owner",
        "exit 1: 401 login",
    )
    assert open_todos(p2conn, "paper") == []
    code, lines = _cli(["resolve", f"ai-cli:failed:{tid}"], db, env)
    assert json.loads("".join(lines))["result"] == "already-resolved"
    for bad, result in (("ai-cli:failed:x", "bad-id"), ("ai-cli:failed:999", "not-found")):
        code, lines = _cli(["resolve", bad], db, env)
        assert (code, json.loads("".join(lines))["result"]) == (1, result)
    code, lines = _cli(["ai-retry", "nope"], db, env)
    assert json.loads("".join(lines))["result"] == "bad-id"
    code, lines = _cli(["ai-retry"], db, env)
    assert json.loads("".join(lines))["result"] == "bad-id"
    with pytest.raises(SystemExit):
        cli.main(["status", "x", "--db", str(db)], env=env)
    with pytest.raises(TodoError, match="ledger"), transaction(p2conn):
        retry_ai(p2conn, "live", str(tid), AT)


# ── E7: switch costs that cannot be computed wait ───────────────────────────────────────────


def test_switch_costs_without_a_price_wait(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    prices(world, "NVDA", "SPY")  # no price of the holding to give up
    nvda = candidate(p2conn)
    hanwha = pick_of(p2conn, HANWHA)
    with transaction(p2conn):
        ai_repo.save_sleeve(
            p2conn,
            "paper",
            RULE_ID,
            LedgerState(
                cash=dict.fromkeys(Currency, D(0)),
                positions={HANWHA: Position(HANWHA, Currency.KRW, 2, D(1944000), D(1944000))},
            ),
            AT,
        )
    tid = task(
        p2conn,
        "switch",
        nvda,
        "s1",
        "buy-price",
        detail={"candidate": nvda, "weakest": hanwha.pick_id},
    )
    report = run(p2ctx, ScriptedRunner())  # no call is made
    assert report["tasks"][0]["status"] == "later"
    waiting = ai_repo.get_task(p2conn, tid)
    assert (waiting.status, waiting.attempts) == ("pending", 0)
    assert waiting.last_error == "prepare: switch costs: no price of KR:012450"
    # A holding without shares costs nothing to give up: zeros are a fact, the question goes on.
    env = flows.FlowEnv(p2conn, p2ctx.cfg, p2ctx.sources, AT)
    sold = Instrument("US:X", Market.US, Currency.USD, Kind.STOCK, "X", "X", "X")
    empty = replace(hanwha, instrument_id="US:X")
    assert flows.switch_costs(env, empty, sold, sold, None, None).total_krw == D(0)
    with pytest.raises(flows.RetryLaterError, match="rate"):
        flows.switch_costs(env, hanwha, sold, sold, D(1), None)  # dollars without a rate


# ── E2 at the source: a cut connection and a corrupt zip are what they are ───────────────────


def test_filing_downloads_name_their_failures() -> None:
    def cut(url: str, params: Any, headers: Any) -> bytes:
        raise http.client.IncompleteRead(b"half", 1024)

    info = FilingInfo("dart", "R1", "보고서", None, "보고서", date(2026, 10, 12), None)
    with pytest.raises(fl.SourceUnreachableError, match="IncompleteRead"):
        DartFilingSource("key", cut).fetch_text(info)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("main.xml", "본문" * 2000)
    data = bytearray(buf.getvalue())
    start = data.index(b"main.xml") + len("main.xml")
    data[start + 10 : start + 60] = b"\x00" * 50  # break the deflate stream
    with pytest.raises(fl.FilingSourceError, match="DART document R1"):
        DartFilingSource("key", lambda u, p, h: bytes(data)).fetch_text(info)


def test_a_company_the_source_does_not_know_does_not_stop_the_others(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    inner = world.sources()
    assert inner.dart is not None

    class OneUnknown:
        name = "dart"

        def fetch_filings(self, instrument: Instrument, start: date, end: date) -> list[FilingInfo]:
            if instrument.instrument_id == HANWHA:
                raise CompanyNotFoundError(f"DART has no corp_code for {instrument.ticker}")
            assert inner.dart is not None
            return inner.dart.fetch_filings(instrument, start, end)

        def fetch_text(self, filing: FilingInfo) -> str:
            raise AssertionError("not read here")

    ctx = replace(p2ctx, sources=replace(inner, dart=OneUnknown()))
    flat_world(p2conn, world, "2026-10-13", start="2026-08-01")
    report = watch_job(ctx, "paper", kst("2026-10-13 08:40"))
    assert report["errors"][f"filings:{HANWHA}"] == "DART has no corp_code for 012450"
    dart = ai_repo.source_state(p2conn, "dart")
    assert dart is not None
    assert dart.state == "ok"  # the source works; it does not know one company
    asked = [c for c in world.calls if c.startswith("filings:dart")]
    assert len(asked) == 7  # the other Korean picks were asked


def test_yahoo_says_what_a_symbol_is() -> None:
    class Ticker:
        def __init__(self, symbol: str) -> None:
            self.info = {"QQQ": {"quoteType": "etf"}, "AAPL": {"quoteType": "EQUITY"}}.get(
                symbol, {}
            )

    module = SimpleNamespace(Ticker=Ticker)
    source = YahooValuationSource(module, attempts=1)
    assert (source.fetch_quote_type("QQQ"), source.fetch_quote_type("AAPL")) == ("ETF", "EQUITY")
    with pytest.raises(Exception, match="quoteType"):
        source.fetch_quote_type("NONE")
