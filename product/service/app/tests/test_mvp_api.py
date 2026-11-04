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
