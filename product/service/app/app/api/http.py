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

COOKIE = "qm_session"
CSRF_COOKIE = "qm_csrf"  # 화면 스크립트가 읽어 X-CSRF-Token 머리글로 되돌려 보내요(두 번 보내기)
CSRF_HEADER = "x-csrf-token"
CONFIRM_HEADER = "x-confirm-token"  # 비밀번호 다시 받기로 받은 1회용 토큰

NeedConfirm = Callable[[Request, str], None]


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
