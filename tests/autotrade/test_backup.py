"""Daily database copies (python -m autotrade.jobs backup) and the V3 migration."""

from __future__ import annotations

import sqlite3
import stat
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from autotrade.config import Config
from autotrade.db import repo
from autotrade.db.connection import connect, transaction
from autotrade.db.migrations import MIGRATIONS, V1, V2, _statements, current_version, migrate
from autotrade.jobs.backup import BackupError, backup_dir_for, backup_path, run_backup
from autotrade.jobs.tasks import JobContext, backup_job

from .helpers import kst


def test_a_backup_is_a_checked_private_copy(conn: sqlite3.Connection, cfg: Config) -> None:
    folder = backup_dir_for(cfg.db_path)
    assert folder == cfg.db_path.parent / "backup" / "autotrade"
    report = run_backup(conn, folder, date(2026, 10, 9))
    target = backup_path(folder, date(2026, 10, 9))
    assert report["path"] == str(target)
    assert report["kept"] == ["autotrade-2026-10-09.db"]
    assert stat.S_IMODE(target.stat().st_mode) == 0o600  # it holds the PIN hash
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    copy = sqlite3.connect(target)
    try:
        assert copy.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert copy.execute("SELECT COUNT(*) FROM ledgers").fetchone()[0] == 2
        assert copy.execute("PRAGMA journal_mode").fetchone()[0] == "delete"
    finally:
        copy.close()
    # Again the same day: the copy is replaced, not duplicated.
    run_backup(conn, folder, date(2026, 10, 9))
    assert sorted(p.name for p in folder.iterdir()) == ["autotrade-2026-10-09.db"]


def test_seven_copies_are_kept(conn: sqlite3.Connection, tmp_path: Path) -> None:
    folder = tmp_path / "copies"
    folder.mkdir()
    for day in range(1, 9):
        (folder / f"autotrade-2026-10-0{day}.db").write_bytes(b"")
    (folder / "autotrade-2026-10-05.db.tmp").write_bytes(b"half")
    (folder / "notes.txt").write_text("not a backup")
    report = run_backup(conn, folder, date(2026, 10, 9))
    assert report["removed"] == ["autotrade-2026-10-01.db", "autotrade-2026-10-02.db"]
    assert report["kept"] == [f"autotrade-2026-10-0{d}.db" for d in range(3, 10)]
    assert sorted(p.name for p in folder.iterdir()) == [*report["kept"], "notes.txt"]


def test_a_copy_that_fails_its_check_is_not_kept(
    conn: sqlite3.Connection, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = sqlite3.connect

    class Broken:
        def __init__(self, inner: sqlite3.Connection) -> None:
            self.inner = inner

        def execute(self, sql: str) -> Any:
            return self if sql.startswith("PRAGMA quick_check") else self.inner.execute(sql)

        def fetchone(self) -> tuple[str]:
            return ("*** in database main *** page 3 is never used",)

        def close(self) -> None:
            self.inner.close()

    monkeypatch.setattr(sqlite3, "connect", lambda *a, **k: Broken(real(*a, **k)))
    with pytest.raises(BackupError, match="failed its check"):
        run_backup(conn, tmp_path / "b", date(2026, 10, 9))
    assert list((tmp_path / "b").iterdir()) == []


def test_no_backup_inside_a_transaction(conn: sqlite3.Connection, tmp_path: Path) -> None:
    conn.execute("BEGIN")
    try:
        with pytest.raises(BackupError, match="transaction"):
            run_backup(conn, tmp_path / "b", date(2026, 10, 9))
    finally:
        conn.execute("ROLLBACK")


def test_backup_job_reports_failures(ctx: JobContext, monkeypatch: pytest.MonkeyPatch) -> None:
    ok = backup_job(ctx, kst("2026-10-09 16:05"))
    assert (ok["job"], ok["result"]) == ("backup", "ok")

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise OSError("disk full")

    monkeypatch.setattr("autotrade.jobs.tasks.run_backup", broken)
    failed = backup_job(ctx, kst("2026-10-09 16:10"))
    assert (failed["result"], failed["error"]) == ("failed", "OSError: disk full")


def test_v3_keeps_the_events_and_widens_them(tmp_path: Path) -> None:
    """A database made at V2 (the deployed API) gains refs and 'todo-resolved' with every row."""
    path = tmp_path / "v2.db"
    conn = connect(path)
    try:
        conn.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL,"
            " applied_at TEXT NOT NULL)"
        )
        for version, sql in ((1, V1), (2, V2)):
            with transaction(conn):
                for statement in _statements(sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, 'old', '2026-10-09T00:00:00+00:00')",
                    (version,),
                )
        at = kst("2026-07-01 08:30")
        with transaction(conn):
            repo.ensure_ledger(conn, "paper", "모의투자", at)
            conn.execute(
                "INSERT INTO events (ledger_id, kind, event_date, occurred_at, amount, currency,"
                " payload, created_at, updated_at) VALUES ('paper', 'start', '2026-07-01', ?,"
                " '10000000', 'KRW', '{}', ?, ?)",
                ("2026-06-30T23:30:00+00:00",) * 3,
            )
            conn.execute(
                "INSERT INTO snapshots (ledger_id, date, valued_at, total_krw, positions,"
                " cash_krw, cash_usd, cash_parts, fx_rate, fx_at, contributions, pnl_krw,"
                " created_at) VALUES ('paper', '2026-07-01', ?, '1', '[]', '1', '0', '[]', '1',"
                " ?, '1', '0', ?)",
                ("2026-07-01T07:00:00+00:00",) * 3,
            )
        assert current_version(conn) == 2
        assert migrate(conn, at) == len(MIGRATIONS)
        [start] = repo.events_of_ledger(conn, "paper")
        assert (start.kind, start.amount, start.ref) == ("start", Decimal("10000000"), None)
        snap = repo.get_snapshot(conn, "paper", date(2026, 7, 1))
        assert snap is not None
        assert snap.baseline_cash_krw is None
        with transaction(conn):
            repo.insert_event(
                conn,
                ledger_id="paper",
                kind="todo-resolved",
                event_date=date(2026, 7, 2),
                occurred_at=at,
                ref="todo-resolved:plan:1",
            )
        with pytest.raises(sqlite3.IntegrityError), transaction(conn):  # one start per ledger
            repo.insert_event(
                conn, ledger_id="paper", kind="start", event_date=date(2026, 7, 2), occurred_at=at
            )
        with pytest.raises(sqlite3.IntegrityError), transaction(conn):  # one event per ref
            repo.insert_event(
                conn,
                ledger_id="paper",
                kind="todo-resolved",
                event_date=date(2026, 7, 2),
                occurred_at=at,
                ref="todo-resolved:plan:1",
            )
    finally:
        conn.close()
