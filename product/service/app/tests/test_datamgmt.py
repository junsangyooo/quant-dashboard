"""T-53 데이터 관리: 백업 → 삭제 → 복원 왕복 · 운용 중 삭제 거절 · CSV 열 = V2-12 · 업데이트 단계."""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app import datamgmt as dm
from app import updates
from app.db import DB
from app.main import create_app
from app.domain.markets.kr import KST
from tests.conftest import PASSWORD, CsrfClient, FakeToss, confirm, setup_owner
from tests.fake_telegram import MY_CHAT, TOKEN, FakeTelegram
from tests.test_blocks import B, G, R

NOW = datetime(2026, 11, 2, 17, 0, tzinfo=KST)
PW2 = "another pass 77"


def boot(tmp_path: Path, **kw: Any) -> CsrfClient:
    app = create_app(tmp_path / "data", scrypt_n=2**12, scheduler=False, now=lambda: NOW,
                     toss_transport=lambda: FakeToss(), **kw)
    c = CsrfClient(app)
    c.app_ref = app  # type: ignore[attr-defined]
    return c


def strategy_body(name: str) -> dict[str, Any]:
    g = G([B("u", "universe", [R("manual_list", value=["005930"])]), B("s", "signal", [R("price", "gte", 1)]),
           B("k", "select", [R("top_n", value=1)]), B("b", "buy"), B("x", "sell", [R("max_hold", value=5)]),
           B("w", "weight")], ("u", "s"), ("s", "k"), ("k", "b"), ("b", "x"), ("w", "b"))
    return {"name": name, "graph": g}


