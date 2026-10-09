"""Valuation in won.

A position is worth qty x price, converted at the rate and rounded half-up to the won once per
row (예시-값표 §1.1: 46 x $62.40 x 1,382.4 = 3,968,040.96 -> 3,968,041). Dollar cash is valued
the same way ($126.96 x 1,382.4 -> 175,510).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from autotrade.domain.instruments import Currency
from autotrade.domain.money import ZERO, round_won, usd_in_krw


def position_value_krw(qty: int, price: Decimal, currency: Currency, fx_rate: Decimal) -> Decimal:
    gross = price * qty
    if currency is Currency.KRW:
        return round_won(gross)
    return round_won(gross * fx_rate)


def unit_price_krw(price: Decimal, currency: Currency, fx_rate: Decimal) -> Decimal:
    """Exact won price of one share (not rounded), used for share arithmetic."""
    if currency is Currency.KRW:
        return price
    return price * fx_rate


def cash_value_krw(amounts: Mapping[Currency, Decimal], fx_rate: Decimal) -> Decimal:
    total = ZERO
    for currency, amount in amounts.items():
        total += amount if currency is Currency.KRW else usd_in_krw(amount, fx_rate)
    return total


@dataclass(frozen=True)
class ValuedPosition:
    instrument_id: str
    qty: int
    price: Decimal
    currency: Currency
    value_krw: Decimal


def total_krw(positions: Iterable[ValuedPosition], cash_krw: Decimal) -> Decimal:
    return sum((p.value_krw for p in positions), cash_krw)
