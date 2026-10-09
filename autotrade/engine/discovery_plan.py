"""The discovery planner (tick task 'ai-plan'): '3년 발굴' decisions become orders.

It runs on weekdays between the 08:30 check and the Korean order time (09:05), so its orders go
out at the next stage times like every plan (sell 09:05 -> FX 09:10 -> buy; US at the NYSE
open; a closed market's orders roll to its next session). A decision made after the window waits
for the next morning: a paper fill is a session's open, and an afternoon decision must not fill
at that morning's price. One plan per rule per day (UNIQUE); none while an earlier discovery plan
still runs, and none before the ledger's first plan (that one belongs to the 'start' event).

What it plans (autotrade/domain/discovery_plan.py): the sales of picks decided to sell, the
same amount for held picks the rule does not own yet (new picks, the seed, a confirmed candidate),
the Korean equal weight on the month's first planning day once that month's reviews are done
(D35), and idle money into the index ETF of its currency.

Before planning it closes picks whose sale has filled ('sold', the sale's day) and clears the
'buy' decisions that have their shares.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.domain.discovery_plan import DiscoveryInput, Holding, plan_discovery
from autotrade.domain.instruments import Currency, Instrument, Market
from autotrade.domain.money import ZERO, round_won, usd_in_krw
from autotrade.domain.stages import StageMarket, schedule, stage_specs
from autotrade.engine import reviews, sleeves
from autotrade.engine.check import insert_stages_and_orders
from autotrade.engine.common import load_rule, slotter_for
from autotrade.market.calendar import KRX, calendar_for
from autotrade.market.freshness import expected_session
from autotrade.market.service import latest_close, rate_freshness
from autotrade.rules.discovery import RULE_ID
from autotrade.rules.index_half import RULE_ID as INDEX_RULE
from autotrade.timeutil import at_kst, kst_date

JOB = "ai-plan"
KR_ORDER_TIME = time(9, 5)  # when KRX is closed: the usual Korean order time


@dataclass
class PlanOutcome:
    result: str  # 'planned' | 'nothing' | 'waiting' (data or a market is not ready)
    plan_id: int | None
    details: dict[str, Any] = field(default_factory=dict)


def window(cfg: Config, d: date) -> tuple[datetime, datetime]:
    """[check time, the Korean order time) of day d."""
    start = at_kst(d, cfg.check_time)
    if KRX.is_trading_day(d):
        return start, slotter_for(cfg).nominal(StageMarket.KR, d)
    return start, at_kst(d, KR_ORDER_TIME)


def parking_ids(conn: sqlite3.Connection) -> dict[Currency, Instrument]:
    """The index ETFs of the long-term rule hold the AI rule's idle money, one per currency."""
    rule, instruments = load_rule(conn, INDEX_RULE)
    return {instruments[i].currency: instruments[i] for i in rule.instrument_ids}


def ew_month(conn: sqlite3.Connection, ledger_id: str, d: date) -> str | None:
    """The month whose Korean equal weight is due today, if any: its reviews were queued and
    are done, and no discovery plan of the month has equalized yet."""
    month = d.replace(day=1)
    key = f"{month:%Y-%m}"
    if not reviews.queued_for(conn, ledger_id, month):
        return None
    open_reviews = [
        t
        for t in ai_repo.tasks_of(conn, kind="monthly-review", statuses=("pending", "running"))
        if t.detail.get("month") == key and t.ledger_id == ledger_id
    ]
    if open_reviews:
        return None
    for plan in repo.plans_of_ledger(conn, ledger_id):
        if plan.rule_id == RULE_ID and plan.basis.get("equalize") == key:
            return None
    return key


def reconcile(conn: sqlite3.Connection, ledger_id: str, at: datetime) -> dict[str, list[str]]:
    state = ai_repo.load_sleeve(conn, ledger_id, RULE_ID)
    out: dict[str, list[str]] = {"sold": [], "bought": []}
    fills = repo.fills_of_rule(conn, ledger_id, RULE_ID)
    for pick in ai_repo.picks_of(conn, ledger_id, RULE_ID, ("held",)):
        owned = pick.instrument_id in state.positions
        if pick.decision == "sell" and not owned:
            sold = [f for f in fills if f.instrument_id == pick.instrument_id and f.side == "sell"]
            closed = kst_date(sold[-1].filled_at) if sold else kst_date(at)
            ai_repo.update_pick(
                conn, pick.pick_id, at, status="sold", closed_on=closed, decision=None
            )
            out["sold"].append(pick.instrument_id)
        elif pick.decision == "buy" and owned:
            ai_repo.update_pick(conn, pick.pick_id, at, decision=None)
            out["bought"].append(pick.instrument_id)
    return out


def needed_instruments(conn: sqlite3.Connection, ledger_id: str) -> list[Instrument]:
    ids = set(ai_repo.load_sleeve(conn, ledger_id, RULE_ID).positions)
    ids |= {p.instrument_id for p in ai_repo.picks_of(conn, ledger_id, RULE_ID, ("held",))}
    ids |= {i.instrument_id for i in parking_ids(conn).values()}
    return [repo.get_instrument(conn, i) for i in sorted(ids)]


def _fresh_price(
    conn: sqlite3.Connection, cfg: Config, inst: Instrument, at: datetime
) -> Decimal | None:
    close = latest_close(conn, cfg, inst, at)
    if close is None:
        return None
    lag = cfg.kr_publication_lag if inst.market is Market.KR else cfg.us_publication_lag
    if close.session_date < expected_session(calendar_for(inst.market), at, lag):
        return None
    return close.price


