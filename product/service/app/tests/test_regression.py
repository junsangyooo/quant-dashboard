"""회귀: 옛 일곱 칸 본문을 그래프로 바꾼 전략의 백테스트 · 모의투자가 바꾸기 전 엔진과 거래 하나하나 같다.

기준(tests/fixtures/regression_baseline.json)은 바꾸기 전 엔진으로 만들었다(tests/regression/make_baseline.py).
비교 값: 날짜 · 종목 · 매수/매도 · 수량 · 가격 · 금액 · 비용 · 손익(소수점까지 그대로) + 마지막 자산.
이유 글은 비교하지 않는다(그래프 규칙 2절: 매수 이유에 통과한 경로의 ③ 필터가 더해진다).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app import strategy as st
from app.engine import run_backtest
from tests.regression.cases import SEEDS, YAHOO, bar_set, bodies, digest, trade_key, yahoo_body
from tests.regression.replay import paper_replay

FIX = Path(__file__).resolve().parent / "fixtures"
BASE = json.loads((FIX / "regression_baseline.json").read_text())
CASES = bodies()
BARS = {seed: bar_set(seed) for seed in SEEDS}


def _graph(body: dict) -> dict:  # type: ignore[type-arg]
    g = st.normalize(body)
    assert "graph" in g and "slots" not in g
    assert st.validate(g) == []
    return g


@pytest.mark.parametrize("row", BASE["backtests"], ids=lambda r: f"s{r['seed']}-c{r['case']}-{r['template']}")
def test_backtest_same_as_seven_slot_engine(row: dict) -> None:  # type: ignore[type-arg]
    body = _graph(CASES[row["case"]])
    assert st.mode_of(body) == row["template"]
    bars = BARS[row["seed"]]
    days = sorted({x["d"] for rows in bars.values() for x in rows})
    res = run_backtest(body, bars, None, days[60], days[-1], 10_000_000.0)
    assert [trade_key(t) for t in res["trades"][:3]] == row["first"]
    assert len(res["trades"]) == row["trades"]
    assert digest(res["trades"]) == row["digest"]
    assert repr(float(res["final"])) == row["final"]


@pytest.mark.parametrize("row", BASE["papers"], ids=lambda r: f"c{r['case']}-{r['template']}")
def test_paper_same_as_seven_slot_engine(row: dict, tmp_path: Path) -> None:  # type: ignore[type-arg]
    body = _graph(CASES[row["case"]])
    r = paper_replay(body, BARS[SEEDS[0]], 150, 270, tmp_path / "p")
    assert len(r["trades"]) == row["trades"]
    assert digest(r["trades"]) == row["digest"]
    assert repr(r["final"]) == row["final"]


def test_stored_seven_slot_body_runs_the_same(tmp_path: Path) -> None:
    """옛 버전(일곱 칸 그대로 저장된 본문)도 읽을 때 그래프로 바뀌어 같은 거래가 나온다."""
    row = BASE["papers"][1]
    r = paper_replay(CASES[row["case"]], BARS[SEEDS[0]], 150, 270, tmp_path / "old")
    assert digest(r["trades"]) == row["digest"]


def test_yahoo_real_bars_once() -> None:
    """야후 실제 일봉(005930 · 000660, 2022-01-01~2025-09-30, 1,000만 원, 20일 이동평균선 상향 돌파,
    상위 2종목, 손절 −10% · 익절 +20%, 동일 비중). 일봉은 기준을 만들 때 받아 둔 것."""
    bars = json.loads((FIX / "yahoo_bars.json").read_text())
    body = _graph(yahoo_body())
    res = run_backtest(body, bars, None, YAHOO["start"], YAHOO["end"], YAHOO["cash"])
    base = BASE["yahoo"]
    assert len(res["trades"]) == base["trades"]
    assert digest(res["trades"]) == base["digest"]
    assert repr(float(res["final"])) == base["final"]
    assert res["buys"] == base["buys"] and res["sells"] == base["sells"]
