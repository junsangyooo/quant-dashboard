"""JSON errors: {"error": "<code>", "detail"?: {...}} (CONTRACT.md 원칙). Never 401.

A few errors carry fields beside "error", exactly as the contract's write table shows them:
{error:'pin', remaining}, {error:'locked', until, scope}.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: str,
        detail: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(code)
        self.status = status
        self.code = code
        self.detail = detail
        self.extra = extra or {}


def error_body(code: str, detail: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"error": code, **extra}
    if detail is not None:
        body["detail"] = detail
    return body


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> Response:
        return JSONResponse(error_body(exc.code, exc.detail, **exc.extra), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _bad_request(request: Request, exc: RequestValidationError) -> Response:
        fields = [".".join(str(p) for p in e.get("loc", ())) for e in exc.errors()]
        return JSONResponse(error_body("bad-request", {"fields": fields}), status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException) -> Response:
        code = {404: "not-found", 405: "method-not-allowed"}.get(exc.status_code, "http-error")
        return JSONResponse(error_body(code), status_code=exc.status_code)
