"""SQLite connection (WAL) and explicit transactions.

The connection runs in autocommit mode (isolation_level=None); jobs open one explicit
BEGIN IMMEDIATE transaction around their work, so a crash leaves nothing half-written and
dry runs simply roll back. Engine functions never commit on their own.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from autotrade.timeutil import to_iso


def connect(path: Path | str, *, check_same_thread: bool = True) -> sqlite3.Connection:
    """Open the database. The web API passes check_same_thread=False: each request owns its
    connection, but FastAPI may open and close it on different worker threads."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        str(path), isolation_level=None, timeout=30.0, check_same_thread=check_same_thread
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def journal_mode(conn: sqlite3.Connection) -> str:
    row = conn.execute("PRAGMA journal_mode").fetchone()
    return str(row[0])


@contextmanager
def transaction(conn: sqlite3.Connection, *, rollback: bool = False) -> Iterator[None]:
    """One write transaction. rollback=True discards everything at the end (dry run)."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("ROLLBACK" if rollback else "COMMIT")


def json_default(value: object) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return to_iso(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    raise TypeError(f"not JSON serialisable: {type(value).__name__}")


def dumps(value: object) -> str:
    """JSON for payload columns. Decimals stay exact as strings."""
    return json.dumps(value, default=json_default, ensure_ascii=False, sort_keys=True)


def loads(text: str | None) -> Any:
    return json.loads(text) if text else None
