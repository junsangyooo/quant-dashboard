"""Phase 2: the AI rule's decisions become orders (sells, the same amount per new pick, the
monthly Korean equal weight of T29 EW-M, the index ETF that holds idle money), and the planner's
window in the tick."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal

from autotrade.db import ai_repo, repo
from autotrade.db.connection import transaction
from autotrade.db.models import FillRow
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
    assert discovery_plan.ew_month(p2conn, "paper", date(2026, 8, 3), 3) is None  # not queued
    with transaction(p2conn):
        reviews.queue_reviews(p2conn, "paper", kst("2026-07-31 22:00"))
    assert discovery_plan.ew_month(p2conn, "paper", date(2026, 8, 3), 3) is None  # reviews pending
    with transaction(p2conn):
        for t in ai_repo.tasks_of(p2conn, kind="monthly-review"):
            ai_repo.finish_task(p2conn, t.task_id, kst("2026-08-01 01:00"), status="done")
    assert discovery_plan.ew_month(p2conn, "paper", date(2026, 8, 3), 3) == "2026-08"


def test_without_the_start_plan_the_planner_waits(
    p2conn: sqlite3.Connection, p2ctx: JobContext
) -> None:
    start = repo.start_event(p2conn, "paper")
    assert start is not None
    assert start.plan_id is not None
    with transaction(p2conn):
        p2conn.execute("UPDATE events SET plan_id = NULL WHERE kind = 'start'")
    assert ai_plan_due(p2conn, p2ctx.cfg, "paper", kst("2026-07-02 08:40")) is None


def test_selling_the_index_etf_pays_no_transaction_tax() -> None:
    from autotrade.domain.discovery_plan import sell_net

    assert sell_net(Holding(KR_ETF, 10, D(33000)), 10, FEES) == D(330000) - D(49)
    assert sell_net(Holding(A, 10, D(33000)), 10, FEES) == D(330000) - D(49) - D(660)
    assert sell_net(Holding(C, 10, D(100)), 10, FEES) == D(1000) - D("1.00")


# ── audit 2026-10-10 ─────────────────────────────────────────────────────────────────────────


def _ai_sale(conn: sqlite3.Connection, instrument_id: str, qty: int, day: str) -> None:
    """An AI-rule plan that sells `qty` of what it parked, due at the day's Korean order time."""
    at = kst(f"{day} 08:40")
    with transaction(conn):
        plan_id = repo.insert_plan(
            conn,
            ledger_id="paper",
            rule_id=RULE_ID,
            plan_date=date.fromisoformat(day),
            run_id=None,
            reason="ai",
            basis={},
            weights_before={},
            weights_after_est={},
            created_at=at,
        )
        stage_id = repo.insert_stage(
            conn,
            plan_id=plan_id,
            seq=1,
            kind="sell",
            market="KR",
            due_at=kst(f"{day} 09:05"),
            depends_on=[],
        )
        repo.insert_order(
            conn,
            repo.NewOrder(
                idem_key=f"test-sale-{day}",
                ledger_id="paper",
                plan_id=plan_id,
                stage_id=stage_id,
                stage="sell",
                market="KR",
                instrument_id=instrument_id,
                side="sell",
                fx_direction=None,
                currency=Currency.KRW,
                qty=qty,
                est_price=D(11000),
                est_amount=D(11000) * qty,
                est_fee=D(0),
                est_rate=None,
                est_received=None,
            ),
            at,
        )


