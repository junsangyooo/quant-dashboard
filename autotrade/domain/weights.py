"""In-rule weights, drift and the threshold decision (인계 1·2·3, ops notes step 4-5).

weight_i = (value_i + cash waiting to buy i) / sum over the rule, in won. Cash that is a
sub-share leftover or waits for a withdrawal belongs to no rule and is not counted.
A rebalance is due when any instrument's |drift| is strictly greater than the threshold
(8/21: 2.3%p > 2%p, '0.3%p 넘음').
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from autotrade.domain.money import ZERO, round_half_up

PCT1 = Decimal("0.1")


@dataclass(frozen=True)
class DriftReport:
    weights: dict[str, Decimal]  # fractions (0.524 = 52.4%)
    drifts: dict[str, Decimal]  # weight - target, fractions
    rule_value_krw: Decimal
    threshold: Decimal
    max_instrument: str | None  # the instrument furthest from its target ('가장 많이 벗어난 종목')
    max_drift: Decimal  # signed drift of max_instrument

    @property
    def exceeded(self) -> bool:
        return abs(self.max_drift) > self.threshold

    @property
    def over_by(self) -> Decimal:
        """How far the largest drift is past the threshold (0.4%p at 10/07 08:30)."""
        return max(ZERO, abs(self.max_drift) - self.threshold)

    @property
    def to_threshold(self) -> Decimal:
        """Room left before a rebalance ('리밸런싱까지 1.8%p'); 0 once exceeded."""
        return max(ZERO, self.threshold - abs(self.max_drift))


def in_rule_weights(
    values_krw: Mapping[str, Decimal], buy_wait_krw: Mapping[str, Decimal]
) -> tuple[dict[str, Decimal], Decimal]:
    """Weights per instrument and the rule's value. Empty weights when the rule holds nothing."""
    held = {i: values_krw[i] + buy_wait_krw.get(i, ZERO) for i in values_krw}
    total = sum(held.values(), ZERO)
    if total <= 0:
        return {}, total
    return {i: v / total for i, v in held.items()}, total


def drift_report(
    values_krw: Mapping[str, Decimal],
    buy_wait_krw: Mapping[str, Decimal],
    targets: Mapping[str, Decimal],
    threshold: Decimal,
) -> DriftReport:
    weights, total = in_rule_weights(values_krw, buy_wait_krw)
    if not weights:
        return DriftReport({}, {}, total, threshold, None, ZERO)
    drifts = {i: weights[i] - targets[i] for i in targets}
    # Largest |drift| wins; ties go to the first instrument in the rule's order.
    max_id = None
    max_drift = ZERO
    for instrument_id in targets:
        d = drifts[instrument_id]
        if max_id is None or abs(d) > abs(max_drift):
            max_id, max_drift = instrument_id, d
    return DriftReport(weights, drifts, total, threshold, max_id, max_drift)


def pct1(fraction: Decimal) -> Decimal:
    """Fraction -> percent with one decimal, half-up (display helper: 0.52401 -> 52.4)."""
    return round_half_up(fraction * 100, PCT1)
