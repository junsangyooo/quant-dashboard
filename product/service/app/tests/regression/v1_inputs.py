"""변환 일치 문턱(R-C10 · TASKS T-02 · T-24)의 입력: v1 전략과 일봉.

- 회귀 사례: `cases.bodies()`(일곱 칸 본문) × 씨앗 3개 = 백테스트 252건(`regression_baseline.json`과 같은 행),
  모의투자 10건.
- 옛 예시 4개: v1 앱에 들어 있던 예시 전략(`app/v1/strategy.py` EXAMPLES). 종목은 대형주 10종목 코드라
  그 코드로 가짜 일봉을 만들어요.
- 무작위 그래프: `random_graph(seed)`가 v1 조건 15개로 맞는 그래프를 만들어요. 같은 씨앗이면 같은 그래프예요.

결과(거래 목록)는 `make_v1_trades.py`가 v1 엔진(`app/engine_v1.py`)으로 돌려 `tests/fixtures/v1_trades.json`에 고정해요.
"""

from __future__ import annotations

import random
from typing import Any

from app.v1 import strategy as st1
from tests.regression.cases import SEEDS, SYMS, bar_set

RANDOM_COUNT = 60  # 무작위 그래프 수(씨앗 0 ~ 59)
RANDOM_SEED_BASE = 20261102


def example_bodies() -> list[dict[str, Any]]:
    return [st1.example_body(e["id"]) for e in st1.EXAMPLES]


def example_bars(seed: int = SEEDS[0]) -> dict[str, list[dict[str, Any]]]:
    """대형주 10종목 코드에 가짜 일봉을 붙여요(회귀 일봉 두 묶음을 이어 써요)."""
    a = bar_set(seed)
    b = bar_set(seed + 1)
    rows = [*a.values(), *b.values()]
    return {sym: rows[i] for i, sym in enumerate(st1.BIG10)}


def _node(nid: str, piece: str, **params: Any) -> dict[str, Any]:
    return {"id": nid, "piece": piece, "params": params, "x": 0, "y": 0}


def _signal(rnd: random.Random, nid: str) -> dict[str, Any]:
    kind = rnd.choice(["ma_cross_up", "rsi_below", "high_breakout"])
    if kind == "ma_cross_up":
        return _node(nid, kind, n=rnd.choice([3, 5, 10, 20, 40]))
    if kind == "rsi_below":
        return _node(nid, kind, period=rnd.choice([5, 7, 14]), level=rnd.choice([30, 40, 45, 50]))
    return _node(nid, kind, n=rnd.choice([5, 10, 20, 40]))


def _filter(rnd: random.Random, nid: str) -> dict[str, Any]:
    if rnd.random() < 0.5:
        return _node(nid, "min_turnover", n=rnd.choice([1, 5, 20, 50]))
    return _node(nid, "min_price", n=rnd.choice([5000, 10000, 30000, 80000]))


def _sell(rnd: random.Random, nid: str) -> dict[str, Any]:
    kind = rnd.choice(["stop_loss", "take_profit", "max_hold", "ma_break_down"])
    if kind == "stop_loss":
        return _node(nid, kind, pct=rnd.choice([3, 5, 8, 12]))
    if kind == "take_profit":
        return _node(nid, kind, pct=rnd.choice([5, 10, 20, 40]))
    if kind == "max_hold":
        return _node(nid, kind, n=rnd.choice([3, 10, 20, 60]))
    return _node(nid, kind, n=rnd.choice([5, 10, 20]))


def _try_graph(rnd: random.Random) -> dict[str, Any]:
    mode = rnd.choice(["event", "event", "rank", "target"])
    nodes = [_node("u1", "manual_list", symbols=rnd.sample(SYMS, rnd.randint(2, 6)))]
    edges: list[dict[str, str]] = []
    has_select = mode != "target" or rnd.random() < 0.5
    if has_select:
        nodes.append(_node("k1", "top_n", n=rnd.randint(1, 4)))
    nodes.append(_node("b1", "next_open"))
    entry_end = "k1" if has_select else "b1"
    # 진입 경로 1~3개: 경로마다 신호 0~2(목표 비중 밖에서는 1~2) → 필터 0~2, 줄줄이
    n_paths = rnd.choice([1, 1, 2, 3])
    count = 0
    for _ in range(n_paths):
        chain = []
        for _ in range(rnd.randint(0 if mode == "target" else 1, 2)):
            count += 1
            nodes.append(_signal(rnd, f"s{count}"))
            chain.append(f"s{count}")
        for _ in range(rnd.randint(0, 2)):
            count += 1
            nodes.append(_filter(rnd, f"f{count}"))
            chain.append(f"f{count}")
        prev = "u1"
        for nid in chain:
            edges.append({"from": prev, "to": nid})
            prev = nid
        edges.append({"from": prev, "to": entry_end})
    if has_select:
        edges.append({"from": "k1", "to": "b1"})
    # 매도 경로(목표 비중에는 없음): ⑤에서 0~3갈래, 갈래마다 1~2개를 줄줄이(같은 날 모두 맞아야 팔림)
    if mode != "target":
        for _ in range(rnd.choice([0, 1, 2, 2, 3]) if mode == "event" else rnd.choice([0, 1])):
            prev = "b1"
            for _ in range(rnd.choice([1, 1, 2])):
                count += 1
                nodes.append(_sell(rnd, f"x{count}"))
                edges.append({"from": prev, "to": f"x{count}"})
                prev = f"x{count}"
    # 비중
    nodes.append(_node("w1", "equal"))
    edges.append({"from": "w1", "to": "b1"})
    if rnd.random() < 0.4:
        nodes.append(_node("w2", "max_per_stock", pct=rnd.choice([20, 30, 50])))
        edges.append({"from": "w2", "to": "b1"})
    if mode != "event":
        nodes.append(_node("w3", "rebalance_every", n=rnd.choice([1, 5, 10, 20]), how=mode))
        edges.append({"from": "w3", "to": "b1"})
    # 같은 선 두 번은 하나로
    seen: set[tuple[str, str]] = set()
    uniq = []
    for e in edges:
        key = (e["from"], e["to"])
        if key not in seen:
            seen.add(key)
            uniq.append(e)
    return {"name": "무작위", "graph": {"nodes": nodes, "edges": uniq}}


def random_graph(seed: int) -> dict[str, Any]:
    """씨앗 하나로 문제 없는 v1 그래프 하나. 문제가 있으면 같은 난수열로 다시 만들어요(결정적)."""
    rnd = random.Random(RANDOM_SEED_BASE + seed)
    for _ in range(200):
        body = _try_graph(rnd)
        if st1.validate(st1.normalize(body)) == []:
            return body
    raise RuntimeError(f"seed {seed}: no valid graph")


def random_bodies() -> list[dict[str, Any]]:
    return [random_graph(i) for i in range(RANDOM_COUNT)]


def random_bars(seed: int) -> dict[str, list[dict[str, Any]]]:
    """무작위 그래프 i는 회귀 일봉 씨앗 SEEDS[i % 3]을 써요."""
    return bar_set(SEEDS[seed % len(SEEDS)])
