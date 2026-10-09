"""Market data values shared by the sources, the store and the paper executor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class Bar:
    """One daily bar. session_date is the exchange's local date (ET for US)."""

    instrument_id: str
    session_date: date
    open: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal
    source: str


@dataclass(frozen=True)
class DividendInfo:
    """A cash dividend as a source reports it: per share, before tax, in the instrument's
    currency. ex_date is exchange-local; pay_date is None when the source does not give it."""

    instrument_id: str
    ex_date: date
    per_share: Decimal
    pay_date: date | None
    source: str


@dataclass(frozen=True)
class FxQuote:
    """KRW per USD at a moment, on the 0.1 won grid."""

    rate: Decimal
    as_of: datetime
    source: str


PAIR_USDKRW = "USDKRW"
