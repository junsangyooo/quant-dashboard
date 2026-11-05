"""DART 저장(dart_corp · dart_jobs · dart_quota · dart_fin · dart_disc · dart_shares · dart_div).

큐 · 하루 한도 · 읽기 흐름은 `app/dart.py`(`DartStore`)가, 백테스트 · 실전 배당 대조는 읽기만 써요. 접수일 다음 거래일부터
쓰는 규칙(R-J9)은 읽는 쪽이 정해요(여기는 행을 그대로 돌려줘요).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .db import DB

# ── 하루 한도 ───────────────────────────────────────────────────────────────


def quota_used(db: DB, day: str) -> int:
    row = db.one("SELECT used FROM dart_quota WHERE day=?", (day,))
    return int(row["used"]) if row else 0


def count_request(db: DB, day: str) -> None:
    db.run("INSERT INTO dart_quota(day, used) VALUES(?, 1) ON CONFLICT(day) DO UPDATE SET used=used+1", (day,))


def fill_quota(db: DB, day: str, limit: int) -> None:
    """DART가 한도를 알려 오면 그날 쓴 수를 한도로."""
    db.run("INSERT INTO dart_quota(day, used) VALUES(?, ?) ON CONFLICT(day) DO UPDATE SET used=?", (day, limit, limit))


# ── 큐 ──────────────────────────────────────────────────────────────────────


def add_job(db: DB, phase: int, kind: str, arg: str) -> None:
    """이미 있는 일은 그대로."""
    db.run("INSERT OR IGNORE INTO dart_jobs(phase, kind, arg) VALUES(?,?,?)", (phase, kind, arg))


def add_jobs(db: DB, rows: list[tuple[int, str, str]]) -> None:
    db.many("INSERT OR IGNORE INTO dart_jobs(phase, kind, arg) VALUES(?,?,?)", rows)


def job_counts(db: DB, slow_phase: int) -> tuple[int, int, int]:
    """(전체 · 끝낸 것 · `slow_phase` 앞 단계의 남은 것)."""
    total = int(db.one_row("SELECT COUNT(*) n FROM dart_jobs")["n"])
    done = int(db.one_row("SELECT COUNT(*) n FROM dart_jobs WHERE done=1")["n"])
    fast_left = int(db.one_row("SELECT COUNT(*) n FROM dart_jobs WHERE done=0 AND phase<?", (slow_phase,))["n"])
    return total, done, fast_left


def next_job(db: DB) -> sqlite3.Row | None:
    return db.one("SELECT * FROM dart_jobs WHERE done=0 ORDER BY phase, id LIMIT 1")


def job_done(db: DB, jid: int) -> None:
    db.run("UPDATE dart_jobs SET done=1 WHERE id=?", (jid,))


# ── 받은 것 ─────────────────────────────────────────────────────────────────


def corp_codes(db: DB) -> list[str]:
    """회사 번호(종목 코드 순)."""
    return [r["corp_code"] for r in db.all("SELECT corp_code FROM dart_corp ORDER BY stock_code")]


def stock_of(db: DB, corp: str) -> str | None:
    row = db.one("SELECT stock_code FROM dart_corp WHERE corp_code=?", (corp,))
    return str(row["stock_code"]) if row else None


def put_corps(db: DB, rows: list[tuple[str, str, str]]) -> None:
    """(종목 코드 · 회사 번호 · 이름)."""
    db.many("INSERT INTO dart_corp(stock_code, corp_code, name) VALUES(?,?,?) "
            "ON CONFLICT(stock_code) DO UPDATE SET corp_code=excluded.corp_code, name=excluded.name", rows)


def put_shares(db: DB, row: tuple[str, int, str, float | None, float | None, str, str]) -> None:
    """(종목 · 연도 · 보고서 · 주식 총수 · 자기주식 · 접수번호 · 접수일)."""
    db.run("INSERT OR REPLACE INTO dart_shares VALUES(?,?,?,?,?,?,?)", row)


def put_div(db: DB, row: tuple[str, int, float | None, str, str]) -> None:
    """(종목 · 연도 · 주당 배당금 · 접수번호 · 접수일)."""
    db.run("INSERT OR REPLACE INTO dart_div VALUES(?,?,?,?,?)", row)


def put_fin(db: DB, rows: list[tuple[Any, ...]]) -> None:
    db.many("INSERT OR REPLACE INTO dart_fin VALUES(?,?,?,?,?,?,?,?,?)", rows)


def put_disc(db: DB, rows: list[tuple[Any, ...]]) -> None:
    db.many("INSERT OR REPLACE INTO dart_disc VALUES(?,?,?,?,?)", rows)


# ── 읽기 ────────────────────────────────────────────────────────────────────


def fin_rows(db: DB, stock: str) -> list[sqlite3.Row]:
    return db.all("SELECT * FROM dart_fin WHERE stock_code=? ORDER BY year, reprt", (stock,))


def disc_rows(db: DB, stock: str) -> list[sqlite3.Row]:
    return db.all("SELECT * FROM dart_disc WHERE stock_code=? ORDER BY rcept_dt", (stock,))


def shares_before(db: DB, stock: str, d: str) -> sqlite3.Row | None:
    """d 전에 접수한 마지막 주식 총수."""
    return db.one("SELECT shares FROM dart_shares WHERE stock_code=? AND rcept_dt<? ORDER BY rcept_dt DESC LIMIT 1",
                  (stock, d))


def dps_before(db: DB, stock: str, d: str) -> sqlite3.Row | None:
    """d 전에 접수한 마지막 주당 배당금."""
    return db.one("SELECT dps FROM dart_div WHERE stock_code=? AND rcept_dt<? ORDER BY rcept_dt DESC LIMIT 1",
                  (stock, d))


def latest_dps(db: DB, stock: str) -> float | None:
    """마지막으로 받은 주당 배당금(없거나 0이면 None)."""
    row = db.one("SELECT dps FROM dart_div WHERE stock_code=? ORDER BY rcept_dt DESC LIMIT 1", (stock,))
    return float(row["dps"]) if row and row["dps"] else None
