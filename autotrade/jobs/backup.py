"""Copies of data/autotrade.db under data/backup/autotrade/.

- Daily (after the snapshot, autotrade/jobs/schedule.py): autotrade-<KST date>.db, seven kept.
  Running it again the same day replaces that day's copy.
- Before a deploy (`python -m autotrade.jobs backup --predeploy`, deploy/deploy.sh runs it before
  `migrate`): autotrade-predeploy-<UTC YYYYmmdd-HHMMSS>.db, the newest five kept. They are a
  separate set: they never push a daily copy out, nor the other way round.
- VACUUM INTO writes a consistent, compacted copy while the web service and the jobs keep using
  the database (WAL). The copy goes to a temporary name, is checked (PRAGMA integrity_check) and
  only then renamed, so a file named like a backup is always a complete one.
- Files are 0600 in a 0700 folder: the copy holds the PIN hash and the sessions.
- The cookie and PIN secret (data/autotrade.secret) is deliberately not copied next to the hash.
  Restoring a copy without it only means setting the PIN again (python -m autotrade.jobs set-pin).
- A copy reads the database whatever its schema (a pre-deploy copy is made before `migrate`).

Restore: stop autotrade.service, copy a backup over data/autotrade.db (remove the -wal and -shm
files first), start the service.
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from autotrade.timeutil import UTC, require_aware

KEEP = 7
PREDEPLOY_KEEP = 5
NAME = re.compile(r"^autotrade-(\d{4}-\d{2}-\d{2})\.db$")
PREDEPLOY_NAME = re.compile(r"^autotrade-predeploy-(\d{8}-\d{6})\.db$")
STRAY_AGE_S = 3600.0  # a temporary file older than this was left by a copy that died


class BackupError(RuntimeError):
    pass


def backup_dir_for(db_path: Path) -> Path:
    """data/backup/autotrade next to data/autotrade.db."""
    return db_path.parent / "backup" / "autotrade"


def backup_path(backup_dir: Path, d: date) -> Path:
    return backup_dir / f"autotrade-{d.isoformat()}.db"


def predeploy_path(backup_dir: Path, at: datetime) -> Path:
    return backup_dir / f"autotrade-predeploy-{require_aware(at).astimezone(UTC):%Y%m%d-%H%M%S}.db"


def _rotate(backup_dir: Path, name: re.Pattern[str], keep: int) -> list[str]:
    """Delete the oldest copies of one set beyond `keep`, and temporary files a dead copy left
    (only old ones: another copy may be writing its own right now)."""
    dated = sorted(
        (m.group(1), p) for p in backup_dir.iterdir() if (m := name.match(p.name)) is not None
    )
    removed: list[str] = []
    for _, path in dated[: max(len(dated) - keep, 0)]:
        path.unlink()
        removed.append(path.name)
    now = time.time()
    for stray in backup_dir.glob("*.tmp"):
        try:
            if now - stray.stat().st_mtime > STRAY_AGE_S:
                stray.unlink()
        except FileNotFoundError:  # its copy just finished
            continue
    return removed


def _copy(conn: sqlite3.Connection, backup_dir: Path, target: Path) -> None:
    """VACUUM INTO a 0600 temporary file, check it, rename it to `target`."""
    if conn.in_transaction:
        raise BackupError("VACUUM INTO cannot run inside a transaction")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.chmod(0o700)
    tmp = target.with_name(f"{target.name}.{os.getpid()}.tmp")
    tmp.unlink(missing_ok=True)
    # VACUUM INTO accepts an existing empty file: create it 0600 so the copy is never readable.
    os.close(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    try:
        conn.execute("VACUUM INTO ?", (str(tmp),))
        check = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        try:
            verdict = str(check.execute("PRAGMA integrity_check").fetchone()[0])
        finally:
            check.close()
        if verdict != "ok":
            raise BackupError(f"copy failed its check: {verdict}")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, target)


def _report(
    backup_dir: Path, target: Path, name: re.Pattern[str], removed: list[str]
) -> dict[str, Any]:
    return {
        "result": "ok",
        "path": str(target),
        "bytes": target.stat().st_size,
        "kept": sorted(p.name for p in backup_dir.iterdir() if name.match(p.name)),
        "removed": removed,
    }


def run_backup(
    conn: sqlite3.Connection, backup_dir: Path, d: date, keep: int = KEEP
) -> dict[str, Any]:
    """Copy the database behind `conn` (outside any transaction) to the backup of day d."""
    target = backup_path(backup_dir, d)
    _copy(conn, backup_dir, target)
    return _report(backup_dir, target, NAME, _rotate(backup_dir, NAME, keep))


def run_predeploy_backup(
    conn: sqlite3.Connection, backup_dir: Path, at: datetime, keep: int = PREDEPLOY_KEEP
) -> dict[str, Any]:
    """Copy the database behind `conn` before a deploy (any schema), the newest `keep` kept."""
    target = predeploy_path(backup_dir, at)
    _copy(conn, backup_dir, target)
    return _report(backup_dir, target, PREDEPLOY_NAME, _rotate(backup_dir, PREDEPLOY_NAME, keep))
