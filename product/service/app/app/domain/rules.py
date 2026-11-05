"""실전 · 모의투자가 같이 쓰는 규칙 층(ENGINE-RULES R-O3 · R-O5 · R-O8 · R-O9 · R-V1). 백테스트는 쓰지 않아요(R-B1).

숫자는 근거 없는 제안값이에요(SPEC 10-3 · OPEN-QUESTIONS Q-D7). 한 곳에 모아 두고 시험이 이 상수를 읽어요.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .markets.kr import tick_size

DAILY_LOSS = -0.03  # 하루 손실 한도: 운용 자산(전날 평가액) 기준 −3%
PER_STOCK = 0.40  # 종목당 한도: 운용 금액의 40%
ORDER_MAX = 20_000_000  # 주문 하나 2,000만 원(최대 9,999만 원까지 바꿀 수 있어요)
ORDER_MAX_CEIL = 99_990_000
ORDER_HUGE = 100_000_000  # 1억 원 이상은 나눠 내지 않고 할 일(R-O9)
DAILY_ORDERS = 40
PRICE_BAND = 0.10  # 지정가 상한 = 종가 × 1.1(매수) · 하한 = 종가 × 0.9(일반 매도)


def buy_cap(close: float) -> float:
    """R-O3 지정가 상한: 종가 × 1.1을 호가 단위로 내림."""
    raw = close * (1 + PRICE_BAND)
    t = tick_size(raw)
    return math.floor(raw / t) * t


def sell_floor(close: float) -> float:
    """R-O5 일반 매도 지정가 하한: 종가 × 0.9를 호가 단위로 올림."""
    raw = close * (1 - PRICE_BAND)
    t = tick_size(raw)
    return math.ceil(raw / t) * t


def gap_pct(open_: float, close: float) -> int:
    return round((open_ / close - 1) * 100)


@dataclass
class RuleLayer:
    """엔진(Engine)에 끼우는 실전 · 모의 규칙. amount = 운용 금액(모의는 가상 시작 금액)."""

    amount: float
    daily_loss: float = DAILY_LOSS
    per_stock: float = PER_STOCK
    order_max: float = ORDER_MAX
    daily_orders: int = DAILY_ORDERS

    def cap_target(self, value: float) -> float:
        """종목당 한도: 넘는 매수는 그만큼 줄여요(R-O8)."""
        return min(value, self.amount * self.per_stock)

    def loss_blocked(self, prev_equity: float | None, equity: float) -> bool:
        """하루 손실 한도를 넘었나(전날 평가액 대비)."""
        if not prev_equity or prev_equity <= 0:
            return False
        return equity / prev_equity - 1 <= self.daily_loss

    def buy_block(self, open_: float, close: float, value: float) -> str | None:
        """체결 직전 매수를 막는 이유(없으면 None)."""
        if value > self.order_max:
            return "매수 안 함 · 주문 크기 한도를 넘었어요"
        if open_ > buy_cap(close):
            return f"매수 안 함 · 시가가 종가보다 {gap_pct(open_, close)}% 높았어요"
        return None

    def sell_block(self, kind: str, open_: float, close: float) -> str | None:
        """일반 매도는 시가가 하한보다 낮으면 안 팔려요(보호 매도는 하한 없음 · R-O5)."""
        if kind == "normal" and open_ < sell_floor(close):
            return f"매도 안 함 · 시가가 종가보다 {abs(gap_pct(open_, close))}% 낮았어요"
        return None
