"""v1 엔진(고정본 `app/v1/`)을 부르는 입구. 시험에서만 써요(SPEC 4-8 · TASKS T-02 · T-24).

변환 일치 문턱(R-C10): 같은 일봉으로 v1 엔진과 v3 엔진을 돌려 거래 하나하나를 비교해요.
"""

from __future__ import annotations

from typing import Any

from .v1 import strategy as strategy_v1
from .v1.engine import Engine, Series, run_backtest, universe_of, warmup_calendar_days

__all__ = ["Engine", "Series", "run_backtest", "run_v1", "strategy_v1", "universe_of", "warmup_calendar_days"]


def run_v1(body: dict[str, Any], bars: dict[str, list[dict[str, Any]]], start: str, end: str,
           cash: float, index: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """v1 본문(일곱 칸 `slots` 또는 v2 `graph` 노드)을 v1 엔진으로 백테스트해요."""
    graph = strategy_v1.normalize(body)
    return run_backtest(graph, bars, index, start, end, cash)
