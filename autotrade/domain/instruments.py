"""Instruments: market, currency and kind."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Market(str, Enum):
    KR = "KR"
    US = "US"


class Currency(str, Enum):
    KRW = "KRW"
    USD = "USD"


class Kind(str, Enum):
    ETF = "etf"
    STOCK = "stock"
    COIN = "coin"


MARKET_CURRENCY: dict[Market, Currency] = {Market.KR: Currency.KRW, Market.US: Currency.USD}


@dataclass(frozen=True)
class Instrument:
    """A tradable thing. instrument_id follows the 'KR:069500' / 'US:SPYM' convention."""

    instrument_id: str
    market: Market
    currency: Currency
    kind: Kind
    ticker: str
    name: str
    yahoo_symbol: str

    def __post_init__(self) -> None:
        if MARKET_CURRENCY[self.market] is not self.currency:
            raise ValueError(f"{self.instrument_id}: {self.market} trades in {self.currency}")
        if self.instrument_id != f"{self.market.value}:{self.ticker}":
            raise ValueError(f"{self.instrument_id}: id must be '<market>:<ticker>'")


def kr_etf(ticker: str, name: str) -> Instrument:
    return Instrument(
        instrument_id=f"KR:{ticker}",
        market=Market.KR,
        currency=Currency.KRW,
        kind=Kind.ETF,
        ticker=ticker,
        name=name,
        yahoo_symbol=f"{ticker}.KS",
    )


def us_etf(ticker: str, name: str) -> Instrument:
    return Instrument(
        instrument_id=f"US:{ticker}",
        market=Market.US,
        currency=Currency.USD,
        kind=Kind.ETF,
        ticker=ticker,
        name=name,
        yahoo_symbol=ticker,
    )
