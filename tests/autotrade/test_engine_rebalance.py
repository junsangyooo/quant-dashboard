"""Rebalance days of the example table run through the engine (예시-값표 §1.4, §1.3, §3)."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from autotrade.db import repo
from autotrade.domain.cash import Purpose
from autotrade.domain.instruments import Currency
from autotrade.domain.valuation import position_value_krw
from autotrade.domain.weights import drift_report, pct1
from autotrade.engine.common import buy_wait_krw
from autotrade.jobs.tasks import JobContext, check_job, snapshot_job, stage_job
from autotrade.timeutil import KST

from .fakes import KR, US, World
from .helpers import kst, seed_ledger

D = Decimal
TARGETS = {KR: D("0.5"), US: D("0.5")}


def seed_0821(conn: sqlite3.Connection, world: World) -> None:
    # Index-half holdings of the two-rule paper world before 8/21; won cost basis as on 7/1.
    seed_ledger(
        conn,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("34044"),
        usd=D("1.86"),
        positions={
            KR: (125, D("4000600"), D("4000600")),
            US: (44, D("2906.90"), D("4046405")),
        },
    )
    world.bar(KR, "2026-08-20", close="33790", open_="33700")
    world.bar(US, "2026-08-20", close="62.90", open_="62.70")  # see test_planner: not in the table
    world.rate(kst("2026-08-21 08:25"), "1389.6")
    world.rate(kst("2026-08-21 09:10"), "1389.6")
    world.bar(KR, "2026-08-21", close="33850", open_="33800")
    world.bar(US, "2026-08-21", close="63.20", open_="63.00")


def test_0821_rebalance_stage_amounts(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_0821(conn, world)
    report = check_job(ctx, "paper", kst("2026-08-21 08:30"))
    assert report["result"] == "rebalance"
    drift = report["details"]["drift"]
    assert pct1(D(drift["max_drift"])) == D("2.3")  # '2.3%p 벗어남'
    assert pct1(D(drift["over_by"])) == D("0.3")  # '0.3%p 넘음 -> 리밸런싱'
    basis = report["details"]["basis"]
    assert str(basis["closes"][KR]["date"]) == "2026-08-20"  # '기준 한국 8/20 종가'
    assert str(basis["closes"][US]["date"]) == "2026-08-20"  # '미국 8/20 종가(ET)'
    assert D(basis["fx"]["rate"]) == D("1389.6")  # '환율 1,389.6원 08:30'

    for t in ("09:05", "09:10", "22:30"):
        assert stage_job(ctx, "paper", kst(f"2026-08-21 {t}"))["result"] == "done"
    sell, fx, buy = repo.fills_of_ledger(conn, "paper")
    # '매도·한국 09:05 KOSPI200 ETF 5주 · 33,800원 = 169,000원 · 수수료 25원'
    assert (sell.side, sell.qty, sell.price, sell.gross, sell.fee) == (
        "sell",
        5,
        D("33800"),
        D("169000"),
        D("25"),
    )
    assert sell.filled_at.astimezone(KST) == kst("2026-08-21 09:05")
    # '환전 09:10 175,000원 -> $125.93 · 환율 1,389.6원'
    assert (fx.gross, fx.received, fx.krw_rate) == (D("175000"), D("125.93"), D("1389.6"))
    # '매수·미국 S&P 500 ETF 2주 · $63.00 = $126.00 · 수수료 $0.13(181원)'
    assert (buy.side, buy.qty, buy.price, buy.gross, buy.fee, buy.fee_krw) == (
        "buy",
        2,
        D("63.00"),
        D("126.00"),
        D("0.13"),
        D("181"),
    )
    event = repo.event_of_plan(conn, report["plan_id"])
    assert event is not None
    assert event.kind == "rebalance"
    assert event.status == "done"
    assert D(event.payload["fees_krw"]) == D("206")  # '수수료 합계 206원'
    assert pct1(D(event.payload["weights_before"][KR])) == D("52.3")  # '전 52.3 : 47.7'
    assert pct1(D(event.payload["weights_after_est"][KR])) == D("50.2")  # '후 50.2 : 49.8'
    state = repo.load_state(conn, "paper")
    assert state.cash_of(Currency.USD) == D("1.66")  # 1.86 + 125.93 - 126.13
    assert state.qty_of(KR) == 120
    assert state.qty_of(US) == 46


def seed_1007(conn: sqlite3.Connection, world: World) -> None:
    seed_ledger(
        conn,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("47675"),
        usd=D("1.66"),
        positions={
            KR: (120, D("3840576"), D("3840576")),
            US: (46, D("3033.03"), D("4221675")),
        },
    )
    world.bar(KR, "2026-10-06", close="36360", open_="36300")
    world.bar(US, "2026-10-06", close="62.40", open_="62.10")
    world.rate(kst("2026-10-07 08:25"), "1380.6")
    world.rate(kst("2026-10-07 09:10"), "1380.6")
    world.rate(kst("2026-10-07 16:00"), "1382.4")
    world.bar(KR, "2026-10-07", close="36250", open_="36380")


def test_1007_rebalance_and_the_1600_view(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_1007(conn, world)
    report = check_job(ctx, "paper", kst("2026-10-07 08:30"))
    assert report["result"] == "rebalance"
    drift = report["details"]["drift"]
    # §1.3: '10/07 08:30 확인 때 값: KOSPI200 ETF 52.4% -> +2.4%p, 0.4%p 넘음 -> 리밸런싱'
    assert pct1(D(drift["weights"][KR])) == D("52.4")
    assert pct1(D(drift["max_drift"])) == D("2.4")
    assert pct1(D(drift["over_by"])) == D("0.4")

    assert stage_job(ctx, "paper", kst("2026-10-07 09:05"))["result"] == "done"
    assert stage_job(ctx, "paper", kst("2026-10-07 09:10"))["result"] == "done"
    sell, fx = repo.fills_of_ledger(conn, "paper")
    # '매도·한국 09:05 KOSPI200 ETF 5주 · 36,380원 = 181,900원 · 수수료 27원 (모의 체결)'
    assert (sell.qty, sell.price, sell.gross, sell.fee, sell.executor) == (
        5,
        D("36380"),
        D("181900"),
        D("27"),
        "paper",
    )
    # '환전 09:10 173,000원 -> $125.30 · 환율 1,380.6원 (모의 체결)'
    assert (fx.gross, fx.received, fx.krw_rate) == (D("173000"), D("125.30"), D("1380.6"))
    pending = repo.pending_orders(conn, "paper")
    assert len(pending) == 1
    us_buy = pending[0]
    # '매수·미국 22:30 대기 S&P 500 ETF 2주 · 약 $124.80 (+수수료 $0.12)'
    assert (us_buy.qty, us_buy.est_amount, us_buy.est_fee) == (2, D("124.80"), D("0.12"))
    us_stage = repo.get_stage(conn, us_buy.stage_id)
    assert us_stage.due_at.astimezone(KST) == kst("2026-10-07 22:30")

    snap = snapshot_job(ctx, "paper", kst("2026-10-07 16:00"))
    assert snap["result"] == "ok"
    assert str(snap["us_close_date"]) == "2026-10-06"  # '미국 10/06 종가(ET)'
    parts = repo.cash_parts(conn, "paper")
    by_purpose = {(p.currency, p.purpose): p.amount for p in parts}
    assert by_purpose[(Currency.USD, Purpose.BUY_WAIT)] == D("126.96")  # §1.1 '$126.96'
    assert by_purpose[(Currency.KRW, Purpose.SUB_SHARE)] == D("56548")  # §1.1 '56,548'
    rate = D("1382.4")
    values = {
        KR: position_value_krw(115, D("36250"), Currency.KRW, rate),
        US: position_value_krw(46, D("62.40"), Currency.USD, rate),
    }
    assert values == {KR: D("4168750"), US: D("3968041")}
    waiting = buy_wait_krw(parts, rate)
    assert waiting == {US: D("175510")}
    now = drift_report(values, waiting, TARGETS, D("0.02"))
    # §1.3 '지금(16:00)': 50.2% / 49.8% (매수 대기 포함), 리밸런싱까지 1.8%p
    assert (pct1(now.weights[KR]), pct1(now.weights[US])) == (D("50.2"), D("49.8"))
    assert pct1(now.to_threshold) == D("1.8")
    assert snap["total_krw"] == D("4168750") + D("3968041") + D("175510") + D("56548")


def test_partial_failure_is_retried_next_day_at_the_same_time(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    # §3 '일부 실패': the 10/07 22:30 US buy has no price -> again 10/08 22:30.
    seed_1007(conn, world)
    check_job(ctx, "paper", kst("2026-10-07 08:30"))
    stage_job(ctx, "paper", kst("2026-10-07 09:05"))
    stage_job(ctx, "paper", kst("2026-10-07 09:10"))
    world.fail_bars.add(US)
    failed = stage_job(ctx, "paper", kst("2026-10-07 22:30"))
    assert failed["result"] == "failed"
    [order] = [o for o in repo.orders_of_ledger(conn, "paper") if o.status == "failed"]
    assert order.failure_reason == "no-quote"
    assert order.retry_at is not None
    assert order.retry_at.astimezone(KST) == kst("2026-10-08 22:30")  # '10/08 22:30 다시 시도'
    assert not order.manual
    plan = repo.get_plan(conn, order.plan_id)
    assert plan.status == "partial-failed"
    event = repo.event_of_plan(conn, plan.plan_id)
    assert event is not None
    assert event.status == "partial-failed"
    # The dollars still wait for the retry.
    parts = repo.cash_parts(conn, "paper")
    assert [p.amount for p in parts if p.purpose is Purpose.BUY_WAIT] == [D("126.96")]

    # Next morning: the source is back; the check sees the open plan and sends nothing new.
    world.fail_bars.clear()
    world.bar(KR, "2026-10-07", close="36250", open_="36380")
    world.bar(US, "2026-10-07", close="62.40", open_="62.30")
    world.rate(kst("2026-10-08 08:25"), "1382.4")
    morning = check_job(ctx, "paper", kst("2026-10-08 08:30"))
    assert morning["result"] == "partial-failed"
    assert len(repo.pending_orders(conn, "paper")) == 1

    world.bar(US, "2026-10-08", close="62.70", open_="62.50")
    retried = stage_job(ctx, "paper", kst("2026-10-08 22:30"))
    assert retried["result"] == "done"
    last = repo.fills_of_ledger(conn, "paper")[-1]
    assert (last.qty, last.price, last.gross, last.fee) == (2, D("62.50"), D("125.00"), D("0.13"))
    assert last.filled_at.astimezone(KST) == kst("2026-10-08 22:30")
    assert repo.get_plan(conn, plan.plan_id).status == "done"
    event = repo.event_of_plan(conn, plan.plan_id)
    assert event is not None
    assert event.status == "done"
    assert event.payload["retried"] is True


def test_second_failure_becomes_a_manual_action(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_1007(conn, world)
    check_job(ctx, "paper", kst("2026-10-07 08:30"))
    stage_job(ctx, "paper", kst("2026-10-07 09:05"))
    stage_job(ctx, "paper", kst("2026-10-07 09:10"))
    world.fail_bars.add(US)
    stage_job(ctx, "paper", kst("2026-10-07 22:30"))
    again = stage_job(ctx, "paper", kst("2026-10-08 22:30"))
    assert again["result"] == "failed"
    manual = [o for o in repo.orders_of_ledger(conn, "paper") if o.manual]
    assert len(manual) == 1
    assert manual[0].attempt == 2
    plan = repo.get_plan(conn, manual[0].plan_id)
    assert plan.status == "todo"  # '직접 할 일'
    # A rule with a manual action open makes no new plans.
    world.fail_bars.clear()
    world.bar(KR, "2026-10-08", close="38000", open_="37000")
    world.bar(US, "2026-10-08", close="60.00", open_="61.00")
    world.rate(kst("2026-10-09 08:25"), "1382.4")
    blocked = check_job(ctx, "paper", kst("2026-10-09 08:30"))
    assert (blocked["result"], blocked["details"]["open_plan_status"]) == ("partial-failed", "todo")
    assert repo.pending_orders(conn, "paper") == []


def test_a_stage_waits_for_its_open_and_fills_at_the_stage_time(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_1007(conn, world)
    world.remove_bar(KR, "2026-10-07")  # the open is not published at 09:05
    check_job(ctx, "paper", kst("2026-10-07 08:30"))
    waiting = stage_job(ctx, "paper", kst("2026-10-07 09:05"))
    assert waiting["result"] == "waiting"
    assert repo.fills_of_ledger(conn, "paper") == []

    world.bar(KR, "2026-10-07", close="36250", open_="36380")
    later = stage_job(ctx, "paper", kst("2026-10-07 09:30"))
    assert later["result"] == "done"
    sell, fx = repo.fills_of_ledger(conn, "paper")
    assert sell.filled_at.astimezone(KST) == kst("2026-10-07 09:05")  # the stage time, not 09:30
    assert fx.filled_at.astimezone(KST) == kst("2026-10-07 09:10")
    assert fx.krw_rate == D("1380.6")  # the 09:10 rate


def test_a_missing_open_after_the_close_fails(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_1007(conn, world)
    world.remove_bar(KR, "2026-10-07")
    check_job(ctx, "paper", kst("2026-10-07 08:30"))
    late = stage_job(ctx, "paper", kst("2026-10-07 16:30"))
    assert late["result"] == "failed"
    [order] = [o for o in repo.orders_of_ledger(conn, "paper") if o.status == "failed"]
    assert order.retry_at is not None
    assert order.retry_at.astimezone(KST) == kst("2026-10-08 09:05")
