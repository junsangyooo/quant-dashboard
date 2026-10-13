"""Order planning to target weights (ops notes step 5-6, 인계 3·4).

Inputs are the holdings, the latest closes (the plan prices), the 08:30 rate and the free cash.
The plan is whole shares; anything below one share stays aside as cash.

How the numbers are chosen (each rule reproduces 예시-값표, see tests/autotrade/test_planner.py):

1. Weights and drift are measured on what the rule holds: positions + cash waiting to buy them.
2. Free cash (new cash, dividends, sub-share leftovers) joins the target base only when it could
   buy at least one share of some instrument at that instrument's target share
   ("1주 미만은 모아 둔다"). 10/07: 49,967 won free -> half is 24,983 < one share -> kept aside.
3. When a drift exceeds the threshold, over-weight instruments sell floor(excess / price) shares
   and under-weight ones buy floor(deficit / (price x (1 + fee))) shares
   (8/21: excess 5.59 shares -> sell 5, deficit 2.16 -> buy 2; 10/07: 5.50 -> 5, 2.32 -> 2).
   Without a drift, only buys are planned, and only from free cash that qualifies (start, deposits).
4. The FX converts what the other-currency buys need, qty x price x (1 + fee), at the plan rate,
   rounded up to the next 1,000 won. Dollars already in the account are not netted: they stay as
   a buffer against the gap between the plan price (prior close) and the fill (next open).
   §4: 54 x $66.00 x 1.001 x 1,392.0 = 4,966,049 -> 4,967,000. 10/07: 2 x $62.40 x 1.001 x
   1,380.6 = 172,471 -> 173,000. §1.6: ($2,870.40 + $529.20) x 1.001 x 1,382.4 -> 4,705,000.
5. If the cash cannot cover the buys, buys are cut one share at a time, starting with the
   instrument that would end furthest above its target.

That is the paper ledger: its conversions are virtual and it measures the strategy. The live
ledger plans with `plan_per_currency` (D47, 2026-10-13): Toss converts nothing for an order
(autotrade/PHASE3.md 1.1), so the live ledger runs on the money as the owner deposited it. Each
currency's cash goes to the rule's instruments of that currency; nothing is converted and no
market is sold to pay for the other. The owner moves money between the currencies in the Toss
app (autotrade/domain/currency_mix.py says how much would bring the mix back to the targets).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import Enum

from autotrade.domain.instruments import Currency, Instrument, Market
from autotrade.domain.money import (
    ZERO,
    FeeRates,
    ceil_cents,
    ceil_to_step,
    floor_div,
    krw_to_usd,
    trade_fee,
    usd_in_krw,
    usd_to_krw,
)
from autotrade.domain.valuation import position_value_krw, unit_price_krw
from autotrade.domain.weights import DriftReport, drift_report, in_rule_weights

ONE = Decimal("1")


class StageKind(str, Enum):
    SELL = "sell"
    FX = "fx"
    BUY = "buy"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"
    FX = "fx"


class FxDirection(str, Enum):
    KRW_TO_USD = "krw_to_usd"
    USD_TO_KRW = "usd_to_krw"

    @property
    def source(self) -> Currency:
        return Currency.KRW if self is FxDirection.KRW_TO_USD else Currency.USD

    @property
    def target(self) -> Currency:
        return Currency.USD if self is FxDirection.KRW_TO_USD else Currency.KRW


class PlanReason(str, Enum):
    DRIFT = "drift"  # a weight left the band
    NEW_CASH = "new_cash"  # free cash big enough to buy shares (start, deposit)


@dataclass(frozen=True)
class PlanItem:
    instrument: Instrument
    target: Decimal  # in-rule weight, fraction
    qty: int  # shares held
    price: Decimal  # plan price in the instrument's currency (latest close)
    buy_wait_krw: Decimal = ZERO  # cash already waiting to buy this instrument
    # The most one share of a buy may take, fee included, in the instrument's currency. The live
    # ledger sets it to what its send divides the cash by (the limit price over the plan price,
    # on the tick, plus the fee: autotrade/broker/toss.py buy_unit), so a planned share is one
    # the send can pay for at that price. None (paper): the plan price plus the fee.
    buy_unit: Decimal | None = None

    def buy_cost(self, qty: int, fees: FeeRates) -> Decimal:
        """What `qty` shares of a buy take at most, in the instrument's currency."""
        if self.buy_unit is not None:
            return self.buy_unit * qty
        return self.price * qty * (ONE + fees.rate_for(self.instrument.currency))


