"""A long paper record (7/1 to 10/7, 71 weekdays) run day by day through the engine, read
through the API: period chips and period P&L, the drift history, monthly changes, mode returns,
a dividend and a deposit."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from autotrade.db import repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency
from autotrade.domain.ledger import CashFlowKind, apply_cash_flow
from autotrade.jobs.tasks import JobContext, check_job, snapshot_job, stage_job
from autotrade.market.calendar import KRX, NYSE

from ..fakes import KR, US, World
from ..helpers import kst
from .support import PIN, Clock

D = Decimal
START = date(2026, 7, 1)
END = date(2026, 10, 7)


def add_cash_event(
    db: sqlite3.Connection, kind: CashFlowKind, d: date, amount: str, iid: str | None
) -> None:
    at = kst(f"{d.isoformat()} 12:00")
    with transaction(db):
        state = apply_cash_flow(repo.load_state(db, "paper"), kind, D(amount))
        repo.save_state(db, "paper", state, at)
        repo.insert_event(
            db,
            ledger_id="paper",
            kind=kind.value,
            event_date=d,
            occurred_at=at,
            amount=D(amount),
            currency=Currency.KRW,
            payload={"instrument_id": iid} if iid else {},
        )


@pytest.fixture
def long_record(db: sqlite3.Connection, world: World, jobs: JobContext) -> None:
    day = START - timedelta(days=1)
    world.bar(KR, day.isoformat(), close="32000", open_="32000")
    world.bar(US, day.isoformat(), close="66.00", open_="66.00")
    n = 0
    d = START
    while d <= END:
        if d.weekday() < 5:
            n += 1
            kospi = 32000 + 60 * n  # a slow rally: the rule rebalances on the way
            for t in ("08:25", "09:10", "16:00", "22:30"):
                world.rate(kst(f"{d.isoformat()} {t}"), "1390.0")
            if KRX.is_trading_day(d):
                world.bar(KR, d.isoformat(), close=str(kospi), open_=str(kospi - 30))
            if NYSE.is_trading_day(d):
                world.bar(US, d.isoformat(), close="66.00", open_="66.00")
            if d == date(2026, 9, 30):
                add_cash_event(db, CashFlowKind.DIVIDEND, d, "16243", KR)
            if d == date(2026, 10, 6):
                add_cash_event(db, CashFlowKind.DEPOSIT, d, "1000000", None)
            check_job(jobs, "paper", kst(f"{d.isoformat()} 08:30"))
            stage_job(jobs, "paper", kst(f"{d.isoformat()} 09:30"))
            snapshot_job(jobs, "paper", kst(f"{d.isoformat()} 16:00"))
            stage_job(jobs, "paper", kst(f"{d.isoformat()} 23:59"))
        d += timedelta(days=1)


def test_long_record(
    long_record: None, logged_in: TestClient, clock: Clock, db: sqlite3.Connection
) -> None:
    clock.now = kst("2026-10-07 16:10")
    assert logged_in.post("/api/auth/pin", json={"pin": PIN}).status_code == 204

    home = logged_in.get("/api/home").json()
    trend = home["trend"]
    assert trend["periods"] == ["1m", "3m", "1y", "all"]
    assert trend["period"] == "3m"
    assert trend["empty"] is None
    assert trend["series"][0]["date"] == "2026-07-07"  # 3 months back from 10/07
    # '3개월(7/7부터) 기간 손익' = now - value on 7/7 - money in since
    snaps = {s.date: s for s in repo.snapshots_of_ledger(db, "paper")}
    start_value = snaps[date(2026, 7, 7)].total_krw
    amount = D(home["total"]) - start_value - D("1000000")
    assert trend["periodPnl"]["amount"] == int(amount)
    assert trend["periodPnl"]["pct"] == float((amount / start_value * 100).quantize(D("0.01")))
    whole = logged_in.get("/api/home?period=all").json()["trend"]
    assert (whole["period"], whole["periodPnl"], whole["series"][0]["date"]) == (
        "all",
        None,
        "2026-07-01",
    )
    assert logged_in.get("/api/home?period=1m").json()["trend"]["series"][0]["date"] == "2026-09-07"
    assert logged_in.get("/api/home?period=1y").json()["trend"]["series"][0]["date"] == "2026-07-01"
    markers = {m["date"]: m for m in trend["events"]}
    assert markers["2026-09-30"] == {
        "date": "2026-09-30",
        "kind": "dividend",
        "kinds": ["dividend"],
    }
    # Two events on one day (a rebalance at 08:30, the deposit at noon) share one marker that
    # lists both kinds.
    assert markers["2026-10-06"] == {
        "date": "2026-10-06",
        "kind": "rebalance",
        "count": 2,
        "kinds": ["rebalance", "deposit"],
    }

    pnl = home["pnl"]
    contributions = D("11000000")
    assert pnl["amount"] == home["total"] - int(contributions)
    history = logged_in.get("/api/history").json()
    assert sum(m["change"] for m in history["months"]) == pnl["amount"]  # month changes add up
    assert [m["month"] for m in history["months"]] == ["2026-10", "2026-09", "2026-08", "2026-07"]
    assert history["tiles"]["rebalances"]["count"] >= 1
    # 예시-값표 §0: '7/1~10/7 평일 71일 = 확인 71회' (holidays included: the check still runs)
    assert history["tiles"]["checks"] == {"count": 71, "failed": 0}
    kinds = {k["kind"]: k["count"] for k in history["filters"]["kinds"]}
    assert (kinds["dividend"], kinds["deposit"]) == (1, 1)
    september = next(m for m in history["months"] if m["month"] == "2026-09")
    dividend = next(e for e in september["events"] if e["kind"] == "dividend")
    assert (dividend["amount"], dividend["treatment"], dividend["instrument"]["id"]) == (
        16243,
        "income",
        KR,
    )
    day = logged_in.get("/api/day/2026-09-30").json()
    assert {"kind": "dividend", "krw": 16243, "treatment": "income"}.items() <= day["events"][
        0
    ].items()
    deposit_day = logged_in.get("/api/day/2026-10-06").json()
    assert [e["kind"] for e in deposit_day["events"]] == ["rebalance", "deposit"]
    deposit = next(e for e in deposit_day["events"] if e["kind"] == "deposit")
    assert (deposit["krw"], deposit["treatment"]) == (1000000, "pnl-excluded")
    # The day's change does not count the deposit as gain.
    before = snaps[date(2026, 10, 5)] if date(2026, 10, 5) in snaps else snaps[date(2026, 10, 2)]
    assert deposit_day["change"]["amount"] == int(
        snaps[date(2026, 10, 6)].total_krw - before.total_krw - D("1000000")
    )

    # A weekend has no value of its own: Friday's total, no change.
    saturday = logged_in.get("/api/day/2026-10-03").json()
    assert saturday["total"] == logged_in.get("/api/day/2026-10-02").json()["total"]
    assert (saturday["change"], saturday["check"]["result"]) == (None, "weekend")

    breakdown = logged_in.get("/api/home/breakdown?period=3m").json()
    parts = ("deposit", "withdrawal", "market", "dividend", "fees")
    assert sum(breakdown[p] for p in parts) == breakdown["end"] - breakdown["start"]
    assert (breakdown["from"], breakdown["deposit"], breakdown["dividend"]) == (
        "2026-07-07",
        1000000,
        16243,
    )

    plan = logged_in.get("/api/plan").json()
    drift = plan["drift"]
    assert drift["periods"] == ["3m", "1y", "all"]
    assert drift["since"] == "2026-07-07"
    assert drift["lines"][0]["points"][0]["date"] == "2026-07-07"
    assert all(p["value"] is not None and p["value"] >= 0 for p in drift["lines"][0]["points"])
    assert drift["staleFrom"] is None
    assert {e["kind"] for e in drift["events"]} <= {"rebalance", "partial-failed", "in-progress"}
    assert logged_in.get("/api/plan?drift=all").json()["drift"]["since"] == "2026-07-01"

    mode = logged_in.get("/api/mode").json()
    performance = mode["performance"]
    assert performance["ret"] == {"pct": pnl["pct"], "amount": pnl["amount"]}
    assert performance["baselinePct"] == home["baseline"]["pct"]
    assert performance["checks"] == 71

    health = logged_in.get("/api/health").json()
    assert len(health["recent14"]) == 10  # weekdays of the last 14 days
    assert health["summary"]["kind"] in ("ok", "check")
    assert logged_in.get("/api/shell").json()["status"]["kind"] in ("ok", "check")
