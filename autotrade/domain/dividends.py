"""Cash dividends after the tax withheld at the source (pure functions).

- Korean ETF distributions: 15.4% withheld (income tax 14% + local tax 1.4%).
- US ETF dividends: 15% withheld in the US (Korea-US treaty rate), paid in dollars.

Rounding: the gross is rounded to the unit (won, or cent) and the tax rounded up to it, so the
net is never overstated. 예시-값표 §1.4 9/30: 120 shares x 160 won = 19,200, tax 2,956.8 -> 2,957,
net 16,243 ('배당 16,243원 (세후, 120주 × 160원 − 세금)').

Who gets a dividend: the shares held before the ex-date session. A buy that fills on the ex-date
or later does not get it; a sale on the ex-date or later does not lose it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Protocol

from autotrade.domain.instruments import Currency
from autotrade.domain.money import CENT, WON


@dataclass(frozen=True)
class DividendAmounts:
    gross: Decimal
    tax: Decimal
    net: Decimal


def after_tax(
    per_share: Decimal, qty: Decimal | int, currency: Currency, tax_rate: Decimal
) -> DividendAmounts:
    """Gross, tax and net of one dividend in the instrument's currency. qty may be fractional
    (the untouched baseline holds fractional units)."""
    if per_share < 0 or tax_rate < 0 or tax_rate >= 1:
        raise ValueError(f"bad dividend: per share {per_share}, tax {tax_rate}")
    unit = WON if currency is Currency.KRW else CENT
    gross = (per_share * Decimal(qty)).quantize(unit, rounding=ROUND_HALF_UP)
    tax = (gross * tax_rate).quantize(unit, rounding=ROUND_CEILING)
    return DividendAmounts(gross, tax, gross - tax)


class TradingDays(Protocol):
    def next_trading_day(self, d: date) -> date: ...


def estimated_pay_date(ex_date: date, calendar: TradingDays, lag_days: int) -> date:
    """The pay date when the source gives none: `lag_days` trading days after the ex-date.

    Korean ETFs: the record date is the trading day after the ex-date and the cash comes two
    trading days after the record date (KODEX 200: ex 7/30, record 7/31, paid 8/4), so 3.
    The SPDR Portfolio S&P 500 ETF pays two trading days after its ex-date, so 2 for the US.
    """
    if lag_days < 0:
        raise ValueError("lag_days must be >= 0")
    d = ex_date
    for _ in range(lag_days):
        d = calendar.next_trading_day(d)
    return d


@dataclass(frozen=True)
class HeldFill:
    """A filled trade of one instrument, by its session date (exchange-local)."""

    session_date: date
    qty: int  # positive for a buy, negative for a sale


def qty_before_ex_date(qty_now: int, fills: list[HeldFill], ex_date: date) -> int:
    """Shares held before the ex-date session: today's quantity with every trade from the
    ex-date on undone. Works for ledgers that did not build their positions through fills."""
    after = sum(f.qty for f in fills if f.session_date >= ex_date)
    return max(qty_now - after, 0)
