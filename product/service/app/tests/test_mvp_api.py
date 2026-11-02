"""디자인 고치기 1회 뒤 더한 API: 비밀번호 변경 · 공인 IP 보기 · 지난 모의투자 · 계획 이유 · 화면 파일."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.helpers import legacy, new_strategy
from tests.conftest import CsrfClient, PASSWORD, FakeBars, FakeIp, FakeToss, setup_owner
from tests.test_engine_paper import _api_body

NEW_PW = "brand new pass 42"


def test_password_change(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    app_client.put("/api/connect/toss", json={"client_id": FakeToss.CLIENT_ID, "client_secret": FakeToss.SECRET})
    # 새 비밀번호 두 칸이 다르면 횟수를 세지 않는다
    r = app_client.post("/api/password", json={"current": PASSWORD, "password": NEW_PW, "password2": "x" * 9})
    assert r.status_code == 400 and "달라요" in r.json()["error"]
    # 지금 비밀번호가 틀리면 로그인과 같이 센다
    r = app_client.post("/api/password", json={"current": "wrong pass 1", "password": NEW_PW, "password2": NEW_PW})
    assert r.status_code == 401 and r.json()["tries_left"] == 4 and "지금 비밀번호" in r.json()["error"]
    r = app_client.post("/api/password", json={"current": PASSWORD, "password": NEW_PW, "password2": NEW_PW})
    assert r.status_code == 200, r.text
    assert NEW_PW not in r.text and PASSWORD not in r.text
    # 다시 켠 것처럼 잠그고: 옛 비밀번호는 안 되고 새 비밀번호로 열면 저장한 키가 그대로 풀린다
    app_client.app_ref.state.vault.lock_now()
    assert app_client.post("/api/login", json={"password": PASSWORD}).status_code == 401
    assert app_client.post("/api/login", json={"password": NEW_PW}).status_code == 200
    assert app_client.get("/api/connect").json()["toss"]["secret_tail"] == FakeToss.SECRET[-4:]


def test_password_change_counts_toward_lock(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    for _ in range(4):
        r = app_client.post("/api/password", json={"current": "nope nope 1", "password": NEW_PW, "password2": NEW_PW})
        assert r.status_code == 401
    r = app_client.post("/api/password", json={"current": "nope nope 1", "password": NEW_PW, "password2": NEW_PW})
    assert r.status_code == 429 and "잠금" in r.json()["error"]
    # 잠긴 동안에는 맞는 비밀번호도 받지 않는다
    r = app_client.post("/api/password", json={"current": PASSWORD, "password": NEW_PW, "password2": NEW_PW})
    assert r.status_code == 429


def test_password_change_keeps_recovery_code(app_client) -> None:  # type: ignore[no-untyped-def]
    code = setup_owner(app_client)
    assert app_client.post("/api/password", json={"current": PASSWORD, "password": NEW_PW, "password2": NEW_PW}).status_code == 200
    r = app_client.post("/api/recover", json={"recovery_code": code, "password": PASSWORD, "password2": PASSWORD})
    assert r.status_code == 200, r.text


def test_password_change_needs_login(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    app_client.post("/api/logout")
    r = app_client.post("/api/password", json={"current": PASSWORD, "password": NEW_PW, "password2": NEW_PW})
    assert r.status_code == 401


def test_public_ip_only_when_asked(app_client, fake_ip: FakeIp, fake_toss: FakeToss) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    # 다른 화면 API를 불러도 공인 IP 서비스는 부르지 않는다
    for path in ("/api/home", "/api/connect", "/api/plan", "/api/strategies"):
        app_client.get(path)
    assert fake_ip.calls == []
    r = app_client.post("/api/public-ip")
    assert r.status_code == 200 and r.json() == {"ip": "123.45.67.89"}
    assert fake_ip.calls == ["https://api.ipify.org?format=json"]
    assert fake_toss.calls == []  # 토스는 부르지 않는다
    fake_ip.down = True
    r = app_client.post("/api/public-ip")
    assert r.status_code == 502 and "공인 IP" in r.json()["error"]
    fake_ip.down = False
    fake_ip.body = b"<html>"
    assert app_client.post("/api/public-ip").status_code == 502


def test_public_ip_needs_login(app_client, fake_ip: FakeIp) -> None:  # type: ignore[no-untyped-def]
    assert app_client.post("/api/public-ip").status_code == 401
    assert fake_ip.calls == []


def test_offline_env_never_reaches_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MVP_TOSS_OFFLINE", "1")
    app = create_app(tmp_path / "d", bars_source=FakeBars(), scrypt_n=2**12, scheduler=False)
    with CsrfClient(app) as c:
        setup_owner(c)
        r = c.post("/api/public-ip")
        assert r.status_code == 502


def test_runs_and_history_by_run(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    sid = new_strategy(app_client, "기록", "event")
    v1 = app_client.post(f"/api/strategies/{sid}/versions", json={"body": _api_body()}).json()["version_id"]
    assert app_client.post("/api/paper/start", json={"version_id": v1, "cash": 10_000_000}).status_code == 200
    first = app_client.get("/api/paper/runs").json()["runs"][0]
    assert first["status"] == "running" and first["version_no"] == 2 and first["ret"] == 0
    r = app_client.post("/api/paper/stop").json()
    assert r["run"]["status"] == "ended" and r["run"]["ended_at"]
    home = app_client.get("/api/home").json()
    assert home["running"] is False and home["last_run"]["id"] == first["id"]
    # 끝낸 뒤 새로 시작하면 지난 실행이 전략 상세 목록에 남는다
    app_client.post("/api/paper/start", json={"version_id": v1, "cash": 5_000_000})
    detail = app_client.get(f"/api/strategies/{sid}").json()
    assert [x["id"] for x in detail["past_runs"]] == [first["id"]]
    assert detail["paper"]["cash0"] == 5_000_000 and detail["deletable"] is False
    view = app_client.get(f"/api/paper/runs/{first['id']}").json()
    assert view["status"] == "ended" and view["trades_count"] == 0 and view["realized"] == 0
    assert app_client.get("/api/paper/runs/9999").status_code == 404
    runs = app_client.get(f"/api/paper/runs?strategy_id={sid}").json()["runs"]
    assert [x["status"] for x in runs] == ["running", "ended"]


def test_plan_has_reasons_with_slot_numbers(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    sid = new_strategy(app_client, "계획", "event")
    vid = app_client.post(f"/api/strategies/{sid}/versions", json={"body": _api_body()}).json()["version_id"]
    app_client.post("/api/paper/start", json={"version_id": vid, "cash": 10_000_000})
    plan = app_client.get("/api/plan").json()
    assert plan["running"] and plan["last"]["how"] == "start"
    for p in plan["plans"]:
        circles = [r["circle"] for r in p["reasons"]]
        assert all(circles)
        if p["side"] == "buy":
            assert "②" in circles and "③" in circles and "④" in circles


def test_import_names_and_source_line(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    text = (Path(__file__).parent.parent / "samples" / "lab-ma-breakout.txt").read_text(encoding="utf-8")
    p1 = app_client.post("/api/import/preview", json={"text": text}).json()
    assert p1["renamed"] is False
    app_client.post("/api/import/accept", json={"text": text})
    p2 = app_client.post("/api/import/preview", json={"text": text}).json()
    assert p2["renamed"] is True and p2["name"].endswith(" (2)")
    r = app_client.post("/api/import/accept", json={"text": text, "name": "내 이름"}).json()
    assert app_client.get(f"/api/strategies/{r['id']}").json()["name"] == "내 이름"
    # 이 앱에서 복사한 글은 버전까지 출처에 남는다
    copy = app_client.get(f"/api/strategies/{r['id']}/copytext").json()["text"]
    p3 = app_client.post("/api/import/preview", json={"text": copy}).json()
    assert p3["source_line"] == "내 이름 · 버전 1에서 복사"


def test_check_without_saving(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    sid = new_strategy(app_client, "검사", "event")
    body = app_client.get(f"/api/strategies/{sid}").json()["body"]
    r = app_client.post(f"/api/strategies/{sid}/check", json={"body": body}).json()
    assert r["problems"] and r["blanks_by_slot"]
    assert len(app_client.get(f"/api/strategies/{sid}").json()["versions"]) == 1


def test_auto_tick_records_fill_range(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    sid = new_strategy(app_client, "자동", "event")
    vid = app_client.post(f"/api/strategies/{sid}/versions", json={"body": _api_body()}).json()["version_id"]
    app_client.post("/api/paper/start", json={"version_id": vid, "cash": 10_000_000})
    # 로그인하지 않아도(잠긴 채로) 자동 확인은 돈다
    app_client.app_ref.state.vault.lock_now()
    assert app_client.app_ref.state.auto_tick() == "ran"
    app_client.post("/api/login", json={"password": PASSWORD})
    fill = app_client.get("/api/home").json()["auto"]["last_fill"]
    assert fill is not None and fill["new_days"] == 0 and "run_id" in fill


def test_serves_built_screens(tmp_path: Path, fake_bars: FakeBars, monkeypatch: pytest.MonkeyPatch) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>quant</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    monkeypatch.setenv("MVP_WEB_DIST", str(dist))
    app = create_app(tmp_path / "d", bars_source=fake_bars, scrypt_n=2**12, scheduler=False)
    with CsrfClient(app) as c:
        assert c.get("/").text.startswith("<!doctype html>")
        assert c.get("/plan").text.startswith("<!doctype html>")  # 화면 주소는 index.html
        r = c.get("/assets/app.js")
        assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
        assert "content-security-policy" in r.headers
        assert "nope" not in c.get("/../secret.txt").text
        assert "nope" not in c.get("/assets/../../secret.txt").text
        assert c.get("/api/nothing").status_code == 401  # API는 index.html로 넘어가지 않는다
