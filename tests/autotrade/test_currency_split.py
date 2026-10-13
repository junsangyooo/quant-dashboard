"""The live ledger's pure pieces (D47·D48, 2026-10-13): the per-currency plan, the suggestion
that would bring the mix back to the targets, the new money set apart in the cash parts, and the
'환전 제안' chip. The paper planner (plan_rule) keeps its own tests (test_planner.py) untouched."""

from __future__ import annotations

from decimal import Decimal

import pytest

from autotrade.domain.cash import Claim, Purpose, partition
from autotrade.domain.currency_mix import CurrencyMix, drift_within_currencies, suggest
from autotrade.domain.instruments import Currency, kr_etf, us_etf
from autotrade.domain.money import FeeRates
from autotrade.domain.planner import (
    FxDirection,
    PlanInput,
    PlanItem,
    PlanReason,
    Side,
    plan_per_currency,
    plan_rule,
)
from autotrade.domain.status import RuleStatus, StatusFlags, rule_status

D = Decimal
KOSPI = kr_etf("069500", "KOSPI200 ETF")
SNP = us_etf("SPYM", "S&P 500 ETF")
TIGER = kr_etf("102110", "TIGER 200")
HALF = D("0.5")
FEES = FeeRates()


def index_half(
    kospi_qty: int = 0, snp_qty: int = 0, free_krw: str = "0", free_usd: str = "0"
) -> PlanInput:
    return PlanInput(
        items=(
            PlanItem(KOSPI, HALF, kospi_qty, D("32000")),
            PlanItem(SNP, HALF, snp_qty, D("66.00")),
        ),
        threshold=D("0.02"),
        fx_rate=D("1392.0"),
        free_krw=D(free_krw),
        free_usd=D(free_usd),
        fees=FEES,
    )


# ── the per-currency plan ────────────────────────────────────────────────────────────────


def test_won_only_buys_only_the_korean_etf() -> None:
    plan = plan_per_currency(index_half(free_krw="10000000"))
    assert plan.fx is None and plan.sells == ()  # noqa: PT018
    assert [(o.instrument.ticker, o.side, o.qty) for o in plan.buys] == [("069500", Side.BUY, 312)]
    assert plan.reason is PlanReason.NEW_CASH
    # Paper, on the same money, converts half (its virtual conversion measures the strategy).
    paper = plan_rule(index_half(free_krw="10000000"))
    assert paper.fx is not None and paper.fx.direction is FxDirection.KRW_TO_USD  # noqa: PT018


def test_dollars_only_buy_only_the_us_etf() -> None:
    plan = plan_per_currency(index_half(free_usd="1436.78"))
    assert plan.fx is None
    # floor(1,436.78 / (66.00 x 1.001)) = 21
    assert [(o.instrument.ticker, o.qty) for o in plan.buys] == [("SPYM", 21)]


def test_each_currency_buys_its_own() -> None:
    plan = plan_per_currency(index_half(free_krw="8000000", free_usd="1436.78"))
    assert plan.fx is None
    assert [(o.instrument.ticker, o.qty) for o in plan.buys] == [("069500", 249), ("SPYM", 21)]
    # The report stays the whole rule's: 0 held so far, so no weights yet.
    assert plan.report.weights == {}
    assert plan.weights_after["KR:069500"] > D("0.7")  # the mix is the owner's


def test_no_market_is_sold_for_the_other() -> None:
    # All in Korea and no cash: far outside the band, still nothing to do.
    plan = plan_per_currency(index_half(kospi_qty=300))
    assert plan.report.exceeded
    assert not plan.has_orders
    assert plan.reason is None


def test_a_drift_within_one_currency_is_traded_back() -> None:
    inp = PlanInput(
        items=(
            PlanItem(KOSPI, D("0.3"), 200, D("10000")),
            PlanItem(TIGER, D("0.2"), 100, D("10000")),
            PlanItem(SNP, HALF, 0, D("66.00")),
        ),
        threshold=D("0.02"),
        fx_rate=D("1392.0"),
        free_krw=D("0"),
        free_usd=D("0"),
        fees=FEES,
    )
    plan = plan_per_currency(inp)
    # Within the won: 2,000,000 : 1,000,000 against 60 : 40 -> sell 20 KOSPI, buy 19 TIGER.
    assert plan.fx is None
    assert [(o.instrument.ticker, o.qty) for o in plan.sells] == [("069500", 20)]
    assert [(o.instrument.ticker, o.qty) for o in plan.buys] == [("102110", 19)]
    assert plan.reason is PlanReason.DRIFT
    assert not any(o.instrument.ticker == "SPYM" for o in (*plan.sells, *plan.buys))


