"""GET /api/shell (the header on every screen) and GET /api/health (SCR-HEALTH).

Phase 1 has three data sources (Korean and US closes, the rate). The Toss link and the Toss
balance check join them once the live link matters (autotrade/PHASE3.md 2.7, api/views/live.py),
with the live to-dos (a cancel that failed, an account that does not match, the link itself).
Those show whatever the mode is. While live is on, `liveCash` says what the live ledger's money
waits for (D47·D48): it is never a to-do and never counted. Push devices do not exist yet: no
row.

'PIN 실패 급증' (autotrade/api/auth.py) is a red manual to-do, first in the list and counted in
the header's '할 일 n', from the moment it is raised until `python -m autotrade.jobs unlock`.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from autotrade.api.auth import pin_alert
from autotrade.api.views import fmt
from autotrade.api.views import live as live_view
from autotrade.api.views.context import LedgerContext
from autotrade.api.views.history import OK_RESULTS, DayData, failure_reason
from autotrade.api.views.orders import waiting_retry
from autotrade.db import repo
from autotrade.db.models import FreshnessRow, RunRow
from autotrade.domain.instruments import Market
from autotrade.market.calendar import CalendarRangeError, calendar_for
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
    """Failed orders whose retry is still to come."""
    return [o for stage in ctx.stages or [] for o in stage["orders"] if waiting_retry(o)]


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


def _pin_todo(conn: sqlite3.Connection) -> dict[str, Any] | None:
    """'PIN 실패 급증': facts since (raised), count (wrong PINs counted for it), lastAt (the latest
    wrong PIN on record, left out when none), closed (1 = new logins closed until unlock)."""
    alert = pin_alert(conn)
    if alert is None:
        return None
    facts: dict[str, Any] = {
        "since": fmt.iso(alert.since),
        "count": alert.count,
        "closed": 1 if alert.closed else 0,
    }
    if alert.last_at is not None:
        facts["lastAt"] = fmt.iso(alert.last_at)
    return {
        "id": "pin-failures",
        "severity": "red",
        "kind": "pin-failures",
        "facts": facts,
        "action": {"kind": "manual"},
        "effect": "other",
    }


def _last_success(ctx: LedgerContext) -> RunRow | None:
    runs = [
        r for r in repo.runs_of_ledger(ctx.conn, ctx.ledger_id, "check") if r.result in OK_RESULTS
    ]
    runs = [r for r in runs if r.started_at <= ctx.now]
    return runs[-1] if runs else None


def shell(ctx: LedgerContext, mode_changed_at: datetime | None) -> dict[str, Any]:
    failure = _today_check_failure(ctx)
    todo = _todo_orders(ctx)
    pin_todo = 1 if _pin_todo(ctx.conn) is not None else 0
    live_manual, cancels = live_view.header_counts(ctx.conn, ctx.cfg, ctx.now)
    todo_count = (
        len(todo)
        + (1 if failure is not None and failure[1] is None else 0)
        + pin_todo
        + live_manual
    )
    stale = ctx.stale_source() if ctx.status.value == "quote-wait" else None
    retries = _retry_orders(ctx)
    # AI-rule sources (filings, the AI CLI) count once dead for more than a trading day.
    ai_dead = ctx.ai_rule.header_causes()
    status: dict[str, Any]
    # Before the first check there are no order to-dos or failed checks: only 'PIN 실패 급증'
    # can make a count then, and it outranks '첫 확인 전'. A live order that could not be
    # cancelled outranks everything: it may still fill.
    if cancels:
        status = {"kind": "cancel-failed", "count": cancels}
    elif todo_count:
        status = {"kind": "todo", "count": todo_count}
    elif ctx.last_check is None:
        status = {"kind": "before-first", "firstCheckAt": fmt.iso(ctx.first_check_at)}
    elif failure is not None:
        status = {"kind": "check-failed", "at": fmt.iso(failure[0].started_at)}
    elif stale is not None or retries or ai_dead:
        causes = (1 if stale is not None else 0) + len(retries) + ai_dead
        status = {"kind": "check", "count": causes}
    else:
        last = _last_success(ctx)
        status = {"kind": "ok", "lastCheckAt": fmt.iso((last or ctx.last_check).started_at)}

    banner: dict[str, Any] | None = None
    plan_day = None if ctx.open_plan is None else fmt.day(ctx.open_plan.plan_date)
    failed_cancels = live_view.cancel_failed_orders(ctx.conn) if cancels else []
    if failed_cancels:
        first = failed_cancels[0]
        banner = {
            "kind": "cancel-failed",
            "market": first["market"],
            "side": first["side"],
            "link": "mode",
        }
    elif failure is not None:
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
    since = live_view.live_since(ctx.conn)
    return {
        "now": fmt.iso(ctx.now),
        "mode": ctx.mode,
        "modeChangedAt": None if mode_changed_at is None else fmt.iso(mode_changed_at),
        "liveSince": None if since is None else fmt.iso(since),
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


def _missing_dates(row: FreshnessRow) -> list[date]:
    """The sessions a stale market's closes are missing ('10/05·10/06 종가를 못 받았어요')."""
    market = SOURCE_MARKET.get(row.series)
    if market is None or not row.basis or not row.expected:
        return []
    try:
        latest, expected = date.fromisoformat(row.basis[:10]), date.fromisoformat(row.expected[:10])
        return calendar_for(market).trading_days(latest, expected)
    except (ValueError, CalendarRangeError):
        return []


