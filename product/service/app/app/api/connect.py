"""설정 › 연결 라우터(V2-05 · T-50 · TASKS P1-09): 토스 · DART 키 저장 · 지우기와 토스 연결 확인.

키 저장 · 확인 흐름은 쓰기 일 `services/connect.py`(`Connections`)예요. 처음 넣기는 로그인만, 바꾸기 · 지우기는 비밀번호를
다시 받아요(SPEC 7-4). 운용 중 계좌번호 변경은 실전 상태의 주인이 거절해요(R-L10).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from ..run.live import Live
from ..services.connect import Connections
from .http import NeedConfirm, json_body


def connect_router(*, conns: Connections, live: Live, need_confirm: NeedConfirm) -> APIRouter:
    r = APIRouter()

    @r.get("/api/connect")
    def connect_view() -> dict[str, Any]:
        return conns.view()

    @r.put("/api/connect/toss")
    async def toss_save(request: Request) -> dict[str, Any]:
        if conns.view()["toss"]["saved"]:
            need_confirm(request, "toss_key_change")  # 처음 넣기는 로그인만, 바꾸기는 비밀번호
        b = await json_body(request)
        live.check_account_change(str(b.get("account_no") or "") or None)  # 운용 중 계좌번호 변경 거절(R-L10)
        conns.save_toss(
            str(b.get("client_id") or ""),
            str(b.get("client_secret") or ""),
            str(b.get("account_no") or "") or None,
        )
        return conns.view()

    @r.delete("/api/connect/toss")
    def toss_delete(request: Request) -> dict[str, Any]:
        need_confirm(request, "toss_key_delete")
        conns.delete_toss()
        return conns.view()

    @r.post("/api/connect/toss/check")
    async def toss_check() -> dict[str, Any]:
        return {"result": await asyncio.to_thread(conns.check), **conns.view()}

    @r.put("/api/connect/dart")
    async def dart_save(request: Request) -> dict[str, Any]:
        if conns.view()["dart"]["saved"]:
            need_confirm(request, "dart_key_change")
        b = await json_body(request)
        conns.save_dart(str(b.get("key") or ""))
        return conns.view()

    @r.delete("/api/connect/dart")
    def dart_delete(request: Request) -> dict[str, Any]:
        need_confirm(request, "dart_key_delete")
        conns.delete_dart()
        return conns.view()

    return r
