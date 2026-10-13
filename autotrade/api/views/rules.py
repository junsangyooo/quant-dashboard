"""GET /api/rules and /api/rules/{id} (SCR-RULES): the fixed rule's six tiles."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.context import LedgerContext
from autotrade.api.views.refs import instrument as instrument_json
from autotrade.domain.status import RuleStatus

# '과거 1년 수익' tile: measured, never expected. Vault 3-시험/T09 (주식 비중과 공격몫), as
# summarised in 5-설계/파이프라인.md '장투': after tax, one-year holding, 100% stocks, 2015–25 —
# median +9.5%, a bad year (10th percentile) −13.6%, worst −33.5%.
INDEX_HALF_MEASURED: dict[str, Any] = {
    "median": 9.5,
    "worst": -33.5,
    "badYear": -13.6,
    "period": "2015–25",
    "afterTax": True,
    "source": "T09",
}


def rule_list(ctx: LedgerContext) -> dict[str, Any]:
    rules = [
        {
            "rule": ctx.rule_json(),
            "share": ctx.share(),
            "status": ctx.status.value,
            "example": False,
        }
    ]
    ai = ctx.ai_rule
    if ai.shown:
        rules.append(
            {"rule": ai.rule_json(), "share": ai.share(), "status": ai.status, "example": False}
        )
    return {"rules": rules}


def deviation(ctx: LedgerContext) -> dict[str, Any]:
    """The condition tile's two points: the largest deviation now (hollow) and at today's 08:30
    check (orange); null when unknown (quote wait, no check today)."""
    now = None
    if ctx.drift is not None and ctx.status is not RuleStatus.QUOTE_WAIT:
        now = fmt.pp1(ctx.drift.max_drift)
    at_check = None
    last = ctx.last_check
    if last is not None and last.run_date == ctx.today:
        drift = last.details.get("drift")
        if isinstance(drift, dict) and drift.get("max_instrument"):  # nothing held: no point
            at_check = fmt.pp1(Decimal(str(drift["max_drift"])))
    return {"now": now, "atCheck": at_check}


def action_stages(ctx: LedgerContext) -> list[str]:
    """The legs of the rule's orders. The live ledger converts nothing (D47) and sells only to
    buy within one currency, which takes two instruments in it ('지수 반반' only buys there)."""
    if not ctx.live:
        return ["sell", "fx", "buy"]
    currencies = [inst.currency for inst in ctx.rule_instruments.values()]
    within = any(currencies.count(c) >= 2 for c in set(currencies))
    return ["sell", "buy"] if within else ["buy"]


def tiles(ctx: LedgerContext) -> dict[str, Any]:
    targets = [fmt.pct1(t.weight) for t in ctx.rule.targets]
    return {
        "kind": "tiles",
        "what": {
            "instruments": [instrument_json(ctx.instruments[i]) for i in ctx.rule.instrument_ids],
            "weights": targets,
            "basis": "krw",
        },
        "when": {"time": ctx.rule.check_time, "days": "weekdays", "tz": "KST"},
        "condition": {
            "threshold": fmt.pp1(ctx.rule.threshold),
            "targetEach": targets,
            "deviation": deviation(ctx),
        },
        "action": {"stages": action_stages(ctx)},
        "measured": INDEX_HALF_MEASURED,
        "now": {
            "status": ctx.status.value,
            "stages": ctx.stages,
            "nextCheckAt": fmt.iso(ctx.next_check),
        },
    }


def rule_detail(ctx: LedgerContext) -> dict[str, Any]:
    return {
        "rule": ctx.rule_json(),
        "share": ctx.share(),
        "status": ctx.status.value,
        "example": False,
        "stale": ctx.stale_at_check(),
        "display": tiles(ctx),
    }
