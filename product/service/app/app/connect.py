"""연결 확인의 기록 시각(기준선 시계 고정 자리 · 열린 질문 Q-N24).

토스 키 저장 · 연결 확인 흐름은 `app/services/connect.py`(쓰기 일 층 · TASKS P1-09)로 옮겼어요. 이 파일에는 **정의** `_now`만
남아요: 기준선 도구(`tests/baseline/clock.py`)가 `CLOCK_SITES`의 `("app.connect", "datetime")`로 이 모듈 이름의 전역을 바꿔
끼워 연결 확인 시각을 고정해요. 옮기면 그 기록과 시험의 '닿는 자리'를 고쳐야 해서 Q-N24 답 전까지 여기 두고, 조립(`app.py`)이
이 함수를 `Connections(now=…)`로 넘겨요.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
