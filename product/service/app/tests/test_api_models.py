"""API 응답 모델(TASKS P1-09 · ARCHITECTURE 2절 API 층 · 7절 'API 모양'): 모든 라우트에 지금 모양 그대로의 pydantic 응답 모델.

- 시험에서는 응답 모델이 모르는 키를 거절(`forbid`)하고 실행 때는 남겨요(`allow`) · 기존 HTTP 시험 전체가 엄격한 모델로 돌아요.
- HTTP 시험이 닿지 않는 상태(운용 중 화면 · 전부 팔기 · 모의투자 체결)는 만든 값을 모델로 직접 검사해요. **HTTP 요청을 새로
  보내지 않아요**(API 모양 기준선의 '선택 키' 표시가 바뀌지 않게 · 돈 라우트 시험은 기록되지 않는 ASGI 클라이언트로).
- 돈이 움직이는 라우트(주문 · 매도 · 멈추기)는 응답 검사 실패를 500으로 바꾸지 않고 기록한 뒤 원래 응답을 보내요.
- 실행 중 OpenAPI 주소는 열리지 않아요(`openapi_url=None` · 생성 타입은 앱 객체에서 바로 만들어요 · `scripts/gen_api_types.py`).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import APIRouter, FastAPI
from fastapi.routing import APIRoute

from app.api import live as live_api
from app.api import paper as paper_api
from app.api import strategies as strategies_api
from app.api.errors import install_error_handlers
from app.api.models import SHAPE_MISMATCH, ApiModel, MoneyRoute
from app.app import create_app
from app.domain.markets.kr import KST
from tests.conftest import FakeBars

APP = Path(__file__).resolve().parent.parent
# 돈이 움직이는 라우트: 실전 조작(시작 · 새 매수 멈춤 · 다시 켜기 · 끝내기 · 전부 팔기 · 금액 · 한도 · 전략) · 할 일 처리(주문 기록 · 권리 변동 ·
# 계좌에 맞추기 · 큰 주문)
MONEY = {
    "POST /api/live/start", "POST /api/live/pause", "POST /api/live/resume", "POST /api/live/end",
    "POST /api/live/sell-all", "PUT /api/live/amount", "PUT /api/live/limits", "PUT /api/live/strategy",
    "POST /api/todos/{tid}/unknown", "POST /api/todos/{tid}/corp", "POST /api/todos/{tid}/match",
    "POST /api/todos/{tid}/big-order",
}
# JSON이 아닌 몸통(파일 내려받기 · 화면 파일): 응답 모델 대신 몸통 꼴만 OpenAPI에 적어요
FILE_ROUTES = {"GET /api/data/backup": "application/octet-stream", "GET /api/history/csv": "text/csv",
               "GET /{path:path}": "text/html"}


def _flat(routes: Any) -> list[APIRoute]:
    """포함한 라우터는 그 안의 라우트로 펼쳐요(`tests/baseline/plugin.py`와 같은 꼴)."""
    out: list[APIRoute] = []
    for r in routes:
        inner = getattr(r, "original_router", None)
        if inner is not None:
            out += _flat(inner.routes)
        elif isinstance(r, APIRoute):
            out.append(r)
    return out


def _routes(app: FastAPI) -> dict[str, APIRoute]:
    out = {}
    for r in _flat(app.routes):
        for m in r.methods - {"HEAD", "OPTIONS"}:
            out[f"{m} {r.path}"] = r
    return out


@pytest.fixture
def app(tmp_path: Path, fake_bars: FakeBars) -> FastAPI:
    return create_app(tmp_path / "data", bars_source=fake_bars, scrypt_n=2**12, scheduler=False, keyfile=False)


# ── 모든 라우트에 응답 모델 ────────────────────────────────────────────────


def test_every_json_route_has_a_response_model_without_unset_keys(app: FastAPI) -> None:
    routes = _routes(app)
    assert len(routes) == 66  # 남는 라우트 수(P1-01 기준선 66 · 지금 그대로)
    for key, r in routes.items():
        if key in FILE_ROUTES:
            assert r.response_model is None, key
            assert FILE_ROUTES[key] in r.responses[200]["content"], key
            continue
        assert isinstance(r.response_model, type) and issubclass(r.response_model, ApiModel), key
        assert r.response_model_exclude_unset is True, key


def test_money_routes_never_turn_a_shape_failure_into_500(app: FastAPI) -> None:
    routes = _routes(app)
    assert {k for k, r in routes.items() if isinstance(r, MoneyRoute)} == MONEY


def test_models_forbid_unknown_keys_in_tests_and_allow_them_at_runtime(tmp_path: Path) -> None:
    assert live_api.LiveScreen.model_config["extra"] == "forbid"
    with pytest.raises(ValueError):
        live_api.LiveSummary.model_validate({"running": False, "paused": False, "halted": None, "todos": [],
                                             "unknown": 1})
    # 실행(시험 밖 프로세스)은 모르는 키를 남겨요 · HOME은 임시 폴더(P1-02 ④)
    env = {k: v for k, v in os.environ.items() if k != "PYTEST_VERSION"} | {"HOME": str(tmp_path)}
    code = ("from app.app import create_app\nfrom app.api import live\n"
            "print(live.LiveScreen.model_config['extra'])\n"
            "m = live.LiveSummary.model_validate({'running': False, 'paused': False, 'halted': None, 'todos': [], 'x': 1})\n"
            "print(m.model_dump(exclude_unset=True))\n")
    out = subprocess.run([sys.executable, "-c", code], cwd=APP, env=env, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.splitlines() == ["allow", "{'running': False, 'paused': False, 'halted': None, 'todos': [], 'x': 1}"]


def test_optional_keys_stay_absent_and_numbers_keep_their_type() -> None:
    """`exclude_unset`: 없던 키는 내보내지 않음 · 엄격한 타입: 정수 · 실수 · 참거짓을 바꾸지 않음."""
    m = live_api.LiveSummary.model_validate({"running": False, "paused": True, "halted": None, "todos": []})
    assert m.model_dump(mode="json", exclude_unset=True) == {"running": False, "paused": True, "halted": None,
                                                            "todos": []}
    row = {"sym": "005930", "name": "삼성전자", "side": "buy", "reason": [], "close": 10_000, "kind": None,
           "cap": 11_000, "qty": 3, "max": 33_000, "est": 30_000.5}
    assert live_api.PlanRow.model_validate(row).model_dump(mode="json", exclude_unset=True) == row
    with pytest.raises(ValueError):
        live_api.PlanRow.model_validate(row | {"qty": True})  # 참거짓은 정수가 아님


def test_runtime_never_serves_openapi(app: FastAPI) -> None:
    assert app.openapi_url is None and app.docs_url is None and app.redoc_url is None
    assert app.openapi()["info"]["title"] == "quant-mvp"  # 생성 타입의 원본은 앱 객체에서 바로(주소 없음)


# ── HTTP 시험이 닿지 않는 상태를 모델로 ──────────────────────────────────────


def test_live_running_screen_summary_and_sell_all_match_the_models(tmp_path: Path) -> None:
    from tests.test_blocks import R
    from tests.test_live import SYM, SYM2, World, body, give_pos, morning, running

    w = World(tmp_path, closes={SYM: [10_000.0] * 60, SYM2: [20_000.0] * 60})
    rid = running(w, body(syms=[SYM, SYM2], top=2, sell=[R("stop_loss", value=7, exec_="intraday")]))
    live_api.LiveScreen.model_validate(live_api.screen(w.live))  # 계획 줄(매수) · 계좌
    morning(w, date(2026, 11, 3))
    for o in w.orders():
        w.server.fill(o["toss_order_id"], str(o["qty"]), "10000")
    w.clock.at(date(2026, 11, 3), 9, 1)
    w.live.after_open(rid)
    sc = live_api.screen(w.live)
    assert sc["holdings"] and sc["recent"] and sc["history"] and sc["watch"]
    live_api.LiveScreen.model_validate(sc)
    live_api.LiveSummary.model_validate(live_api.summary(w.live))
    give_pos(w, rid, SYM2, 4, 20_000)
    w.holding(SYM2, 3, 20_000)  # 계좌 3 < 앱 4 → 건너뜀
    w.clock.at(date(2026, 11, 3), 11, 0)
    out = {"orders": w.live.sell_all_and_end(rid), **live_api.summary(w.live)}
    assert {o.get("status") or o.get("skip") for o in out["orders"]} >= {"계좌 불일치"}
    live_api.SellAllOut.model_validate(out)
    live_api.LiveScreen.model_validate(live_api.screen(w.live))  # 다음 계획 · 막힌 종목 · 할 일


def test_live_screen_before_and_after_a_run_matches_the_model(tmp_path: Path) -> None:
    from tests.test_live import World, running

    w = World(tmp_path)
    live_api.LiveScreen.model_validate(live_api.screen(w.live))  # 운용 전 · 마지막 운용 없음
    rid = running(w)
    w.live.end(rid)
    sc = live_api.screen(w.live)
    assert sc["last_run"] is not None
    live_api.LiveScreen.model_validate(sc)  # 운용 끝 · 마지막 운용 행


def test_paper_run_with_trades_holdings_and_plans_matches_the_model(tmp_path: Path) -> None:
    from tests.test_blocks import R
    from tests.test_paper_v2 import MON, Now, body, flat, save, setup

    now = Now(datetime(2026, 3, 3, 15, 0, tzinfo=KST))
    db, paper, _ = setup(tmp_path, {"111111": flat(10), "222222": flat(10, 20_000)}, now)
    vid = save(db, body(["111111", "222222"], sell=[R("max_hold", value=2)], top=2))
    v = paper.start(vid, 10_000_000)
    for d in ("2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06"):
        now.at(d, 20, 10)
        paper.tick()
    got = paper.view(v["id"])
    assert got["trades"] and MON.isoformat() <= got["last_date"]
    paper_api.PaperRunV2.model_validate(got)
    paper_api.PaperRuns.model_validate({"runs": paper.list()})
    paper_api.PaperRunV2.model_validate(paper.stop(v["id"]))


def test_catalog_matches_the_model() -> None:
    """조건 사전 전부(모든 항목 · 단계 · 조건 · 실행 방식)."""
    cat = {**strategies_api.catalog_view(), "dart": False}
    strategies_api.Catalog.model_validate(cat)


# ── 돈 라우트: 응답 검사가 실패해도 원래 응답 ─────────────────────────────────


class _Tiny(ApiModel):
    ok: bool


def _call(app: FastAPI, method: str, path: str) -> httpx.Response:
    """기록되지 않는 ASGI 클라이언트(시험 클라이언트가 아니라 API 모양 수집에 들어가지 않음)."""

    async def go() -> httpx.Response:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://testserver") as c:
            return await c.request(method, path)

    return asyncio.run(go())


def test_money_route_logs_and_returns_the_original_body(caplog: pytest.LogCaptureFixture,
                                                       shape_mismatches: list[logging.LogRecord]) -> None:
    app = FastAPI()
    install_error_handlers(app)
    money = APIRouter(route_class=MoneyRoute)
    plain = APIRouter()

    @money.post("/money", response_model=_Tiny, response_model_exclude_unset=True)
    def sent() -> dict[str, Any]:
        return {"ok": True, "order": {"sym": "005930", "status": "sent"}}  # 모델에 없는 키(시험은 forbid)

    @plain.post("/plain", response_model=_Tiny, response_model_exclude_unset=True)
    def other() -> dict[str, Any]:
        return {"ok": True, "order": {"sym": "005930"}}

    app.include_router(money)
    app.include_router(plain)
    with caplog.at_level(logging.ERROR, logger="quant-mvp"):
        r = _call(app, "POST", "/money")
        assert r.status_code == 200
        assert json.loads(r.text) == {"ok": True, "order": {"sym": "005930", "status": "sent"}}
        r2 = _call(app, "POST", "/plain")
    assert r2.status_code == 500 and r2.json()["error"]  # 돈이 안 움직이는 라우트는 지금처럼 500
    logs = [x.getMessage() for x in caplog.records if SHAPE_MISMATCH in x.getMessage()]
    assert logs == [f"{SHAPE_MISMATCH} POST /money at ['response.order']"]
    assert "005930" not in logs[0]  # 값은 남기지 않아요(S2)
    shape_mismatches.clear()  # 일부러 낸 기록(이 시험 밖에서는 0건이어야 해요 · conftest)
