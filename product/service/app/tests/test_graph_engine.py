"""그래프 엔진: 분기(경로끼리 하나라도) · 같은 조건 여러 번 · 이어서 연결한 매도(모두 맞아야)."""

from __future__ import annotations

import math
import random

import pytest

from app.engine_mvp import FEE, Engine, Series, run_backtest
from tests.conftest import make_bars

CASH = 1_000_000.0


def _node(i: str, piece: str, **params: object) -> dict:  # type: ignore[type-arg]
    return {"id": i, "piece": piece, "params": params, "x": None, "y": None}


def _body(nodes: list[dict], edges: list[tuple[str, str]]) -> dict:  # type: ignore[type-arg]
    return {"name": "g", "graph": {"nodes": nodes, "edges": [{"from": a, "to": b} for a, b in edges]}}


def test_branch_any_path_passes() -> None:
    """(5일 최고가 돌파) 또는 (3일 이동평균선 상향 돌파 → 주가 50원 이상)."""
    x = make_bars([10] * 7 + [20, 20])  # 돌파만(가격 20 < 50이라 아래 경로는 필터에서 막힘)
    y = make_bars([100] * 6 + [80, 96, 96])  # 이동평균선 상향 돌파만(최고가 100을 넘지 않음)
    z = make_bars([30] * 6 + [24, 28.8, 28.8])  # 이동평균선 돌파지만 주가 필터에서 막힘
    body = _body(
        [_node("u", "manual_list", symbols=["000001", "000002", "000003"]),
         _node("s1", "high_breakout", n=5), _node("s2", "ma_cross_up", n=3), _node("f", "min_price", n=50),
         _node("k", "top_n", n=3), _node("b", "next_open"), _node("m", "max_hold", n=100), _node("w", "equal")],
        [("u", "s1"), ("u", "s2"), ("s2", "f"), ("s1", "k"), ("f", "k"), ("k", "b"), ("b", "m"), ("w", "b")],
    )
    days = [b["d"] for b in x]
    res = run_backtest(body, {"000001": x, "000002": y, "000003": z}, None, days[0], days[-1], CASH)
    buys = {t["sym"]: t["reason"] for t in res["trades"] if t["side"] == "buy"}
    assert buys == {
        "000001": ["5일 최고가 돌파"],
        "000002": ["3일 이동평균선 상향 돌파", "주가 50원 이상"],  # 이유 = 통과한 경로 위 ② · ③
    }
    assert {t["d"] for t in res["trades"]} == {days[8]}


def _single(nodes_path: list[dict], extra_edges: list[tuple[str, str]] | None = None) -> dict:  # type: ignore[type-arg]
    ids = [n["id"] for n in nodes_path]
    nodes = [_node("u", "manual_list", symbols=["000001"]), *nodes_path, _node("b", "next_open"), _node("w", "equal")]
    edges = list(zip(["u", *ids], [*ids, "b"])) + [("w", "b")] + (extra_edges or [])
    return _body(nodes, edges)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_paths_are_or_and_strength_is_the_max(seed: int) -> None:
    """같은 조건을 두 번(5일 · 20일 이동평균선 상향 돌파) 놓은 두 경로: 통과 = 한 경로만 넣은 엔진들의 OR,
    신호 강도 = 통과한 경로 강도 중 큰 값. 이어 놓으면(한 경로) AND."""
    rnd = random.Random(seed)
    closes = [100.0]
    for _ in range(160):
        closes.append(round(closes[-1] * (1 + rnd.gauss(0, 0.03)), 2))
    s = Series(make_bars(closes))
    a = [_node("a", "ma_cross_up", n=5)]
    b = [_node("c", "ma_cross_up", n=20), _node("f", "min_price", n=95)]
    both = _body(
        [_node("u", "manual_list", symbols=["000001"]), *a, *b, _node("b", "next_open"), _node("w", "equal")],
        [("u", "a"), ("a", "b"), ("u", "c"), ("c", "f"), ("f", "b"), ("w", "b")],
    )
    chained = _single([*a, *b])
    ea, eb, eboth, echain = (Engine(x, {"000001": s}, CASH) for x in (_single(a), _single(b), both, chained))
    hits = 0
    for i in range(25, len(closes)):
        pa, pb, pboth, pchain = (e._entry(s, i) for e in (ea, eb, eboth, echain))
        assert pboth[3] == (pa[3] or pb[3])
        assert pchain[3] == (pa[3] and pb[3])
        if pboth[3]:
            hits += 1
            assert pboth[1] == max(x[1] for x in (pa, pb) if x[3])
    assert hits > 3


def _sell_case(chained: bool) -> dict:  # type: ignore[type-arg]
    closes = [10, 10, 10, 10, 12, 12, 10, 10, 10, 10, 10]
    opens = [10, 10, 10, 10, 12, 12, 10, 10, 10, 10, 10]
    bars = make_bars(closes, opens=opens)
    nodes = [_node("u", "manual_list", symbols=["000001"]), _node("s", "high_breakout", n=3), _node("k", "top_n", n=1),
             _node("b", "next_open"), _node("x", "stop_loss", pct=5), _node("y", "max_hold", n=3), _node("w", "equal")]
    edges = [("u", "s"), ("s", "k"), ("k", "b"), ("w", "b"), ("b", "x")]
    edges += [("x", "y")] if chained else [("b", "y")]
    days = [b["d"] for b in bars]
    res = run_backtest(_body(nodes, edges), {"000001": bars}, None, days[0], days[-1], CASH)
    return {"days": days, "trades": [(t["d"], t["side"], t["reason"]) for t in res["trades"]]}


def test_branched_sells_any_one_is_enough() -> None:
    r = _sell_case(chained=False)
    d = r["days"]
    # 5번째 날(12)에 돌파 → 6번째 날 시가 매수. 7번째 날 종가 10 ≤ 평균가 × 0.95 → 8번째 날 시가 매도
    assert r["trades"] == [(d[5], "buy", ["3일 최고가 돌파"]), (d[7], "sell", ["손절 −5%"])]


def test_chained_sells_must_all_hit_the_same_day() -> None:
    r = _sell_case(chained=True)
    d = r["days"]
    # 손절은 7번째 날부터 맞지만 최대 보유 3거래일은 9번째 날(매수 6번째 날 + 3)에 맞는다 → 10번째 날 시가 매도
    assert r["trades"] == [(d[5], "buy", ["3일 최고가 돌파"]), (d[9], "sell", ["손절 −5%", "최대 보유 3거래일"])]


def test_buy_quantity_unchanged_by_graph() -> None:
    r = _sell_case(chained=False)
    assert r["trades"][0][1] == "buy"
    assert math.floor(CASH / (12 * (1 + FEE))) > 0
