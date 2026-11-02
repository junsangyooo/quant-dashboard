"""변환 일치 문턱(TASKS T-24 · SPEC 4-8 · ENGINE-RULES R-C10).

`tests/fixtures/v1_trades.json`(T-02에서 v1 엔진으로 고정한 거래)과 v3 엔진(변환한 전략)을 같은 일봉으로
돌린 거래를 비교해요(날짜 · 종목 · 매수/매도 · 수량 · 가격).

- v1 거래에 같은 날 매도와 매수가 함께 있는 날(갈아타기)이 없으면: 거래가 모두 같아야 해요(완전 일치).
- 있으면: 첫 차이가 나는 날까지 모두 같고, 그 날 v1에 매도가 있고, 그 날의 차이가 v1 매수 몇 개가 v3에서 빠진 것
  뿐이며(나머지 거래는 같음), 빠진 매수가 v3에서 다음 거래일 같은 종목 매수로 나와야 해요(R-O2 · 하루 늦은 매수).
  그 뒤는 비교하지 않아요.

표 다시 만들기: `.venv/bin/python -m tests.regression.threshold --write`
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from app.copytext import convert_v1
from app.engine import run_backtest
from app.v1 import strategy as st1
from tests.regression.cases import SEEDS, bar_set, bodies, trade_key
from tests.regression.v1_inputs import example_bars, random_bars

FIX = Path(__file__).resolve().parents[1] / "fixtures"
TABLE = Path(__file__).resolve().parent / "conversion_table.md"
V1 = json.loads((FIX / "v1_trades.json").read_text())


def key5(t: list[Any]) -> tuple[Any, ...]:
    return tuple(t[:5])


def switch_days(trades: list[list[Any]]) -> set[str]:
    days: dict[str, set[str]] = {}
    for t in trades:
        days.setdefault(t[0], set()).add(t[2])
    return {d for d, sides in days.items() if sides == {"buy", "sell"}}


def compare(v1: list[list[Any]], v3: list[list[Any]], calendar: list[str]) -> dict[str, Any]:
    """{'ok', 'kind'('same' · 'late_buy' · 'mismatch'), 'day', 'syms', 'why'}"""
    a = [key5(t) for t in v1]
    b = [key5(t) for t in v3]
    switching = switch_days(v1)
    if a == b:
        return {"ok": True, "kind": "same", "day": "", "syms": [], "switching": bool(switching)}
    if not switching:
        return {"ok": False, "kind": "mismatch", "day": "", "syms": [], "why": "갈아타기가 없는데 거래가 달라요",
                "switching": False}
    days = sorted({t[0] for t in a} | {t[0] for t in b})
    for d in days:
        da = [t for t in a if t[0] == d]
        db = [t for t in b if t[0] == d]
        if da == db:
            continue
        missing = [t for t in da if t not in db]
        extra = [t for t in db if t not in da]
        why = ""
        if extra:
            why = f"v3에만 있는 거래 {extra[:2]}"
        elif not missing or any(t[2] != "buy" for t in missing):
            why = "빠진 것이 매수가 아니에요"
        elif not any(t[2] == "sell" for t in da):
            why = "그날 v1에 매도가 없어요(갈아타기가 아님)"
        else:
            nxt = calendar[calendar.index(d) + 1] if d in calendar and calendar.index(d) + 1 < len(calendar) else None
            later = [t for t in b if t[0] == nxt and t[2] == "buy"]
            late = [m[1] for m in missing if any(t[1] == m[1] for t in later)]
            if len(late) != len(missing):
                why = "빠진 매수가 다음 거래일에 없어요"
        syms = [m[1] for m in missing]
        if why:
            return {"ok": False, "kind": "mismatch", "day": d, "syms": syms, "why": why, "switching": True}
        return {"ok": True, "kind": "late_buy", "day": d, "syms": syms, "switching": True}
    return {"ok": False, "kind": "mismatch", "day": "", "syms": [], "why": "알 수 없음", "switching": True}


def _calendar(bars: dict[str, list[dict[str, Any]]]) -> list[str]:
    return sorted({x["d"] for rows in bars.values() for x in rows})


def run_all() -> list[dict[str, Any]]:
    cases = bodies()
    bars = {seed: bar_set(seed) for seed in SEEDS}
    rows: list[dict[str, Any]] = []

    def one(name: str, body_v1: dict[str, Any], data: dict[str, list[dict[str, Any]]], start: str, end: str,
            fixed: dict[str, Any]) -> None:
        v3 = convert_v1(st1.normalize(body_v1))
        res = run_backtest(v3, data, None, start, end, float(V1["cash"]), check=False)
        got = compare(fixed["trades"], [trade_key(t) for t in res["trades"]], _calendar(data))
        rows.append({"name": name, "trades": len(fixed["trades"]), **got})

    for f in V1["backtests"]:
        cal = _calendar(bars[f["seed"]])
        one(f"백테스트 s{f['seed']}-c{f['case']} {f['template']}", cases[f["case"]], bars[f["seed"]], f["start"],
            f["end"], f)
    for f in V1["papers"]:
        cal = _calendar(bars[SEEDS[0]])
        one(f"모의투자 c{f['case']} {f['template']}", cases[f["case"]], bars[SEEDS[0]], cal[f["first"]],
            cal[f["last"]], f)
    ex = example_bars()
    for f in V1["examples"]:
        one(f"예시 {f['name']}", f["body"], ex, f["start"], f["end"], f)
    for f in V1["randoms"]:
        one(f"무작위 {f['seed']}", f["body"], random_bars(f["seed"]), f["start"], f["end"], f)
    return rows


def table(rows: list[dict[str, Any]]) -> str:
    same = sum(1 for r in rows if r["kind"] == "same")
    late = sum(1 for r in rows if r["kind"] == "late_buy")
    bad = sum(1 for r in rows if not r["ok"])
    no_switch = [r for r in rows if not r["switching"]]
    lines = [
        "# 변환 일치 표 (R-C10 · TASKS T-24)",
        "",
        "`tests/regression/threshold.py --write`가 만든 표예요. v1 엔진으로 고정한 거래(`tests/fixtures/v1_trades.json`)와 "
        "v3 엔진(변환한 전략)을 같은 가짜 일봉으로 돌려 비교했어요(날짜 · 종목 · 매수/매도 · 수량 · 가격).",
        "",
        f"- 전략 {len(rows)}개: 완전 일치 {same} · 첫 차이가 하루 늦은 매수 {late} · 어긋남 {bad}",
        f"- 같은 날 갈아타기가 없는 전략 {len(no_switch)}개는 모두 완전 일치"
        f"({sum(1 for r in no_switch if r['kind'] == 'same')}/{len(no_switch)})",
        "",
        "| 전략 | v1 거래 수 | 결과 | 첫 차이 날짜 | 종목 |",
        "|---|---|---|---|---|",
    ]
    names = {"same": "완전 일치", "late_buy": "첫 차이 = 하루 늦은 매수", "mismatch": "어긋남"}
    for r in rows:
        result = names[r["kind"]] + (f" · {r['why']}" if r.get("why") else "")
        lines.append(f"| {r['name']} | {r['trades']} | {result} | {r['day'] or '—'} | {' · '.join(r['syms']) or '—'} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    rows = run_all()
    text = table(rows)
    if "--write" in sys.argv:
        TABLE.write_text(text, encoding="utf-8")
    print("\n".join(text.splitlines()[:6]))
