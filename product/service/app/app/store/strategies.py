"""전략 · 버전 · 백테스트 기록(strategies · versions · backtest_runs).

v2 전략 API(`api_v2.py`) · 실전(`run/live.py`) · 모의투자(`run/paper.py`) · 조립(`main.py`)이 같이 써요.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .db import DB

# ── 전략 ────────────────────────────────────────────────────────────────────


def list_strategies(db: DB) -> list[sqlite3.Row]:
    return db.all("SELECT * FROM strategies ORDER BY id")


def strategy(db: DB, sid: int) -> sqlite3.Row | None:
    return db.one("SELECT * FROM strategies WHERE id=?", (sid,))


def has_strategy(db: DB, sid: int) -> bool:
    return db.one("SELECT id FROM strategies WHERE id=?", (sid,)) is not None


def strategy_name_row(db: DB, sid: int) -> sqlite3.Row | None:
    return db.one("SELECT name FROM strategies WHERE id=?", (sid,))


def strategy_names(db: DB) -> list[sqlite3.Row]:
    """이름 겹침 확인(`id` · `name`)."""
    return db.all("SELECT id, name FROM strategies")


def add_strategy(db: DB, name: str, template: str, source: str | None, created_at: str) -> int:
    return db.run("INSERT INTO strategies(name,template,source,created_at) VALUES(?,?,?,?)",
                  (name, template, source, created_at))


def delete_strategy(db: DB, sid: int) -> None:
    """버전과 전략을 한 트랜잭션으로 지워요."""
    with db.tx():
        db.run("DELETE FROM versions WHERE strategy_id=?", (sid,))
        db.run("DELETE FROM strategies WHERE id=?", (sid,))


def strategy_in_use(db: DB, sid: int) -> bool:
    """모의투자나 실전 운용 기록이 있는 전략(삭제 막음)."""
    return db.one(
        "SELECT r.id FROM paper_runs r JOIN versions v ON v.id=r.version_id WHERE v.strategy_id=? "
        "UNION SELECT id FROM runs WHERE strategy_id=? LIMIT 1", (sid, sid)) is not None


# ── 버전 ────────────────────────────────────────────────────────────────────


def add_version(db: DB, sid: int, body: str, problems: int, created_at: str, *, name: str,
                template: str) -> tuple[int, int]:
    """다음 번호로 버전을 더하고 전략 이름 · 꼴을 맞춰요(한 트랜잭션). (버전 id, 번호)."""
    with db.tx():
        no = int(db.one_row("SELECT COALESCE(MAX(no),0)+1 AS n FROM versions WHERE strategy_id=?", (sid,))["n"])
        vid = db.run("INSERT INTO versions(strategy_id,no,body,problems,created_at,format) VALUES(?,?,?,?,?,?)",
                     (sid, no, body, problems, created_at, "blocks"))
        db.run("UPDATE strategies SET name=?, template=? WHERE id=?", (name, template, sid))
    return vid, no


def version(db: DB, vid: int) -> sqlite3.Row | None:
    return db.one("SELECT * FROM versions WHERE id=?", (vid,))


def version_body(db: DB, vid: int) -> sqlite3.Row | None:
    return db.one("SELECT body FROM versions WHERE id=?", (vid,))


def version_no(db: DB, vid: int) -> sqlite3.Row | None:
    return db.one("SELECT no FROM versions WHERE id=?", (vid,))


def latest_version(db: DB, sid: int) -> sqlite3.Row | None:
    return db.one("SELECT * FROM versions WHERE strategy_id=? ORDER BY no DESC LIMIT 1", (sid,))


def versions_of(db: DB, sid: int) -> list[sqlite3.Row]:
    return db.all("SELECT * FROM versions WHERE strategy_id=? ORDER BY no DESC", (sid,))


def version_with_name(db: DB, vid: int) -> sqlite3.Row | None:
    """버전 전체 + 전략 이름."""
    return db.one("SELECT v.*, s.name FROM versions v JOIN strategies s ON s.id=v.strategy_id WHERE v.id=?", (vid,))


def version_no_name(db: DB, vid: int) -> sqlite3.Row | None:
    """버전 번호 · 전략 이름."""
    return db.one("SELECT v.no, s.name FROM versions v JOIN strategies s ON s.id=v.strategy_id WHERE v.id=?", (vid,))


def version_summary(db: DB, vid: int) -> sqlite3.Row | None:
    """버전 번호 · 전략 id · 전략 이름."""
    return db.one("SELECT v.no, v.strategy_id, s.name FROM versions v JOIN strategies s ON s.id=v.strategy_id "
                  "WHERE v.id=?", (vid,))


# ── 백테스트 기록 ───────────────────────────────────────────────────────────


def add_backtest_run(db: DB, vid: int, ran_at: str, start_d: str, end_d: str, cash: Any) -> int:
    return db.run("INSERT INTO backtest_runs(version_id, ran_at, start_d, end_d, cash) VALUES(?,?,?,?,?)",
                  (vid, ran_at, start_d, end_d, cash))


def was_backtested(db: DB, vid: int) -> bool:
    """이 앱에서 백테스트한 버전인가."""
    return db.one("SELECT 1 FROM backtest_runs WHERE version_id=?", (vid,)) is not None


def last_backtest_at(db: DB, vid: int) -> str | None:
    row = db.one("SELECT ran_at FROM backtest_runs WHERE version_id=? ORDER BY id DESC LIMIT 1", (vid,))
    return str(row["ran_at"]) if row else None
