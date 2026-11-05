"""조립(ARCHITECTURE 2절 조립 층 · TASKS P1-08): 앱 루프.

조립이 만든 일을 30초마다(`run/scheduler.py`의 시각 표 `LOOP_EVERY_S`) 차례로 돌려요: 세션 만료 확인 → 평일 16:30 자동 확인 →
(켤 때 한 번) 꺼져 있던 날 모의투자 채우기 · 업데이트 끝 알림 → 스케줄러(20:10 확인) → 실전 tick(08:30 점검 · 08:35 주문 ·
장중 감시) → 텔레그램 받기. 한 일이 실패해도 루프는 멈추지 않아요(종류만 기록).

`create_app`(어댑터 고르기 · 라우터 등록 · 설정 한 번 읽기)은 아직 `main.py`에 있고 P1-09에서 이 파일로 옮겨 와요. 그때까지
`main.create_app`이 일(`LoopSteps`)을 만들어 lifespan에서 `auto_loop`를 띄워요. 일은 부를 때마다 이름을 찾는 함수로 넘겨요
(앱 상태의 객체를 시험이 바꿔 끼워도 루프가 그것을 불러요 · 옮기기 전 `main._auto_loop`와 같음).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .domain.markets.kr import KST
from .run.data import Calendar
from .run.scheduler import LOOP_EVERY_S, UPDATE_FROM, UPDATE_UNTIL
from .services import updates
from .store.db import DB

log = logging.getLogger("quant-mvp")


@dataclass(frozen=True)
class LoopSteps:
    touch: Callable[[], object]  # 세션이 만료됐으면 요청이 없어도 30초 안에 데이터 키와 연결 객체를 지워요
    auto_tick: Callable[[], object]  # 평일 16:30 자동으로 한 번(`app.state.auto_tick`)
    catch_up: Callable[[], object]  # 켤 때 한 번: 꺼져 있던 날을 이어서 채워요(모의투자 · R-V4)
    announce: Callable[[], object]  # 켤 때 한 번: 업데이트 끝 알림(SPEC 5-10 · 루프 안에서 바로 불러요)
    run_due: Callable[[], object]  # 스케줄러: 때가 된 일(20:10 확인 · 실패하면 10분 뒤 다시)
    live_tick: Callable[[], object]  # 실전 tick: 08:20 대조 · 08:30 ~ 08:50 점검 창 · 08:35 주문 · 장중 1분마다(R-O1)
    poll: Callable[[], object]  # 텔레그램 `/상태` · `/멈춤`(등록 대화방만)


async def auto_loop(steps: LoopSteps) -> None:
    first = True
    while True:
        try:
            steps.touch()
            await asyncio.to_thread(steps.auto_tick)
            if first:
                first = False
                await asyncio.to_thread(steps.catch_up)
                steps.announce()
            await asyncio.to_thread(steps.run_due)
            await asyncio.to_thread(steps.live_tick)
            await asyncio.to_thread(steps.poll)
        except Exception as exc:  # 루프는 멈추지 않는다
            log.error("auto tick failed: %s", type(exc).__name__)
        await asyncio.sleep(LOOP_EVERY_S)


# ── 설치기(입구 `install.py` · `python -m app.install`)가 조립을 거쳐 쓰는 것 ─────────────────────────────


def stored_calendar(data: Path) -> Calendar | None:
    """`can-update`: 앱이 데이터 폴더 DB에 받아 둔 토스 장 달력(DB가 없으면 None · 그때는 평일 규칙)."""
    db_path = data / "app.db"
    return Calendar(DB(db_path), None) if db_path.exists() else None


def update_window_state(now: datetime, cal: Calendar | None = None) -> str | None:
    """SPEC 5-10 업데이트 창(거래일 16:00 ~ 20:00 · `run/scheduler.py` 시각 표): 안이면 None · 거래일이 아니면 'closed' ·
    시간 밖이면 'hours'(글은 설치기가 붙여요)."""
    local = now.astimezone(KST)
    is_open = cal.is_open(local.date()) if cal is not None else local.weekday() < 5
    if not is_open:
        return "closed"
    if not (UPDATE_FROM <= local.time() < UPDATE_UNTIL):
        return "hours"
    return None


def write_update_step(data: Path, step: str, state: str, version: str, now: datetime) -> None:
    """설치기 `step`: `update.json`에 한 단계를 적어요(꼴은 `services/updates.py` · 시각은 한국 시간 초 단위)."""
    updates.write_step(data, step, state, version, at=now.astimezone(KST).isoformat(timespec="seconds"))
