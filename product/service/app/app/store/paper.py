"""모의투자 v2 저장(paper_runs · paper_trades · paper_equity · paper_judgements). `run/paper.py`가 써요.

상태 값(`v2-running` · `v2-ended`)은 부르는 쪽이 넘겨요(MVP 모의투자와 섞이지 않게 정한 값 · `run/paper.py`).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .db import DB


def paper_run(db: DB, rid: int, statuses: tuple[str, str]) -> sqlite3.Row | None:
    return db.one("SELECT * FROM paper_runs WHERE id=? AND status IN (?,?)", (rid, *statuses))


def paper_run_for(db: DB, strategy_id: int, status: str) -> sqlite3.Row | None:
    """그 전략의 그 상태 모의투자(버전을 거쳐 찾음)."""
    return db.one("SELECT r.* FROM paper_runs r JOIN versions v ON v.id=r.version_id "
                  "WHERE v.strategy_id=? AND r.status=?", (strategy_id, status))


def paper_runs_with(db: DB, status: str) -> list[sqlite3.Row]:
    return db.all("SELECT * FROM paper_runs WHERE status=? ORDER BY id", (status,))


def paper_run_ids(db: DB, statuses: tuple[str, str]) -> list[sqlite3.Row]:
    """새것 먼저."""
    return db.all("SELECT id FROM paper_runs WHERE status IN (?,?) ORDER BY id DESC", statuses)


def add_paper_run(db: DB, version_id: int, cash0: float, state: str, status: str, started_at: str,
                  last_date: str | None) -> int:
    return db.run("INSERT INTO paper_runs(version_id,cash0,state,status,started_at,last_date) VALUES(?,?,?,?,?,?)",
                  (version_id, cash0, state, status, started_at, last_date))


def set_paper_last_date(db: DB, rid: int, last_date: str) -> None:
    db.run("UPDATE paper_runs SET last_date=? WHERE id=?", (last_date, rid))


def end_paper_run(db: DB, rid: int, status: str, ended_at: str) -> None:
    db.run("UPDATE paper_runs SET status=?, ended_at=? WHERE id=?", (status, ended_at, rid))


def save_paper_state(db: DB, rid: int, state: str, last_date: str) -> None:
    db.run("UPDATE paper_runs SET state=?, last_date=? WHERE id=?", (state, last_date, rid))


def add_paper_trade(db: DB, rid: int, d: str, symbol: str, side: str, qty: int, price: float, amount: float,
                    cost: float, pnl: Any, reason: str) -> None:
    db.run("INSERT INTO paper_trades(run_id,d,symbol,side,qty,price,amount,cost,pnl,reason) "
           "VALUES(?,?,?,?,?,?,?,?,?,?)", (rid, d, symbol, side, qty, price, amount, cost, pnl, reason))


def paper_trades(db: DB, rid: int) -> list[sqlite3.Row]:
    return db.all("SELECT * FROM paper_trades WHERE run_id=? ORDER BY id", (rid,))


def add_paper_judgement(db: DB, rid: int, d: str, made_at: str, plans: str, how: str) -> None:
    db.run("INSERT INTO paper_judgements(run_id,d,made_at,plans,how) VALUES(?,?,?,?,?)", (rid, d, made_at, plans, how))


def put_paper_equity(db: DB, rid: int, d: str, equity: float, cash: float) -> None:
    db.run("INSERT INTO paper_equity(run_id,d,equity,cash) VALUES(?,?,?,?) "
           "ON CONFLICT(run_id,d) DO UPDATE SET equity=excluded.equity, cash=excluded.cash", (rid, d, equity, cash))


def paper_curve(db: DB, rid: int) -> list[sqlite3.Row]:
    return db.all("SELECT d, equity FROM paper_equity WHERE run_id=? ORDER BY d", (rid,))
