"""Daily copy of data/autotrade.db: VACUUM INTO data/backup/autotrade/autotrade-<KST date>.db.

- VACUUM INTO writes a consistent, compacted copy while the web service and the jobs keep using
  the database (WAL). The copy goes to a temporary name, is checked (PRAGMA quick_check) and only
  then renamed, so a file named like a backup is always a complete one.
- Files are 0600 in a 0700 folder: the copy holds the PIN hash and the sessions.
- Seven daily copies are kept; older ones are deleted. Running it again the same day replaces
  that day's copy.
- The cookie and PIN secret (data/autotrade.secret) is deliberately not copied next to the hash.
  Restoring a copy without it only means setting the PIN again (python -m autotrade.jobs set-pin).

Restore: stop autotrade.service, copy a backup over data/autotrade.db (remove the -wal and -shm
files first), start the service.
"""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

KEEP = 7
NAME = re.compile(r"^autotrade-(\d{4}-\d{2}-\d{2})\.db$")


class BackupError(RuntimeError):
    pass


def backup_dir_for(db_path: Path) -> Path:
    """data/backup/autotrade next to data/autotrade.db."""
    return db_path.parent / "backup" / "autotrade"


def backup_path(backup_dir: Path, d: date) -> Path:
    return backup_dir / f"autotrade-{d.isoformat()}.db"


def _rotate(backup_dir: Path, keep: int) -> list[str]:
    dated = sorted(
        (m.group(1), p) for p in backup_dir.iterdir() if (m := NAME.match(p.name)) is not None
    )
    removed: list[str] = []
    for _, path in dated[: max(len(dated) - keep, 0)]:
        path.unlink()
        removed.append(path.name)
    for stray in backup_dir.glob("*.tmp"):
        stray.unlink()
    return removed


def run_backup(
    conn: sqlite3.Connection, backup_dir: Path, d: date, keep: int = KEEP
) -> dict[str, Any]:
    """Copy the database behind `conn` (outside any transaction) to the backup of day d."""
    if conn.in_transaction:
        raise BackupError("VACUUM INTO cannot run inside a transaction")
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_dir.chmod(0o700)
    target = backup_path(backup_dir, d)
    tmp = target.with_name(target.name + ".tmp")
    tmp.unlink(missing_ok=True)
    # VACUUM INTO accepts an existing empty file: create it 0600 so the copy is never readable.
    os.close(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
    try:
        conn.execute("VACUUM INTO ?", (str(tmp),))
        check = sqlite3.connect(f"file:{tmp}?mode=ro", uri=True)
        try:
            verdict = str(check.execute("PRAGMA quick_check").fetchone()[0])
        finally:
            check.close()
        if verdict != "ok":
            raise BackupError(f"copy failed its check: {verdict}")
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, target)
    removed = _rotate(backup_dir, keep)
    kept = sorted(p.name for p in backup_dir.iterdir() if NAME.match(p.name))
    return {
        "result": "ok",
        "path": str(target),
        "bytes": target.stat().st_size,
        "kept": kept,
        "removed": removed,
    }
