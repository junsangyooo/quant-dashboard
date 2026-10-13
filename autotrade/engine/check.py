"""The daily check, weekdays 08:30 KST (ops notes 매일 확인 1-8).

1. Data: Korean and US closes of the last finished sessions and the 08:30 rate, each with its
   freshness. A failed download with nothing fresh to fall back on fails the check (retried at
   09:30, then '직접 할 일'); data that is merely old means 'quote-wait' and 0 orders.
2. Holidays per market: the check runs when one market is closed; that market's orders roll to its
   next session, and a plan whose first stage cannot run today is not made today ('holiday').
3. A pending withdrawal means 0 orders on the paper ledger. On the live ledger it holds its own
   money only: that cash is never invested, the rest is planned as usual (PHASE3.md 2.5).
   The live ledger first matches the Toss account (engine/live.py reconcile, PHASE3.md 2.5):
   an account it cannot read as the truth, or that does not match, fails the check (0 orders).
4-5. In-rule weights and drift; a plan to target when the band is exceeded or free cash can buy.
   The live ledger plans per currency on the money as deposited (D47, domain/planner.py
   plan_per_currency): won buys the Korean instruments, dollars the US ones, nothing is
   converted. The owner's money that arrived today is not used today (D48,
   engine/common.py new_money_waiting): the check holds it back and records how much.
6. Stages sell -> FX -> buy with their times (live plans have no FX stage).
8. One plan per rule per day (UNIQUE) and one order per idempotency key: running the same check
   twice sends nothing twice.

Run results (runs.result) follow autotrade/CONTRACT.md where a screen shows them.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from autotrade.config import Config
from autotrade.db import repo
from autotrade.domain.instruments import Currency, Instrument, Market
from autotrade.domain.ledger import CashFlowKind, apply_cash_flow
from autotrade.domain.planner import (
    Plan,
    PlanInput,
    PlanItem,
    StageKind,
    plan_per_currency,
    plan_rule,
)
from autotrade.domain.stages import StageMarket, schedule, stage_specs
from autotrade.domain.weights import DriftReport
from autotrade.engine import live, sleeves
from autotrade.engine.bootstrap import MODE, start_amount_key, start_date_key
from autotrade.engine.common import (
    HELD_BACK,
    buy_wait_krw,
    capped,
    idem_key,
    load_rule,
    new_money_waiting,
    refresh_cash_parts,
    slotter_for,
    withdraw_wait_amounts,
)
from autotrade.market.calendar import calendar_for
from autotrade.market.freshness import Freshness
from autotrade.market.service import (
    FetchErrors,
    latest_close,
    market_freshness,
    rate_freshness,
    record_freshness,
)
from autotrade.rules.index_half import RULE_ID
from autotrade.rules.model import RuleDef
from autotrade.timeutil import at_kst, is_weekday, kst_date, require_aware

# runs.result values
REBALANCE = "rebalance"  # a plan was made today
IN_RANGE = "in-range"
HOLIDAY = "holiday"  # a market is closed today and nothing was sent
QUOTE_WAIT = "quote-wait"
WITHDRAW_WAIT = "withdraw-wait"
IN_PROGRESS = "in-progress"  # an earlier plan is still running
PARTIAL_FAILED = "partial-failed"
TODO = "todo"  # the check failed and has no retry left ('직접 할 일')
ALREADY_PLANNED = "already-planned"
FAILED = "failed"
WEEKEND = "weekend"
NOT_STARTED = "not-started"
NOT_LIVE = "not-live"  # the live ledger's check while the mode is paper: nothing runs
# The live ledger's check before the first weekday check after live was turned on (the one its
# preview showed, engine/live.py first_live_check): nothing runs.
NOT_YET = "not-yet"


class CheckFailedError(RuntimeError):
    """The check could not get the data it needs."""


@dataclass(frozen=True)
class CheckOutcome:
    result: str
    run_id: int | None
    plan_id: int | None
    error: str | None
    details: dict[str, Any] = field(default_factory=dict)


def ensure_started(conn: sqlite3.Connection, ledger_id: str, d: date, at: datetime) -> bool:
    """Write the 'start' event (the start amount) on the first check on or after the start date."""
    if repo.start_event(conn, ledger_id) is not None:
        return True
    start_text = repo.get_setting(conn, start_date_key(ledger_id)) or ""
    start_date = date.fromisoformat(start_text) if start_text else d
    if d < start_date:
        return False
    amount_text = repo.get_setting(conn, start_amount_key(ledger_id))
    if not amount_text:
        raise CheckFailedError(f"ledger {ledger_id} has no start amount")
    amount = Decimal(amount_text)
    state = apply_cash_flow(repo.load_state(conn, ledger_id), CashFlowKind.START, amount)
    repo.save_state(conn, ledger_id, state, at)
    event_id = repo.insert_event(
        conn,
        ledger_id=ledger_id,
        kind="start",
        event_date=d,
        occurred_at=at,
        amount=amount,
        currency=Currency.KRW,
        payload={"amount": amount},
    )
    # The start amount is shared by the rules' target shares (PHASE2.md §1).
    parts = sleeves.split_inflow(
        conn, ledger_id, CashFlowKind.START, amount, Currency.KRW, None, event_id, at
    )
    if parts:
        event = repo.start_event(conn, ledger_id)
        if event is not None:
            payload = dict(event.payload)
            payload["sleeves"] = parts
            repo.update_event(conn, event_id, at, payload=payload)
    repo.mark_ledger_started(conn, ledger_id, d, amount, at)
    return True


def _fresh_json(f: Freshness) -> dict[str, Any]:
    return {
        "state": f.state.value,
        "basis": f.basis,
        "expected": f.expected,
        "missing_sessions": f.missing_sessions,
    }


def _report_json(
    report: DriftReport, weights_after: dict[str, Decimal] | None = None
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "weights": report.weights,
        "drifts": report.drifts,
        "rule_value_krw": report.rule_value_krw,
        "threshold": report.threshold,
        "max_instrument": report.max_instrument,
        "max_drift": report.max_drift,
        "exceeded": report.exceeded,
        "over_by": report.over_by,
        "to_threshold": report.to_threshold,
    }
    if weights_after is not None:
        out["weights_after"] = weights_after
    return out


def retry_time(cfg: Config, d: date, at: datetime, final_attempt: bool) -> datetime | None:
    """When a check that failed at `at` is tried again: 09:30 the same day, unless this was the
    final attempt or 09:30 has passed (then it is '직접 할 일')."""
    if final_attempt:
        return None
    retry_at = at_kst(d, cfg.retry_time)
    return retry_at if retry_at > at else None


def record_check_failure(
    conn: sqlite3.Connection,
    ledger_id: str,
    d: date,
    at: datetime,
    error: str,
    retry_at: datetime | None,
) -> None:
    """The day's 'check-failed' event: status 'retry' while a retry is due, 'todo' after the
    last attempt (the '직접 할 일' that `todos` lists and `resolve check-failed:<date>` closes)."""
    status = "retry" if retry_at is not None else "todo"
    existing = repo.check_failure_event(conn, ledger_id, d)
    payload: dict[str, Any] = {"error": error, "retry_at": retry_at}
    if existing is None:
        payload["attempts"] = 1
        repo.insert_event(
            conn,
            ledger_id=ledger_id,
            kind="check-failed",
            event_date=d,
            occurred_at=at,
            status=status,
            payload=payload,
        )
    else:
        payload["attempts"] = int(existing.payload.get("attempts", 1)) + 1
        payload["first_error"] = existing.payload.get("first_error", existing.payload.get("error"))
        repo.update_event(conn, existing.event_id, at, status=status, payload=payload)


def _mark_check_recovered(conn: sqlite3.Connection, ledger_id: str, d: date, at: datetime) -> None:
    existing = repo.check_failure_event(conn, ledger_id, d)
    if existing is not None and existing.status != "recovered":
        payload = dict(existing.payload)
        payload["recovered_at"] = at
        repo.update_event(conn, existing.event_id, at, status="recovered", payload=payload)


def _persist_plan(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    rule: RuleDef,
    plan: Plan,
    d: date,
    at: datetime,
    run_id: int,
    basis: dict[str, Any],
    *,
    released: bool = False,
) -> int:
    start = repo.start_event(conn, ledger_id)
    # The first plan after the start buys the start amount; it belongs to the 'start' event.
    is_first = (
        start is not None
        and start.plan_id is None
        and start.status is None
        and not _has_any_plan(conn, ledger_id)
    )
    reason = "start" if is_first else (plan.reason.value if plan.reason else "drift")
    plan_id = repo.insert_plan(
        conn,
        ledger_id=ledger_id,
        rule_id=rule.rule_id,
        plan_date=d,
        run_id=run_id,
        reason=reason,
        basis=basis,
        weights_before=plan.report.weights,
        weights_after_est=plan.weights_after,
        created_at=at,
    )
    insert_stages_and_orders(conn, cfg, ledger_id, rule.rule_id, plan, plan_id, d, at)
    payload: dict[str, Any] = {
        "reason": reason,
        "max_instrument": plan.report.max_instrument,
        "max_drift": plan.report.max_drift,
        "threshold": plan.report.threshold,
        "over_by": plan.report.over_by,
        "weights_before": plan.report.weights,
        "weights_after_est": plan.weights_after,
        "basis": basis,
    }
    if released:  # the cash a withdraw wait held came back today (인계 14)
        payload["withdraw_released"] = True
    if is_first and start is not None:
        repo.update_event(conn, start.event_id, at, status="in-progress", plan_id=plan_id)
    else:
        repo.insert_event(
            conn,
            ledger_id=ledger_id,
            kind="rebalance",
            event_date=d,
            occurred_at=at,
            rule_id=rule.rule_id,
            plan_id=plan_id,
            status="in-progress",
            payload=payload,
        )
    return plan_id


def insert_stages_and_orders(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    rule_id: str,
    plan: Plan,
    plan_id: int,
    d: date,
    at: datetime,
) -> None:
    """A plan's stages (sell -> FX -> buy, with their times) and its orders, one
    idempotency key each. A live plan never converts (D47): Toss's API cannot."""
    if ledger_id == live.LIVE and plan.fx is not None:
        raise ValueError("a live plan with a conversion: the live ledger never converts (D47)")
    specs = stage_specs(plan)
    due = schedule(specs, at, slotter_for(cfg))
    stage_ids: dict[tuple[StageKind, StageMarket], int] = {}
    for spec in specs:
        stage_ids[(spec.kind, spec.market)] = repo.insert_stage(
            conn,
            plan_id=plan_id,
            seq=spec.seq,
            kind=spec.kind.value,
            market=spec.market.value,
            due_at=due[spec.seq],
            depends_on=spec.depends_on,
        )
    for order in (*plan.sells, *plan.buys):
        market = StageMarket(order.market.value)
        repo.insert_order(
            conn,
            repo.NewOrder(
                idem_key=idem_key(
                    ledger_id,
                    d,
                    rule_id,
                    order.stage.value,
                    market.value,
                    order.instrument.instrument_id,
                    1,
                ),
                ledger_id=ledger_id,
                plan_id=plan_id,
                stage_id=stage_ids[(order.stage, market)],
                stage=order.stage.value,
                market=market.value,
                instrument_id=order.instrument.instrument_id,
                side=order.side.value,
                fx_direction=None,
                currency=order.currency,
                qty=order.qty,
                est_price=order.est_price,
                est_amount=order.est_gross,
                est_fee=order.est_fee,
                est_rate=None,
                est_received=None,
            ),
            at,
        )
    if plan.fx is not None:
        fx = plan.fx
        repo.insert_order(
            conn,
            repo.NewOrder(
                idem_key=idem_key(ledger_id, d, rule_id, "fx", "FX", fx.direction.value, 1),
                ledger_id=ledger_id,
                plan_id=plan_id,
                stage_id=stage_ids[(StageKind.FX, StageMarket.FX)],
                stage="fx",
                market="FX",
                instrument_id=None,
                side="fx",
                fx_direction=fx.direction.value,
                currency=fx.direction.source,
                qty=None,
                est_price=None,
                est_amount=fx.from_amount,
                est_fee=Decimal(0),
                est_rate=fx.est_rate,
                est_received=fx.est_to_amount,
            ),
            at,
        )


