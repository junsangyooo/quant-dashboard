"""v1 엔진으로 돌린 거래 목록을 고정해요(TASKS T-02). 한 번 만들고 다시 만들지 않아요.

    cd product/service/app && .venv/bin/python -m tests.regression.make_v1_trades

- 백테스트: 회귀 사례 252건 · 옛 예시 4개 · 무작위 그래프 60개 → v1 엔진(`app/engine_v1.py`)
- 모의투자 10건: v1 모의투자(지금 `app/paper.py`)를 같은 일봉으로 하루씩 돌린 결과
  (v1 모의투자는 v1 엔진의 `Engine`을 하루씩 부른 것이라 `paper_replay`로 그대로 남겨요)
- 거래 하나 = `cases.trade_key`(날짜 · 종목 · 매수/매도 · 수량 · 가격 · 금액 · 비용 · 손익)
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from app.engine_v1 import run_v1
from tests.regression.cases import SEEDS, bar_set, bodies, digest, trade_key
from tests.regression.replay import paper_replay
from tests.regression.v1_inputs import (
    RANDOM_COUNT,
    RANDOM_SEED_BASE,
    example_bars,
    example_bodies,
    random_bars,
    random_bodies,
)

FIX = Path(__file__).resolve().parents[1] / "fixtures"
OUT = FIX / "v1_trades.json"
CASH = 10_000_000.0


def _days(bars: dict[str, list[dict[str, Any]]]) -> list[str]:
    return sorted({x["d"] for rows in bars.values() for x in rows})


def _bt(body: dict[str, Any], bars: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    days = _days(bars)
    res = run_v1(body, bars, days[60], days[-1], CASH)
    return {"start": days[60], "end": days[-1], "trades": [trade_key(t) for t in res["trades"]],
            "final": repr(float(res["final"]))}


def build() -> dict[str, Any]:
    base = json.loads((FIX / "regression_baseline.json").read_text())
    cases = bodies()
    bars = {seed: bar_set(seed) for seed in SEEDS}
    out: dict[str, Any] = {
        "made_with": "app/engine_v1.py (app/v1 = 39dedac engine · graph · pieces · strategy)",
        "cash": CASH,
        "random": {"count": RANDOM_COUNT, "seed_base": RANDOM_SEED_BASE},
        "backtests": [],
        "papers": [],
        "examples": [],
        "randoms": [],
    }
    for row in base["backtests"]:
        r = _bt(cases[row["case"]], bars[row["seed"]])
        out["backtests"].append({"seed": row["seed"], "case": row["case"], "template": row["template"], **r})
    with tempfile.TemporaryDirectory() as tmp:
        for row in base["papers"]:
            p = paper_replay(cases[row["case"]], bars[SEEDS[0]], 150, 270, Path(tmp) / f"p{row['case']}")
            out["papers"].append({"case": row["case"], "template": row["template"], "first": 150, "last": 270,
                                  "trades": [trade_key(t) for t in p["trades"]], "final": repr(p["final"]),
                                  "digest": digest(p["trades"])})
    ex_bars = example_bars()
    for body in example_bodies():
        out["examples"].append({"name": body["name"], "body": body, **_bt(body, ex_bars)})
    for i, body in enumerate(random_bodies()):
        out["randoms"].append({"seed": i, "body": body, **_bt(body, random_bars(i))})
    return out


if __name__ == "__main__":
    data = build()
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    n = sum(len(x["trades"]) for k in ("backtests", "papers", "examples", "randoms") for x in data[k])
    print(f"{OUT.name}: {n} trades, {OUT.stat().st_size // 1024} KB")
