"""POST /api/auth/pin · /logout · /logout-others (CONTRACT.md 쓰기).

The session cookie is '__Host-qsess' (Secure, Path=/, no Domain, HttpOnly, SameSite=Strict); in
development over plain http it is 'qsess' without Secure (autotrade/api/settings.py).
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict

from autotrade.api import auth
from autotrade.api.deps import app_state, client_ip, current_session, get_conn
from autotrade.api.errors import ApiError
from autotrade.api.security import is_valid_pin, read_token
from autotrade.db.auth_repo import SessionRow

router = APIRouter(prefix="/api/auth")


class PinBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pin: str


def _clear_cookie(request: Request, response: Response) -> None:
    settings = app_state(request).settings
    response.delete_cookie(
        settings.cookie_name,
        path="/",
        secure=settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )


@router.post("/pin", status_code=204)
def login(
    body: PinBody, request: Request, conn: sqlite3.Connection = Depends(get_conn)
) -> Response:
    state = app_state(request)
    if not is_valid_pin(body.pin):
        raise ApiError(400, "invalid-pin")
    issued = auth.login(
        conn,
        state.settings,
        state.secret,
        body.pin,
        client_ip(request),
        request.headers.get("user-agent"),
        state.clock(),
    )
    response = Response(status_code=204)
    response.set_cookie(
        state.settings.cookie_name,
        issued.token,
        max_age=int(state.settings.session_ttl.total_seconds()),
        path="/",
        secure=state.settings.cookie_secure,
        httponly=True,
        samesite="strict",
    )
    return response


@router.post("/logout", status_code=204)
def logout(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> Response:
    state = app_state(request)
    at = state.clock()
    token = request.cookies.get(state.settings.cookie_name)
    session_id = read_token(token, state.secret, at.timestamp())
    if session_id is not None:
        auth.logout(conn, session_id, at)
    response = Response(status_code=204)
    _clear_cookie(request, response)
    return response


@router.post("/logout-others", status_code=204)
def logout_others(
    request: Request,
    session: SessionRow = Depends(current_session),
    conn: sqlite3.Connection = Depends(get_conn),
) -> Response:
    auth.logout_others(conn, session.session_id, app_state(request).clock())
    return Response(status_code=204)
