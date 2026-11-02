"""데이터 구조 v2 · 옛 데이터 옮기기(TASKS T-13).

`tests/fixtures/v1_app.db`는 v1 MVP 앱(구조 v1 · 2026-11-02)을 API로 돌려 만든 데이터 파일이에요:
계정(비밀번호 `PASSWORD`) · 토스 키(지어낸 값) · 전략 2개(일곱 칸 본문 1 · 그래프 본문 1, 버전 3개) ·
모의투자 1건(22거래일 확인 · 체결 7건).
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import DB, SCHEMA_VERSION, body_format
from app.main import create_app
from tests.conftest import CsrfClient, PASSWORD, FakeBars, FakeIp, FakeToss

FIX = Path(__file__).resolve().parent / "fixtures" / "v1_app.db"
V2_TABLES = {
    "stock_info", "stock_warnings", "sectors", "sector_members", "investor",
    "dart_corp", "dart_jobs", "dart_quota", "dart_fin", "dart_disc", "dart_shares", "dart_div",
    "runs", "run_versions", "run_cash", "positions", "run_equity", "orders", "fills", "cond_orders",
    "todos", "alerts", "corp_actions",
}
KEEP = ["owner", "secrets", "strategies", "versions", "paper_runs", "paper_trades", "paper_equity",
        "paper_judgements", "bars"]


def _dump(path: Path, table: str) -> list[tuple]:  # type: ignore[type-arg]
    con = sqlite3.connect(path)
    try:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})") if r[1] not in ("format",)]
        return con.execute(f"SELECT {','.join(cols)} FROM {table} ORDER BY rowid").fetchall()
    finally:
        con.close()


def test_new_file_is_v2(tmp_path: Path) -> None:
    db = DB(tmp_path / "new.db")
    tables = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert V2_TABLES <= tables and set(KEEP) <= tables
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION == 2
    assert db.migrated_from is None
    assert not (tmp_path / "new.db.v1-backup").exists()


def test_v1_file_moves_to_v2_keeping_everything(tmp_path: Path) -> None:
    path = tmp_path / "app.db"
    shutil.copy(FIX, path)
    before = {t: _dump(path, t) for t in KEEP}
    assert len(before["strategies"]) == 2 and len(before["versions"]) == 3 and len(before["paper_trades"]) == 7
    db = DB(path)
    assert db.migrated_from == 0
    assert db.conn.execute("PRAGMA user_version").fetchone()[0] == 2
    db.conn.close()
    # 같은 행 그대로(전략 · 버전 본문 · 모의투자 기록 · 계정 · 키 · 일봉)
    for t in KEEP:
        assert _dump(path, t) == before[t], t
    con = sqlite3.connect(path)
    formats = con.execute("SELECT format FROM versions ORDER BY id").fetchall()
    assert [f[0] for f in formats] == ["graph", "graph", "graph"]  # v1 앱은 일곱 칸 본문도 그래프로 저장했어요
    cols = [r[1] for r in con.execute("PRAGMA table_info(bar_meta)")]
    assert "source" in cols and "yahoo" not in cols
    con.close()
    # 옮기기 전 파일을 복사해 둬요
    backup = tmp_path / "app.db.v1-backup"
    assert backup.exists()
    assert sqlite3.connect(backup).execute("PRAGMA user_version").fetchone()[0] == 0
    # 다시 열어도 그대로(한 번만 옮겨요)
    again = DB(path)
    assert again.migrated_from is None


def test_v1_file_opens_in_the_app(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    shutil.copy(FIX, data / "app.db")
    app = create_app(data, bars_source=FakeBars(), toss_transport=lambda: FakeToss(), ip_fetch=FakeIp(),
                     scrypt_n=2**12, scheduler=False)
    with CsrfClient(app) as c:
        r = c.post("/api/login", json={"password": PASSWORD})
        assert r.status_code == 200, r.text
        names = sorted(s["name"] for s in c.get("/api/strategies").json()["strategies"])
        assert names == ["옛 일곱 칸 전략", "추세 그래프 전략"]
        # 키도 그대로 풀려요(지어낸 값 · 화면에는 끝자리만)
        conn = c.get("/api/connect").json()
        assert conn["toss"]["saved"] is True
        # 새 버전은 꼴과 함께 저장돼요
        sid = next(s["id"] for s in c.get("/api/strategies").json()["strategies"] if s["name"] == "추세 그래프 전략")
        body = c.get(f"/api/strategies/{sid}").json()["body"]
        r = c.post(f"/api/strategies/{sid}/versions", json={"body": body})
        assert r.status_code == 200
    row = sqlite3.connect(data / "app.db").execute("SELECT format FROM versions ORDER BY id DESC LIMIT 1").fetchone()
    assert row[0] == "graph"


def test_body_format() -> None:
    assert body_format('{"slots": {}}') == "slots"
    assert body_format('{"graph": {"nodes": []}}') == "graph"
    assert body_format('{"graph": {"blocks": []}}') == "blocks"
    assert body_format("nope") == "unknown"


def test_v1_slots_body_is_marked(tmp_path: Path) -> None:
    """일곱 칸 본문이 그대로 저장된 더 옛 버전도 꼴을 적어 둬요(읽을 때 v3로 바꿔요 · T-22)."""
    path = tmp_path / "app.db"
    shutil.copy(FIX, path)
    con = sqlite3.connect(path)
    con.execute("INSERT INTO versions(strategy_id,no,body,problems,created_at) VALUES(1,9,?,0,'t')",
                ('{"name": "옛", "template": "event", "slots": {}}',))
    con.commit()
    con.close()
    DB(path).conn.close()
    con = sqlite3.connect(path)
    assert con.execute("SELECT format FROM versions WHERE no=9").fetchone()[0] == "slots"