def last_run(conn: sqlite3.Connection, ledger_id: str, d: date) -> ai_repo.JobRunRow | None:
    runs = [r for r in ai_repo.job_runs_on(conn, JOB, d) if r.ledger_id == ledger_id]
    return runs[-1] if runs else None


def has_work(conn: sqlite3.Connection, ledger_id: str, at: datetime) -> bool:
    """Something to plan (database only, for the schedule): a decision since the last run
    today, or on the day's first run any held pick without shares, the monthly equal weight or
    sleeve cash."""
    d = kst_date(at)
    prior = last_run(conn, ledger_id, d)
    held = ai_repo.picks_of(conn, ledger_id, RULE_ID, ("held",))
    decided = [p for p in held if p.decision is not None]
    if prior is None:
        state = ai_repo.load_sleeve(conn, ledger_id, RULE_ID)
        missing = [p for p in held if p.instrument_id not in state.positions]
        cash = any(v > 0 for v in state.cash.values())
        return bool(decided or missing or cash or ew_month(conn, ledger_id, d))
    return any(p.decided_at is not None and p.decided_at > prior.started_at for p in decided)


def plan_ai(conn: sqlite3.Connection, cfg: Config, ledger_id: str, at: datetime) -> PlanOutcome:
    """Reconcile, then plan in the caller's transaction (the job downloaded the closes)."""
    d = kst_date(at)
    details: dict[str, Any] = {"reconciled": reconcile(conn, ledger_id, at)}
    state = sleeves.view(conn, ledger_id, RULE_ID)
    held = ai_repo.picks_of(conn, ledger_id, RULE_ID, ("held",))
    parking = parking_ids(conn)
    fx_fresh, quote = rate_freshness(conn, cfg, at)
    rate = quote.rate if quote is not None and fx_fresh.usable else None
    holdings: dict[str, Holding] = {}
    waiting: list[str] = []
    for inst in needed_instruments(conn, ledger_id):
        price = _fresh_price(conn, cfg, inst, at)
        if price is None or (inst.currency is Currency.USD and rate is None):
            waiting.append(inst.instrument_id)
            continue
        holdings[inst.instrument_id] = Holding(inst, state.qty_of(inst.instrument_id), price)
    details["waiting"] = waiting
    if rate is None:
        details["fx"] = "stale"
    month = ew_month(conn, ledger_id, d)
    sell = [p.instrument_id for p in held if p.decision == "sell" and p.instrument_id in holdings]
    keep = [p for p in held if p.decision != "sell"]
    buy = [
        p.instrument_id
        for p in keep
        if p.instrument_id in holdings and holdings[p.instrument_id].qty == 0
    ]
    equalize = [
        p.instrument_id
        for p in keep
        if month is not None
        and p.instrument_id in holdings
        and holdings[p.instrument_id].instrument.market is Market.KR
        and holdings[p.instrument_id].qty > 0
    ]
    value = sum(
        (
            h.price * h.qty
            if h.instrument.currency is Currency.KRW
            else usd_in_krw(h.price * h.qty, rate or ZERO)
            for h in holdings.values()
        ),
        ZERO,
    )
    value += state.cash_of(Currency.KRW)
    if rate is not None:
        value += usd_in_krw(state.cash_of(Currency.USD), rate)
    per_pick = round_won(value / len(keep)) if keep else ZERO
    plan = plan_discovery(
        DiscoveryInput(
            holdings=holdings,
            sell=sell,
            buy=buy,
            equalize=equalize,
            parking={c: i.instrument_id for c, i in parking.items() if i.instrument_id in holdings},
            per_pick_krw=per_pick,
            cash_krw=state.cash_of(Currency.KRW),
            cash_usd=state.cash_of(Currency.USD) if rate is not None else ZERO,
            fx_rate=rate or Decimal(1),
            fees=cfg.fees,
            fx_step_krw=cfg.fx_step_krw,
        )
    )
    details.update(
        {
            "per_pick_krw": per_pick,
            "sell": [(o.instrument.instrument_id, o.qty) for o in plan.sells],
            "buy": [(o.instrument.instrument_id, o.qty) for o in plan.buys],
            "fx": None if plan.fx is None else {"direction": plan.fx.direction.value},
            "equalize": month if equalize else None,
        }
    )
    if not plan.has_orders:
        return PlanOutcome("nothing", None, details)
    due = schedule(stage_specs(plan), at, slotter_for(cfg))
    if kst_date(min(due.values())) != d:
        details["deferred"] = True  # nothing could start today (holidays): plan tomorrow
        return PlanOutcome("waiting", None, details)
    basis = {
        "reason": "ai",
        "equalize": month if equalize else None,
        "decisions": {p.instrument_id: p.decision for p in held if p.decision},
        "per_pick_krw": per_pick,
        "fx_rate": rate,
    }
    plan_id = repo.insert_plan(
        conn,
        ledger_id=ledger_id,
        rule_id=RULE_ID,
        plan_date=d,
        run_id=None,
        reason="ai",
        basis=basis,
        weights_before=plan.report.weights,
        weights_after_est=plan.weights_after,
        created_at=at,
    )
    insert_stages_and_orders(conn, cfg, ledger_id, RULE_ID, plan, plan_id, d, at)
    repo.insert_event(
        conn,
        ledger_id=ledger_id,
        kind="rebalance",
        event_date=d,
        occurred_at=at,
        rule_id=RULE_ID,
        plan_id=plan_id,
        status="in-progress",
        payload={
            **basis,
            "weights_before": plan.report.weights,
            "weights_after_est": plan.weights_after,
        },
    )
    details["plan_id"] = plan_id
    return PlanOutcome("planned", plan_id, details)