def _has_any_plan(conn: sqlite3.Connection, ledger_id: str) -> bool:
    row = conn.execute("SELECT 1 FROM plans WHERE ledger_id = ? LIMIT 1", (ledger_id,)).fetchone()
    return row is not None


def _check_body(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    at: datetime,
    d: date,
    fetch: FetchErrors,
    details: dict[str, Any],
    run_id: int,
) -> tuple[str, int | None]:
    rule, instruments = load_rule(conn, RULE_ID)
    insts: list[Instrument] = [instruments[i] for i in rule.instrument_ids]
    markets = sorted({i.market for i in insts}, key=lambda m: m.value)
    closed = [m for m in markets if not calendar_for(m).is_trading_day(d)]
    details["rule_id"] = rule.rule_id
    details["closed_markets"] = [m.value for m in closed]

    # 1. Data and its freshness.
    fresh: dict[Market, Freshness] = {}
    for m in markets:
        f = market_freshness(conn, cfg, m, insts, at)
        record_freshness(conn, f, at)
        fresh[m] = f
    fx_fresh, quote = rate_freshness(conn, cfg, at)
    record_freshness(conn, fx_fresh, at)
    details["freshness"] = {f.series.value: _fresh_json(f) for f in (*fresh.values(), fx_fresh)}

    problems: list[str] = []
    for m in markets:
        error = fetch.for_market(m, insts)
        if error and not fresh[m].usable:
            problems.append(f"{m.value}: {error}")
    if fetch.fx and not fx_fresh.usable:
        problems.append(f"FX: {fetch.fx}")
    if problems:
        raise CheckFailedError("no-quote: " + " | ".join(problems))

    closes = {i.instrument_id: latest_close(conn, cfg, i, at) for i in insts}
    details["basis"] = basis = {
        "closes": {
            iid: None
            if c is None
            else {"price": c.price, "date": c.session_date, "source": c.source}
            for iid, c in closes.items()
        },
        "fx": None
        if quote is None
        else {"rate": quote.rate, "as_of": quote.as_of, "source": quote.source},
    }
    stale = [f.series.value for f in (*fresh.values(), fx_fresh) if not f.usable]
    if stale or quote is None:
        details["stale"] = stale
        return QUOTE_WAIT, None

    open_plans = repo.open_plans(conn, ledger_id, rule.rule_id)
    if ledger_id == live.LIVE:
        # The account is the truth: match it before anything is weighed (PHASE3.md 2.5).
        outcome = live.reconcile(conn, cfg, at)
        details["reconcile"] = {"state": outcome.state, "reason": outcome.reason}
        if not outcome.ok and not open_plans:
            kind = "mismatch" if outcome.state == "mismatch" else "broker"
            raise CheckFailedError(f"{kind}: {outcome.reason}")

    # 2-4. Weights on what the rule holds, cash waiting to buy included.
    released = repo.expire_withdraw_waits(conn, ledger_id, d)
    if released:  # a withdrawal that did not come: its cash is free again
        details["withdraw_released"] = released
    waits = repo.withdraw_waits(conn, ledger_id)
    state = sleeves.base_view(conn, ledger_id)  # what '지수 반반' holds of the shared ledger
    parts = refresh_cash_parts(conn, ledger_id, at)
    waiting = buy_wait_krw(parts, quote.rate)
    held = withdraw_wait_amounts(parts)
    # The live ledger sizes a buy as its send will pay for it (limit price and fee): a share the
    # send cannot pay for at the plan price is never planned (PlanItem.buy_unit).
    caps = (
        live.buy_units(conn, cfg, {iid: c.price for iid, c in closes.items() if c is not None})
        if ledger_id == live.LIVE
        else {}
    )
    items: list[PlanItem] = []
    for inst in insts:
        close = closes[inst.instrument_id]
        if close is None:  # pragma: no cover — excluded by the freshness check above
            raise CheckFailedError(f"no close for {inst.instrument_id}")
        items.append(
            PlanItem(
                instrument=inst,
                target=rule.target_of(inst.instrument_id),
                qty=state.qty_of(inst.instrument_id),
                price=close.price,
                buy_wait_krw=waiting.get(inst.instrument_id, Decimal(0)),
                buy_unit=caps.get(inst.instrument_id),
            )
        )

    free = {
        c: max(state.cash_of(c) - held.get(c, Decimal(0)), Decimal(0))
        for c in (Currency.KRW, Currency.USD)
    }
    # D48: the owner's money of today waits for the next weekday's check.
    new_money = capped(new_money_waiting(conn, ledger_id, at), free)
    if new_money:
        details[HELD_BACK] = {c.value: v for c, v in new_money.items()}
    usable = {c: free[c] - new_money.get(c, Decimal(0)) for c in free}
    if open_plans:
        # Cash already waiting for those plans' buys is not free.
        usable = dict.fromkeys(usable, Decimal(0))
    inp = PlanInput(
        items=tuple(items),
        threshold=rule.threshold,
        fx_rate=quote.rate,
        free_krw=usable[Currency.KRW],
        free_usd=usable[Currency.USD],
        fees=cfg.fees,
        fx_step_krw=cfg.fx_step_krw,
    )
    # Paper converts (virtually) to the targets; live runs on the money as deposited (D47).
    plan = plan_per_currency(inp) if ledger_id == live.LIVE else plan_rule(inp)
    details["drift"] = _report_json(plan.report)

    if open_plans:
        latest = open_plans[-1]
        details["open_plan_id"] = latest.plan_id
        details["open_plan_status"] = latest.status
        # A plan waiting for a retry or for a manual action is '일부 실패' on the check;
        # 'todo' as a run result is kept for a check that failed with no retry left.
        if latest.status in ("partial-failed", "todo"):
            return PARTIAL_FAILED, None
        return IN_PROGRESS, None
    if waits and ledger_id == live.LIVE:
        # The live ledger's wait holds its own money only (the owner sold in the app to take the
        # money out, or to convert it): it was left out of the free cash above, and the rest of
        # the money is planned as usual. A wait that stopped every order would stop them for
        # days whenever he follows a conversion suggestion by selling the Korean ETF (D47).
        details["withdraw_held"] = {c.value: v for c, v in held.items()}
        details["withdraw_held_until"] = max(w.until for w in waits)
    elif waits:
        details["withdraw_wait_until"] = max(w.until for w in waits)
        return WITHDRAW_WAIT, None
    if repo.plan_on(conn, ledger_id, rule.rule_id, d) is not None:
        return ALREADY_PLANNED, None
    if not plan.has_orders:
        details["free_cash_krw"] = plan.free_cash_krw
        return (HOLIDAY if closed else IN_RANGE), None

    specs = stage_specs(plan)
    due = schedule(specs, at, slotter_for(cfg))
    first_due = min(due.values())
    details["planned"] = {
        "reason": plan.reason.value if plan.reason else None,
        "sells": [(o.instrument.instrument_id, o.qty) for o in plan.sells],
        "buys": [(o.instrument.instrument_id, o.qty) for o in plan.buys],
        "fx": None
        if plan.fx is None
        else {"direction": plan.fx.direction.value, "from": plan.fx.from_amount},
        "first_due": first_due,
    }
    if kst_date(first_due) != d:
        # Nothing could start today: the closed market's orders wait for tomorrow's check.
        details["deferred"] = True
        return HOLIDAY, None

    plan_id = _persist_plan(
        conn, cfg, ledger_id, rule, plan, d, at, run_id, basis, released=released > 0
    )
    details["drift"] = _report_json(plan.report, plan.weights_after)
    details["plan_id"] = plan_id
    return REBALANCE, plan_id


