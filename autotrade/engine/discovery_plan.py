"""The discovery planner (tick task 'ai-plan'): '3년 발굴' decisions become orders.

It runs on weekdays between the 08:30 check and the Korean order time (09:05), so its orders go
out at the next stage times like every plan (sell 09:05 -> FX 09:10 -> buy; US at the NYSE
open; a closed market's orders roll to its next session). A decision made after the window waits
for the next morning: a paper fill is a session's open, and an afternoon decision must not fill
at that morning's price. One plan per rule per day (UNIQUE); none while an earlier discovery plan
still runs, and none before the ledger's first plan (that one belongs to the 'start' event).

What it plans (autotrade/domain/discovery_plan.py): the sales of picks decided to sell, the
same amount for held picks the rule does not own yet (the seed, a confirmed new pick or
candidate), the Korean equal weight on the month's first planning day once that month's reviews
are done (D35), and idle money into the index ETF of its currency.

- The live ledger (3단계 몫, 2026-10-15): the same plan per currency (no conversion, D47), its
  buys sized as the send pays them (limit price and fee), its part of the owner's money of the
  day left for the next day (D48), and no buy of a company the account also holds outside the
  ledger (the reconciliation could no longer tell his shares from the rule's).
- The equal weight waits while a review of the month is pending, being asked, or failed with
  attempts left. A review that failed for good waits for a person (a red 'to do'); the equal
  weight then goes on without that pick (its shares stay as they are: it is not traded on a
  month nobody judged it), and the plan says which picks it left out.

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
from autotrade.db import ai_repo, live_repo, repo
from autotrade.domain.discovery_plan import DiscoveryInput, Holding, plan_discovery
from autotrade.domain.instruments import Currency, Instrument, Market
from autotrade.domain.ledger import LedgerState
from autotrade.domain.money import ZERO, round_won, usd_in_krw
from autotrade.domain.planner import Plan
from autotrade.domain.stages import StageMarket, schedule, stage_specs
from autotrade.engine import live, reviews, sleeves
from autotrade.engine.check import insert_stages_and_orders
from autotrade.engine.common import PAPER, capped, load_rule, new_money_of_rule, slotter_for
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


def judging_ledger(ledger_id: str) -> str:
    """The ledger whose AI tasks judge this ledger's picks: the live ledger follows the paper
    ledger's judgment (engine/live_discovery.py follow), every other ledger judges its own."""
    return PAPER if ledger_id == live.LIVE else ledger_id


def ew_month(conn: sqlite3.Connection, ledger_id: str, d: date, max_attempts: int) -> str | None:
    """The month whose Korean equal weight is due today, if any: its reviews were queued and
    none is still to be asked (pending, running, or failed with attempts left), and no discovery
    plan of the month has equalized yet. The reviews are the judging ledger's."""
    month = d.replace(day=1)
    key = f"{month:%Y-%m}"
    judge = judging_ledger(ledger_id)
    if not reviews.queued_for(conn, judge, month):
        return None
    open_reviews = [
        t
        for t in ai_repo.open_tasks(conn, max_attempts, kind="monthly-review", ledger_id=judge)
        if t.detail.get("month") == key
    ]
    if open_reviews:
        return None
    for plan in repo.plans_of_ledger(conn, ledger_id):
        if plan.rule_id == RULE_ID and plan.basis.get("equalize") == key:
            return None
    return key


def unreviewed(conn: sqlite3.Connection, ledger_id: str, key: str, max_attempts: int) -> set[str]:
    """Companies the month's review did not judge: it failed for good, or it was cancelled (by
    the owner, or because the pick had a decision). The equal weight leaves them out. The
    reviews are the judging ledger's."""
    judge = judging_ledger(ledger_id)
    return {
        ai_repo.get_pick(conn, t.pick_id).instrument_id
        for t in ai_repo.tasks_of(conn, kind="monthly-review", statuses=("failed", "cancelled"))
        if t.ledger_id == judge
        and t.detail.get("month") == key
        and t.pick_id is not None
        and (t.status == "cancelled" or t.is_stuck(max_attempts))
    }


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


