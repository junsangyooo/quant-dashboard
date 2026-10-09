"""In-rule weights, drift and valuation (예시-값표 §1.1, §1.3, §2.3, §4)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from autotrade.domain.instruments import Currency, Instrument, Kind, Market
from autotrade.domain.valuation import (
    ValuedPosition,
    cash_value_krw,
    position_value_krw,
    total_krw,
    unit_price_krw,
)
from autotrade.domain.weights import drift_report, in_rule_weights, pct1

D = Decimal
K = "KR:069500"
S = "US:SPYM"
TARGETS = {K: D("0.5"), S: D("0.5")}
TWO = D("0.02")


def test_position_values_round_once_per_row() -> None:
    assert position_value_krw(115, D("36250"), Currency.KRW, D("1382.4")) == D("4168750")
    assert position_value_krw(46, D("62.40"), Currency.USD, D("1382.4")) == D("3968041")
    assert position_value_krw(3, D("176.40"), Currency.USD, D("1382.4")) == D("731566")  # NVDA
    assert position_value_krw(14, D("56300"), Currency.KRW, D("1382.4")) == D("788200")
    assert unit_price_krw(D("62.40"), Currency.USD, D("1382.4")) == D("86261.760")
    assert unit_price_krw(D("36250"), Currency.KRW, D("1382.4")) == D("36250")


def test_cash_value_and_total() -> None:
    cash = cash_value_krw({Currency.KRW: D("56548"), Currency.USD: D("126.96")}, D("1382.4"))
    assert cash == D("56548") + D("175510")
    rows = [ValuedPosition(K, 115, D("36250"), Currency.KRW, D("4168750"))]
    assert total_krw(rows, cash) == D("4168750") + D("232058")


def test_check_weights_1007_0830() -> None:
    # §1.3: '10/07 08:30 확인 때 값: KOSPI200 ETF 52.4% -> +2.4%p, 0.4%p 넘음 -> 리밸런싱'.
    values = {
        K: position_value_krw(120, D("36360"), Currency.KRW, D("1380.6")),
        S: position_value_krw(46, D("62.40"), Currency.USD, D("1380.6")),
    }
    report = drift_report(values, {}, TARGETS, TWO)
    assert pct1(report.weights[K]) == D("52.4")
    assert pct1(report.drifts[K]) == D("2.4")
    assert report.exceeded
    assert pct1(report.over_by) == D("0.4")
    assert report.to_threshold == 0


def test_weights_1007_1600_include_the_buy_wait_dollars() -> None:
    # §1.3 '지금(16:00)': KOSPI200 ETF 50.2%, S&P 500 ETF (매수 대기 포함) 49.8%,
    # 리밸런싱까지 1.8%p.
    values = {K: D("4168750"), S: D("3968041")}
    report = drift_report(values, {S: D("175510")}, TARGETS, TWO)
    assert pct1(report.weights[K]) == D("50.2")
    assert pct1(report.weights[S]) == D("49.8")
    assert pct1(report.max_drift) == D("0.2")
    assert pct1(report.to_threshold) == D("1.8")
    assert not report.exceeded


def test_first_day_weights_and_rule_share() -> None:
    # §4 at 7/1 16:00: KOSPI200 ETF 4,999,800, dollars waiting $3,568.24 = 4,965,206,
    # leftover 40,252.
    report = drift_report({K: D("4999800"), S: D("0")}, {S: D("4965206")}, TARGETS, TWO)
    assert pct1(report.weights[K]) == D("50.2")
    assert pct1(report.weights[S]) == D("49.8")
    assert pct1(report.rule_value_krw / D("10005258")) == D("99.6")  # '자산의 99.6%'


def test_withdraw_wait_is_excluded_from_the_rule() -> None:
    # §2.3: KOSPI200 ETF 104 x 36,250, S&P 500 ETF 45 x $62.40 x 1,382.4 -> 49.3% : 50.7%.
    values = {
        K: position_value_krw(104, D("36250"), Currency.KRW, D("1382.4")),
        S: position_value_krw(45, D("62.40"), Currency.USD, D("1382.4")),
    }
    assert values[S] == D("3881779")
    report = drift_report(values, {}, TARGETS, TWO)
    assert pct1(report.weights[K]) == D("49.3")
    assert pct1(report.weights[S]) == D("50.7")
    assert pct1(report.to_threshold) == D("1.3")


def test_empty_rule_has_no_weights() -> None:
    weights, total = in_rule_weights({K: D("0"), S: D("0")}, {})
    assert weights == {}
    assert total == 0
    report = drift_report({K: D("0"), S: D("0")}, {}, TARGETS, TWO)
    assert report.max_instrument is None
    assert not report.exceeded


def test_instrument_ids_follow_the_market_convention() -> None:
    with pytest.raises(ValueError, match="trades in"):
        Instrument("KR:069500", Market.KR, Currency.USD, Kind.ETF, "069500", "x", "069500.KS")
    with pytest.raises(ValueError, match="id must be"):
        Instrument("KOSPI", Market.KR, Currency.KRW, Kind.ETF, "069500", "x", "069500.KS")
