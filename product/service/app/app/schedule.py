"""스케줄러(T-51 · SPEC 10 main): 거래일 · 장 시작은 토스 market-calendar(`market.Calendar`)로 정해요.

- 일은 '평소 시각'(예: 20:10 확인 · 08:30 점검 · 08:35 시가 주문)과 장 시작을 따라 옮기는지(R-O1)로 적어요.
- 쉬는 날에는 돌지 않아요. 장이 늦게 열리는 날은 아침 일을 그만큼 늦춰요(`DayHours.at`).
- 하루 한 번: 그날 돈 일은 `meta sched.<이름>`에 날짜를 남겨 다시 돌지 않아요(앱을 다시 켜도 같아요).
- 일이 예외를 내면 날짜를 남기지 않아 다음 바퀴에 다시 해요(R-L4의 10분마다 다시는 실전 단계에서 더해요).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from .db import DB
from .domain.markets.kr import KST
from .market import Calendar

log = logging.getLogger("quant-mvp")


@dataclass
class Job:
    name: str
    hh: int
    mm: int
    run: Callable[[], object]
    follow_open: bool = False  # 장 시작이 늦으면 같이 늦춰요(아침 일)
    retry_every: timedelta = timedelta(minutes=10)


class Scheduler:
    def __init__(self, db: DB, calendar: Calendar, now: Callable[[], datetime]) -> None:
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
