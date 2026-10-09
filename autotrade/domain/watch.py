"""The daily code checks of '3년 발굴' (PHASE2.md §4·§5, AI 0): filings and price shocks.

Filings are sorted by kind (T28):
- Korea (DART report names): routine ownership and offering papers are skipped
  (소유상황·대량보유·소유주식변동·기업설명회·증권발행실적·투자설명서·일괄신고·의결권대리행사);
  reports and earnings notices go to '실적 지표 뽑기' (Haiku); the rest to '관련 있나 가리기'.
- US (EDGAR forms): 8-K item 2.02 is earnings, an 8-K that only reports the shareholder vote
  (5.07, with or without exhibits 9.01) is skipped, other 8-Ks are screened. A foreign issuer's
  6-K (TSMC) is mostly a monthly revenue or earnings release, so it is read as earnings.

Shocks are measured against the same market's index on adjusted closes (T28 measure.py):
- one day: the stock's daily return minus the index's daily return <= -8%;
- 20 trading days: (stock 20-day ratio) / (index 20-day ratio) - 1 <= -20%;
- once set off, the stock is not counted again for 20 trading days.
A shock never sells by itself (D31): it only asks the AI to confirm twice.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

KR_SKIP = (
    "소유상황보고서",
    "대량보유상황보고서",
    "소유주식변동",
    "기업설명회",
    "증권발행실적",
    "투자설명서",
    "일괄신고",
    "의결권대리행사",
)
KR_EARNINGS = ("분기보고서", "반기보고서", "사업보고서", "실적", "손익구조", "감사보고서")
US_WATCHED = ("8-K", "8-K/A", "6-K", "6-K/A")
US_VOTE_ONLY = {"5.07", "9.01"}


def classify_kr(report_name: str) -> str:
    """'earnings' | 'other' | 'skipped' for a DART report name."""
    if any(k in report_name for k in KR_SKIP):
        return "skipped"
    if any(k in report_name for k in KR_EARNINGS):
        return "earnings"
    return "other"


def classify_us(form: str, items: str | None) -> str:
    """'earnings' | 'other' | 'skipped' for an EDGAR filing."""
    if form not in US_WATCHED:
        return "skipped"
    if form.startswith("6-K"):
        return "earnings"
    parts = {p.strip() for p in (items or "").split(",") if p.strip()}
    if "2.02" in parts:
        return "earnings"
    if parts and parts <= US_VOTE_ONLY and "5.07" in parts:
        return "skipped"
    return "other"


@dataclass(frozen=True)
class Shock:
    on: date  # the session that set it off
    kind: str  # 'day' | '20d' | 'day+20d'
    day_rel: Decimal  # stock minus index, that day
    rel20: Decimal | None  # relative 20-day change (None before 20 common sessions)


def _common(
    stock: Sequence[tuple[date, Decimal]], index: Sequence[tuple[date, Decimal]]
) -> list[tuple[date, Decimal, Decimal]]:
    by_index = dict(index)
    return [(d, c, by_index[d]) for d, c in sorted(stock) if d in by_index and c > 0]


def find_shocks(
    stock: Sequence[tuple[date, Decimal]],
    index: Sequence[tuple[date, Decimal]],
    *,
    day_line: Decimal,
    line_20d: Decimal,
    window: int,
    after: date | None,
    blocked_until: date | None,
) -> list[Shock]:
    """Shocks on the common sessions after `after` (adjusted closes, T28 measure.py).

    A session counts only after `blocked_until` (the previous shock's cooldown) and at least
    `window` sessions after a shock found in this same scan.
    """
    common = _common(stock, index)
    out: list[Shock] = []
    last_hit: int | None = None
    for i in range(1, len(common)):
        d, s1, b1 = common[i]
        if (after is not None and d <= after) or (blocked_until is not None and d <= blocked_until):
            continue
        if last_hit is not None and i - last_hit < window:
            continue
        _, s0, b0 = common[i - 1]
        if b0 <= 0:
            continue
        day_rel = (s1 / s0 - 1) - (b1 / b0 - 1)
        rel20: Decimal | None = None
        if i >= window:
            _, s20, b20 = common[i - window]
            if b20 > 0:
                rel20 = (s1 / s20) / (b1 / b20) - 1
        day_hit = day_rel <= day_line
        hit20 = rel20 is not None and rel20 <= line_20d
        if day_hit or hit20:
            kind = "day+20d" if day_hit and hit20 else ("day" if day_hit else "20d")
            out.append(Shock(d, kind, day_rel, rel20))
            last_hit = i
    return out


@dataclass(frozen=True)
class WindowReturn:
    first: date  # first common session on or after the start
    last: date  # last common session on or before the end
    value: Decimal  # the stock's return (fraction)
    index: Decimal  # the index's return over the same sessions


def window_return(
    stock: Sequence[tuple[date, Decimal]],
    index: Sequence[tuple[date, Decimal]],
    start: date,
    end: date | None = None,
) -> WindowReturn | None:
    """Returns from the first common session on or after `start` to the last one on or before
    `end` (the latest when None), on adjusted closes (T24 score.py: a sold pick is scored up to
    the day it was sold)."""
    common = [x for x in _common(stock, index) if x[0] >= start and (end is None or x[0] <= end)]
    if len(common) < 2:
        return None
    d0, s0, b0 = common[0]
    d1, s1, b1 = common[-1]
    if b0 <= 0:
        return None
    return WindowReturn(d0, d1, s1 / s0 - 1, b1 / b0 - 1)


def excess_path(
    stock: Sequence[tuple[date, Decimal]],
    index: Sequence[tuple[date, Decimal]],
    start: date,
    end: date | None = None,
) -> list[tuple[date, Decimal]]:
    """Excess return over the index (as a fraction) on every common session from the first one
    on or after `start` (0 there) to `end`."""
    common = [x for x in _common(stock, index) if x[0] >= start and (end is None or x[0] <= end)]
    if not common:
        return []
    _, s0, b0 = common[0]
    if b0 <= 0:
        return []
    return [(d, (s / s0 - 1) - (b / b0 - 1)) for d, s, b in common]
