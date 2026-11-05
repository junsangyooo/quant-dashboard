"""처음 열기 · 로그인 · 계정 라우터(SPEC 7-4 · V2-33 · T-50 · T-51 · TASKS P1-09).

상태 · 처음 열기 · 로그인 · 복구 · 비밀번호 바꾸기 · 잠그기 · 비밀번호 다시 받기(1회용 토큰) · 정보 · 공인 IP 보기.
금고(`security/vault.py`)를 부르고 세션 쿠키를 붙이거나 지우기만 해요.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from .. import APP_VERSION_TEXT
from ..security import vault as vault_mod
from ..security.access import Csrf
from ..security.vault import Vault
from ..services import updates
from ..services.connect import Connections
from ..store import vault as vault_store
from ..store.db import DB
from .http import COOKIE, clear_session_cookies, json_body, set_session_cookies


def account_router(*, db: DB, vault: Vault, conns: Connections, csrf: Csrf, data: Path, port: int,
                lookup_ip: Callable[[], str]) -> APIRouter:
    r = APIRouter()

    @r.get("/api/health")
    def health() -> dict[str, Any]:
        return {"app": "quant-mvp", "version": APP_VERSION_TEXT}

    @r.get("/api/state")
    def state(request: Request) -> dict[str, Any]:
        return {
            "setup": vault.is_setup(),
            "logged_in": vault.session_ok(request.cookies.get(COOKIE)),
            "unlocked": vault.unlocked,
            "locked_for": vault.locked_for(),
            "restarted": vault.is_setup() and not vault.opened_since_start,
            "update_chip": updates.status(data)["chip"],  # 머리 칩 '업데이트 중'(5-10)
            "auto": vault.runner_ready,  # 키 파일로 로그인 없이 운용 이어짐(T-50)
            "version": APP_VERSION_TEXT,
        }

    @r.post("/api/setup")
    async def setup(request: Request) -> Response:
        b = await json_body(request)
        token, code = vault.setup(
            str(b.get("password") or ""),
            str(b.get("password2") or ""),
            adult=b.get("adult") is True,
            terms=b.get("terms") is True,
        )
        resp = JSONResponse({"ok": True, "recovery_code": code})
        set_session_cookies(resp, token, csrf.value_for)
        return resp

    @r.post("/api/login")
    async def login(request: Request) -> Response:
        b = await json_body(request)
        token = await asyncio.to_thread(vault.login, str(b.get("password") or ""))
        resp = JSONResponse({"ok": True})
        set_session_cookies(resp, token, csrf.value_for)
        return resp

    @r.post("/api/recover")
    async def recover(request: Request) -> Response:
        b = await json_body(request)
        token, code = await asyncio.to_thread(
            vault.recover,
            str(b.get("recovery_code") or ""),
            str(b.get("password") or ""),
            str(b.get("password2") or ""),
        )
        resp = JSONResponse({"ok": True, "recovery_code": code})
        set_session_cookies(resp, token, csrf.value_for)
        return resp

    @r.get("/api/about")
    def about() -> dict[str, Any]:
        row = vault_store.owner_dates(db)
        return {
            "version": APP_VERSION_TEXT,
            "terms_at": row["terms_at"] if row else None,
            "created_at": row["created_at"] if row else None,
            "address": f"127.0.0.1:{port}",
        }

    @r.post("/api/password")
    async def password_change(request: Request) -> dict[str, Any]:
        b = await json_body(request)
        await asyncio.to_thread(
            vault.change_password,
            str(b.get("current") or ""),
            str(b.get("password") or ""),
            str(b.get("password2") or ""),
        )
        return {"ok": True}

    @r.post("/api/public-ip")
    async def public_ip_view() -> dict[str, Any]:
        # 누를 때만 부른다. 저장하지 않는다.
        ip = await asyncio.to_thread(lookup_ip)
        return {"ip": ip}

    @r.post("/api/logout")
    def logout(request: Request) -> Response:
        # 잠그기 = 앱 전체 잠금: 모든 세션을 끝내고 데이터 키를 메모리에서 지운다.
        # 자동 확인은 데이터 키가 풀려 있을 때 토스에서 일봉을 받는다.
        vault.lock_now()
        conns.drop()
        resp = JSONResponse({"ok": True})
        clear_session_cookies(resp)
        return resp

    # ── 비밀번호 다시 받기(SPEC 7-4 · V2-33) ─────────────────────────────

    @r.post("/api/confirm")
    async def confirm(request: Request) -> dict[str, Any]:
        b = await json_body(request)
        action = str(b.get("action") or "")
        token = await asyncio.to_thread(vault.confirm, str(b.get("password") or ""), action)
        return {"token": token, "expires_in": vault_mod.CONFIRM_S}

    return r
