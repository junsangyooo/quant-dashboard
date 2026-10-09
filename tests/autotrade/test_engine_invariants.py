"""The invariants of ops notes 품질 기준.

- Stale data, a closed market or a pending withdrawal -> 0 orders for that market.
- Running the same check twice -> no duplicate orders.
- Rebuilding the ledger from events matches to the won.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

import pytest

from autotrade.db import repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency
from autotrade.engine.check import run_check
from autotrade.engine.rebuild import verify_ledger
from autotrade.jobs.tasks import JobContext, check_job, snapshot_job, stage_job
from autotrade.market.service import FetchErrors
from autotrade.timeutil import ET, KST

from .fakes import KR, US, World
from .helpers import kst, seed_ledger

D = Decimal


def seed_drifted(conn: sqlite3.Connection) -> None:
    """KOSPI200 ETF over target: 120 x ~36,000 vs 46 x ~$62 (about 52 : 48)."""
    seed_ledger(
        conn,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("47675"),
        usd=D("1.66"),
        positions={KR: (120, D("3840576"), D("3840576")), US: (46, D("3033.03"), D("4221675"))},
    )


def prices(world: World, d: str, kr: str = "36360", us: str = "62.40") -> None:
    world.bar(KR, d, close=kr, open_=kr)
    world.bar(US, d, close=us, open_=us)


def no_orders(conn: sqlite3.Connection) -> bool:
    return repo.orders_of_ledger(conn, "paper") == [] and repo.open_plans(conn, "paper") == []


# ── stale data ────────────────────────────────────────────────────────────────────────────


def test_stale_us_closes_mean_zero_orders(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    # §3 '시세 대기': US closes stuck at 10/02; at 10/07 08:30 the 10/05 and 10/06 closes
    # are missing.
    seed_drifted(conn)
    world.bar(KR, "2026-10-06", close="36360")
    world.bar(US, "2026-10-02", close="62.10")
    world.rate(kst("2026-10-07 08:25"), "1380.6")
    report = check_job(ctx, "paper", kst("2026-10-07 08:30"))
    assert report["result"] == "quote-wait"
    assert report["details"]["stale"] == ["us-quotes"]
    assert no_orders(conn)
    fresh = repo.get_freshness(conn, "us-quotes")
    assert fresh is not None
    assert (fresh.state, fresh.basis, fresh.expected, fresh.missing_sessions) == (
        "stale",
        "2026-10-02",
        "2026-10-06",
        2,  # '2거래일째 갱신 없음'
    )


def test_stale_korean_closes_mean_zero_orders(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_drifted(conn)
    world.bar(KR, "2026-10-01", close="36360")
    world.bar(US, "2026-10-06", close="62.40")
    world.rate(kst("2026-10-07 08:25"), "1380.6")
    assert check_job(ctx, "paper", kst("2026-10-07 08:30"))["result"] == "quote-wait"
    assert no_orders(conn)


def test_a_stale_rate_means_zero_orders(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_drifted(conn)
    prices(world, "2026-10-06")
    world.rate(kst("2026-10-02 08:25"), "1380.6")  # three weekdays old
    report = check_job(ctx, "paper", kst("2026-10-07 08:30"))
    assert report["result"] == "quote-wait"
    assert report["details"]["stale"] == ["fx"]
    assert no_orders(conn)


def test_a_fresh_book_survives_a_failed_download(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    # The 10/06 US close was stored earlier; the source being down at 08:30 does not fail the check.
    seed_drifted(conn)
    prices(world, "2026-10-06")
    world.rate(kst("2026-10-07 08:25"), "1380.6")
    snapshot_job(ctx, "paper", kst("2026-10-07 08:00"))  # caches the bars and the rate
    world.fail_bars.add(US)
    report = check_job(ctx, "paper", kst("2026-10-07 08:30"))
    assert report["result"] == "rebalance"


# ── closed markets ────────────────────────────────────────────────────────────────────────


def test_korean_holiday_sends_nothing_and_the_next_check_plans(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    # 10/09 (한글날): Korea is closed; the US is open. The plan would start with a Korean sell.
    seed_drifted(conn)
    prices(world, "2026-10-08")
    world.rate(kst("2026-10-09 08:25"), "1380.6")
    report = check_job(ctx, "paper", kst("2026-10-09 08:30"))
    assert report["result"] == "holiday"
    assert report["details"]["closed_markets"] == ["KR"]
    assert report["details"]["deferred"] is True
    assert no_orders(conn)
    # Next trading day (Monday 10/12) the check plans as usual (the US traded on 10/09).
    world.bar(US, "2026-10-09", close="62.40", open_="62.40")
    world.rate(kst("2026-10-12 08:25"), "1380.6")
    assert check_job(ctx, "paper", kst("2026-10-12 08:30"))["result"] == "rebalance"


def test_us_holiday_holds_only_the_us_orders(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    # 7/3 (US closed): sell in Korea and convert that day; the US buy waits for 7/6 22:30.
    seed_drifted(conn)
    prices(world, "2026-07-02")
    world.rate(kst("2026-07-03 08:25"), "1390.0")
    world.rate(kst("2026-07-03 09:10"), "1390.0")
    world.bar(KR, "2026-07-03", close="36400", open_="36380")
    report = check_job(ctx, "paper", kst("2026-07-03 08:30"))
    assert report["result"] == "rebalance"
    stages = repo.stages_of(conn, report["plan_id"])
    us_stage = next(s for s in stages if s.market == "US")
    assert us_stage.due_at.astimezone(ET).date() == date(2026, 7, 6)
    assert us_stage.due_at.astimezone(KST) == kst("2026-07-06 22:30")

    stage_job(ctx, "paper", kst("2026-07-03 23:59"))
    executed = [o for o in repo.orders_of_ledger(conn, "paper") if o.executed_at is not None]
    assert {o.market for o in executed} == {"KR", "FX"}  # nothing in the closed market
    assert all(f.instrument_id != US for f in repo.fills_of_ledger(conn, "paper"))


def test_us_first_plan_on_a_us_holiday_waits(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    # S&P over target on 7/3: the plan would begin with a US sell; nothing is sent today.
    seed_ledger(
        conn,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("0"),
        usd=D("0"),
        positions={KR: (100, D("3000000"), D("3000000")), US: (40, D("2640"), D("3670000"))},
    )
    prices(world, "2026-07-02", kr="30000", us="66.00")
    world.rate(kst("2026-07-03 08:25"), "1390.0")
    report = check_job(ctx, "paper", kst("2026-07-03 08:30"))
    assert report["result"] == "holiday"
    assert report["details"]["closed_markets"] == ["US"]
    assert no_orders(conn)


# ── withdraw wait ─────────────────────────────────────────────────────────────────────────


def test_pending_withdrawal_means_zero_orders(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_drifted(conn)
    with transaction(conn):
        repo.add_withdraw_wait(
            conn, "paper", Currency.KRW, D("40000"), date(2026, 10, 12), kst("2026-10-02 10:00")
        )
    prices(world, "2026-10-06")
    world.rate(kst("2026-10-07 08:25"), "1380.6")
    report = check_job(ctx, "paper", kst("2026-10-07 08:30"))
    assert report["result"] == "withdraw-wait"
    assert str(report["details"]["withdraw_wait_until"]) == "2026-10-12"
    assert no_orders(conn)
    # The wait ends after 10/12: on 10/13 the check trades again.
    prices(world, "2026-10-12")
    world.rate(kst("2026-10-13 08:25"), "1380.6")
    assert check_job(ctx, "paper", kst("2026-10-13 08:30"))["result"] == "rebalance"
    assert repo.withdraw_waits(conn, "paper") == []


# ── idempotency ───────────────────────────────────────────────────────────────────────────


def test_running_the_same_check_twice_sends_orders_once(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_drifted(conn)
    prices(world, "2026-10-06")
    world.rate(kst("2026-10-07 08:25"), "1380.6")
    world.rate(kst("2026-10-07 09:10"), "1380.6")
    world.bar(KR, "2026-10-07", close="36250", open_="36380")
    first = check_job(ctx, "paper", kst("2026-10-07 08:30"))
    orders = repo.orders_of_ledger(conn, "paper")
    second = check_job(ctx, "paper", kst("2026-10-07 08:30"))
    assert first["result"] == "rebalance"
    assert second["result"] == "in-progress"
    assert repo.orders_of_ledger(conn, "paper") == orders

    # The engine function itself, twice in one transaction: still one set of orders.
    with transaction(conn):
        run_check(conn, ctx.cfg, "paper", kst("2026-10-07 08:31"), fetch=FetchErrors())
        run_check(conn, ctx.cfg, "paper", kst("2026-10-07 08:32"), fetch=FetchErrors())
    assert repo.orders_of_ledger(conn, "paper") == orders

    # Stages twice: each order fills once.
    stage_job(ctx, "paper", kst("2026-10-07 09:10"))
    fills = repo.fills_of_ledger(conn, "paper")
    assert stage_job(ctx, "paper", kst("2026-10-07 09:10"))["result"] == "nothing-due"
    assert repo.fills_of_ledger(conn, "paper") == fills
    assert len(fills) == 2

    # A completed plan for today blocks another one today.
    world.bar(US, "2026-10-07", close="62.40", open_="62.40")
    stage_job(ctx, "paper", kst("2026-10-07 22:30"))
    assert repo.get_plan(conn, first["plan_id"]).status == "done"
    assert check_job(ctx, "paper", kst("2026-10-07 23:00"))["result"] == "already-planned"


def test_idempotency_key_is_unique(conn: sqlite3.Connection, ctx: JobContext, world: World) -> None:
    seed_drifted(conn)
    prices(world, "2026-10-06")
    world.rate(kst("2026-10-07 08:25"), "1380.6")
    check_job(ctx, "paper", kst("2026-10-07 08:30"))
    order = repo.orders_of_ledger(conn, "paper")[0]
    again = repo.NewOrder(
        idem_key=order.idem_key,
        ledger_id="paper",
        plan_id=order.plan_id,
        stage_id=order.stage_id,
        stage=order.stage,
        market=order.market,
        instrument_id=order.instrument_id,
        side=order.side,
        fx_direction=order.fx_direction,
        currency=order.currency,
        qty=order.qty,
        est_price=order.est_price,
        est_amount=order.est_amount,
        est_fee=order.est_fee,
        est_rate=order.est_rate,
        est_received=order.est_received,
    )
    with transaction(conn):
        assert repo.insert_order(conn, again, kst("2026-10-07 08:40")) == (order.order_id, False)
    with pytest.raises(sqlite3.IntegrityError), transaction(conn):
        conn.execute(
            "INSERT INTO orders (idem_key, ledger_id, plan_id, stage_id, stage, market, side,"
            " currency, est_amount, status, created_at) VALUES (?, 'paper', ?, ?, 'sell', 'KR',"
            " 'sell', 'KRW', '1', 'pending', 'x')",
            (order.idem_key, order.plan_id, order.stage_id),
        )


# ── rebuild ───────────────────────────────────────────────────────────────────────────────


def test_rebuild_matches_after_weeks_of_trading(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    # Start 7/1, then a KOSPI rally triggers a rebalance on 7/7; the ledger rebuilt from the
    # records equals the stored one to the won, and a tampered table is caught.
    world.bar(KR, "2026-06-30", close="32000", open_="31900")
    world.bar(US, "2026-06-30", close="66.00", open_="65.80")
    world.rate(kst("2026-07-01 08:25"), "1392.0")
    world.rate(kst("2026-07-01 09:10"), "1392.0")
    world.rate(kst("2026-07-01 16:00"), "1391.5")
    world.bar(KR, "2026-07-01", close="32050", open_="32000")
    world.bar(US, "2026-07-01", close="66.20", open_="66.00")
    check_job(ctx, "paper", kst("2026-07-01 08:30"))
    for t in ("09:05", "09:10", "22:30"):
        stage_job(ctx, "paper", kst(f"2026-07-01 {t}"))
    snapshot_job(ctx, "paper", kst("2026-07-01 16:00"))

    world.bar(KR, "2026-07-02", close="33000", open_="32500")
    world.bar(US, "2026-07-02", close="66.00", open_="66.10")
    world.bar(KR, "2026-07-03", close="34600", open_="34000")
    world.rate(kst("2026-07-06 08:25"), "1390.0")
    world.rate(kst("2026-07-06 09:10"), "1390.0")
    world.bar(KR, "2026-07-06", close="34800", open_="34700")
    report = check_job(ctx, "paper", kst("2026-07-06 08:30"))
    assert report["result"] == "rebalance"
    world.bar(US, "2026-07-06", close="65.50", open_="65.80")
    for t in ("09:05", "09:10", "22:30"):
        stage_job(ctx, "paper", kst(f"2026-07-06 {t}"))
    assert repo.get_plan(conn, report["plan_id"]).status == "done"
    assert len(repo.fills_of_ledger(conn, "paper")) == 6

    assert verify_ledger(conn, "paper") == []

    with transaction(conn):
        conn.execute(
            "UPDATE cash SET amount = amount + 1 WHERE ledger_id = 'paper' AND currency = 'KRW'"
        )
    assert verify_ledger(conn, "paper") == [verify_ledger(conn, "paper")[0]]
    assert verify_ledger(conn, "paper")[0].startswith("cash KRW")
