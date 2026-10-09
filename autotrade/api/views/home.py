"""GET /api/home and /api/home/breakdown (SCR-HOME)."""

from __future__ import annotations

from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.context import CompRow, LedgerContext, event_krw
from autotrade.api.views.refs import instrument as instrument_json
from autotrade.api.views.series import (
    contributions_by_date,
    event_markers,
    long_record,
    period_start,
    series_points,
    value_on,
)
from autotrade.db import repo
from autotrade.domain.instruments import Currency
from autotrade.domain.money import ZERO
from autotrade.rules.discovery import RULE_ID as AI_RULE
from autotrade.timeutil import kst_date

HOME_PERIODS = ("1m", "3m", "1y", "all")
COUNTRY = {Currency.KRW: "KR", Currency.USD: "US"}


def pnl(ctx: LedgerContext) -> dict[str, Any] | None:
    """None until the first fill ('손익 · 첫 체결 뒤'); % hidden when the base is not positive."""
    if not ctx.started or not ctx.has_fills:
        return None
    amount = ctx.total - ctx.contributions
    pct = fmt.ret2(amount / ctx.contributions) if ctx.contributions > 0 else None
    return {"amount": fmt.krw(amount), "pct": pct}


def baseline(ctx: LedgerContext) -> dict[str, Any] | None:
    if not ctx.snapshots:
        return None
    last = ctx.snapshots[-1]
    if last.baseline_krw is None or last.contributions <= 0:
        return None
    return {"pct": fmt.ret2((last.baseline_krw - last.contributions) / last.contributions)}


def plan_card(ctx: LedgerContext) -> dict[str, Any] | None:
    if not ctx.started or ctx.last_check is None:
        return None  # before the first check only the chip row shows
    return {
        "rule": ctx.rule_json(),
        "share": ctx.share(),
        "status": ctx.status.value,
        "next": ctx.next_action,
        "gauge": ctx.gauge(),
        "stages": ctx.stages,
        "nextCheckAt": fmt.iso(ctx.next_check),
        "others": {"count": 1, "status": ctx.ai_rule.status} if ctx.ai_rule.shown else None,
    }


def _row_json(row: CompRow) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": row.kind, "pct": float(row.pct), "krw": fmt.krw(row.krw)}
    if row.kind == "holding" and row.instrument is not None:
        out["instrument"] = instrument_json(row.instrument)
        out["qty"] = row.qty
        if row.cost_krw is not None and row.cost_krw > 0:
            out["pnlPct"] = fmt.ret1((row.krw - row.cost_krw) / row.cost_krw)
        if row.avg_price is not None:
            cur = row.instrument.currency
            amount = fmt.krw(row.avg_price) if cur is Currency.KRW else fmt.usd(row.avg_price)
            out["avgCost"] = {"amount": amount, "currency": cur.value}
    else:
        out["cash"] = {"currency": (row.currency or Currency.KRW).value}
        if row.usd is not None:
            out["usd"] = fmt.usd(row.usd)
        if row.chip is not None:
            out["chip"] = row.chip
    return out


def composition(ctx: LedgerContext) -> dict[str, Any]:
    comp = ctx.composition
    rule_id = ctx.rule.rule_id
    rule_rows = [r for r in comp.rows if r.group == rule_id]
    groups: list[dict[str, Any]] = [
        {
            "key": rule_id,
            "rule": ctx.rule_json(),
            "pct": float(comp.group_pct(rule_id)),
            "target": ctx.target_pct,
            "rows": [_row_json(r) for r in rule_rows],
        }
    ]
    ai = ctx.ai_rule
    ai_rows = [r for r in comp.rows if r.group == AI_RULE]
    if ai.shown and (ai_rows or ai.target):
        groups.append(
            {
                "key": AI_RULE,
                "rule": ai.rule_json(),
                "pct": float(comp.group_pct(AI_RULE)),
                "target": None if ai.target is None else float(ai.target),
                "rows": [_row_json(r) for r in ai_rows],
            }
        )
    outside = [r for r in comp.rows if r.group == "outside"]
    if outside:
        groups.append(
            {
                "key": "outside",
                "pct": float(comp.group_pct("outside")),
                "target": None,
                "rows": [_row_json(r) for r in outside],
            }
        )
    cash_rows = [r for r in comp.rows if r.group == "cash"]
    if cash_rows:
        groups.append(
            {
                "key": "cash",
                "label": "cash",
                "pct": float(comp.group_pct("cash")),
                "target": None,
                "rows": [_row_json(r) for r in cash_rows],
            }
        )

    holdings = [r for r in comp.rows if r.kind == "holding" and r.instrument is not None]
    instruments = {r.instrument.instrument_id for r in holdings if r.instrument is not None}
    kinds = {r.instrument.kind for r in holdings if r.instrument is not None}
    countries = {r.instrument.market.value for r in holdings if r.instrument is not None}
    countries |= {COUNTRY[r.currency] for r in comp.rows if r.kind == "cash" and r.currency}
    currencies = {r.currency for r in comp.rows if r.currency is not None}
    rules = {r.group for r in comp.rows if r.group not in ("cash", "outside")}
    group_by = [
        name
        for name, count in (
            ("instrument", len(instruments)),
            ("kind", len(kinds)),
            ("country", len(countries)),
            ("currency", len(currencies)),
            ("rule", len(rules)),
        )
        if count >= 2
    ]
    withdraw = [r for r in comp.rows if r.chip and r.chip.get("kind") == "withdraw-wait"]
    pending_bar = None
    if withdraw:
        until = max(r.until for r in withdraw if r.until is not None)
        pending_bar = {
            "withdraw": {
                "krw": fmt.krw(sum((r.krw for r in withdraw), ZERO)),
                "until": fmt.day(until),
            }
        }
    outside_rules = (
        {"count": len(outside), "krw": fmt.krw(comp.group_krw("outside"))} if outside else None
    )
    return {
        "groupBy": group_by,
        "groups": groups,
        "pendingBar": pending_bar,
        "outsideRules": outside_rules,
    }


