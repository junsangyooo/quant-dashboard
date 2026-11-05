"""실전 운용 저장(runs · live_state · positions · run_versions · run_cash · run_equity · orders · fills · cond_orders ·
corp_actions). 실전 흐름(`run/live.py`)이 써요.

- 문장마다 자동 커밋(옮기기 전과 같은 경계). 주문은 'sending' 행을 먼저 쓰고(`add_order`) 그다음에 토스를 불러요(S9 ·
  부르는 쪽 `live.Live._send`가 그 순서를 지켜요).
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .db import DB

# ── 운용 ────────────────────────────────────────────────────────────────────


def run_with_status(db: DB, status: str) -> sqlite3.Row | None:
    """그 상태의 가장 최근 운용."""
    return db.one("SELECT * FROM runs WHERE status=? ORDER BY id DESC LIMIT 1", (status,))


def run_by_id(db: DB, rid: int) -> sqlite3.Row | None:
    return db.one("SELECT * FROM runs WHERE id=?", (rid,))


def latest_run(db: DB) -> sqlite3.Row | None:
    return db.one("SELECT * FROM runs ORDER BY id DESC LIMIT 1")


def any_unended_run(db: DB) -> bool:
    return db.one("SELECT 1 FROM runs WHERE status != 'ended' LIMIT 1") is not None


def add_run(db: DB, strategy_id: int, version_id: int, status: str, amount: float, settings: str, account_tail: str,
            started_at: str) -> int:
    return db.run("INSERT INTO runs(strategy_id,version_id,status,amount,settings,account_tail,started_at) "
                  "VALUES(?,?,?,?,?,?,?)", (strategy_id, version_id, status, amount, settings, account_tail, started_at))


def end_run(db: DB, rid: int, status: str, ended_at: str, end_kind: str) -> None:
    db.run("UPDATE runs SET status=?, ended_at=?, end_kind=? WHERE id=?", (status, ended_at, end_kind, rid))


def set_run_version(db: DB, rid: int, version_id: int) -> None:
    db.run("UPDATE runs SET version_id=? WHERE id=?", (version_id, rid))


def set_run_amount(db: DB, rid: int, amount: float) -> None:
    db.run("UPDATE runs SET amount=? WHERE id=?", (amount, rid))


def set_run_settings(db: DB, rid: int, settings: str) -> None:
    db.run("UPDATE runs SET settings=? WHERE id=?", (settings, rid))


def add_run_version(db: DB, rid: int, version_id: int, from_d: str) -> None:
    db.run("INSERT INTO run_versions(run_id,version_id,from_d) VALUES(?,?,?)", (rid, version_id, from_d))


def put_run_version(db: DB, rid: int, version_id: int, from_d: str) -> None:
    """같은 날부터의 버전이 있으면 바꿔요."""
    db.run("INSERT INTO run_versions(run_id,version_id,from_d) VALUES(?,?,?) ON CONFLICT(run_id,from_d) DO "
           "UPDATE SET version_id=excluded.version_id", (rid, version_id, from_d))


def add_cash(db: DB, rid: int, d: str, kind: str, amount: float, ref: str | None, at: str) -> None:
    """운용 현금 기록(start · buy · sell · dividend · amount_change)."""
    db.run("INSERT INTO run_cash(run_id,d,kind,amount,ref,at) VALUES(?,?,?,?,?,?)", (rid, d, kind, amount, ref, at))


def put_equity(db: DB, rid: int, d: str, equity: float, cash: float) -> None:
    db.run("INSERT INTO run_equity(run_id,d,equity,cash) VALUES(?,?,?,?) ON CONFLICT(run_id,d) DO UPDATE "
           "SET equity=excluded.equity, cash=excluded.cash", (rid, d, equity, cash))


def equity_curve(db: DB, rid: int) -> list[sqlite3.Row]:
    return db.all("SELECT d, equity FROM run_equity WHERE run_id=? ORDER BY d", (rid,))


# ── 엔진 상태 · 보유 ────────────────────────────────────────────────────────


def state_row(db: DB, rid: int) -> sqlite3.Row | None:
    return db.one("SELECT state FROM live_state WHERE run_id=?", (rid,))


def save_state(db: DB, rid: int, state: str, updated_at: str, pos: dict[str, dict[str, Any]]) -> None:
    """상태 한 덩어리를 쓰고 보유 표를 다시 채워요(문장마다 자동 커밋 · 옮기기 전과 같은 차례)."""
    db.run("INSERT INTO live_state(run_id,state,updated_at) VALUES(?,?,?) ON CONFLICT(run_id) DO UPDATE "
           "SET state=excluded.state, updated_at=excluded.updated_at", (rid, state, updated_at))
    db.run("DELETE FROM positions WHERE run_id=?", (rid,))
    for sym, p in pos.items():
        db.run("INSERT INTO positions(run_id,symbol,qty,avg_price,first_d,peak) VALUES(?,?,?,?,?,?)",
               (rid, sym, int(p["qty"]), float(p["avg"]), p.get("entry_d"), p.get("peak")))


# ── 주문 · 체결 ─────────────────────────────────────────────────────────────


def last_round(db: DB, rid: int, d: str, symbol: str, side: str) -> int:
    """그날 그 종목 · 방향의 마지막 회차(없으면 0)."""
    row = db.one_row("SELECT MAX(round) AS r FROM orders WHERE run_id=? AND d=? AND symbol=? AND side=?",
                     (rid, d, symbol, side))
    return int(row["r"] or 0)


def add_order(db: DB, rid: int, d: str, symbol: str, side: str, rnd: int, client_order_id: str,
              toss_order_id: str | None, kind: str, qty: int, price: float | None, tif: str, status: str, reason: str,
              created_at: str) -> int:
    return db.run("INSERT INTO orders(run_id,d,symbol,side,round,client_order_id,toss_order_id,kind,qty,price,tif,"
                  "status,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                  (rid, d, symbol, side, rnd, client_order_id, toss_order_id, kind, qty, price, tif, status, reason,
                   created_at))


def order(db: DB, oid: int) -> sqlite3.Row | None:
    return db.one("SELECT * FROM orders WHERE id=?", (oid,))


def run_order(db: DB, oid: int, rid: int) -> sqlite3.Row | None:
    return db.one("SELECT * FROM orders WHERE id=? AND run_id=?", (oid, rid))


def set_order_status(db: DB, oid: int, status: str) -> None:
    """상태만(바꾼 시각은 그대로)."""
    db.run("UPDATE orders SET status=? WHERE id=?", (status, oid))


def set_order_status_at(db: DB, oid: int, status: str, at: str) -> None:
    db.run("UPDATE orders SET status=?, updated_at=? WHERE id=?", (status, at, oid))


def mark_order_sent(db: DB, oid: int, toss_order_id: str, at: str) -> None:
    db.run("UPDATE orders SET toss_order_id=?, status='sent', updated_at=? WHERE id=?", (toss_order_id, at, oid))


def close_order(db: DB, oid: int, status: str, reason: str, at: str) -> None:
    """미체결 취소 · 일부 체결 마감(사유 글에 메모)."""
    db.run("UPDATE orders SET status=?, reason=?, updated_at=? WHERE id=?", (status, reason, at, oid))


def move_order(db: DB, oid: int, price: float | None, reason: str, at: str) -> None:
    """장중 다시 내기 단계(가격 · 단계)."""
    db.run("UPDATE orders SET price=?, reason=?, updated_at=? WHERE id=?", (price, reason, at, oid))


def run_toss_ids(db: DB, rid: int) -> set[Any]:
    """이 운용이 낸 주문의 토스 주문 번호(없는 것은 None)."""
    return {o["toss_order_id"] for o in db.all("SELECT toss_order_id FROM orders WHERE run_id=?", (rid,))}


def known_toss_ids(db: DB) -> set[Any]:
    """이 앱이 아는 토스 주문 번호 전부."""
    return {o["toss_order_id"] for o in db.all("SELECT toss_order_id FROM orders WHERE toss_order_id IS NOT NULL")}


def open_orders(db: DB, rid: int) -> list[sqlite3.Row]:
    """보냄 · 일부 체결."""
    return db.all("SELECT * FROM orders WHERE run_id=? AND status IN ('sent','partial')", (rid,))


def open_buys(db: DB, rid: int) -> list[sqlite3.Row]:
    return db.all("SELECT * FROM orders WHERE run_id=? AND side='buy' AND status IN ('sent','partial')", (rid,))


def open_buys_on(db: DB, rid: int, d: str) -> list[sqlite3.Row]:
    return db.all("SELECT * FROM orders WHERE run_id=? AND d=? AND side='buy' AND status IN ('sent','partial')",
                  (rid, d))


def open_intraday(db: DB, rid: int) -> list[sqlite3.Row]:
    """장중 매도 길(보호 · 익절 · 전부 팔기)의 미체결."""
    return db.all("SELECT * FROM orders WHERE run_id=? AND kind IN ('intraday_protect','intraday_take',"
                  "'stop_all') AND status IN ('sent','partial')", (rid,))


def has_pending_sell(db: DB, rid: int, symbol: str) -> bool:
    """그 종목의 매도가 이미 나가 있나(보내는 중 포함)."""
    return db.one("SELECT 1 FROM orders WHERE run_id=? AND symbol=? AND side='sell' AND status IN "
                  "('sent','partial','sending')", (rid, symbol)) is not None


def add_fill(db: DB, oid: int, qty: int, price: float, commission: float, tax: float, filled_at: str,
             note: str | None) -> None:
    db.run("INSERT INTO fills(order_id,qty,price,commission,tax,filled_at,note) VALUES(?,?,?,?,?,?,?)",
           (oid, qty, price, commission, tax, filled_at, note))


def filled_qty(db: DB, oid: int) -> int:
    return int(db.one_row("SELECT IFNULL(SUM(qty),0) AS q FROM fills WHERE order_id=?", (oid,))["q"])


def recent_fills(db: DB, rid: int) -> list[sqlite3.Row]:
    return db.all("SELECT o.d, o.symbol, o.side, f.qty, f.price FROM fills f JOIN orders o ON o.id=f.order_id "
                  "WHERE o.run_id=? ORDER BY f.id DESC LIMIT 5", (rid,))


# ── 조건주문 ────────────────────────────────────────────────────────────────


def watching_conds(db: DB, rid: int, symbol: str) -> list[sqlite3.Row]:
    return db.all("SELECT * FROM cond_orders WHERE run_id=? AND symbol=? AND status='watching'", (rid, symbol))


def watching_cond(db: DB, rid: int, symbol: str) -> sqlite3.Row | None:
    return db.one("SELECT * FROM cond_orders WHERE run_id=? AND symbol=? AND status='watching'", (rid, symbol))


def live_conds(db: DB, rid: int) -> list[sqlite3.Row]:
    """감시 중 · 발동한 조건주문."""
    return db.all("SELECT * FROM cond_orders WHERE run_id=? AND status IN ('watching','triggered')", (rid,))


def cond(db: DB, cid: int) -> sqlite3.Row | None:
    return db.one("SELECT * FROM cond_orders WHERE id=?", (cid,))


def add_cond(db: DB, rid: int, symbol: str, toss_cond_id: str, kind: str, qty: int, stop_trigger: float | None,
             take_trigger: float | None, expire: str, status: str, created_at: str) -> None:
    db.run("INSERT INTO cond_orders(run_id,symbol,toss_cond_id,kind,qty,stop_trigger,take_trigger,expire,"
           "status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
           (rid, symbol, toss_cond_id, kind, qty, stop_trigger, take_trigger, expire, status, created_at))


def set_cond_status(db: DB, cid: int, status: str) -> None:
    db.run("UPDATE cond_orders SET status=? WHERE id=?", (status, cid))


def trigger_cond(db: DB, cid: int, at: str) -> None:
    db.run("UPDATE cond_orders SET status='triggered', triggered_at=? WHERE id=?", (at, cid))


# ── 기업 행동 ───────────────────────────────────────────────────────────────


def add_corp_action(db: DB, rid: int, symbol: str, kind: str, ratio: float, detected_at: str, data: str) -> None:
    db.run("INSERT INTO corp_actions(run_id,symbol,kind,ratio,detected_at,data) VALUES(?,?,?,?,?,?)",
           (rid, symbol, kind, ratio, detected_at, data))


def pending_corp_action(db: DB, rid: int, symbol: str) -> sqlite3.Row | None:
    """아직 맞추지 않은 마지막 권리 변동."""
    return db.one("SELECT * FROM corp_actions WHERE run_id=? AND symbol=? AND applied_at IS NULL "
                  "ORDER BY id DESC LIMIT 1", (rid, symbol))


def apply_corp_action(db: DB, cid: int, at: str) -> None:
    db.run("UPDATE corp_actions SET applied_at=? WHERE id=?", (at, cid))
