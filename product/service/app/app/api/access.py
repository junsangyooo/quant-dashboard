"""설정 › 접속 라우터(V2-05 · V2-06 · V2-56 · TASKS P1-09): 설치 위치 · Tailscale · 이 컴퓨터 주소."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request

from ..services import access
from ..store.db import DB
from .http import ERRORS, NeedConfirm, json_body
from .models import ApiModel, Bool, Str


class Tailscale(ApiModel):
    ok: Bool
    name: Str | None
    address: Str | None


class AccessView(ApiModel):
    place: Literal["server", "pc"] | None
    place_name: Str | None
    tailscale: Tailscale
    local: Str


def access_router(*, db: DB, ts_ok: list[str], port: int, need_confirm: NeedConfirm) -> APIRouter:
    r = APIRouter(responses=ERRORS)

    @r.get("/api/access", response_model=AccessView, response_model_exclude_unset=True)
    def access_get() -> dict[str, Any]:
        return access.access_view(db, ts_ok=ts_ok, port=port)

    @r.put("/api/access/place", response_model=AccessView, response_model_exclude_unset=True)
    async def access_place(request: Request) -> dict[str, Any]:
        b = await json_body(request)
        access.set_place(db, str(b.get("place") or ""), confirm=lambda action: need_confirm(request, action))
        return access.access_view(db, ts_ok=ts_ok, port=port)

    return r
