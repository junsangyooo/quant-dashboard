"""GET /api/rules and /api/rules/{id} (SCR-RULES): the fixed rule's six tiles."""

from __future__ import annotations

from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.context import LedgerContext
from autotrade.api.views.refs import instrument as instrument_json

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
    rules = [{"rule": ctx.rule_json(), "share": ctx.share(), "status": ctx.status.value}]
    ai = ctx.ai_rule
    if ai.shown:
        rules.append({"rule": ai.rule_json(), "share": ai.share(), "status": ai.status})
    return {"rules": rules}


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
        "condition": {"threshold": fmt.pp1(ctx.rule.threshold), "targetEach": targets},
        "action": {"stages": ["sell", "fx", "buy"]},
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
        "display": tiles(ctx),
    }
