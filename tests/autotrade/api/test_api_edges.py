"""Edge paths: pending conversion, recovered check, filled retry, empty days, both markets
closed, errors inside the app, session refresh, mode change records, formatting helpers."""

from __future__ import annotations

import hashlib
import hmac
import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autotrade.api import schema
from autotrade.api.security import read_token, verify_pin
from autotrade.api.views import fmt
from autotrade.api.views import home as home_view
from autotrade.api.views.context import LedgerContext
from autotrade.api.views.history import DayData
from autotrade.api.views.series import months_back, period_start
from autotrade.config import Config
from autotrade.db import auth_repo, repo
from autotrade.db.connection import transaction
from autotrade.jobs.tasks import JobContext, check_job, stage_job

from ..fakes import KR, US, World
from ..helpers import kst, seed_ledger
from .support import PIN, Clock

D = Decimal


def relogin(client: TestClient, clock: Clock, when: str) -> None:
    clock.now = kst(when)
    assert client.post("/api/auth/pin", json={"pin": PIN}).status_code == 204


def seed(db: sqlite3.Connection, world: World) -> None:
    seed_ledger(
        db,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("47675"),
        usd=D("1.66"),
        positions={KR: (120, D("3840576"), D("3840576")), US: (46, D("3033.03"), D("4221675"))},
    )
    world.bar(KR, "2026-10-06", close="36360", open_="36300")
    world.bar(US, "2026-10-06", close="62.40", open_="62.10")
    world.rate(kst("2026-10-07 08:25"), "1380.6")
    world.rate(kst("2026-10-07 09:10"), "1380.6")