def trend(ctx: LedgerContext, period: str | None) -> dict[str, Any]:
    long = long_record(ctx)
    chosen = period if (long and period in HOME_PERIODS) else ("3m" if long else "all")
    since = period_start(chosen, ctx.today, ctx.start_date)
    if not ctx.started or ctx.last_check is None:
        empty: str | None = "before-first-check"
    elif len(ctx.snapshots) <= 1:
        empty = "first-day"
    else:
        empty = None
    period_pnl = None
    if long and chosen != "all":
        start_value = value_on(ctx, since)
        if start_value is not None and start_value > 0:
            flows = contributions_by_date(ctx)
            net_in = sum((v for d, v in flows.items() if d > since), ZERO)
            amount = ctx.total - start_value - net_in
            period_pnl = {"amount": fmt.krw(amount), "pct": fmt.ret2(amount / start_value)}
    return {
        "periods": list(HOME_PERIODS) if long else None,
        "period": chosen,
        "periodPnl": period_pnl,
        "series": series_points(ctx, since),
        "events": event_markers(ctx, since),
        "empty": empty,
    }


def home(ctx: LedgerContext, period: str | None) -> dict[str, Any]:
    stale = ["hero", "plan", "composition"] if ctx.stale_series else []
    return {
        "ledger": ctx.ledger_id,
        "example": False,
        "startDate": fmt.day(ctx.start_date),
        "basis": ctx.basis(),
        "stale": stale,
        "total": fmt.krw(ctx.total),
        "pnl": pnl(ctx),
        "baseline": baseline(ctx),
        "planChip": {
            "ruleId": ctx.rule.rule_id,
            "status": ctx.status.value,
            "next": ctx.next_action,
        },
        "trend": trend(ctx, period),
        "planCard": plan_card(ctx),
        "composition": composition(ctx),
    }


def breakdown(ctx: LedgerContext, period: str | None) -> dict[str, Any]:
    """Change over the period split into money in/out, market, dividends and fees.

    Every part is signed (withdrawals and fees are negative), so they add up to end - start.
    """
    long = long_record(ctx)
    chosen = period if (long and period in HOME_PERIODS) else "all"
    since = period_start(chosen, ctx.today, ctx.start_date)
    end = ctx.total
    if chosen == "all":
        # From the start amount: the start is not a deposit ('입금 개수에 넣지 않음').
        start_value, after = ctx.start_amount if ctx.started else ZERO, None
    else:
        start_value = value_on(ctx, since) or ZERO
        after = since
    deposit = withdrawal = dividend = ZERO
    for ev in ctx.events:
        if ev.amount is None or (after is not None and ev.event_date <= after):
            continue
        if ev.kind == "deposit":
            deposit += ev.amount
        elif ev.kind == "withdrawal":
            withdrawal -= ev.amount
        elif ev.kind == "dividend":
            dividend += event_krw(ev)
    fees = -sum(
        (
            f.fee_krw
            for f in repo.fills_of_ledger(ctx.conn, ctx.ledger_id)
            if f.filled_at <= ctx.now and (after is None or kst_date(f.filled_at) > after)
        ),
        ZERO,
    )
    parts = {
        "deposit": fmt.krw(deposit),
        "withdrawal": fmt.krw(withdrawal),
        "dividend": fmt.krw(dividend),
        "fees": fmt.krw(fees),
    }
    # The market part is what is left after rounding, so the parts add up to end - start exactly.
    market = fmt.krw(end) - fmt.krw(start_value) - sum(parts.values())
    return {
        "from": fmt.day(since),
        "to": fmt.day(ctx.today),
        "start": fmt.krw(start_value),
        "deposit": parts["deposit"],
        "withdrawal": parts["withdrawal"],
        "market": market,
        "dividend": parts["dividend"],
        "fees": parts["fees"],
        "end": fmt.krw(end),
    }
