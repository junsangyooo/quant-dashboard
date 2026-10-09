"""Order planning: the example-table rebalances (예시-값표 §1.4 8/21·10/7, §4, §1.6, §2.1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from autotrade.domain.instruments import kr_etf, us_etf
from autotrade.domain.money import FeeRates
from autotrade.domain.planner import (
    FxDirection,
    PlanInput,
    PlanItem,
    PlanReason,
    Side,
    StageKind,
    fx_krw_needed,
    plan_rule,
)
from autotrade.domain.weights import pct1

D = Decimal
KOSPI = kr_etf("069500", "KOSPI200 ETF")
SNP = us_etf("SPYM", "S&P 500 ETF")
HALF = D("0.5")
FEES = FeeRates()


def plan_for(
    kospi_qty: int,
    kospi_price: str,
    snp_qty: int,
    snp_price: str,
    rate: str,
    free_krw: str,
    free_usd: str,
    snp_wait_krw: str = "0",
) -> PlanInput:
    return PlanInput(
        items=(
            PlanItem(KOSPI, HALF, kospi_qty, D(kospi_price)),
            PlanItem(SNP, HALF, snp_qty, D(snp_price), D(snp_wait_krw)),
        ),
        threshold=D("0.02"),
        fx_rate=D(rate),
        free_krw=D(free_krw),
        free_usd=D(free_usd),
        fees=FEES,
    )


def test_0821_rebalance() -> None:
    # Holdings before 8/21 (two-rule world): KOSPI200 ETF 125, S&P 500 ETF 44, KRW 34,044, $1.86.
    # The check used 8/20 closes: KOSPI200 ETF 33,790 (table generator) and the US close, which
    # the table does not print. The FX amount 175,000 needs a close in ($62.55, $62.90]; $62.90.
    plan = plan_rule(plan_for(125, "33790", 44, "62.90", "1389.6", "34044", "1.86"))
    assert plan.reason is PlanReason.DRIFT
    assert pct1(plan.report.weights[KOSPI.instrument_id]) == D("52.3")  # '전 52.3 : 47.7'
    assert pct1(plan.report.max_drift) == D("2.3")  # '2.3%p 벗어남'
    assert pct1(plan.report.over_by) == D("0.3")  # '0.3%p 넘음'
    [sell] = plan.sells
    assert (sell.stage, sell.side, sell.instrument, sell.qty) == (
        StageKind.SELL,
        Side.SELL,
        KOSPI,
        5,
    )
    assert plan.fx is not None
    assert plan.fx.direction is FxDirection.KRW_TO_USD
    assert plan.fx.from_amount == D("175000")
    assert plan.fx.est_to_amount == D("125.93")
    assert plan.fx.funds == (SNP.instrument_id,)
    [buy] = plan.buys
    assert (buy.instrument, buy.qty) == (SNP, 2)
    assert pct1(plan.weights_after[KOSPI.instrument_id]) == D("50.2")  # '후 50.2 : 49.8'
    assert pct1(plan.weights_after[SNP.instrument_id]) == D("49.8")


def test_1007_rebalance() -> None:
    # 10/07 08:30 check: 10/06 closes KOSPI200 ETF 36,360, S&P 500 ETF $62.40, rate 1,380.6.
    plan = plan_rule(plan_for(120, "36360", 46, "62.40", "1380.6", "47675", "1.66"))
    assert pct1(plan.report.weights[KOSPI.instrument_id]) == D("52.4")  # §1.3 08:30
    assert pct1(plan.report.max_drift) == D("2.4")
    assert pct1(plan.report.over_by) == D("0.4")
    assert plan.report.max_instrument == KOSPI.instrument_id
    # Free cash 47,675 + $1.66 cannot buy a share at a 50% split: kept aside, not invested.
    assert plan.investable_cash_krw == 0
    assert [(o.instrument, o.qty) for o in plan.sells] == [(KOSPI, 5)]
    assert plan.fx is not None
    assert plan.fx.from_amount == D("173000")
    assert plan.fx.est_to_amount == D("125.30")
    [buy] = plan.buys
    assert (buy.instrument, buy.qty, buy.est_price) == (SNP, 2, D("62.40"))
    assert buy.est_gross == D("124.80")  # '약 $124.80'
    assert buy.est_fee == D("0.12")  # '+수수료 $0.12'


def test_first_day_buys_from_the_start_amount() -> None:
    # §4: start 10,000,000 won, closes KOSPI200 ETF 32,000 and $66.00, rate 1,392.0.
    plan = plan_rule(plan_for(0, "32000", 0, "66.00", "1392.0", "10000000", "0"))
    assert plan.reason is PlanReason.NEW_CASH
    assert plan.sells == ()
    kospi, snp = plan.buys
    assert (kospi.instrument, kospi.qty, kospi.est_gross, kospi.est_fee) == (
        KOSPI,
        156,
        D("4992000"),
        D("748"),
    )
    assert (snp.instrument, snp.qty, snp.est_gross) == (SNP, 54, D("3564.00"))  # '약 $3,564.00'
    assert plan.fx is not None
    assert plan.fx.from_amount == D("4967000")
    assert plan.fx.est_to_amount == D("3568.24")


@pytest.mark.parametrize(
    ("usd_cost", "rate", "krw"),
    [
        # §1.6 live preview: S&P 46 x $62.40 + NVDA 3 x $176.40 = $3,399.60
        (D("3399.60") * D("1.001"), "1382.4", "4705000"),
        # §2.1 live first check: S&P 45 x $63.34 + NVDA 3 x $178.20 = $3,384.90
        (D("3384.90") * D("1.001"), "1389.9", "4710000"),
        # §4 and 10/7 through the same formula
        (D("3564.00") * D("1.001"), "1392.0", "4967000"),
        (D("124.80") * D("1.001"), "1380.6", "173000"),
    ],
)
def test_fx_amount_rounds_the_need_up_to_1000_won(usd_cost: Decimal, rate: str, krw: str) -> None:
    assert fx_krw_needed(usd_cost, D(rate), D("1000")) == D(krw)


def test_drift_at_exactly_the_threshold_does_not_trade() -> None:
    # 52,000 : 48,000 is exactly +2.0%p: '넘으면' means strictly more.
    plan = plan_rule(plan_for(52, "1000", 48, "1.00", "1000.0", "0", "0"))
    assert plan.report.max_drift == D("0.02")
    assert not plan.report.exceeded
    assert not plan.has_orders
    assert plan.order_count == 0


def test_small_free_cash_is_kept_aside_when_in_range() -> None:
    plan = plan_rule(plan_for(110, "36250", 46, "62.40", "1382.4", "60000", "2.00"))
    assert not plan.report.exceeded
    assert plan.investable_cash_krw == 0
    assert not plan.has_orders


def test_deposit_with_drift_buys_both_sides_without_selling() -> None:
    # 53 : 47 drift plus a large new deposit: the deposit absorbs the drift, nothing is sold.
    plan = plan_rule(plan_for(100, "53000", 47, "100.00", "1000.0", "2000000", "0"))
    assert plan.report.exceeded
    assert plan.investable_cash_krw == D("2000000")
    assert plan.sells == ()
    bought = {o.instrument.instrument_id: o.qty for o in plan.buys}
    # base 12,000,000 -> 6,000,000 each: KOSPI +700,000 / 53,008 = 13 shares,
    # S&P +1,300,000 / 100,100 = 12 shares.
    assert bought == {KOSPI.instrument_id: 13, SNP.instrument_id: 12}


def test_us_overweight_sells_us_converts_back_and_buys_korea() -> None:
    plan = plan_rule(plan_for(100, "30000", 40, "66.00", "1390.0", "0", "0"))
    # Two instruments drift by the same amount; the rule's first one is reported.
    assert plan.report.max_instrument == KOSPI.instrument_id
    assert pct1(plan.report.drifts[SNP.instrument_id]) == D("5.0")
    assert [(o.instrument, o.qty) for o in plan.sells] == [(SNP, 3)]
    assert plan.fx is not None
    assert plan.fx.direction is FxDirection.USD_TO_KRW
    assert plan.fx.funds == (KOSPI.instrument_id,)
    # 3 x $66.00 - $0.20 fee = $197.80 pays for at most 9 shares of 30,000 won (271,000 won).
    [buy] = plan.buys
    assert (buy.instrument, buy.qty) == (KOSPI, 9)
    assert plan.fx.from_amount == D("194.97")
    assert plan.fx.est_to_amount == D("271008")


def test_free_cash_below_one_share_per_target_is_not_invested() -> None:
    # 100,000 won: half is 50,000, below one share of either (60,000): kept aside.
    plan = plan_rule(plan_for(0, "60000", 0, "60.00", "1000.0", "100000", "0"))
    assert plan.investable_cash_krw == 0
    assert not plan.has_orders


def test_buys_are_cut_to_the_cash() -> None:
    # 121,000 won qualifies (60,500 per side buys one share each), but one share of each plus
    # the 1,000-won FX rounding needs 60,009 + 61,000 = 121,009: one buy is cut.
    plan = plan_rule(plan_for(0, "60000", 0, "60.00", "1000.0", "121000", "0"))
    assert plan.investable_cash_krw == D("121000")
    assert [(o.instrument, o.qty) for o in plan.buys] == [(SNP, 1)]
    assert plan.fx is not None
    assert plan.fx.from_amount == D("61000")


def test_exceeded_without_a_whole_share_sends_nothing() -> None:
    # 3 : 2 shares of a 1,000,000 won instrument: 60% vs 40%, but half a share fixes nothing.
    plan = plan_rule(plan_for(3, "1000000", 2, "1000.00", "1000.0", "0", "0"))
    assert plan.report.exceeded
    assert not plan.has_orders


def test_korean_only_rule_needs_no_conversion() -> None:
    other = kr_etf("360750", "TIGER S&P500")
    plan = plan_rule(
        PlanInput(
            items=(
                PlanItem(KOSPI, HALF, 60, D("10000")),
                PlanItem(other, HALF, 40, D("10000")),
            ),
            threshold=D("0.02"),
            fx_rate=D("1380.0"),
            free_krw=D("0"),
            free_usd=D("0"),
            fees=FEES,
        )
    )
    assert plan.fx is None
    assert [(o.instrument.instrument_id, o.qty) for o in plan.sells] == [(KOSPI.instrument_id, 10)]
    assert [(o.instrument.instrument_id, o.qty) for o in plan.buys] == [(other.instrument_id, 9)]


def test_targets_must_sum_to_one_and_be_unique() -> None:
    with pytest.raises(ValueError, match="sum to 1"):
        PlanInput(
            items=(PlanItem(KOSPI, D("0.6"), 0, D("1")), PlanItem(SNP, D("0.6"), 0, D("1"))),
            threshold=D("0.02"),
            fx_rate=D("1"),
            free_krw=D("0"),
            free_usd=D("0"),
            fees=FEES,
        )
    with pytest.raises(ValueError, match="duplicate"):
        PlanInput(
            items=(PlanItem(KOSPI, HALF, 0, D("1")), PlanItem(KOSPI, HALF, 0, D("1"))),
            threshold=D("0.02"),
            fx_rate=D("1"),
            free_krw=D("0"),
            free_usd=D("0"),
            fees=FEES,
        )


def test_fx_direction_currencies() -> None:
    assert FxDirection.KRW_TO_USD.source.value == "KRW"
    assert FxDirection.KRW_TO_USD.target.value == "USD"
    assert FxDirection.USD_TO_KRW.source.value == "USD"
    assert FxDirection.USD_TO_KRW.target.value == "KRW"
