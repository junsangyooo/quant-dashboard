"""API 층이 같이 쓰는 HTTP 도우미(ARCHITECTURE 2절 API 층 · TASKS P1-09): 오류 응답 꼴 · JSON 몸통 읽기 · 세션 쿠키 ·
비밀번호 다시 받기 토큰 머리글.

- 오류 응답은 늘 `{"error": "<화면에 보여도 되는 글>", ...}`(받은 값을 되돌려 보내지 않음).
- 쿠키: 세션(`qm_session` · httponly) · CSRF 값(`qm_csrf` · 화면 스크립트가 읽어 `X-CSRF-Token` 머리글로 되돌려 보냄) ·
  둘 다 SameSite=Strict · 경로 `/`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from ..security.vault import SESSION_S, Vault, VaultError
from .models import ApiModel, Bool, Int, Str, opt

COOKIE = "qm_session"
CSRF_COOKIE = "qm_csrf"  # 화면 스크립트가 읽어 X-CSRF-Token 머리글로 되돌려 보내요(두 번 보내기)
CSRF_HEADER = "x-csrf-token"
CONFIRM_HEADER = "x-confirm-token"  # 비밀번호 다시 받기로 받은 1회용 토큰

NeedConfirm = Callable[[Request, str], None]


class ErrorBody(ApiModel):
    """오류 응답(4xx · 5xx): 화면에 보여도 되는 글 한 줄 + 오류마다 덧붙는 값(받은 값은 되돌려 보내지 않음)."""

    error: Str
    need_login: Bool = opt()  # 401 세션 없음 · 만료(로그인 화면으로)
    csrf: Bool = opt()  # 403 CSRF 값이 맞지 않음
    tries_left: Int = opt()  # 401 비밀번호 틀림(남은 횟수)
    locked_for: Int = opt()  # 429 잠금(남은 초)
    need_confirm: Bool = opt()  # 403 비밀번호 다시 받기(SPEC 7-4)
    action: Str = opt()
    title: Str = opt()
    kind: Str = opt()  # 형식 · 시세 · 텔레그램 오류의 종류
    detail: Str = opt()  # 형식 오류의 자세한 글
    symbols: list[Str] = opt()  # 일봉이 없는 종목 코드


ERRORS: dict[int | str, dict[str, Any]] = {"default": {"model": ErrorBody, "description": "error"}}


class OkOut(ApiModel):
    ok: Bool


def err(message: str, status: int = 400, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": message, **extra}, status_code=status)


async def json_body(request: Request) -> dict[str, Any]:
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise VaultError("JSON으로 보내 주세요", 415)
    try:
        data = await request.json()
    except ValueError:
        raise VaultError("요청 형식이 맞지 않아요") from None
    if not isinstance(data, dict):
        raise VaultError("요청 형식이 맞지 않아요")
    return data


def set_session_cookies(resp: Response, token: str, csrf_for: Callable[[str], str]) -> None:
    resp.set_cookie(
        COOKIE, token, max_age=SESSION_S, httponly=True, samesite="strict", path="/"
    )
    resp.set_cookie(
        CSRF_COOKIE, csrf_for(token), max_age=SESSION_S, httponly=False, samesite="strict", path="/"
    )


def clear_session_cookies(resp: Response) -> None:
    resp.delete_cookie(COOKIE, path="/")
    resp.delete_cookie(CSRF_COOKIE, path="/")


def confirmer(vault: Vault) -> NeedConfirm:
    """돈이 움직이는 일(SPEC 7-4)의 1회용 토큰 확인(`app.state.need_confirm` · 없거나 다른 일이면 403 `need_confirm`)."""

    def need_confirm(request: Request, action: str) -> None:
        vault.use_confirm(request.headers.get(CONFIRM_HEADER), action)

    return need_confirm
