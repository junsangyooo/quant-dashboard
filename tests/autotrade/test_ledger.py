"""Ledger arithmetic (pure): cash flows, trades, conversions, cost basis."""

from __future__ import annotations

from decimal import Decimal

import pytest

from autotrade.domain.instruments import Currency
from autotrade.domain.ledger import (
    CashFlowKind,
    FxFill,
    LedgerError,
    LedgerState,
    TradeFill,
    apply_cash_flow,
    apply_fx,
    apply_trade,
    same_to_the_won,
)
from autotrade.domain.money import round_cents, round_won
from autotrade.domain.planner import FxDirection, Side

D = Decimal
K = "KR:069500"
S = "US:SPYM"


def start(amount: str = "10000000") -> LedgerState:
    return apply_cash_flow(LedgerState(), CashFlowKind.START, D(amount))


def test_first_day_cash_path() -> None:
    # §4: buy 156 x 32,000 (fee 748), convert 4,967,000 at 1,392.0, buy 54 x $66.00 (fee $3.56).
    s = apply_trade(start(), TradeFill(K, Currency.KRW, Side.BUY, 156, D("32000"), D("748")))
    assert s.cash_of(Currency.KRW) == D("5007252")
    s = apply_fx(s, FxFill(FxDirection.KRW_TO_USD, D("4967000"), D("3568.24"), D("1392.0")))
    assert s.cash_of(Currency.KRW) == D("40252")  # '원화 현금 · 1주 미만 대기 40,252'
    assert s.cash_of(Currency.USD) == D("3568.24")
    s = apply_trade(s, TradeFill(S, Currency.USD, Side.BUY, 54, D("66.00"), D("3.56"), D("1392.0")))
    assert s.cash_of(Currency.USD) == D("0.68")
    pos = s.positions[S]
    assert pos.qty == 54
    assert pos.cost_native == D("3567.56")
    assert pos.cost_krw == round_won(D("3567.56") * D("1392.0"))
    assert s.fees_krw == D("748") + D("4956")  # $3.56 x 1,392.0 = 4,955.52 -> 4,956
    assert s.contributions_krw == D("10000000")


def test_average_prices_of_the_example_table() -> None:
    # §1.1: S&P 500 ETF 44 x $66.00 + $2.90 (7/1) and 2 x $63.00 + $0.13 (8/21) -> avg $65.94.
    s = apply_cash_flow(LedgerState(), CashFlowKind.START, D("10000000"))
    s = apply_fx(s, FxFill(FxDirection.KRW_TO_USD, D("4768000"), D("3425.28"), D("1392.0")))
    s = apply_trade(s, TradeFill(S, Currency.USD, Side.BUY, 44, D("66.00"), D("2.90"), D("1392.0")))
    s = apply_trade(s, TradeFill(S, Currency.USD, Side.BUY, 2, D("63.00"), D("0.13"), D("1389.6")))
    assert round_cents(s.positions[S].avg_price) == D("65.94")
    # KOSPI200 ETF 125 x 32,000 + 600, then two sells of 5: the average stays 32,004.8 -> 32,005.
    s = apply_trade(s, TradeFill(K, Currency.KRW, Side.BUY, 125, D("32000"), D("600")))
    s = apply_trade(s, TradeFill(K, Currency.KRW, Side.SELL, 5, D("33800"), D("25")))
    s = apply_trade(s, TradeFill(K, Currency.KRW, Side.SELL, 5, D("36380"), D("27")))
    assert round_won(s.positions[K].avg_price) == D("32005")
    assert s.positions[K].qty == 115


def test_selling_everything_removes_the_position_and_books_the_gain() -> None:
    s = apply_trade(start(), TradeFill(K, Currency.KRW, Side.BUY, 10, D("1000"), D("1")))
    s = apply_trade(s, TradeFill(K, Currency.KRW, Side.SELL, 10, D("1100"), D("1")))
    assert K not in s.positions
    assert s.realized_krw == D("10999") - D("10001")
    assert s.cash_of(Currency.KRW) == D("10000000") - D("10001") + D("10999")


