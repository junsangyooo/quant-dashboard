"""데이터 구조 v2(TASKS T-13). v1 파일 옮기기 시험 3건은 P1-02 ①에서 지웠어요(설치본이 없어 v1 자료가 없음)."""

from __future__ import annotations

from pathlib import Path

from app.store.db import DB, SCHEMA_VERSION, body_format

V2_TABLES = {
    "stock_info", "stock_warnings", "sectors", "sector_members", "investor",
    "dart_corp", "dart_jobs", "dart_quota", "dart_fin", "dart_disc", "dart_shares", "dart_div",
    "runs", "run_versions", "run_cash", "positions", "run_equity", "orders", "fills", "cond_orders",
    "todos", "alerts", "corp_actions",
}
KEEP = ["owner", "secrets", "strategies", "versions", "paper_runs", "paper_trades", "paper_equity",
        "paper_judgements", "bars"]


def test_new_file_is_v2(tmp_path: Path) -> None:
    db = DB(tmp_path / "new.db")
    tables = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert V2_TABLES <= tables and set(KEEP) <= tables
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 2
    assert db.migrated_from is None
    assert not (tmp_path / "new.db.v1-backup").exists()


def test_old_or_unknown_schema_version_is_an_error(tmp_path: Path) -> None:
    """옛 v1 표(버전 0 + owner 표)나 모르는 번호(1)는 옮기지 않고 오류예요(P1-02 ① · 옮기기 코드는 지움)."""
    import sqlite3

    import pytest

    old = tmp_path / "old.db"
    con = sqlite3.connect(old)
    con.execute("CREATE TABLE owner(id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    with pytest.raises(RuntimeError, match="알 수 없는 데이터 구조 버전이에요 · 0"):
        DB(old)
    assert not (tmp_path / "old.db.v1-backup").exists()  # 복사본도 만들지 않아요
    one = tmp_path / "one.db"
    con = sqlite3.connect(one)
    con.execute("PRAGMA user_version=1")
    con.close()
    with pytest.raises(RuntimeError, match="알 수 없는 데이터 구조 버전이에요 · 1"):
        DB(one)


def test_body_format() -> None:
    assert body_format('{"slots": {}}') == "slots"
    assert body_format('{"graph": {"nodes": []}}') == "graph"
    assert body_format('{"graph": {"blocks": []}}') == "blocks"
    assert body_format("nope") == "unknown"
