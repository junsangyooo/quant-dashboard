"""Request dependencies: the database connection, the clock, the caller's address and session."""

from __future__ import annotations

import sqlite3
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from datetime import datetime
from email.message import Message
from typing import TypeVar

from fastapi import Depends, Request
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError

from autotrade.api import schema
from autotrade.api.errors import ApiError
from autotrade.api.security import read_token
from autotrade.api.settings import ApiSettings
from autotrade.config import Config
from autotrade.db import auth_repo
from autotrade.db.auth_repo import SessionRow
from autotrade.db.connection import connect, transaction

TRUSTED_PROXIES = frozenset({"127.0.0.1", "::1"})

Body = TypeVar("Body", bound=BaseModel)


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
    """A connection for this request, only to a database at the code's schema (else 503 schema,
    autotrade/api/schema.py; 503 db when the file cannot be opened). A missing database is not
    created here."""
    path = app_state(request).cfg.db_path
    if str(path) != ":memory:" and not path.exists():
        raise schema.mismatch(0)
    try:
        conn = connect(path, check_same_thread=False)
    except sqlite3.Error as exc:
        raise ApiError(503, "db") from exc
    try:
        schema.require_current(conn)
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
    token = request.cookies.get(state.settings.cookie_name)
    session_id = read_token(token, state.secret, at.timestamp())
    if session_id is None:
        raise ApiError(403, "session")
    row = auth_repo.get_session(conn, session_id)
    if row is None or not row.is_open(at):
        raise ApiError(403, "session")
    if at - row.last_seen_at >= state.settings.touch_interval:
        with transaction(conn):
            auth_repo.touch_session(conn, session_id, at)
    return row


def _json_content_type(value: str | None) -> bool:
    """No content type, application/json or application/*+json (what FastAPI itself accepts)."""
    if not value:
        return True
    message = Message()
    message["content-type"] = value
    subtype = message.get_content_subtype()
    return message.get_content_maintype() == "application" and (
        subtype == "json" or subtype.endswith("+json")
    )


def session_body(model: type[Body]) -> Callable[..., Awaitable[Body]]:
    """The JSON body of a protected route, read only after the session check: without a session
    a malformed body is 403 session like any other request, not 400 (a body parameter would make
    FastAPI read and parse it before any dependency runs). Errors are 400 bad-request with the
    field paths, as for FastAPI's own validation; the input values are not kept."""

    async def read(request: Request, _: SessionRow = Depends(current_session)) -> Body:
        if not _json_content_type(request.headers.get("content-type")):
            raise RequestValidationError([{"loc": ("body",), "type": "content-type"}])
        raw = await request.body()
        try:
            return model.model_validate_json(raw or b"null")
        except ValidationError as exc:
            errors = [
                {"loc": ("body", *e["loc"]), "type": e["type"]}
                for e in exc.errors(include_input=False, include_url=False)
            ]
            raise RequestValidationError(errors) from None

    return read
