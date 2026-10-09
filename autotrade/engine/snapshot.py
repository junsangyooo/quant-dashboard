"""Daily valuation at 16:00 KST (ops notes 스냅숏).

Korean prices are that day's close, US prices the previous US close (ET), the rate the 16:00
quote. One row per ledger and weekday; running it again replaces the row.
The row also carries the untouched baseline ('손대지 않았을 때', autotrade/domain/baseline.py).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from autotrade.config import Config
from autotrade.db import repo
from autotrade.db.models import SnapshotRow
from autotrade.domain import baseline
from autotrade.domain.cash import CashPart
from autotrade.domain.instruments import Currency, Instrument, Market
from autotrade.domain.money import ZERO, usd_in_krw
from autotrade.domain.valuation import position_value_krw
from autotrade.engine.common import load_rule, refresh_cash_parts
from autotrade.market.calendar import calendar_for
from autotrade.market.freshness import FreshState
from autotrade.market.service import (
    latest_close,
    market_freshness,
    rate_freshness,
    record_freshness,
)
from autotrade.rules.index_half import RULE_ID
from autotrade.rules.model import RuleDef
from autotrade.timeutil import at_kst, is_weekday, kst_date, require_aware


class SnapshotError(RuntimeError):
    pass


@dataclass(frozen=True)
class SnapshotOutcome:
    result: str  # 'ok' | 'weekend' | 'not-started'
    row: SnapshotRow | None


def _part_json(p: CashPart) -> dict[str, Any]:
    return {
        "currency": p.currency.value,
        "purpose": p.purpose.value,
        "amount": p.amount,
        "instrument_id": p.instrument_id,
        "until": p.until,
    }


def _start_prices(
    conn: sqlite3.Connection,
    cfg: Config,
    rule: RuleDef,
    instruments: dict[str, Instrument],
    start: date,
) -> dict[str, Decimal] | None:
    """Won price of one share at the start: the first sessions' opens, the start-day 09:10 rate."""
    quote = repo.fx_at(conn, at_kst(start, cfg.stage_times.fx_time))
    out: dict[str, Decimal] = {}
    for iid in rule.instrument_ids:
        inst = instruments[iid]
        cal = calendar_for(inst.market)
        session = start if cal.is_trading_day(start) else cal.next_trading_day(start)
        bar = repo.get_bar(conn, iid, session)
        if bar is None or bar.open is None:
            return None
        if inst.currency is Currency.USD and quote is None:
            return None
        rate = quote.rate if quote is not None else Decimal(0)
        out[iid] = baseline.krw_unit_price(bar.open, inst.currency, rate)
    return out


def _baseline(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    d: date,
    total: Decimal,
    unit_prices: dict[str, Decimal],
    rule: RuleDef,
    instruments: dict[str, Instrument],
) -> tuple[Decimal | None, dict[str, str] | None]:
    start = repo.start_event(conn, ledger_id)
    if start is None or start.amount is None:
        return None, None
    if d <= start.event_date:
        return total, None  # the start day: the baseline made the same purchase
    previous = repo.latest_snapshot_before(conn, ledger_id, d)
    units: dict[str, Decimal] | None = None
    if previous is not None and previous.baseline_units:
        units = {k: Decimal(v) for k, v in previous.baseline_units.items()}
        since = previous.date
    else:
        prices = _start_prices(conn, cfg, rule, instruments, start.event_date)
        if prices is None:
            return None, None
        targets = {t.instrument_id: t.weight for t in rule.targets}
        units = baseline.units_for_amount(start.amount, targets, prices)
        since = start.event_date
    targets = {t.instrument_id: t.weight for t in rule.targets}
    for ev in repo.events_of_ledger(conn, ledger_id, ["deposit", "withdrawal"]):
        if since < ev.event_date <= d and ev.amount is not None:
            change = baseline.units_for_amount(ev.amount, targets, unit_prices)
            units = baseline.add_units(units, change, 1 if ev.kind == "deposit" else -1)
    value = baseline.value_krw(units, unit_prices)
    return value, {k: str(v) for k, v in units.items()}


def take_snapshot(
    conn: sqlite3.Connection, cfg: Config, ledger_id: str, at: datetime
) -> SnapshotOutcome:
    require_aware(at)
    d = kst_date(at)
    if not is_weekday(d):
        return SnapshotOutcome("weekend", None)
    if repo.start_event(conn, ledger_id) is None:
        return SnapshotOutcome("not-started", None)
    rule, instruments = load_rule(conn, RULE_ID)
    state = repo.load_state(conn, ledger_id)
    for iid in state.positions:
        instruments.setdefault(iid, repo.get_instrument(conn, iid))
    insts = list(instruments.values())

    fx_fresh, quote = rate_freshness(conn, cfg, at)
    record_freshness(conn, fx_fresh, at)
    if quote is None:
        raise SnapshotError("no KRW/USD rate stored")
    stale: list[str] = [] if fx_fresh.usable else [fx_fresh.series.value]
    closes_used: dict[Market, date | None] = {Market.KR: None, Market.US: None}
    for market in (Market.KR, Market.US):
        if any(i.market is market for i in insts):
            f = market_freshness(conn, cfg, market, insts, at)
            record_freshness(conn, f, at)
            if f.state is not FreshState.FRESH:
                stale.append(f.series.value)

    positions_json: list[dict[str, Any]] = []
    total = ZERO
    unit_prices: dict[str, Decimal] = {}
    for inst in insts:
        close = latest_close(conn, cfg, inst, at)
        if close is None:
            if state.qty_of(inst.instrument_id) > 0:
                raise SnapshotError(f"no close for held {inst.instrument_id}")
            continue
        unit_prices[inst.instrument_id] = baseline.krw_unit_price(
            close.price, inst.currency, quote.rate
        )
        prev = closes_used[inst.market]
        closes_used[inst.market] = (
            close.session_date if prev is None else min(prev, close.session_date)
        )
        qty = state.qty_of(inst.instrument_id)
        if qty == 0:
            continue
        value = position_value_krw(qty, close.price, inst.currency, quote.rate)
        total += value
        pos = state.positions[inst.instrument_id]
        positions_json.append(
            {
                "instrument_id": inst.instrument_id,
                "qty": qty,
                "price": close.price,
                "price_date": close.session_date,
                "currency": inst.currency.value,
                "value_krw": value,
                "avg_price": pos.avg_price,
                "cost_krw": pos.cost_krw,
            }
        )
    cash_krw = state.cash_of(Currency.KRW)
    cash_usd = state.cash_of(Currency.USD)
    total += cash_krw + usd_in_krw(cash_usd, quote.rate)
    parts = refresh_cash_parts(conn, ledger_id, at)
    base_value, base_units = _baseline(
        conn, cfg, ledger_id, d, total, unit_prices, rule, instruments
    )
    row = SnapshotRow(
        ledger_id=ledger_id,
        date=d,
        valued_at=at,
        total_krw=total,
        positions=positions_json,
        cash_krw=cash_krw,
        cash_usd=cash_usd,
        cash_parts=[_part_json(p) for p in parts],
        fx_rate=quote.rate,
        fx_at=quote.as_of,
        kr_close_date=closes_used[Market.KR],
        us_close_date=closes_used[Market.US],
        contributions=state.contributions_krw,
        pnl_krw=total - state.contributions_krw,
        baseline_krw=base_value,
        baseline_units=base_units,
        stale=stale,
    )
    repo.upsert_snapshot(conn, row, at)
    return SnapshotOutcome("ok", row)