def test_a_rebalance_before_its_first_stage(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    seed(db, world)
    check_job(jobs, "paper", kst("2026-10-07 08:30"))
    relogin(logged_in, clock, "2026-10-07 08:40")
    home = logged_in.get("/api/home").json()
    assert home["planChip"]["next"] == {
        "kind": "order",
        "at": "2026-10-07T09:05:00+09:00",
        "market": "KR",
        "side": "sell",
        "instrumentName": "KOSPI200 ETF",
        "qty": 5,
    }
    sell, fx, buy = home["planCard"]["stages"]
    assert [s["status"] for s in (sell, fx, buy)] == ["pending", "pending", "pending"]
    order = fx["orders"][0]
    assert order["fx"] == {"krw": 173000, "usd": 125.3, "rate": 1380.6}
    assert order["approx"] is True
    assert sell["orders"][0]["fee"] == {"krw": 27}
    assert home["trend"]["events"][-1] == {
        "date": "2026-10-07",
        "kind": "in-progress",
        "kinds": ["in-progress"],
    }
    assert logged_in.get("/api/history").json()["tiles"]["rebalances"]["inProgress"] == 1


def test_recovered_check_and_filled_retry(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    seed(db, world)
    world.fail_bars.add(US)
    world.remove_bar(US, "2026-10-06")
    check_job(jobs, "paper", kst("2026-10-07 08:30"))
    world.fail_bars.clear()
    world.bar(US, "2026-10-06", close="62.40", open_="62.10")
    assert check_job(jobs, "paper", kst("2026-10-07 09:30"), retry=True)["result"] == "rebalance"
    world.bar(KR, "2026-10-07", close="36250", open_="36380")
    stage_job(jobs, "paper", kst("2026-10-07 09:45"))
    world.fail_bars.add(US)
    stage_job(jobs, "paper", kst("2026-10-07 22:30"))
    world.fail_bars.clear()
    world.bar(US, "2026-10-07", close="62.40", open_="62.40")
    world.bar(US, "2026-10-08", close="62.70", open_="62.50")
    world.rate(kst("2026-10-08 08:25"), "1381.0")
    stage_job(jobs, "paper", kst("2026-10-08 22:30"))
    relogin(logged_in, clock, "2026-10-09 08:00")
    history = logged_in.get("/api/history").json()
    rows = history["months"][0]["events"]
    failed = next(e for e in rows if e["kind"] == "check-failed")
    assert (failed["failureReason"], failed["recoveredOn"]) == ("no-quote", "2026-10-07")
    rebalance = next(e for e in rows if e["kind"] == "partial-failed")
    assert rebalance["retry"] == {"date": "2026-10-08", "filled": True}  # '10/8 다시 · 체결'
    assert history["tiles"]["rebalances"]["partialFailed"] == 1
    assert history["tiles"]["checks"]["failed"] == 0  # recovered the same morning


def test_days_without_a_check(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext
) -> None:
    seed(db, world)
    check_job(jobs, "paper", kst("2026-10-07 08:30"))
    day = logged_in.get("/api/day/2026-07-02").json()
    assert day["check"] == {"at": None, "result": "no-run", "band": None}
    assert day["total"] == 0  # no value recorded yet
    assert day["change"] is None


def test_both_markets_closed(db: sqlite3.Connection, api_cfg: Config, world: World) -> None:
    seed(db, world)
    ctx = LedgerContext(db, api_cfg, "paper", kst("2026-12-28 10:00"))
    data = DayData(ctx)
    assert data.calendar_state(date(2026, 12, 25)) == "holiday-both"  # Christmas, both closed
    assert data.calendar_state(date(2026, 12, 24)) == "no-run"
    assert ctx.closed_markets(date(2030, 1, 1)) == []  # outside the calendar table


def test_health_check_reports_a_broken_database(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(conn: sqlite3.Connection) -> int:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(schema, "stored_version", broken)
    response = client.get("/api/healthz")
    assert (response.status_code, response.json()) == (503, {"error": "db"})


def test_unexpected_errors_are_json_with_headers(
    logged_in: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("bug")

    monkeypatch.setattr(home_view, "home", boom)
    response = logged_in.get("/api/home")
    assert (response.status_code, response.json()) == (500, {"error": "internal"})
    assert response.headers["x-frame-options"] == "DENY"


def test_last_seen_is_refreshed_every_ten_minutes(
    logged_in: TestClient, db: sqlite3.Connection, clock: Clock
) -> None:
    [session] = auth_repo.open_sessions(db, clock.now)
    assert session.last_seen_at == kst("2026-07-01 16:10")
    clock.now += timedelta(minutes=5)
    logged_in.get("/api/shell")
    assert auth_repo.get_session(db, session.session_id).last_seen_at == kst("2026-07-01 16:10")  # type: ignore[union-attr]
    clock.now += timedelta(minutes=6)
    logged_in.get("/api/shell")
    assert auth_repo.get_session(db, session.session_id).last_seen_at == kst("2026-07-01 16:21")  # type: ignore[union-attr]


def test_switching_back_to_paper_is_recorded(
    logged_in: TestClient, db: sqlite3.Connection, clock: Clock
) -> None:
    with transaction(db):
        repo.set_setting(db, "mode", "live", kst("2026-07-01 12:00"))
    assert logged_in.post("/api/mode/paper").json() == {"mode": "paper", "cancelFailed": []}
    shell = logged_in.get("/api/shell").json()
    assert (shell["mode"], shell["modeChangedAt"]) == ("paper", "2026-07-01T16:10:00+09:00")


def test_security_edge_cases() -> None:
    secret = b"s" * 32
    assert not verify_pin("123456", "bcrypt$1$2$3$4$5", secret)
    assert read_token("onlyonepart", secret) is None
    payload = "abc.soon"
    sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
    assert read_token(f"{payload}.{sig}", secret) is None  # signed, but the expiry is not a number


def test_formatting_helpers() -> None:
    assert fmt.allocate_pct1([D(0), D(0)]) == [D(0), D(0)]
    assert sum(fmt.allocate_pct1([D(1), D(1), D(1)])) == D(100)
    assert fmt.pp1(D("-0.0004")) == 0.0  # no '-0.0'
    assert fmt.pp1(D("-0.002")) == -0.2
    assert fmt.ret2(D("0.000526")) == 0.05
    assert months_back(date(2026, 5, 31), 3) == date(2026, 2, 28)
    assert months_back(date(2026, 1, 15), 1) == date(2025, 12, 15)
    assert period_start("1y", date(2026, 10, 7), date(2025, 1, 2)) == date(2025, 10, 7)


def test_composition_rows_without_a_rule_holding(
    app: FastAPI, db: sqlite3.Connection, api_cfg: Config
) -> None:
    ctx = LedgerContext(db, api_cfg, "paper", kst("2026-06-30 20:00"))
    comp = home_view.composition(ctx)
    assert comp["groups"][0]["rows"] == []
    assert comp["outsideRules"] is None
