"""국내(KR) 시장 정보 한 곳(ARCHITECTURE 4절 '시장' · 6절 '시각' · QUALITY E7 · TASKS P1-05).

한국 시간 · 정규장 시작 · 그날 일봉을 확정으로 보는 시각 · 달력을 모를 때의 휴장 규칙(평일 = 거래일) · 호가 단위 ·
가격 제한폭(상하한가)을 여기에만 둬요. 순수 함수만 있어요(지금 시각 · 저장 · 전송을 모름 · 시각은 받아서 셈).
토스 장 달력을 받아 담아 두는 일(`market.Calendar`)과 일 시각 표(08:30 점검 · 20:10 확인 등 · P1-08 `run/scheduler.py`)는
여기가 아니에요.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Protocol

KST = timezone(timedelta(hours=9))  # 한국 시간(서머타임 없음)
BASE_OPEN = (9, 0)  # 평소 정규장 시작. 늦게 여는 날(수능일 · 새해 첫 거래일)은 차이만큼 점검 · 주문을 옮겨요(R-O1)
BAR_FINAL_AT = (20, 0)  # 그날 일봉을 확정으로 보는 시각(20:10 확인 바로 앞)
PRICE_LIMIT = Decimal("0.30")  # 가격 제한폭 ±30%(전일 종가 기준 상한가 · 하한가)


class TradingDays(Protocol):
    """거래일인지 알려 주는 것(`market.Calendar` · 시험의 가짜 달력)."""

    def is_open(self, d: date) -> bool: ...


def weekday_open(d: date) -> bool:
    """장 달력을 모를 때의 규칙: 평일 = 거래일 · 주말 = 휴장."""
    return d.weekday() < 5


# ── 장 시간 ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DayHours:
    d: date
    open: bool
    start: datetime | None  # 정규장 시작(KST)
    known: bool  # 토스 달력으로 안 값인가(False면 평일 규칙으로 짐작)

    @property
    def shift(self) -> timedelta:
        """평소 09:00보다 얼마나 늦게 여는가(R-O1)."""
        if not self.start:
            return timedelta(0)
        base = datetime.combine(self.d, datetime.min.time(), KST).replace(hour=BASE_OPEN[0], minute=BASE_OPEN[1])
        return max(timedelta(0), self.start.astimezone(KST) - base)

    def at(self, hh: int, mm: int) -> datetime:
        """평소 hh:mm인 일정을 그날 장 시작에 맞춰 옮긴 시각(08:30 점검 · 08:35 주문)."""
        return datetime.combine(self.d, datetime.min.time(), KST).replace(hour=hh, minute=mm) + self.shift


def weekday_hours(d: date) -> DayHours:
    """토스 달력이 없을 때 그날 장 시간: 평일이면 평소 시각에 열고 주말이면 쉬어요(known=False)."""
    weekday = weekday_open(d)
    start = datetime.combine(d, datetime.min.time(), KST).replace(hour=BASE_OPEN[0]) if weekday else None
    return DayHours(d, weekday, start, False)


def complete_until(now: datetime, calendar: TradingDays | None = None) -> date:
    """확인에 쓸 수 있는 마지막 일봉 날짜: 거래일 20:00 뒤면 그날, 아니면 앞 거래일."""
    local = now.astimezone(KST)
    today = local.date()
    is_open = calendar.is_open if calendar else weekday_open
    if is_open(today) and (local.hour, local.minute) >= BAR_FINAL_AT:
        return today
    d = today - timedelta(days=1)
    for _ in range(30):
        if is_open(d):
            return d
        d -= timedelta(days=1)
    return d


def day_end(d: date) -> datetime:
    """그날의 마지막 초(한국 시간 23:59:59) · 일봉을 거슬러 받을 때 커서로 써요."""
    return datetime(d.year, d.month, d.day, 23, 59, 59, tzinfo=KST)


# ── 호가 단위 · 가격 제한폭 ───────────────────────────────────────────────────


def tick_size(price: float) -> int:
    """국내 주식 호가 단위(2023년 1월 개편 뒤 · 코스피 · 코스닥 같음)."""
    if price < 2_000:
        return 1
    if price < 5_000:
        return 5
    if price < 20_000:
        return 10
    if price < 50_000:
        return 50
    if price < 200_000:
        return 100
    if price < 500_000:
        return 500
    return 1_000


def tick_round(price: float) -> float:
    """가장 가까운 호가로 반올림."""
    t = tick_size(price)
    return float(round(price / t) * t)


def ticks_below(price: float, n: int) -> float:
    """n호가 아래(가장 낮은 호가 아래로는 내려가지 않음)."""
    p = price
    for _ in range(n):
        p -= tick_size(p - 1)
    return max(p, tick_size(price))


def lower_limit(close: float) -> float:
    """하한가(전일 종가 × 0.7, 호가 올림): 보호 매도 '가격 하한 없음' 지정가(R-O5)."""
    raw = close * float(1 - PRICE_LIMIT)
    t = tick_size(raw)
    return math.ceil(raw / t) * t
