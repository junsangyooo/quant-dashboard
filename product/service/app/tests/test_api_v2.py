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


EXAMPLE = (__import__("pathlib").Path(__file__).resolve().parents[2] / "examples" / "copy-v3-example.txt")


def test_list_detail_and_versions(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    sid = app_client.post("/api/v2/strategies", json={"body": _body()}).json()["id"]
    app_client.post(f"/api/v2/strategies/{sid}/versions", json={"body": _body()})
    lst = app_client.get("/api/v2/strategies").json()["strategies"]
    assert [(s["name"], s["mode_name"], s["problems"], s["version"]["no"]) for s in lst] == [
        ("대형주 돌파", "조건 충족 시 매매", 0, 2)]
    d = app_client.get(f"/api/v2/strategies/{sid}").json()
    assert [v["no"] for v in d["versions"]] == [2, 1] and d["versions"][0]["backtested"] is False
    assert d["block_lines"]["x"] == ["손절 −7% · 장중 감시", "최대 보유 20거래일 · 종가 확인"]
    assert d["block_lines"]["b"] == ["다음 날 시가 매수", "판 뒤 다시 사지 않는 기간 1거래일"]
    assert d["deletable"] is True


def test_paste_preview_and_accept(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    text = EXAMPLE.read_text(encoding="utf-8")
    p = app_client.post("/api/v2/import/preview", json={"text": text}).json()
    assert (p["name"], p["stages"], p["entry"], p["sell"], p["rows"]) == ("대형주 돌파", 7, 1, 1, 9)
    assert p["blank_kinds"] == ["숫자", "기간"] and p["notes"] == [
        "실험실 결과는 이 앱의 백테스트와 다를 수 있어요 · 숫자는 직접 정해요"]
    cards = {c["stage"]: c["lines"] for c in p["cards"]}
    assert cards["signal"] == ["n일 최고가 상향 돌파"] or cards["signal"][0].startswith("n일 최고가")
    assert cards["buy"] == ["다음 날 시가 매수", "판 뒤 다시 사지 않는 기간 1거래일"]
    assert p["others"] == ["universe", "select", "weight"]
    r = app_client.post("/api/v2/import/accept", json={"text": text}).json()
    got = app_client.get(f"/api/v2/strategies/{r['id']}").json()
    assert got["name"] == "대형주 돌파" and got["version"]["no"] == 1
    # 같은 글 다시 → 이름 뒤에 (2)
    assert app_client.post("/api/v2/import/accept", json={"text": text}).json()["name"] == "대형주 돌파 (2)"
    bad = app_client.post("/api/v2/import/preview", json={"text": "그냥 글"})
    assert bad.status_code == 400 and bad.json()["error"] == "복사한 전략 글이 아니에요"
    newer = app_client.post("/api/v2/import/preview", json={"text": text.replace("app>=1.0", "app>=2.0", 1)})
    assert newer.json()["error"] == "앱을 새 버전으로 바꿔야 가져올 수 있어요"


def test_file_export_import_and_delete(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    sid = app_client.post("/api/v2/strategies", json={"body": _body()}).json()["id"]
    f = app_client.get(f"/api/v2/strategies/{sid}/file").json()
    assert f["name"] == "대형주 돌파.json" and '"value": 50' in f["text"]
    r = app_client.post("/api/v2/import/file", json={"text": f["text"]}).json()
    again = app_client.get(f"/api/v2/strategies/{r['id']}").json()
    assert again["body"]["graph"] == app_client.get(f"/api/v2/strategies/{sid}").json()["body"]["graph"]
    assert app_client.delete(f"/api/v2/strategies/{r['id']}").json() == {"ok": True}
    assert app_client.get(f"/api/v2/strategies/{r['id']}").status_code == 404
