"""The rule's money in each currency, and the conversion that would bring it back to the targets
(D47, 2026-10-13).

The live ledger runs on the money as the owner deposited it: won buys the rule's Korean
instruments, dollars its US ones, and nothing is converted (Toss's API cannot, PHASE3.md 1.1).
So the mix between 한국 and 미국 is the owner's: he converts in the Toss app whenever he wants.
When the mix is further from the rule's targets than the rule's band, the screens show how much
would bring it back ('약 5,000,000원을 달러로 바꾸면 50:50'). It is information only: never a
to-do, it blocks nothing, and it is gone once the mix is back within the band.

What counts as a currency's money: the rule's holdings of that currency at their won value,
and that currency's cash except what waits for a withdrawal (it leaves the account). Cash waiting
for the next check, below one share or just deposited, counts: it will buy that currency's
instruments.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from autotrade.domain.instruments import Currency
from autotrade.domain.money import CENT, ZERO
from autotrade.domain.planner import FxDirection
from autotrade.domain.weights import drift_report


@dataclass(frozen=True)
class CurrencyMix:
    kr_krw: Decimal  # 한국: won holdings and won cash, in won
    us_krw: Decimal  # 미국: dollar holdings and dollar cash, in won at the rate
    target_kr: Decimal  # the rule's target share of its won instruments (0.5 for 지수 반반)

    @property
    def total(self) -> Decimal:
        return self.kr_krw + self.us_krw

    @property
    def kr_share(self) -> Decimal:
        """한국's share of the rule's money (0 when it has none)."""
        return self.kr_krw / self.total if self.total > 0 else ZERO


@dataclass(frozen=True)
class FxSuggestion:
    direction: FxDirection  # KRW_TO_USD: 한국 is over its target
    krw: Decimal  # the won to convert (or that the dollars bring), on the won step
    usd: Decimal  # the dollars it buys (or to convert), to the cent at the rate
    rate: Decimal
    mix: CurrencyMix


def suggest(
    mix: CurrencyMix, threshold: Decimal, rate: Decimal, step: Decimal
) -> FxSuggestion | None:
    """The conversion that brings the mix to the targets, when it is off by more than the band
    (strictly, like a drift: 52.0% against 50% is in). None within the band, for an empty rule,
    or when the amount rounds to nothing on the step."""
    if mix.total <= 0 or rate <= 0 or step <= 0:
        return None
    off = mix.kr_share - mix.target_kr
    if abs(off) <= threshold:
        return None
    move = abs(mix.kr_krw - mix.target_kr * mix.total)
    krw = (move / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step
    if krw <= 0:
        return None
    usd = (krw / rate).quantize(CENT, rounding=ROUND_HALF_UP)
    direction = FxDirection.KRW_TO_USD if off > 0 else FxDirection.USD_TO_KRW
    return FxSuggestion(direction, krw, usd, rate, mix)


def drift_within_currencies(
    values_krw: Mapping[str, Decimal],
    buy_wait_krw: Mapping[str, Decimal],
    targets: Mapping[str, Decimal],
    currencies: Mapping[str, Currency],
    threshold: Decimal,
) -> bool:
    """Whether an instrument is off its share of its own currency's money by more than the band:
    the only drift the live ledger trades back (D47, planner.plan_per_currency). It takes two
    instruments in one currency; '지수 반반' has one in each, so never."""
    for currency in Currency:
        ids = [i for i in targets if currencies[i] is currency]
        share = sum((targets[i] for i in ids), ZERO)
        if len(ids) < 2 or share <= 0:
            continue
        report = drift_report(
            {i: values_krw[i] for i in ids},
            buy_wait_krw,
            {i: targets[i] / share for i in ids},
            threshold,
        )
        if report.exceeded:
            return True
    return False
