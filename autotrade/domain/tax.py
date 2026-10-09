"""Tax numbers for US stocks (D36, PHASE2.md §7 '미국 종목과 세금').

Korea taxes a resident's realized foreign stock gains of a calendar year at 22% above a
2,500,000 won deduction, losses of the same year offsetting gains, across the whole account (the
long-term rule's US ETF included). The code puts these numbers into the AI packets; the AI
decides with them whether to sell, trim or switch a US stock. They are estimates: the won values
use the rates the ledger booked (the conversion of the plan, or the rate at the fill), and the
tax office uses the base rates of the settlement days.

  realized_krw        this year's realized foreign gains, net of losses (the whole ledger)
  deduction_left_krw  what is left of the 2,500,000 won deduction
  unrealized_krw      a position's gain in won: value now minus what it cost in won
  tax_if_sold_krw     how much this year's tax changes if the position is sold now (negative:
                      selling at a loss saves tax already due)
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from autotrade.domain.money import ZERO, floor_won, round_won


@dataclass(frozen=True)
class SoldLot:
    """A realized sale of foreign shares, in won."""

    year: int
    proceeds_krw: Decimal  # after fees
    cost_krw: Decimal  # what the shares cost in won (fees included)

    @property
    def gain_krw(self) -> Decimal:
        return self.proceeds_krw - self.cost_krw


@dataclass(frozen=True)
class TaxNumbers:
    year: int
    realized_krw: Decimal
    deduction_krw: Decimal
    deduction_left_krw: Decimal
    unrealized_krw: Decimal
    tax_if_sold_krw: Decimal


def tax_due(gains_krw: Decimal, rate: Decimal, deduction: Decimal) -> Decimal:
    """The year's tax on net realized foreign gains (floored to the won)."""
    return floor_won(max(ZERO, gains_krw - deduction) * rate)


def realized_in(lots: Iterable[SoldLot], year: int) -> Decimal:
    return sum((lot.gain_krw for lot in lots if lot.year == year), ZERO)


def numbers(
    year: int,
    realized_krw: Decimal,
    unrealized_krw: Decimal,
    rate: Decimal,
    deduction: Decimal,
) -> TaxNumbers:
    now = tax_due(realized_krw, rate, deduction)
    after = tax_due(realized_krw + unrealized_krw, rate, deduction)
    return TaxNumbers(
        year=year,
        realized_krw=round_won(realized_krw),
        deduction_krw=deduction,
        deduction_left_krw=round_won(max(ZERO, deduction - max(ZERO, realized_krw))),
        unrealized_krw=round_won(unrealized_krw),
        tax_if_sold_krw=after - now,
    )