def test_dollar_sell_books_in_won() -> None:
    s = apply_fx(start(), FxFill(FxDirection.KRW_TO_USD, D("1400000"), D("1000.00"), D("1400.0")))
    s = apply_trade(s, TradeFill(S, Currency.USD, Side.BUY, 10, D("50.00"), D("0.50"), D("1400.0")))
    s = apply_trade(s, TradeFill(S, Currency.USD, Side.SELL, 4, D("60.00"), D("0.24"), D("1300.0")))
    assert s.positions[S].qty == 6
    # proceeds $239.76 at 1,300 = 311,688; cost removed 4/10 of $500.50 x 1,400 = 280,280
    assert s.realized_krw == D("311688") - D("280280")
    assert s.positions[S].cost_krw == D("420420")
    s = apply_fx(s, FxFill(FxDirection.USD_TO_KRW, D("100.00"), D("130000"), D("1300.0")))
    assert s.cash_of(Currency.USD) == D("1000.00") - D("500.50") + D("239.76") - D("100.00")


def test_cash_flows() -> None:
    s = start("1000")
    s = apply_cash_flow(s, CashFlowKind.DEPOSIT, D("500"))
    s = apply_cash_flow(s, CashFlowKind.DIVIDEND, D("16243"))
    s = apply_cash_flow(s, CashFlowKind.WITHDRAWAL, D("300"))
    assert s.contributions_krw == D("1200")
    assert s.income_krw == D("16243")
    assert s.cash_of(Currency.KRW) == D("17443")
    s = apply_cash_flow(s, CashFlowKind.DIVIDEND, D("1.00"), Currency.USD, D("1400.0"))
    assert s.income_krw == D("17643")
    assert s.cash_of(Currency.USD) == D("1.00")


@pytest.mark.parametrize(
    "change",
    [
        lambda s: apply_cash_flow(s, CashFlowKind.WITHDRAWAL, D("2000")),
        lambda s: apply_cash_flow(s, CashFlowKind.DEPOSIT, D("0")),
        lambda s: apply_cash_flow(s, CashFlowKind.DEPOSIT, D("1"), Currency.USD),
        lambda s: apply_trade(s, TradeFill(K, Currency.KRW, Side.BUY, 1, D("5000"), D("0"))),
        lambda s: apply_trade(s, TradeFill(K, Currency.KRW, Side.SELL, 1, D("100"), D("0"))),
        lambda s: apply_trade(s, TradeFill(K, Currency.KRW, Side.BUY, 0, D("100"), D("0"))),
        lambda s: apply_trade(s, TradeFill(S, Currency.USD, Side.BUY, 1, D("1"), D("0"))),
        lambda s: apply_trade(s, TradeFill(K, Currency.KRW, Side.FX, 1, D("1"), D("0"))),
        lambda s: apply_fx(s, FxFill(FxDirection.KRW_TO_USD, D("0"), D("1"), D("1"))),
        lambda s: apply_fx(s, FxFill(FxDirection.USD_TO_KRW, D("1"), D("1400"), D("1400"))),
    ],
)
def test_impossible_changes_are_refused(change: object) -> None:
    with pytest.raises(LedgerError):
        change(start("1000"))  # type: ignore[operator]


def test_same_to_the_won_reports_differences() -> None:
    a = apply_trade(start(), TradeFill(K, Currency.KRW, Side.BUY, 1, D("1000"), D("0")))
    b = apply_trade(start(), TradeFill(K, Currency.KRW, Side.BUY, 2, D("1000"), D("0")))
    assert same_to_the_won(a, a) == []
    problems = same_to_the_won(a, b)
    assert any("cash KRW" in p for p in problems)
    assert any("qty" in p for p in problems)
    assert same_to_the_won(a, start())[-1].endswith("present in only one state")
