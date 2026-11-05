"""바깥 문 미들웨어(QUALITY S4 · TASKS P1-09): 호스트 · 출처 검사 → 세션 → CSRF → 보안 머리글.

허용 목록 · CSRF 값 셈은 보안 층(`security/access.py`)이고, 여기는 그 값으로 요청을 막고 응답에 머리글을 붙여요.
로그인 없이 닿는 API는 `PUBLIC_API` 다섯 개뿐이에요.
"""

from __future__ import annotations

from fastapi import FastAPI, Request

from ..security.access import Csrf
from ..security.vault import Vault
from .http import COOKIE, CSRF_HEADER, err

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
PUBLIC_API = {"/api/health", "/api/state", "/api/setup", "/api/login", "/api/recover"}


def install_guard(app: FastAPI, *, vault: Vault, allowed_hosts: set[str], allowed_origins: set[str],
                  csrf: Csrf) -> None:
    @app.middleware("http")
    async def guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        host = request.headers.get("host", "")
        if host not in allowed_hosts:
            return err("이 주소로는 열 수 없어요", 403)
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD") and origin and origin not in allowed_origins:
            return err("다른 사이트에서 온 요청은 받지 않아요", 403)
        path = request.url.path
        if path.startswith("/api/") and path not in PUBLIC_API:
            session = request.cookies.get(COOKIE)
            if not vault.session_ok(session):
                return err("다시 로그인해 주세요", 401, need_login=True)
            # 바꾸는 요청은 CSRF 값이 세션과 맞아야 해요(쿠키는 SameSite=Strict · 두 겹)
            if request.method not in SAFE_METHODS:
                sent = request.headers.get(CSRF_HEADER) or ""
                if not session or not csrf.matches(sent, session):
                    return err("요청 확인 값이 맞지 않아요 · 화면을 다시 열어 주세요", 403, csrf=True)
        response = await call_next(request)
        if path.startswith("/api/"):
            response.headers["cache-control"] = "no-store"
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["content-security-policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response
