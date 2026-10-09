"""What the screens show of the unattended jobs: dividends (in won) and resolved manual actions."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from autotrade.db import repo
from autotrade.domain.money import usd_in_krw
from autotrade.jobs.tasks import JobContext, check_job, dividend_job, resolve_job, stage_job

from ..fakes import KR, US, World
from ..helpers import kst, seed_ledger
from ..test_engine_rebalance import seed_1007
from .support import PIN, Clock

D = Decimal


def relogin(client: TestClient, clock: Clock, when: str) -> None:
    clock.now = kst(when)
    assert client.post("/api/auth/pin", json={"pin": PIN}).status_code == 204


def test_the_0930_dividend_on_the_screens(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    seed_ledger(
        db,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("47675"),
        usd=D("1.66"),
        positions={KR: (120, D("3840576"), D("3840576")), US: (46, D("3033.03"), D("4221675"))},
    )
    world.dividend(KR, "2026-09-23", "160")  # paid 9/30
    world.dividend(US, "2026-09-11", "0.239", pay_date="2026-09-15")
    world.rate(kst("2026-09-15 07:55"), "1385.0")
    assert dividend_job(jobs, "paper", kst("2026-09-15 08:00"))["result"] == "booked"
    assert dividend_job(jobs, "paper", kst("2026-09-30 08:00"))["result"] == "booked"
    relogin(logged_in, clock, "2026-10-01 09:00")

    history = logged_in.get("/api/history").json()
    september = next(m for m in history["months"] if m["month"] == "2026-09")
    rows = [e for e in september["events"] if e["kind"] == "dividend"]
    kr_row, us_row = rows  # newest first
    # 예시-값표 §1.4: '9/30 배당 16,243원 (세후, 120주 × 160원 − 세금) · 지수 반반 (KOSPI200 ETF)'
    assert (kr_row["date"], kr_row["amount"], kr_row["treatment"]) == (
        "2026-09-30",
        16243,
        "income",
    )
    assert (kr_row["instrument"]["id"], kr_row["rule"]["id"]) == (KR, "index_half")
    # The dollar dividend shows in won: 46 x $0.239 -> $9.34 after 15% -> x 1,385.0.
    assert us_row["amount"] == int(usd_in_krw(D("9.34"), D("1385.0")))
    assert history["filters"]["rules"][0]["count"] == 2  # the rule's chip counts its dividends
    kinds = {k["kind"]: k["count"] for k in history["filters"]["kinds"]}
    assert kinds["dividend"] == 2

    day = logged_in.get("/api/day/2026-09-30").json()
    [event] = day["events"]
    assert {"kind": "dividend", "krw": 16243, "treatment": "income"}.items() <= event.items()

    breakdown = logged_in.get("/api/home/breakdown?period=all").json()
    assert breakdown["dividend"] == 16243 + us_row["amount"]


def test_a_resolved_manual_action_on_the_screens(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    seed_1007(db, world)
    check_job(jobs, "paper", kst("2026-10-07 08:30"))
    stage_job(jobs, "paper", kst("2026-10-07 09:05"))
    stage_job(jobs, "paper", kst("2026-10-07 09:10"))
    world.fail_bars.add(US)
    stage_job(jobs, "paper", kst("2026-10-07 22:30"))
    stage_job(jobs, "paper", kst("2026-10-08 22:30"))
    relogin(logged_in, clock, "2026-10-09 09:00")
    health = logged_in.get("/api/health").json()
    [todo] = [t for t in health["todos"] if t["kind"] == "order-failed"]
    assert logged_in.get("/api/shell").json()["status"]["kind"] == "todo"

    out = resolve_job(jobs, "paper", todo["id"], kst("2026-10-09 09:30"), note="bought in Toss")
    assert out["result"] == "resolved"  # the web's todo id is the CLI's
    relogin(logged_in, clock, "2026-10-09 10:00")
    assert [
        t for t in logged_in.get("/api/health").json()["todos"] if t["kind"] == "order-failed"
    ] == []
    assert logged_in.get("/api/shell").json()["status"]["kind"] != "todo"
    history = logged_in.get("/api/history").json()
    october = next(m for m in history["months"] if m["month"] == "2026-10")
    [row] = [e for e in october["events"] if e["date"] == "2026-10-07"]
    assert (row["kind"], row["resolvedOn"]) == ("partial-failed", "2026-10-09")
    # The resolution itself is a record, not a screen event.
    assert all(e["kind"] != "todo-resolved" for m in history["months"] for e in m["events"])
    assert all(e["kind"] != "todo-resolved" for e in history["trend"]["events"])
    assert repo.events_of_ledger(db, "paper", ["todo-resolved"])
    calendar = {c["date"]: c["state"] for c in history["calendar"]}
    assert calendar["2026-10-07"] == "partial-failed"


def test_a_resolved_check_failure_leaves_the_header(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    world.fail_bars.update({KR, US})
    world.fail_fx = True
    check_job(jobs, "paper", kst("2026-07-01 08:30"))
    check_job(jobs, "paper", kst("2026-07-01 09:30"), retry=True)
    relogin(logged_in, clock, "2026-07-01 10:00")
    assert logged_in.get("/api/shell").json()["status"]["kind"] == "todo"
    resolve_job(jobs, "paper", "check-failed:2026-07-01", kst("2026-07-01 10:05"))
    relogin(logged_in, clock, "2026-07-01 10:10")
    shell = logged_in.get("/api/shell").json()
    assert shell["status"]["kind"] != "todo"
    assert shell["banner"] is None
    history = logged_in.get("/api/history").json()
    [row] = [e for m in history["months"] for e in m["events"] if e["kind"] == "check-failed"]
    assert row["resolvedOn"] == "2026-07-01"
