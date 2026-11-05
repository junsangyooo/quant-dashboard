"""일봉 캐시 · 종목 정보(bars · bar_meta · stock_info). 일봉 캐시는 `run.data.Market`이, 종목 정보는 조립이 써요.

장 달력은 `meta` 표(`cal.날짜`)에 있어요(`DB.get_meta` · `run.data.Calendar`).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .db import DB


def bar_meta(db: DB, symbol: str) -> sqlite3.Row | None:
    """받아 둔 범위 · 받은 때."""
    return db.one("SELECT * FROM bar_meta WHERE symbol=?", (symbol,))


def bar_range(db: DB, symbol: str) -> sqlite3.Row | None:
    return db.one("SELECT from_d, to_d FROM bar_meta WHERE symbol=?", (symbol,))


def put_bars(db: DB, symbol: str, bars: list[dict[str, Any]]) -> None:
    """한 트랜잭션으로 넣거나 바꿔요(`DB.many`)."""
    db.many(
        "INSERT INTO bars(symbol,d,o,h,l,c,v) VALUES(?,?,?,?,?,?,?) "
        "ON CONFLICT(symbol,d) DO UPDATE SET o=excluded.o,h=excluded.h,l=excluded.l,"
        "c=excluded.c,v=excluded.v",
        [(symbol, b["d"], b["o"], b["h"], b["l"], b["c"], b["v"]) for b in bars],
    )


def put_bar_meta(db: DB, symbol: str, source: str, from_d: str, to_d: str, fetched_at: float) -> None:
    db.run(
        "INSERT INTO bar_meta(symbol,source,from_d,to_d,fetched_at) VALUES(?,?,?,?,?) "
        "ON CONFLICT(symbol) DO UPDATE SET source=excluded.source, from_d=excluded.from_d,"
        "to_d=excluded.to_d, fetched_at=excluded.fetched_at",
        (symbol, source, from_d, to_d, fetched_at),
    )


def bars_between(db: DB, symbol: str, start: str, end: str) -> list[dict[str, Any]]:
    """start ~ end(그날 포함 · 날짜 순)."""
    rows = db.all("SELECT d,o,h,l,c,v FROM bars WHERE symbol=? AND d>=? AND d<=? ORDER BY d", (symbol, start, end))
    return [dict(r) for r in rows]


def stock_info_map(db: DB) -> dict[str, dict[str, Any]]:
    """종목 코드 → 종목 정보 한 줄."""
    return {r["symbol"]: dict(r) for r in db.all("SELECT * FROM stock_info")}
