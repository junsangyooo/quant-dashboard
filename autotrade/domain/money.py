"""Decimal money and the rounding rules.

Units: won are whole won, dollars are cents, the KRW/USD rate is 0.1 won.

The rules were reverse-engineered from Vault 7-웹기획/예시-값표.md and are locked by
tests/autotrade/test_money.py:

- Korean fee (0.015%) is floored to the won. §4 first day: 4,992,000 x 0.015% = 748.8 -> 748,
  which is the only value that leaves the table's 40,252 won of leftover cash; the 7/1 fee total
  5,667 likewise needs 832,500 x 0.015% = 124.875 -> 124. (ops notes says fees are "rounded";
  the table says floor for won.)
- US fee (0.1%) is rounded half-up to the cent: $126.00 -> $0.126 -> $0.13 (8/21), and
  $124.80 -> $0.1248 -> $0.12 (10/7).
- KRW -> USD conversion floors to the cent: 175,000 / 1,389.6 = 125.935... -> $125.93.
- USD -> KRW conversion floors to the won (the bank keeps the fraction).
- Valuing dollars in won rounds half-up: $0.13 x 1,389.6 = 180.648 -> 181 won.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from autotrade.domain.instruments import Currency

WON = Decimal("1")
CENT = Decimal("0.01")
RATE_STEP = Decimal("0.1")
ZERO = Decimal("0")


def dec(value: Decimal | int | str | float) -> Decimal:
    """Exact Decimal from a number or its text. Floats go through repr to avoid binary noise."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(repr(value))
    return Decimal(value)


def round_half_up(x: Decimal, step: Decimal) -> Decimal:
    """Round to a decimal step such as Decimal('0.1'), half-up."""
    return x.quantize(step, rounding=ROUND_HALF_UP)


def round_won(x: Decimal) -> Decimal:
    return x.quantize(WON, rounding=ROUND_HALF_UP)


def floor_won(x: Decimal) -> Decimal:
    return x.quantize(WON, rounding=ROUND_FLOOR)


def round_cents(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def floor_cents(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_FLOOR)


def ceil_cents(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_CEILING)


def round_rate(x: Decimal) -> Decimal:
    return x.quantize(RATE_STEP, rounding=ROUND_HALF_UP)


def ceil_to_step(x: Decimal, step: Decimal) -> Decimal:
    """Smallest multiple of step that is >= x (step > 0)."""
    if step <= 0:
        raise ValueError("step must be positive")
    return (x / step).to_integral_value(rounding=ROUND_CEILING) * step


def floor_div(x: Decimal, unit: Decimal) -> int:
    """floor(x / unit) as an int; 0 when x <= 0. unit must be positive."""
    if unit <= 0:
        raise ValueError("unit must be positive")
    if x <= 0:
        return 0
    return int((x / unit).to_integral_value(rounding=ROUND_FLOOR))


@dataclass(frozen=True)
class FeeRates:
    """Commission rates as fractions (0.00015 = 0.015%). FX spread is inside the rate.

    kr_stock_sell_tax: the Korean securities transaction tax on a stock sale (ETFs are exempt),
    0.20% for 2026 (KOSPI 0.05% + 농특세 0.15%; KOSDAQ 0.20%) as the owner's notes read it; it
    only touches the AI rule's Korean stocks. Check before live trading (open question).
    """

    kr: Decimal = Decimal("0.00015")
    us: Decimal = Decimal("0.001")
    kr_stock_sell_tax: Decimal = Decimal("0.0020")

    def rate_for(self, currency: Currency) -> Decimal:
        return self.kr if currency is Currency.KRW else self.us


def kr_fee(gross_krw: Decimal, rate: Decimal) -> Decimal:
    """Korean commission, floored to the won."""
    return floor_won(gross_krw * rate)


def us_fee(gross_usd: Decimal, rate: Decimal) -> Decimal:
    """US commission, rounded half-up to the cent."""
    return round_cents(gross_usd * rate)


def trade_fee(currency: Currency, gross: Decimal, fees: FeeRates) -> Decimal:
    if currency is Currency.KRW:
        return kr_fee(gross, fees.kr)
    return us_fee(gross, fees.us)


def krw_to_usd(krw: Decimal, rate: Decimal) -> Decimal:
    """Dollars received for won, floored to the cent."""
    return floor_cents(krw / rate)


def usd_to_krw(usd: Decimal, rate: Decimal) -> Decimal:
    """Won received for dollars, floored to the won."""
    return floor_won(usd * rate)


def usd_in_krw(usd: Decimal, rate: Decimal) -> Decimal:
    """Valuation of a dollar amount in won, rounded half-up."""
    return round_won(usd * rate)


def normalize_price(currency: Currency, raw: Decimal) -> Decimal:
    """Quote prices on their tick: whole won for KRX, cents for US ETFs."""
    if currency is Currency.KRW:
        return round_won(raw)
    return round_cents(raw)


def quantize_amount(currency: Currency, amount: Decimal) -> Decimal:
    """Round a cash amount to its unit (won or cent), half-up."""
    if currency is Currency.KRW:
        return round_won(amount)
    return round_cents(amount)
