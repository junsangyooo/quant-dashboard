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
class FxQuote:
    """KRW per USD at a moment, on the 0.1 won grid."""

    rate: Decimal
    as_of: datetime
    source: str


PAIR_USDKRW = "USDKRW"
