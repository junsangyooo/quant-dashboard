"""백테스트 기본 기간의 '오늘'(기준선 시계 고정 자리 · 1단계 예외 실제 시계 · 열린 질문 Q-N24).

v2 전략 API는 `app/api/strategies.py`(API 층 · TASKS P1-09)로 옮겼어요. 이 파일에는 **정의** `backtest_today`만 남아요:
기준선 도구(`tests/baseline/clock.py`)가 `CLOCK_SITES`의 `("app.api_v2", "datetime")`로 이 모듈 이름의 전역을 바꿔 끼워
백테스트 기본 기간의 끝(옛 `api_v2.py:237` `datetime.now(KST).date()`)을 고정해요. 옮기면 그 기록과 시험의 '닿는 자리'를
고쳐야 해서 Q-N24 답 전까지 여기 두고, 조립(`app.py`)이 이 함수를 전략 라우터의 `today`로 넘겨요.
"""

from __future__ import annotations

from datetime import date, datetime

from .domain.markets.kr import KST


def backtest_today() -> date:
    return datetime.now(KST).date()
