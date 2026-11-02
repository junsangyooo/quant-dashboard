"""블록 모델(TASKS T-21): ENGINE-RULES 1절(R-G1 ~ R-G12) · 2절(R-P1 ~ R-P12)의 시험 예 전부 +
실행 방식 자리 규칙(R-X2 · 다이아몬드) · 매매 방식(R-M1) · 문장으로 보기(SPEC 4-1).

시험 이름의 번호가 규칙 번호예요. 글자는 그림 V2-23(문제 목록 펼침 · 문장으로 보기)과 SPEC 4-4 그대로예요.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app import blocks as bk
from app.blocks import GraphError, new_block, new_row


def B(bid: str, stage: str, rows: list[dict[str, Any]] | None = None, match: str | None = None) -> dict[str, Any]:
    b = new_block(bid, stage)
    if rows is not None:
        b["rows"] = rows
    if match:
        b["match"] = match
    return b


def R(item: str, op: str | None = None, value: Any = None, exec_: str | None = None, **params: Any) -> dict[str, Any]:
    return new_row(item, op, value=value, params=params or None, exec_=exec_)


def G(blocks: list[dict[str, Any]], *edges: tuple[str, str]) -> dict[str, Any]:
    return {"blocks": blocks, "edges": [{"from": a, "to": b} for a, b in edges]}


def big_breakout() -> dict[str, Any]:
    """SPEC 4-1 문장 예의 전략(그림 V2-23 대형주 돌파와 같은 꼴)."""
    return G(
        [
            B("u", "universe", [R("market", value=["KOSPI", "KOSDAQ"]), R("exclude_preferred")]),
            B("s", "signal", [R("ma", "cross_up", n=20)]),
            B("f", "filter", [R("turnover", "gte", 50)]),
            B("k", "select", [R("top_n", value=5)]),
            B("b", "buy"),
            B("x", "sell", [R("stop_loss", value=7), R("max_hold", value=20)]),
            B("w", "weight"),
        ],
        ("u", "s"), ("s", "f"), ("f", "k"), ("k", "b"), ("b", "x"), ("w", "b"),
    )


def kinds(graph: dict[str, Any], **kw: Any) -> list[str]:
    return [p["kind"] for p in bk.analyze(graph, **kw)["problems"]]


# ── 1. 전략 모양 ─────────────────────────────────────────────────────────────


def test_R_G1_save_and_read_back_same() -> None:
    body = {"name": "대형주 돌파", "graph": big_breakout()}
    once = bk.normalize(json.loads(json.dumps(body, ensure_ascii=False)))
    assert bk.normalize(once) == once
    assert [b["id"] for b in once["graph"]["blocks"]] == ["u", "s", "f", "k", "b", "x", "w"]
    assert once["graph"]["blocks"][5]["rows"][0] == {"item": "stop_loss", "op": "fixed", "params": {}, "value": 7,
                                                     "value2": None, "exec": "intraday"}


def test_R_G2_counts() -> None:
    g = big_breakout()
    assert bk.add_block_reason(g, "weight") == "비중 단계는 하나만 놓을 수 있어요"
    assert bk.add_block_reason(g, "signal") is None
    many = G([B(f"s{i}", "signal") for i in range(20)])
    assert bk.add_block_reason(many, "signal") == "단계는 20개까지 놓을 수 있어요"
    with pytest.raises(GraphError, match="단계는 20개까지"):
        bk.normalize({"name": "x", "graph": G([B(f"s{i}", "signal") for i in range(21)])})
    full = B("f", "filter", [R("price", "gte", 1000) for _ in range(10)])
    assert bk.add_row_reason(full, "volume") == "한 단계에 조건은 10개까지 추가할 수 있어요"


def test_R_G3_toggle_defaults() -> None:
    assert new_block("x", "sell")["match"] == "any"
    assert new_block("s", "signal")["match"] == "all" and new_block("f", "filter")["match"] == "all"
    # 토글 없는 단계는 늘 all
    body = bk.normalize({"name": "x", "graph": G([{**B("u", "universe", [R("market", value=["KOSPI"])]),
                                                    "match": "any"}])})
    assert body["graph"]["blocks"][0]["match"] == "all"


def test_R_G4_items_per_stage() -> None:
    assert bk.add_row_reason(B("s", "signal"), "per") == "PER은 ② 신호 단계에 추가할 수 없어요"
    assert bk.add_row_reason(B("x", "sell"), "profit_state") is None
    with pytest.raises(GraphError, match="② 신호 단계에 추가할 수 없어요"):
        bk.normalize({"name": "x", "graph": G([B("s", "signal", [R("per", "lte", 15)])])})


def test_R_G5_manual_list_is_filtered_by_other_rows() -> None:
    block = B("u", "universe", [R("manual_list", value=["111111", "222222", "333333"]), R("market", value=["KOSDAQ"])])
    info = {"111111": {"market": "KOSPI"}, "222222": {"market": "KOSPI"}, "333333": {"market": "KOSDAQ"}}
    assert bk.universe_symbols(block, info) == ["333333"]


def test_R_G6_select_has_one_row() -> None:
    k = B("k", "select", [R("top_n", value=5)])
    assert bk.add_row_reason(k, "top_n") == "종목 선정 단계에는 조건을 하나만 추가할 수 있어요"


def test_R_G7_buy_cooldown_default_is_one() -> None:
    b = new_block("b", "buy")
    assert b["rows"] == [{"item": "next_open", "op": "fixed", "params": {}, "value": 1, "value2": None, "exec": None}]


def test_R_G8_weight_row_kinds_once() -> None:
    w = new_block("w", "weight")
    assert bk.add_row_reason(w, "equal") == "동일 비중은 하나만 추가할 수 있어요"
    assert bk.add_row_reason(w, "max_per_stock") is None


def test_R_G9_entry_paths_or_between_and_within() -> None:
    g = G(
        [B("u", "universe", [R("manual_list", value=["111111"])]),
         B("s1", "signal", [R("high_n", "cross_up", n=20)]), B("s2", "signal", [R("ma", "cross_up", n=60)]),
         B("f", "filter", [R("turnover", "gte", 100)]), B("k", "select", [R("top_n", value=5)]), B("b", "buy"),
         B("w", "weight")],
        ("u", "s1"), ("u", "s2"), ("s1", "k"), ("s2", "f"), ("f", "k"), ("k", "b"), ("w", "b"),
    )
    paths = bk.entry_paths(g)
    assert [p["blocks"] for p in paths] == [["u", "s1", "k", "b"], ["u", "s2", "f", "k", "b"]]
    # 갈래 둘 중 하나만 통과 → 후보
    passed = {"u": True, "s1": False, "s2": True, "f": True, "k": True, "b": True}
    assert bk.paths_pass(paths, passed) == [1]
    # '하나라도' 블록에서 한 줄만 맞음 → 통과
    any_block = B("s", "signal", [R("ma", "cross_up", n=5), R("rsi", "lt", 30, period=14)], match="any")
    assert bk.block_pass(any_block, [False, True]) is True
    assert bk.block_pass({**any_block, "match": "all"}, [False, True]) is False


def test_R_G10_chained_sells_all_same_day() -> None:
    g = G([B("b", "buy"), B("x1", "sell", [R("stop_loss", value=7)]), B("x2", "sell", [R("take_profit", value=15)])],
          ("b", "x1"), ("x1", "x2"))
    paths = bk.sell_paths(g)
    assert [p["blocks"] for p in paths] == [["b", "x1", "x2"]]
    assert bk.paths_pass(paths, {"x1": True, "x2": False}, skip=("b",)) == []
    assert bk.paths_pass(paths, {"x1": True, "x2": True}, skip=("b",)) == [0]


def test_R_G11_weight_only_into_buy() -> None:
    g = G([B("b", "buy"), B("x", "sell", [R("stop_loss", value=7)]), B("w", "weight")], ("b", "x"))
    assert bk.edge_reason(g, "w", "x") == "비중 단계는 매수 단계에 연결해요"
    assert bk.edge_reason(g, "w", "b") is None


def test_R_G12_link_rules_cycle_and_path_limit() -> None:
    g = G([B("u", "universe"), B("s1", "signal"), B("s2", "signal"), B("b", "buy")], ("u", "s1"), ("s1", "s2"))
    assert bk.edge_reason(g, "s2", "s1") == "선이 이미 지나온 조건으로 돌아가면 안 돼요"
    assert bk.edge_reason(g, "b", "s1") == "신호 · 필터 단계는 매수 단계 앞에 이어요"
    assert bk.edge_reason(g, "s1", "u") == "유니버스 단계 앞에는 다른 단계를 연결할 수 없어요"
    assert bk.edge_reason(g, "u", "s1") == "이미 연결돼 있어요"
    # ④가 있으면 ② · ③ → ⑤ 막음
    g4 = G([B("u", "universe"), B("s", "signal"), B("k", "select"), B("b", "buy")], ("u", "s"))
    assert bk.edge_reason(g4, "s", "b") == "종목 선정 단계는 매수 단계 바로 앞에 하나만 놓아요"
    # ⑥ → ⑥은 이유 없음 · 확인 창
    gs = G([B("b", "buy"), B("x1", "sell", [R("stop_loss", value=7)]), B("x2", "sell", [R("max_hold", value=20)])],
           ("b", "x1"), ("b", "x2"))
    assert bk.edge_reason(gs, "x1", "x2") is None
    assert bk.needs_confirm(gs, "x1", "x2") == (
        "이어서 연결한 매도 조건은 같은 날 모두 맞아야 해요",
        "하나라도 맞으면 팔려면 같은 단계 안으로 옮겨요",
        "그래도 연결하면 손절 −7%는 종가 확인으로 바뀌고, 최대 보유 20거래일과 같은 날 맞아야 팔려요",
    )


def test_R_G12_path_limit_exact() -> None:
    """진입 경로 20개는 되고 21번째는 막혀요."""
    blocks = [B("u", "universe"), B("b", "buy")]
    edges: list[tuple[str, str]] = []
    for i in range(5):
        blocks.append(B(f"s{i}", "signal"))
    for j in range(4):
        blocks.append(B(f"f{j}", "filter"))
        edges.append((f"f{j}", "b"))
    for i in range(5):
        for j in range(4):
            edges.append((f"s{i}", f"f{j}"))
    edges += [("u", f"s{i}") for i in range(4)]  # 신호 4 × 필터 4 = 16 · s4는 아직 ①에서 안 이어짐
    g = G(blocks, *edges)
    assert len(bk.entry_paths(g)) == 16
    assert bk.edge_reason(g, "u", "s4") is None  # 16 + 4 = 20개까지는 돼요
    blocks.append(B("f4", "filter"))
    g = G(blocks, *[e for e in edges], ("f4", "b"), ("s0", "f4"), ("s1", "f4"), ("s2", "f4"), ("s3", "f4"))
    assert len(bk.entry_paths(g)) == 20
    assert bk.edge_reason(g, "u", "s4") == "경로가 너무 많아요 · 진입 경로는 최대 20개예요"


def test_delete_block_keeps_gap() -> None:
    """블록을 삭제하면 선도 삭제하고 앞뒤를 잇지 않아요(끊긴 곳은 문제)."""
    g = big_breakout()
    g["blocks"] = [b for b in g["blocks"] if b["id"] != "f"]
    g["edges"] = [e for e in g["edges"] if "f" not in (e["from"], e["to"])]
    assert "dead" in kinds(g)


# ── 2. 문제 목록 ─────────────────────────────────────────────────────────────


def test_no_problems_for_full_strategy() -> None:
    a = bk.analyze(big_breakout())
    assert a["problems"] == [] and a["mode"] == "event"
    assert a["summary"] == {"title": "문제 없음 · 모두 채웠어요", "line": "저장하면 백테스트할 수 있어요"}


def test_R_P1_blank_and_range() -> None:
    g = big_breakout()
    g["blocks"][2]["rows"] = [R("per", "lte", 1200), R("per", "lte", None), R("turnover", "gte", 200_000)]
    ps = bk.analyze(g)["problems"]
    assert [(p["kind"], p["title"], p["detail"]) for p in ps] == [
        ("range", "PER은 0~1,000배로 입력해요", "③ 필터 · 지금 1,200배"),
        ("blank", "PER 값이 비어 있어요", "③ 필터 · PER은 0~1,000배로 입력해요"),
        ("range", "거래대금은 0.1~100,000억 원으로 입력해요", "③ 필터 · 지금 200,000억 원"),
    ]


def test_R_P2_between_order() -> None:
    g = big_breakout()
    g["blocks"][2]["rows"] = [{**R("per", "between", 20), "value2": 10}]
    ps = bk.analyze(g)["problems"]
    assert [(p["kind"], p["title"]) for p in ps] == [("order", "앞 값이 뒤 값보다 커요")]


def test_R_P3_empty_stage() -> None:
    g = big_breakout()
    g["blocks"][2]["rows"] = []
    ps = bk.analyze(g)["problems"]
    assert [(p["kind"], p["title"]) for p in ps] == [("empty", "조건이 없는 단계예요 · 조건을 추가하거나 단계를 삭제해요")]


def test_R_P4_locked_without_dart() -> None:
    g = big_breakout()
    g["blocks"][2]["rows"].append(R("per", "lte", 15))
    assert kinds(g, dart=True) == []
    ps = bk.analyze(g, dart=False)["problems"]
    assert [(p["kind"], p["title"]) for p in ps] == [("locked", "PER은 DART를 연결해야 써요 · 연결 ›")]


def test_R_P5_cannot_be_true_same_day() -> None:
    g = big_breakout()
    g["blocks"][5] = B("x", "sell", [R("stop_loss", value=7), R("take_profit", value=15)], match="all")
    ps = [p for p in bk.analyze(g)["problems"] if p["kind"] == "conflict"]
    assert [(p["title"], p["detail"]) for p in ps] == [
        ("같은 날 함께 맞을 수 없는 조건이에요", "손절 −7%와 익절 +15% · 이 경로로는 팔지 않아요")]
    # 같은 선의 위 + 아래, 이상 a + 이하 b(a > b)
    g2 = big_breakout()
    g2["blocks"][2]["rows"] = [R("ma", "above", n=20), R("ma", "below", n=20), R("price", "gte", 20000),
                               R("price", "lte", 10000)]
    assert [p["kind"] for p in bk.analyze(g2)["problems"]].count("conflict") == 2
    # '하나라도' 블록의 손절 + 익절은 문제가 아니에요
    assert "conflict" not in kinds(G(big_breakout()["blocks"][:5] + [
        B("x", "sell", [R("stop_loss", value=7), R("take_profit", value=15)], match="any"), B("w", "weight")],
        ("u", "s"), ("s", "f"), ("f", "k"), ("k", "b"), ("b", "x"), ("w", "b")))


def test_R_P6_no_signal() -> None:
    g = big_breakout()
    g["blocks"] = [b for b in g["blocks"] if b["id"] != "s"]
    g["edges"] = [e for e in g["edges"] if "s" not in (e["from"], e["to"])] + [{"from": "u", "to": "f"}]
    ps = bk.analyze(g)["problems"]
    assert [p["title"] for p in ps] == ["진입 경로 1에 신호가 없어요 · 신호 없이 연결하면 매일 모든 종목이 매수 후보가 돼요"]
    # 순위 교체 + 'PER 낮은 순' + 신호 없음 → 문제 아님
    next(b for b in g["blocks"] if b["id"] == "k")["rows"] = [R("top_n", value=10, by="per", order="asc")]
    g["blocks"] = [b for b in g["blocks"] if b["stage"] != "sell"]
    g["edges"] = [e for e in g["edges"] if e["to"] != "x"]
    w = next(b for b in g["blocks"] if b["stage"] == "weight")
    w["rows"].append(R("rebalance_every", value=20, how="rank"))
    assert bk.mode_of(g) == "rank"
    assert kinds(g) == []


def test_R_P7_required() -> None:
    g = big_breakout()
    g["blocks"] = [b for b in g["blocks"] if b["stage"] != "sell"]
    g["edges"] = [e for e in g["edges"] if e["to"] != "x"]
    ps = bk.analyze(g)["problems"]
    assert [p["title"] for p in ps] == ["필요한 조건 · 조건 충족 시 매매에는 매도 경로가 하나 이상 있어야 해요"]
    empty = G([])
    titles = [p["title"] for p in bk.analyze(empty)["problems"]]
    assert titles == ["필요한 조건 · 유니버스 단계가 있어야 해요", "필요한 조건 · 매수 단계가 있어야 해요",
                      "필요한 조건 · 동일 비중 조건이 있어야 해요",
                      "필요한 조건 · 조건 충족 시 매매에는 종목 선정 단계가 있어야 해요",
                      "필요한 조건 · 조건 충족 시 매매에는 매도 경로가 하나 이상 있어야 해요"]


def test_R_P8_target_has_no_sell() -> None:
    g = big_breakout()
    next(b for b in g["blocks"] if b["stage"] == "weight")["rows"].append(R("rebalance_every", value=20, how="target"))
    assert bk.mode_of(g) == "target"
    ps = [p for p in bk.analyze(g)["problems"] if p["kind"] == "unusable"]
    assert [p["title"] for p in ps] == ["목표 비중 리밸런싱에서는 매도 단계를 쓰지 않아요"]


def test_R_P9_rebalance_how_blank() -> None:
    g = big_breakout()
    next(b for b in g["blocks"] if b["stage"] == "weight")["rows"].append(R("rebalance_every", value=20))
    assert bk.mode_of(g) is None
    ps = bk.analyze(g)["problems"]
    assert [(p["kind"], p["title"]) for p in ps] == [("blank", "리밸런싱 방식 값이 비어 있어요")]


def test_R_P10_loose_block() -> None:
    g = big_breakout()
    g["blocks"].append(B("f2", "filter", [R("price", "gte", 1000)]))
    ps = bk.analyze(g)["problems"]
    assert [(p["kind"], p["title"], p["block"]) for p in ps] == [("loose", "선으로 연결해야 전략에 들어가요", "f2")]


def test_R_P11_stop_with_other_rows_is_a_warning() -> None:
    g = big_breakout()
    g["blocks"][5] = B("x", "sell", [R("stop_loss", value=7), R("max_hold", value=20)], match="all")
    a = bk.analyze(g)
    assert a["problems"] == []
    assert [(w["title"], w["detail"]) for w in a["warnings"]] == [
        ("손절이 다른 조건과 같은 날 맞아야 팔려요", "−7%보다 내려가도 안 팔릴 수 있어요")]
    assert a["summary"]["title"] == "문제 없음 · 모두 채웠어요"


def test_R_P12_loading_is_not_a_problem() -> None:
    g = big_breakout()
    assert kinds(g) == []
    assert bk.backtest_wait({"dart": 40}) == "DART 재무를 받는 중이에요 · 40% · 끝나면 백테스트할 수 있어요"
    assert bk.backtest_wait(None) is None


def test_problem_header_lines() -> None:
    assert bk.summary_line(2, 1, 1) == {"title": "문제 2 · 빈칸 1", "line": "백테스트를 할 수 없어요 · 경고 1"}


# ── 실행 방식 자리 규칙 (R-X2) · 손절 없음 (R-X10) ──────────────────────────


def test_R_X2_place_rules() -> None:
    g = big_breakout()
    assert bk.exec_of(g, "x", 0) == "intraday"  # '하나라도' · ⑤ 바로 뒤 · 뒤에 ⑥ 없음
    g["blocks"][5]["match"] = "all"
    assert bk.exec_of(g, "x", 0) == "close"
    assert bk.exec_chip(g, "x", 0) == {"exec": "close", "name": "종가 확인",
                                       "reason": "다른 조건과 함께 맞아야 해서 종가로 확인해요"}
    # 다이아몬드: ⑤ → ⑥a → ⑥b와 ⑤ → ⑥b가 함께 있는 ⑥b의 손절 → 종가 확인
    d = G([B("b", "buy"), B("xa", "sell", [R("take_profit", value=15)]), B("xb", "sell", [R("stop_loss", value=7)])],
          ("b", "xa"), ("xa", "xb"), ("b", "xb"))
    assert bk.exec_of(d, "xb", 0) == "close"
    assert bk.exec_of(d, "xa", 0) == "close"  # 뒤에 이어진 ⑥이 있어요
    # 줄 하나짜리 '모두' 블록은 혼자 정해요
    one = G([B("b", "buy"), B("x", "sell", [R("stop_loss", value=7)], match="all")], ("b", "x"))
    assert bk.exec_of(one, "x", 0) == "intraday"


def test_R_X10_no_stop() -> None:
    assert bk.has_stop(big_breakout()) is True
    g = big_breakout()
    g["blocks"][5]["match"] = "all"  # '모두' 블록에만 손절 → 손절 없음
    assert bk.has_stop(g) is False


# ── 매매 방식 (R-M1) · 문장으로 보기 ─────────────────────────────────────────


def test_R_M1_mode_change_note() -> None:
    a = big_breakout()
    b = json.loads(json.dumps(a))
    next(x for x in b["blocks"] if x["stage"] == "weight")["rows"].append(R("rebalance_every", value=20, how="rank"))
    assert bk.mode_of(b) == "rank"
    assert bk.mode_change_note(b, a) == "방식이 바뀌면 돌파 신호의 뜻도 바뀌어요"  # 리밸런싱 줄 삭제 → 방식 바뀜


def test_sentence_spec_example() -> None:
    body = {"name": "x", "graph": big_breakout()}
    assert bk.sentence(body) == (
        "코스피 · 코스닥 보통주 가운데 20일 이동평균선을 상향 돌파하고 거래대금이 50억 원 이상인 종목을, "
        "신호 강도가 높은 순으로 5종목까지 다음 날 시가에 사요. 손절 −7%(장중 감시)에 닿거나 20거래일이 지나면 팔아요. "
        "같은 금액으로 나눠 사요."
    )


def test_sentence_blanks_and_branches() -> None:
    g = big_breakout()
    g["blocks"][1]["rows"][0]["params"]["n"] = None
    text = bk.sentence({"name": "x", "graph": g})
    assert text.startswith("코스피 · 코스닥 보통주 가운데 [빈칸] 이동평균선을 상향 돌파하고")
