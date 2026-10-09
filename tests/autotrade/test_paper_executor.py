"""Paper executor (fills at the session open) and the live-order guard."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from autotrade.broker.base import (
    Failed,
    FailureReason,
    FxFilled,
    FxRequest,
    LiveOrdersBlockedError,
    TradeFilled,
    TradeRequest,
    Waiting,
    executor_for,
    live_orders_allowed,
)
from autotrade.broker.paper import PaperExecutor, affordable_qty
from autotrade.domain.instruments import Currency, kr_etf, us_etf
from autotrade.domain.money import FeeRates
from autotrade.domain.planner import FxDirection, Side
from autotrade.market.types import Bar, FxQuote

from .helpers import kst

D = Decimal
KOSPI = kr_etf("069500", "KOSPI200 ETF")
SNP = us_etf("SPYM", "S&P 500 ETF")


class Reader:
    def __init__(self) -> None:
        self.bars: dict[tuple[str, date], Bar] = {}
        self.quotes: list[FxQuote] = []

    def bar(self, instrument_id: str, session_date: date) -> Bar | None:
        return self.bars.get((instrument_id, session_date))

    def fx_at(self, at: datetime) -> FxQuote | None:
        found = [q for q in self.quotes if q.as_of <= at]
        return found[-1] if found else None


def executor(reader: Reader) -> PaperExecutor:
    return PaperExecutor(reader, FeeRates(), timedelta(minutes=60))


def trade(
    side: Side, qty: int, cash: str = "1000000000", held: int = 0, **kw: object
) -> TradeRequest:
    base: dict[str, object] = {
        "order_id": 1,
        "instrument": KOSPI,
        "side": side,
        "qty": qty,
        "session_date": date(2026, 10, 7),
        "due_at": kst("2026-10-07 09:05"),
        "available_cash": D(cash),
        "held_qty": held,
        "fetch_error": None,
        "deadline_passed": False,
    }
    base.update(kw)
    return TradeRequest(**base)  # type: ignore[arg-type]


def test_trades_fill_at_the_open() -> None:
    reader = Reader()
    reader.bars[(KOSPI.instrument_id, date(2026, 10, 7))] = Bar(
        KOSPI.instrument_id, date(2026, 10, 7), D("36380"), None, None, D("36250"), "pykrx"
    )
    out = executor(reader).trade(trade(Side.SELL, 5, held=120))
    assert out == TradeFilled(5, D("36380"), D("181900"), D("27"), "pykrx:open:2026-10-07")
    # Selling more than held sells what is there; a buy is cut to the cash.
    assert isinstance(executor(reader).trade(trade(Side.SELL, 5, held=3)), TradeFilled)
    cut = executor(reader).trade(trade(Side.BUY, 5, cash="100000"))
    assert isinstance(cut, TradeFilled)
    assert cut.qty == 2
    assert executor(reader).trade(trade(Side.BUY, 1, cash="100")) == Failed(
        FailureReason.OTHER, "cash does not cover one share at the open"
    )
    assert executor(reader).trade(trade(Side.SELL, 1, held=0)) == Failed(
        FailureReason.OTHER, "nothing to sell"
    )
    assert executor(reader).trade(trade(Side.FX, 1)) == Failed(
        FailureReason.OTHER, "not a trade: fx"
    )


def test_missing_open_waits_fails_on_error_or_after_the_close() -> None:
    reader = Reader()
    assert executor(reader).trade(trade(Side.BUY, 1)) == Waiting(
        "open of 2026-10-07 not published yet"
    )
    failed = executor(reader).trade(trade(Side.BUY, 1, fetch_error="SourceError: timeout"))
    assert failed == Failed(FailureReason.NO_QUOTE, "SourceError: timeout")
    assert failed.retryable
    late = executor(reader).trade(trade(Side.BUY, 1, deadline_passed=True))
    assert isinstance(late, Failed)
    assert late.reason is FailureReason.NO_QUOTE


def fx(amount: str, available: str, **kw: object) -> FxRequest:
    base: dict[str, object] = {
        "order_id": 2,
        "direction": FxDirection.KRW_TO_USD,
        "amount": D(amount),
        "due_at": kst("2026-10-07 09:10"),
        "available": D(available),
        "fetch_error": None,
        "deadline_passed": False,
    }
    base.update(kw)
    return FxRequest(**base)  # type: ignore[arg-type]


def test_conversion_uses_the_quote_at_the_stage_time() -> None:
    reader = Reader()
    reader.quotes.append(FxQuote(D("1380.6"), kst("2026-10-07 09:10"), "yfinance"))
    out = executor(reader).fx(fx("173000", "229548"))
    assert isinstance(out, FxFilled)
    assert (out.from_amount, out.to_amount, out.rate) == (D("173000"), D("125.30"), D("1380.6"))
    back = executor(reader).fx(fx("100.00", "126.96", direction=FxDirection.USD_TO_KRW))
    assert isinstance(back, FxFilled)
    assert back.to_amount == D("138060")
    capped = executor(reader).fx(fx("173000", "100000"))
    assert isinstance(capped, FxFilled)
    assert capped.from_amount == D("100000")
    assert executor(reader).fx(fx("173000", "0")) == Failed(
        FailureReason.OTHER, "no cash to convert"
    )
    assert executor(reader).fx(fx("1", "1")) == Failed(
        FailureReason.OTHER, "amount too small to convert"
    )


def test_conversion_without_a_recent_quote() -> None:
    reader = Reader()
    reader.quotes.append(FxQuote(D("1380.6"), kst("2026-10-07 07:00"), "yfinance"))  # 2h10m old
    assert executor(reader).fx(fx("1000", "1000")) == Waiting("rate not available yet")
    assert executor(reader).fx(fx("1000", "1000", fetch_error="down")) == Failed(
        FailureReason.NO_QUOTE, "down"
    )
    late = executor(reader).fx(fx("1000", "1000", deadline_passed=True))
    assert isinstance(late, Failed)


def test_affordable_qty() -> None:
    assert affordable_qty(5, D("36380"), D("181926"), Currency.KRW, FeeRates()) == 4
    assert affordable_qty(5, D("36380"), D("181927"), Currency.KRW, FeeRates()) == 5
    assert affordable_qty(2, D("62.40"), D("124.92"), Currency.USD, FeeRates()) == 2
    assert affordable_qty(2, D("62.40"), D("124.91"), Currency.USD, FeeRates()) == 1


def test_live_orders_need_both_switches() -> None:
    assert live_orders_allowed("live", {"AUTOTRADE_LIVE_ORDERS": "1"})
    assert not live_orders_allowed("live", {})
    assert not live_orders_allowed("paper", {"AUTOTRADE_LIVE_ORDERS": "1"})
    assert not live_orders_allowed("live")  # the test environment never has the switch


def test_only_the_paper_ledger_has_an_executor() -> None:
    paper = executor(Reader())
    assert executor_for("paper", paper) is paper
    with pytest.raises(LiveOrdersBlockedError):
        executor_for("live", paper)


def test_the_korean_transaction_tax_is_charged_on_stock_sales_only() -> None:
    """2026: KOSPI 0.05% + 농특세 0.15%, KOSDAQ 0.20% on a stock sale; domestic ETFs are exempt."""
    from autotrade.domain.instruments import Instrument, Kind, Market

    stock = Instrument(
        "KR:042660", Market.KR, Currency.KRW, Kind.STOCK, "042660", "한화오션", "042660.KS"
    )
    us_stock = Instrument(
        "US:AVGO", Market.US, Currency.USD, Kind.STOCK, "AVGO", "Broadcom", "AVGO"
    )
    reader = Reader()
    day = date(2026, 10, 7)
    for inst, price in ((KOSPI, "33000"), (stock, "33000"), (us_stock, "330.00")):
        reader.bars[(inst.instrument_id, day)] = Bar(
            inst.instrument_id, day, D(price), D(price), D(price), D(price), "t"
        )
    ex = executor(reader)
    etf_sale = ex.trade(trade(Side.SELL, 10, held=10))
    assert isinstance(etf_sale, TradeFilled)
    assert etf_sale.fee == D(49)  # 330,000 x 0.015% = 49.5 -> 49, and no tax: an ETF
    stock_sale = ex.trade(trade(Side.SELL, 10, held=10, instrument=stock))
    assert isinstance(stock_sale, TradeFilled)
    assert stock_sale.fee == D(49) + D(660)  # + 330,000 x 0.20%
    stock_buy = ex.trade(trade(Side.BUY, 10, instrument=stock))
    assert isinstance(stock_buy, TradeFilled)
    assert stock_buy.fee == D(49)  # a buy pays no tax
    us_sale = ex.trade(trade(Side.SELL, 10, held=10, instrument=us_stock))
    assert isinstance(us_sale, TradeFilled)
    assert us_sale.fee == D("3.30")  # 0.1% only: the Korean tax is for Korean stocks
    assert FeeRates().kr_stock_sell_tax == D("0.0020")
