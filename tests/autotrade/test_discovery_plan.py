"""Phase 2: the AI rule's decisions become orders (sells, the same amount per new pick, the
monthly Korean equal weight of T29 EW-M, the index ETF that holds idle money), and the planner's
window in the tick."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal

from autotrade.db import ai_repo, repo
from autotrade.db.connection import transaction
from autotrade.domain.discovery_plan import DiscoveryInput, Holding, plan_discovery
from autotrade.domain.instruments import Currency, Instrument, Kind, Market, kr_etf, us_etf
from autotrade.domain.money import FeeRates
from autotrade.domain.planner import FxDirection
from autotrade.engine import discovery_plan, reviews, sleeves
from autotrade.engine.rebuild import verify_ledger
from autotrade.jobs.ai_tasks import plan_job
from autotrade.jobs.schedule import ai_plan_due
from autotrade.jobs.tasks import JobContext, stage_job
from autotrade.rules.discovery import RULE_ID

from .fakes import World
from .helpers import kst
from .phase2 import pick_of

D = Decimal
FEES = FeeRates()
KR_ETF = kr_etf("069500", "KOSPI200 ETF")
US_ETF = us_etf("SPYM", "S&P 500 ETF")


def stock(market: Market, ticker: str) -> Instrument:
    cur = Currency.KRW if market is Market.KR else Currency.USD
    yahoo = f"{ticker}.KS" if market is Market.KR else ticker
    return Instrument(f"{market.value}:{ticker}", market, cur, Kind.STOCK, ticker, ticker, yahoo)


A, B, C = stock(Market.KR, "000001"), stock(Market.KR, "000002"), stock(Market.US, "CCC")


def inp(holdings: list[Holding], **kw: object) -> DiscoveryInput:
    args: dict[str, object] = {
        "holdings": {h.instrument.instrument_id: h for h in holdings},
        "sell": (),
        "buy": (),
        "equalize": (),
        "parking": {Currency.KRW: KR_ETF.instrument_id, Currency.USD: US_ETF.instrument_id},
        "per_pick_krw": D(0),
        "cash_krw": D(0),
        "cash_usd": D(0),
        "fx_rate": D("1400"),
        "fees": FEES,
    }
    args.update(kw)
    return DiscoveryInput(**args)  # type: ignore[arg-type]


def orders(plan: object) -> dict[str, tuple[str, int]]:
    out: dict[str, tuple[str, int]] = {}
    for o in (*plan.sells, *plan.buys):  # type: ignore[attr-defined]
        out[o.instrument.instrument_id] = (o.side.value, o.qty)
    return out


def etfs(kr_qty: int = 0, us_qty: int = 0) -> list[Holding]:
    return [Holding(KR_ETF, kr_qty, D(33000)), Holding(US_ETF, us_qty, D("66.00"))]


# ── the pure plan ────────────────────────────────────────────────────────────────────────────


def test_new_picks_get_the_same_amount_and_the_rest_waits_in_the_index_etf() -> None:
    plan = plan_discovery(
        inp(
            [Holding(A, 0, D(50000)), Holding(B, 0, D(1000000)), Holding(C, 0, D(100)), *etfs()],
            buy=(A.instrument_id, B.instrument_id, C.instrument_id),
            per_pick_krw=D(666666),
            cash_krw=D(2000000),
        )
    )
    # A: 666,666 / 50,007.5 -> 13 shares. B is dearer than its amount: nothing.
    # C: 666,666 / (100 x 1.001 x 1,400) -> 4 shares, $400.40 -> 561,000 won converted.
    # The rest, 2,000,000 - 650,097 - 561,000 = 788,903 won -> 23 ETF shares of 33,004.
    assert orders(plan) == {
        A.instrument_id: ("buy", 13),
        C.instrument_id: ("buy", 4),
        KR_ETF.instrument_id: ("buy", 23),
    }
    assert plan.fx is not None
    assert (plan.fx.direction, plan.fx.from_amount, plan.fx.est_to_amount) == (
        FxDirection.KRW_TO_USD,
        D(561000),
        D("400.71"),
    )


def test_a_sale_pays_the_tax_and_parks_its_money() -> None:
    plan = plan_discovery(inp([Holding(A, 10, D(60000)), *etfs()], sell=(A.instrument_id,)))
    sale = plan.sells[0]
    # 600,000: fee 90 and the transaction tax 1,200 -> 598,710 -> 18 ETF shares.
    assert (sale.qty, sale.est_fee) == (10, D(1290))
    assert orders(plan) == {A.instrument_id: ("sell", 10), KR_ETF.instrument_id: ("buy", 18)}
    assert plan.fx is None


def test_korean_picks_are_set_to_equal_money_once_a_month() -> None:
    plan = plan_discovery(
        inp(
            [Holding(A, 10, D(60000)), Holding(B, 2, D(100000)), Holding(C, 3, D(100)), *etfs()],
            equalize=(A.instrument_id, B.instrument_id),
        )
    )
    # 600,000 and 200,000 -> 400,000 each: A sells 3, B buys 1 (2 would cost 200,030).
    # The US pick is never rebalanced; 79,598 won left -> 2 ETF shares.
    assert orders(plan) == {
        A.instrument_id: ("sell", 3),
        B.instrument_id: ("buy", 1),
        KR_ETF.instrument_id: ("buy", 2),
    }


def test_the_index_etf_pays_for_a_buy_then_buys_are_cut() -> None:
    funded = plan_discovery(
        inp(
            [Holding(A, 0, D(50000)), *etfs(kr_qty=100)],
            buy=(A.instrument_id,),
            per_pick_krw=D(500000),
        )
    )
    # 9 shares cost 450,067; one ETF share nets 32,996 -> sell 14 (461,944).
    assert orders(funded) == {A.instrument_id: ("buy", 9), KR_ETF.instrument_id: ("sell", 14)}
    cut = plan_discovery(
        inp(
            [Holding(A, 0, D(50000)), *etfs()],
            buy=(A.instrument_id,),
            per_pick_krw=D(500000),
            cash_krw=D(100000),
        )
    )
    # Only 100,000 won: one share (50,007), the rest parks (one ETF share).
    assert orders(cut) == {A.instrument_id: ("buy", 1), KR_ETF.instrument_id: ("buy", 1)}
    nothing = plan_discovery(
        inp([Holding(A, 0, D(50000)), *etfs()], buy=(A.instrument_id,), per_pick_krw=D(500000))
    )
    assert not nothing.has_orders


def test_dollars_from_a_us_sale_pay_for_a_korean_buy() -> None:
    plan = plan_discovery(
        inp(
            [Holding(A, 0, D(50000)), Holding(C, 10, D(100)), *etfs()],
            sell=(C.instrument_id,),
            buy=(A.instrument_id,),
            per_pick_krw=D(500000),
        )
    )
    assert plan.fx is not None
    assert plan.fx.direction is FxDirection.USD_TO_KRW
    assert orders(plan)[A.instrument_id] == ("buy", 9)
    assert orders(plan)[C.instrument_id] == ("sell", 10)


# ── the planner on the paper ledger ──────────────────────────────────────────────────────────


def seed_prices(
    conn: sqlite3.Connection, world: World, days: list[str], close: str = "100"
) -> None:
    """Every seed pick and both ETFs at one price (won or dollars) on the given sessions."""
    ids = {p.instrument_id for p in ai_repo.picks_of(conn, "paper", RULE_ID)} | {
        KR_ETF.instrument_id,
        US_ETF.instrument_id,
    }
    for iid in ids:
        for d in days:
            world.bar(iid, d, close=close, open_=close)


def test_the_first_plan_buys_the_seed_and_parks_the_rest(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    world.rate(kst("2026-07-02 08:25"), "1400.0")
    world.rate(kst("2026-07-02 09:10"), "1400.0")
    seed_prices(p2conn, world, ["2026-07-01", "2026-07-02"], "10000")
    at = kst("2026-07-02 08:40")
    due = ai_plan_due(p2conn, p2ctx.cfg, "paper", at)
    assert due is not None
    assert due.task == "ai-plan"
    report = plan_job(p2ctx, "paper", at)
    assert report["result"] == "planned"
    plan = repo.get_plan(p2conn, report["plan_id"])
    assert (plan.rule_id, plan.reason) == (RULE_ID, "ai")
    # 2,000,000 / 15 = 133,333 a pick: 13 shares of a 10,000-won stock (130,019),
    # and US picks at $10,000 x 1,400 are dearer than their amount.
    bought = dict(report["buy"])
    kr_picks = [
        p.instrument_id
        for p in ai_repo.picks_of(p2conn, "paper", RULE_ID)
        if p.instrument_id.startswith("KR:")
    ]
    assert all(bought[i] == 13 for i in kr_picks)
    assert not any(i.startswith("US:") and i != US_ETF.instrument_id for i in bought)
    event = repo.event_of_plan(p2conn, plan.plan_id)
    assert event is not None
    assert (event.kind, event.rule_id, event.payload["reason"]) == ("rebalance", RULE_ID, "ai")
    for t in ("09:05", "09:10", "22:30"):
        stage_job(p2ctx, "paper", kst(f"2026-07-02 {t}"))
    sleeve = ai_repo.load_sleeve(p2conn, "paper", RULE_ID)
    assert sleeve.qty_of(kr_picks[0]) == 13
    assert sleeves.verify_sleeves(p2conn, "paper") == []
    assert verify_ledger(p2conn, "paper") == []
    # Planned once a day; the next morning has nothing new.
    assert ai_plan_due(p2conn, p2ctx.cfg, "paper", kst("2026-07-02 08:50")) is None


def test_a_sale_closes_the_pick_when_it_fills(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    world.rate(kst("2026-07-02 08:25"), "1400.0")
    world.rate(kst("2026-07-03 08:25"), "1400.0")
    seed_prices(p2conn, world, ["2026-07-01", "2026-07-02", "2026-07-03"], "10000")
    plan_job(p2ctx, "paper", kst("2026-07-02 08:40"))
    for t in ("09:05", "09:10", "22:30"):
        stage_job(p2ctx, "paper", kst(f"2026-07-02 {t}"))
    ocean = pick_of(p2conn, "KR:042660")
    with transaction(p2conn):
        ai_repo.update_pick(
            p2conn,
            ocean.pick_id,
            kst("2026-07-03 08:35"),
            decision="sell",
            decided_at=kst("2026-07-03 08:35"),
        )
    at = kst("2026-07-03 08:40")
    assert ai_plan_due(p2conn, p2ctx.cfg, "paper", at) is not None
    report = plan_job(p2ctx, "paper", at)
    assert ("KR:042660", 13) in [tuple(x) for x in report["sell"]]
    stage_job(p2ctx, "paper", kst("2026-07-03 09:05"))  # it closes the pick after its fills
    assert ai_repo.load_sleeve(p2conn, "paper", RULE_ID).qty_of("KR:042660") == 0
    with transaction(p2conn):
        out = discovery_plan.reconcile(p2conn, "paper", kst("2026-07-06 08:40"))
    assert out == {"sold": [], "bought": []}  # nothing left to close
    sold = ai_repo.get_pick(p2conn, ocean.pick_id)
    assert (sold.status, sold.closed_on, sold.decision) == ("sold", date(2026, 7, 3), None)
    fills = [
        f
        for f in repo.fills_of_rule(p2conn, "paper", RULE_ID)
        if f.instrument_id == "KR:042660" and f.side == "sell"
    ]
    assert fills[0].fee == D(19) + D(260)  # 130,000: fee 19 and the transaction tax 260


def test_the_planner_window(p2ctx: JobContext, p2conn: sqlite3.Connection, world: World) -> None:
    c = p2ctx.cfg
    assert ai_plan_due(p2conn, c, "paper", kst("2026-07-02 08:29")) is None
    assert ai_plan_due(p2conn, c, "paper", kst("2026-07-02 09:05")) is None  # orders time
    assert ai_plan_due(p2conn, c, "paper", kst("2026-07-04 08:40")) is None  # Saturday
    assert ai_plan_due(p2conn, c, "live", kst("2026-07-02 08:40")) is None
    start, end = discovery_plan.window(c, date(2026, 11, 19))  # 수능: KRX opens at 10:00
    assert (start, end) == (kst("2026-11-19 08:30"), kst("2026-11-19 10:05"))
    assert discovery_plan.window(c, date(2026, 10, 9))[1] == kst("2026-10-09 09:05")  # 한글날
    # An open discovery plan blocks the next one.
    world.rate(kst("2026-07-02 08:25"), "1400.0")
    seed_prices(p2conn, world, ["2026-07-01", "2026-07-02"], "10000")
    plan_job(p2ctx, "paper", kst("2026-07-02 08:40"))
    assert ai_plan_due(p2conn, c, "paper", kst("2026-07-03 08:40")) is None


def test_the_monthly_equal_weight_waits_for_the_reviews(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    assert discovery_plan.ew_month(p2conn, "paper", date(2026, 8, 3)) is None  # not queued
    with transaction(p2conn):
        reviews.queue_reviews(p2conn, "paper", kst("2026-07-31 22:00"))
    assert discovery_plan.ew_month(p2conn, "paper", date(2026, 8, 3)) is None  # reviews pending
    with transaction(p2conn):
        for t in ai_repo.tasks_of(p2conn, kind="monthly-review"):
            ai_repo.finish_task(p2conn, t.task_id, kst("2026-08-01 01:00"), status="done")
    assert discovery_plan.ew_month(p2conn, "paper", date(2026, 8, 3)) == "2026-08"


def test_without_the_start_plan_the_planner_waits(
    p2conn: sqlite3.Connection, p2ctx: JobContext
) -> None:
    start = repo.start_event(p2conn, "paper")
    assert start is not None
    assert start.plan_id is not None
    with transaction(p2conn):
        p2conn.execute("UPDATE events SET plan_id = NULL WHERE kind = 'start'")
    assert ai_plan_due(p2conn, p2ctx.cfg, "paper", kst("2026-07-02 08:40")) is None
