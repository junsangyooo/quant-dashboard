"""GET /api/history (SCR-HISTORY) and GET /api/day/{date} (SCR-DAY)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.context import LedgerContext, event_kind, event_krw
from autotrade.api.views.discovery import AI_EVENT_KINDS, judgment
from autotrade.api.views.orders import plan_stages, stages_mini
from autotrade.api.views.refs import instrument as instrument_json
from autotrade.api.views.series import (
    month_changes,
    month_key,
    pnl_now,
    snapshot_pnl,
    weekdays,
)
from autotrade.db import repo
from autotrade.db.models import EventRow, PlanRow, RunRow, SnapshotRow
from autotrade.domain.money import ZERO
from autotrade.rules.discovery import RULE_ID as AI_RULE
from autotrade.timeutil import from_iso, kst_date

REBALANCE_KINDS = ("rebalance", "partial-failed", "in-progress")
OK_RESULTS = (
    "rebalance",
    "in-range",
    "holiday",
    "quote-wait",
    "withdraw-wait",
    "in-progress",
    "partial-failed",
    "already-planned",
)
DAY_RESULT = {
    "rebalance": "rebalance",
    "already-planned": "rebalance",
    "in-range": "in-range",
    "partial-failed": "partial-failed",
    "in-progress": "in-progress",
    "failed": "failed",
    "todo": "failed",
    "holiday": "holiday",
    "quote-wait": "quote-wait",
    "withdraw-wait": "withdraw-wait",
}
CALENDAR_PRIORITY = (
    "failed",
    "partial-failed",
    "in-progress",
    "rebalance",
    "quote-wait",
    "holiday-both",
    "holiday-one",
    "normal",
    "no-run",
)


def rebalance_cause(reason: object, released: object) -> str | None:
    """Why '지수 반반' planned (CONTRACT.md RebalanceCause): 'band' when a weight left the band,
    'new-cash' when free cash is invested (the start, a deposit, a dividend), 'withdraw-expired'
    when that cash had been held for a withdrawal that did not come (인계 14). None otherwise
    (the AI rule's plans)."""
    if reason == "drift":
        return "band"
    if reason in ("new_cash", "start"):
        return "withdraw-expired" if released else "new-cash"
    return None


def failure_reason(run: RunRow) -> str:
    """A failed check's reason as a code (CONTRACT.md: codes, never sentences)."""
    return "no-quote" if (run.error or "").startswith("no-quote") else "other"


class DayData:
    """Runs, plans and snapshots of the ledger, indexed by KST date."""

    def __init__(self, ctx: LedgerContext) -> None:
        self.ctx = ctx
        self.runs: dict[date, list[RunRow]] = {}
        for run in repo.runs_of_ledger(ctx.conn, ctx.ledger_id, "check"):
            if run.started_at <= ctx.now:
                self.runs.setdefault(run.run_date, []).append(run)
        self.plans: dict[date, PlanRow] = {}
        self.plans_by_id: dict[int, PlanRow] = {}
        # A live plan that bought nothing is no rebalance day (LedgerContext.events).
        untraded = {
            e.plan_id
            for e in repo.events_of_ledger(ctx.conn, ctx.ledger_id, ["rebalance"])
            if e.payload.get("untraded")
        }
        for plan in repo.plans_of_ledger(ctx.conn, ctx.ledger_id):
            self.plans_by_id[plan.plan_id] = plan
            if plan.created_at <= ctx.now and plan.plan_id not in untraded:
                self.plans[plan.plan_date] = plan
        self.snaps: dict[date, SnapshotRow] = {s.date: s for s in ctx.snapshots}
        self.retried = {
            o.plan_id for o in repo.orders_of_ledger(ctx.conn, ctx.ledger_id) if o.attempt > 1
        }

    def check_failed(self, d: date) -> bool:
        runs = self.runs.get(d, [])
        return bool(runs) and not any(r.result in OK_RESULTS for r in runs)

    def calendar_state(self, d: date) -> str:
        ctx = self.ctx
        if d > ctx.today:
            return "future"
        if not ctx.started or d < ctx.start_date:
            return "before-record"
        states: list[str] = []
        runs = self.runs.get(d, [])
        if self.check_failed(d):
            states.append("failed")
        plan = self.plans.get(d)
        if plan is not None:
            if (
                plan.status in ("partial-failed", "todo", "resolved")
                or plan.plan_id in self.retried
            ):
                states.append("partial-failed")
            elif plan.status == "in-progress":
                states.append("in-progress")
            else:
                states.append("rebalance")
        if any(r.result == "quote-wait" for r in runs):
            states.append("quote-wait")
        closed = ctx.closed_markets(d)
        if len(closed) == 2:
            states.append("holiday-both")
        elif closed:
            states.append("holiday-one")
        states.append("normal" if runs else "no-run")
        return min(states, key=CALENDAR_PRIORITY.index)

    def day_change(self, d: date) -> tuple[Decimal | None, Decimal | None]:
        """(change, total) of a day from the snapshots; change is net of money in and out.

        change = the day's P&L (its 16:00 value less the money in by then) - the previous value's
        (series.py): money counts in the first day whose value holds it, so a deposit after a
        day's 16:00 value is the next value's, weekends included. Today before 16:00 the value is
        the one now. A day without a snapshot (a weekend, a missed run) has no change, and its
        total is the last value before it: nothing was revalued that day. Before the first value
        that is the start (a live ledger turned on after its first day's snapshot ran: worth what
        came in). None before the start.
        """
        ctx = self.ctx
        snap = self.snaps.get(d)
        before = [s for s in ctx.snapshots if s.date < d]
        if snap is None and d != ctx.today:
            if before:
                return None, before[-1].total_krw
            started = ctx.start is not None and ctx.start_date <= d
            return None, (ctx.start_amount if started else None)
        total, pnl = (
            (snap.total_krw, snapshot_pnl(snap)) if snap is not None else (ctx.total, pnl_now(ctx))
        )
        if not before:
            return None, total
        return pnl - snapshot_pnl(before[-1]), total

    def recovered_on(self, d: date) -> str | None:
        for later in sorted(x for x in self.runs if x >= d):
            if any(r.result in OK_RESULTS for r in self.runs[later]):
                return fmt.day(later)
        return None


def _weights_mini(ctx: LedgerContext, weights: Any, ev: EventRow | None = None) -> list[float]:
    if not isinstance(weights, dict):
        return []
    return [fmt.pct1(Decimal(str(weights.get(iid, "0")))) for iid in _plan_ids(ctx, ev)]


def _plan_ids(ctx: LedgerContext, ev: EventRow | None) -> list[str]:
    """The instruments a rebalance row lists: the fixed rule's two, or what the AI rule's plan
    held and bought (its weights before and after, in name order)."""
    if ev is None or ev.rule_id != AI_RULE:
        return list(ctx.rule.instrument_ids)
    ids: set[str] = set()
    for key in ("weights_before", "weights_after_est"):
        found = ev.payload.get(key)
        if isinstance(found, dict):
            ids |= set(found)
    return sorted(ids)


def _targets(ctx: LedgerContext, ev: EventRow) -> list[float]:
    """The target tick of the mini bars: the fixed rule's targets; the AI rule has none."""
    if ev.rule_id == AI_RULE:
        return []
    return [fmt.pct1(t.weight) for t in ctx.rule.targets]


def _rule_of(ctx: LedgerContext, ev: EventRow) -> dict[str, Any]:
    return ctx.ai_rule.rule_json() if ev.rule_id == AI_RULE else ctx.rule_json()


def _retry(data: DayData, plan: PlanRow) -> dict[str, Any] | None:
    """'9/15 다시 · 체결': the day of the latest retry and whether it filled."""
    if plan.plan_id not in data.retried:
        return None
    retries = [o for o in repo.orders_of_plan(data.ctx.conn, plan.plan_id) if o.attempt > 1]
    fills = {f.order_id: f for f in repo.fills_of_plan(data.ctx.conn, plan.plan_id)}
    last = retries[-1]
    fill = fills.get(last.order_id)
    if fill is not None:
        return {"date": fmt.day(kst_date(fill.filled_at)), "filled": True}
    stage = repo.get_stage(data.ctx.conn, last.stage_id)
    return {"date": fmt.day(kst_date(stage.due_at)), "filled": False}


def history_event(data: DayData, ev: EventRow) -> dict[str, Any]:
    ctx = data.ctx
    change, total = data.day_change(ev.event_date)
    out: dict[str, Any] = {
        "date": fmt.day(ev.event_date),
        "kind": event_kind(ev),
        "dayChange": None if change is None else fmt.krw(change),
        "dayTotal": fmt.krw(total if total is not None else ctx.start_amount),
    }
    if ev.kind == "start":
        out["amount"] = fmt.krw(ev.amount or ZERO)
        out["treatment"] = "pnl-excluded"
        if ev.plan_id is not None:  # the first purchase belongs to the start (§1.4 7/1 '첫 매수')
            stages = plan_stages(ctx.conn, ev.plan_id, ctx.instruments, ctx.executor)
            out["stagesMini"] = stages_mini(stages)
            out["fill"] = ctx.executor
            out["fees"] = fmt.krw(
                sum((f.fee_krw for f in repo.fills_of_plan(ctx.conn, ev.plan_id)), ZERO)
            )
    elif ev.kind == "rebalance" and ev.plan_id is not None:
        plan = data.plans_by_id[ev.plan_id]
        stages = plan_stages(ctx.conn, plan.plan_id, ctx.instruments, ctx.executor)
        out["rule"] = _rule_of(ctx, ev)
        out["stagesMini"] = stages_mini(stages)
        out["weightsMini"] = {
            "before": _weights_mini(ctx, ev.payload.get("weights_before"), ev),
            "after": _weights_mini(ctx, ev.payload.get("weights_after_est"), ev),
            "target": _targets(ctx, ev),
        }
        waiting = next((st for st in stages if st["status"] == "pending"), None)
        if waiting is not None and event_kind(ev) == "in-progress":
            out["pending"] = {"side": waiting["kind"], "at": waiting["at"]}  # '매수 22:30'
        out["fill"] = ctx.executor
        max_drift = ev.payload.get("max_drift")
        # A live plan only invests the money of each currency (D47): the whole rule's drift it
        # records, across the currencies, is not why it ran ('리밸런싱 · 50.0%p 벗어남').
        if max_drift is not None and not ctx.live:
            out["deviation"] = fmt.pp1(abs(Decimal(str(max_drift))))
        cause = rebalance_cause(ev.payload.get("reason"), ev.payload.get("withdraw_released"))
        if cause is not None:  # the screen says why: a band breach or new cash invested
            out["cause"] = cause
        out["fees"] = fmt.krw(
            sum((f.fee_krw for f in repo.fills_of_plan(ctx.conn, plan.plan_id)), ZERO)
        )
        retry = _retry(data, plan)
        if retry is not None:
            out["retry"] = retry
    elif ev.kind in AI_EVENT_KINDS:
        out["rule"] = ctx.ai_rule.rule_json()
        iid = ev.payload.get("instrument_id")
        if isinstance(iid, str):
            out["instrument"] = instrument_json(repo.get_instrument(ctx.conn, iid))
    elif ev.kind == "check-failed":
        error = str(ev.payload.get("error") or "")
        out["failureReason"] = "no-quote" if error.startswith("no-quote") else "other"
        recovered = data.recovered_on(ev.event_date)
        if recovered is not None:
            out["recoveredOn"] = recovered
    elif ev.kind in ("deposit", "withdrawal", "dividend"):
        out["amount"] = fmt.krw(event_krw(ev))
        out["treatment"] = "income" if ev.kind == "dividend" else "pnl-excluded"
        iid = ev.payload.get("instrument_id")
        if isinstance(iid, str) and iid in ctx.instruments:
            out["instrument"] = instrument_json(ctx.instruments[iid])
        if ev.kind == "dividend" and ev.rule_id == ctx.rule.rule_id:
            out["rule"] = ctx.rule_json()  # '지수 반반 (KOSPI200 ETF)'
    resolved = ev.payload.get("resolved_at")
    if ev.status == "resolved" and resolved:
        # The owner closed the manual action ('직접 할 일', python -m autotrade.jobs resolve).
        out["resolvedOn"] = fmt.day(kst_date(from_iso(str(resolved))))
    return out


def history(ctx: LedgerContext, year: int | None) -> dict[str, Any]:
    data = DayData(ctx)
    chosen = year or ctx.today.year
    years = sorted(
        {s.date.year for s in ctx.snapshots}
        | {e.event_date.year for e in ctx.listed_events}
        | ({ctx.today.year} if ctx.started else set())
    ) or [ctx.today.year]
    year_events = [e for e in ctx.listed_events if e.event_date.year == chosen]
    rebalances = [e for e in year_events if e.kind == "rebalance"]
    rule_dividends = [
        e for e in year_events if e.kind == "dividend" and e.rule_id == ctx.rule.rule_id
    ]
    ai_events = [
        e
        for e in year_events
        if e.kind in AI_EVENT_KINDS or (e.kind == "rebalance" and e.rule_id == AI_RULE)
    ]
    plan_kinds = [event_kind(e) for e in rebalances]
    check_days = [d for d in data.runs if d.year == chosen]
    fees = sum(
        (
            f.fee_krw
            for f in repo.fills_of_ledger(ctx.conn, ctx.ledger_id)
            if kst_date(f.filled_at).year == chosen and f.filled_at <= ctx.now
        ),
        ZERO,
    )
    pnl = None
    if ctx.started and ctx.has_fills:
        amount = ctx.total - ctx.contributions
        pnl = {
            "amount": fmt.krw(amount),
            "pct": fmt.ret2(amount / ctx.contributions) if ctx.contributions > 0 else None,
        }
    kinds_count = {
        "rebalance": len(rebalances),
        "deposit": sum(1 for e in year_events if e.kind == "deposit"),
        "withdrawal": sum(1 for e in year_events if e.kind == "withdrawal"),
        "dividend": sum(1 for e in year_events if e.kind == "dividend"),
        "failed": sum(1 for e in year_events if e.kind == "check-failed"),
    }
    if ctx.ai_rule.shown:
        kinds_count["ai"] = sum(1 for e in year_events if e.kind in AI_EVENT_KINDS)
    changes = month_changes(ctx)
    months: list[dict[str, Any]] = []
    for month in sorted(changes, reverse=True):
        if not month.startswith(f"{chosen:04d}-"):
            continue
        rows = [e for e in year_events if month_key(e.event_date) == month]
        rows.sort(key=lambda e: (e.occurred_at, e.event_id), reverse=True)
        months.append(
            {
                "month": month,
                "change": changes[month],
                "events": [history_event(data, e) for e in rows],
            }
        )
    first_day = date(chosen, 1, 1)
    last_day = date(chosen, 12, 31)
    return {
        "ledger": ctx.ledger_id,
        "example": False,
        "year": chosen,
        "years": years,
        "trend": {
            "since": fmt.day(ctx.start_date),
            "basis": ctx.basis(),
            "total": fmt.krw(ctx.total),
            "pnl": pnl,
            "series": [
                {"date": fmt.day(s.date), "value": fmt.krw(s.total_krw)}
                for s in ctx.snapshots
                if s.date.year == chosen
            ],
            "events": [
                {"date": fmt.day(e.event_date), "kind": event_kind(e)}
                for e in sorted(year_events, key=lambda e: (e.event_date, e.event_id))
            ],
        },
        "tiles": {
            "rebalances": {
                "count": len(rebalances),
                "partialFailed": plan_kinds.count("partial-failed"),
                "inProgress": plan_kinds.count("in-progress"),
            },
            "fees": {"krw": fmt.krw(fees)},
            "checks": {
                "count": len(check_days),
                "failed": sum(1 for d in check_days if data.check_failed(d)),
            },
        },
        "calendar": [
            {"date": fmt.day(d), "state": data.calendar_state(d)}
            for d in weekdays(first_day, last_day)
        ],
        "filters": {
            "total": len(year_events),
            # The rule chip counts its rebalances and dividends (§1.4: '지수 반반 3'); the AI
            # rule's chip its plans and its judgments.
            "rules": [
                {
                    "rule": ctx.rule_json(),
                    "count": len([e for e in rebalances if e.rule_id != AI_RULE])
                    + len(rule_dividends),
                },
                *(
                    [{"rule": ctx.ai_rule.rule_json(), "count": len(ai_events)}]
                    if ctx.ai_rule.shown
                    else []
                ),
            ],
            "kinds": [{"kind": k, "count": n} for k, n in kinds_count.items()],
        },
        "months": months,
        "offPeriods": [],
    }


def _check_basis(run: RunRow) -> dict[str, Any]:
    basis = run.details.get("basis") or {}
    closes = basis.get("closes") or {}
    kr = [v for k, v in closes.items() if k.startswith("KR:") and isinstance(v, dict)]
    us = [v for k, v in closes.items() if k.startswith("US:") and isinstance(v, dict)]
    fx = basis.get("fx") if isinstance(basis.get("fx"), dict) else None
    return {
        "valuedAt": fmt.iso(run.started_at),
        "krClose": str(kr[0]["date"]) if kr else None,
        "usClose": str(us[0]["date"]) if us else None,
        "fxRate": None if fx is None else fmt.rate(Decimal(str(fx["rate"]))),
        "fxAt": None if fx is None else fmt.iso(from_iso(str(fx["as_of"]))),
    }


def _snapshot_basis(snap: SnapshotRow) -> dict[str, Any]:
    return {
        "valuedAt": fmt.iso(snap.valued_at),
        "krClose": None if snap.kr_close_date is None else fmt.day(snap.kr_close_date),
        "usClose": None if snap.us_close_date is None else fmt.day(snap.us_close_date),
        "fxRate": fmt.rate(snap.fx_rate),
        "fxAt": fmt.iso(snap.fx_at),
    }


def _check_json(ctx: LedgerContext, data: DayData, d: date) -> dict[str, Any]:
    closed = ctx.closed_markets(d)
    if d.weekday() >= 5:
        return {"at": None, "result": "weekend", "band": None}
    runs = data.runs.get(d, [])
    if not runs:
        return {"at": None, "result": "no-run", "band": None}
    run = next((r for r in reversed(runs) if r.result in OK_RESULTS), runs[-1])
    out: dict[str, Any] = {
        "at": fmt.iso(run.started_at),
        "result": DAY_RESULT.get(run.result or "", "failed"),
    }
    planned = next(
        (r.details for r in runs if r.details.get("plan_id") and r.details.get("planned")), None
    )
    if planned is not None:  # the check that planned the day's rebalance: why it did
        cause = rebalance_cause(planned["planned"].get("reason"), planned.get("withdraw_released"))
        if cause is not None:
            out["cause"] = cause
    if out["result"] == "failed":  # '시세 응답 없음 · 9/10 정상' (codes and a date)
        failure: dict[str, Any] = {"reason": failure_reason(run)}
        recovered = data.recovered_on(d)
        if recovered is not None:
            failure["recoveredOn"] = recovered
        out["failure"] = failure
    if closed:
        out["holidayMarkets"] = closed
    drift = run.details.get("drift")
    # The live check records the whole rule's drift, across the currencies: no band, '넘음 →
    # 리밸런싱' or '리밸런싱까지' for it (D47: the live ledger never rebalances between them).
    if ctx.live or not isinstance(drift, dict) or not drift.get("max_instrument"):
        out["band"] = None
        return out
    iid = str(drift["max_instrument"])
    max_drift = Decimal(str(drift["max_drift"]))
    after = drift.get("weights_after")
    after_drift = None
    if isinstance(after, dict) and iid in after:
        after_drift = Decimal(str(after[iid])) - ctx.rule.target_of(iid)
    out["band"] = {
        "threshold": fmt.pp1(ctx.rule.threshold),
        "before": fmt.pp1(max_drift),
        "after": None if after_drift is None else fmt.pp1(after_drift),
    }
    out["ruleId"] = ctx.rule.rule_id
    out["rule"] = ctx.rule_json()
    out["instrument"] = instrument_json(ctx.instruments[iid])
    out["weight"] = fmt.pct1(Decimal(str(drift["weights"][iid])))
    out["toThreshold"] = fmt.pp1(Decimal(str(drift["to_threshold"])))
    out["over"] = fmt.pp1(Decimal(str(drift["over_by"])))
    return out


def day_events(ctx: LedgerContext, data: DayData, d: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for ev in ctx.listed_events:
        if ev.event_date != d:
            continue
        kind = event_kind(ev)
        if ev.kind == "rebalance" and ev.plan_id is not None:
            plan = data.plans_by_id[ev.plan_id]
            stages = plan_stages(ctx.conn, plan.plan_id, ctx.instruments, ctx.executor)
            ids = _plan_ids(ctx, ev)
            ai = ev.rule_id == AI_RULE
            out.append(
                {
                    "kind": kind,
                    "rule": _rule_of(ctx, ev),
                    "stagesMini": stages_mini(stages),
                    "weights": {
                        "instruments": [
                            instrument_json(repo.get_instrument(ctx.conn, i)) for i in ids
                        ],
                        "before": _weights_mini(ctx, ev.payload.get("weights_before"), ev),
                        "after": _weights_mini(ctx, ev.payload.get("weights_after_est"), ev),
                        "target": [] if ai else [fmt.pct1(t.weight) for t in ctx.rule.targets],
                        "threshold": 0.0 if ai else fmt.pp1(ctx.rule.threshold),
                    },
                    "stages": stages,
                    "feesKrw": fmt.krw(
                        sum((f.fee_krw for f in repo.fills_of_plan(ctx.conn, plan.plan_id)), ZERO)
                    ),
                }
            )
        elif ev.kind in ("start", "deposit", "withdrawal", "dividend"):
            item: dict[str, Any] = {
                "kind": ev.kind,
                "krw": fmt.krw(event_krw(ev)),
                "treatment": "income" if ev.kind == "dividend" else "pnl-excluded",
            }
            iid = ev.payload.get("instrument_id")
            if isinstance(iid, str) and iid in ctx.instruments:
                item["instrument"] = instrument_json(ctx.instruments[iid])
            if ev.kind == "start" and ev.plan_id is not None:
                item["stages"] = plan_stages(ctx.conn, ev.plan_id, ctx.instruments, ctx.executor)
                item["feesKrw"] = fmt.krw(
                    sum((f.fee_krw for f in repo.fills_of_plan(ctx.conn, ev.plan_id)), ZERO)
                )
            out.append(item)
        elif ev.kind in ("live-on", "live-off"):
            out.append({"kind": ev.kind, "at": fmt.iso(ev.occurred_at)})
        elif ev.kind in AI_EVENT_KINDS:
            out.append(
                {
                    "kind": ev.kind,
                    "rule": ctx.ai_rule.rule_json(),
                    "judgment": judgment(ctx.conn, ev),
                }
            )
    return out


def day(ctx: LedgerContext, d: date) -> dict[str, Any]:
    data = DayData(ctx)
    event_dates = sorted({e.event_date for e in ctx.listed_events})
    before = [x for x in event_dates if x < d]
    after = [x for x in event_dates if x > d]
    change, total = data.day_change(d)
    change_json = None
    if change is not None and total is not None:
        base = total - change
        change_json = {
            "amount": fmt.krw(change),
            "pct": fmt.ret2(change / base) if base > 0 else 0.0,
        }
    # The basis of the day's value, from the same source as its total (DayData.day_change): the
    # day's own 16:00 value; on a day without one (a weekend, a missed value) the last value
    # before it; today before 16:00 the value now.
    snap = data.snaps.get(d)
    earlier = [s for s in ctx.snapshots if s.date < d]
    if snap is not None:
        basis = _snapshot_basis(snap)
    elif d != ctx.today and earlier:
        basis = _snapshot_basis(earlier[-1])
    elif d == ctx.today:
        basis = ctx.basis()
    else:
        runs = data.runs.get(d, [])
        basis = _check_basis(runs[-1]) if runs else ctx.basis()
    return {
        "date": fmt.day(d),
        "ledger": ctx.ledger_id,
        "example": False,
        "prev": fmt.day(before[-1]) if before else None,
        "next": fmt.day(after[0]) if after else None,
        "total": fmt.krw(total if total is not None else ZERO),
        "change": change_json,
        "events": day_events(ctx, data, d),
        "check": _check_json(ctx, data, d),
        "basis": basis,
    }
