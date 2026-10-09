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
from .helpers import kst


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
    monkeypatch.delenv("AUTOTRADE_LIVE_ORDERS", raising=False)
    monkeypatch.delenv("AUTOTRADE_DB", raising=False)


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(db_path=tmp_path / "autotrade.db", paper_start_date=date(2026, 7, 1))


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
