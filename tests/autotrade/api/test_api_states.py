"""The screens' other states, each built through the engine and read through the API."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from autotrade.db import repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency
from autotrade.jobs.tasks import JobContext, check_job, snapshot_job, stage_job

from ..fakes import KR, US, World
from ..helpers import kst, seed_ledger
from .support import PIN, Clock

D = Decimal


def move_clock(client: TestClient, clock: Clock, when: str) -> None:
    """Jump the clock and log in again (a session lasts 30 days)."""
    clock.now = kst(when)
    assert client.post("/api/auth/pin", json={"pin": PIN}).status_code == 204


def seed_1007(db: sqlite3.Connection, world: World) -> None:
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
    world.rate(kst("2026-10-07 16:00"), "1382.4")
    world.bar(KR, "2026-10-07", close="36250", open_="36380")


def test_before_the_first_check(logged_in: TestClient, clock: Clock) -> None:
    move_clock(logged_in, clock, "2026-06-30 20:00")
    home = logged_in.get("/api/home").json()
    assert home["total"] == 10000000  # '모의투자 시작 금액'
    assert home["pnl"] is None
    assert home["baseline"] is None
    assert home["planCard"] is None
    assert home["trend"]["empty"] == "before-first-check"
    assert home["planChip"] == {
        "ruleId": "index_half",
        "status": "scheduled",
        "next": {
            "kind": "first-check",
            "at": "2026-07-01T08:30:00+09:00",
        },  # '첫 확인 7/1(수) 08:30'
    }
    rule_group, cash_group = home["composition"]["groups"]
    assert (rule_group["pct"], rule_group["rows"]) == (0.0, [])
    [cash] = cash_group["rows"]
    assert (cash["krw"], cash["pct"], cash["chip"]) == (10000000, 100.0, {"kind": "first-buy"})
    shell = logged_in.get("/api/shell").json()
    assert shell["status"] == {"kind": "before-first", "firstCheckAt": "2026-07-01T08:30:00+09:00"}
    assert shell["banner"] is None
    health = logged_in.get("/api/health").json()
    assert health["summary"]["kind"] == "before-first"
    assert health["summary"]["firstCheckAt"] == "2026-07-01T08:30:00+09:00"
    assert health["lastRun"] is None
    plan = logged_in.get("/api/plan").json()
    assert plan["schedule"]["items"][0] == {
        "kind": "first-check",
        "at": "2026-07-01T08:30:00+09:00",
    }
    assert [row["weight"] for row in plan["rules"][0]["rows"]] == [None, None]
    assert plan["rules"][0]["gauge"]["needle"] is None
    assert logged_in.get("/api/mode").json()["performance"]["checks"] == 0


def test_quote_wait(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    # §3 '시세 대기': US closes stuck at 10/02 at the 10/07 08:30 check.
    seed_1007(db, world)
    world.remove_bar(US, "2026-10-06")
    world.bar(US, "2026-10-02", close="62.10")
    assert check_job(jobs, "paper", kst("2026-10-07 08:30"))["result"] == "quote-wait"
    move_clock(logged_in, clock, "2026-10-07 08:40")
    home = logged_in.get("/api/home").json()
    assert home["stale"] == ["hero", "plan", "composition"]
    assert home["planChip"]["status"] == "quote-wait"
    assert home["planChip"]["next"] == {
        "kind": "quote-wait",
        "market": "US",
        "basisDate": "2026-10-02",
    }
    assert home["planCard"]["gauge"]["needle"] is None
    card = logged_in.get("/api/plan").json()["rules"][0]
    assert [row["weight"] for row in card["rows"]] == [None, None]
    assert (card["basisLine"]["staleMarket"], card["basisLine"]["staleBasisDate"]) == (
        "US",
        "2026-10-02",
    )
    shell = logged_in.get("/api/shell").json()
    assert shell["status"] == {"kind": "check", "count": 1}  # '점검 1'
    assert shell["banner"] == {
        "kind": "stale",
        "market": "US",
        "basisDate": "2026-10-02",
        "tradingDays": 2,
        "link": "health",
    }  # '미국 시세 10/02 기준 · 2거래일째 갱신 없음'
    health = logged_in.get("/api/health").json()
    us = next(s for s in health["sources"] if s["id"] == "us-quotes")
    assert (us["state"], us["basis"]) == ("stale", "2026-10-02")
    [todo] = health["todos"]
    assert todo["kind"] == "stale"
    assert todo["facts"] == {"market": "US", "basisDate": "2026-10-02", "tradingDays": 2}
    assert todo["action"] == {"kind": "auto-retry", "at": "2026-10-08T08:30:00+09:00"}
    assert health["summary"]["kind"] == "check"
    assert health["summary"]["staleCount"] == 1
    day = logged_in.get("/api/day/2026-10-07").json()
    assert day["check"]["result"] == "quote-wait"


def test_partial_failure_then_manual_action(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    seed_1007(db, world)
    check_job(jobs, "paper", kst("2026-10-07 08:30"))
    stage_job(jobs, "paper", kst("2026-10-07 09:05"))
    stage_job(jobs, "paper", kst("2026-10-07 09:10"))
    world.fail_bars.add(US)
    assert stage_job(jobs, "paper", kst("2026-10-07 22:30"))["result"] == "failed"
    move_clock(logged_in, clock, "2026-10-08 08:40")
    shell = logged_in.get("/api/shell").json()
    assert shell["status"] == {"kind": "check", "count": 1}
    assert shell["banner"] == {  # '10/07 미국 매수 실패 · 10/08 22:30 다시 시도 · 계획 보기 ›'
        "kind": "partial-retry",
        "date": "2026-10-07",
        "market": "US",
        "side": "buy",
        "retryAt": "2026-10-08T22:30:00+09:00",
        "link": "plan",
    }
    home = logged_in.get("/api/home").json()
    assert home["planChip"]["status"] == "partial-failed"
    assert home["planChip"]["next"] == {
        "kind": "retry",
        "at": "2026-10-08T22:30:00+09:00",
        "market": "US",
        "side": "buy",
    }
    buy = home["planCard"]["stages"][-1]
    assert buy["status"] == "failed"
    assert buy["orders"][0]["failure"] == {
        "reason": "no-quote",
        "retryAt": "2026-10-08T22:30:00+09:00",
    }
    assert [s["status"] for s in home["planCard"]["stages"]] == ["done", "done", "failed"]
    plan = logged_in.get("/api/plan").json()
    assert {
        "kind": "retry",
        "at": "2026-10-08T22:30:00+09:00",
        "market": "US",
        "side": "buy",
    } in plan["schedule"]["items"]

    # The retry fails too: '직접 할 일'.
    assert stage_job(jobs, "paper", kst("2026-10-08 22:30"))["result"] == "failed"
    move_clock(logged_in, clock, "2026-10-09 08:40")
    shell = logged_in.get("/api/shell").json()
    assert shell["status"] == {"kind": "todo", "count": 1}
    assert shell["banner"] == {
        "kind": "partial-todo",
        "date": "2026-10-07",
        "market": "US",
        "side": "buy",
        "reason": "retry-failed",
        "link": "health",
    }
    health = logged_in.get("/api/health").json()
    [todo] = health["todos"]
    assert (todo["kind"], todo["action"], todo["facts"]["market"]) == (
        "order-failed",
        {"kind": "manual"},
        "US",
    )
    home = logged_in.get("/api/home").json()
    assert home["planChip"]["next"] == {"kind": "todo", "market": "US", "side": "buy"}
    history = logged_in.get("/api/history").json()
    rebalance = history["months"][0]["events"][0]
    assert rebalance["kind"] == "partial-failed"
    assert rebalance["retry"] == {"date": "2026-10-08", "filled": False}


def test_failed_check(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    seed_1007(db, world)
    world.remove_bar(US, "2026-10-06")
    world.fail_bars.add(US)
    assert check_job(jobs, "paper", kst("2026-10-07 08:30"))["result"] == "failed"
    move_clock(logged_in, clock, "2026-10-07 09:00")
    shell = logged_in.get("/api/shell").json()
    assert shell["status"] == {"kind": "check-failed", "at": "2026-10-07T08:30:00+09:00"}
    assert shell["banner"] == {  # '10/07 08:30 확인 실패 · 09:30 자동 재시도'
        "kind": "check-failed",
        "at": "2026-10-07T08:30:00+09:00",
        "retryAt": "2026-10-07T09:30:00+09:00",
        "link": "health",
    }
    health = logged_in.get("/api/health").json()
    assert health["summary"]["kind"] == "check-failed"
    assert health["summary"]["retryAt"] == "2026-10-07T09:30:00+09:00"
    assert health["lastRun"]["reason"] == "no-quote"
    failed = next(t for t in health["todos"] if t["kind"] == "check-failed")
    assert failed["action"] == {"kind": "auto-retry", "at": "2026-10-07T09:30:00+09:00"}
    assert failed["effect"] == "no-order-sent"
    # Second failure at 09:30: no retry left.
    check_job(jobs, "paper", kst("2026-10-07 09:30"), retry=True)
    move_clock(logged_in, clock, "2026-10-07 09:40")
    shell = logged_in.get("/api/shell").json()
    assert shell["status"] == {"kind": "todo", "count": 1}
    assert shell["banner"]["retryAt"] is None
    day = logged_in.get("/api/day/2026-10-07").json()
    assert day["check"]["result"] == "failed"
    history = logged_in.get("/api/history").json()
    assert history["tiles"]["checks"]["failed"] == 1
    state = {c["date"]: c["state"] for c in history["calendar"]}["2026-10-07"]
    assert state == "failed"


def test_a_month_of_history(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    # Start 7/1, a KOSPI rally, a rebalance on 7/6 (US closed 7/3).
    world.bar(KR, "2026-06-30", close="32000", open_="31900")
    world.bar(US, "2026-06-30", close="66.00", open_="65.80")
    for t, r in (("07-01 08:25", "1392.0"), ("07-01 09:10", "1392.0"), ("07-01 16:00", "1391.5")):
        world.rate(kst(f"2026-{t}"), r)
    world.bar(KR, "2026-07-01", close="32050", open_="32000")
    world.bar(US, "2026-07-01", close="66.20", open_="66.00")
    check_job(jobs, "paper", kst("2026-07-01 08:30"))
    for t in ("09:05", "09:10"):
        stage_job(jobs, "paper", kst(f"2026-07-01 {t}"))
    snapshot_job(jobs, "paper", kst("2026-07-01 16:00"))
    stage_job(jobs, "paper", kst("2026-07-01 22:30"))
    world.rate(kst("2026-07-02 08:25"), "1391.0")
    check_job(jobs, "paper", kst("2026-07-02 08:30"))
    world.bar(KR, "2026-07-02", close="33000", open_="32500")
    world.bar(US, "2026-07-02", close="66.00", open_="66.10")
    world.rate(kst("2026-07-02 16:00"), "1390.0")
    snapshot_job(jobs, "paper", kst("2026-07-02 16:00"))
    world.rate(kst("2026-07-03 08:25"), "1390.0")
    check_job(jobs, "paper", kst("2026-07-03 08:30"))
    world.bar(KR, "2026-07-03", close="34600", open_="34000")
    world.rate(kst("2026-07-03 16:00"), "1390.0")
    snapshot_job(jobs, "paper", kst("2026-07-03 16:00"))
    world.rate(kst("2026-07-06 08:25"), "1390.0")
    world.rate(kst("2026-07-06 09:10"), "1390.0")
    world.bar(KR, "2026-07-06", close="34800", open_="34700")
    assert check_job(jobs, "paper", kst("2026-07-06 08:30"))["result"] == "rebalance"
    world.bar(US, "2026-07-06", close="65.50", open_="65.80")
    for t in ("09:05", "09:10"):
        stage_job(jobs, "paper", kst(f"2026-07-06 {t}"))
    world.rate(kst("2026-07-06 16:00"), "1390.0")
    snapshot_job(jobs, "paper", kst("2026-07-06 16:00"))
    stage_job(jobs, "paper", kst("2026-07-06 22:30"))
    move_clock(logged_in, clock, "2026-07-07 08:00")

    history = logged_in.get("/api/history").json()
    home = logged_in.get("/api/home").json()
    # The month changes add up to the P&L.
    assert sum(m["change"] for m in history["months"]) == home["pnl"]["amount"]
    assert history["trend"]["pnl"] == home["pnl"]
    assert history["tiles"]["rebalances"] == {"count": 1, "partialFailed": 0, "inProgress": 0}
    fills = repo.fills_of_ledger(db, "paper")
    assert history["tiles"]["fees"]["krw"] == int(sum(f.fee_krw for f in fills))
    assert history["tiles"]["checks"] == {"count": 4, "failed": 0}
    states = {c["date"]: c["state"] for c in history["calendar"]}
    assert (
        states["2026-07-01"],
        states["2026-07-02"],
        states["2026-07-03"],
        states["2026-07-06"],
    ) == (
        "rebalance",
        "normal",
        "holiday-one",  # US closed
        "rebalance",
    )
    kinds = {k["kind"]: k["count"] for k in history["filters"]["kinds"]}
    assert kinds == {"rebalance": 1, "deposit": 0, "withdrawal": 0, "dividend": 0, "failed": 0}
    assert history["filters"]["total"] == 2
    [july] = history["months"]
    assert [e["kind"] for e in july["events"]] == ["rebalance", "start"]  # newest first
    rebalance = july["events"][0]
    assert rebalance["stagesMini"] == ["done", "done", "done"]
    assert rebalance["fill"] == "paper"
    assert rebalance["deviation"] > 2.0
    assert rebalance["weightsMini"]["before"][0] > 52.0
    assert 49.0 <= rebalance["weightsMini"]["after"][0] <= 51.0

    day = logged_in.get("/api/day/2026-07-06").json()
    assert (day["prev"], day["next"]) == ("2026-07-01", None)
    [event] = day["events"]
    assert event["kind"] == "rebalance"
    assert [s["kind"] for s in event["stages"]] == ["sell", "fx", "buy"]
    assert event["weights"]["target"] == [50.0, 50.0]
    assert event["weights"]["threshold"] == 2.0
    assert event["feesKrw"] > 0
    check = day["check"]
    assert check["result"] == "rebalance"
    assert check["band"]["threshold"] == 2.0
    assert check["band"]["before"] > 2.0
    assert check["over"] == round(check["band"]["before"] - 2.0, 1)
    assert check["instrument"]["id"] == KR
    assert day["change"] is not None
    weekend = logged_in.get("/api/day/2026-07-04").json()
    assert weekend["check"] == {"at": None, "result": "weekend", "band": None}
    holiday = logged_in.get("/api/day/2026-07-03").json()
    assert holiday["check"]["holidayMarkets"] == ["US"]

    breakdown = logged_in.get("/api/home/breakdown?period=all").json()
    parts = ("deposit", "withdrawal", "market", "dividend", "fees")
    assert sum(breakdown[p] for p in parts) == breakdown["end"] - breakdown["start"]
    assert breakdown["start"] == 10000000
    assert breakdown["fees"] == -history["tiles"]["fees"]["krw"]
    assert logged_in.get("/api/plan").json()["drift"]["empty"] is None
    mode = logged_in.get("/api/mode").json()
    assert mode["performance"]["checks"] == 4
    assert mode["performance"]["rebalances"] == 1
    assert mode["performance"]["paperFills"] == len(fills)
    assert mode["performance"]["ret"] is None  # under 30 trading days


def test_withdraw_wait(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    seed_1007(db, world)
    with transaction(db):
        repo.add_withdraw_wait(
            db, "paper", Currency.KRW, D("40000"), date(2026, 10, 12), kst("2026-10-02 10:00")
        )
    assert check_job(jobs, "paper", kst("2026-10-07 08:30"))["result"] == "withdraw-wait"
    move_clock(logged_in, clock, "2026-10-07 08:40")
    home = logged_in.get("/api/home").json()
    assert home["planChip"]["status"] == "withdraw-wait"
    assert home["planChip"]["next"] == {"kind": "withdraw-wait", "until": "2026-10-12"}
    assert home["composition"]["pendingBar"] == {"withdraw": {"krw": 40000, "until": "2026-10-12"}}
    chips = [r.get("chip") for g in home["composition"]["groups"] for r in g["rows"]]
    assert {"kind": "withdraw-wait", "until": "2026-10-12"} in chips
    plan = logged_in.get("/api/plan").json()
    assert {"kind": "withdraw-wait", "krw": 40000, "until": "2026-10-12"} in plan["schedule"][
        "items"
    ]
    assert plan["rules"][0]["basisLine"]["withdrawExcluded"] is True
    assert logged_in.get("/api/day/2026-10-07").json()["check"]["result"] == "withdraw-wait"


def test_parameters(logged_in: TestClient) -> None:
    live = logged_in.get("/api/home?ledger=live")
    assert (live.status_code, live.json()) == (
        404,
        {"error": "no-ledger", "detail": {"ledger": "live"}},
    )
    assert logged_in.get("/api/home?ledger=bogus").status_code == 400
    assert logged_in.get("/api/home?period=5y").json()["error"] == "bad-request"
    assert logged_in.get("/api/plan?drift=1m").status_code == 400
    assert logged_in.get("/api/day/2026-13-01").status_code == 400
    assert logged_in.get("/api/history?year=1999").status_code == 400
    assert logged_in.get("/api/history?year=2026").json()["year"] == 2026
