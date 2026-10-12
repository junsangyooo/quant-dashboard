"""Helpers shared by the check, the stage runner and the snapshot."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal

from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.db.models import OrderRow
from autotrade.domain.cash import CashPart, Claim, Purpose, partition
from autotrade.domain.instruments import Currency, Instrument
from autotrade.domain.money import ZERO, usd_in_krw
from autotrade.domain.planner import FxDirection
from autotrade.domain.stages import Slotter
from autotrade.engine.sleeves import BASE_RULE, base_view
from autotrade.market.calendar import KRX, NYSE
from autotrade.rules.model import RuleDef

PAPER = "paper"
LIVE = "live"


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


def refresh_cash_parts(
    conn: sqlite3.Connection, ledger_id: str, at: datetime, checked_at: datetime | None = None
) -> list[CashPart]:
    """Recompute and store what each part of the base rule's cash is for (pending_cash).

    Other rules' sleeves keep their cash apart (autotrade/engine/sleeves.py): their cash, their
    pending orders and their part of new money are left out here.
    """
    state = base_view(conn, ledger_id)
    if checked_at is None:
        last = repo.last_cash_check(conn, ledger_id)
        checked_at = None if last is None else last.started_at
    new_cash = dict(repo.inflows_since(conn, ledger_id, checked_at))
    for flow in ai_repo.sleeve_flows_since(
        conn, ledger_id, checked_at, ("start", "deposit", "dividend")
    ):
        new_cash[flow.currency] = new_cash.get(flow.currency, ZERO) - flow.amount
    parts = partition(
        state.cash,
        repo.withdraw_waits(conn, ledger_id),
        pending_claims(conn, ledger_id, BASE_RULE),
        new_cash,
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
