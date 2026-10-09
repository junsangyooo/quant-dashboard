"""Read endpoints (CONTRACT.md 읽기). Thin: resolve the ledger, build the context, call a view."""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Request

from autotrade.api.deps import app_state, current_session, get_conn
from autotrade.api.errors import ApiError
from autotrade.api.views import account as account_view
from autotrade.api.views import health as health_view
from autotrade.api.views import history as history_view
from autotrade.api.views import home as home_view
from autotrade.api.views import mode as mode_view
from autotrade.api.views import plan as plan_view
from autotrade.api.views import rules as rules_view
from autotrade.api.views.context import LedgerContext
from autotrade.db import auth_repo, repo
from autotrade.db.auth_repo import SessionRow
from autotrade.engine.bootstrap import MODE
from autotrade.timeutil import from_iso

router = APIRouter(prefix="/api", dependencies=[Depends(current_session)])

LedgerParam = Literal["paper", "live"]
MODE_CHANGED_AT = "mode.changed_at"


def context(request: Request, conn: sqlite3.Connection, ledger: str | None) -> LedgerContext:
    """The asked ledger, or the current mode's. A ledger that never started is 404, unless it is
    the current mode's (then the screens show their 'before the first check' state)."""
    mode = repo.get_setting(conn, MODE) or "paper"
    ledger_id = ledger or mode
    ctx = LedgerContext(conn, app_state(request).cfg, ledger_id, app_state(request).clock())
    if not ctx.started and ledger_id != mode:
        raise ApiError(404, "no-ledger", {"ledger": ledger_id})
    return ctx


@router.get("/shell")
def shell(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    ctx = context(request, conn, None)
    changed = repo.get_setting(conn, MODE_CHANGED_AT)
    return health_view.shell(ctx, from_iso(changed) if changed else None)


@router.get("/home")
def home(
    request: Request,
    ledger: LedgerParam | None = None,
    period: Literal["1m", "3m", "1y", "all"] | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    return home_view.home(context(request, conn, ledger), period)


@router.get("/home/breakdown")
def breakdown(
    request: Request,
    ledger: LedgerParam | None = None,
    period: Literal["1m", "3m", "1y", "all"] | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    return home_view.breakdown(context(request, conn, ledger), period)


@router.get("/plan")
def plan(
    request: Request,
    ledger: LedgerParam | None = None,
    drift: Literal["3m", "1y", "all"] | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    return plan_view.plan(context(request, conn, ledger), drift)


@router.get("/history")
def history(
    request: Request,
    ledger: LedgerParam | None = None,
    year: int | None = Query(None, ge=2000, le=2100),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    return history_view.history(context(request, conn, ledger), year)


@router.get("/day/{day}")
def day(
    day: date,
    request: Request,
    ledger: LedgerParam | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    return history_view.day(context(request, conn, ledger), day)


@router.get("/rules")
def rules(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return rules_view.rule_list(context(request, conn, None))


@router.get("/rules/{rule_id}")
def rule(
    rule_id: str,
    request: Request,
    lane: str | None = None,
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    ctx = context(request, conn, None)
    if rule_id != ctx.rule.rule_id:
        raise ApiError(404, "not-found", {"rule": rule_id})
    return rules_view.rule_detail(ctx)


@router.get("/health")
def health(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return health_view.health(context(request, conn, None))


@router.get("/mode")
def mode(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    return mode_view.mode(context(request, conn, None))


@router.get("/account")
def account(
    session: SessionRow = Depends(current_session),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    return account_view.account(session, auth_repo.get_prefs(conn))
