"""거래 비용 한 표(TASKS P1-10 · ARCHITECTURE 4절 '시장' · ENGINE-RULES R-B1 · R-B3 · R-L7 · 지난 T-87).

수수료 · 매도 세금 · 배당 원천징수를 날짜별 표 하나에 둬요. 비용 숫자는 여기에만 정의해요(`tests/test_costs.py`가 지켜요).
순수 값과 찾기만 있어요(지금 시각 · 저장 · 전송을 모름 · 날짜는 받아서 찾음).

- 값은 옮기기 전 코드 값 그대로예요: 수수료 0.015%(사고팔 때 · 옛 `engine.FEE`) · 매도 세금 0.18%(옛 `engine.SELL_TAX` · v1 값) ·
  배당 원천징수 15.4%(옛 `live.py`의 배당 맞추기 식).
- 1단계는 표가 한 줄(모든 날 같은 값)이라 엔진 · 실행 흐름은 그 줄의 이름(`FEE` · `SELL_TAX` · `DIVIDEND_WITHHOLDING`)을 읽어요.
  매도한 날의 세율 표(R-B4 · 2019 ~ 2026 줄)와 백테스트 칩의 오늘 세율(그림 '0.20%')은 2단계예요(OPEN-QUESTIONS Q-N26 · Q-T9).
- 실전 체결은 토스가 알려 준 수수료 · 세금을 먼저 써요(R-L7). 이 표는 그 값이 없을 때만 써요.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Costs:
    """`since`부터(그날 포함) 다음 줄 전날까지 쓰는 비용 비율(체결 금액 · 배당금에 곱해요)."""

    since: date
    fee: float  # 수수료(사고팔 때)
    sell_tax: float  # 매도 세금(증권거래세 + 농어촌특별세 합계)
    dividend_withholding: float  # 배당 원천징수(배당소득세 + 지방소득세)


# 날짜 차례대로. 첫 줄은 모든 날을 덮어요(`date.min`).
TABLE: tuple[Costs, ...] = (
    Costs(since=date.min, fee=0.00015, sell_tax=0.0018, dividend_withholding=0.154),
)

_SINCE = [row.since for row in TABLE]


def costs_on(day: date | str) -> Costs:
    """그날(`date` 또는 `YYYY-MM-DD`)에 쓰는 줄."""
    d = date.fromisoformat(day) if isinstance(day, str) else day
    return TABLE[bisect_right(_SINCE, d) - 1]


# 1단계: 표가 한 줄이라 모든 날 같은 값이에요(`tests/test_costs.py`가 날짜마다 같은지 봐요).
FLAT = TABLE[0]
FEE = FLAT.fee
SELL_TAX = FLAT.sell_tax
DIVIDEND_WITHHOLDING = FLAT.dividend_withholding
