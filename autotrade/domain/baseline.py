"""'손대지 않았을 때' — the untouched baseline (D-baseline-hold, 인계 4·14).

On the start day the start amount is split by the rule's targets and 'bought' at the start-day
prices, in fractional units, with no fees, and then never traded. Deposits buy more units at that
day's prices; withdrawals sell units in the same 50:50 proportion by value.

Each leg is valued with the won price of one share rounded to the won, and each leg's value is
rounded to the won, as the table shows it: §1.2 at 10/07,
5,000,000 x 36,250/32,000 = 5,664,062.5 -> 5,664,063 and 5,000,000 x 86,262/91,872 =
4,694,683.9 -> 4,694,684, together 10,358,747 (+3.59%), where 91,872 = $66.00 x 1,392.0 and
86,262 = round($62.40 x 1,382.4). (Rounding the sum instead gives 10,358,746.)

On the start day itself the US open is not known yet at the 16:00 valuation, so the baseline
equals the ledger's own value ('첫날은 같은 매수', §4).
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal

from autotrade.domain.instruments import Currency
from autotrade.domain.money import ZERO, round_won


class BaselineError(ValueError):
    pass


def krw_unit_price(price: Decimal, currency: Currency, fx_rate: Decimal) -> Decimal:
    """Won price of one share, rounded to the won."""
    if currency is Currency.KRW:
        return round_won(price)
    return round_won(price * fx_rate)


def units_for_amount(
    amount_krw: Decimal, targets: Mapping[str, Decimal], krw_prices: Mapping[str, Decimal]
) -> dict[str, Decimal]:
    units: dict[str, Decimal] = {}
    for iid, weight in targets.items():
        price = krw_prices.get(iid)
        if price is None or price <= 0:
            raise BaselineError(f"no price for {iid}")
        units[iid] = amount_krw * weight / price
    return units


def add_units(
    a: Mapping[str, Decimal], b: Mapping[str, Decimal], sign: int = 1
) -> dict[str, Decimal]:
    out = dict(a)
    for iid, u in b.items():
        out[iid] = out.get(iid, ZERO) + sign * u
        if out[iid] < 0:
            raise BaselineError(f"baseline units for {iid} would go negative")
    return out


def value_krw(units: Mapping[str, Decimal], krw_prices: Mapping[str, Decimal]) -> Decimal:
    """Sum of the legs, each rounded half-up to the won (as positions are, one row at a time)."""
    total = ZERO
    for iid, u in units.items():
        price = krw_prices.get(iid)
        if price is None:
            raise BaselineError(f"no price for {iid}")
        total += round_won(u * price)
    return total
