"""회귀 기준 만들기(한 번만 · 그래프 엔진으로 바꾸기 전의 엔진으로 돌렸다, 2026-10-30).

    cd mvp && PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m tests.regression.make_baseline [--yahoo]

--yahoo: 야후에서 005930 · 000660 일봉을 받아 tests/fixtures/yahoo_bars.json에 담고 기준도 만든다.
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

from app import strategy as st
from app.engine import run_backtest
from tests.regression.cases import SEEDS, YAHOO, bar_set, bodies, digest, trade_key, yahoo_body
from tests.regression.replay import paper_replay

FIX = Path(__file__).resolve().parent.parent / "fixtures"


def main() -> None:
    out: dict = {"made_with": "seven-slot engine (before the graph engine)", "backtests": [], "papers": []}
    cases = bodies()
    for b in cases:
        assert st.validate(b) == [], (b, st.validate(b))
    for seed in SEEDS:
        bars = bar_set(seed)
        days = sorted({x["d"] for rows in bars.values() for x in rows})
        for i, body in enumerate(cases):
            res = run_backtest(body, bars, None, days[60], days[-1], 10_000_000.0)
            out["backtests"].append({
                "seed": seed, "case": i, "template": body["template"],
                "trades": len(res["trades"]), "digest": digest(res["trades"]),
                "final": repr(float(res["final"])), "first": [trade_key(t) for t in res["trades"][:3]],
            })
    # 모의투자: 방식마다 몇 개씩, 시드 하나로 120거래일
    bars = bar_set(SEEDS[0])
    with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / ".build4") as tmp:
        for i, body in enumerate(cases):
            if i % 9:
                continue
            r = paper_replay(body, bars, 150, 270, Path(tmp) / f"p{i}")
            out["papers"].append({"case": i, "template": body["template"], "trades": len(r["trades"]),
                                  "digest": digest(r["trades"]), "final": repr(r["final"])})
    if "--yahoo" in sys.argv:
        from app.db import DB
        from app.market import Market, YahooSource

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / ".build4") as tmp:
            m = Market(DB(Path(tmp) / "y.db"), YahooSource(cache_dir=str(Path(tmp) / "yc")))
            start = date.fromisoformat(YAHOO["start"])
            end = date.fromisoformat(YAHOO["end"])
            from app.engine import warmup_calendar_days
            warm = start - timedelta(days=warmup_calendar_days(yahoo_body()))
            bars_y = m.many(YAHOO["symbols"], warm, end)
        (FIX / "yahoo_bars.json").write_text(json.dumps(bars_y, ensure_ascii=False))
        res = run_backtest(yahoo_body(), bars_y, None, YAHOO["start"], YAHOO["end"], YAHOO["cash"])
        out["yahoo"] = {"trades": len(res["trades"]), "digest": digest(res["trades"]), "final": repr(float(res["final"])),
                        "total": res["total"], "cagr": res["cagr"], "mdd": res["mdd"], "win_rate": res["win_rate"],
                        "costs": res["costs"], "buys": res["buys"], "sells": res["sells"],
                        "start": res["start"], "end": res["end"]}
    else:
        old = json.loads((FIX / "regression_baseline.json").read_text()) if (FIX / "regression_baseline.json").exists() else {}
        if "yahoo" in old:
            out["yahoo"] = old["yahoo"]
    (FIX / "regression_baseline.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(len(out["backtests"]), "backtests,", len(out["papers"]), "papers,", "yahoo" in out)


if __name__ == "__main__":
    main()
