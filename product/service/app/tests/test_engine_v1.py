"""v1 엔진 고정 · 회귀 입력(TASKS T-02 · SPEC 4-8 · ENGINE-RULES R-C10).

- `app/v1/`은 39dedac의 v1 엔진 · 그래프 컴파일 · 조건 정의 · 전략 코드를 글자 그대로 복사한 것(SHA-256).
- `engine_v1`로 돌린 결과가 `regression_baseline.json`(일곱 칸 엔진으로 만든 기준)과 같아요.
- `v1_trades.json`(T-24가 비교할 거래 목록)은 v1 엔진으로 다시 돌린 결과와 같고, 무작위 그래프는 씨앗으로 다시 만들어져요.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from app.engine_v1 import run_v1
from tests.regression.cases import SEEDS, YAHOO, bar_set, bodies, digest, trade_key, yahoo_body
from tests.regression.make_v1_trades import CASH
from tests.regression.v1_inputs import (
    RANDOM_COUNT,
    example_bars,
    example_bodies,
    random_bars,
    random_bodies,
    random_graph,
)

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
BASE = json.loads((FIX / "regression_baseline.json").read_text())
V1 = json.loads((FIX / "v1_trades.json").read_text())
CASES = bodies()
BARS = {seed: bar_set(seed) for seed in SEEDS}

FROZEN = {
    "engine.py": "84a33cf8dc845e59a25b818dfb4243348e1cca3e353b30215c55af1be4ff0309",
    "graph.py": "97eb39cb11c6dfd40f71ce9dce2c9ba816a43e8c6baa5e20b1acea544df36ea5",
    "pieces.py": "d3a3e996b8ac5a6eb85a41be842c5ba63a21e788832b186f0267a0b28907bf07",
    "strategy.py": "7c33cffccc7dd0ac10631f26d4ac22a9cc3e10558b70acbe534eff5bc711f7ff",
}


def test_v1_files_are_frozen() -> None:
    for name, sha in FROZEN.items():
        assert hashlib.sha256((ROOT / "app" / "v1" / name).read_bytes()).hexdigest() == sha, name


def test_v1_imports_only_itself() -> None:
    for path in (ROOT / "app" / "v1").glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.ImportFrom) and node.level:
                assert node.level == 1, f"{path.name}: v1 밖을 가져와요"


def test_only_tests_use_v1() -> None:
    for path in (ROOT / "app").glob("*.py"):
        if path.name == "engine_v1.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert "engine_v1" not in text and "from .v1" not in text, path.name


@pytest.mark.parametrize("row", BASE["backtests"], ids=lambda r: f"s{r['seed']}-c{r['case']}-{r['template']}")
def test_engine_v1_matches_baseline(row: dict) -> None:  # type: ignore[type-arg]
    bars = BARS[row["seed"]]
    days = sorted({x["d"] for rows in bars.values() for x in rows})
    res = run_v1(CASES[row["case"]], bars, days[60], days[-1], 10_000_000.0)
    assert [trade_key(t) for t in res["trades"][:3]] == row["first"]
    assert len(res["trades"]) == row["trades"]
    assert digest(res["trades"]) == row["digest"]
    assert repr(float(res["final"])) == row["final"]


def test_engine_v1_matches_yahoo_baseline() -> None:
    bars = json.loads((FIX / "yahoo_bars.json").read_text())
    res = run_v1(yahoo_body(), bars, YAHOO["start"], YAHOO["end"], YAHOO["cash"])
    base = BASE["yahoo"]
    assert digest(res["trades"]) == base["digest"] and repr(float(res["final"])) == base["final"]


def _digest_of(keys: list[list]) -> str:  # type: ignore[type-arg]
    return hashlib.sha256(json.dumps(keys, ensure_ascii=False).encode()).hexdigest()


def test_fixed_trades_file_agrees_with_baseline() -> None:
    assert V1["cash"] == CASH
    assert len(V1["backtests"]) == 252 and len(V1["papers"]) == 10
    assert len(V1["examples"]) == 4 and len(V1["randoms"]) == RANDOM_COUNT
    for fixed, row in zip(V1["backtests"], BASE["backtests"], strict=True):
        assert (fixed["seed"], fixed["case"]) == (row["seed"], row["case"])
        assert _digest_of(fixed["trades"]) == row["digest"] and fixed["final"] == row["final"]
    for fixed, row in zip(V1["papers"], BASE["papers"], strict=True):
        assert fixed["case"] == row["case"]
        assert _digest_of(fixed["trades"]) == row["digest"] and fixed["final"] == row["final"]


def test_random_graphs_rebuild_from_seed() -> None:
    assert [r["body"] for r in V1["randoms"]] == random_bodies()
    assert random_graph(7) == random_graph(7) and random_graph(7) != random_graph(8)
    modes = {r["body"]["graph"]["nodes"][-1]["piece"] for r in V1["randoms"]}
    assert "rebalance_every" in modes  # 리밸런싱 방식도 섞여 있어요


def test_examples_are_the_v1_examples() -> None:
    assert [e["body"] for e in V1["examples"]] == example_bodies()
    assert [e["name"] for e in V1["examples"]] == ["대형주 돌파", "돌파 둘 중 하나", "대형주 동일 비중", "추세 상위 교체"]


def _check(body: dict, bars: dict, fixed: dict) -> None:  # type: ignore[type-arg]
    res = run_v1(body, bars, fixed["start"], fixed["end"], CASH)
    assert [trade_key(t) for t in res["trades"]] == fixed["trades"]
    assert repr(float(res["final"])) == fixed["final"]


@pytest.mark.parametrize("i", range(4))
def test_examples_rerun_same(i: int) -> None:
    fixed = V1["examples"][i]
    _check(fixed["body"], example_bars(), fixed)


@pytest.mark.parametrize("i", range(RANDOM_COUNT))
def test_randoms_rerun_same(i: int) -> None:
    fixed = V1["randoms"][i]
    _check(fixed["body"], random_bars(i), fixed)
