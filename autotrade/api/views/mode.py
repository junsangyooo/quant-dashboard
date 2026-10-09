"""GET /api/mode (SCR-MODE). Phase 1 runs the paper ledger only: live cannot be turned on."""

from __future__ import annotations

from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.context import LedgerContext
from autotrade.api.views.history import DayData
from autotrade.api.views.series import long_record
from autotrade.db import repo


def mode(ctx: LedgerContext) -> dict[str, Any]:
    data = DayData(ctx)
    check_days = list(data.runs)
    fills = [f for f in repo.fills_of_ledger(ctx.conn, ctx.ledger_id) if f.filled_at <= ctx.now]
    long = long_record(ctx)
    ret = None
    baseline_pct = None
    if long and ctx.contributions > 0:
        amount = ctx.total - ctx.contributions
        ret = {"pct": fmt.ret2(amount / ctx.contributions), "amount": fmt.krw(amount)}
        last = ctx.snapshots[-1]
        if last.baseline_krw is not None and last.contributions > 0:
            baseline_pct = fmt.ret2((last.baseline_krw - last.contributions) / last.contributions)
    return {
        "mode": ctx.mode,
        "live": None,
        "liveOff": None,
        "twoLedgers": None,
        "performance": {
            "since": fmt.day(ctx.start_date),
            "checks": len(check_days),
            "rebalances": sum(1 for e in ctx.events if e.kind == "rebalance"),
            "failures": sum(1 for d in check_days if data.check_failed(d)),
            "paperFills": len(fills),
            "ret": ret,
            "baselinePct": baseline_pct,
        },
        "preflight": None,
        "preview": None,
        "cancelFailed": None,
        "canTurnOn": {"ok": False, "cause": "live-not-available"},
    }