def fill_history(db: DB, status: str = "ended") -> int:
    sid = int(db.one("SELECT id FROM strategies LIMIT 1")["id"])
    vid = int(db.one("SELECT id FROM versions WHERE strategy_id=? LIMIT 1", (sid,))["id"])
    db.run("INSERT INTO stock_info(symbol, name) VALUES('005930','삼성전자') ON CONFLICT DO NOTHING")
    rid = db.run("INSERT INTO runs(strategy_id, version_id, status, amount, settings, account_tail, started_at, "
                 "ended_at, end_kind) VALUES(?,?,?,?,?,?,?,?,?)",
                 (sid, vid, status, 10_000_000, "{}", "1234", "2026-10-01T20:10:00+09:00", None, None))
    o1 = db.run("INSERT INTO orders(run_id, d, symbol, side, round, client_order_id, kind, qty, price, status, reason, "
                "created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, "2026-10-02", "005930", "buy", 1, f"c-{rid}-1", "limit", 10, 77_000, "filled", "신호", "t"))
    db.run("INSERT INTO fills(order_id, qty, price, commission, tax, filled_at) VALUES(?,?,?,?,?,?)",
           (o1, 10, 70_000, 100, 0, "2026-10-02T09:00:01+09:00"))
    o2 = db.run("INSERT INTO orders(run_id, d, symbol, side, round, client_order_id, kind, qty, price, status, reason, "
                "created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (rid, "2026-10-08", "005930", "sell", 1, f"c-{rid}-2", "limit", 10, 63_000, "filled", "손절 −7%", "t"))
    db.run("INSERT INTO fills(order_id, qty, price, commission, tax, filled_at) VALUES(?,?,?,?,?,?)",
           (o2, 10, 72_000, 100, 1_296, "2026-10-08T09:00:01+09:00"))
    db.run("INSERT INTO orders(run_id, d, symbol, side, round, client_order_id, kind, qty, price, status, reason, "
           "created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
           (rid, "2026-10-09", "005930", "buy", 1, f"c-{rid}-3", "limit", 5, 75_000, "failed", "잔고 부족", "t"))
    return rid


def seeded(tmp_path: Path, status: str = "ended") -> CsrfClient:
    c = boot(tmp_path)
    setup_owner(c)
    c.put("/api/connect/toss", json={"client_id": FakeToss.CLIENT_ID, "client_secret": FakeToss.SECRET,
                                     "account_no": "12345671234"})
    for n in ("돌파", "배당"):
        assert c.post("/api/v2/strategies", json={"body": strategy_body(n)}).status_code == 200
    fill_history(c.app_ref.state.db, status)  # type: ignore[attr-defined]
    return c


def test_backup_delete_restore_roundtrip(tmp_path: Path) -> None:
    c = seeded(tmp_path)
    db: DB = c.app_ref.state.db  # type: ignore[attr-defined]
    before = dm.snapshot(db)
    assert before["strategies"] and before["orders"] and before["runs"]

    r = c.get("/api/data/backup")
    assert r.status_code == 200 and r.content.startswith(b"SQLite format 3\x00")
    assert r.headers["content-disposition"] == 'attachment; filename="quant-backup-20261102.db"'
    raw = r.content
    assert FakeToss.SECRET.encode() not in raw
    (tmp_path / "b.db").write_bytes(raw)
    con = sqlite3.connect(tmp_path / "b.db")
    assert con.execute("SELECT COUNT(*) FROM secrets").fetchone()[0] == 0  # API 키는 들어 있지 않아요(V2-53)
    con.close()

    # 삭제(비밀번호) → 처음 화면
    assert c.delete("/api/data").status_code == 403
    r = c.delete("/api/data", headers=confirm(c, "data_delete"))
    assert r.status_code == 200
    assert c.get("/api/state").json()["setup"] is False
    assert all(not v for k, v in dm.snapshot(db).items() if k != "meta_sample")
    assert not (tmp_path / "data" / "app.db.before-replace").exists()

    # 새 계정 → 복원(비밀번호) → 다시 로그인은 백업의 비밀번호로
    c.post("/api/setup", json={"password": PW2, "password2": PW2, "adult": True, "terms": True})
    assert c.post("/api/data/restore", content=raw).status_code == 403
    r = c.post("/api/data/restore", content=raw,
               headers={**confirm(c, "restore", PW2), "content-type": "application/octet-stream"})
    assert r.status_code == 200 and r.json()["line"] == dm.RESTORE_LINE
    assert c.get("/api/state").json()["logged_in"] is False
    assert c.post("/api/login", json={"password": PW2}).status_code == 401
    assert c.post("/api/login", json={"password": PASSWORD}).status_code == 200

    after = dm.snapshot(db)
    for k in ("strategies", "versions", "runs", "orders", "fills", "paper_runs"):
        assert after[k] == before[k], k
    assert after["secrets"] == []
    # 복원은 새 매수 멈춤으로 시작(R-L10)
    assert db.get_meta("live.new_buys_paused") == "1" and db.get_meta("live.new_buys_paused_by") == "restore"
    # API 키는 다시 입력해요
    assert c.get("/api/connect").json()["toss"]["saved"] is False


def test_delete_refused_while_live_running(tmp_path: Path) -> None:
    c = seeded(tmp_path, status="running")
    r = c.delete("/api/data", headers=confirm(c, "data_delete"))
    assert r.status_code == 409 and r.json()["error"] == "실전 운용 중에는 삭제할 수 없어요 · 먼저 운용을 끝내요"
    r = c.delete("/api/data")  # 비밀번호 창보다 먼저
    assert r.status_code == 409
    assert c.get("/api/state").json()["setup"] is True
    assert c.app_ref.state.db.one("SELECT COUNT(*) AS n FROM strategies")["n"] == 2  # type: ignore[attr-defined]


def test_restore_rejects_other_files(tmp_path: Path) -> None:
    c = boot(tmp_path)
    setup_owner(c)
    h = lambda: confirm(c, "restore")  # noqa: E731
    for raw in (b"", b"hello", b"SQLite format 3\x00" + b"\x00" * 100):
        assert c.post("/api/data/restore", content=raw, headers=h()).json()["error"] == dm.NOT_BACKUP
    other = tmp_path / "other.db"
    con = sqlite3.connect(other)
    con.execute("CREATE TABLE t(x)")
    con.commit()
    con.close()
    assert c.post("/api/data/restore", content=other.read_bytes(), headers=h()).json()["error"] == dm.NOT_BACKUP
    # 앱보다 새 구조
    newer = tmp_path / "newer.db"
    DB(newer).backup_to(tmp_path / "x.db")
    con = sqlite3.connect(tmp_path / "x.db")
    con.execute("INSERT INTO owner VALUES(1,1,x'00',x'00',x'00',x'00',0,0,1,'t','t')")
    con.execute("PRAGMA user_version=99")
    con.commit()
    con.close()
    r = c.post("/api/data/restore", content=(tmp_path / "x.db").read_bytes(), headers=h())
    assert r.status_code == 400 and "새 버전" in r.json()["error"]
    assert c.get("/api/state").json()["logged_in"] is True  # 아무것도 바뀌지 않았어요


def test_history_csv_columns_match_v2_12(tmp_path: Path) -> None:
    c = seeded(tmp_path)
    r = c.get("/api/history/csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    text = r.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0] == dm.CSV_COLUMNS == ["날짜", "종목", "구분", "가격", "수량", "손익", "상태", "이유"]
    assert rows[1] == ["2026-10-02", "삼성전자(005930)", "매수", "70000", "10", "", "체결", "신호"]
    # 손익 = 10 × (72,000 − 평균 단가 70,010) − 수수료 100 − 세금 1,296
    assert rows[2] == ["2026-10-08", "삼성전자(005930)", "매도", "72000", "10", str(19_900 - 1_396), "체결", "손절 −7%"]
    assert rows[3] == ["2026-10-09", "삼성전자(005930)", "매수", "75000", "5", "", "실패", "잔고 부족"]


def test_overview(tmp_path: Path) -> None:
    c = seeded(tmp_path)
    v = c.get("/api/data").json()
    assert v["strategies"] == 2 and v["live_running"] is False and v["restore_line"] == dm.RESTORE_LINE
    assert set(v["bars"]) == {"symbols", "from", "to", "fetched_at"}


# ── 업데이트 상태(5-10) ──────────────────────────────────────────────────────


def write_update(data: Path, step: str, state: str, version: str = "1.1") -> None:
    (data / "update.json").write_text(json.dumps({"version": version, "step": step, "state": state}))


def test_update_status_steps(tmp_path: Path) -> None:
    c = boot(tmp_path)
    setup_owner(c)
    data = tmp_path / "data"
    s = c.get("/api/update").json()
    assert s["updating"] is False and s["chip"] is None
    assert [x["title"] for x in s["steps"]] == ["스케줄러 멈춤", "백업", "데이터 구조 바꿈", "다시 켬", "대조"]
    write_update(data, "migrate", "running")
    s = c.get("/api/update").json()
    assert s["updating"] is True and s["chip"] == "업데이트 중"
    assert [x["state"] for x in s["steps"]] == ["done", "done", "now", "wait", "wait"]
    write_update(data, "reconcile", "done")
    s = c.get("/api/update").json()
    assert s["updating"] is False and s["state"] == "done" and all(x["state"] == "done" for x in s["steps"])
    write_update(data, "backup", "failed")
    s = c.get("/api/update").json()
    assert s["updating"] is False and [x["state"] for x in s["steps"]][:2] == ["done", "failed"]


def test_update_done_message_once(tmp_path: Path) -> None:
    fake = FakeTelegram()
    c = boot(tmp_path, telegram_transport=fake)
    setup_owner(c)
    c.put("/api/telegram", json={"token": TOKEN})
    fake.message(MY_CHAT, "/start")
    c.post("/api/telegram/find-chat")
    data, db = tmp_path / "data", c.app_ref.state.db  # type: ignore[attr-defined]
    t = c.app_ref.state.telegram  # type: ignore[attr-defined]
    send = lambda text: t.notify("info", text)  # noqa: E731
    write_update(data, "restart", "running")
    assert updates.announce(data, db, send) is False
    write_update(data, "reconcile", "done", "1.1")
    assert updates.announce(data, db, send) is True
    assert fake.sent[-1]["text"] == "업데이트 끝 · 버전 1.1"
    assert updates.announce(data, db, send) is False  # 한 번만
    write_update(data, "reconcile", "done", "1.2")
    assert updates.announce(data, db, send) is True and fake.sent[-1]["text"] == "업데이트 끝 · 버전 1.2"
