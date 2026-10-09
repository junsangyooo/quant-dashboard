"""The first day end to end (예시-값표 §4): check -> stages -> snapshot -> US buy, then rebuild."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from autotrade.db import repo
from autotrade.domain.cash import Purpose
from autotrade.domain.instruments import Currency
from autotrade.domain.weights import drift_report, pct1
from autotrade.engine.common import buy_wait_krw
from autotrade.engine.rebuild import verify_ledger
from autotrade.jobs.tasks import JobContext, check_job, snapshot_job, stage_job, status_job
from autotrade.timeutil import KST

from .fakes import KR, US, World
from .helpers import kst

D = Decimal


def first_day_world(world: World) -> None:
    world.bar(KR, "2026-06-30", close="32000", open_="31900")
    world.bar(US, "2026-06-30", close="66.00", open_="65.80")
    world.rate(kst("2026-07-01 08:25"), "1392.0")
    world.rate(kst("2026-07-01 09:10"), "1392.0")
    world.rate(kst("2026-07-01 16:00"), "1391.5")
    world.bar(KR, "2026-07-01", close="32050", open_="32000")
    world.bar(US, "2026-07-01", close="66.20", open_="66.00")


def test_first_day(ctx: JobContext, conn: sqlite3.Connection, world: World) -> None:
    first_day_world(world)

    report = check_job(ctx, "paper", kst("2026-07-01 08:30"))
    assert report["result"] == "rebalance"
    plan = repo.get_plan(conn, report["plan_id"])
    assert plan.reason == "start"
    start = repo.start_event(conn, "paper")
    assert start is not None
    assert (start.amount, start.status, start.plan_id) == (
        D("10000000"),
        "in-progress",
        plan.plan_id,
    )

    stages = repo.stages_of(conn, plan.plan_id)
    assert [(s.kind, s.market, s.due_at.astimezone(KST).strftime("%H:%M")) for s in stages] == [
        ("fx", "FX", "09:10"),
        ("buy", "KR", "09:05"),
        ("buy", "US", "22:30"),
    ]
    orders = {(o.side, o.market): o for o in repo.orders_of_ledger(conn, "paper")}
    kr_buy, fx, us_buy = orders[("buy", "KR")], orders[("fx", "FX")], orders[("buy", "US")]
    assert (kr_buy.qty, kr_buy.est_amount, kr_buy.est_fee) == (156, D("4992000"), D("748"))
    assert (fx.est_amount, fx.est_rate, fx.est_received) == (
        D("4967000"),
        D("1392.0"),
        D("3568.24"),
    )
    assert (us_buy.qty, us_buy.est_amount) == (54, D("3564.00"))  # '약 $3,564.00 22:30 대기'

    assert stage_job(ctx, "paper", kst("2026-07-01 09:00"))["result"] == "nothing-due"
    assert stage_job(ctx, "paper", kst("2026-07-01 09:05"))["result"] == "done"
    assert stage_job(ctx, "paper", kst("2026-07-01 09:10"))["result"] == "done"
    fills = repo.fills_of_ledger(conn, "paper")
    assert [(f.kind, f.qty, f.price, f.gross, f.fee) for f in fills] == [
        ("trade", 156, D("32000"), D("4992000"), D("748")),  # '156주 · 4,992,000원 09:05 체결'
        ("fx", None, None, D("4967000"), D("0")),
    ]
    assert fills[1].received == D("3568.24")  # '4,967,000원 -> $3,568.24 · 1,392.0원'
    assert fills[1].krw_rate == D("1392.0")

    snap = snapshot_job(ctx, "paper", kst("2026-07-01 16:00"))
    assert snap["result"] == "ok"
    assert snap["total_krw"] == D("10005258")  # §4 합
    assert snap["pnl_krw"] == D("5258")  # '+5,258원 · +0.05%'
    assert snap["baseline_krw"] == D("10005258")  # 첫날은 같은 매수
    assert str(snap["kr_close_date"]) == "2026-07-01"
    assert str(snap["us_close_date"]) == "2026-06-30"
    parts = repo.cash_parts(conn, "paper")
    assert {(p.currency, p.purpose, p.instrument_id): p.amount for p in parts} == {
        (Currency.USD, Purpose.BUY_WAIT, US): D("3568.24"),  # '달러 현금 · 매수 대기 $3,568.24'
        (Currency.KRW, Purpose.SUB_SHARE, None): D("40252"),  # '원화 현금 · 1주 미만 대기 40,252'
    }
    report_1600 = drift_report(
        {KR: D("4999800"), US: D("0")},
        buy_wait_krw(parts, D("1391.5")),
        {KR: D("0.5"), US: D("0.5")},
        D("0.02"),
    )
    assert (pct1(report_1600.weights[KR]), pct1(report_1600.weights[US])) == (D("50.2"), D("49.8"))

    assert stage_job(ctx, "paper", kst("2026-07-01 22:30"))["result"] == "done"
    us_fill = repo.fills_of_ledger(conn, "paper")[-1]
    assert (us_fill.qty, us_fill.price, us_fill.gross, us_fill.fee) == (
        54,
        D("66.00"),
        D("3564.00"),
        D("3.56"),
    )
    assert us_fill.krw_rate == D("1392.0")  # cost basis at the rate that paid for it
    state = repo.load_state(conn, "paper")
    assert state.cash_of(Currency.USD) == D("0.68")
    assert state.cash_of(Currency.KRW) == D("40252")
    assert repo.get_plan(conn, plan.plan_id).status == "done"
    start = repo.start_event(conn, "paper")
    assert start is not None
    assert start.status == "done"
    assert D(start.payload["fees_krw"]) == D("748") + D("4956")

    # The invariant: the ledger rebuilt from events and fills equals the stored one.
    assert verify_ledger(conn, "paper") == []


def test_days_after_the_start(ctx: JobContext, conn: sqlite3.Connection, world: World) -> None:
    first_day_world(world)
    check_job(ctx, "paper", kst("2026-07-01 08:30"))
    for t in ("09:05", "09:10", "22:30"):
        stage_job(ctx, "paper", kst(f"2026-07-01 {t}"))
    snapshot_job(ctx, "paper", kst("2026-07-01 16:00"))

    world.rate(kst("2026-07-02 08:25"), "1391.0")
    day2 = check_job(ctx, "paper", kst("2026-07-02 08:30"))
    assert day2["result"] == "in-range"
    # 156 x 32,050 = 4,999,800 vs 54 x $66.20 x 1,391.0 = 4,972,547 -> 50.1% : 49.9%
    assert pct1(D(day2["details"]["drift"]["weights"][KR])) == D("50.1")

    world.bar(KR, "2026-07-02", close="32300", open_="32100")
    world.bar(US, "2026-07-02", close="66.10", open_="66.20")
    world.rate(kst("2026-07-02 16:00"), "1390.0")
    snap = snapshot_job(ctx, "paper", kst("2026-07-02 16:00"))
    # Day two: the baseline holds 5,000,000 won each from 7/1's opens (32,000 and $66.00 x 1,392.0).
    row = repo.get_snapshot(conn, "paper", kst("2026-07-02 16:00").date())
    assert row is not None
    assert row.baseline_units is not None
    units = {k: D(v) for k, v in row.baseline_units.items()}
    assert units[KR] == D("156.25")
    assert units[US] == D("5000000") / D("91872")
    assert snap["baseline_krw"] == round(D("156.25") * D("32300")) + round(
        D("5000000") / D("91872") * round(D("66.20") * D("1390.0"))
    )

    # 7/3: the US is closed; Korea trades. In range, so nothing is sent: '휴장'.
    world.rate(kst("2026-07-03 08:25"), "1389.0")
    holiday = check_job(ctx, "paper", kst("2026-07-03 08:30"))
    assert holiday["result"] == "holiday"
    assert holiday["details"]["closed_markets"] == ["US"]

    # Weekends do not run.
    assert check_job(ctx, "paper", kst("2026-07-04 08:30"))["result"] == "weekend"
    assert snapshot_job(ctx, "paper", kst("2026-07-04 16:00"))["result"] == "weekend"

    status = status_job(ctx, "paper", kst("2026-07-03 09:00"))
    assert status["rule_status"] == "holiday"
    assert status["ledger_check"] == []
    assert status["next_check_at"] == kst("2026-07-06 08:30")
    assert verify_ledger(conn, "paper") == []


def test_before_the_start_date_nothing_happens(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    world.rate(kst("2026-06-29 08:25"), "1390.0")
    assert check_job(ctx, "paper", kst("2026-06-29 08:30"))["result"] == "not-started"
    assert repo.start_event(conn, "paper") is None
    assert snapshot_job(ctx, "paper", kst("2026-06-29 16:00"))["result"] == "not-started"
