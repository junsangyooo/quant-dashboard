"""오류 → HTTP 응답(ARCHITECTURE 2절 API 층 '오류 → HTTP 상태' · TASKS P1-09).

오류 종류와 HTTP 상태는 지금과 똑같이 이어 줘요(오류 객체의 `status` · `kind` · 덧붙인 값을 그대로 · 오류 번호로 바꾸는 일은
열린 질문 Q-N23의 답 뒤). 받은 값을 응답에 되돌려 보내지 않고, 모르는 예외는 종류와 위치만 기록해요.
텔레그램 봇 오류(`ports.TelegramError`)는 API 층이 포트를 가져오지 않아서 조립이 `with_kind`로 등록해요.
"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..copy import texts as T
from ..domain import copytext as ct
from ..domain.engine import BacktestError as BacktestErrorV2
from ..run.data import MarketDataError
from ..run.live import LiveError
from ..run.paper import PaperError
from ..security.vault import VaultError
from ..services import data_admin as dm
from .http import err

log = logging.getLogger("quant-mvp")


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra


async def with_kind(_: Request, exc: Exception) -> JSONResponse:
    """`message` · `status` · `kind`를 가진 오류(텔레그램 봇 오류)."""
    return err(exc.message, exc.status, kind=exc.kind)  # type: ignore[attr-defined]


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def on_api(_: Request, exc: ApiError) -> JSONResponse:
        return err(exc.message, exc.status, **exc.extra)

    @app.exception_handler(ct.FormatError)
    async def on_format_v3(_: Request, exc: ct.FormatError) -> JSONResponse:
        if exc.kind == "graph":
            return err(exc.message, 400, kind="graph", title=ct.BAD_LINKS, detail=exc.detail)
        return err(exc.message, 400, kind=exc.kind)

    @app.exception_handler(dm.DataError)
    async def on_data(_: Request, exc: dm.DataError) -> JSONResponse:
        return err(exc.message, exc.status)

    @app.exception_handler(LiveError)
    async def on_live(_: Request, exc: LiveError) -> JSONResponse:
        return err(exc.message, exc.status)

    @app.exception_handler(VaultError)
    async def on_vault(_: Request, exc: VaultError) -> JSONResponse:
        return err(exc.message, exc.status, **exc.extra)

    @app.exception_handler(MarketDataError)
    async def on_market(_: Request, exc: MarketDataError) -> JSONResponse:
        if exc.kind == "symbol":
            return err(exc.message, 400, kind="symbol", symbols=exc.symbols)
        return err(exc.message, 502, kind="market")

    @app.exception_handler(BacktestErrorV2)
    async def on_bt2(_: Request, exc: BacktestErrorV2) -> JSONResponse:
        return err(exc.message, 400)

    @app.exception_handler(PaperError)
    async def on_paper2(_: Request, exc: PaperError) -> JSONResponse:
        return err(exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def on_validation(_: Request, __: RequestValidationError) -> JSONResponse:
        return err(T.bad_request, 400)  # 받은 값을 되돌려 보내지 않는다

    @app.exception_handler(StarletteHTTPException)
    async def on_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return err("없는 주소예요" if exc.status_code == 404 else "요청을 받지 못했어요", exc.status_code)

    @app.exception_handler(Exception)
    async def on_any(_: Request, exc: Exception) -> JSONResponse:
        # 예외 글에는 무엇이 들었는지 모르니 종류와 위치만 남긴다
        where = traceback.extract_tb(exc.__traceback__)[-1:] if exc.__traceback__ else []
        log.error("unhandled %s at %s", type(exc).__name__, [f"{f.filename}:{f.lineno}" for f in where])
        return err(T.unknown_error, 500)
