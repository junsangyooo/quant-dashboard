"""The web API serves only the database schema its code was written for (CONTRACT.md 세션과 보안).

The API never migrates: `python -m autotrade.jobs migrate` is the one command that does, and
deploy/deploy.sh runs it after a fresh predeploy backup. While the stored schema differs from the
code's — the minutes of a deploy between `git pull` and the restart, a failed migration, a code
rollback over a migrated database — every /api route (and /api/healthz, which the deploy health
check reads) answers 503 {error: 'schema', detail: {stored, code}} instead of reading or writing
tables of another shape. A missing database file counts as schema 0; the API does not create it.

- stored: MAX(version) of schema_migrations, 0 when the table does not exist.
- code: the last entry of autotrade.db.migrations.MIGRATIONS.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from autotrade.api.errors import ApiError
from autotrade.db.migrations import MIGRATIONS


def code_version() -> int:
    return MIGRATIONS[-1][0]


def stored_version(conn: sqlite3.Connection) -> int:
    """MAX(version) of schema_migrations; 0 when the table is missing (a new database)."""
    try:
        row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    except sqlite3.OperationalError:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_migrations'"
        ).fetchone()
        if exists is None:
            return 0
        raise
    return int(row[0]) if row and row[0] is not None else 0


def mismatch(stored: int) -> ApiError:
    detail: dict[str, Any] = {"stored": stored, "code": code_version()}
    return ApiError(503, "schema", detail)


def require_current(conn: sqlite3.Connection) -> None:
    """503 schema unless the database is at the code's version; 503 db if it cannot be read."""
    try:
        stored = stored_version(conn)
    except sqlite3.Error as exc:
        raise ApiError(503, "db") from exc
    if stored != code_version():
        raise mismatch(stored)
