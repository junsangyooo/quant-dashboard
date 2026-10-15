"""Helpers shared by the check, the stage runner and the snapshot."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping
from datetime import date, datetime
from decimal import Decimal

from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.db.models import EventRow, OrderRow
from autotrade.domain.cash import CashPart, Claim, Purpose, partition
from autotrade.domain.instruments import Currency, Instrument
from autotrade.domain.money import ZERO, usd_in_krw
from autotrade.domain.planner import FxDirection
from autotrade.domain.stages import Slotter
from autotrade.engine.sleeves import BASE_RULE, base_view
from autotrade.market.calendar import KRX, NYSE
from autotrade.rules.model import RuleDef
from autotrade.timeutil import kst_date

PAPER = "paper"
LIVE = "live"
# The payload reason of the two events an owner's conversion makes on the live ledger (out of
# one currency, into the other: engine/live.py). api/views/accounts.py reads them as a transfer
# between the accounts; the whole ledger's views do not list them (no money came or went).
CONVERSION = "conversion"
# Money the reconciliation books as the owner's money in (engine/live.py): a deposit it could not
# explain otherwise, and the money a conversion of his brought. Not dividends, not sale proceeds.
OWNER_IN = ("unexplained-in", CONVERSION)
# The key of a check run's details that records the new money it held back (D48).
HELD_BACK = "new_money_wait"


def idem_key(
    ledger_id: str, d: date, rule_id: str, stage: str, market: str, target: str, attempt: int
) -> str:
    return f"{ledger_id}:{d.isoformat()}:{rule_id}:{stage}:{market}:{target}:a{attempt}"


def slotter_for(cfg: Config) -> Slotter:
    return Slotter(KRX, NYSE, cfg.stage_times)


def load_rule(conn: sqlite3.Connection, rule_id: str) -> tuple[RuleDef, dict[str, Instrument]]:
    row = repo.get_rule(conn, rule_id)
    rule = RuleDef.from_json(row.definition)
    instruments = {iid: repo.get_instrument(conn, iid) for iid in rule.instrument_ids}
    return rule, instruments


def pending_claims(
    conn: sqlite3.Connection, ledger_id: str, rule_id: str | None = None
) -> list[Claim]:
    """Cash that pending buys and conversions will spend, and for which instruments
    (one rule's orders when rule_id is given)."""
    orders = repo.pending_orders(conn, ledger_id)
    if rule_id is not None:
        rules = {o.plan_id: repo.get_plan(conn, o.plan_id).rule_id for o in orders}
        orders = [o for o in orders if rules[o.plan_id] == rule_id]
    buys_by_plan: dict[int, list[OrderRow]] = {}
    for o in orders:
        if o.side == "buy":
            buys_by_plan.setdefault(o.plan_id, []).append(o)
    claims: list[Claim] = []
    for o in orders:
        if o.side == "buy" and o.instrument_id is not None:
            claims.append(
                Claim(o.currency, o.est_amount + o.est_fee, {o.instrument_id: Decimal(1)})
            )
        elif o.side == "fx" and o.fx_direction is not None:
            target = FxDirection(o.fx_direction).target
            funded = {
                b.instrument_id: b.est_amount + b.est_fee
                for b in buys_by_plan.get(o.plan_id, [])
                if b.currency is target and b.instrument_id is not None
            }
            if funded:
                claims.append(Claim(o.currency, o.est_amount, funded))
    return claims


def new_money_waiting(
    conn: sqlite3.Connection, ledger_id: str, at: datetime
) -> dict[Currency, Decimal]:
    """D48 (2026-10-13): the owner's money in that arrived on the KST date of `at` (`OWNER_IN`:
    a deposit, or the money a conversion of his brought), less what his conversions of that day
    took out of the same currency. No check uses it on that date: it waits for the first
    weekday 08:30 check after it, so the owner can convert won he has just deposited at any
    time of the day before the Korean ETF is bought with it. Live ledger only (paper: {}).

    'Arrived' is the day the account first showed it (the event's date, engine/live.py; money
    dated earlier because an app buy spent it keeps that day). A withdrawal does not shorten the
    wait (it may be the proceeds of a sale leaving): money already there may then wait a day
    too, never the other way. The caller caps the amounts at the free cash."""
    out: dict[Currency, Decimal] = {}
    for ev, sign in _new_money_events(conn, ledger_id, at):
        assert ev.amount is not None
        currency = ev.currency or Currency.KRW
        out[currency] = out.get(currency, ZERO) + sign * ev.amount
    return {c: v for c, v in out.items() if v > 0}


def _new_money_events(
    conn: sqlite3.Connection, ledger_id: str, at: datetime
) -> list[tuple[EventRow, int]]:
    """The events new_money_waiting counts, with their sign (+1 in, -1 a conversion out)."""
    if ledger_id != LIVE:
        return []
    out: list[tuple[EventRow, int]] = []
    for ev in repo.events_on(conn, ledger_id, kst_date(at), ("deposit", "withdrawal")):
        if ev.amount is None or ev.occurred_at > at or ev.payload.get("source") != "broker":
            continue
        reason = ev.payload.get("reason")
        if ev.kind == "deposit" and reason in OWNER_IN:
            out.append((ev, 1))
        elif ev.kind == "withdrawal" and reason == CONVERSION:
            out.append((ev, -1))
    return out


def new_money_of_rule(
    conn: sqlite3.Connection, ledger_id: str, rule_id: str, at: datetime
) -> dict[Currency, Decimal]:
    """The part of new_money_waiting a rule holds (D48 for a ledger shared by rules): a sleeve's
    is its part of each of those events (engine/sleeves.py split_inflow), the base rule's the
    rest. With no sleeve it is new_money_waiting itself."""
    events = _new_money_events(conn, ledger_id, at)
    if not events:
        return {}
    sign_of = {ev.event_id: sign for ev, sign in events}
    sleeve_rules = [r for r in ai_repo.sleeve_rules(conn, ledger_id) if r != BASE_RULE]
    parts: dict[str, dict[Currency, Decimal]] = {}
    for r in sleeve_rules:
        mine: dict[Currency, Decimal] = {}
        for flow in ai_repo.sleeve_flows(conn, ledger_id, r):
            sign = sign_of.get(flow.event_id) if flow.event_id is not None else None
            if sign is not None:
                mine[flow.currency] = mine.get(flow.currency, ZERO) + sign * flow.amount
        parts[r] = mine
    if rule_id != BASE_RULE:
        return {c: v for c, v in parts.get(rule_id, {}).items() if v > 0}
    out = new_money_waiting(conn, ledger_id, at)
    for mine in parts.values():
        for currency, amount in mine.items():
            if amount > 0 and currency in out:
                out[currency] -= amount
    return {c: v for c, v in out.items() if v > 0}


def capped(
    waiting: Mapping[Currency, Decimal], free: Mapping[Currency, Decimal]
) -> dict[Currency, Decimal]:
    """The waiting new money within the free cash of each currency."""
    out: dict[Currency, Decimal] = {}
    for currency, amount in waiting.items():
        kept = min(amount, max(ZERO, free.get(currency, ZERO)))
        if kept > 0:
            out[currency] = kept
    return out


def held_back(details: Mapping[str, object]) -> dict[Currency, Decimal]:
    """The new money a check held back (its run details, written by engine/check.py)."""
    raw = details.get(HELD_BACK)
    if not isinstance(raw, dict):
        return {}
    return {Currency(str(k)): Decimal(str(v)) for k, v in raw.items()}


def refresh_cash_parts(conn: sqlite3.Connection, ledger_id: str, at: datetime) -> list[CashPart]:
    """Recompute and store what each part of the base rule's cash is for (pending_cash).

    Other rules' sleeves keep their cash apart (autotrade/engine/sleeves.py): their cash, their
    pending orders and their part of new money are left out here.

    New cash is what came in since the last check that judged the cash, and what that check held
    back (D48: it is still to be used), less what the owner's conversions took out of it since.
    Today's money of the owner (live) is set aside first.
    """
    state = base_view(conn, ledger_id)
    last = repo.last_cash_check(conn, ledger_id)
    checked_at = None if last is None else last.started_at
    new_cash = dict(repo.inflows_since(conn, ledger_id, checked_at))
    for flow in ai_repo.sleeve_flows_since(
        conn, ledger_id, checked_at, ("start", "deposit", "dividend")
    ):
        new_cash[flow.currency] = new_cash.get(flow.currency, ZERO) - flow.amount
    if last is not None:
        for currency, amount in held_back(last.details).items():
            new_cash[currency] = new_cash.get(currency, ZERO) + amount
    if ledger_id == LIVE:
        for ev in repo.events_of_ledger(conn, ledger_id, ["withdrawal"]):
            if ev.payload.get("reason") != CONVERSION or ev.amount is None:
                continue
            if checked_at is not None and ev.occurred_at <= checked_at:
                continue
            currency = ev.currency or Currency.KRW
            new_cash[currency] = new_cash.get(currency, ZERO) - ev.amount
    parts = partition(
        state.cash,
        repo.withdraw_waits(conn, ledger_id),
        pending_claims(conn, ledger_id, BASE_RULE),
        new_cash,
        held=new_money_of_rule(conn, ledger_id, BASE_RULE, at),
    )
    repo.replace_cash_parts(conn, ledger_id, parts, at)
    return parts


def buy_wait_krw(parts: Iterable[CashPart], fx_rate: Decimal) -> dict[str, Decimal]:
    """Cash waiting to buy each instrument, in won (dollars valued at the rate)."""
    out: dict[str, Decimal] = {}
    for p in parts:
        if p.purpose is Purpose.BUY_WAIT and p.instrument_id is not None:
            krw = p.amount if p.currency is Currency.KRW else usd_in_krw(p.amount, fx_rate)
            out[p.instrument_id] = out.get(p.instrument_id, ZERO) + krw
    return out


def withdraw_wait_amounts(parts: Iterable[CashPart]) -> dict[Currency, Decimal]:
    out: dict[Currency, Decimal] = {}
    for p in parts:
        if p.purpose is Purpose.WITHDRAW_WAIT:
            out[p.currency] = out.get(p.currency, ZERO) + p.amount
    return out
