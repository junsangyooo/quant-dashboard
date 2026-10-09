"""GET /api/plan (SCR-PLAN): rule cards, the schedule and the drift history."""

from __future__ import annotations

from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.context import LedgerContext, event_kind
from autotrade.api.views.orders import waiting_retry
from autotrade.api.views.refs import instrument as instrument_json
from autotrade.api.views.series import long_record, period_start, snapshot_drift
from autotrade.domain.cash import Purpose
from autotrade.domain.instruments import Currency
from autotrade.domain.money import ZERO, usd_in_krw
from autotrade.domain.status import RuleStatus
from autotrade.rules.discovery import RULE_ID as AI_RULE

DRIFT_PERIODS = ("3m", "1y", "all")
LEDGER_EVENTS = ("start", "live-on", "live-off")  # events of the whole ledger, not of one rule


def rule_card(ctx: LedgerContext) -> dict[str, Any]:
    report = ctx.drift if ctx.status is not RuleStatus.QUOTE_WAIT else None
    rows: list[dict[str, Any]] = []
    for target in ctx.rule.targets:
        inst = ctx.instruments[target.instrument_id]
        weight = None if report is None else report.weights.get(target.instrument_id)
        drift = None if report is None else report.drifts.get(target.instrument_id)
        rows.append(
            {
                "instrument": instrument_json(inst),
                "weight": None if weight is None else fmt.pct1(weight),
                "target": fmt.pct1(target.weight),
                "toThreshold": None
                if drift is None
                else fmt.pp1(max(ZERO, ctx.rule.threshold - abs(drift))),
            }
        )
    stale = ctx.stale_source() if ctx.status is RuleStatus.QUOTE_WAIT else None
    val = ctx.valuation
    return {
        "rule": ctx.rule_json(),
        "share": ctx.share(),
        "status": ctx.status.value,
        "next": ctx.next_action,
        "gauge": ctx.gauge(),
        "rows": rows,
        "basisLine": {
            "pendingBuyIncluded": any(
                p.purpose is Purpose.BUY_WAIT and p.amount > 0 for p in ctx.parts
            ),
            "fxRate": None if val is None or val.fx is None else fmt.rate(val.fx.rate),
            "fxAt": None if val is None or val.fx is None else fmt.iso(val.fx.as_of),
            "withdrawExcluded": ctx.withdraw_until is not None,
            "staleMarket": None if stale is None else stale[0],
            "staleBasisDate": None if stale is None else stale[1],
        },
    }


def _cash_krw(ctx: LedgerContext, purpose: Purpose) -> int:
    total = ZERO
    for p in ctx.parts:
        if p.purpose is purpose:
            total += p.amount if p.currency is Currency.KRW else usd_in_krw(p.amount, ctx.fx_rate)
    return fmt.krw(total)


def schedule(ctx: LedgerContext) -> dict[str, Any]:
    now = None
    if ctx.open_plan is not None:
        now = {"ruleId": ctx.rule.rule_id, "status": ctx.status.value, "stages": ctx.stages or []}
    items: list[dict[str, Any]] = []
    ai = ctx.ai_rule
    open_stages = [(ctx.rule.rule_id, ctx.stages)]
    if ai.shown:
        open_stages.append((AI_RULE, ai.stages))
    for rule_id, stages in open_stages:
        for stage in stages or []:
            for order in stage["orders"]:
                if waiting_retry(order):
                    items.append(
                        {
                            "kind": "retry",
                            "at": order["failure"]["retryAt"],
                            "market": order["market"],
                            "side": order["side"],
                            "ruleId": rule_id,
                        }
                    )
    if ctx.last_check is None:
        items.append({"kind": "first-check", "at": fmt.iso(ctx.first_check_at)})
    else:
        items.append({"kind": "next-check", "at": fmt.iso(ctx.next_check)})
    items.extend(ctx.upcoming_holidays())
    if ctx.withdraw_until is not None:
        items.append(
            {
                "kind": "withdraw-wait",
                "krw": _cash_krw(ctx, Purpose.WITHDRAW_WAIT),
                "until": fmt.day(ctx.withdraw_until),
            }
        )
    if ctx.last_check is not None and _cash_krw(ctx, Purpose.NEW) > 0:
        items.append({"kind": "new-cash", "krw": _cash_krw(ctx, Purpose.NEW)})
    if _cash_krw(ctx, Purpose.SUB_SHARE) > 0:
        items.append({"kind": "sub-share-cash", "krw": _cash_krw(ctx, Purpose.SUB_SHARE)})
    if ai.shown:
        if now is None and ai.open_plan is not None:
            now = {"ruleId": AI_RULE, "status": ai.status, "stages": ai.stages or []}
        items.extend(ai.schedule_items())
    return {"now": now, "items": items}


def drift_history(ctx: LedgerContext, period: str | None) -> dict[str, Any]:
    long = long_record(ctx)
    chosen = period if (long and period in DRIFT_PERIODS) else ("3m" if long else "all")
    since = period_start(chosen, ctx.today, ctx.start_date)
    points: list[dict[str, Any]] = []
    stale_from: str | None = None
    for snap in ctx.snapshots:
        if snap.date < since:
            continue
        value = snapshot_drift(ctx, snap)
        points.append(
            {"date": fmt.day(snap.date), "value": None if value is None else fmt.pp1(value)}
        )
        if value is None and stale_from is None:
            stale_from = fmt.day(snap.date)
        elif value is not None:
            stale_from = None
    # A rule's plans sit on its line; the start and live on/off belong to the whole ledger
    # (ruleId null). The AI rule has no drift line, so its plans are not marked here.
    events = [
        {
            "date": fmt.day(ev.event_date),
            "kind": event_kind(ev),
            "ruleId": None if ev.kind in LEDGER_EVENTS else (ev.rule_id or ctx.rule.rule_id),
        }
        for ev in ctx.events
        if ev.event_date >= since
        and (ev.kind in LEDGER_EVENTS or (ev.kind == "rebalance" and ev.rule_id != AI_RULE))
    ]
    return {
        "periods": list(DRIFT_PERIODS) if long else None,
        "period": chosen,
        "since": fmt.day(since),
        "lines": [{"ruleId": ctx.rule.rule_id, "points": points}],
        "staleFrom": stale_from,
        "events": events,
        "empty": "second-day" if len(ctx.snapshots) < 2 else None,
    }


def plan(ctx: LedgerContext, drift_period: str | None) -> dict[str, Any]:
    cards = [rule_card(ctx)]
    shares = None
    ai = ctx.ai_rule
    if ai.shown:
        cards.append(ai.card())
        # The bar shows when two rules or more have a share (CONTRACT.md PlanResponse).
        shares = [
            {"rule": ctx.rule_json(), "pct": float(ctx.rule_share)},
            {"rule": ai.rule_json(), "pct": float(ctx.composition.group_pct(AI_RULE))},
        ]
    return {
        "ledger": ctx.ledger_id,
        "example": False,
        "ruleShares": shares,
        "rules": cards,
        "schedule": schedule(ctx),
        "drift": drift_history(ctx, drift_period),
    }
