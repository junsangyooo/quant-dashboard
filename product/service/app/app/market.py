"""서버 시계: 한국 시간 지금 시각(`Clock` 포트의 기본 구현 · `create_app(now=…)`의 기본값).

일봉 · 장 달력을 받아 담아 두는 일은 `run/data.py`로, 토스 일봉 원천(`TossSource`)은 `adapters/toss.py`로 옮겼어요(P1-08).
이 함수만 이 자리에 남아요: 기준선 시계 고정 자리(`tests/baseline/clock.py` `CLOCK_SITES`의 `app.market.datetime`)가 이 모듈에
닿고, 시계 자리를 옮기는 일은 열린 질문 Q-N24의 답 뒤예요.
"""

from __future__ import annotations

from datetime import datetime

from .domain.markets.kr import KST


def now_kst() -> datetime:
    return datetime.now(KST)
