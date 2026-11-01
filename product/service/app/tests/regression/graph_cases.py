"""화면(web/src/graph/rules.ts)과 서버(app/graph.py)가 같은 검사 결과를 내는지 대조할 그래프들.

    cd mvp && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tests.regression.graph_cases --write

web/tests/fixtures/graph_cases.json에 그래프마다 서버 결과(analyze · edge_reason · add_reason)를 적는다.
tests/test_graph_mirror.py는 이 파일이 지금 서버 결과와 같은지, web/tests/graphMirror.test.ts는 화면 결과가
이 파일과 같은지 본다.
"""

from __future__ import annotations

import copy
import json
import random
import sys
from pathlib import Path
from typing import Any

from app import graph as gr
from app import strategy as st

OUT = Path(__file__).resolve().parents[2] / "web" / "tests" / "fixtures" / "graph_cases.json"
PIECE_IDS = list(st.PIECES)


def _rand_value(rnd: random.Random, p: dict[str, Any]) -> Any:
    kind = p.get("kind")
    if kind == "symbols":
        return rnd.choice([[], ["005930"], ["005930", "000660", "005380"], ["5930", "AAPL"], [f"{i:06d}" for i in range(31)], st.BIG10])
    if kind == "choice":
        return rnd.choice([None, "target", "rank"])
    lo, hi = p["min"], p["max"]
    return rnd.choice([None, lo, hi, (lo + hi) / 2, round(rnd.uniform(lo, hi), 2), hi + 1, lo - 1, 2.5, "abc", True,
                       int(lo) + 3 if p["integer"] else round(lo + 0.37, 2)])


def _random_graph(rnd: random.Random) -> dict[str, Any]:
    start = rnd.choice(["blank", "breakout", "either", "equal", "trend", "empty"])
    if start == "blank":
        g = st.blank_body()["graph"]
    elif start == "empty":
        g = {"nodes": [], "edges": []}
    else:
        g = st.example_body(start)["graph"]
    g = copy.deepcopy(g)
    nid = 0
    for _ in range(rnd.randint(0, 14)):
        op = rnd.random()
        if op < 0.35:
            piece = rnd.choice(PIECE_IDS)
            if gr.add_reason(g, piece) is None:
                nid += 1
                params = {p["key"]: _rand_value(rnd, p) for p in st.PIECES[piece]["params"]}
                g["nodes"].append({"id": f"r{nid}", "piece": piece, "params": params,
                                   "x": rnd.choice([None, round(rnd.uniform(0, 900), 1)]),
                                   "y": rnd.choice([None, round(rnd.uniform(0, 700), 1)])})
        elif op < 0.75 and len(g["nodes"]) >= 2:
            a, b = rnd.sample([n["id"] for n in g["nodes"]], 2)
            if gr.edge_reason(g, a, b) is None:
                g["edges"].append({"from": a, "to": b})
        elif op < 0.85 and g["edges"]:
            g["edges"].pop(rnd.randrange(len(g["edges"])))
        elif op < 0.92 and g["nodes"]:
            victim = rnd.choice(g["nodes"])["id"]
            g["nodes"] = [n for n in g["nodes"] if n["id"] != victim]
            g["edges"] = [e for e in g["edges"] if victim not in (e["from"], e["to"])]
        elif g["nodes"]:
            n = rnd.choice(g["nodes"])
            for p in st.PIECES[n["piece"]]["params"]:
                n["params"][p["key"]] = _rand_value(rnd, p)
    return g


def _special() -> list[dict[str, Any]]:
    out = []
    # ④를 나중에 놓아 ② → ⑤가 남은 그래프(연결 규칙 문제)
    g = st.example_body("either")["graph"]
    g = copy.deepcopy(g)
    g["nodes"] = [n for n in g["nodes"] if n["id"] != "k1"]
    g["edges"] = [e for e in g["edges"] if "k1" not in (e["from"], e["to"])] + [
        {"from": "s1", "to": "b1"}, {"from": "f1", "to": "b1"}]
    g["nodes"].append({"id": "k9", "piece": "top_n", "params": {"n": 3}, "x": 700, "y": 100})
    out.append(g)
    # 20개 진입 경로(한도) · 매도 이어서 연결
    nodes = [{"id": "u", "piece": "manual_list", "params": {"symbols": ["005930"]}, "x": 0, "y": 0},
             {"id": "b", "piece": "next_open", "params": {}, "x": 600, "y": 0},
             {"id": "w", "piece": "equal", "params": {}, "x": 400, "y": 300}]
    edges = [{"from": "w", "to": "b"}]
    for i in range(5):
        nodes.append({"id": f"s{i}", "piece": "ma_cross_up", "params": {"n": 5 + i}, "x": 200, "y": 40 * i})
        edges.append({"from": "u", "to": f"s{i}"})
    for j in range(4):
        nodes.append({"id": f"f{j}", "piece": "min_price", "params": {"n": 1000 * (j + 1)}, "x": 400, "y": 50 * j})
        edges.append({"from": f"f{j}", "to": "b"})
        for i in range(5):
            edges.append({"from": f"s{i}", "to": f"f{j}"})
    nodes += [{"id": "x1", "piece": "stop_loss", "params": {"pct": 5}, "x": 800, "y": 0},
              {"id": "x2", "piece": "max_hold", "params": {"n": 10}, "x": 1000, "y": 0}]
    edges += [{"from": "b", "to": "x1"}, {"from": "x1", "to": "x2"}]
    out.append({"nodes": nodes, "edges": edges})
    return out


def build() -> dict[str, Any]:
    rnd = random.Random(20261030)
    graphs: list[dict[str, Any]] = [copy.deepcopy(st.blank_body()["graph"]), {"nodes": [], "edges": []}]
    graphs += [copy.deepcopy(st.example_body(e["id"])["graph"]) for e in st.EXAMPLES]
    graphs += _special()
    while len(graphs) < 260:
        graphs.append(_random_graph(rnd))
    cases = []
    for g in graphs:
        ids = [n["id"] for n in g["nodes"]]
        pairs = [(a, b) for a in ids for b in ids]
        if len(pairs) > 40:
            pairs = rnd.sample(pairs, 40)
        cases.append({
            "graph": g,
            "analysis": gr.analyze(g),
            "edges": [[a, b, gr.edge_reason(g, a, b)] for a, b in pairs],
            "adds": {p: gr.add_reason(g, p) for p in PIECE_IDS},
        })
    cat = st.catalog()
    return {"catalog": {"pieces": cat["pieces"], "slots": cat["slots"], "names": cat["names"]}, "cases": cases}


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


if __name__ == "__main__":
    text = dumps(build())
    if "--write" in sys.argv:
        OUT.write_text(text, encoding="utf-8")
        print("wrote", OUT, len(text))
    else:
        print(len(text))
