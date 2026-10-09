"""Request dependencies: the database connection, the clock, the caller's address and session."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, Request

from autotrade.api.errors import ApiError
from autotrade.api.security import read_token
from autotrade.api.settings import COOKIE_NAME, ApiSettings
from autotrade.config import Config
from autotrade.db import auth_repo
from autotrade.db.auth_repo import SessionRow
from autotrade.db.connection import connect, transaction

TRUSTED_PROXIES = frozenset({"127.0.0.1", "::1"})


@dataclass(frozen=True)
class AppState:
    cfg: Config
    settings: ApiSettings
    secret: bytes
    clock: Callable[[], datetime]


def app_state(request: Request) -> AppState:
    state: AppState = request.app.state.autotrade
    return state


def get_conn(request: Request) -> Iterator[sqlite3.Connection]:
    conn = connect(app_state(request).cfg.db_path, check_same_thread=False)
    try:
        yield conn
    finally:
        conn.close()


def client_ip(request: Request) -> str:
    """The caller's address. X-Forwarded-For is read only when the peer is the local proxy
    (nginx), and then the rightmost hop that is not the proxy itself is used — the one nginx
    appended, which a client cannot forge."""
    peer = request.client.host if request.client else "unknown"
    if peer in TRUSTED_PROXIES:
        forwarded = request.headers.get("x-forwarded-for", "")
        for hop in reversed([h.strip() for h in forwarded.split(",") if h.strip()]):
            if hop not in TRUSTED_PROXIES:
                return hop
    return peer


def current_session(request: Request, conn: sqlite3.Connection = Depends(get_conn)) -> SessionRow:
    """The open session behind the cookie, or 403 (never 401, CONTRACT.md 원칙)."""
    state = app_state(request)
    at = state.clock()
    session_id = read_token(request.cookies.get(COOKIE_NAME), state.secret, at.timestamp())
    if session_id is None:
        raise ApiError(403, "session")
    row = auth_repo.get_session(conn, session_id)
    if row is None or not row.is_open(at):
        raise ApiError(403, "session")
    if at - row.last_seen_at >= state.settings.touch_interval:
        with transaction(conn):
            auth_repo.touch_session(conn, session_id, at)
    return row
