"""Number and time formats of CONTRACT.md 원칙 (the server rounds; the screen only formats).

krw: whole won · usd: cents · rate: 0.1 · pct1: weight % to 0.1 · pp1: signed %p to 0.1 ·
ret2: return % to 0.01 · times: ISO 8601 in KST (+09:00) · dates: YYYY-MM-DD.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from autotrade.timeutil import KST

HUNDRED = Decimal(100)


def _num(x: Decimal, step: str) -> float:
    value = float(x.quantize(Decimal(step), rounding=ROUND_HALF_UP))
    return value if value != 0 else 0.0  # never '-0.0'


def krw(x: Decimal) -> int:
    return int(x.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def usd(x: Decimal) -> float:
    return _num(x, "0.01")


def rate(x: Decimal) -> float:
    return _num(x, "0.1")


def pct1(fraction: Decimal) -> float:
    """0.50152 -> 50.2"""
    return _num(fraction * HUNDRED, "0.1")


def pp1(fraction: Decimal) -> float:
    """Signed percentage points: 0.0017 -> 0.2, -0.002 -> -0.2"""
    return _num(fraction * HUNDRED, "0.1")


def ret2(fraction: Decimal) -> float:
    return _num(fraction * HUNDRED, "0.01")


def ret1(fraction: Decimal) -> float:
    return _num(fraction * HUNDRED, "0.1")


def iso(dt: datetime) -> str:
    return dt.astimezone(KST).isoformat(timespec="seconds")


def day(d: date) -> str:
    return d.isoformat()


def allocate_pct1(values: Sequence[Decimal]) -> list[Decimal]:
    """Percent shares to 0.1 that add up to exactly 100.0 (largest remainder).

    Composition rows must add up (§1.1: 40.7 + 38.7 + 1.7 + 7.7 + 7.1 + 3.5 + 0.6 = 100.0), so the
    rows are not rounded one by one.
    """
    total = sum(values, Decimal(0))
    if total <= 0:
        return [Decimal(0) for _ in values]
    raw = [v * 1000 / total for v in values]  # in tenths of a percent
    floors = [r.to_integral_value(rounding=ROUND_FLOOR) for r in raw]
    short = int(1000 - sum(floors, Decimal(0)))
    order = sorted(range(len(values)), key=lambda i: (raw[i] - floors[i], values[i]), reverse=True)
    for i in order[: max(short, 0)]:
        floors[i] += 1
    return [f / 10 for f in floors]
