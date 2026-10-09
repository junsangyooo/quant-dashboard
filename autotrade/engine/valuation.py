"""What a ledger is worth at a moment, from stored prices only (no writes, no network).

Korean positions use the newest Korean close published by `at`, US positions the newest US close
(ET), dollars the newest stored rate at or before `at`. The 16:00 snapshot stores this; the web
API computes the same thing for 'now' (예시-값표 §0 '평가 기준').
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from autotrade.config import Config
from autotrade.db import repo
from autotrade.domain import baseline
from autotrade.domain.instruments import Currency, Instrument, Market
from autotrade.domain.money import ZERO, usd_in_krw
from autotrade.domain.valuation import position_value_krw
from autotrade.market.freshness import Freshness, FreshState
from autotrade.market.service import Close, latest_close, market_freshness, rate_freshness
from autotrade.market.types import FxQuote
from autotrade.timeutil import require_aware


class ValuationError(RuntimeError):
    """A held instrument has no price, or dollars have no rate."""


@dataclass(frozen=True)
class PositionValue:
    instrument: Instrument
    qty: int
    price: Decimal
    price_date: date
    value_krw: Decimal
    avg_price: Decimal
    cost_krw: Decimal


@dataclass(frozen=True)
class Valuation:
    at: datetime
    total_krw: Decimal
    positions: tuple[PositionValue, ...]
    cash_krw: Decimal
    cash_usd: Decimal
    fx: FxQuote | None
    kr_close: date | None
    us_close: date | None
    contributions: Decimal
    freshness: tuple[Freshness, ...]
    closes: dict[str, Close] = field(default_factory=dict)
    unit_prices: dict[str, Decimal] = field(default_factory=dict)  # won per share, rounded

    @property
    def stale(self) -> list[str]:
        return [f.series.value for f in self.freshness if f.state is not FreshState.FRESH]

    @property
    def pnl_krw(self) -> Decimal:
        return self.total_krw - self.contributions

    def value_of(self, instrument_id: str) -> Decimal:
        for p in self.positions:
            if p.instrument.instrument_id == instrument_id:
                return p.value_krw
        return ZERO


def value_ledger(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    at: datetime,
    instruments: Iterable[Instrument],
) -> Valuation:
    """Value the ledger at `at`. `instruments` are the rule's; held ones are added."""
    require_aware(at)
    state = repo.load_state(conn, ledger_id)
    by_id = {i.instrument_id: i for i in instruments}
    for iid in state.positions:
        if iid not in by_id:
            by_id[iid] = repo.get_instrument(conn, iid)
    insts = list(by_id.values())

    fx_fresh, quote = rate_freshness(conn, cfg, at)
    freshness: list[Freshness] = [fx_fresh]
    for market in (Market.KR, Market.US):
        if any(i.market is market for i in insts):
            freshness.append(market_freshness(conn, cfg, market, insts, at))

    holds_dollars = state.cash_of(Currency.USD) > 0 or any(
        pos.currency is Currency.USD for pos in state.positions.values()
    )
    if holds_dollars and quote is None:
        raise ValuationError("no KRW/USD rate stored")

    closes: dict[str, Close] = {}
    unit_prices: dict[str, Decimal] = {}
    oldest: dict[Market, date | None] = {Market.KR: None, Market.US: None}
    positions: list[PositionValue] = []
    total = ZERO
    for inst in insts:
        close = latest_close(conn, cfg, inst, at)
        qty = state.qty_of(inst.instrument_id)
        if close is None:
            if qty > 0:
                raise ValuationError(f"no close for held {inst.instrument_id}")
            continue
        closes[inst.instrument_id] = close
        prev = oldest[inst.market]
        oldest[inst.market] = close.session_date if prev is None else min(prev, close.session_date)
        if inst.currency is Currency.USD and quote is None:
            continue  # nothing held in dollars (checked above): no won price without a rate
        rate = quote.rate if quote is not None else Decimal(0)
        unit_prices[inst.instrument_id] = baseline.krw_unit_price(close.price, inst.currency, rate)
        if qty == 0:
            continue
        value = position_value_krw(qty, close.price, inst.currency, rate)
        total += value
        pos = state.positions[inst.instrument_id]
        positions.append(
            PositionValue(
                inst, qty, close.price, close.session_date, value, pos.avg_price, pos.cost_krw
            )
        )
    cash_krw = state.cash_of(Currency.KRW)
    cash_usd = state.cash_of(Currency.USD)
    if cash_usd > 0 and quote is not None:
        total += usd_in_krw(cash_usd, quote.rate)
    total += cash_krw
    return Valuation(
        at=at,
        total_krw=total,
        positions=tuple(positions),
        cash_krw=cash_krw,
        cash_usd=cash_usd,
        fx=quote,
        kr_close=oldest[Market.KR],
        us_close=oldest[Market.US],
        contributions=state.contributions_krw,
        freshness=tuple(freshness),
        closes=closes,
        unit_prices=unit_prices,
    )
