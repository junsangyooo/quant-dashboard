"""전략 저장 · 복원의 기록 시각(기준선 시계 고정 자리 · 열린 질문 Q-N24).

FastAPI 앱 조립(`create_app` · 라우터 등록 · 앱 루프)은 `app/app.py`(조립 층 · TASKS P1-09)로, 라우트는 `app/api/*`(기능별
라우터)로, 쓰기 일은 `app/services/*`로 옮겼어요. 서버는 `python -m app.serve`로 켜요(ARCHITECTURE 5절).

이 파일에는 **정의** `_now`만 남아요: 기준선 도구(`tests/baseline/clock.py`)가 `CLOCK_SITES`의 `("app.main", "datetime")`로 이
모듈 이름의 전역을 바꿔 끼워 전략 저장 · 백테스트 기록 · 복원 시각을 고정해요. 옮기면 그 기록과 시험의 '닿는 자리'를 고쳐야 해서
Q-N24 답 전까지 여기 두고, 조립(`app.py`)이 이 함수를 전략 라우터 · 데이터 라우터의 `now`로 넘겨요.
"""

from __future__ import annotations

from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
