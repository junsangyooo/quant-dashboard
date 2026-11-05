"""처음 열기 · 로그인 · 계정 라우터(SPEC 7-4 · V2-33 · T-50 · T-51 · TASKS P1-09).

상태 · 처음 열기 · 로그인 · 복구 · 비밀번호 바꾸기 · 잠그기 · 비밀번호 다시 받기(1회용 토큰) · 정보 · 공인 IP 보기.
금고(`security/vault.py`)를 부르고 세션 쿠키를 붙이거나 지우기만 해요.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request, Response

from .. import APP_VERSION_TEXT
from ..security import vault as vault_mod
from ..security.access import Csrf
from ..security.vault import Vault
from ..services import updates
from ..services.connect import Connections
from ..store import vault as vault_store
from ..store.db import DB
from .http import COOKIE, ERRORS, OkOut, clear_session_cookies, json_body, set_session_cookies
from .models import ApiModel, Bool, Int, Str


class Health(ApiModel):
    app: Str  # 늘 "quant-mvp"(바깥 약속)
    version: Str


class AppState(ApiModel):
    setup: Bool
    logged_in: Bool
    unlocked: Bool
    locked_for: Int
    restarted: Bool  # 서버가 다시 켜진 뒤 아직 한 번도 로그인하지 않음('앱을 다시 켰어요' 안내)
    update_chip: Str | None
    auto: Bool
    version: Str


class RecoveryOut(ApiModel):
    ok: Bool
    recovery_code: Str  # 이때 한 번만 바깥에 나가요


class About(ApiModel):
    version: Str
    terms_at: Str | None
    created_at: Str | None
    address: Str


class PublicIp(ApiModel):
    ip: Str


class ConfirmToken(ApiModel):
    token: Str
    expires_in: Int


def account_router(*, db: DB, vault: Vault, conns: Connections, csrf: Csrf, data: Path, port: int,
                lookup_ip: Callable[[], str]) -> APIRouter:
    r = APIRouter(responses=ERRORS)

    @r.get("/api/health", response_model=Health, response_model_exclude_unset=True)
    def health() -> dict[str, Any]:
        return {"app": "quant-mvp", "version": APP_VERSION_TEXT}

    @r.get("/api/state", response_model=AppState, response_model_exclude_unset=True)
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

    # 쿠키는 주입받은 `response`에 붙여요(FastAPI가 응답에 옮겨 줘요 · 몸통은 응답 모델로 검사)

    @r.post("/api/setup", response_model=RecoveryOut, response_model_exclude_unset=True)
    async def setup(request: Request, response: Response) -> dict[str, Any]:
        b = await json_body(request)
        token, code = vault.setup(
            str(b.get("password") or ""),
            str(b.get("password2") or ""),
            adult=b.get("adult") is True,
            terms=b.get("terms") is True,
        )
        set_session_cookies(response, token, csrf.value_for)
        return {"ok": True, "recovery_code": code}

    @r.post("/api/login", response_model=OkOut, response_model_exclude_unset=True)
    async def login(request: Request, response: Response) -> dict[str, Any]:
        b = await json_body(request)
        token = await asyncio.to_thread(vault.login, str(b.get("password") or ""))
        set_session_cookies(response, token, csrf.value_for)
        return {"ok": True}

    @r.post("/api/recover", response_model=RecoveryOut, response_model_exclude_unset=True)
    async def recover(request: Request, response: Response) -> dict[str, Any]:
        b = await json_body(request)
        token, code = await asyncio.to_thread(
            vault.recover,
            str(b.get("recovery_code") or ""),
            str(b.get("password") or ""),
            str(b.get("password2") or ""),
        )
        set_session_cookies(response, token, csrf.value_for)
        return {"ok": True, "recovery_code": code}

    @r.get("/api/about", response_model=About, response_model_exclude_unset=True)
    def about() -> dict[str, Any]:
        row = vault_store.owner_dates(db)
        return {
            "version": APP_VERSION_TEXT,
            "terms_at": row["terms_at"] if row else None,
            "created_at": row["created_at"] if row else None,
            "address": f"127.0.0.1:{port}",
        }

    @r.post("/api/password", response_model=OkOut, response_model_exclude_unset=True)
    async def password_change(request: Request) -> dict[str, Any]:
        b = await json_body(request)
        await asyncio.to_thread(
            vault.change_password,
            str(b.get("current") or ""),
            str(b.get("password") or ""),
            str(b.get("password2") or ""),
        )
        return {"ok": True}

    @r.post("/api/public-ip", response_model=PublicIp, response_model_exclude_unset=True)
    async def public_ip_view() -> dict[str, Any]:
        # 누를 때만 부른다. 저장하지 않는다.
        ip = await asyncio.to_thread(lookup_ip)
        return {"ip": ip}

    @r.post("/api/logout", response_model=OkOut, response_model_exclude_unset=True)
    def logout(response: Response) -> dict[str, Any]:
        # 잠그기 = 앱 전체 잠금: 모든 세션을 끝내고 데이터 키를 메모리에서 지운다.
        # 자동 확인은 데이터 키가 풀려 있을 때 토스에서 일봉을 받는다.
        vault.lock_now()
        conns.drop()
        clear_session_cookies(response)
        return {"ok": True}

    # ── 비밀번호 다시 받기(SPEC 7-4 · V2-33) ─────────────────────────────

    @r.post("/api/confirm", response_model=ConfirmToken, response_model_exclude_unset=True)
    async def confirm(request: Request) -> dict[str, Any]:
        b = await json_body(request)
        action = str(b.get("action") or "")
        token = await asyncio.to_thread(vault.confirm, str(b.get("password") or ""), action)
        return {"token": token, "expires_in": vault_mod.CONFIRM_S}

    return r
