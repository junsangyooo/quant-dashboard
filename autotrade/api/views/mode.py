"""GET /api/mode (SCR-MODE). Phase 1 runs the paper ledger only: live cannot be turned on."""

from __future__ import annotations

from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.context import LedgerContext
from autotrade.api.views.history import DayData
from autotrade.api.views.orders import plan_stages
from autotrade.api.views.series import long_record
from autotrade.db import repo
from autotrade.domain.instruments import Currency
from autotrade.domain.money import usd_in_krw


def off_preview(ctx: LedgerContext) -> dict[str, Any] | None:
    """What turning live off leaves behind (SCR-MODE off modal): the live ledger's orders that
    would be cancelled and the cash that stays in the account. Null unless live is on."""
    if ctx.mode != "live":
        return None
    cancel: list[dict[str, Any]] = []
    for plan in repo.open_plans(ctx.conn, "live"):
        for stage in plan_stages(ctx.conn, plan.plan_id, ctx.instruments, "live"):
            cancel.extend(o for o in stage["orders"] if o["status"] == "pending")
    state = repo.load_state(ctx.conn, "live")
    quote = repo.fx_at(ctx.conn, ctx.now)
    rate = quote.rate if quote is not None else ctx.fx_rate
    cash: list[dict[str, Any]] = []
    for currency in Currency:
        amount = state.cash_of(currency)
        if amount <= 0:
            continue
        if currency is Currency.KRW:
            cash.append({"currency": "KRW", "krw": fmt.krw(amount)})
        else:
            cash.append(
                {
                    "currency": "USD",
                    "usd": fmt.usd(amount),
                    "krw": fmt.krw(usd_in_krw(amount, rate)),
                }
            )
    return {"cancel": cancel, "cash": cash}


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
        "offPreview": off_preview(ctx),
    }
