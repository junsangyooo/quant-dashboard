"""할 일 · 알림함(todos · alerts). 실전(`run/live.py`) · 모의투자(`run/paper.py`) · 텔레그램(`telegram.py`) · 조립이 같이 써요."""

from __future__ import annotations

import sqlite3

from .db import DB

# ── 할 일 ───────────────────────────────────────────────────────────────────


def open_todo_id(db: DB, kind: str, symbol: str | None) -> int | None:
    """같은 종류 · 종목(없으면 '')의 열린 할 일."""
    row = db.one("SELECT id FROM todos WHERE kind=? AND IFNULL(symbol,'')=? AND status='open'", (kind, symbol or ""))
    return int(row["id"]) if row else None


def has_open_todo(db: DB, kind: str) -> bool:
    return db.one("SELECT 1 FROM todos WHERE kind=? AND status='open'", (kind,)) is not None


def add_todo(db: DB, run_id: int | None, kind: str, severity: str, symbol: str | None, title: str, body: str | None,
             data: str | None, created_at: str) -> int:
    return db.run("INSERT INTO todos(run_id,kind,severity,symbol,title,body,data,status,created_at) "
                  "VALUES(?,?,?,?,?,?,?, 'open', ?)", (run_id, kind, severity, symbol, title, body, data, created_at))


def resolve_open(db: DB, at: str, *kinds: str) -> None:
    """그 종류(여럿)의 열린 할 일을 모두 해결로."""
    marks = ",".join("?" * len(kinds))
    db.run(f"UPDATE todos SET status='resolved', resolved_at=? WHERE kind IN ({marks}) AND status='open'",
           (at, *kinds))


def resolve_open_for(db: DB, at: str, kind: str, symbol: str) -> None:
    """그 종류 · 종목의 열린 할 일을 해결로."""
    db.run("UPDATE todos SET status='resolved', resolved_at=? WHERE kind=? AND symbol=? AND status='open'",
           (at, kind, symbol))


def resolve_todo(db: DB, tid: int, at: str) -> None:
    db.run("UPDATE todos SET status='resolved', resolved_at=? WHERE id=?", (at, tid))


def todo_of_kind(db: DB, tid: int, kind: str) -> sqlite3.Row | None:
    return db.one("SELECT * FROM todos WHERE id=? AND kind=?", (tid, kind))


def open_big_order(db: DB, tid: int) -> sqlite3.Row | None:
    """열린 큰 주문 할 일(huge · too_big)."""
    return db.one("SELECT * FROM todos WHERE id=? AND kind IN ('huge','too_big') AND status='open'", (tid,))


def open_todos(db: DB) -> list[sqlite3.Row]:
    """화면 목록(새것 먼저)."""
    return db.all("SELECT id,kind,severity,symbol,title,body,created_at FROM todos WHERE status='open' ORDER BY id DESC")


def count_open_todos(db: DB) -> int:
    return int(db.one_row("SELECT COUNT(*) AS n FROM todos WHERE status='open'")["n"])


# ── 알림함 ──────────────────────────────────────────────────────────────────


def add_alert(db: DB, at: str, live: int, kind: str, title: str, body: str | None, telegram: str | None = None) -> int:
    """`live`는 1(실전) · 0(모의) · `telegram`은 보낸 결과('sent' 또는 없음)."""
    return db.run("INSERT INTO alerts(at, live, kind, title, body, telegram) VALUES(?,?,?,?,?,?)",
                  (at, live, kind, title, body, telegram))


def recent_alerts(db: DB) -> list[sqlite3.Row]:
    return db.all("SELECT id,at,live,kind,title,read FROM alerts ORDER BY id DESC LIMIT 50")
