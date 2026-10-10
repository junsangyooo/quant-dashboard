"""Helpers for the web API tests."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from autotrade.api.auth import set_pin
from autotrade.api.security import load_or_create_secret
from autotrade.api.settings import ApiSettings
from autotrade.jobs.tasks import JobContext, check_job, snapshot_job, stage_job

from ..fakes import KR, US, World
from ..helpers import kst

PIN = "123456"
COOKIE = "__Host-qsess"  # the production cookie (ApiSettings.cookie_secure is True in tests)


@dataclass
class Clock:
    now: datetime

    def __call__(self) -> datetime:
        return self.now


def owner_pin(db: sqlite3.Connection, settings: ApiSettings, pin: str = PIN) -> None:
    set_pin(
        db,
        load_or_create_secret(settings.secret_path),
        pin,
        settings.scrypt_n,
        kst("2026-06-30 12:00"),
    )


def first_day(world: World, jobs: JobContext) -> None:
    """예시-값표 §4 through the engine: start 7/1, buys at 09:05 and 09:10, snapshot 16:00."""
    world.bar(KR, "2026-06-30", close="32000", open_="31900")
    world.bar(US, "2026-06-30", close="66.00", open_="65.80")
    world.rate(kst("2026-07-01 08:25"), "1392.0")
    world.rate(kst("2026-07-01 09:10"), "1392.0")
    world.rate(kst("2026-07-01 16:00"), "1391.5")
    world.bar(KR, "2026-07-01", close="32050", open_="32000")
    world.bar(US, "2026-07-01", close="66.20", open_="66.00")
    assert check_job(jobs, "paper", kst("2026-07-01 08:30"))["result"] == "rebalance"
    stage_job(jobs, "paper", kst("2026-07-01 09:05"))
    stage_job(jobs, "paper", kst("2026-07-01 09:10"))
    assert snapshot_job(jobs, "paper", kst("2026-07-01 16:00"))["result"] == "ok"
