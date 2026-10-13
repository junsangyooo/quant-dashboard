"""The live ledger runs on the money as the owner deposited it (D47) and new money waits a
trading day (D48), both 2026-10-13. Against the fake Toss (tests/autotrade/live_world.py).

D47: won buys the Korean ETF, dollars the US one; the live ledger never converts and never
sells one market to pay for the other. The owner converts in the Toss app whenever he wants; the
reconciliation recognizes it, and the dollars are bought at the next trading day's check.
D48: money the reconciliation books as the owner's money in (a deposit, a conversion of his) on
KST date D is not used by any check on D, not even one before it arrived; the first weekday 08:30
check after D uses it. Dividends and sale proceeds are not new money.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from autotrade.api.views.context import LedgerContext
from autotrade.db import repo
from autotrade.db.connection import transaction
from autotrade.domain.cash import Purpose
from autotrade.domain.instruments import Currency
from autotrade.domain.status import RuleStatus
from autotrade.engine.common import HELD_BACK, new_money_waiting, refresh_cash_parts
from autotrade.engine.rebuild import verify_ledger
from autotrade.market.service import prefetch_dividends

from .fakes import KR, World
from .helpers import kst
from .live_world import Live, make_live

D = Decimal
USD, KRW = Currency.USD, Currency.KRW


@pytest.fixture
def lw(tmp_path: Path, world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[Live]:
    monkeypatch.setenv("AUTOTRADE_LIVE_ORDERS", "1")
    yield from make_live(tmp_path, world)


def planned_buys(report: dict[str, Any]) -> list[tuple[str, int]]:
    return [(str(iid), int(qty)) for iid, qty in report["details"]["planned"]["buys"]]


def money_events(lw: Live, on: str) -> list[tuple[str, Decimal | None, Currency | None, str]]:
    """The deposits and withdrawals the reconciliation booked on `on`, in order."""
    day = date.fromisoformat(on)
    return [
        (e.kind, e.amount, e.currency, str(e.payload.get("reason")))
        for e in repo.events_of_ledger(lw.conn, "live", ["deposit", "withdrawal"])
        if e.event_date == day
    ]


def thursday(world: World) -> None:
    """The rate the Thursday 7/2 08:30 check reads (the 7/1 closes are in the world already)."""
    world.rate(kst("2026-07-02 08:25"), "1392.0")


# ── D47: the money as deposited ──────────────────────────────────────────────────────────


def test_a_won_only_start_buys_only_korea(lw: Live) -> None:
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    report = lw.check("2026-07-01 08:30")
    assert report["result"] == "rebalance"
    details = report["details"]
    assert (details["planned"]["sells"], details["planned"]["fx"]) == ([], None)
    assert planned_buys(report) == [("KR:069500", 312)]
    assert [(o.side, o.market) for o in repo.orders_of_ledger(lw.conn, "live")] == [("buy", "KR")]
    lw.fake.slip = D("160")
    lw.sync("2026-07-01 09:05")
    lw.stages()
    lw.sync("2026-07-01 22:30")
    assert [o.symbol for o in lw.fake.ours()] == ["069500"]  # nothing in dollars, ever
    # The rule is all in Korea: the chip says '환전 제안' and how much would make it 50:50
    # (the valuation is the 08:30 one: 310 x 32,000 + 78,512 = 9,998,512, half 4,999,256).
    ctx = LedgerContext(lw.conn, lw.cfg, "live", lw.at("2026-07-01 22:35"))
    assert ctx.status is RuleStatus.FX_SUGGEST
    found = ctx.fx_suggestion
    assert found is not None
    assert (found.direction.value, found.krw, found.usd) == (
        "krw_to_usd",
        D("4999000"),
        D("3591.24"),
    )


def test_the_owner_converts_on_tuesday_and_wednesday_buys_both(lw: Live, world: World) -> None:
    """The worked example: live from Tuesday 14:00 with 10,000,000원 only; at 15:00 the owner
    converts 2,000,000원 in the app; Wednesday 08:30 plans both markets, 09:05 buys Korea with
    the won and 22:30 the S&P 500 ETF with the dollars."""
    world.rate(kst("2026-06-30 13:55"), "1392.0")
    lw.turn_on("2026-06-30 14:00")
    lw.fake.convert(D("2000000"), D("1436.78"))
    lw.sync("2026-06-30 15:00")
    booked = lw.reconcile()["booked"]
    assert (booked[0]["conversion"], booked[0]["from"], booked[0]["to"]) == (
        "krw_to_usd",
        "2000000",
        "1436.78",
    )
    assert money_events(lw, "2026-06-30") == [
        ("withdrawal", D("2000000"), KRW, "conversion"),
        ("deposit", D("1436.78"), USD, "conversion"),
    ]
    # Tuesday's dollars are new money of Tuesday: no check that day may use them.
    assert new_money_waiting(lw.conn, "live", lw.now()) == {USD: D("1436.78")}

    # Wednesday 08:30: Tuesday's money is this check's. 8,000,000원 -> 249 shares; $1,436.78 ->
    # floor(1,436.78 / (66.00 x 1.001)) = 21 shares.
    lw.sync("2026-07-01 08:29")
    report = lw.check("2026-07-01 08:30")
    assert report["result"] == "rebalance"
    assert HELD_BACK not in report["details"]
    assert planned_buys(report) == [("KR:069500", 249), ("US:SPYM", 21)]
    orders = {o.market: o for o in repo.orders_of_ledger(lw.conn, "live")}
    assert set(orders) == {"KR", "US"}  # no 'FX' order: nothing to convert
    stages = repo.stages_of(lw.conn, orders["KR"].plan_id)
    assert [(s.kind, s.market, s.due_at) for s in stages] == [
        ("buy", "KR", kst("2026-07-01 09:05")),
        ("buy", "US", kst("2026-07-01 22:30")),
    ]

    # 09:05: the Korean buy, cut to what the won pays at the limit price:
    # floor(8,000,000 / (32,160 x 1.00015)) = 248.
    lw.fake.slip = D("160")
    lw.sync("2026-07-01 09:05")
    assert [(o.symbol, o.quantity, o.price) for o in lw.fake.ours()] == [
        ("069500", D("248"), D("32160"))
    ]
    assert lw.stages()["result"] == "done"

    # 22:30: the US buy with the converted dollars, a limit 0.5% over $66.00.
    lw.fake.slip = D("0.33")
    lw.sync("2026-07-01 22:30")
    us = lw.fake.ours()[1]
    assert (us.symbol, us.quantity, us.price) == ("SPYM", D("21"), D("66.33"))
    assert lw.stages()["result"] == "done"
    assert lw.reconcile()["result"] in ("match", "quiet")
    state = lw.state()
    assert (state.qty_of("KR:069500"), state.qty_of("US:SPYM")) == (248, 21)
    # 8,000,000 - 248 x 32,000 - 1,190 and 1,436.78 - 21 x 66.00 - 1.39, as the account shows.
    assert state.cash_of(KRW) == lw.fake.cash["KRW"] == D("62810")
    assert state.cash_of(USD) == lw.fake.cash["USD"] == D("49.39")
    assert verify_ledger(lw.conn, "live") == []
    assert repo.get_plan(lw.conn, orders["KR"].plan_id).status == "done"


def test_no_market_is_sold_to_pay_for_the_other(lw: Live) -> None:
    lw.fake.cash["KRW"] = D("0")
    lw.fake.hold("069500", D("300"), D("30000"), name="KODEX 200")
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    report = lw.check("2026-07-01 08:30")
    # 100% Korea, far outside the band: the plan makes no order; the owner converts if he wants.
    assert report["result"] == "in-range"
    assert report["details"]["drift"]["exceeded"] is True
    assert repo.orders_of_ledger(lw.conn, "live") == []
    ctx = LedgerContext(lw.conn, lw.cfg, "live", lw.at("2026-07-01 08:31"))
    assert ctx.status is RuleStatus.FX_SUGGEST


# ── D48: new money waits a trading day ───────────────────────────────────────────────────


def test_a_conversion_on_a_check_day_is_used_the_next_trading_day(lw: Live, world: World) -> None:
    lw.turn_on("2026-06-30 21:00")
    # Wednesday 07:00, before the check: the owner converts 2,000,000원 of the won.
    lw.fake.convert(D("2000000"), D("1436.78"))
    lw.sync("2026-07-01 07:00")
    assert lw.reconcile()["booked"][0]["conversion"] == "krw_to_usd"
    lw.sync("2026-07-01 08:29")
    report = lw.check("2026-07-01 08:30")
    # The won left buys Korea today; the dollars came today, so they wait.
    assert report["details"][HELD_BACK] == {"USD": D("1436.78")}
    assert planned_buys(report) == [("KR:069500", 249)]
    lw.fake.slip = D("160")
    lw.sync("2026-07-01 09:05")
    lw.stages()
    lw.sync("2026-07-01 22:30")
    assert [o.symbol for o in lw.fake.ours()] == ["069500"]  # no US order on Wednesday
    # Thursday 08:30: Wednesday's dollars are used (and the won the limit left on Wednesday).
    thursday(world)
    lw.sync("2026-07-02 08:29")
    report = lw.check("2026-07-02 08:30")
    assert report["result"] == "rebalance"
    assert HELD_BACK not in report["details"]
    # 62,810원 -> 1 share at 32,050; $1,436.78 -> floor(1,436.78 / (66.20 x 1.001)) = 21.
    assert planned_buys(report) == [("KR:069500", 1), ("US:SPYM", 21)]


def test_a_deposit_on_a_check_day_is_not_used_that_day_even_before_the_check(
    lw: Live, world: World
) -> None:
    lw.turn_on("2026-06-30 21:00")
    lw.fake.deposit("KRW", D("3000000"))
    lw.sync("2026-07-01 06:00")  # Wednesday, before the 08:30 check
    assert [b["deposit"] for b in lw.reconcile()["booked"]] == ["3000000"]
    lw.sync("2026-07-01 08:29")
    report = lw.check("2026-07-01 08:30")
    assert report["details"][HELD_BACK] == {"KRW": D("3000000")}
    assert planned_buys(report) == [("KR:069500", 312)]  # the start's won only
    # 09:05: the limit's headroom is not paid from it either: 310 shares, as without it.
    lw.fake.slip = D("160")
    lw.sync("2026-07-01 09:05")
    assert lw.fake.ours()[0].quantity == D("310")
    lw.stages()
    # Until the next check it is new cash, set apart (not '1주 미만').
    parts = {(p.currency, p.purpose): p.amount for p in repo.cash_parts(lw.conn, "live")}
    assert parts == {(KRW, Purpose.NEW): D("3000000"), (KRW, Purpose.SUB_SHARE): D("78512")}
    # After midnight it is no longer the day's, and still new cash for the next check.
    lw.at("2026-07-02 00:30")
    assert new_money_waiting(lw.conn, "live", lw.now()) == {}
    with transaction(lw.conn):
        parts = {
            (p.currency, p.purpose): p.amount for p in refresh_cash_parts(lw.conn, "live", lw.now())
        }
    assert parts == {(KRW, Purpose.NEW): D("3000000"), (KRW, Purpose.SUB_SHARE): D("78512")}
    # Thursday 08:30: used. 3,078,512원 -> floor(3,078,512 / (32,050 x 1.00015)) = 96.
    thursday(world)
    lw.sync("2026-07-02 08:29")
    report = lw.check("2026-07-02 08:30")
    assert HELD_BACK not in report["details"]
    assert planned_buys(report) == [("KR:069500", 96)]


def test_dividends_and_sale_proceeds_are_not_new_money(lw: Live, world: World) -> None:
    lw.fake.hold("069500", D("100"), D("30000"), name="KODEX 200")
    lw.turn_on("2026-06-30 21:00")
    world.dividend(KR, "2026-07-01", "160", pay_date="2026-07-03")
    prefetch_dividends(
        lw.conn,
        lw.cfg,
        lw.ctx.sources,
        [repo.get_instrument(lw.conn, KR)],
        date(2026, 6, 1),
        date(2026, 7, 3),
        lw.at("2026-07-03 08:00"),
    )
    lw.fake.deposit("KRW", D("13536"))
    lw.at("2026-07-03 08:05")
    lw.fake.app_trade("069500", "SELL", D("10"), D("32000"), commission=D("48"))
    lw.sync("2026-07-03 08:10")
    assert lw.reconcile()["result"] == "match"
    assert [e.kind for e in repo.events_of_ledger(lw.conn, "live", ["dividend"])] == ["dividend"]
    assert new_money_waiting(lw.conn, "live", lw.now()) == {}


# ── the reconciliation: a conversion that came with a deposit ────────────────────────────


def test_a_deposit_and_a_conversion_in_one_look_are_both(lw: Live) -> None:
    lw.turn_on("2026-06-30 21:00")
    # 3,000,000원 in, 1,000,000원 of it converted, before the tick looked again: won +2,000,000,
    # dollars +$718.39. A deposit and a conversion, not two deposits and not a mismatch.
    lw.fake.deposit("KRW", D("3000000"))
    lw.fake.convert(D("1000000"), D("718.39"))
    lw.sync("2026-06-30 22:00")
    result = lw.reconcile()
    assert result["result"] == "match"
    # The conversion's rate is not in the balances: the market's (1,392.0), so it moves no P&L.
    assert money_events(lw, "2026-06-30") == [
        ("deposit", D("2999999"), KRW, "unexplained-in"),
        ("withdrawal", D("999999"), KRW, "conversion"),
        ("deposit", D("718.39"), USD, "conversion"),
    ]
    usd = repo.events_of_ledger(lw.conn, "live", ["deposit"])[-1]
    assert (usd.payload["krw_rate"], usd.payload["amount_krw"], usd.payload["rate_basis"]) == (
        "1392.0",
        "999999",
        "market",
    )
    state = lw.state()
    assert (state.cash_of(KRW), state.cash_of(USD)) == (D("12000000"), D("718.39"))
    # Money in: the won deposited, the dollars at the market rate: as two deposits would be.
    assert state.contributions_krw == D("10000000") + D("2999999")
    assert verify_ledger(lw.conn, "live") == []
    # Both are the owner's new money of the day: the won he kept, the dollars he got.
    assert new_money_waiting(lw.conn, "live", lw.now()) == {KRW: D("2000000"), USD: D("718.39")}


def test_a_conversion_bigger_than_the_deposit_with_it(lw: Live) -> None:
    lw.turn_on("2026-06-30 21:00")
    # 1,000,000원 in, 3,000,000원 converted: won -2,000,000, dollars +$2,155.17 (a rate of 928:
    # no market's). The dollars cost 2,999,997원 at the market rate; the rest came in.
    lw.fake.deposit("KRW", D("1000000"))
    lw.fake.convert(D("3000000"), D("2155.17"))
    lw.sync("2026-06-30 22:00")
    assert lw.reconcile()["result"] == "match"
    assert money_events(lw, "2026-06-30") == [
        ("deposit", D("999997"), KRW, "unexplained-in"),
        ("withdrawal", D("2999997"), KRW, "conversion"),
        ("deposit", D("2155.17"), USD, "conversion"),
    ]
    assert verify_ledger(lw.conn, "live") == []


def test_dollars_converted_back_and_won_withdrawn_in_one_look(lw: Live) -> None:
    lw.fake.cash["USD"] = D("1000")
    lw.turn_on("2026-06-30 21:00")
    # $500 to won (696,000원 at 1,392.0), then 1,000,000원 out: won -304,000, dollars -$500.
    lw.fake.cash["USD"] -= D("500")
    lw.fake.cash["KRW"] += D("696000") - D("1000000")
    lw.sync("2026-06-30 22:00")
    assert lw.reconcile()["result"] == "match"
    assert money_events(lw, "2026-06-30") == [
        ("withdrawal", D("500"), USD, "conversion"),
        ("deposit", D("696000"), KRW, "conversion"),
        ("withdrawal", D("1000000"), KRW, "unexplained-out"),
    ]
    assert verify_ledger(lw.conn, "live") == []


def test_a_dividend_and_a_dollar_deposit_in_one_look_stay_apart(lw: Live, world: World) -> None:
    lw.fake.hold("069500", D("100"), D("30000"), name="KODEX 200")
    lw.turn_on("2026-06-30 21:00")
    world.dividend(KR, "2026-07-01", "160", pay_date="2026-07-03")
    prefetch_dividends(
        lw.conn,
        lw.cfg,
        lw.ctx.sources,
        [repo.get_instrument(lw.conn, KR)],
        date(2026, 6, 1),
        date(2026, 7, 3),
        lw.at("2026-07-03 08:00"),
    )
    lw.fake.deposit("KRW", D("13536"))  # the dividend
    lw.fake.deposit("USD", D("100"))  # dollars from elsewhere, in the same five minutes
    lw.sync("2026-07-03 08:10")
    assert lw.reconcile()["result"] == "match"
    assert [(e.kind, e.amount) for e in repo.events_of_ledger(lw.conn, "live", ["dividend"])] == [
        ("dividend", D("13536"))
    ]
    assert money_events(lw, "2026-07-03") == [("deposit", D("100"), USD, "unexplained-in")]


def test_converting_sale_proceeds_does_not_hold_the_orders(lw: Live) -> None:
    """D47's way to move money from Korea to the US without adding any: sell in the app and
    convert the proceeds. They waited for a withdrawal (인계 5); converted, they no longer do."""
    lw.fake.cash["KRW"] = D("0")
    lw.fake.hold("069500", D("20"), D("30000"), name="KODEX 200")
    lw.turn_on("2026-06-30 21:00")
    lw.at("2026-07-01 08:00")
    lw.fake.app_trade("069500", "SELL", D("14"), D("32000"), commission=D("67"))
    lw.sync("2026-07-01 08:05")
    lw.reconcile()
    assert [w.amount for w in repo.withdraw_waits(lw.conn, "live")] == [D("447933")]
    lw.fake.convert(D("447933"), D("321.79"))
    lw.sync("2026-07-01 08:10")
    assert lw.reconcile()["booked"][0]["conversion"] == "krw_to_usd"
    assert repo.withdraw_waits(lw.conn, "live") == []
    lw.sync("2026-07-01 08:29")
    report = lw.check("2026-07-01 08:30")
    assert report["result"] == "in-range"  # not 'withdraw-wait'; the dollars wait for tomorrow
    assert report["details"][HELD_BACK] == {"USD": D("321.79")}
    assert verify_ledger(lw.conn, "live") == []


def test_dollars_converted_back_are_new_won(lw: Live) -> None:
    lw.fake.cash["USD"] = D("1000")
    lw.turn_on("2026-06-30 21:00")
    # $500 -> 696,500원 in the app (1,393.0: within the band of 1,392.0).
    lw.fake.cash["USD"] -= D("500")
    lw.fake.cash["KRW"] += D("696500")
    lw.sync("2026-06-30 22:00")
    booked = lw.reconcile()["booked"]
    assert (booked[0]["conversion"], booked[0]["from"], booked[0]["to"]) == (
        "usd_to_krw",
        "500",
        "696500",
    )
    assert money_events(lw, "2026-06-30") == [
        ("withdrawal", D("500"), USD, "conversion"),
        ("deposit", D("696500"), KRW, "conversion"),
    ]
    assert new_money_waiting(lw.conn, "live", lw.now()) == {KRW: D("696500")}
    assert verify_ledger(lw.conn, "live") == []


def test_the_untouched_line_of_a_won_only_ledger_is_still_half_and_half(
    lw: Live, world: World
) -> None:
    """'손대지 않았을 때' stays the rule's 50:50 bought at the start and held (인계 4·14): with won
    only, the live ledger itself is all in Korea (D47), so the gap to that line is the owner's
    mix of currencies, which the plan screen's '환전 제안' speaks to."""
    world.rate(kst("2026-06-30 08:25"), "1392.0")
    from autotrade.market.service import prefetch_fx

    prefetch_fx(lw.conn, lw.ctx.sources, kst("2026-06-30 09:10"))
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    lw.check("2026-07-01 08:30")
    lw.fake.slip = D("160")
    lw.sync("2026-07-01 09:05")
    lw.stages()
    snap = lw.snapshot("2026-07-01 16:05")
    assert snap["result"] == "ok"
    row = repo.latest_snapshot_before(lw.conn, "live", date(2026, 7, 2))
    assert row is not None and row.baseline_units is not None  # noqa: PT018
    units = {k: D(v) for k, v in row.baseline_units.items()}
    # 5,000,000원 each at the start day's opens: 31,950원 and $65.95 x 1,392.0 = 91,802원.
    assert units["KR:069500"] == D("5000000") / D("31950")
    assert units["US:SPYM"] == D("5000000") / D("91802")
    assert row.total_krw == D("9935500") + D("78512")  # 310 x 32,050 + the won left