def run_check(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    at: datetime,
    *,
    fetch: FetchErrors | None = None,
    attempt: int = 1,
    final_attempt: bool = False,
    clock: Callable[[], float] = time.monotonic,
) -> CheckOutcome:
    """One check. The caller owns the transaction (see autotrade/jobs/tasks.py)."""
    require_aware(at)
    d = kst_date(at)
    if not is_weekday(d):
        return CheckOutcome(WEEKEND, None, None, None)
    if ledger_id == live.LIVE and (repo.get_setting(conn, MODE) or "paper") != live.LIVE:
        return CheckOutcome(NOT_LIVE, None, None, None)
    if ledger_id == live.LIVE:
        first = live.first_live_check(conn, cfg)
        if first is not None and at < first:
            return CheckOutcome(NOT_YET, None, None, None, {"first_check": first})
    if not ensure_started(conn, ledger_id, d, at):
        return CheckOutcome(NOT_STARTED, None, None, None)
    started = clock()
    run_id = repo.insert_run(conn, ledger_id, "check", d, at, attempt)
    details: dict[str, Any] = {"attempt": attempt}
    error: str | None = None
    plan_id: int | None = None
    try:
        result, plan_id = _check_body(
            conn, cfg, ledger_id, at, d, fetch or FetchErrors(), details, run_id
        )
    except CheckFailedError as exc:
        result, error = FAILED, str(exc)
        retry_at = retry_time(cfg, d, at, final_attempt)
        details["retry_at"] = retry_at
        record_check_failure(conn, ledger_id, d, at, error, retry_at)
        if retry_at is None:
            result = TODO
    elapsed_ms = int((clock() - started) * 1000)
    repo.finish_run(
        conn,
        run_id,
        ended_at=at + timedelta(milliseconds=elapsed_ms),
        duration_ms=elapsed_ms,
        result=result,
        error=error,
        details=details,
    )
    if result not in (FAILED, TODO):
        _mark_check_recovered(conn, ledger_id, d, at)
    refresh_cash_parts(conn, ledger_id, at)
    return CheckOutcome(result, run_id, plan_id, error, details)


def needs_retry(conn: sqlite3.Connection, ledger_id: str, d: date) -> tuple[bool, int]:
    """Whether the 09:30 retry should run, and the attempt number it would be."""
    runs = repo.runs_on(conn, ledger_id, "check", d)
    if any(r.result not in (FAILED, TODO, None) for r in runs):
        return False, len(runs) + 1
    return True, len(runs) + 1