def test_each_rule_keeps_its_own_cost_basis(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    """E8: '지수 반반' bought KOSPI200 at 32,000; the AI rule parks money in it at 10,000 and
    sells that later. The long-term rule's cost and realized gains do not move."""
    for t in ("09:05", "09:10", "22:30"):
        stage_job(p2ctx, "paper", kst(f"2026-07-01 {t}"))  # '지수 반반' buys at the 7/1 open
    kr = KR_ETF.instrument_id
    before = sleeves.base_view(p2conn, "paper")
    own_cost = before.positions[kr].cost_krw
    assert before.positions[kr].cost_native / before.qty_of(kr) > D(32000)  # its open plus fee
    world.rate(kst("2026-07-02 08:25"), "1400.0")
    world.rate(kst("2026-07-02 09:10"), "1400.0")
    seed_prices(p2conn, world, ["2026-07-02", "2026-07-03"], "10000")
    plan_job(p2ctx, "paper", kst("2026-07-02 08:40"))
    for t in ("09:05", "09:10", "22:30"):
        stage_job(p2ctx, "paper", kst(f"2026-07-02 {t}"))
    parked = ai_repo.load_sleeve(p2conn, "paper", RULE_ID).qty_of(kr)
    assert parked > 0
    assert sleeves.base_view(p2conn, "paper").positions[kr].cost_krw == own_cost
    _ai_sale(p2conn, kr, parked, "2026-07-03")
    stage_job(p2ctx, "paper", kst("2026-07-03 09:05"))
    assert ai_repo.load_sleeve(p2conn, "paper", RULE_ID).qty_of(kr) == 0
    after = sleeves.base_view(p2conn, "paper")
    assert (after.qty_of(kr), after.positions[kr].cost_krw) == (before.qty_of(kr), own_cost)
    assert after.realized_krw == before.realized_krw == D(0)  # it never sold
    # Ledger minus sleeve (the pooled average) would have moved it.
    pooled = sleeves.subtract(
        repo.load_state(p2conn, "paper"), ai_repo.load_sleeve(p2conn, "paper", RULE_ID)
    )
    assert pooled.positions[kr].cost_krw != own_cost
    assert pooled.realized_krw != D(0)
    assert sleeves.verify_sleeves(p2conn, "paper") == []
    assert verify_ledger(p2conn, "paper") == []


def test_own_costs_fall_back_where_the_fills_do_not_cover_the_shares() -> None:
    """A ledger seeded mid-way has shares no fill bought: the subtraction stays for them."""
    from autotrade.domain.ledger import LedgerState, Position

    rest = LedgerState(
        positions={
            "KR:069500": Position("KR:069500", Currency.KRW, 10, D(320000), D(320000)),
            "US:SPYM": Position("US:SPYM", Currency.USD, 5, D(330), D(462000)),
        }
    )
    gap = sleeves.OwnBook({}, D(5), frozenset({"KR:069500"}))
    assert sleeves.with_own_costs(rest, gap) == rest  # realized and costs from the ledger
    mine = sleeves.OwnBook(
        {"KR:069500": Position("KR:069500", Currency.KRW, 10, D(300000), D(300000))},
        D(7),
        frozenset(),
    )
    mixed = sleeves.with_own_costs(rest, mine)
    assert mixed.positions["KR:069500"].cost_krw == D(300000)
    assert mixed.positions["US:SPYM"] == rest.positions["US:SPYM"]  # no fill of it: as it was
    assert mixed.realized_krw == rest.realized_krw  # not every share is accounted for


def test_the_equal_weight_waits_for_reviews_with_attempts_left_only(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    """E9: a review failed with attempts left holds the equal weight; one that failed for good
    (a red 'to do') does not, and its pick is left out of it."""
    world.rate(kst("2026-07-02 08:25"), "1400.0")
    seed_prices(p2conn, world, ["2026-07-01", "2026-07-02"], "10000")
    plan_job(p2ctx, "paper", kst("2026-07-02 08:40"))
    for hhmm in ("09:05", "09:10", "22:30"):
        stage_job(p2ctx, "paper", kst(f"2026-07-02 {hhmm}"))
    with transaction(p2conn):
        reviews.queue_reviews(p2conn, "paper", kst("2026-07-31 22:00"))
    month = ai_repo.tasks_of(p2conn, kind="monthly-review")
    ocean = pick_of(p2conn, "KR:042660")
    with transaction(p2conn):
        for review in month:
            status = "failed" if review.pick_id == ocean.pick_id else "done"
            ai_repo.finish_task(p2conn, review.task_id, kst("2026-08-01 01:00"), status=status)
    assert discovery_plan.ew_month(p2conn, "paper", date(2026, 8, 3), 3) is None  # 2 attempts left
    [stuck] = [r for r in month if r.pick_id == ocean.pick_id]
    with transaction(p2conn):
        for _ in range(2):
            ai_repo.finish_task(p2conn, stuck.task_id, kst("2026-08-01 02:00"), status="failed")
    assert discovery_plan.ew_month(p2conn, "paper", date(2026, 8, 3), 3) == "2026-08"
    assert discovery_plan.unreviewed(p2conn, "paper", "2026-08", 3) == {ocean.instrument_id}
    # The plan of that day leaves the unreviewed pick out of the equal weight.
    world.rate(kst("2026-08-03 08:25"), "1400.0")
    seed_prices(p2conn, world, ["2026-07-31", "2026-08-03"], "10000")
    world.bar("KR:012450", "2026-07-31", close="20000", open_="20000")  # one pick doubled
    report = plan_job(p2ctx, "paper", kst("2026-08-03 08:40"))
    assert report["result"] == "planned"
    plan = repo.get_plan(p2conn, report["plan_id"])
    assert plan.basis["equalize"] == "2026-08"
    assert plan.basis["equalize_skipped"] == ["KR:042660"]
    traded = {i for i, _ in (*report["sell"], *report["buy"])}
    assert "KR:012450" in traded  # the others are equalized
    assert "KR:042660" not in traded


def _fill(n: int, side: str, qty: int, price: str, kind: str = "trade") -> FillRow:
    return FillRow(
        fill_id=n,
        order_id=n,
        ledger_id="paper",
        kind=kind,
        instrument_id=None if kind == "fx" else KR_ETF.instrument_id,
        side="fx" if kind == "fx" else side,
        fx_direction="krw_to_usd" if kind == "fx" else None,
        currency=Currency.KRW,
        qty=None if kind == "fx" else qty,
        price=None if kind == "fx" else D(price),
        gross=D(price) * max(qty, 1),
        fee=D(0),
        fee_krw=D(0),
        krw_rate=D("1400") if kind == "fx" else None,
        received=D(1) if kind == "fx" else None,
        filled_at=kst(f"2026-07-0{n} 09:05"),
        price_source="test",
        executor="paper",
    )


def test_own_book_folds_a_rule_s_trades_and_marks_gaps() -> None:
    book = sleeves.own_book(
        [
            _fill(1, "buy", 10, "30000"),
            _fill(2, "fx", 0, "1000000", kind="fx"),  # a conversion moves no share
            _fill(3, "sell", 4, "33000"),
        ]
    )
    pos = book.positions[KR_ETF.instrument_id]
    assert (pos.qty, pos.cost_krw, book.realized_krw, book.gaps) == (
        6,
        D(180000),
        D(12000),
        frozenset(),
    )
    # A sale of shares no fill bought (a ledger seeded mid-way): the instrument is a gap, and
    # its later fills are not folded either.
    seeded = sleeves.own_book([_fill(1, "sell", 4, "33000"), _fill(2, "buy", 1, "30000")])
    assert (seeded.positions, seeded.gaps) == ({}, frozenset({KR_ETF.instrument_id}))


def test_verify_sleeves_checks_the_base_rule_s_own_shares(
    p2ctx: JobContext, p2conn: sqlite3.Connection
) -> None:
    for t in ("09:05", "09:10", "22:30"):
        stage_job(p2ctx, "paper", kst(f"2026-07-01 {t}"))
    assert sleeves.verify_sleeves(p2conn, "paper") == []
    # Shares the ledger has that no fill of '지수 반반' bought: reported, never silently costed.
    with transaction(p2conn):
        state = repo.load_state(p2conn, "paper")
        kr = state.positions[KR_ETF.instrument_id]
        more = replace(kr, qty=kr.qty + 5, cost_native=kr.cost_native + 5, cost_krw=kr.cost_krw + 5)
        positions = {**state.positions, KR_ETF.instrument_id: more}
        repo.save_state(
            p2conn, "paper", replace(state, positions=positions), kst("2026-07-02 08:00")
        )
    [problem] = sleeves.verify_sleeves(p2conn, "paper")
    assert problem.startswith("index_half KR:069500: own fills hold ")
    base = sleeves.base_view(p2conn, "paper")
    assert base.positions[KR_ETF.instrument_id] == more  # the subtraction stays for it
