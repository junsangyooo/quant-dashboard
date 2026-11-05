"""데이터 관리(T-53 · SPEC 7-6 V2-53 · FEAT-BACKUP-EXPORT): 백업 파일 · 복원 · 앱 데이터 삭제 · 기록 CSV · 현황.

- 백업 파일은 sqlite 한 장이에요(전략 · 기록 · 운용 · 설정 · 계정). API 키 · 텔레그램 연결은 빼요: 복원한 뒤 키를
  다시 입력해요(V2-53). 키 파일 감싸기도 빼서, 복원 뒤 비밀번호로 들어오면 그 컴퓨터 키 파일로 다시 감싸요.
- 복원은 '새 매수 멈춤'으로 시작해요(R-L10). 복원 · 삭제는 비밀번호(SPEC 7-4), 실전 운용 중 삭제는 거절.
"""

from __future__ import annotations

import csv
import io
import json
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..store import data_admin as admin_store
from ..store import runs as run_store
from ..store.db import DB

MAX_BACKUP = 512 * 1024 * 1024
BACKUP_PREFIX = "quant-backup"
RUNNING_LIVE = "실전 운용 중에는 삭제할 수 없어요 · 먼저 운용을 끝내요"
RESTORE_LINE = "복원하면 새 매수를 멈춘 채 시작해요 · 토스 주문 내역과 맞는지 확인한 뒤 다시 켜요"
NOT_BACKUP = "이 앱의 백업 파일이 아니에요"
CSV_COLUMNS = ["날짜", "종목", "구분", "가격", "수량", "손익", "상태", "이유"]  # V2-12 주문 내역 열
SIDE = {"buy": "매수", "sell": "매도"}
STATUS = {"filled": "체결", "partial": "일부 체결", "failed": "실패", "rejected": "실패", "canceled": "취소",
          "cancelled": "취소", "open": "미체결", "sent": "미체결", "unknown": "결과 모름", "skipped": "매수 안 함"}


class DataError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def live_running(db: DB) -> bool:
    return run_store.any_unended_run(db)


def backup_bytes(db: DB) -> bytes:
    """백업 파일: 전략 · 기록 · 설정. API 키(비밀 값)와 키 파일 감싸기는 빼요(V2-53 'API 키는 들어 있지 않아요')."""
    return admin_store.backup_without_keys(db)


def backup_name(today: str) -> str:
    return f"{BACKUP_PREFIX}-{today.replace('-', '')}.db"


def check_backup(path: Path) -> None:
    """이 앱이 만든 파일인지: sqlite · 무결성 · 계정 표 · 우리 구조 판(앱보다 새 판이면 거절)."""
    verdict = admin_store.backup_verdict(path)
    if verdict == admin_store.NEWER_BACKUP:
        raise DataError("앱보다 새 버전에서 만든 백업이에요 · 앱을 먼저 업데이트해요")
    if verdict != admin_store.BACKUP_OK:
        raise DataError(NOT_BACKUP)


def restore(db: DB, raw: bytes, *, now_iso: str) -> None:
    if not raw or len(raw) > MAX_BACKUP or not raw.startswith(b"SQLite format 3\x00"):
        raise DataError(NOT_BACKUP)
    with tempfile.TemporaryDirectory(dir=db.path.parent) as d:
        src = Path(d) / "restore.db"
        src.write_bytes(raw)
        check_backup(src)
        db.replace_with(src)
    # R-L10: 복원은 새 매수 멈춤으로 시작
    db.set_meta("live.new_buys_paused", "1")
    db.set_meta("live.new_buys_paused_by", "restore")
    db.set_meta("data.restored_at", now_iso)
    for k in admin_store.sched_meta_keys(db):
        db.set_meta(k, None)  # 하루 한 번 표시는 이 컴퓨터 몫


def delete_all(db: DB) -> None:
    if live_running(db):
        raise DataError(RUNNING_LIVE, 409)
    db.replace_with(None, keep=False)


def overview(db: DB) -> dict[str, Any]:
    bars = admin_store.bar_summary(db)
    last = admin_store.last_bar_fetch(db)

    def count(table: str) -> int:
        return admin_store.row_count(db, table)

    return {
        "bars": {"symbols": int(bars["n"] or 0), "from": bars["a"], "to": bars["b"], "fetched_at": last["t"]},
        "dart": {"financials": count("dart_fin"), "disclosures": count("dart_disc"), "shares": count("dart_shares")},
        "strategies": count("strategies"),
        "live_running": live_running(db),
        "restore_line": RESTORE_LINE,
    }


def history_rows(db: DB, run_id: int | None = None) -> list[dict[str, Any]]:
    """기록 주문 내역(V2-12): 날짜 · 종목 · 구분 · 가격 · 수량 · 손익 · 상태 · 이유. 손익은 매도 체결만(평균 단가 기준)."""
    orders = admin_store.history_orders(db, run_id)
    fills: dict[int, list[Any]] = defaultdict(list)
    for f in admin_store.all_fills(db):
        fills[int(f["order_id"])].append(f)
    held: dict[tuple[int, str], tuple[int, float]] = {}  # (운용, 종목) → (수량, 평균 단가 · 비용 포함)
    out = []
    for o in orders:
        fs = fills.get(int(o["id"]), [])
        qty = sum(int(f["qty"]) for f in fs)
        price = (sum(int(f["qty"]) * float(f["price"]) for f in fs) / qty) if qty else (float(o["price"]) if o["price"] else None)
        cost = sum(float(f["commission"]) + float(f["tax"]) for f in fs)
        key = (int(o["run_id"]), str(o["symbol"]))
        pnl = None
        if qty and o["side"] == "buy":
            q0, a0 = held.get(key, (0, 0.0))
            held[key] = (q0 + qty, (q0 * a0 + qty * float(price or 0) + cost) / (q0 + qty))
        elif qty and o["side"] == "sell":
            q0, a0 = held.get(key, (0, 0.0))
            pnl = round(qty * (float(price or 0) - a0) - cost)
            held[key] = (max(0, q0 - qty), a0)
        out.append({
            "d": o["d"], "symbol": o["symbol"], "name": o["sname"] or o["symbol"], "side": SIDE.get(o["side"], o["side"]),
            "price": round(price) if price is not None else None, "qty": qty or int(o["qty"]), "pnl": pnl,
            "status": STATUS.get(o["status"], o["status"]), "reason": o["reason"] or "",
        })
    return out


def history_csv(db: DB, run_id: int | None = None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(CSV_COLUMNS)
    for r in history_rows(db, run_id):
        w.writerow([r["d"], f"{r['name']}({r['symbol']})" if r["name"] != r["symbol"] else r["symbol"], r["side"],
                    "" if r["price"] is None else r["price"], r["qty"], "" if r["pnl"] is None else r["pnl"],
                    r["status"], r["reason"]])
    return "﻿" + buf.getvalue()  # 엑셀이 한글을 바로 읽도록 BOM


def snapshot(db: DB) -> dict[str, Any]:
    """왕복 시험용: 전략 · 기록 · 운용을 한 덩어리로."""
    tables = ["strategies", "versions", "runs", "run_versions", "run_cash", "positions", "run_equity", "orders",
              "fills", "cond_orders", "todos", "paper_runs", "backtest_runs"]
    return {t: admin_store.table_rows(db, t) for t in tables} | {
        "secrets": admin_store.secret_names(db),
        "meta_sample": json.dumps(sorted(admin_store.meta_keys(db))),
    }