def has_work(conn: sqlite3.Connection, ledger_id: str, at: datetime, max_attempts: int) -> bool:
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
        return bool(decided or missing or cash or ew_month(conn, ledger_id, d, max_attempts))
    return any(p.decided_at is not None and p.decided_at > prior.started_at for p in decided)


def outside_held(conn: sqlite3.Connection, ledger_id: str) -> set[str]:
    """Live: instruments the account holds that the ledger does not hold all of (the owner's own
    shares, outside the rules). None of them is bought for the rule."""
    if ledger_id != live.LIVE:
        return set()
    snap = live_repo.latest_snapshot(conn)
    if snap is None:
        return set()
    state = repo.load_state(conn, ledger_id)
    return {h.instrument_id for h in snap.holdings if h.qty > state.qty_of(h.instrument_id)}


def _usable_rate(conn: sqlite3.Connection, cfg: Config, at: datetime) -> Decimal | None:
    fx_fresh, quote = rate_freshness(conn, cfg, at)
    return quote.rate if quote is not None and fx_fresh.usable else None


def priced_holdings(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    at: datetime,
    state: LedgerState,
    rate: Decimal | None,
) -> tuple[dict[str, Holding], list[str]]:
    """What the plan may touch, at fresh closes (and the instruments still waiting for one).
    Live: a share is planned only if the send can pay it (the limit price and the fee)."""
    prices: dict[str, Decimal] = {}
    waiting: list[str] = []
    for inst in needed_instruments(conn, ledger_id):
        price = _fresh_price(conn, cfg, inst, at)
        if price is None or (inst.currency is Currency.USD and rate is None):
            waiting.append(inst.instrument_id)
            continue
        prices[inst.instrument_id] = price
    units = live.buy_units(conn, cfg, prices) if ledger_id == live.LIVE else {}
    holdings = {
        iid: Holding(
            repo.get_instrument(conn, iid), state.qty_of(iid), price, buy_unit=units.get(iid)
        )
        for iid, price in prices.items()
    }
    return holdings, waiting


def first_plan(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    at: datetime,
    cash: dict[Currency, Decimal],
) -> Plan | None:
    """The rule's first orders in a ledger that has not started, given the cash the start will
    give it (the live mode screen's preview, PHASE3.md 2.7): every held pick the same amount,
    the rest in the index ETF of its currency, per currency for the live ledger (D47). None
    when the rule has no held pick there. Reads only."""
    held = ai_repo.picks_of(conn, ledger_id, RULE_ID, ("held",))
    if not held:
        return None
    rate = _usable_rate(conn, cfg, at)
    holdings, _ = priced_holdings(conn, cfg, ledger_id, at, LedgerState(), rate)
    outside = outside_held(conn, ledger_id)
    value = cash.get(Currency.KRW, ZERO)
    if rate is not None:
        value += usd_in_krw(cash.get(Currency.USD, ZERO), rate)
    parking = parking_ids(conn)
    return plan_discovery(
        DiscoveryInput(
            holdings=holdings,
            sell=[],
            buy=[
                p.instrument_id
                for p in held
                if p.instrument_id in holdings and p.instrument_id not in outside
            ],
            equalize=[],
            parking={c: i.instrument_id for c, i in parking.items() if i.instrument_id in holdings},
            per_pick_krw=round_won(value / len(held)),
            cash_krw=cash.get(Currency.KRW, ZERO),
            cash_usd=cash.get(Currency.USD, ZERO) if rate is not None else ZERO,
            fx_rate=rate or Decimal(1),
            fees=cfg.fees,
            fx_step_krw=cfg.fx_step_krw,
            convert=ledger_id != live.LIVE,
        )
    )


