"""Paper executor: fills at the session's open from the stored daily bar (ops notes 모의 체결).

- A trade fills at the open of its session. If the open is not stored, the stage fails when the
  download failed ('시세 응답 없음') or the session is over, and waits otherwise (the open of a
  session that just started may not be published yet).
- A buy is cut to what the cash can pay (plan price = prior close, fill = next open).
- A conversion fills at the newest stored rate at or before the stage time, if it is recent.
- Fees: Korea 0.015% (floored to the won), US 0.1% (rounded to the cent); FX spread is ignored.
  Selling a Korean stock (the AI rule's picks) also pays the securities transaction tax, kept in
  the fill's fee (FeeRates.kr_stock_sell_tax).
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from autotrade.broker.base import (
    Failed,
    FailureReason,
    FxFilled,
    FxRequest,
    Outcome,
    TradeFilled,
    TradeRequest,
    Waiting,
)
from autotrade.db import repo
from autotrade.domain.instruments import Currency, Kind
from autotrade.domain.money import FeeRates, floor_won, krw_to_usd, trade_fee, usd_to_krw
from autotrade.domain.planner import FxDirection, Side
from autotrade.market.freshness import weekday_age
from autotrade.market.types import Bar, FxQuote


class MarketReader(Protocol):
    def bar(self, instrument_id: str, session_date: date) -> Bar | None: ...

    def fx_at(self, at: datetime) -> FxQuote | None: ...


class DbMarketReader:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def bar(self, instrument_id: str, session_date: date) -> Bar | None:
        return repo.get_bar(self.conn, instrument_id, session_date)

    def fx_at(self, at: datetime) -> FxQuote | None:
        return repo.fx_at(self.conn, at)


def affordable_qty(
    wanted: int, price: Decimal, cash: Decimal, currency: Currency, fees: FeeRates
) -> int:
    """Largest qty <= wanted whose gross + fee fits in cash."""
    qty = wanted
    while qty > 0:
        gross = price * qty
        if gross + trade_fee(currency, gross, fees) <= cash:
            return qty
        qty -= 1
    return 0


class PaperExecutor:
    name = "paper"

    def __init__(self, reader: MarketReader, fees: FeeRates, fx_fill_max_age: timedelta) -> None:
        self.reader = reader
        self.fees = fees
        self.fx_fill_max_age = fx_fill_max_age

    def trade(self, req: TradeRequest) -> Outcome:
        bar = self.reader.bar(req.instrument.instrument_id, req.session_date)
        if bar is None or bar.open is None or bar.open <= 0:
            if req.fetch_error:
                return Failed(FailureReason.NO_QUOTE, req.fetch_error)
            if req.deadline_passed:
                return Failed(FailureReason.NO_QUOTE, f"no open price for {req.session_date}")
            return Waiting(f"open of {req.session_date} not published yet")
        price = bar.open
        currency = req.instrument.currency
        if req.side is Side.BUY:
            qty = affordable_qty(req.qty, price, req.available_cash, currency, self.fees)
            if qty == 0:
                return Failed(FailureReason.OTHER, "cash does not cover one share at the open")
        elif req.side is Side.SELL:
            qty = min(req.qty, req.held_qty)
            if qty == 0:
                return Failed(FailureReason.OTHER, "nothing to sell")
        else:
            return Failed(FailureReason.OTHER, f"not a trade: {req.side.value}")
        gross = price * qty
        fee = trade_fee(currency, gross, self.fees)
        if req.side is Side.SELL and currency is Currency.KRW and req.instrument.kind is Kind.STOCK:
            fee += floor_won(gross * self.fees.kr_stock_sell_tax)
        return TradeFilled(
            qty, price, gross, fee, f"{bar.source}:open:{req.session_date.isoformat()}"
        )

    def fx(self, req: FxRequest) -> Outcome:
        quote = self.reader.fx_at(req.due_at)
        usable = quote is not None and weekday_age(quote.as_of, req.due_at) <= self.fx_fill_max_age
        if quote is None or not usable:
            if req.fetch_error:
                return Failed(FailureReason.NO_QUOTE, req.fetch_error)
            if req.deadline_passed:
                return Failed(FailureReason.NO_QUOTE, f"no rate near {req.due_at.isoformat()}")
            return Waiting("rate not available yet")
        amount = min(req.amount, req.available)
        if amount <= 0:
            return Failed(FailureReason.OTHER, "no cash to convert")
        if req.direction is FxDirection.KRW_TO_USD:
            received = krw_to_usd(amount, quote.rate)
        else:
            received = usd_to_krw(amount, quote.rate)
        if received <= 0:
            return Failed(FailureReason.OTHER, "amount too small to convert")
        return FxFilled(amount, received, quote.rate, f"{quote.source}:{quote.as_of.isoformat()}")
