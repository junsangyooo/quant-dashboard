"""The untouched baseline (§1.2) and the rule status priority (인계 12)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from autotrade.domain import baseline
from autotrade.domain.instruments import Currency
from autotrade.domain.status import RuleStatus, StatusFlags, rule_status
from autotrade.domain.weights import pct1

D = Decimal
K = "KR:069500"
S = "US:SPYM"
TARGETS = {K: D("0.5"), S: D("0.5")}


def test_baseline_1007() -> None:
    # 7/1: 5,000,000 won each at 32,000 and $66.00 x 1,392.0 = 91,872; 10/07: 36,250 and 86,262.
    start = {
        K: baseline.krw_unit_price(D("32000"), Currency.KRW, D("1392.0")),
        S: baseline.krw_unit_price(D("66.00"), Currency.USD, D("1392.0")),
    }
    assert start[S] == D("91872")
    units = baseline.units_for_amount(D("10000000"), TARGETS, start)
    now = {
        K: baseline.krw_unit_price(D("36250"), Currency.KRW, D("1382.4")),
        S: baseline.krw_unit_price(D("62.40"), Currency.USD, D("1382.4")),
    }
    assert now[S] == D("86262")  # 'S&P 500 ETF 원화가 91,872 -> 86,262원'
    value = baseline.value_krw(units, now)
    assert value == D("10358747")  # '손대지 않았을 때 +3.59% (10,358,747원)'
    assert pct1(value / D("10000000") - 1) == D("3.6")
    assert (value / D("10000000") - 1).quantize(D("0.0001")) == D("0.0359")


def test_baseline_deposits_and_withdrawals_move_units_by_value() -> None:
    prices = {K: D("40000"), S: D("80000")}
    units = baseline.units_for_amount(D("1000000"), TARGETS, prices)
    more = baseline.add_units(units, baseline.units_for_amount(D("200000"), TARGETS, prices))
    assert baseline.value_krw(more, prices) == D("1200000")
    less = baseline.add_units(more, baseline.units_for_amount(D("200000"), TARGETS, prices), -1)
    assert baseline.value_krw(less, prices) == D("1000000")
    with pytest.raises(baseline.BaselineError):
        baseline.add_units(units, baseline.units_for_amount(D("5000000"), TARGETS, prices), -1)
    with pytest.raises(baseline.BaselineError):
        baseline.units_for_amount(D("1"), TARGETS, {K: D("1")})
    with pytest.raises(baseline.BaselineError):
        baseline.value_krw(units, {K: D("1")})


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (
            StatusFlags(quote_wait=True, partial_failed=True, in_progress=True),
            RuleStatus.QUOTE_WAIT,
        ),
        (StatusFlags(partial_failed=True, in_progress=True), RuleStatus.PARTIAL_FAILED),
        (StatusFlags(in_progress=True, holiday=True), RuleStatus.IN_PROGRESS),
        (StatusFlags(holiday=True, scheduled=True), RuleStatus.HOLIDAY),
        (StatusFlags(scheduled=True), RuleStatus.SCHEDULED),
        (StatusFlags(), RuleStatus.IN_RANGE),
    ],
)
def test_status_priority(flags: StatusFlags, expected: RuleStatus) -> None:
    assert rule_status(flags) is expected
