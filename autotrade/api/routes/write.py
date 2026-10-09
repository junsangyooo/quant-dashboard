"""Write endpoints (CONTRACT.md 쓰기) besides auth. Phase 1: live mode and web push are not
available — they answer 409 and 501 instead of pretending."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict

from autotrade.api import auth
from autotrade.api.deps import app_state, client_ip, current_session, get_conn
from autotrade.api.errors import ApiError
from autotrade.api.views import fmt
from autotrade.api.views.account import LOCKED_EVENTS, NOTIFY_DEFAULTS, effective_events
from autotrade.db import auth_repo, repo
from autotrade.db.auth_repo import SessionRow
from autotrade.db.connection import transaction
from autotrade.engine.bootstrap import MODE
from autotrade.timeutil import to_iso

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


@router.post("/account/pin", status_code=204)
def change_pin(
    body: PinChangeBody,
    request: Request,
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
    body: NotificationsBody, request: Request, conn: sqlite3.Connection = Depends(get_conn)
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
def turn_live_on(body: LiveBody) -> Response:
    raise ApiError(409, "blocked", {"cause": "live-not-available"})


@router.post("/mode/paper")
def turn_live_off(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    """Idempotent. In phase 1 the mode is always paper, so nothing changes."""
    if (repo.get_setting(conn, MODE) or "paper") != "paper":
        at = app_state(request).clock()
        with transaction(conn):
            repo.set_setting(conn, MODE, "paper", at)
            repo.set_setting(conn, "mode.changed_at", to_iso(at), at)
    return {"mode": "paper", "cancelFailed": []}


@router.post("/mode/cancel-retry")
def cancel_retry() -> dict[str, Any]:
    return {"cancelFailed": []}


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
