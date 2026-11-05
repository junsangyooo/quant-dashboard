"""복사 글 v3 · 전략 파일 · 옛 전략 변환(TASKS T-22 · ENGINE-RULES R-C1 ~ R-C9 · 11-6 시험 전부)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain import blocks as bk
from app.domain import copytext as ct
from app.domain.copytext import FormatError
from tests.baseline import replay
from tests.test_blocks import big_breakout

EXAMPLE = Path(__file__).resolve().parents[2] / "examples" / "copy-v3-example.txt"
# v1 쪽 입력 · 기대값은 P1-01a가 얼린 `tests/baseline/frozen/v1_fixtures.json`(P1-03 전에는 지운 v1 전략 모듈 · 회귀 도구가
# 만들던 값 · 같음을 `test_v1_*`로 확인한 뒤 v1 코드를 지움). 값은 그대로예요.
FX = replay.load_v1_fixtures()


def _example(eid: str) -> dict:  # type: ignore[type-arg]
    return next(e for e in FX["examples"] if e["id"] == eid)


def example_text() -> str:
    return EXAMPLE.read_text(encoding="utf-8")


def _rewrite(text: str, mutate) -> str:  # type: ignore[no-untyped-def]
    lines = text.rstrip("\n").split("\n")
    data = json.loads("\n".join(lines[1:-1]))
    mutate(data)
    body = json.dumps(data, ensure_ascii=False, indent=2)
    return f"{lines[0]}\n{body}\ncheck: {ct.check_of(body)}\n"


# ── 11-6 ─────────────────────────────────────────────────────────────────────


def test_read_example() -> None:
    body, notes = ct.parse_copy_text(example_text())
    a = bk.analyze(body["graph"])
    assert a["problems"] and {p["kind"] for p in a["problems"]} == {"blank"}  # 문제 = 빈칸만
    buy = next(b for b in body["graph"]["blocks"] if b["stage"] == "buy")
    assert buy["rows"][0]["value"] == 1  # 가져온 ⑤ = 1
    assert notes == ["실험실 결과는 이 앱의 백테스트와 다를 수 있어요 · 숫자는 직접 정해요"]
    assert [b["stage"] for b in body["graph"]["blocks"]] == ["universe", "signal", "filter", "select", "buy", "sell",
                                                            "weight"]
    sell = body["graph"]["blocks"][5]
    assert sell["match"] == "any" and [r["exec"] for r in sell["rows"]] == ["intraday", "intraday", "close"]


def test_rewrite_example_same_text() -> None:
    text = example_text()
    body, _ = ct.parse_copy_text(text)
    assert ct.to_copy_text(body) == text  # 글자 하나까지 같음
    assert text.rstrip().endswith("check: f6d308820f59")


def test_one_char_changed_is_not_copy_text() -> None:
    text = example_text().replace('"대형주 돌파"', '"대형주 돌파!"')
    with pytest.raises(FormatError) as e:
        ct.parse_copy_text(text)
    assert e.value.message == "복사한 전략 글이 아니에요"


def test_unknown_item() -> None:
    text = _rewrite(example_text(), lambda d: d["graph"]["blocks"][2]["rows"].__setitem__(
        0, {**d["graph"]["blocks"][2]["rows"][0], "item": "foo"}))
    with pytest.raises(FormatError) as e:
        ct.parse_copy_text(text)
    assert e.value.message == "이 앱 버전에 없는 조건이 있어요 · foo"


def test_op_not_allowed_for_item() -> None:
    text = _rewrite(example_text(), lambda d: d["graph"]["blocks"][2]["rows"][0].__setitem__("op", "cross_up"))
    with pytest.raises(FormatError) as e:
        ct.parse_copy_text(text)
    assert e.value.message.startswith("이 앱 버전에 없는 조건이 있어요 · ")


def test_v1_and_v2_texts_become_v3() -> None:
    old = {"name": "옛 글", "template": "event", "slots": {
        "universe": [{"piece": "manual_list", "params": {"symbols": ["005930"]}}],
        "signal": [{"piece": "ma_cross_up", "params": {"n": 20}}],
        "filter": [{"piece": "min_turnover", "params": {"n": 50}}],
        "select": [{"piece": "top_n", "params": {"n": 5}}],
        "buy": [{"piece": "next_open", "params": {}}],
        "sell": [{"piece": "stop_loss", "params": {"pct": 7}}, {"piece": "ma_break_down", "params": {"n": 10}}],
        "weight": [{"piece": "equal", "params": {}}, {"piece": "max_per_stock", "params": {"pct": 40}}]}}
    raw = json.dumps(old, ensure_ascii=False)
    body, _ = ct.parse_copy_text(f"quant-strategy/1 app>=0.1\n{raw}\ncheck: {ct.check_of(raw)}")
    rows = [(b["stage"], r["item"], r["op"]) for b in body["graph"]["blocks"] for r in b["rows"]]
    assert rows == [("universe", "manual_list", "pick"), ("signal", "ma", "cross_up"), ("filter", "turnover", "gte"),
                    ("select", "top_n", "top_n"), ("buy", "next_open", "fixed"), ("sell", "stop_loss", "fixed"),
                    ("sell", "ma", "below"), ("weight", "equal", "fixed"), ("weight", "max_per_stock", "fixed")]
    assert all(r["value"] is None for b in body["graph"]["blocks"] for r in b["rows"] if r["item"] != "next_open")
    # v2(graph 노드) 글: v1 예시
    v2 = _example("either")["copy_text"]  # 얼린 v2 복사 글(st1.to_copy_text(st1.example_body("either")))
    body2, _ = ct.parse_copy_text(v2)
    assert [b["stage"] for b in body2["graph"]["blocks"]].count("signal") == 2
    assert "converted" not in body2  # 복사 글로 받은 전략은 새 전략(⑤ = 1)
    assert next(b for b in body2["graph"]["blocks"] if b["stage"] == "buy")["rows"][0]["value"] == 1


# ── R-C1 ~ R-C9 ──────────────────────────────────────────────────────────────


def test_R_C2_blanks() -> None:
    body = {"name": "대형주 돌파", "graph": big_breakout()}
    text = ct.to_copy_text(body)
    data = json.loads("\n".join(text.rstrip("\n").split("\n")[1:-1]))
    rows = [r for b in data["graph"]["blocks"] for r in b["rows"]]
    assert all(r["value"] is None or isinstance(r["value"], list) for r in rows)
    assert next(r for r in rows if r["item"] == "market")["value"] == ["KOSPI", "KOSDAQ"]  # 고르기 값은 남겨요
    assert next(r for r in rows if r["item"] == "ma")["params"] == {"n": None}
    assert next(r for r in rows if r["item"] == "top_n")["params"] == {"by": "strength", "order": "desc"}
    assert [r["exec"] for r in rows if r["exec"]] == ["intraday", "close"]


def test_R_C4_rejects() -> None:
    with pytest.raises(FormatError) as e:
        ct.parse_copy_text(example_text().replace("app>=1.0", "app>=2.0", 1))
    assert e.value.message == "앱을 새 버전으로 바꿔야 가져올 수 있어요"
    with pytest.raises(FormatError, match="복사한 전략 글이 아니에요"):
        ct.parse_copy_text(example_text() + " " * (64 * 1024))
    with pytest.raises(FormatError, match="복사한 전략 글이 아니에요"):
        ct.parse_copy_text("그냥 글이에요")
    with pytest.raises(FormatError, match="복사한 전략 글이 아니에요"):
        ct.parse_copy_text(example_text().replace("check: f6d308820f59", "check: f6d308820f5a"))


def test_R_C5_link_check() -> None:
    bad = _rewrite(example_text(), lambda d: d["graph"]["edges"].append({"from": "b6", "to": "b2"}))
    with pytest.raises(FormatError) as e:
        ct.parse_copy_text(bad)
    assert e.value.kind == "graph"
    assert e.value.message == "복사한 전략 글의 연결이 맞지 않아요 · 매도 단계는 매수 단계 뒤에 이어요"
    # 끊긴 ③ → 받고 문제
    loose = _rewrite(example_text(), lambda d: d["graph"].__setitem__("edges", [
        e for e in d["graph"]["edges"] if e != {"from": "b2", "to": "b3"} and e != {"from": "b3", "to": "b4"}
    ] + [{"from": "b2", "to": "b4"}]))
    body, _ = ct.parse_copy_text(loose)
    assert [p["kind"] for p in bk.analyze(body["graph"])["problems"] if p["kind"] != "blank"] == ["loose"]


def test_R_C6_imported_cooldown_is_one() -> None:
    body, _ = ct.parse_copy_text(example_text())
    assert next(b for b in body["graph"]["blocks"] if b["stage"] == "buy")["rows"][0]["value"] == 1


def test_R_C7_strategy_file_roundtrip() -> None:
    body = bk.normalize({"name": "대형주 돌파", "graph": big_breakout()})
    text = ct.to_file(body)
    again = ct.read_file(text)
    assert again == body
    assert next(r for b in again["graph"]["blocks"] for r in b["rows"] if r["item"] == "turnover")["value"] == 50
    with pytest.raises(FormatError, match="전략 파일 형식이 맞지 않아요"):
        ct.read_file("{nope")


def test_R_C8_aliases_and_v1_cooldown_zero() -> None:
    v1 = _example("breakout")["body"]  # 얼린 옛 예시(st1.example_body("breakout"))
    body = ct.convert_v1(v1)
    assert body["converted"] == "v1"
    by_item = {r["item"]: r for b in body["graph"]["blocks"] for r in b["rows"]}
    assert by_item["high_n"]["params"] == {"n": 20}
    assert by_item["turnover"]["value"] == 100 and by_item["turnover"]["op"] == "gte"
    assert by_item["next_open"]["value"] == 0  # R-G7: v1 변환 ⑤ = 0
    assert by_item["stop_loss"]["exec"] == "close" and by_item["stop_loss"]["value"] == 7
    assert by_item["top_n"]["value"] == 5 and by_item["top_n"]["params"] == {"by": "strength", "order": "desc"}
    rsi = ct.v1_row("rsi_below", {"period": 14, "level": 30})
    assert (rsi["item"], rsi["op"], rsi["params"], rsi["value"]) == ("rsi", "lt", {"period": 14}, 30)
    assert ct.v1_row("ma_break_down", {"n": 10})["op"] == "below"
    with pytest.raises(FormatError, match="이 앱 버전에 없는 조건이 있어요 · ai_judge"):
        ct.v1_row("ai_judge", {})


def test_R_C9_block_count() -> None:
    """블록 수 = 노드 수 − (⑦ 노드 수 − 1). 회귀 사례 전부와 옛 예시 4개."""
    samples = [(r["normalized"], r["mode"]) for r in FX["bodies"]] + [(e["body"], e["mode"]) for e in FX["examples"]]
    for v1, mode in samples:  # 얼린 (st1.normalize(본문) · st1.mode_of) · 옛 예시 4개
        nodes = v1["graph"]["nodes"]
        weights = sum(1 for n in nodes if n["piece"] in ("equal", "max_per_stock", "rebalance_every"))
        body = ct.convert_v1(v1)
        assert len(body["graph"]["blocks"]) == len(nodes) - (weights - 1)
        assert all(b["match"] == "all" for b in body["graph"]["blocks"])
        assert bk.analyze(body["graph"])["problems"] == []
        assert bk.mode_of(body["graph"]) == mode
        w = [e for e in body["graph"]["edges"] if any(b["id"] == e["from"] and b["stage"] == "weight"
                                                     for b in body["graph"]["blocks"])]
        assert len(w) == 1  # ⑦ 블록으로 들어가는 선은 하나


def test_stored_v1_body_reads_as_v3() -> None:
    """저장된 v1 본문(일곱 칸 · 그래프 노드)도 읽을 때 v3로(T-13 format 열과 함께 써요)."""
    slots = FX["bodies"][0]["slots"]  # 얼린 bodies()[0]
    body = ct.read_body(slots)
    assert body["converted"] == "v1" and bk.analyze(body["graph"])["problems"] == []