def _run_json(run: RunRow) -> dict[str, Any]:
    out: dict[str, Any] = {
        "at": fmt.iso(run.started_at),
        "result": run.result or "running",
        "seconds": round((run.duration_ms or 0) / 1000, 1),
    }
    if run.result in ("failed", "todo"):
        out["reason"] = failure_reason(run)
    return out


def health(ctx: LedgerContext, *, include_live: bool = True) -> dict[str, Any]:
    """include_live=False leaves out the Toss rows and the live to-dos (the mode screen's
    '작동' check judges the engine's own data; the Toss link has its own row there)."""
    rows = {r.series: r for r in repo.all_freshness(ctx.conn)}
    sources = [_source(ctx, s, rows.get(s)) for s in SOURCE_IDS]
    if include_live:
        sources += live_view.sources(ctx.conn, ctx.cfg, ctx.now)
    sources += ctx.ai_rule.sources()  # filings, ai-cli, metric-table where the AI rule runs
    todos: list[dict[str, Any]] = []
    pin_todo = _pin_todo(ctx.conn)
    if pin_todo is not None:
        todos.append(pin_todo)
    for src in sources:
        if src["state"] == "stale" and src["id"] in SOURCE_IDS:
            row = rows[src["id"]]
            market = "FX" if src["id"] == "fx" else SOURCE_MARKET[src["id"]].value
            facts: dict[str, Any] = {
                "market": market,
                "basisDate": str(row.basis or "")[:10],
                "tradingDays": row.missing_sessions,
            }
            missing = _missing_dates(row)
            if missing:
                facts["missingDates"] = ",".join(fmt.day(d) for d in missing)
            todos.append(
                {
                    "id": f"stale:{src['id']}",
                    "severity": "red",
                    "kind": "stale",
                    "facts": facts,
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
                "facts": {"at": fmt.iso(run.started_at), "reason": failure_reason(run)},
                "action": {"kind": "auto-retry", "at": fmt.iso(retry_at)}
                if retry_at
                else {"kind": "manual"},
                "effect": "no-order-sent",
            }
        )
    for order in _todo_orders(ctx):
        # A live order the broker refused is 'order-rejected' (CONTRACT, phase 3).
        rejected = ctx.ledger_id == "live" and order["failure"]["reason"] == "broker-rejected"
        todos.append(
            {
                "id": f"order-failed:{order['id']}",
                "severity": "red",
                "kind": "order-rejected" if rejected else "order-failed",
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
    todos += ctx.ai_rule.todos()
    if include_live:
        todos += live_view.todos(ctx.conn, ctx.cfg, ctx.now)
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
    stale_count = sum(1 for s in sources if s["state"] in ("stale", "maintenance"))
    if last is None:
        kind = "before-first"
    elif failure is not None:
        kind = "check-failed"
    elif stale_count or any(t["severity"] == "red" for t in todos):
        kind = "check"  # a yellow card alone is '정상 · 할 일 n'
    else:
        kind = "ok"
    summary: dict[str, Any] = {
        "kind": kind,
        "sourcesTotal": len(sources),
        "staleCount": stale_count,
        # '할 일 n': the cards the owner has to act on himself (action 'manual'): every yellow
        # card, and a red one once the engine has stopped retrying. Retried faults are counted by
        # staleCount and failCount.
        "todoCount": sum(1 for t in todos if t["action"]["kind"] == "manual"),
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
            last_run["reason"] = failure_reason(last)
    return {
        "summary": summary,
        "todos": todos,
        "sources": sources,
        "recent14": recent,
        "lastRun": last_run,
        # The push devices (what '알림 기기' expands to). Web push comes in phase 3: none yet.
        "devices": [],
        # D47·D48 while live is on: information beside the to-dos, never one of them.
        "liveCash": live_view.live_cash(ctx) if include_live else None,
    }
