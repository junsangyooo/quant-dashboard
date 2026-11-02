"""백테스트 v2 API(TASKS T-32): 토스 일봉(가짜) · 코스피 비교 · 칩 · 고정 고지 · '실전이었다면' 줄 · 기록."""

from __future__ import annotations

from typing import Any

from tests.conftest import setup_owner
from tests.test_blocks import B, G, R


def _body(universe: list[dict[str, Any]] | None = None, filt: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    g = G([B("u", "universe", universe or [R("manual_list", value=["005930", "000660"])]),
           B("s", "signal", [R("ma", "cross_up", n=5)]),
           B("f", "filter", filt or [R("price", "gte", 1)]),
           B("k", "select", [R("top_n", value=2)]), B("b", "buy"),
           B("x", "sell", [R("stop_loss", value=7), R("max_hold", value=10)]), B("w", "weight")],
          ("u", "s"), ("s", "f"), ("f", "k"), ("k", "b"), ("b", "x"), ("w", "b"))
    return {"name": "백테스트 시험", "graph": g}


def _save(client, body: dict[str, Any]) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    r = client.post("/api/v2/strategies", json={"body": body}).json()
    d = client.get(f"/api/v2/strategies/{r['id']}").json()
    return r["id"], d["version"]["id"]


def test_input_and_result(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    sid, vid = _save(app_client, _body())
    inp = app_client.get(f"/api/v2/versions/{vid}/backtest").json()
    assert inp["chips"] == ["거래비용 반영 · 수수료 0.015% · 매도 세금 0.18%", "토스 일봉(수정주가)",
                            "판 돈은 다음 거래일 매수부터", "비교 기준 코스피"]
    assert inp["judge_line"] == "확인은 그날 종가로, 체결은 다음 거래일 시가로 해요"
    assert inp["range"]["first"] == ""  # 시세 조건만이라 시작 가능 날짜 제한 없음
    r = app_client.post("/api/v2/backtest", json={"version_id": vid, "start": "2024-03-01", "end": "2025-05-30",
                                                  "cash": 10_000_000})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["trade_count"] == len(res["trades"]) > 0 and len(res["recent"]) <= 5
    assert res["recent"][0]["name"]  # 종목 이름
    assert res["live_note"].startswith("시가가 종가보다 10% 넘게 높아 실전에서 안 샀을 매수")
    assert res["survivor_line"] == ("과거 결과는 앞으로의 수익을 뜻하지 않아요 · 상장폐지된 종목은 포함되지 않아요 · "
                                    "실제보다 좋게 나올 수 있어요")
    assert res["wide_universe"] is False and res["bench_curve"]  # 코스피 비교 선
    d = app_client.get(f"/api/v2/strategies/{sid}").json()
    assert d["version"]["backtested"] is True  # 버전마다 남아요


def test_blocked_cases(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    bad = _body()
    bad["graph"]["blocks"][2]["rows"] = [R("price", "gte", None)]
    _, vid = _save(app_client, bad)
    r = app_client.post("/api/v2/backtest", json={"version_id": vid, "start": "2024-03-01", "end": "2025-05-30",
                                                  "cash": 10_000_000})
    assert r.status_code == 400 and r.json()["error"] == "문제 1 · 편집 ›"
    _, vid = _save(app_client, _body(filt=[R("per", "lte", 15)]))
    r = app_client.post("/api/v2/backtest", json={"version_id": vid, "start": "2024-03-01", "end": "2025-05-30",
                                                  "cash": 10_000_000})
    assert r.status_code == 400 and r.json()["error"] == "문제 1 · 편집 ›"  # DART 없음 → 잠긴 조건
    _, vid = _save(app_client, _body())
    r = app_client.post("/api/v2/backtest", json={"version_id": vid, "start": "2024-03-01", "end": "2025-05-30",
                                                  "cash": 1000})
    assert r.json()["error"] == "시작 금액은 10만 원 ~ 100억 원 사이로 입력해요"


def test_dart_strategy_start_date_and_loading(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    app_client.put("/api/connect/dart", json={"key": "fake-dart-key-0000"})
    _, vid = _save(app_client, _body(filt=[R("per", "lte", 15)]))
    inp = app_client.get(f"/api/v2/versions/{vid}/backtest").json()
    assert inp["range"]["first"] == "2016-04-01" and inp["range"]["reason"] == "DART 재무가 2015년 보고서부터예요"
    r = app_client.post("/api/v2/backtest", json={"version_id": vid, "start": "2015-01-02", "end": "2025-05-30",
                                                  "cash": 10_000_000})
    assert r.json()["error"] == "DART 재무를 받는 중이에요 · 0% · 끝나면 백테스트할 수 있어요"  # R-P12
