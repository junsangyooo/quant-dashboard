"""The web API and the web app of quant.jsyoo.dev.

    uvicorn autotrade.api.app:app --host 127.0.0.1 --port 8890   (deploy/autotrade.service)

- /api/healthz: no session. /api/auth/*: no session. Every other /api/* needs the 'qsess'
  session cookie; a missing or revoked session is 403 JSON (never 401).
- /docs, /redoc and /openapi.json are off. Unknown /api paths are JSON 404.
- Everything else is the built web app from web/dist (autotrade/api/routes/static.py).
- Every response carries the CSP of CONTRACT.md and the other security headers.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from autotrade.api import errors
from autotrade.api.deps import AppState
from autotrade.api.routes import auth as auth_routes
from autotrade.api.routes import read as read_routes
from autotrade.api.routes import static as static_routes
from autotrade.api.routes import system as system_routes
from autotrade.api.routes import write as write_routes
from autotrade.api.security import load_or_create_secret
from autotrade.api.settings import ApiSettings, default_settings
from autotrade.config import Config, load_config
from autotrade.db.connection import connect
from autotrade.engine.bootstrap import bootstrap
from autotrade.timeutil import UTC

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


def _utc_now() -> datetime:
    return datetime.now(UTC)


def create_app(
    cfg: Config | None = None,
    settings: ApiSettings | None = None,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    config = cfg or load_config()
    api_settings = settings or default_settings(config)
    now = clock or _utc_now

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conn = connect(config.db_path)
        try:
            bootstrap(conn, config, now())
        finally:
            conn.close()
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
        try:
            response = await call_next(request)
        except Exception:  # anything unhandled still answers JSON with the headers
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
