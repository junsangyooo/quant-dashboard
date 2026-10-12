"""Write endpoints (CONTRACT.md 쓰기) besides auth. Web push is not available: 501 instead of
pretending. The live mode switch (autotrade/PHASE3.md 2.6) checks only what the tick recorded:
this process cannot reach Toss; the cancels at the broker are requests the tick carries out.

Bodies come through deps.session_body, never as a body parameter: the session is checked first,
so a request without one is 403 session whatever its body (tests/autotrade/api pins this)."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict

from autotrade.api import auth
from autotrade.api.deps import app_state, client_ip, current_session, get_conn, session_body
from autotrade.api.errors import ApiError
from autotrade.api.views import fmt
from autotrade.api.views import live as live_view
from autotrade.api.views import mode as mode_view
from autotrade.api.views.account import LOCKED_EVENTS, NOTIFY_DEFAULTS, effective_events
from autotrade.api.views.context import LedgerContext
from autotrade.db import auth_repo, live_repo
from autotrade.db.auth_repo import SessionRow
from autotrade.db.connection import transaction
from autotrade.engine import live
from autotrade.engine.live import LiveStartError, PreviewData

router = APIRouter(prefix="/api", dependencies=[Depends(current_session)])


class PinChangeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current: str
    next: str


class LiveBody(BaseModel):
    pin: str | None = None
    confirm: bool | None = None
    previewHash: str | None = None  # noqa: N815 — the contract's field name


class NotificationsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    events: dict[str, bool] | None = None
    hideAmounts: bool | None = None  # noqa: N815 — the contract's field name


PIN_CHANGE_BODY = session_body(PinChangeBody)
NOTIFICATIONS_BODY = session_body(NotificationsBody)
LIVE_BODY = session_body(LiveBody)


@router.post("/account/pin", status_code=204)
def change_pin(
    request: Request,
    body: PinChangeBody = Depends(PIN_CHANGE_BODY),
    session: SessionRow = Depends(current_session),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Response:
    state = app_state(request)
    auth.change_pin(
        conn,
        state.settings,
        state.secret,
        body.current,
        body.next,
        session.session_id,
        client_ip(request),
        state.clock(),
    )
    return Response(status_code=204)


@router.put("/account/notifications")
def save_notifications(
    request: Request,
    body: NotificationsBody = Depends(NOTIFICATIONS_BODY),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    at = app_state(request).clock()
    with transaction(conn):
        current = auth_repo.get_prefs(conn)
        events = effective_events(current)
        for key, on in (body.events or {}).items():
            if key not in NOTIFY_DEFAULTS:
                raise ApiError(400, "unknown-event", {"event": key})
            if key in LOCKED_EVENTS and not on:
                raise ApiError(400, "locked-event", {"event": key})
            events[key] = on
        hide = (
            body.hideAmounts
            if body.hideAmounts is not None
            else bool(current and current.hide_amounts)
        )
        auth_repo.save_prefs(conn, events, hide, at)
    return {"savedAt": fmt.iso(at)}


@router.post("/mode/live")
def turn_live_on(
    request: Request,
    body: LiveBody = Depends(LIVE_BODY),
    session: SessionRow = Depends(current_session),
    conn: sqlite3.Connection = Depends(get_conn),
) -> dict[str, Any]:
    """PIN + confirmation + the preview the owner saw (인계 13). Idempotent: when the mode is
    live already, 200 at once."""
    state = app_state(request)
    at = state.clock()
    if body.confirm is not True or not body.previewHash:
        raise ApiError(
            400,
            "bad-request",
            {"fields": ["confirm" if body.confirm is not True else "previewHash"]},
        )
    if live.mode_of(conn) == live.LIVE:
        return {"mode": "live"}
    auth.confirm_pin(
        conn,
        state.settings,
        state.secret,
        body.pin or "",
        session.session_id,
        client_ip(request),
        at,
    )
    paper = LedgerContext(conn, state.cfg, "paper", at)
    found = mode_view.checks(paper, at)
    if not found.can_turn_on["ok"]:
        raise ApiError(409, "blocked", {"cause": found.can_turn_on["cause"]})
    data = found.preview
    if not isinstance(data, PreviewData):  # pragma: no cover — can_turn_on said ok
        raise ApiError(409, "blocked", {"cause": "preview"})
    stored = live_repo.get_preview(conn, body.previewHash)
    if live.preview_changed(stored, data):
        payload = mode_view.preview_json(data)
        with transaction(conn):
            mode_view.store(conn, data, payload)
        raise ApiError(409, "preview-changed", extra={"preview": payload})
    try:
        with transaction(conn):
            if live.mode_of(conn) != live.LIVE:  # another request may have won the race
                live.turn_on(conn, state.cfg, at, data)
    except LiveStartError as exc:
        raise ApiError(409, "blocked", {"cause": "preview"}) from exc
    return {"mode": "live"}


@router.post("/mode/paper")
def turn_live_off(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    """Idempotent; a session is enough (인계 7: no PIN, also while the PIN is locked). Orders
    that never left are cancelled now; orders at the broker are cancel requests the next tick
    carries out (`cancelPending`)."""
    at = app_state(request).clock()
    with transaction(conn):
        live.turn_off(conn, at)
    return {
        "mode": "paper",
        "cancelFailed": live_view.cancel_failed_orders(conn),
        "cancelPending": live_view.cancel_pending_orders(conn),
    }


@router.post("/mode/cancel-retry")
def cancel_retry(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    """'취소 다시 시도': the failed cancels are asked again; the tick tries within 5 minutes."""
    at = app_state(request).clock()
    with transaction(conn):
        live.retry_cancels(conn, at)
    return {
        "cancelFailed": live_view.cancel_failed_orders(conn),
        "cancelPending": live_view.cancel_pending_orders(conn),
    }


@router.post("/account/push")
def push_subscribe() -> Response:
    raise ApiError(501, "not-implemented", {"feature": "push"})


@router.post("/account/push/test")
def push_test() -> Response:
    raise ApiError(501, "not-implemented", {"feature": "push"})


@router.delete("/account/push")
def push_unsubscribe() -> Response:
    """Stop pushing to this device (phase 3)."""
    raise ApiError(501, "not-implemented", {"feature": "push"})