def test_a_drift_within_one_currency_shows_on_the_status() -> None:
    targets = {"a": D("0.3"), "b": D("0.2"), "c": HALF}
    currencies = {"a": Currency.KRW, "b": Currency.KRW, "c": Currency.USD}
    off = {"a": D("2000000"), "b": D("1000000"), "c": D("0")}
    on = {"a": D("1800000"), "b": D("1200000"), "c": D("0")}
    assert drift_within_currencies(off, {}, targets, currencies, D("0.02"))
    assert not drift_within_currencies(on, {}, targets, currencies, D("0.02"))
    # One instrument per currency (지수 반반): never, whatever the mix.
    two = {"a": HALF, "c": HALF}
    assert not drift_within_currencies({"a": D(1), "c": D(0)}, {}, two, currencies, D("0.02"))


# ── the suggestion ───────────────────────────────────────────────────────────────────────


def test_the_suggestion_shows_beyond_the_band_and_hides_within() -> None:
    rate, step = D("1392.0"), D("1000")
    # 52.0% is the band's edge: not beyond it (a drift must be strictly over, 인계).
    assert suggest(CurrencyMix(D("5200000"), D("4800000"), HALF), D("0.02"), rate, step) is None
    found = suggest(CurrencyMix(D("5210000"), D("4790000"), HALF), D("0.02"), rate, step)
    assert found is not None
    assert (found.direction, found.krw, found.usd) == (
        FxDirection.KRW_TO_USD,
        D("210000"),
        D("150.86"),
    )
    # Won only: half of it.
    found = suggest(CurrencyMix(D("10000000"), D("0"), HALF), D("0.02"), rate, step)
    assert found is not None
    assert (found.krw, found.usd) == (D("5000000"), D("3591.95"))


def test_too_many_dollars_suggest_converting_back() -> None:
    found = suggest(CurrencyMix(D("3000000"), D("7000000"), HALF), D("0.02"), D("1392.0"), D(1000))
    assert found is not None
    assert (found.direction, found.krw, found.usd) == (
        FxDirection.USD_TO_KRW,
        D("2000000"),
        D("1436.78"),
    )


@pytest.mark.parametrize(
    ("kr", "us"),
    [("0", "0"), ("1000", "0")],  # nothing, or an amount that rounds to 0 on the step
)
def test_no_suggestion_without_an_amount(kr: str, us: str) -> None:
    assert suggest(CurrencyMix(D(kr), D(us), HALF), D("0.02"), D("1392.0"), D(10000)) is None


def test_the_suggestion_never_blocks_a_status_above_it() -> None:
    assert rule_status(StatusFlags(fx_suggest=True)) is RuleStatus.FX_SUGGEST
    for flags in (
        StatusFlags(fx_suggest=True, scheduled=True),
        StatusFlags(fx_suggest=True, in_progress=True),
        StatusFlags(fx_suggest=True, withdraw_wait=True),
        StatusFlags(fx_suggest=True, quote_wait=True),
    ):
        assert rule_status(flags) is not RuleStatus.FX_SUGGEST


# ── the new money set apart ──────────────────────────────────────────────────────────────


def test_todays_money_is_set_apart_before_a_pending_buy_claims_it() -> None:
    cash = {Currency.KRW: D("3078512"), Currency.USD: D("1500.00")}
    claims = [Claim(Currency.USD, D("1387.39"), {"US:SPYM": D(1)})]
    parts = partition(
        cash,
        [],
        claims,
        {Currency.KRW: D("3000000")},
        held={Currency.KRW: D("3000000"), Currency.USD: D("63.22")},
    )
    got = {(p.currency, p.purpose, p.instrument_id): p.amount for p in parts}
    assert got == {
        (Currency.KRW, Purpose.NEW, None): D("3000000"),
        (Currency.KRW, Purpose.SUB_SHARE, None): D("78512"),
        (Currency.USD, Purpose.BUY_WAIT, "US:SPYM"): D("1436.78"),
        (Currency.USD, Purpose.NEW, None): D("63.22"),
    }
    # Without `held` (paper) a pending buy claims all of its currency's free cash, as always.
    paper = partition(cash, [], claims, {Currency.KRW: D("3000000")})
    assert {(p.currency, p.purpose): p.amount for p in paper}[
        (Currency.USD, Purpose.BUY_WAIT)
    ] == D("1500.00")
