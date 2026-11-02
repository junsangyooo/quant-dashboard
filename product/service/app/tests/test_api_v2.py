"""v2 전략 API(T-30 · 편집기가 써요): 카탈로그 · 분석 · 블록 본문 저장 · 옛 본문 읽기."""

from __future__ import annotations

from typing import Any

from tests.conftest import setup_owner
from tests.helpers import legacy
from tests.test_blocks import big_breakout


def _body() -> dict[str, Any]:
    return {"name": "대형주 돌파", "graph": big_breakout()}


def test_needs_login(app_client) -> None:  # type: ignore[no-untyped-def]
    assert app_client.get("/api/v2/catalog").status_code == 401


def test_catalog(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    c = app_client.get("/api/v2/catalog").json()
    assert len(c["items"]) == 53 and [s["circle"] for s in c["stages"]] == list("①②③④⑤⑥⑦")
    per = next(i for i in c["items"] if i["id"] == "per")
    assert per["help"].startswith("주가를 최근 4분기 순이익 합으로 나눈 값이에요")
    assert per["source_display"] == "DART 순이익 · 토스 수정 종가"
    assert per["backtest_display"] == "일부만 · 공시일 기준" and per["start"] == "2016-04-01"
    assert c["dart"] is False


def test_save_and_read_blocks(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    r = app_client.post("/api/v2/strategies", json={"body": _body()})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    assert r.json()["problems"] == 0
    got = app_client.get(f"/api/v2/strategies/{sid}").json()
    assert got["version"]["no"] == 1 and got["body"]["graph"]["blocks"][0]["stage"] == "universe"
    assert got["analysis"]["summary"]["title"] == "문제 없음 · 모두 채웠어요"
    assert got["sentence"].startswith("코스피 · 코스닥 보통주 가운데")
    assert got["chips"]["x"][0] == {"exec": "intraday", "name": "장중 감시", "reason": ""}
    body = got["body"]
    body["graph"]["blocks"][2]["rows"].append({"item": "per", "op": "lte", "params": {}, "value": None,
                                               "value2": None, "exec": None})
    r = app_client.post(f"/api/v2/strategies/{sid}/versions", json={"body": body})
    assert r.status_code == 200 and r.json()["no"] == 2 and r.json()["problems"] == 2  # 빈칸 + 잠김(DART 없음)
    a = app_client.post("/api/v2/analyze", json={"body": body}).json()
    assert [p["title"] for p in a["analysis"]["problems"]] == ["PER은 DART를 연결해야 써요 · 연결 ›",
                                                              "PER 값이 비어 있어요"]
    text = app_client.get(f"/api/v2/strategies/{sid}/copytext").json()["text"]
    assert text.startswith("quant-strategy/3 app>=1.0\n")


def test_bad_body_rejected(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    bad = _body()
    bad["graph"]["blocks"][1]["rows"].append({"item": "per", "op": "lte", "params": {}, "value": 1,
                                             "value2": None, "exec": None})
    r = app_client.post("/api/v2/analyze", json={"body": bad})
    assert r.status_code == 400 and r.json()["error"] == "PER은 ② 신호 단계에 추가할 수 없어요"


def test_old_body_reads_as_v3(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    sid = app_client.post("/api/strategies", json={"body": legacy("event", "옛 전략")}).json()["id"]
    got = app_client.get(f"/api/v2/strategies/{sid}").json()
    assert [b["stage"] for b in got["body"]["graph"]["blocks"]][:2] == ["universe", "select"]
    assert got["body"]["converted"] == "v1"
