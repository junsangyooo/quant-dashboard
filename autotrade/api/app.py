"""The web API and the web app of quant.jsyoo.dev.

    uvicorn autotrade.api.app:app --host 127.0.0.1 --port 8890   (deploy/autotrade.service)

- /api/healthz: no session. /api/auth/*: no session. Every other /api/* needs the session cookie
  ('__Host-qsess'); a missing or revoked session is 403 JSON (never 401).
- /docs, /redoc and /openapi.json are off. Unknown /api paths are JSON 404.
- Everything else is the built web app from web/dist (autotrade/api/routes/static.py).
- Every response carries the CSP of CONTRACT.md and the other security headers.
- The app never migrates the database (`python -m autotrade.jobs migrate` does, after a backup):
  while the stored schema is not the code's, /api answers 503 schema (autotrade/api/schema.py).
- Unsafe methods (POST, PUT, PATCH, DELETE) must come from this site: SameSite=Strict counts every
  *.jsyoo.dev site as the same site, so the cookie alone does not stop a script on a sibling site
  (CONTRACT.md 세션과 보안, `origin_allowed`).
- An unhandled error answers 500 JSON and its traceback goes to the log (method and path only:
  never headers, cookies or the body, which may hold a PIN).
- Development only: with AUTOTRADE_DEV=1 and a database outside data/ (a dev-seed world),
  AUTOTRADE_FAKE_NOW (ISO 8601, KST without an offset) stops the clock there, and the session
  cookie is 'qsess' without Secure so plain http works. The production unit sets neither variable
  (deploy/autotrade.service unsets them), and on data/autotrade.db they change nothing.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from autotrade.api import errors, schema
from autotrade.api.deps import AppState
from autotrade.api.routes import auth as auth_routes
from autotrade.api.routes import read as read_routes
from autotrade.api.routes import static as static_routes
from autotrade.api.routes import system as system_routes
from autotrade.api.routes import write as write_routes
from autotrade.api.security import load_or_create_secret
from autotrade.api.settings import ApiSettings, default_settings, dev_database, dev_mode
from autotrade.config import Config, load_config
from autotrade.db.connection import connect
from autotrade.timeutil import UTC, parse_cli_time

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
    "form-action 'self'"
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CSP,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
}
UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
SAME_ORIGIN_FETCH = frozenset({"same-origin", "none"})
DEFAULT_PORTS = {"http": 80, "https": 443}

log = logging.getLogger("autotrade.api")


def _utc_now() -> datetime:
    return datetime.now(UTC)


def dev_clock(env: Mapping[str, str], db_path: Path | None = None) -> Callable[[], datetime] | None:
    """The fixed clock of a dev-seed world: AUTOTRADE_FAKE_NOW, honoured only with
    AUTOTRADE_DEV=1 (never set on the server) and never for a database under data/."""
    if env.get("AUTOTRADE_DEV") != "1" or not env.get("AUTOTRADE_FAKE_NOW"):
        return None
    if db_path is not None and not dev_database(db_path):
        log.warning("AUTOTRADE_FAKE_NOW ignored: %s is under data/", db_path)
        return None
    fixed = parse_cli_time(env["AUTOTRADE_FAKE_NOW"])
    return lambda: fixed


def same_host(origin: str, host: str) -> bool:
    """Is the browser's Origin ('https://quant.jsyoo.dev') the site of this request's Host header?
    Hostnames must be equal; a Host with a port must have the origin's port (explicit or its
    scheme's default); a Host without one (nginx passes `$host`) needs the scheme's default."""
    try:
        o = urlsplit(origin)
        h = urlsplit("//" + host)
        origin_port = o.port or DEFAULT_PORTS.get(o.scheme)
        host_port = h.port
    except ValueError:  # a port that is not a number
        return False
    if not o.hostname or o.hostname != h.hostname or origin_port is None:
        return False
    if host_port is None:
        return origin_port == DEFAULT_PORTS.get(o.scheme)
    return host_port == origin_port


def origin_allowed(method: str, headers: Mapping[str, str]) -> bool:
    """CSRF guard for unsafe methods. Allowed: Sec-Fetch-Site same-origin or none, or an Origin
    whose host:port is the request's Host (behind nginx the app sees http while the browser's
    origin is https, so hosts are compared, not schemes). A request with neither header is not a
    browser's (curl, the deploy checks, tests) and passes: it cannot carry the owner's cookie
    unless it already has it."""
    if method not in UNSAFE_METHODS:
        return True
    fetch_site = headers.get("sec-fetch-site")
    origin = headers.get("origin")
    if fetch_site is None and origin is None:
        return True
    if fetch_site is not None and fetch_site.lower() in SAME_ORIGIN_FETCH:
        return True
    host = headers.get("host")
    if origin is None or host is None:
        return False
    return same_host(origin, host)


def _safe_path(request: Request) -> str:
    """The path for the log: no query string, control characters escaped, at most 200 chars."""
    return repr(request.url.path[:200])


def _describe(exc: BaseException) -> str:
    """The exception for the log; a pydantic error lists where it failed, never the input."""
    if isinstance(exc, ValidationError):
        return f"ValidationError at {[e['loc'] for e in exc.errors(include_input=False)]}"
    return f"{type(exc).__name__}: {exc}"


def _log_handler() -> None:
    """A stderr handler for 'autotrade.api' (the unit appends stderr to data/logs/autotrade.log).
    uvicorn configures only its own loggers; added once, records still reach the root logger."""
    if not log.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
        log.addHandler(handler)
        log.setLevel(logging.INFO)


def _log_schema(config: Config) -> None:
    """At startup: say so in the log when /api will answer 503 schema (nothing is changed)."""
    path = config.db_path
    if not path.exists():
        log.warning("no database at %s: /api answers 503 until `autotrade.jobs migrate`", path)
        return
    try:
        conn = connect(path)
        try:
            stored = schema.stored_version(conn)
        finally:
            conn.close()
    except sqlite3.Error as exc:
        log.warning("cannot read %s at startup: %s", path, exc)
        return
    if stored != schema.code_version():
        log.warning(
            "schema %d stored, %d in the code: /api answers 503 until `autotrade.jobs migrate`",
            stored,
            schema.code_version(),
        )


def create_app(
    cfg: Config | None = None,
    settings: ApiSettings | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    _log_handler()
    config = cfg or load_config()
    dev = dev_mode(os.environ, config.db_path)
    api_settings = settings or default_settings(config, dev=dev)
    now = clock or dev_clock(os.environ, config.db_path) or _utc_now
    if os.environ.get("AUTOTRADE_DEV") == "1" and not dev:
        log.warning("AUTOTRADE_DEV=1 ignored: %s is under data/", config.db_path)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _log_schema(config)
        app.state.autotrade = AppState(
            cfg=config,
            settings=api_settings,
            secret=load_or_create_secret(api_settings.secret_path),
            clock=now,
        )
        yield

    app = FastAPI(
        title="autotrade",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    errors.install(app)

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if not origin_allowed(request.method, request.headers):
            response: Response = JSONResponse({"error": "origin"}, status_code=403)
        else:
            try:
                response = await call_next(request)
            except Exception as exc:  # anything unhandled still answers JSON with the headers
                log.error(
                    "unhandled %s %s: %s",
                    request.method,
                    _safe_path(request),
                    _describe(exc),
                    exc_info=None if isinstance(exc, ValidationError) else exc,
                )
                response = JSONResponse({"error": "internal"}, status_code=500)
        for name, value in SECURITY_HEADERS.items():
            response.headers[name] = value
        if request.url.path.startswith("/api/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(system_routes.router)
    app.include_router(auth_routes.router)
    app.include_router(read_routes.router)
    app.include_router(write_routes.router)
    app.include_router(static_routes.router)  # last: the catch-all for the web app
    return app


app = create_app()
