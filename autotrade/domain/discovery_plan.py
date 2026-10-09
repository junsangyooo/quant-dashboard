"""Orders of '3년 발굴' from its decisions (pure; D27·D35·PHASE2.md §7 '판 돈').

Inputs are the rule's own part of the ledger (its sleeve), the latest closes and the rate:

1. Sell: every share of a pick decided to sell (two '반증', or a switch).
2. Korean equal weight (D35, T29 EW-M): on the month's first planning day the Korean picks are
   set to equal money among themselves; over-weight ones sell floor(excess / price) shares and
   under-weight ones buy floor(deficit / (price x (1 + fee))). US picks are never rebalanced.
3. Buy: each pick to buy gets the same amount (D27): floor(amount / unit cost) whole shares;
   a pick dearer than its amount is left for later (the cash waits).
4. Funding, per currency: cash and the sales first, then the index ETF that held money for the
   rule (sold to pay), then a conversion from the other currency, and last the buys are cut one
   share at a time, the largest first.
5. Parking: money left in a currency after the plan buys that currency's index ETF ('판 돈은
   다음에 살 때까지 같은 나라 지수 ETF에 둔다'), whole shares only.

A Korean stock sale pays the transaction tax (FeeRates.kr_stock_sell_tax) on top of the fee.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from autotrade.domain.instruments import Currency, Instrument, Kind
from autotrade.domain.money import (
    ZERO,
    FeeRates,
    ceil_cents,
    ceil_to_step,
    floor_div,
    floor_won,
    krw_to_usd,
    trade_fee,
    usd_in_krw,
    usd_to_krw,
)
from autotrade.domain.planner import FxDirection, FxOrder, Plan, Side, StageKind, TradeOrder
from autotrade.domain.weights import DriftReport, in_rule_weights

ONE = Decimal(1)


@dataclass(frozen=True)
class Holding:
    instrument: Instrument
    qty: int  # shares in the rule's part of the ledger
    price: Decimal  # plan price (latest close), instrument currency


@dataclass(frozen=True)
class DiscoveryInput:
    holdings: Mapping[str, Holding]  # every instrument the plan may touch
    sell: Sequence[str]
    buy: Sequence[str]
    equalize: Sequence[str]
    parking: Mapping[Currency, str]  # currency -> the index ETF that holds idle money
    per_pick_krw: Decimal
    cash_krw: Decimal
    cash_usd: Decimal
    fx_rate: Decimal
    fees: FeeRates
    fx_step_krw: Decimal = Decimal("1000")


def _krw(h: Holding, amount: Decimal, rate: Decimal) -> Decimal:
    return amount if h.instrument.currency is Currency.KRW else usd_in_krw(amount, rate)


def sell_net(h: Holding, qty: int, fees: FeeRates) -> Decimal:
    gross = h.price * qty
    net = gross - trade_fee(h.instrument.currency, gross, fees)
    if h.instrument.currency is Currency.KRW and h.instrument.kind is Kind.STOCK:
        net -= floor_won(gross * fees.kr_stock_sell_tax)
    return net


def buy_cost(h: Holding, qty: int, fees: FeeRates) -> Decimal:
    gross = h.price * qty
    return gross + trade_fee(h.instrument.currency, gross, fees)


def _unit_cost_krw(h: Holding, inp: DiscoveryInput) -> Decimal:
    rate_fee = ONE + inp.fees.rate_for(h.instrument.currency)
    return _krw(h, h.price * rate_fee, inp.fx_rate)


def _trade(stage: StageKind, h: Holding, qty: int, fees: FeeRates) -> TradeOrder:
    gross = h.price * qty
    fee = trade_fee(h.instrument.currency, gross, fees)
    if stage is StageKind.SELL and gross - sell_net(h, qty, fees) > fee:
        fee = gross - sell_net(h, qty, fees)
    return TradeOrder(
        stage=stage,
        side=Side.SELL if stage is StageKind.SELL else Side.BUY,
        instrument=h.instrument,
        qty=qty,
        est_price=h.price,
        est_gross=gross,
        est_fee=fee,
    )


@dataclass
class _Book:
    sells: dict[str, int]
    buys: dict[str, int]


def _balance(inp: DiscoveryInput, book: _Book) -> dict[Currency, Decimal]:
    """Money left per currency after the planned trades (negative = short)."""
    left = {Currency.KRW: inp.cash_krw, Currency.USD: inp.cash_usd}
    for iid, n in book.sells.items():
        h = inp.holdings[iid]
        left[h.instrument.currency] += sell_net(h, n, inp.fees)
    for iid, n in book.buys.items():
        h = inp.holdings[iid]
        left[h.instrument.currency] -= buy_cost(h, n, inp.fees)
    return left


def _sell_parking(inp: DiscoveryInput, book: _Book, currency: Currency, short: Decimal) -> None:
    iid = inp.parking.get(currency)
    if iid is None or iid not in inp.holdings:
        return
    h = inp.holdings[iid]
    available = h.qty - book.sells.get(iid, 0)
    one = sell_net(h, 1, inp.fees)
    if available <= 0 or one <= 0:
        return
    n = min(available, int(ceil_to_step(short / one, ONE)))
    if n > 0:
        book.sells[iid] = book.sells.get(iid, 0) + n


def _conversion(inp: DiscoveryInput, left: dict[Currency, Decimal]) -> FxOrder | None:
    rate = inp.fx_rate
    if left[Currency.USD] < 0 < left[Currency.KRW]:
        from_krw = min(
            ceil_to_step(-left[Currency.USD] * rate, inp.fx_step_krw),
            floor_div(left[Currency.KRW], inp.fx_step_krw) * inp.fx_step_krw,
        )
        if from_krw <= 0:
            return None
        return FxOrder(FxDirection.KRW_TO_USD, from_krw, rate, krw_to_usd(from_krw, rate), ())
    if left[Currency.KRW] < 0 < left[Currency.USD]:
        target = ceil_to_step(-left[Currency.KRW], inp.fx_step_krw)
        from_usd = min(ceil_cents(target / rate), left[Currency.USD])
        if from_usd <= 0:
            return None
        return FxOrder(FxDirection.USD_TO_KRW, from_usd, rate, usd_to_krw(from_usd, rate), ())
    return None


def _after_fx(left: dict[Currency, Decimal], fx: FxOrder | None) -> dict[Currency, Decimal]:
    out = dict(left)
    if fx is not None:
        out[fx.direction.source] -= fx.from_amount
        out[fx.direction.target] += fx.est_to_amount
    return out


def plan_discovery(inp: DiscoveryInput) -> Plan:
    book = _Book({}, {})
    for iid in inp.sell:
        h = inp.holdings[iid]
        if h.qty > 0:
            book.sells[iid] = h.qty
    eq = [iid for iid in inp.equalize if iid not in book.sells and inp.holdings[iid].qty > 0]
    if len(eq) >= 2:
        values = {iid: inp.holdings[iid].price * inp.holdings[iid].qty for iid in eq}
        target = sum(values.values(), ZERO) / len(eq)
        for iid in eq:
            h = inp.holdings[iid]
            if values[iid] > target:
                n = floor_div(values[iid] - target, h.price)
                if n > 0:
                    book.sells[iid] = n
            else:
                n = floor_div(target - values[iid], buy_cost(h, 1, inp.fees))
                if n > 0:
                    book.buys[iid] = n
    for iid in inp.buy:
        h = inp.holdings[iid]
        n = floor_div(inp.per_pick_krw, _unit_cost_krw(h, inp))
        if n > 0:
            book.buys[iid] = book.buys.get(iid, 0) + n

    # Funding: the index ETFs first, then a conversion, then cut the buys.
    fx: FxOrder | None = None
    while True:
        left = _balance(inp, book)
        for currency in Currency:
            if left[currency] < 0:
                _sell_parking(inp, book, currency, -left[currency])
        left = _balance(inp, book)
        fx = _conversion(inp, left)
        after = _after_fx(left, fx)
        if all(v >= 0 for v in after.values()) or not book.buys:
            break
        short = [c for c, v in after.items() if v < 0]
        candidates = [i for i in book.buys if inp.holdings[i].instrument.currency in short]
        if not candidates:
            break
        victim = max(
            candidates,
            key=lambda i: _krw(
                inp.holdings[i], buy_cost(inp.holdings[i], book.buys[i], inp.fees), inp.fx_rate
            ),
        )
        book.buys[victim] -= 1
        if book.buys[victim] == 0:
            del book.buys[victim]
    after = _after_fx(_balance(inp, book), fx)

    # Parking: what is left buys the same currency's index ETF.
    for currency, iid in inp.parking.items():
        etf = inp.holdings.get(iid)
        if etf is None or after.get(currency, ZERO) <= 0 or iid in book.sells:
            continue
        n = floor_div(after[currency], buy_cost(etf, 1, inp.fees))
        if n > 0:
            book.buys[iid] = book.buys.get(iid, 0) + n
            after[currency] -= buy_cost(etf, n, inp.fees)

    sells = tuple(
        _trade(StageKind.SELL, inp.holdings[i], n, inp.fees) for i, n in book.sells.items()
    )
    buys = tuple(_trade(StageKind.BUY, inp.holdings[i], n, inp.fees) for i, n in book.buys.items())
    before = {iid: _krw(h, h.price * h.qty, inp.fx_rate) for iid, h in inp.holdings.items()}
    weights, total = in_rule_weights(before, {})
    after_values = {
        iid: _krw(
            h, h.price * (h.qty - book.sells.get(iid, 0) + book.buys.get(iid, 0)), inp.fx_rate
        )
        for iid, h in inp.holdings.items()
    }
    weights_after, _ = in_rule_weights(after_values, {})
    cash_krw = inp.cash_krw + usd_in_krw(inp.cash_usd, inp.fx_rate)
    report = DriftReport(weights, {}, total, ZERO, None, ZERO)
    return Plan(
        report=report,
        free_cash_krw=cash_krw,
        investable_cash_krw=cash_krw,
        reason=None,
        sells=sells,
        fx=fx if (sells or buys) else None,
        buys=buys,
        weights_after=weights_after,
    )