def plan_ai(conn: sqlite3.Connection, cfg: Config, ledger_id: str, at: datetime) -> PlanOutcome:
    """Reconcile, then plan in the caller's transaction (the job downloaded the closes)."""
    d = kst_date(at)
    is_live = ledger_id == live.LIVE
    details: dict[str, Any] = {"reconciled": reconcile(conn, ledger_id, at)}
    state = sleeves.view(conn, ledger_id, RULE_ID)
    held = ai_repo.picks_of(conn, ledger_id, RULE_ID, ("held",))
    parking = parking_ids(conn)
    rate = _usable_rate(conn, cfg, at)
    holdings, waiting = priced_holdings(conn, cfg, ledger_id, at, state, rate)
    details["waiting"] = waiting
    cash = {c: state.cash_of(c) for c in Currency}
    if is_live:
        # D48: the rule's part of the owner's money of today waits for tomorrow.
        new_money = capped(new_money_of_rule(conn, ledger_id, RULE_ID, at), cash)
        if new_money:
            details["new_money_wait"] = {c.value: v for c, v in new_money.items()}
        cash = {c: v - new_money.get(c, ZERO) for c, v in cash.items()}
    outside = outside_held(conn, ledger_id)
    if outside & {p.instrument_id for p in held}:
        details["outside_held"] = sorted(outside & {p.instrument_id for p in held})
    if rate is None:
        details["fx"] = "stale"
    month = ew_month(conn, ledger_id, d, cfg.ai_max_attempts)
    left_out = set() if month is None else unreviewed(conn, ledger_id, month, cfg.ai_max_attempts)
    sell = [p.instrument_id for p in held if p.decision == "sell" and p.instrument_id in holdings]
    keep = [p for p in held if p.decision != "sell"]
    buy = [
        p.instrument_id
        for p in keep
        if p.instrument_id in holdings
        and holdings[p.instrument_id].qty == 0
        and p.instrument_id not in outside
    ]
    equalize = [
        p.instrument_id
        for p in keep
        if month is not None
        and p.instrument_id not in left_out
        and p.instrument_id in holdings
        and p.instrument_id not in outside
        and holdings[p.instrument_id].instrument.market is Market.KR
        and holdings[p.instrument_id].qty > 0
    ]
    skipped = sorted(p.instrument_id for p in keep if p.instrument_id in left_out)
    value = sum(
        (
            h.price * h.qty
            if h.instrument.currency is Currency.KRW
            else usd_in_krw(h.price * h.qty, rate or ZERO)
            for h in holdings.values()
        ),
        ZERO,
    )
    value += cash[Currency.KRW]
    if rate is not None:
        value += usd_in_krw(cash[Currency.USD], rate)
    per_pick = round_won(value / len(keep)) if keep else ZERO
    plan = plan_discovery(
        DiscoveryInput(
            holdings=holdings,
            sell=sell,
            buy=buy,
            equalize=equalize,
            parking={c: i.instrument_id for c, i in parking.items() if i.instrument_id in holdings},
            per_pick_krw=per_pick,
            cash_krw=cash[Currency.KRW],
            cash_usd=cash[Currency.USD] if rate is not None else ZERO,
            fx_rate=rate or Decimal(1),
            fees=cfg.fees,
            fx_step_krw=cfg.fx_step_krw,
            convert=not is_live,
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
    if skipped:
        details["equalize_skipped"] = skipped  # their review failed for good
    if not plan.has_orders:
        return PlanOutcome("nothing", None, details)
    due = schedule(stage_specs(plan), at, slotter_for(cfg))
    if kst_date(min(due.values())) != d:
        details["deferred"] = True  # nothing could start today (holidays): plan tomorrow
        return PlanOutcome("waiting", None, details)
    basis: dict[str, Any] = {
        "reason": "ai",
        "equalize": month if equalize else None,
        "decisions": {p.instrument_id: p.decision for p in held if p.decision},
        "per_pick_krw": per_pick,
        "fx_rate": rate,
    }
    if skipped:
        basis["equalize_skipped"] = skipped
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
