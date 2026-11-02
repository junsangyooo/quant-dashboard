"""SQLite 파일 하나(data/app.db). 연결 하나를 잠금으로 나눠 쓴다.

구조 버전은 `PRAGMA user_version`이에요(TASKS T-13).
- 0 + 표 없음: 새 파일 → v2 구조를 바로 만들어요.
- 0 + v1 표(MVP 0.2): 옛 파일 → `app.db.v1-backup`으로 복사해 두고 v2로 옮겨요(전략 · 버전 · 모의투자 기록은 그대로).
- 2: 지금 구조.
"""

from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

SCHEMA_V1 = """
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

# v2에서 더한 표(SPEC 11-1 · TASKS T-13). 캐시 · 블록 전략 · 실전 운용 · 주문(회차) · 체결 · 할 일 · 알림 ·
# 이 앱이 산 수량 · 운용 현금 · 기업 행동 기록.
SCHEMA_V2 = """
-- 컴퓨터 키 파일로 감싼 데이터 키(T-50 · SPEC 10 vault). 키 파일 자체는 데이터 폴더 밖에 있어요.
CREATE TABLE IF NOT EXISTS owner_keyfile(id INTEGER PRIMARY KEY CHECK (id = 1), wrap BLOB NOT NULL, at TEXT);
CREATE TABLE IF NOT EXISTS stock_info(
  symbol TEXT PRIMARY KEY, name TEXT, market TEXT, security_type TEXT, common INTEGER,
  list_date TEXT, delist_date TEXT, shares REAL, leverage REAL, liquidation INTEGER, suspended INTEGER,
  updated_at TEXT
);
CREATE TABLE IF NOT EXISTS stock_warnings(
  symbol TEXT NOT NULL, kind TEXT NOT NULL, start_d TEXT, end_d TEXT, PRIMARY KEY(symbol, kind, start_d)
);
CREATE TABLE IF NOT EXISTS sectors(sector_id TEXT PRIMARY KEY, name TEXT NOT NULL, depth INTEGER, parent TEXT);
CREATE TABLE IF NOT EXISTS sector_members(sector_id TEXT NOT NULL, symbol TEXT NOT NULL, PRIMARY KEY(sector_id, symbol));
CREATE TABLE IF NOT EXISTS investor(
  symbol TEXT NOT NULL, d TEXT NOT NULL, foreign_net REAL, institution_net REAL, individual_net REAL,
  foreign_rate REAL, PRIMARY KEY(symbol, d)
);
CREATE TABLE IF NOT EXISTS dart_corp(stock_code TEXT PRIMARY KEY, corp_code TEXT NOT NULL, name TEXT);
CREATE TABLE IF NOT EXISTS dart_jobs(
  id INTEGER PRIMARY KEY, phase INTEGER NOT NULL, kind TEXT NOT NULL, arg TEXT NOT NULL,
  done INTEGER NOT NULL DEFAULT 0, UNIQUE(kind, arg)
);
CREATE TABLE IF NOT EXISTS dart_quota(day TEXT PRIMARY KEY, used INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS dart_fin(
  stock_code TEXT NOT NULL, year INTEGER NOT NULL, reprt TEXT NOT NULL, fs_div TEXT NOT NULL,
  account TEXT NOT NULL, amount REAL, add_amount REAL, rcept_no TEXT NOT NULL, rcept_dt TEXT NOT NULL,
  PRIMARY KEY(stock_code, year, reprt, fs_div, account)
);
CREATE TABLE IF NOT EXISTS dart_disc(
  rcept_no TEXT PRIMARY KEY, stock_code TEXT NOT NULL, rcept_dt TEXT NOT NULL, report_nm TEXT NOT NULL, kind TEXT
);
CREATE TABLE IF NOT EXISTS dart_shares(
  stock_code TEXT NOT NULL, year INTEGER NOT NULL, reprt TEXT NOT NULL, shares REAL, treasury REAL,
  rcept_no TEXT NOT NULL, rcept_dt TEXT NOT NULL, PRIMARY KEY(stock_code, year, reprt)
);
CREATE TABLE IF NOT EXISTS dart_div(
  stock_code TEXT NOT NULL, year INTEGER NOT NULL, dps REAL, rcept_no TEXT NOT NULL, rcept_dt TEXT NOT NULL,
  PRIMARY KEY(stock_code, year)
);
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY, strategy_id INTEGER NOT NULL, version_id INTEGER NOT NULL,
  status TEXT NOT NULL, amount REAL NOT NULL, settings TEXT NOT NULL, account_tail TEXT,
  started_at TEXT NOT NULL, ended_at TEXT, end_kind TEXT
);
CREATE TABLE IF NOT EXISTS run_versions(
  run_id INTEGER NOT NULL, version_id INTEGER NOT NULL, from_d TEXT NOT NULL, PRIMARY KEY(run_id, from_d)
);
CREATE TABLE IF NOT EXISTS run_cash(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, d TEXT NOT NULL, kind TEXT NOT NULL,
  amount REAL NOT NULL, ref TEXT, at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions(
  run_id INTEGER NOT NULL, symbol TEXT NOT NULL, qty INTEGER NOT NULL, avg_price REAL NOT NULL,
  first_d TEXT, peak REAL, PRIMARY KEY(run_id, symbol)
);
CREATE TABLE IF NOT EXISTS run_equity(
  run_id INTEGER NOT NULL, d TEXT NOT NULL, equity REAL NOT NULL, cash REAL NOT NULL, PRIMARY KEY(run_id, d)
);
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, d TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL,
  round INTEGER NOT NULL, client_order_id TEXT NOT NULL UNIQUE, toss_order_id TEXT,
  kind TEXT NOT NULL, qty INTEGER NOT NULL, price REAL, tif TEXT, status TEXT NOT NULL, reason TEXT,
  created_at TEXT NOT NULL, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS fills(
  id INTEGER PRIMARY KEY, order_id INTEGER NOT NULL, qty INTEGER NOT NULL, price REAL NOT NULL,
  commission REAL NOT NULL DEFAULT 0, tax REAL NOT NULL DEFAULT 0, filled_at TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS cond_orders(
  id INTEGER PRIMARY KEY, run_id INTEGER NOT NULL, symbol TEXT NOT NULL, toss_cond_id TEXT, kind TEXT NOT NULL,
  qty INTEGER NOT NULL, stop_trigger REAL, take_trigger REAL, expire TEXT, status TEXT NOT NULL,
  created_at TEXT NOT NULL, triggered_at TEXT
);
CREATE TABLE IF NOT EXISTS todos(
  id INTEGER PRIMARY KEY, run_id INTEGER, kind TEXT NOT NULL, severity TEXT NOT NULL, symbol TEXT,
  title TEXT NOT NULL, body TEXT, data TEXT, status TEXT NOT NULL DEFAULT 'open',
  created_at TEXT NOT NULL, resolved_at TEXT
);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY, at TEXT NOT NULL, live INTEGER NOT NULL, kind TEXT NOT NULL, title TEXT NOT NULL,
  body TEXT, read INTEGER NOT NULL DEFAULT 0, telegram TEXT
);
CREATE TABLE IF NOT EXISTS backtest_runs(
  id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL, ran_at TEXT NOT NULL, start_d TEXT, end_d TEXT, cash REAL
);
CREATE TABLE IF NOT EXISTS corp_actions(
  id INTEGER PRIMARY KEY, run_id INTEGER, symbol TEXT NOT NULL, kind TEXT NOT NULL, ratio REAL,
  detected_at TEXT NOT NULL, applied_at TEXT, data TEXT
);
"""

SCHEMA_VERSION = 2


def body_format(body_json: str) -> str:
    """버전 본문의 꼴: slots(v1 일곱 칸) · graph(v1 그래프 노드) · blocks(v3)."""
    try:
        body = json.loads(body_json)
    except ValueError:
        return "unknown"
    if isinstance(body, dict):
        if "slots" in body:
            return "slots"
        graph = body.get("graph")
        if isinstance(graph, dict):
            return "blocks" if "blocks" in graph else "graph"
    return "unknown"


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
        self.migrated_from: int | None = None
        self._open_schema()

    def _tables(self) -> set[str]:
        return {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}

    def _open_schema(self) -> None:
        version = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        if version == SCHEMA_VERSION:
            self.conn.executescript(SCHEMA_V2)  # 표가 하나 빠졌으면 채워요
            return
        if version > SCHEMA_VERSION:
            raise RuntimeError(f"앱보다 새 데이터 구조예요 · {version}")
        if version == 0 and "owner" not in self._tables() and "strategies" not in self._tables():
            self.conn.executescript(SCHEMA_V1 + SCHEMA_V2)
            self._add_v2_columns()
            self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            return
        self._migrate_v1()

    def _add_v2_columns(self) -> None:
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(versions)")}
        if "format" not in cols:
            self.conn.execute("ALTER TABLE versions ADD COLUMN format TEXT")
        cols = {r[1] for r in self.conn.execute("PRAGMA table_info(bar_meta)")}
        if "yahoo" in cols:
            self.conn.execute("ALTER TABLE bar_meta RENAME COLUMN yahoo TO source")

    def _migrate_v1(self) -> None:
        """MVP 0.2 파일 → v2. 먼저 파일을 복사해 두고, 한 묶음(트랜잭션)으로 옮겨요."""
        if str(self.path) != ":memory:":
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            backup = self.path.with_name(self.path.name + ".v1-backup")
            if not backup.exists():
                dst = sqlite3.connect(str(backup))
                try:
                    self.conn.backup(dst)
                finally:
                    dst.close()
                with contextlib.suppress(OSError):
                    os.chmod(backup, 0o600)
        self.conn.executescript(SCHEMA_V1)  # v1 표가 일부 빠진 옛 파일도 받아요
        self.conn.execute("BEGIN")
        try:
            self._add_v2_columns()
            for r in self.conn.execute("SELECT id, body FROM versions").fetchall():
                self.conn.execute("UPDATE versions SET format=? WHERE id=?", (body_format(r["body"]), r["id"]))
            for stmt in SCHEMA_V2.split(";"):
                if stmt.strip():
                    self.conn.execute(stmt)
            self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self.conn.execute("COMMIT")
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        self.migrated_from = 0

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

    # ── 백업 · 복원 · 삭제(T-53) ──────────────────────────────────────────

    def backup_to(self, dst: Path) -> None:
        """지금 파일을 한 장으로 복사해요(쓰는 중이어도 일관된 사진 · sqlite backup)."""
        with self.lock:
            out = sqlite3.connect(str(dst))
            try:
                self.conn.backup(out)
            finally:
                out.close()
        with contextlib.suppress(OSError):
            os.chmod(dst, 0o600)

    def replace_with(self, src: Path | None, *, keep: bool = True) -> None:
        """파일을 통째로 바꿔요(src가 없으면 빈 새 파일). 같은 DB 객체를 쓰는 곳은 그대로 이어서 써요.

        keep이면 바꾸기 전 파일을 `<이름>.before-replace` 한 장으로 남겨요(덮어씀). 삭제는 keep=False.
        """
        if str(self.path) == ":memory:":
            raise RuntimeError("memory db")
        with self.lock:
            self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            self.conn.close()
            kept = self.path.with_name(self.path.name + ".before-replace")
            with contextlib.suppress(FileNotFoundError):
                if keep:
                    os.replace(self.path, kept)
                else:
                    os.remove(self.path)
                    for old in (kept, self.path.with_name(self.path.name + ".v1-backup")):
                        with contextlib.suppress(FileNotFoundError):
                            os.remove(old)
            for ext in ("-wal", "-shm"):
                with contextlib.suppress(FileNotFoundError):
                    os.remove(str(self.path) + ext)
            if src is not None:
                with open(src, "rb") as fi, open(self.path, "wb") as fo:
                    fo.write(fi.read())
            self.conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
            self.conn.row_factory = sqlite3.Row
            with contextlib.suppress(OSError):
                os.chmod(self.path, 0o600)
                os.chmod(kept, 0o600)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.migrated_from = None
            self._open_schema()

    def get_meta(self, k: str) -> str | None:
        row = self.one("SELECT v FROM meta WHERE k=?", (k,))
        return None if row is None else str(row["v"])

    def set_meta(self, k: str, v: str | None) -> None:
        if v is None:
            self.run("DELETE FROM meta WHERE k=?", (k,))
        else:
            self.run("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
