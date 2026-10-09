"""GET /api/shell (the header on every screen) and GET /api/health (SCR-HEALTH).

Phase 1 has three data sources (Korean and US closes, the rate). Toss link, Toss balance and
push devices do not exist yet, so they are not listed (no invented rows).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.context import LedgerContext
from autotrade.api.views.history import OK_RESULTS, DayData
from autotrade.db import repo
from autotrade.db.models import FreshnessRow, RunRow
from autotrade.domain.instruments import Market
from autotrade.market.calendar import calendar_for
from autotrade.market.freshness import FreshState, Series, quote_freshness, weekday_age
from autotrade.timeutil import from_iso

SOURCE_IDS = ("kr-quotes", "us-quotes", "fx")
SOURCE_MARKET = {"kr-quotes": Market.KR, "us-quotes": Market.US}


def _todo_orders(ctx: LedgerContext) -> list[dict[str, Any]]:
    """Orders waiting for a manual action ('직접 할 일')."""
    out: list[dict[str, Any]] = []
    for stage in ctx.stages or []:
        for order in stage["orders"]:
            failure = order.get("failure")
            if isinstance(failure, dict) and failure.get("manual"):
                out.append(order)
    return out


def _retry_orders(ctx: LedgerContext) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for stage in ctx.stages or []:
        for order in stage["orders"]:
            failure = order.get("failure")
            if isinstance(failure, dict) and failure.get("retryAt"):
                out.append(order)
    return out


def _today_check_failure(ctx: LedgerContext) -> tuple[RunRow, datetime | None] | None:
    """The failed check of today, with its retry time (None once retries are spent)."""
    runs = repo.runs_on(ctx.conn, ctx.ledger_id, "check", ctx.today)
    runs = [r for r in runs if r.started_at <= ctx.now]
    if not runs or any(r.result in OK_RESULTS for r in runs):
        return None
    failure = repo.check_failure_event(ctx.conn, ctx.ledger_id, ctx.today)
    if failure is not None and failure.status == "resolved":
        return None  # the owner closed it (python -m autotrade.jobs resolve check-failed:<date>)
    last = runs[-1]
    retry = last.details.get("retry_at")
    return last, None if not retry else from_iso(str(retry))


def _last_success(ctx: LedgerContext) -> RunRow | None:
    runs = [
        r for r in repo.runs_of_ledger(ctx.conn, ctx.ledger_id, "check") if r.result in OK_RESULTS
    ]
    runs = [r for r in runs if r.started_at <= ctx.now]
    return runs[-1] if runs else None


def shell(ctx: LedgerContext, mode_changed_at: datetime | None) -> dict[str, Any]:
    failure = _today_check_failure(ctx)
    todo = _todo_orders(ctx)
    todo_count = len(todo) + (1 if failure is not None and failure[1] is None else 0)
    stale = ctx.stale_source() if ctx.status.value == "quote-wait" else None
    retries = _retry_orders(ctx)
    status: dict[str, Any]
    if ctx.last_check is None:
        status = {"kind": "before-first", "firstCheckAt": fmt.iso(ctx.first_check_at)}
    elif todo_count:
        status = {"kind": "todo", "count": todo_count}
    elif failure is not None:
        status = {"kind": "check-failed", "at": fmt.iso(failure[0].started_at)}
    elif stale is not None or retries:
        status = {"kind": "check", "count": (1 if stale is not None else 0) + len(retries)}
    else:
        last = _last_success(ctx)
        status = {"kind": "ok", "lastCheckAt": fmt.iso((last or ctx.last_check).started_at)}

    banner: dict[str, Any] | None = None
    plan_day = None if ctx.open_plan is None else fmt.day(ctx.open_plan.plan_date)
    if failure is not None:
        banner = {
            "kind": "check-failed",
            "at": fmt.iso(failure[0].started_at),
            "retryAt": None if failure[1] is None else fmt.iso(failure[1]),
            "link": "health",
        }
    elif todo:
        order = todo[0]
        banner = {
            "kind": "partial-todo",
            "date": plan_day,
            "market": order["market"],
            "side": order["side"],
            "reason": "retry-failed",
            "link": "health",
        }
    elif stale is not None:
        banner = {
            "kind": "stale",
            "market": stale[0],
            "basisDate": stale[1],
            "tradingDays": stale[2],
            "link": "health",
        }
    elif retries:
        order = retries[0]
        banner = {
            "kind": "partial-retry",
            "date": plan_day,
            "market": order["market"],
            "side": order["side"],
            "retryAt": order["failure"]["retryAt"],
            "link": "plan",
        }
    return {
        "now": fmt.iso(ctx.now),
        "mode": ctx.mode,
        "modeChangedAt": None if mode_changed_at is None else fmt.iso(mode_changed_at),
        "liveSince": None,
        "status": status,
        "banner": banner,
    }


def _source(ctx: LedgerContext, series: str, row: FreshnessRow | None) -> dict[str, Any]:
    now = ctx.now
    received = None if row is None or row.fetched_at is None else fmt.iso(row.fetched_at)
    if row is None or row.basis is None:
        return {
            "id": series,
            "state": "unknown",
            "basis": None,
            "receivedAt": received,
            "cadence": "daily",
            "age": 0.0,
        }
    if series == "fx":
        as_of = from_iso(row.basis)
        age_hours = Decimal(weekday_age(as_of, now).total_seconds()) / 3600
        quote = repo.fx_at(ctx.conn, now)
        basis = None if quote is None else str(fmt.rate(quote.rate))
        state = (
            "stale"
            if row.state == FreshState.STALE.value
            else ("late" if age_hours > 24 else "fresh")
        )
        return {
            "id": series,
            "state": state,
            "basis": basis,
            "receivedAt": received,
            "cadence": "daily",
            "age": float(round(age_hours / 24, 2)),
        }
    market = SOURCE_MARKET[series]
    cal = calendar_for(market)
    latest = date.fromisoformat(row.basis)
    lag = ctx.cfg.kr_publication_lag if market is Market.KR else ctx.cfg.us_publication_lag
    published = cal.session_close(latest) + lag
    age = Decimal(max(0.0, (now - published).total_seconds())) / 86400
    if row.state == FreshState.STALE.value:
        state = "stale"
    else:
        current = quote_freshness(Series(series), cal, latest, now, lag)
        state = "fresh" if current.state is FreshState.FRESH else "late"
    return {
        "id": series,
        "state": state,
        "basis": row.basis,
        "receivedAt": received,
        "cadence": "daily",
        "age": float(round(age, 2)),
        "extra": {"market": market.value},
    }


def _run_json(run: RunRow) -> dict[str, Any]:
    out: dict[str, Any] = {
        "at": fmt.iso(run.started_at),
        "result": run.result or "running",
        "seconds": round((run.duration_ms or 0) / 1000, 1),
    }
    return out


def health(ctx: LedgerContext) -> dict[str, Any]:
    rows = {r.series: r for r in repo.all_freshness(ctx.conn)}
    sources = [_source(ctx, s, rows.get(s)) for s in SOURCE_IDS]
    todos: list[dict[str, Any]] = []
    for src in sources:
        if src["state"] == "stale":
            row = rows[src["id"]]
            market = "FX" if src["id"] == "fx" else SOURCE_MARKET[src["id"]].value
            todos.append(
                {
                    "id": f"stale:{src['id']}",
                    "severity": "red",
                    "kind": "stale",
                    "facts": {
                        "market": market,
                        "basisDate": str(row.basis or "")[:10],
                        "tradingDays": row.missing_sessions,
                    },
                    "action": {"kind": "auto-retry", "at": fmt.iso(ctx.next_check)},
                    "effect": "orders-zero-live-blocked",
                }
            )
    failure = _today_check_failure(ctx)
    if failure is not None:
        run, retry_at = failure
        todos.append(
            {
                "id": f"check-failed:{fmt.day(run.run_date)}",
                "severity": "red",
                "kind": "check-failed",
                "facts": {
                    "at": fmt.iso(run.started_at),
                    "reason": "no-quote" if (run.error or "").startswith("no-quote") else "other",
                },
                "action": {"kind": "auto-retry", "at": fmt.iso(retry_at)}
                if retry_at
                else {"kind": "manual"},
                "effect": "no-order-sent",
            }
        )
    for order in _todo_orders(ctx):
        todos.append(
            {
                "id": f"order-failed:{order['id']}",
                "severity": "red",
                "kind": "order-failed",
                "facts": {
                    "date": fmt.day(ctx.open_plan.plan_date) if ctx.open_plan else "",
                    "market": order["market"],
                    "side": order["side"],
                    "reason": order["failure"]["reason"],
                },
                "action": {"kind": "manual"},
                "effect": "other",
            }
        )
    data = DayData(ctx)
    recent: list[dict[str, Any]] = []
    for i in range(13, -1, -1):
        d = ctx.today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        item: dict[str, Any] = {"date": fmt.day(d), "state": data.calendar_state(d)}
        runs = data.runs.get(d, [])
        if runs:
            item["run"] = _run_json(runs[-1])
        recent.append(item)
    fail_count = sum(
        1 for d in data.runs if d > ctx.today - timedelta(days=14) and data.check_failed(d)
    )
    last = ctx.last_check
    last_success = _last_success(ctx)
    stale_count = sum(1 for s in sources if s["state"] == "stale")
    if last is None:
        kind = "before-first"
    elif failure is not None:
        kind = "check-failed"
    elif stale_count or todos:
        kind = "check"
    else:
        kind = "ok"
    summary: dict[str, Any] = {
        "kind": kind,
        "sourcesTotal": len(sources),
        "staleCount": stale_count,
        "todoCount": len(todos),
        "failCount": fail_count,
        "lastCheckAt": None if last is None else fmt.iso(last.started_at),
        "nextCheckAt": fmt.iso(ctx.next_check),
    }
    if last_success is not None:
        summary["lastSuccessAt"] = fmt.iso(last_success.started_at)
    if failure is not None and failure[1] is not None:
        summary["retryAt"] = fmt.iso(failure[1])
    if last is None:
        summary["firstCheckAt"] = fmt.iso(ctx.first_check_at)
    last_run = None
    if last is not None:
        last_run = _run_json(last)
        if last.error:
            last_run["reason"] = "no-quote" if last.error.startswith("no-quote") else "other"
    return {
        "summary": summary,
        "todos": todos,
        "sources": sources,
        "recent14": recent,
        "lastRun": last_run,
    }
