"""복사한 전략 글: quant-strategy/2(그래프, 숫자 비움) · quant-strategy/1(일곱 칸) 받기 · 규칙 어긴 글 거절."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from app import strategy as st
from tests.conftest import setup_owner
from tests.helpers import legacy

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _filled() -> dict:  # type: ignore[type-arg]
    return st.example_body("either")


def _v2(data: dict) -> str:  # type: ignore[type-arg]
    text = json.dumps(data, ensure_ascii=False)
    return f"quant-strategy/2 app>=0.2\n{text}\ncheck: {st.check_of(text)}"


def test_roundtrip_blanks_numbers() -> None:
    text = st.to_copy_text(_filled(), {"from": "실험실", "id": "lab-1"})
    lines = text.strip("\n").split("\n")
    assert lines[0] == "quant-strategy/2 app>=0.2"
    body_text = "\n".join(lines[1:-1])
    assert lines[-1] == "check: " + hashlib.sha256(body_text.encode()).hexdigest()[:12]
    body, notes = st.parse_copy_text(text)
    nodes = {n["id"]: n for n in body["graph"]["nodes"]}
    assert nodes["s1"]["params"]["n"] is None and nodes["x1"]["params"]["pct"] is None
    assert nodes["u1"]["params"]["symbols"] == st.BIG10  # 종목은 남긴다
    assert body["graph"]["edges"] == _filled()["graph"]["edges"]
    assert body["source"]["from"] == "실험실"
    assert notes == []


def test_numbers_in_text_are_blanked() -> None:
    body, notes = st.parse_copy_text(_v2(_filled()))
    assert all(n["params"].get("n") is None for n in body["graph"]["nodes"] if n["piece"] == "high_breakout")
    assert notes and "직접" in notes[0]


def test_rebalance_how_is_structure_not_a_number() -> None:
    body, _ = st.parse_copy_text(st.to_copy_text(st.example_body("trend")))
    reb = next(n for n in body["graph"]["nodes"] if n["piece"] == "rebalance_every")
    assert reb["params"] == {"n": None, "how": "rank"}
    assert st.mode_of(body) == "rank"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "hello",
        '{"graph": {}}',
        "quant-strategy/3 app>=0.1\n{}\ncheck: 000000000000",
        "quant-strategy/2\n{}\ncheck: 000000000000",
        'quant-strategy/2 app>=0.1\n{"a":1}',
        'quant-strategy/2 app>=0.1\n{"a": 1}\ncheck: ' + st.check_of('{"a": 1}'),
    ],
)
def test_not_copy_text(text: str) -> None:
    with pytest.raises(st.FormatError, match="복사한 전략 글이 아니에요"):
        st.parse_copy_text(text)


def test_check_mismatch_and_tamper() -> None:
    text = st.to_copy_text(_filled())
    tampered = text.replace("005930", "005935")
    with pytest.raises(st.FormatError, match="검사 값"):
        st.parse_copy_text(tampered)


def test_needs_newer_app() -> None:
    body = json.dumps(st.blank_numbers(_filled()))
    text = f"quant-strategy/2 app>=0.9\n{body}\ncheck: {st.check_of(body)}"
    with pytest.raises(st.FormatError, match="0.9 이상"):
        st.parse_copy_text(text)


def test_unknown_piece() -> None:
    data = st.blank_numbers(_filled())
    data["graph"]["nodes"].append({"id": "z", "piece": "ai_judge", "params": {}})
    with pytest.raises(st.FormatError, match="모르는 조건"):
        st.parse_copy_text(_v2(data))


def _bad(mutate) -> st.FormatError:  # type: ignore[no-untyped-def]
    data = st.blank_numbers(_filled())
    mutate(data["graph"])
    with pytest.raises(st.FormatError) as e:
        st.parse_copy_text(_v2(data))
    assert e.value.kind == "graph"
    assert str(e.value).startswith("복사한 전략 글의 연결이 맞지 않아요 · ")
    return e.value


def test_rejects_sell_before_buy() -> None:
    err = _bad(lambda g: g["edges"].append({"from": "x1", "to": "b1"}))
    assert err.detail == "⑥ 손절 −n%가 ⑤ 매수 앞에 연결돼 있어요 · 매도 조건은 매수 뒤에 연결해요"


def test_rejects_other_rule_breaks() -> None:
    # ② → ⑥
    assert "매도 조건은 매수 뒤에" in _bad(lambda g: g["edges"].append({"from": "s1", "to": "x2"})).detail
    # ④가 있는데 ③ → ⑤
    assert "종목 선정은 매수 바로 앞에" in _bad(lambda g: g["edges"].append({"from": "f1", "to": "b1"})).detail
    # 순환(② → ③ → ②)
    def cycle(g):  # type: ignore[no-untyped-def]
        g["edges"].append({"from": "f1", "to": "s2"})
    assert "돌아가" in _bad(cycle).detail
    # 유니버스 둘
    assert "유니버스는 하나만" in _bad(lambda g: g["nodes"].append({"id": "u2", "piece": "manual_list", "params": {}})).detail
    # 없는 조건을 가리키는 선
    assert "없는 조건" in _bad(lambda g: g["edges"].append({"from": "s1", "to": "nope"})).detail
    # 같은 선 두 번
    assert "선은 하나" in _bad(lambda g: g["edges"].append({"from": "u1", "to": "s1"})).detail
    # 40개 넘는 조건
    def many(g):  # type: ignore[no-untyped-def]
        for i in range(40):
            g["nodes"].append({"id": f"m{i}", "piece": "min_price", "params": {}})
    assert "40개까지" in _bad(many).detail


def test_rejects_more_than_20_paths() -> None:
    data = st.blank_numbers(st.blank_body("많음"))
    g = data["graph"]
    # ① → (신호 5) → (필터 5) → ④: 25경로
    for i in range(5):
        g["nodes"].append({"id": f"s{i}", "piece": "ma_cross_up", "params": {}})
        g["nodes"].append({"id": f"f{i}", "piece": "min_price", "params": {}})
    g["edges"] = [e for e in g["edges"] if not (e["from"] == "u1" and e["to"] == "k1")]
    for i in range(5):
        g["edges"].append({"from": "u1", "to": f"s{i}"})
        g["edges"].append({"from": f"f{i}", "to": "k1"})
        for j in range(5):
            g["edges"].append({"from": f"s{i}", "to": f"f{j}"})
    with pytest.raises(st.FormatError, match="경로가 너무 많아요"):
        st.parse_copy_text(_v2(data))


def test_loose_lines_and_blanks_are_accepted_as_problems() -> None:
    data = st.blank_numbers(_filled())
    g = data["graph"]
    g["edges"] = [e for e in g["edges"] if e != {"from": "f1", "to": "k1"}]  # 끊긴 선
    g["nodes"].append({"id": "p1", "piece": "min_price", "params": {}, "x": 0, "y": 0})  # 연결 없음
    body, _ = st.parse_copy_text(_v2(data))
    kinds = {p["kind"] for p in st.validate(body)}
    assert {"blank", "dead", "loose"} <= kinds


def test_crlf_and_whitespace_ok() -> None:
    text = st.to_copy_text(_filled()).replace("\n", "\r\n") + "\r\n\r\n"
    body, _ = st.parse_copy_text("\n" + text)
    assert len(body["graph"]["nodes"]) == 9


def test_v1_seven_slot_text_is_read_as_a_graph() -> None:
    old = legacy("event", "옛 글")
    old["slots"]["universe"][0]["params"]["symbols"] = ["005930", "000660"]
    old["slots"]["signal"] = [{"piece": "ma_cross_up", "params": {"n": 20}}]
    old["slots"]["filter"] = [{"piece": "min_turnover", "params": {"n": 50}}]
    old["slots"]["sell"] = [{"piece": "stop_loss", "params": {"pct": 7}}, {"piece": "max_hold", "params": {"n": 20}}]
    text = json.dumps(old, ensure_ascii=False)
    body, notes = st.parse_copy_text(f"quant-strategy/1 app>=0.1\n{text}\ncheck: {st.check_of(text)}")
    a = st.analyze(body)
    assert a["mode"] == "event"
    names = [[st.PIECES[next(n for n in body["graph"]["nodes"] if n["id"] == i)["piece"]]["slot"] for i in p["nodes"]]
             for p in a["entry"]]
    assert names == [["universe", "signal", "filter", "select", "buy"]]
    assert len(a["sell"]) == 2  # 매도는 ⑤에서 갈래(하나라도)
    assert notes and "직접" in notes[0]


def test_samples_parse() -> None:
    files = sorted(SAMPLES.glob("*.txt"))
    assert len(files) == 3
    for f in files:
        body, notes = st.parse_copy_text(f.read_text(encoding="utf-8"))
        assert body["source"]["from"] == "실험실"
        assert st.count_blanks(body) > 0
        assert notes == []
        # 숫자를 넣기 전에는 문제가 있고, 그 문제는 숫자 칸뿐이다
        problems = st.validate(body)
        assert problems and all(p["kind"] == "blank" for p in problems)


def test_import_api_flow(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    text = (SAMPLES / "lab-ma-breakout.txt").read_text(encoding="utf-8")
    r = app_client.post("/api/import/preview", json={"text": text})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["source"]["from"] == "실험실"
    assert p["blanks"] > 0 and p["mode_name"] == "조건 충족 시 매매" and p["body"]["graph"]["nodes"]
    r = app_client.post("/api/import/preview", json={"text": "그냥 글이에요"})
    assert r.status_code == 400 and r.json()["error"] == "복사한 전략 글이 아니에요"
    r = app_client.post("/api/import/accept", json={"text": text})
    sid = r.json()["id"]
    got = app_client.get(f"/api/strategies/{sid}").json()
    assert got["version"]["no"] == 1 and got["version"]["problems"]
    assert got["source"]["from"] == "실험실"
    # 내보내기 → 다시 붙여 넣기
    copy = app_client.get(f"/api/strategies/{sid}/copytext").json()["text"]
    assert copy.startswith("quant-strategy/2 ")
    assert app_client.post("/api/import/preview", json={"text": copy}).status_code == 200


def test_import_api_rejects_bad_links(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    data = st.blank_numbers(_filled())
    data["graph"]["edges"].append({"from": "x1", "to": "b1"})
    r = app_client.post("/api/import/preview", json={"text": _v2(data)})
    assert r.status_code == 400
    j = r.json()
    assert j["kind"] == "graph" and j["title"] == "복사한 전략 글의 연결이 맞지 않아요"
    assert j["detail"].startswith("⑥ 손절 −n%가 ⑤ 매수 앞에")
