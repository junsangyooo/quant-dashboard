"""회귀 기준의 입력: 가짜 일봉 묶음 · 옛 일곱 칸 본문 조합 · 야후 실제 일봉 조건.

기준 결과(baseline.json)는 그래프 엔진으로 바꾸기 전의 엔진(일곱 칸 본문)으로 만들었다
(make_baseline.py, 2026-10-30). 시험(test_regression.py)은 같은 입력을 옛 본문 → 그래프로 바꿔
새 엔진에 넣고, 거래 하나하나(날짜 · 종목 · 매수/매도 · 수량 · 가격 · 금액 · 비용 · 손익)와
마지막 자산이 같은지 본다.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import random
from datetime import date, timedelta
from typing import Any

SYMS = ["111111", "222222", "333333", "444444", "555555", "666666"]
START = date(2023, 1, 2)
DAYS = 420


def _days(n: int) -> list[str]:
    out: list[str] = []
    d = START
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def bar_set(seed: int) -> dict[str, list[dict[str, Any]]]:
    """종목 6개 × 420거래일. 추세 · 진동 · 잡음 · 거래량이 종목마다 다르다(결정적)."""
    rnd = random.Random(seed)
    days = _days(DAYS)
    out: dict[str, list[dict[str, Any]]] = {}
    for k, sym in enumerate(SYMS):
        base = rnd.choice([8_000, 25_000, 60_000, 120_000, 300_000])
        drift = rnd.uniform(-0.0008, 0.0015)
        amp = rnd.uniform(0.03, 0.12)
        period = rnd.randint(18, 70)
        noise = rnd.uniform(0.004, 0.02)
        vol0 = rnd.choice([20_000, 80_000, 300_000, 1_000_000])
        price = float(base)
        bars = []
        for i, d in enumerate(days):
            wave = amp * math.sin(2 * math.pi * (i + k * 7) / period)
            target = base * (1 + drift) ** i * (1 + wave)
            price = price * 0.6 + target * 0.4
            price *= 1 + rnd.gauss(0, noise)
            c = max(100.0, round(price, -1 if price < 50_000 else 2))
            o = max(100.0, round(c * (1 + rnd.gauss(0, noise / 2)), -1 if c < 50_000 else 2))
            h = max(o, c) * (1 + abs(rnd.gauss(0, noise / 3)))
            lo = min(o, c) * (1 - abs(rnd.gauss(0, noise / 3)))
            v = round(vol0 * (1 + 0.8 * math.sin(i / 9 + k)) * rnd.uniform(0.5, 1.5))
            bars.append({"d": d, "o": o, "h": round(h, 2), "l": round(lo, 2), "c": c, "v": float(max(v, 0))})
        # 하루 빠진 날(거래 정지처럼): 셋째 종목만
        if k == 2:
            del bars[200]
        out[sym] = bars
    return out


SEEDS = [11, 23, 47]

SIGNALS = [
    [{"piece": "ma_cross_up", "params": {"n": 5}}],
    [{"piece": "ma_cross_up", "params": {"n": 20}}],
    [{"piece": "rsi_below", "params": {"period": 14, "level": 40}}],
    [{"piece": "high_breakout", "params": {"n": 10}}],
    [{"piece": "ma_cross_up", "params": {"n": 10}}, {"piece": "rsi_below", "params": {"period": 7, "level": 50}}],
    [{"piece": "high_breakout", "params": {"n": 20}}, {"piece": "ma_cross_up", "params": {"n": 5}}],
]
FILTERS = [
    [],
    [{"piece": "min_turnover", "params": {"n": 20}}],
    [{"piece": "min_price", "params": {"n": 30000}}],
    [{"piece": "min_turnover", "params": {"n": 5}}, {"piece": "min_price", "params": {"n": 10000}}],
]
SELLS = [
    [{"piece": "stop_loss", "params": {"pct": 5}}],
    [{"piece": "take_profit", "params": {"pct": 10}}, {"piece": "stop_loss", "params": {"pct": 8}}],
    [{"piece": "max_hold", "params": {"n": 10}}],
    [{"piece": "ma_break_down", "params": {"n": 10}}, {"piece": "take_profit", "params": {"pct": 20}}],
    [
        {"piece": "stop_loss", "params": {"pct": 7}},
        {"piece": "take_profit", "params": {"pct": 15}},
        {"piece": "max_hold", "params": {"n": 40}},
    ],
]


def _body(template: str, signals, filters, top_n, sells, max_pct, every) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    weight: list[dict[str, Any]] = [{"piece": "equal", "params": {}}]
    if max_pct:
        weight.append({"piece": "max_per_stock", "params": {"pct": max_pct}})
    if every:
        weight.append({"piece": "rebalance_every", "params": {"n": every}})
    return {
        "name": "회귀",
        "template": template,
        "slots": {
            "universe": [{"piece": "manual_list", "params": {"symbols": list(SYMS)}}],
            "signal": [dict(s, params=dict(s["params"])) for s in signals],
            "filter": [dict(f, params=dict(f["params"])) for f in filters],
            "select": [{"piece": "top_n", "params": {"n": top_n}}] if top_n else [],
            "buy": [{"piece": "next_open", "params": {}}],
            "sell": [dict(s, params=dict(s["params"])) for s in sells],
            "weight": weight,
        },
    }


def bodies() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    # 조건 충족 시 매매: 신호 6 × 필터 4 × 매도 5에서 고른 조합 + 종목 수 · 최대 비중
    for i, (sig, flt, sell) in enumerate(itertools.product(SIGNALS, FILTERS, SELLS)):
        if i % 3:
            continue
        out.append(_body("event", sig, flt, 1 + i % 3, sell, 40 if i % 2 else None, None))
    # 순위 교체: 신호 × 필터 × (매도 없음 | 손절)
    for i, (sig, flt) in enumerate(itertools.product(SIGNALS, FILTERS)):
        sells = [] if i % 2 else SELLS[0]
        out.append(_body("rank", sig, flt, 2 + i % 2, sells, None, [5, 20][i % 2]))
    # 목표 비중: 신호 있음/없음 × 필터 × 종목 수 있음/없음 × 최대 비중
    tsigs = [[], *SIGNALS[:4]]
    for i, (sig, flt) in enumerate(itertools.product(tsigs, FILTERS)):
        top = None if i % 2 else 2
        out.append(_body("target", sig, flt, top, [], 30 if i % 3 == 0 else None, [1, 5, 20][i % 3]))
    return out


def trade_key(t: dict[str, Any]) -> list[Any]:
    """거래 하나를 비교하는 값(이유 글은 빼고: 이유 글은 그래프 규칙 2절대로 ③ 필터가 더해진다)."""
    return [t["d"], t["sym"], t["side"], int(t["qty"]), repr(float(t["price"])), repr(float(t["amount"])),
            repr(float(t["cost"])), None if t["pnl"] is None else repr(float(t["pnl"]))]


def digest(trades: list[dict[str, Any]]) -> str:
    raw = json.dumps([trade_key(t) for t in trades], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


# 야후 실제 일봉 한 번(기획 3절)
YAHOO = {
    "symbols": ["005930", "000660"],
    "start": "2022-01-01",
    "end": "2025-09-30",
    "cash": 10_000_000.0,
}


def yahoo_body() -> dict[str, Any]:
    return {
        "name": "야후 회귀",
        "template": "event",
        "slots": {
            "universe": [{"piece": "manual_list", "params": {"symbols": ["005930", "000660"]}}],
            "signal": [{"piece": "ma_cross_up", "params": {"n": 20}}],
            "filter": [],
            "select": [{"piece": "top_n", "params": {"n": 2}}],
            "buy": [{"piece": "next_open", "params": {}}],
            "sell": [
                {"piece": "stop_loss", "params": {"pct": 10}},
                {"piece": "take_profit", "params": {"pct": 20}},
            ],
            "weight": [{"piece": "equal", "params": {}}],
        },
    }
