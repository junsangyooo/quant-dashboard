"""Fixtures for the web API tests: a temp database built through the engine, a fixed clock,
and a TestClient over https (the session cookie is Secure).

The app never migrates (autotrade/api/schema.py), so `app` depends on `db`, which bootstraps the
database the way `python -m autotrade.jobs migrate` does on the server."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autotrade.api.app import create_app
from autotrade.api.settings import ApiSettings
from autotrade.config import Config
from autotrade.db.connection import connect
from autotrade.engine.bootstrap import bootstrap
from autotrade.jobs.tasks import JobContext

from ..fakes import World
from ..helpers import PHASE1_SHARES, kst
from .support import PIN, Clock, owner_pin


@pytest.fixture
def api_cfg(tmp_path: Path) -> Config:
    return Config(
        db_path=tmp_path / "autotrade.db",
        paper_start_date=date(2026, 7, 1),
        rule_shares=PHASE1_SHARES,
    )


@pytest.fixture
def settings(tmp_path: Path) -> ApiSettings:
    return ApiSettings(
        secret_path=tmp_path / "autotrade.secret", dist_dir=tmp_path / "dist", scrypt_n=2**10
    )


@pytest.fixture
def clock() -> Clock:
    return Clock(kst("2026-07-01 16:10"))


@pytest.fixture
def db(api_cfg: Config) -> Iterator[sqlite3.Connection]:
    conn = connect(api_cfg.db_path)
    bootstrap(conn, api_cfg, kst("2026-06-30 12:00"))
    yield conn
    conn.close()


@pytest.fixture
def world() -> World:
    return World()


@pytest.fixture
def jobs(db: sqlite3.Connection, api_cfg: Config, world: World) -> JobContext:
    return JobContext(db, api_cfg, world.sources())


@pytest.fixture
def app(api_cfg: Config, settings: ApiSettings, clock: Clock, db: sqlite3.Connection) -> FastAPI:
    return create_app(api_cfg, settings, clock)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, base_url="https://testserver") as c:
        yield c


@pytest.fixture
def logged_in(client: TestClient, db: sqlite3.Connection, settings: ApiSettings) -> TestClient:
    owner_pin(db, settings)
    response = client.post("/api/auth/pin", json={"pin": PIN})
    assert response.status_code == 204, response.text
    return client
