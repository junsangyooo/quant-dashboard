"""SQLite 파일 하나(data/app.db). 연결 하나를 잠금으로 나눠 쓴다."""

from __future__ import annotations

import contextlib
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS owner(
  id INTEGER PRIMARY KEY CHECK (id = 1),
  scrypt_n INTEGER NOT NULL,
  pw_salt BLOB NOT NULL, pw_wrap BLOB NOT NULL,
  rc_salt BLOB NOT NULL, rc_wrap BLOB NOT NULL,
  fails INTEGER NOT NULL DEFAULT 0,
  locked_until REAL NOT NULL DEFAULT 0,
  adult INTEGER NOT NULL, terms_at TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS secrets(name TEXT PRIMARY KEY, blob BLOB NOT NULL, updated_at TEXT);
CREATE TABLE IF NOT EXISTS strategies(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, template TEXT NOT NULL,
  source TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS versions(
  id INTEGER PRIMARY KEY, strategy_id INTEGER NOT NULL, no INTEGER NOT NULL,
  body TEXT NOT NULL, problems INTEGER NOT NULL, created_at TEXT NOT NULL,
  UNIQUE(strategy_id, no)
);
CREATE TABLE IF NOT EXISTS bars(
  symbol TEXT NOT NULL, d TEXT NOT NULL,
  o REAL, h REAL, l REAL, c REAL NOT NULL, v REAL,
  PRIMARY KEY(symbol, d)
);
CREATE TABLE IF NOT EXISTS bar_meta(
  symbol TEXT PRIMARY KEY, yahoo TEXT, from_d TEXT, to_d TEXT, fetched_at REAL
);
CREATE TABLE IF NOT EXISTS paper_runs(
  id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL, cash0 REAL NOT NULL,
  state TEXT NOT NULL, status TEXT NOT NULL, started_at TEXT NOT NULL,
  last_date TEXT, ended_at TEXT
);
CREATE TABLE IF NOT EXISTS paper_equity(
  run_id INTEGER NOT NULL, d TEXT NOT NULL, equity REAL NOT NULL, cash REAL NOT NULL,
  PRIMARY KEY(run_id, d)
);
CREATE TABLE IF NOT EXISTS paper_trades(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, d TEXT NOT NULL, symbol TEXT NOT NULL,
  side TEXT NOT NULL, qty INTEGER NOT NULL, price REAL NOT NULL, amount REAL NOT NULL,
  cost REAL NOT NULL, pnl REAL, reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_judgements(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, d TEXT NOT NULL, made_at TEXT NOT NULL,
  plans TEXT NOT NULL, how TEXT NOT NULL
);
"""


class DB:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with contextlib.suppress(OSError):
                self.path.parent.chmod(0o700)
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        if str(path) != ":memory:":
            with contextlib.suppress(OSError):
                os.chmod(self.path, 0o600)
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def all(self, sql: str, args: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        with self.lock:
            return list(self.conn.execute(sql, args).fetchall())

    def one(self, sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        with self.lock:
            return self.conn.execute(sql, args).fetchone()

    def run(self, sql: str, args: tuple[Any, ...] = ()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, args)
            return int(cur.lastrowid or 0)

    def many(self, sql: str, rows: list[tuple[Any, ...]]) -> None:
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                self.conn.executemany(sql, rows)
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    @contextlib.contextmanager
    def tx(self):  # type: ignore[no-untyped-def]
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                yield self
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    def get_meta(self, k: str) -> str | None:
        row = self.one("SELECT v FROM meta WHERE k=?", (k,))
        return None if row is None else str(row["v"])

    def set_meta(self, k: str, v: str | None) -> None:
        if v is None:
            self.run("DELETE FROM meta WHERE k=?", (k,))
        else:
            self.run("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
