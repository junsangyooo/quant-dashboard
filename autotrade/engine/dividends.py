"""Cash dividends of the paper ledger, booked as income (ops notes 사건; 인계 4 '배당·이자는 수익').

The daily dividend job stores what the source announces (market/service.prefetch_dividends);
this module books, once, every stored dividend whose pay date has come and that the ledger held
shares for before its ex-date:

- the net after the tax withheld at the source goes into the ledger's cash, in the instrument's
  currency (Korean ETF 15.4%, US ETF 15%; autotrade/domain/dividends.py), and counts as income;
- an event 'dividend' on the pay date records it: amount = net, currency, and in the payload the
  ex-date, pay date, shares, per-share amount, gross, tax and, for dollars, the rate of the booking
  and the won value ('amount_krw', what the screens show);
- the event's natural key ('dividend:<instrument>:<ex-date>') makes booking idempotent.

A dollar dividend needs a stored rate to be valued; without one it waits for the next run.
The live ledger's dividends will come from the broker (phase 3), not from this module.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from autotrade.config import Config
from autotrade.db import repo
from autotrade.db.models import DividendRow
from autotrade.domain.dividends import HeldFill, after_tax, qty_before_ex_date
from autotrade.domain.instruments import Currency, Instrument, Market
from autotrade.domain.ledger import CashFlowKind, apply_cash_flow
from autotrade.domain.money import usd_in_krw
from autotrade.engine.common import load_rule, refresh_cash_parts
from autotrade.rules.index_half import RULE_ID
from autotrade.timeutil import et_date, kst_date, require_aware


def tax_rate(cfg: Config, market: Market) -> Decimal:
    return cfg.kr_dividend_tax if market is Market.KR else cfg.us_dividend_tax


def dividend_ref(instrument_id: str, ex_date: date) -> str:
    return f"dividend:{instrument_id}:{ex_date.isoformat()}"


def watched_instruments(conn: sqlite3.Connection, ledger_id: str) -> list[Instrument]:
    """The rule's instruments and whatever else the ledger holds."""
    rule, instruments = load_rule(conn, RULE_ID)
    out = {iid: instruments[iid] for iid in rule.instrument_ids}
    for iid in repo.load_state(conn, ledger_id).positions:
        if iid not in out:
            out[iid] = repo.get_instrument(conn, iid)
    return list(out.values())


def shares_before_ex_date(
    conn: sqlite3.Connection, ledger_id: str, inst: Instrument, ex_date: date
) -> int:
    """Shares of `inst` the ledger held before the ex-date session (its own exchange's dates)."""
    fills: list[HeldFill] = []
    for f in repo.fills_of_ledger(conn, ledger_id):
        if f.kind != "trade" or f.instrument_id != inst.instrument_id or not f.qty:
            continue
        session = et_date(f.filled_at) if inst.market is Market.US else kst_date(f.filled_at)
        fills.append(HeldFill(session, f.qty if f.side == "buy" else -f.qty))
    qty_now = repo.load_state(conn, ledger_id).qty_of(inst.instrument_id)
    return qty_before_ex_date(qty_now, fills, ex_date)


def _book_one(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    div: DividendRow,
    inst: Instrument,
    qty: int,
    at: datetime,
) -> dict[str, Any] | None:
    rate = tax_rate(cfg, inst.market)
    amounts = after_tax(div.per_share, qty, inst.currency, rate)
    if amounts.net <= 0:
        return None
    krw_rate: Decimal | None = None
    amount_krw = amounts.net
    if inst.currency is Currency.USD:
        quote = repo.fx_at(conn, at)
        if quote is None:
            return {"instrument_id": inst.instrument_id, "ex_date": div.ex_date, "wait": "no-rate"}
        krw_rate = quote.rate
        amount_krw = usd_in_krw(amounts.net, krw_rate)
    state = apply_cash_flow(
        repo.load_state(conn, ledger_id),
        CashFlowKind.DIVIDEND,
        amounts.net,
        inst.currency,
        krw_rate,
    )
    repo.save_state(conn, ledger_id, state, at)
    payload: dict[str, Any] = {
        "instrument_id": inst.instrument_id,
        "ex_date": div.ex_date,
        "pay_date": div.pay_date,
        "pay_estimated": div.pay_estimated,
        "per_share": div.per_share,
        "qty": qty,
        "gross": amounts.gross,
        "tax_rate": rate,
        "tax": amounts.tax,
        "net": amounts.net,
        "amount_krw": amount_krw,
        "source": div.source,
    }
    if krw_rate is not None:
        payload["krw_rate"] = krw_rate
    rule, _ = load_rule(conn, RULE_ID)
    event_id = repo.insert_event(
        conn,
        ledger_id=ledger_id,
        kind="dividend",
        event_date=min(div.pay_date, kst_date(at)),
        occurred_at=at,
        rule_id=RULE_ID if inst.instrument_id in rule.instrument_ids else None,
        amount=amounts.net,
        currency=inst.currency,
        ref=dividend_ref(inst.instrument_id, div.ex_date),
        payload=payload,
    )
    return {
        "event_id": event_id,
        "instrument_id": inst.instrument_id,
        "ex_date": div.ex_date,
        "pay_date": div.pay_date,
        "qty": qty,
        "net": amounts.net,
        "currency": inst.currency.value,
        "amount_krw": amount_krw,
    }


def book_dividends(
    conn: sqlite3.Connection, cfg: Config, ledger_id: str, at: datetime
) -> list[dict[str, Any]]:
    """Book every stored dividend paid by today (KST) that the ledger is owed, once.

    Only dividends whose ex-date is after the ledger's start day count (nothing was held before
    it). The caller owns the transaction. Returns what was booked (and what waits for a rate).
    """
    require_aware(at)
    start = repo.start_event(conn, ledger_id)
    if start is None:
        return []
    today = kst_date(at)
    by_id = {i.instrument_id: i for i in watched_instruments(conn, ledger_id)}
    after = today - timedelta(days=cfg.dividend_lookback_days)
    out: list[dict[str, Any]] = []
    for div in repo.dividends_paid(conn, sorted(by_id), after, today):
        if div.ex_date <= start.event_date:
            continue
        if repo.event_by_ref(conn, ledger_id, dividend_ref(div.instrument_id, div.ex_date)):
            continue
        inst = by_id[div.instrument_id]
        qty = shares_before_ex_date(conn, ledger_id, inst, div.ex_date)
        if qty <= 0:
            continue
        booked = _book_one(conn, cfg, ledger_id, div, inst, qty, at)
        if booked is not None:
            out.append(booked)
    if any("event_id" in b for b in out):
        refresh_cash_parts(conn, ledger_id, at)
    return out
