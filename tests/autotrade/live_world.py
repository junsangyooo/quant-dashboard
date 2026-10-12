"""A live ledger against the fake Toss (tests/autotrade/fake_toss.py), for the phase 3 tests.

The first-day market of 예시-값표 §4 (KR 32,000 · US $66.00 · 1,392.0원) and a Toss account
holding 10,000,000 won. The tick's process has AUTOTRADE_LIVE_ORDERS=1 and Toss keys in a
secrets file of its own (never the laptop's); the transport is the fake: nothing reaches out.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from autotrade.config import Config
from autotrade.db import live_repo, repo
from autotrade.db.connection import connect, transaction
from autotrade.engine import live
from autotrade.engine.bootstrap import bootstrap
from autotrade.engine.live import PreviewData
from autotrade.jobs.live_tasks import broker_job, reconcile_job
from autotrade.jobs.tasks import (
    JobContext,
    _prefetch_window,
    _rule_instruments,
    check_job,
    snapshot_job,
    stage_job,
)
from autotrade.timeutil import kst_date
from autotrade.jobs.tick import run_tick

from .fake_toss import FakeToss
from .fakes import KR, US, World
from .helpers import PHASE1_SHARES, kst

D = Decimal
SECRETS = "TOSS_CLIENT_ID=tsck_live_test\nTOSS_CLIENT_SECRET=s3cret\nTOSS_ACCOUNT_NO=123-4567-8901\n"


def market(world: World) -> None:
    """Closes of 6/26-6/30 and the rates around them (the §4 first day, a day early)."""
    for d in ("2026-06-25", "2026-06-26", "2026-06-29"):
        world.bar(KR, d, close="31900", open_="31900")
        world.bar(US, d, close="65.90", open_="65.90")
    world.bar(KR, "2026-06-30", close="32000", open_="31950")
    world.bar(US, "2026-06-30", close="66.00", open_="65.95")
    world.rate(kst("2026-06-30 16:00"), "1392.0")
    world.rate(kst("2026-06-30 21:00"), "1392.0")
    world.rate(kst("2026-07-01 08:25"), "1392.0")
    world.rate(kst("2026-07-01 09:10"), "1392.0")
    world.rate(kst("2026-07-01 16:00"), "1391.5")
    world.bar(KR, "2026-07-01", close="32050", open_="32000")
    world.bar(US, "2026-07-01", close="66.20", open_="66.00")


@dataclass
class Live:
    ctx: JobContext
    fake: FakeToss
    world: World
    clock: list[datetime] = field(default_factory=lambda: [kst("2026-06-30 20:00")])
    lines: list[dict[str, Any]] = field(default_factory=list)

    @property
    def conn(self) -> sqlite3.Connection:
        return self.ctx.conn

    @property
    def cfg(self) -> Config:
        return self.ctx.cfg

    def now(self) -> datetime:
        return self.clock[0]

    def at(self, text: str) -> datetime:
        self.clock[0] = kst(text)
        return self.clock[0]

    def sync(self, text: str | None = None) -> dict[str, Any]:
        at = self.at(text) if text else self.now()
        return broker_job(self.conn, self.cfg, at, transport=self.fake, now=self.now, sleep=lambda s: None)

    def reconcile(self, text: str | None = None) -> dict[str, Any]:
        at = self.at(text) if text else self.now()
        return reconcile_job(self.conn, self.cfg, at)

    def check(self, text: str) -> dict[str, Any]:
        return check_job(self.ctx, "live", self.at(text))

    def stages(self, text: str | None = None) -> dict[str, Any]:
        at = self.at(text) if text else self.now()
        return stage_job(self.ctx, "live", at)

    def snapshot(self, text: str) -> dict[str, Any]:
        return snapshot_job(self.ctx, "live", self.at(text))

    def tick(self, text: str) -> list[dict[str, Any]]:
        at = self.at(text)
        out: list[dict[str, Any]] = []
        run_tick(self.ctx, "live", lambda: at, self.cfg.db_path.parent, out.append)
        self.lines.extend(out)
        return out

    def market_data(self) -> None:
        """What the paper ledger's jobs download anyway (closes, the rate): the preview reads it."""
        _prefetch_window(self.ctx, _rule_instruments(self.conn), kst_date(self.now()), self.now())

    def preview(self) -> PreviewData:
        self.market_data()
        data = live.preview_data(self.conn, self.cfg, self.now())
        assert isinstance(data, PreviewData), data
        return data

    def turn_on(self, text: str = "2026-06-30 21:00") -> PreviewData:
        self.sync(text)
        data = self.preview()
        with transaction(self.conn):
            live.turn_on(self.conn, self.cfg, self.now(), data)
        return data

    def turn_off(self, text: str) -> live.TurnOff:
        with transaction(self.conn):
            return live.turn_off(self.conn, self.at(text))

    def state(self) -> Any:
        return repo.load_state(self.conn, "live")

    def status(self) -> live_repo.BrokerStatus:
        status = live_repo.get_status(self.conn)
        assert status is not None
        return status


@pytest.fixture
def live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first key, in this test's process only (the conftest removes it before each test)."""
    monkeypatch.setenv("AUTOTRADE_LIVE_ORDERS", "1")


def make_live(tmp_path: Path, world: World, *, with_key: bool = True) -> Iterator[Live]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    secrets = tmp_path / "secrets.env"
    secrets.write_text(SECRETS)
    cfg = Config(
        db_path=tmp_path / "data" / "autotrade.db",
        rule_shares=PHASE1_SHARES,
        live_orders=with_key,
        secrets_env=secrets,
    )
    conn = connect(cfg.db_path)
    bootstrap(conn, cfg, kst("2026-06-30 12:00"))
    market(world)
    holder = Live(JobContext(conn, cfg, world.sources()), FakeToss(lambda: holder.now()), world)
    holder.ctx = replace(holder.ctx, toss_transport=holder.fake, wall=holder.now, sleep=lambda s: None)
    holder.fake.cash["KRW"] = D("10000000")
    holder.fake.prices = {"069500": D("32000"), "SPYM": D("66.00")}
    holder.fake.rate = D("1392.0")
    try:
        yield holder
    finally:
        conn.close()
