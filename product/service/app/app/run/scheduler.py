"""일 시각 표 하나 + 스케줄러(T-51 · SPEC 10 main · TASKS P1-08 · ARCHITECTURE 6절 '시각' · QUALITY X5).

- **일 시각 표**(아래 `# ── 일 시각 표` 묶음): 앱이 일을 하는 평소 시각은 모두 여기에만 둬요(20:10 확인 · 16:30 자동 확인 ·
  08:20 대조 · 08:30 ~ 08:50 점검 창 · 08:35 시가 주문 · 09:01 ~ 15:20 장중 · 16:00 ~ 20:00 업데이트 창 · 앱 루프 30초).
  장 시간 · 휴장일 · 한국 시간 · 확정 시각은 `domain/markets/kr.py`예요(일 시각이 아니라 시장 정의).
- 거래일 · 장 시작은 토스 market-calendar(`run/data.py`의 `Calendar`)로 정해요.
- 일은 '평소 시각'(예: 20:10 확인)과 장 시작을 따라 옮기는지(R-O1)로 적어요.
- 쉬는 날에는 돌지 않아요. 장이 늦게 열리는 날은 아침 일을 그만큼 늦춰요(`DayHours.at`).
- 하루 한 번: 그날 돈 일은 `meta sched.<이름>`에 날짜를 남겨 다시 돌지 않아요(앱을 다시 켜도 같아요).
- 일이 예외를 내면 날짜를 남기지 않아 다음 바퀴에 다시 해요(10분 뒤 · R-L4).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from ..domain.markets.kr import KST
from ..ports import Clock
from ..store.db import DB
from .data import Calendar

log = logging.getLogger("quant-mvp")

# ── 일 시각 표(평소 시각 · 한국 시간) ──────────────────────────────────────────
# 하루 한 번 일(스케줄러 · 장 시작을 따라 옮기지 않음)
DAILY_CHECK = (20, 10)  # 20:10 확인: 실전 `live_check` · 모의투자 `paper_check`(R-O1 · R-V2)
DAILY_CHECK_TIME = time(*DAILY_CHECK)  # 그 시각 뒤 시작이면 바로 확인(R-L11) · 전략 변경은 그 시각 전이면 오늘부터(R-L10)
AUTO_CHECK = (16, 30)  # 평일 16:30 자동으로 한 번(`auto_tick` · app.state.auto_tick)
RETRY_EVERY = timedelta(minutes=10)  # 실패한 일은 10분 뒤 다시(R-L4)
UPDATE_FROM = time(16, 0)  # 업데이트 창: 거래일 16:00 ~ 20:00(20:10 확인 전 · SPEC 5-10 · `install can-update`)
UPDATE_UNTIL = time(20, 0)
# 실전 tick(앱 루프마다 · 장 시작이 늦은 날은 `DayHours.at`으로 그만큼 늦춰요 · R-O1)
RECONCILE_AT = (8, 20)  # 대조(R-L6) · 그날 한 번
PRECHECK_AT = (8, 30)  # 점검 창 시작(R-L3)
PRECHECK_EVERY = timedelta(minutes=5)  # 점검이 실패하면(False) 창 안에서 5분마다 다시
ORDER_AT = (8, 35)  # 시가 단일가 주문(R-O3) · 점검 통과 뒤
LATE_OPEN = (8, 50)  # 점검 창 끝(`<=`) · 이 뒤로는 그날 시가 주문을 건너뛰어요(R-L2 · R-L3)
INTRADAY_FROM = (9, 1)  # 체결 대조 · 미체결 취소(그날 한 번) · 장중 감시 1분마다(R-O13 · R-X5)
INTRADAY_UNTIL = (15, 20)  # 장중 감시 끝 · 전부 팔기의 '장중' 끝
# 앱 루프
LOOP_EVERY_S = 30  # 한 바퀴(16:30 자동 확인 → 스케줄러 → 실전 tick → 텔레그램 받기)


@dataclass
class Job:
    name: str
    hh: int
    mm: int
    run: Callable[[], object]
    follow_open: bool = False  # 장 시작이 늦으면 같이 늦춰요(아침 일)
    retry_every: timedelta = RETRY_EVERY


class Scheduler:
    def __init__(self, db: DB, calendar: Calendar, now: Clock) -> None:
        self.db = db
        self.calendar = calendar
        self.now = now
        self.jobs: list[Job] = []
        self._failed_at: dict[str, datetime] = {}

    def add(self, name: str, hh: int, mm: int, run: Callable[[], object], *, follow_open: bool = False) -> None:
        self.jobs.append(Job(name, hh, mm, run, follow_open))

    def when(self, job: Job, now: datetime) -> datetime | None:
        """오늘 그 일이 돌 시각(쉬는 날이면 None)."""
        day = self.calendar.day(now.astimezone(KST).date())
        if not day.open:
            return None
        if job.follow_open:
            return day.at(job.hh, job.mm)
        return datetime.combine(day.d, datetime.min.time(), KST).replace(hour=job.hh, minute=job.mm)

    def due(self) -> list[str]:
        now = self.now().astimezone(KST)
        today = now.date().isoformat()
        out = []
        for job in self.jobs:
            at = self.when(job, now)
            if at is None or now < at or self.db.get_meta(f"sched.{job.name}") == today:
                continue
            failed = self._failed_at.get(job.name)
            if failed is not None and now - failed < job.retry_every:
                continue
            out.append(job.name)
        return out

    def run_due(self) -> list[str]:
        """때가 된 일을 돌려요. 돈 일 이름을 돌려줘요."""
        done = []
        today = self.now().astimezone(KST).date().isoformat()
        names = set(self.due())
        for job in self.jobs:
            if job.name not in names:
                continue
            try:
                job.run()
            except Exception as exc:  # 다른 일은 계속
                log.error("job %s failed: %s", job.name, type(exc).__name__)
                self._failed_at[job.name] = self.now().astimezone(KST)
                continue
            self._failed_at.pop(job.name, None)
            self.db.set_meta(f"sched.{job.name}", today)
            done.append(job.name)
        return done
