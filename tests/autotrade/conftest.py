"""Fixtures for the autotrade tests.

Every test runs with the network blocked and live orders impossible: the laptop's secrets hold a
live broker account (ops notes 안전), so no test may reach the outside world.
"""

from __future__ import annotations

import socket
import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from autotrade.config import Config
from autotrade.db.connection import connect
from autotrade.engine.bootstrap import bootstrap
from autotrade.jobs.tasks import JobContext

from .fakes import World
from .helpers import PHASE1_SHARES, kst


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("network access in autotrade tests")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)


@pytest.fixture(autouse=True)
def _no_live_orders(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "AUTOTRADE_LIVE_ORDERS",
        "AUTOTRADE_DB",
        "AUTOTRADE_AI_CALLS",
        "AUTOTRADE_CLAUDE_BIN",
        "AUTOTRADE_SECRETS_ENV",
        "AUTOTRADE_PAPER_SHARES",
        "AUTOTRADE_LIVE_SHARES",
        "DART_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(
        db_path=tmp_path / "autotrade.db",
        paper_start_date=date(2026, 7, 1),
        rule_shares=PHASE1_SHARES,
    )


@pytest.fixture
def conn(cfg: Config) -> Iterator[sqlite3.Connection]:
    c = connect(cfg.db_path)
    bootstrap(c, cfg, kst("2026-06-30 12:00"))
    yield c
    c.close()


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def ctx(conn: sqlite3.Connection, cfg: Config, world: World) -> JobContext:
    ticks = iter(range(10**6))
    return JobContext(conn, cfg, world.sources(), clock=lambda: float(next(ticks)) * 0.001)


@pytest.fixture
def p2cfg(tmp_path: Path) -> Config:
    """Phase 2: the default shares (paper 80/20 with '3년 발굴')."""
    return Config(db_path=tmp_path / "p2.db", paper_start_date=date(2026, 7, 1))


@pytest.fixture
def p2conn(p2cfg: Config) -> Iterator[sqlite3.Connection]:
    c = connect(p2cfg.db_path)
    bootstrap(c, p2cfg, kst("2026-06-30 12:00"))
    yield c
    c.close()


@pytest.fixture
def p2ctx(p2conn: sqlite3.Connection, p2cfg: Config, world: World) -> JobContext:
    """A paper ledger that started on 7/1, with the seed's 15 picks held."""
    from .phase2 import start_paper

    ticks = iter(range(10**6))
    ctx = JobContext(p2conn, p2cfg, world.sources(), clock=lambda: float(next(ticks)) * 0.001)
    start_paper(ctx, world)
    return ctx
