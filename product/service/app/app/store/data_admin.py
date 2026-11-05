"""데이터 관리 저장 쪽(백업 파일 · 백업 확인 · 현황 셈 · 기록 내보내기 · 왕복 시험용 사진). `services/data_admin.py`가 써요.

백업 파일은 sqlite 한 장에서 API 키 · 키 파일 감싸기 · 텔레그램 연결 · 하루 한 번 표시를 뺀 것이에요(V2-53).
"""

from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from .db import DB, SCHEMA_VERSION

# 백업 파일 확인 결과(`backup_verdict`)
BACKUP_OK, NOT_A_BACKUP, NEWER_BACKUP = "ok", "not_backup", "newer"


def backup_without_keys(db: DB) -> bytes:
    """지금 파일의 사진에서 비밀 값 · 키 파일 감싸기 · `tg.` · `sched.` 메타를 지운 한 장."""
    with tempfile.TemporaryDirectory(dir=db.path.parent) as d:
        dst = Path(d) / "b.db"
        db.backup_to(dst)
        con = sqlite3.connect(dst)
        try:
            con.execute("DELETE FROM secrets")
            con.execute("DELETE FROM owner_keyfile")
            con.execute("DELETE FROM meta WHERE k LIKE 'tg.%' OR k LIKE 'sched.%'")
            con.commit()
            con.execute("VACUUM")
        finally:
            con.close()
        return dst.read_bytes()


def backup_verdict(path: Path) -> str:
    """이 앱이 만든 파일인지(읽기 전용으로 열어 봄): sqlite · 무결성 · 계정 표 · 구조 판.
    `BACKUP_OK` · `NOT_A_BACKUP` · `NEWER_BACKUP`(앱보다 새 판)."""
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return NOT_A_BACKUP
    try:
        if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            return NOT_A_BACKUP
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not {"owner", "meta", "strategies", "versions"} <= tables:
            return NOT_A_BACKUP
        if con.execute("SELECT COUNT(*) FROM owner").fetchone()[0] != 1:
            return NOT_A_BACKUP
        if int(con.execute("PRAGMA user_version").fetchone()[0]) > SCHEMA_VERSION:
            return NEWER_BACKUP
    except sqlite3.DatabaseError:
        return NOT_A_BACKUP
    finally:
        con.close()
    return BACKUP_OK


def sched_meta_keys(db: DB) -> list[str]:
    """하루 한 번 표시(`sched.`) 메타 키."""
    return [r["k"] for r in db.all("SELECT k FROM meta WHERE k LIKE 'sched.%'")]


# ── 현황 ────────────────────────────────────────────────────────────────────


def bar_summary(db: DB) -> sqlite3.Row:
    """받아 둔 일봉: 종목 수(`n`) · 첫 날(`a`) · 끝 날(`b`)."""
    return db.one_row("SELECT COUNT(DISTINCT symbol) AS n, MIN(d) AS a, MAX(d) AS b FROM bars")


def last_bar_fetch(db: DB) -> sqlite3.Row:
    """마지막으로 일봉을 받은 때(`t`)."""
    return db.one_row("SELECT MAX(fetched_at) AS t FROM bar_meta")


def row_count(db: DB, table: str) -> int:
    """표의 행 수(표 이름은 부르는 쪽이 정한 상수)."""
    return int(db.one_row(f"SELECT COUNT(*) AS n FROM {table}")["n"])


# ── 기록 내보내기 · 왕복 시험용 사진 ──────────────────────────────────────


def history_orders(db: DB, run_id: int | None) -> list[sqlite3.Row]:
    """주문(종목 이름 함께 · 날짜 · id 순). run_id가 없으면(0 포함) 모든 운용."""
    where, args = ("WHERE o.run_id=?", (run_id,)) if run_id else ("", ())
    return db.all(f"SELECT o.*, s.name AS sname FROM orders o LEFT JOIN stock_info s ON s.symbol=o.symbol {where} "
                  "ORDER BY o.d, o.id", args)


def all_fills(db: DB) -> list[sqlite3.Row]:
    return db.all("SELECT * FROM fills ORDER BY filled_at, id")


def table_rows(db: DB, table: str) -> list[dict[str, Any]]:
    """표 전체(rowid 순 · 표 이름은 부르는 쪽이 정한 상수)."""
    return [dict(r) for r in db.all(f"SELECT * FROM {table} ORDER BY rowid")]


def secret_names(db: DB) -> list[str]:
    return [r["name"] for r in db.all("SELECT name FROM secrets ORDER BY name")]


def meta_keys(db: DB) -> list[str]:
    return [r["k"] for r in db.all("SELECT k FROM meta")]
