"""The contract gaps the screens found (2026-10-09), on the 예시-값표 worlds: history and day
fields, retried orders, failed check days, ledger-wide drift events, cash countries, the
condition tile's two points, health lists, the off-preview and the web push placeholders."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient

from autotrade.db import repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency
from autotrade.domain.ledger import LedgerState
from autotrade.engine.bootstrap import MODE
from autotrade.jobs.tasks import JobContext, check_job, snapshot_job, stage_job

from ..fakes import US, World
from ..helpers import kst
from .support import Clock
from .test_api_states import move_clock, seed_1007

D = Decimal


def test_the_1007_rebalance_carries_its_waiting_stage_and_targets(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    """예시-값표 §1.4 10/7: sold and converted in the morning, the US buy waits for 22:30."""
    seed_1007(db, world)
    check_job(jobs, "paper", kst("2026-10-07 08:30"))
    stage_job(jobs, "paper", kst("2026-10-07 09:05"))
    stage_job(jobs, "paper", kst("2026-10-07 09:10"))
    snapshot_job(jobs, "paper", kst("2026-10-07 16:00"))
    move_clock(logged_in, clock, "2026-10-07 16:10")
    history = logged_in.get("/api/history").json()
    event = next(e for e in history["months"][0]["events"] if e["kind"] == "in-progress")
    assert event["pending"] == {"side": "buy", "at": "2026-10-07T22:30:00+09:00"}  # '매수 22:30'
    assert event["weightsMini"]["target"] == [50.0, 50.0]  # the target tick ('목표 50')
    day = logged_in.get("/api/day/2026-10-07").json()
    rebalance = next(e for e in day["events"] if e["kind"] == "in-progress")
    fx = next(s for s in rebalance["stages"] if s["kind"] == "fx")["orders"][0]
    assert fx["direction"] == "krw-usd"  # '원 → 달러'
    assert day["check"]["rule"] == {
        "id": "index_half",
        "name": "지수 반반",
        "ai": False,
        "colorIndex": 0,
    }
    assert "failure" not in day["check"]
    plan = logged_in.get("/api/plan").json()
    # The start belongs to the whole ledger, a rebalance to its rule's line.
    assert {"date": "2026-07-01", "kind": "start", "ruleId": None} in plan["drift"]["events"]
    assert {"date": "2026-10-07", "kind": "in-progress", "ruleId": "index_half"} in plan["drift"][
        "events"
    ]
    home = logged_in.get("/api/home").json()
    cash = [r for g in home["composition"]["groups"] for r in g["rows"] if r["kind"] == "cash"]
    countries = {r["cash"]["currency"]: r["cash"]["country"] for r in cash}
    assert countries == {"KRW": "KR", "USD": "US"}  # 묶어 보기 '나라'
    # 예시-값표 §1.3: KOSPI200 ETF +0.2%p at 16:00 (hollow dot), +2.4%p at the 08:30 check.
    rule = logged_in.get("/api/rules/index_half").json()
    assert rule["display"]["condition"]["deviation"] == {"now": 0.2, "atCheck": 2.4}
    assert rule["stale"] == []


def test_a_failed_day_and_a_retry_that_filled(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    seed_1007(db, world)
    # 10/7: no US quote all morning: both checks fail (codes, never sentences).
    world.remove_bar(US, "2026-10-06")
    world.fail_bars.add(US)
    check_job(jobs, "paper", kst("2026-10-07 08:30"))
    check_job(jobs, "paper", kst("2026-10-07 09:30"), retry=True)
    # 10/8: the quote is back; the check plans, the US buy fails at 22:30 and fills on 10/9.
    world.fail_bars.clear()
    world.bar(US, "2026-10-06", close="62.40", open_="62.10")
    world.bar(US, "2026-10-07", close="62.40", open_="62.40")
    world.rate(kst("2026-10-08 08:25"), "1380.6")
    world.rate(kst("2026-10-08 09:10"), "1380.6")
    world.bar("KR:069500", "2026-10-08", close="36250", open_="36380")
    assert check_job(jobs, "paper", kst("2026-10-08 08:30"))["result"] == "rebalance"
    stage_job(jobs, "paper", kst("2026-10-08 09:05"))
    stage_job(jobs, "paper", kst("2026-10-08 09:10"))
    world.fail_bars.add(US)
    stage_job(jobs, "paper", kst("2026-10-08 22:30"))
    world.fail_bars.clear()
    world.bar(US, "2026-10-08", close="62.70", open_="62.50")
    world.bar(US, "2026-10-09", close="62.80", open_="62.60")
    world.rate(kst("2026-10-09 22:25"), "1381.0")
    stage_job(jobs, "paper", kst("2026-10-09 22:30"))
    move_clock(logged_in, clock, "2026-10-07 16:10")
    # Not recovered yet: the reason only ('시세 응답 없음').
    assert logged_in.get("/api/day/2026-10-07").json()["check"]["failure"] == {"reason": "no-quote"}
    move_clock(logged_in, clock, "2026-10-12 08:00")

    failed_day = logged_in.get("/api/day/2026-10-07").json()
    assert failed_day["check"]["result"] == "failed"
    assert failed_day["check"]["failure"] == {"reason": "no-quote", "recoveredOn": "2026-10-08"}
    health = logged_in.get("/api/health").json()
    run_1007 = next(d for d in health["recent14"] if d["date"] == "2026-10-07")["run"]
    assert run_1007["reason"] == "no-quote"
    assert health["devices"] == []  # web push comes in phase 3

    day = logged_in.get("/api/day/2026-10-08").json()
    rebalance = next(e for e in day["events"] if e.get("stages"))
    buy = next(s for s in rebalance["stages"] if s["kind"] == "buy")
    us = next(o for o in buy["orders"] if o["market"] == "US")
    assert us["status"] == "failed"  # the card of the day it failed …
    assert us["failure"] == {"reason": "no-quote", "retryAt": "2026-10-09T22:30:00+09:00"}
    assert us["retried"] == {"at": "2026-10-09T22:30:00+09:00", "status": "filled"}  # '다시 · 체결'
    plan = logged_in.get("/api/plan").json()
    assert not [i for i in plan["schedule"]["items"] if i["kind"] == "retry"]  # nothing waits
    assert logged_in.get("/api/shell").json()["banner"] is None


def test_off_preview_and_web_push_placeholders(
    logged_in: TestClient, db: sqlite3.Connection, world: World, jobs: JobContext, clock: Clock
) -> None:
    seed_1007(db, world)
    check_job(jobs, "paper", kst("2026-10-07 08:30"))
    snapshot_job(jobs, "paper", kst("2026-10-07 16:00"))  # stores the 16:00 rate, 1,382.4
    move_clock(logged_in, clock, "2026-10-07 16:10")
    assert logged_in.get("/api/mode").json()["offPreview"] is None  # live is off
    # Live on (phase 3 turns it on; here the rows are written directly, no broker is touched):
    # the live ledger of 예시-값표 §2.2 with its US buy waiting for 22:30.
    at = kst("2026-10-07 16:00")
    with transaction(db):
        repo.set_setting(db, MODE, "live", at)
        state = LedgerState(cash={Currency.KRW: D("85964"), Currency.USD: D("125.67")})
        repo.save_state(db, "live", state, at)
        plan_id = repo.insert_plan(
            db,
            ledger_id="live",
            rule_id="index_half",
            plan_date=date(2026, 10, 7),
            run_id=None,
            reason="drift",
            basis={},
            weights_before={},
            weights_after_est={},
            created_at=kst("2026-10-07 08:31"),
        )
        stage_id = repo.insert_stage(
            db,
            plan_id=plan_id,
            seq=3,
            kind="buy",
            market="US",
            due_at=kst("2026-10-07 22:30"),
            depends_on=[],
        )
        repo.insert_order(
            db,
            repo.NewOrder(
                idem_key="live:2026-10-07:buy:US",
                ledger_id="live",
                plan_id=plan_id,
                stage_id=stage_id,
                stage="buy",
                market="US",
                instrument_id=US,
                side="buy",
                fx_direction=None,
                currency=Currency.USD,
                qty=2,
                est_price=D("62.40"),
                est_amount=D("124.80"),
                est_fee=D("0.12"),
                est_rate=None,
                est_received=None,
            ),
            kst("2026-10-07 08:31"),
        )
    preview = logged_in.get("/api/mode").json()["offPreview"]
    # '취소될 주문 · 매수·미국·22:30 대기 · S&P 500 ETF 2주 · 약 $124.80'
    [order] = preview["cancel"]
    assert (order["side"], order["market"], order["status"], order["at"]) == (
        "buy",
        "US",
        "pending",
        "2026-10-07T22:30:00+09:00",
    )
    assert (order["instrument"]["name"], order["qty"], order["amountUsd"], order["approx"]) == (
        "S&P 500 ETF",
        2,
        124.8,
        True,
    )
    # '달러 현금 $125.67은 계좌에 남아요' (and the won).
    assert preview["cash"] == [
        {"currency": "KRW", "krw": 85964},
        {"currency": "USD", "usd": 125.67, "krw": 173726},
    ]
    notifications = logged_in.get("/api/account").json()["notifications"]
    assert notifications["available"] is False  # '알림은 준비 중'
    gone = logged_in.delete("/api/account/push")
    assert (gone.status_code, gone.json()) == (
        501,
        {"error": "not-implemented", "detail": {"feature": "push"}},
    )
