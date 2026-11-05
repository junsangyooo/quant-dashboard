"""주문 바꾸기 규칙(순수 함수 · TASKS P1-08 · ENGINE-RULES 5 · 6 · 7절).

실전 흐름(`run/live.py`)이 판정(계획)을 실제 주문 값으로 바꿀 때 쓰는 규칙이에요: 주문 번호 꼴 · 매수 수량 · 매도 지정가 ·
장중 넓히기(R-O6) · 조건주문 다리(R-X6 ~ R-X8) · 미체결 · 닫힌 주문의 기록 상태. 시각 · 저장 · 전송을 모르고, 같은 입력이면
늘 같은 답을 내요(값과 순서는 옮기기 전 `live.py` 그대로).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..domain.engine import FEE
from ..domain.markets.kr import lower_limit, tick_round, ticks_below
from ..domain.rules import sell_floor

LOOKUPS = 3  # R-O12: 결과 모르는 주문은 내역에서 3번 찾아요(2분 동안)
STEP_WAIT = timedelta(minutes=3)  # R-O6: 장중 매도가 3분 미체결이면 한 걸음 넓혀요
TRIGGER_WAIT = timedelta(minutes=15)  # R-X9: 조건주문 발동 뒤 15분 안에 체결이 없으면 취소 + 보호 매도 길
COND_RENEW_DAYS = 30  # R-X8: 만료 30일 전이면 다시 걸어요
COND_EXPIRE_DAYS = 364  # 조건주문 유효 기간(거는 날부터)
COND_STOP_GAP = 0.03  # R-X6: 손절 지정가 = 감시가 −3%(가정)
ORDER_MAX_DEFAULT = 20_000_000  # R-O8: 주문 하나 크기 한도 기본값(운용 설정 `order_max`가 없을 때)


def client_order_id(rid: int, d: str, sym: str, side: str, rnd: int) -> str:
    """앱 주문 번호(S9): 운용 · 날짜 · 종목 · 방향 첫 글자 · 회차(결과 모름이면 +1 · R-O12)."""
    return f"q{rid}-{d.replace('-', '')}-{sym}-{side[0]}-{rnd}"


def buy_quantity(value: float, cap: float, cash: float) -> int:
    """R-O3: 수량 = ⌊목표 ÷ 상한⌋ · 묶이는 돈(상한 × 수량 × (1 + 수수료))이 운용 현금 이하가 될 때까지 1주씩 줄여요."""
    qty = int(value // cap)
    while qty > 0 and qty * cap * (1 + FEE) > cash:
        qty -= 1
    return qty


def open_sell_price(close: float, protect: bool) -> float:
    """시가 매도 지정가: 보호 매도는 하한가(가격 하한 없음 · R-O5), 일반 매도는 가격 하한(R-O3)."""
    return lower_limit(close) if protect else sell_floor(close)


def intraday_sell_price(price: float) -> float:
    """장중 매도 첫 지정가: 현재가 2호가 아래(R-O6 · 전부 팔기의 장중 매도도 같음)."""
    return ticks_below(price, 2)


def widen_step(kind: str, step: int, price: float, floor: float = 0.0) -> tuple[str, float | None] | None:
    """R-O6 넓히기 한 걸음: (주문 꼴, 새 지정가) 또는 None(더 넓히지 않음).

    익절(`intraday_take`)은 한 번만 −5호가로 내리고 지정가 하한(`floor`) 아래로 내려가지 않아요. 보호 매도는 1걸음 −5호가 →
    2걸음 시장가."""
    if kind == "intraday_take":
        if step >= 2:
            return None
        return "LIMIT", max(ticks_below(price, 5), floor)
    if step == 1:
        return "LIMIT", ticks_below(price, 5)
    if step == 2:
        return "MARKET", None
    return None


def cond_triggers(stop: float | None, take: float | None) -> tuple[float | None, float | None]:
    """조건주문 감시가(호가로 반올림 · 없으면 None)."""
    return (tick_round(stop) if stop else None), (tick_round(take) if take else None)


def cond_renew_due(expire: str | None, today: date) -> bool:
    """R-X8: 걸어 둔 조건주문의 만료가 30일 안이면 다시 걸어요."""
    return bool(expire) and date.fromisoformat(expire or "") - today <= timedelta(days=COND_RENEW_DAYS)


def cond_expire(today: date) -> date:
    return today + timedelta(days=COND_EXPIRE_DAYS)


def cond_legs(stop_t: float | None, take_t: float | None) -> tuple[str, list[dict[str, Any]]]:
    """같은 종목 손절 + 익절이면 OCO 하나, 하나면 SINGLE(R-X6). 손절 다리의 지정가는 감시가 −3%를 호가로."""
    legs: list[dict[str, Any]] = []
    if stop_t:
        legs.append({"side": "SELL", "trigger": int(stop_t), "price": int(tick_round(stop_t * (1 - COND_STOP_GAP)))})
    if take_t:
        legs.append({"side": "SELL", "trigger": int(take_t), "price": int(take_t)})
    return ("OCO" if len(legs) == 2 else "SINGLE"), legs


def unfilled_buy_close(filled: int, qty: Any) -> tuple[str, str]:
    """09:00 체결 뒤 남은 매수 취소(R-O13): (기록 상태, 기록 글). 일부 체결이면 남은 매수만 취소."""
    note = f"일부 체결 {filled}/{qty}주" if filled else "미체결 · 취소"
    return ("partial_closed" if filled else "canceled"), note


def closed_status(filled: int) -> str:
    """토스가 닫은 주문(거절 · 취소 · 만료)의 기록 상태: 일부라도 체결됐으면 'partial_closed', 아니면 'failed'."""
    return "partial_closed" if filled else "failed"
