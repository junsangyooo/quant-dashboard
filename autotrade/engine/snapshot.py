"""Daily valuation at 16:00 KST (ops notes 스냅숏).

Korean prices are that day's close, US prices the previous US close (ET), the rate the 16:00
quote. One row per ledger and weekday; running it again replaces the row.
The row also carries the untouched baseline ('손대지 않았을 때', autotrade/domain/baseline.py).
The baseline gets the same dividends as the ledger, on the same pay dates and after the same tax,
on the units it held before each ex-date; it keeps them as cash (untouched: nothing is bought).
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
from autotrade.domain.dividends import after_tax
from autotrade.domain.instruments import Currency, Instrument
from autotrade.domain.money import ZERO, usd_in_krw
from autotrade.engine.common import load_rule, refresh_cash_parts
from autotrade.engine.dividends import tax_rate
from autotrade.engine.valuation import ValuationError, value_ledger
from autotrade.market.calendar import calendar_for
from autotrade.market.service import record_freshness
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


def _start_units(
    conn: sqlite3.Connection,
    cfg: Config,
    rule: RuleDef,
    instruments: dict[str, Instrument],
    start_date: date,
    start_amount: Decimal,
) -> dict[str, Decimal] | None:
    prices = _start_prices(conn, cfg, rule, instruments, start_date)
    if prices is None:
        return None
    targets = {t.instrument_id: t.weight for t in rule.targets}
    return baseline.units_for_amount(start_amount, targets, prices)


def _units_before(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    rule: RuleDef,
    instruments: dict[str, Instrument],
    start_date: date,
    start_amount: Decimal,
    ex_date: date,
) -> dict[str, Decimal]:
    """Baseline units held before an ex-date: those of the last snapshot before it (snapshots run
    every weekday), else the start purchase when the start came before the ex-date."""
    if ex_date <= start_date:
        return {}
    snap = repo.latest_snapshot_before(conn, ledger_id, ex_date)
    if snap is not None and snap.baseline_units:
        return {k: Decimal(v) for k, v in snap.baseline_units.items()}
    return _start_units(conn, cfg, rule, instruments, start_date, start_amount) or {}


def _baseline_dividends(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    rule: RuleDef,
    instruments: dict[str, Instrument],
    start_date: date,
    start_amount: Decimal,
    since: date,
    d: date,
    fx_rate: Decimal,
) -> Decimal:
    """Won the baseline's units earned from dividends paid in (since, d], after the same tax as
    the ledger's; dollars at the snapshot's rate."""
    total = ZERO
    for div in repo.dividends_paid(conn, list(rule.instrument_ids), since, d):
        held = _units_before(
            conn, cfg, ledger_id, rule, instruments, start_date, start_amount, div.ex_date
        ).get(div.instrument_id, ZERO)
        if held <= 0:
            continue
        inst = instruments[div.instrument_id]
        net = after_tax(div.per_share, held, inst.currency, tax_rate(cfg, inst.market)).net
        total += net if inst.currency is Currency.KRW else usd_in_krw(net, fx_rate)
    return total


def _baseline(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    d: date,
    total: Decimal,
    unit_prices: dict[str, Decimal],
    rule: RuleDef,
    instruments: dict[str, Instrument],
    fx_rate: Decimal,
) -> tuple[Decimal | None, dict[str, str] | None, Decimal | None]:
    """(value, units, dividend cash) of the untouched baseline on day d."""
    start = repo.start_event(conn, ledger_id)
    if start is None or start.amount is None:
        return None, None, None
    if d <= start.event_date:
        return total, None, None  # the start day: the baseline made the same purchase
    previous = repo.latest_snapshot_before(conn, ledger_id, d)
    if previous is not None and previous.baseline_units:
        units = {k: Decimal(v) for k, v in previous.baseline_units.items()}
        cash = previous.baseline_cash_krw or ZERO
        since = previous.date
    else:
        start_units = _start_units(conn, cfg, rule, instruments, start.event_date, start.amount)
        if start_units is None:
            return None, None, None
        units, cash, since = start_units, ZERO, start.event_date
    targets = {t.instrument_id: t.weight for t in rule.targets}
    for ev in repo.events_of_ledger(conn, ledger_id, ["deposit", "withdrawal"]):
        if since < ev.event_date <= d and ev.amount is not None:
            change = baseline.units_for_amount(ev.amount, targets, unit_prices)
            units = baseline.add_units(units, change, 1 if ev.kind == "deposit" else -1)
    cash += _baseline_dividends(
        conn, cfg, ledger_id, rule, instruments, start.event_date, start.amount, since, d, fx_rate
    )
    value = baseline.value_krw(units, unit_prices) + cash
    return value, {k: str(v) for k, v in units.items()}, cash


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
    try:
        val = value_ledger(conn, cfg, ledger_id, at, instruments.values())
    except ValuationError as exc:
        raise SnapshotError(str(exc)) from exc
    for fresh in val.freshness:
        record_freshness(conn, fresh, at)
    if val.fx is None:
        raise SnapshotError("no KRW/USD rate stored")
    positions_json = [
        {
            "instrument_id": p.instrument.instrument_id,
            "qty": p.qty,
            "price": p.price,
            "price_date": p.price_date,
            "currency": p.instrument.currency.value,
            "value_krw": p.value_krw,
            "avg_price": p.avg_price,
            "cost_krw": p.cost_krw,
        }
        for p in val.positions
    ]
    parts = refresh_cash_parts(conn, ledger_id, at)
    base_value, base_units, base_cash = _baseline(
        conn, cfg, ledger_id, d, val.total_krw, val.unit_prices, rule, instruments, val.fx.rate
    )
    row = SnapshotRow(
        ledger_id=ledger_id,
        date=d,
        valued_at=at,
        total_krw=val.total_krw,
        positions=positions_json,
        cash_krw=val.cash_krw,
        cash_usd=val.cash_usd,
        cash_parts=[_part_json(p) for p in parts],
        fx_rate=val.fx.rate,
        fx_at=val.fx.as_of,
        kr_close_date=val.kr_close,
        us_close_date=val.us_close,
        contributions=val.contributions,
        pnl_krw=val.pnl_krw,
        baseline_krw=base_value,
        baseline_units=base_units,
        stale=val.stale,
        baseline_cash_krw=base_cash,
    )
    repo.upsert_snapshot(conn, row, at)
    return SnapshotOutcome("ok", row)