@dataclass(frozen=True)
class PlanInput:
    items: tuple[PlanItem, ...]
    threshold: Decimal
    fx_rate: Decimal  # KRW per USD at the check
    free_krw: Decimal
    free_usd: Decimal
    fees: FeeRates
    fx_step_krw: Decimal = Decimal("1000")
    # False: no conversion is planned (plan_per_currency, D47). Each currency's buys are cut to
    # that currency's cash instead.
    convert: bool = True

    def __post_init__(self) -> None:
        total = sum((it.target for it in self.items), ZERO)
        if total != ONE:
            raise ValueError(f"targets must sum to 1, got {total}")
        ids = [it.instrument.instrument_id for it in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate instrument in rule")


@dataclass(frozen=True)
class TradeOrder:
    stage: StageKind
    side: Side
    instrument: Instrument
    qty: int
    est_price: Decimal
    est_gross: Decimal  # qty x price, instrument currency
    est_fee: Decimal  # instrument currency

    @property
    def market(self) -> Market:
        return self.instrument.market

    @property
    def currency(self) -> Currency:
        return self.instrument.currency


@dataclass(frozen=True)
class FxOrder:
    direction: FxDirection
    from_amount: Decimal  # won for KRW->USD, dollars for USD->KRW
    est_rate: Decimal
    est_to_amount: Decimal
    funds: tuple[str, ...]  # instruments whose buys this conversion pays for


@dataclass(frozen=True)
class Plan:
    report: DriftReport
    free_cash_krw: Decimal
    investable_cash_krw: Decimal
    reason: PlanReason | None
    sells: tuple[TradeOrder, ...] = ()
    fx: FxOrder | None = None
    buys: tuple[TradeOrder, ...] = ()
    weights_after: dict[str, Decimal] = field(default_factory=dict)

    @property
    def has_orders(self) -> bool:
        return bool(self.sells or self.buys or self.fx)

    @property
    def order_count(self) -> int:
        return len(self.sells) + len(self.buys) + (1 if self.fx else 0)


def fx_krw_needed(usd_cost: Decimal, rate: Decimal, step: Decimal) -> Decimal:
    """Won to convert for dollar buys costing usd_cost (fees included), rounded up to `step`.

    §1.6: ($2,870.40 + $529.20) x 1.001 x 1,382.4 = 4,704,307 -> 4,705,000.
    """
    return ceil_to_step(usd_cost * rate, step)


def _trade(stage: StageKind, item: PlanItem, qty: int, fees: FeeRates) -> TradeOrder:
    gross = item.price * qty
    return TradeOrder(
        stage=stage,
        side=Side.SELL if stage is StageKind.SELL else Side.BUY,
        instrument=item.instrument,
        qty=qty,
        est_price=item.price,
        est_gross=gross,
        est_fee=trade_fee(item.instrument.currency, gross, fees),
    )


@dataclass(frozen=True)
class _Cash:
    """Cash still missing per currency after the planned trades and conversion (<= 0 is fine)."""

    krw_short: Decimal
    usd_short: Decimal
    fx: FxOrder | None


def _cash_need(
    items: Mapping[str, PlanItem],
    sells: Mapping[str, int],
    buys: Mapping[str, int],
    inp: PlanInput,
) -> _Cash:
    rate = inp.fx_rate
    krw_short = ZERO
    usd_short = ZERO
    for iid, n in buys.items():
        it = items[iid]
        need = it.buy_cost(n, inp.fees)
        if it.instrument.currency is Currency.KRW:
            krw_short += need
        else:
            usd_short += need
    for iid, n in sells.items():
        it = items[iid]
        gross = it.price * n
        net = gross - trade_fee(it.instrument.currency, gross, inp.fees)
        if it.instrument.currency is Currency.KRW:
            krw_short -= net
        else:
            usd_short -= net

    fx: FxOrder | None = None
    if not inp.convert:
        return _Cash(krw_short, usd_short, None)
    if usd_short > 0:
        from_krw = fx_krw_needed(usd_short, rate, inp.fx_step_krw)
        to_usd = krw_to_usd(from_krw, rate)
        funds = tuple(i for i in buys if items[i].instrument.currency is Currency.USD)
        fx = FxOrder(FxDirection.KRW_TO_USD, from_krw, rate, to_usd, funds)
        krw_short += from_krw
        usd_short -= to_usd
    elif krw_short > 0 and usd_short < 0:
        # Dollars from US sells pay for Korean buys: convert what the buys need.
        to_krw_target = ceil_to_step(krw_short, inp.fx_step_krw)
        from_usd = ceil_cents(to_krw_target / rate)
        to_krw = usd_to_krw(from_usd, rate)
        funds = tuple(i for i in buys if items[i].instrument.currency is Currency.KRW)
        fx = FxOrder(FxDirection.USD_TO_KRW, from_usd, rate, to_krw, funds)
        usd_short += from_usd
        krw_short -= to_krw
    return _Cash(krw_short, usd_short, fx)


def _held_after(
    items: Mapping[str, PlanItem],
    sells: Mapping[str, int],
    buys: Mapping[str, int],
    rate: Decimal,
) -> dict[str, Decimal]:
    out: dict[str, Decimal] = {}
    for iid, it in items.items():
        qty = it.qty - sells.get(iid, 0) + buys.get(iid, 0)
        out[iid] = position_value_krw(qty, it.price, it.instrument.currency, rate)
        if iid not in buys:
            out[iid] += it.buy_wait_krw
    return out


def _fit_budget(
    items: Mapping[str, PlanItem],
    sells: Mapping[str, int],
    buys: dict[str, int],
    inp: PlanInput,
) -> tuple[dict[str, int], _Cash]:
    order = list(items)
    while True:
        cash = _cash_need(items, sells, buys, inp)
        if (cash.krw_short <= inp.free_krw and cash.usd_short <= inp.free_usd) or not buys:
            return buys, cash
        after = _held_after(items, sells, buys, inp.fx_rate)
        total = sum(after.values(), ZERO)
        # Cut the buy that would end furthest above its target; ties keep the rule's order.
        victim = max(
            buys,
            key=lambda i: (after[i] - items[i].target * total, -order.index(i)),
        )
        buys[victim] -= 1
        if buys[victim] == 0:
            del buys[victim]


def plan_rule(inp: PlanInput) -> Plan:
    items = {it.instrument.instrument_id: it for it in inp.items}
    rate = inp.fx_rate
    targets = {iid: it.target for iid, it in items.items()}
    values = {
        iid: position_value_krw(it.qty, it.price, it.instrument.currency, rate)
        for iid, it in items.items()
    }
    buy_wait = {iid: it.buy_wait_krw for iid, it in items.items()}
    report = drift_report(values, buy_wait, targets, inp.threshold)

    unit = {
        iid: unit_price_krw(it.price, it.instrument.currency, rate) for iid, it in items.items()
    }
    unit_cost = {
        iid: unit[iid] * (ONE + inp.fees.rate_for(it.instrument.currency))
        if it.buy_unit is None
        else unit_price_krw(it.buy_unit, it.instrument.currency, rate)
        for iid, it in items.items()
    }
    free_total = inp.free_krw + usd_in_krw(inp.free_usd, rate)
    qualifies = free_total > 0 and any(targets[iid] * free_total >= unit_cost[iid] for iid in items)
    investable = free_total if qualifies else ZERO

    if not report.exceeded and investable == ZERO:
        return Plan(report, free_total, ZERO, None)

    held = {iid: values[iid] + buy_wait[iid] for iid in items}
    base = sum(held.values(), ZERO) + investable

    sells: dict[str, int] = {}
    if report.exceeded:
        for iid, it in items.items():
            excess = held[iid] - targets[iid] * base
            n = min(it.qty, floor_div(excess, unit[iid]))
            if n > 0:
                sells[iid] = n

    buys: dict[str, int] = {}
    for iid in items:
        if iid in sells:
            continue
        n = floor_div(targets[iid] * base - held[iid], unit_cost[iid])
        if n > 0:
            buys[iid] = n

    buys, cash = _fit_budget(items, sells, buys, inp)

    reason = PlanReason.DRIFT if report.exceeded else PlanReason.NEW_CASH
    sell_orders = tuple(_trade(StageKind.SELL, items[i], n, inp.fees) for i, n in sells.items())
    buy_orders = tuple(_trade(StageKind.BUY, items[i], n, inp.fees) for i, n in buys.items())
    if not sell_orders and not buy_orders:
        # Exceeded, but no whole share fixes it (tiny rules). Nothing to send.
        return Plan(report, free_total, investable, None)

    weights_after, _ = in_rule_weights(_held_after(items, sells, buys, rate), {})
    return Plan(
        report=report,
        free_cash_krw=free_total,
        investable_cash_krw=investable,
        reason=reason,
        sells=sell_orders,
        fx=cash.fx,
        buys=buy_orders,
        weights_after=weights_after,
    )


def _relative(items: list[PlanItem]) -> tuple[PlanItem, ...]:
    """The items of one currency with their targets as shares of that currency's money: the
    rule's weights within it (0.3 and 0.2 of the rule -> 0.6 and 0.4). The last takes the rest,
    so they add up to exactly 1."""
    share = sum((it.target for it in items), ZERO)
    out: list[PlanItem] = []
    used = ZERO
    for n, it in enumerate(items):
        weight = ONE - used if n == len(items) - 1 else it.target / share
        used += weight
        out.append(replace(it, target=weight))
    return tuple(out)


def plan_per_currency(inp: PlanInput) -> Plan:
    """The live ledger's plan (D47): the money as the owner deposited it.

    - The won goes to the rule's Korean instruments and the dollars to its US ones, each by its
      weight within that currency ('지수 반반': all won to KR:069500, all dollars to US:SPYM).
    - Nothing is converted, and no market is sold to pay for the other.
    - Within one currency the rule's band works as in plan_rule, on the shares of that
      currency's money (it needs two instruments in one currency; '지수 반반' only ever buys).
    - A buy is sized with the items' `buy_unit` (the send's cap: limit price and fee) when they
      carry one, so the plan never counts a share the send cannot pay for at the plan price.

    The report stays the whole rule's (weights against the rule's targets, what the screens
    show); whether it is off by more than the band is the owner's to fix in the Toss app
    (currency_mix.suggest), never the plan's.
    """
    items = {it.instrument.instrument_id: it for it in inp.items}
    rate = inp.fx_rate
    values = {
        iid: position_value_krw(it.qty, it.price, it.instrument.currency, rate)
        for iid, it in items.items()
    }
    report = drift_report(
        values,
        {iid: it.buy_wait_krw for iid, it in items.items()},
        {iid: it.target for iid, it in items.items()},
        inp.threshold,
    )
    free_total = inp.free_krw + usd_in_krw(inp.free_usd, rate)
    sells: list[TradeOrder] = []
    buys: list[TradeOrder] = []
    investable = ZERO
    reasons: set[PlanReason] = set()
    for currency in Currency:
        group = [it for it in inp.items if it.instrument.currency is currency]
        if not group:
            continue
        own = plan_rule(
            replace(
                inp,
                items=_relative(group),
                free_krw=inp.free_krw if currency is Currency.KRW else ZERO,
                free_usd=inp.free_usd if currency is Currency.USD else ZERO,
                convert=False,
            )
        )
        sells.extend(own.sells)
        buys.extend(own.buys)
        investable += own.investable_cash_krw
        if own.reason is not None and (own.sells or own.buys):
            reasons.add(own.reason)
    if not sells and not buys:
        return Plan(report, free_total, investable, None)
    sold = {o.instrument.instrument_id: o.qty for o in sells}
    bought = {o.instrument.instrument_id: o.qty for o in buys}
    weights_after, _ = in_rule_weights(_held_after(items, sold, bought, rate), {})
    return Plan(
        report=report,
        free_cash_krw=free_total,
        investable_cash_krw=investable,
        reason=PlanReason.DRIFT if PlanReason.DRIFT in reasons else PlanReason.NEW_CASH,
        sells=tuple(sells),
        fx=None,
        buys=tuple(buys),
        weights_after=weights_after,
    )
