"""설정 › 알림 · 텔레그램 라우터(V2-08 · V2-52 · T-52 · TASKS P1-09): 봇 토큰 · 대화방 찾기 · 시험 보내기 · 알림 스위치.

일은 쓰기 일 `services/telegram.py`(`Telegram`)예요. 토큰 바꾸기 · 지우기는 비밀번호를 다시 받아요(V2-52).
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from ..services.telegram import Telegram
from .http import NeedConfirm, json_body


def telegram_router(*, telegram: Telegram, need_confirm: NeedConfirm) -> APIRouter:
    r = APIRouter()

    @r.get("/api/telegram")
    def telegram_view() -> dict[str, Any]:
        return telegram.view()

    @r.put("/api/telegram")
    async def telegram_save(request: Request) -> dict[str, Any]:
        if telegram.view()["saved"]:
            need_confirm(request, "telegram_key_change")  # 토큰 변경은 비밀번호(V2-52)
        b = await json_body(request)
        return await asyncio.to_thread(telegram.save_token, str(b.get("token") or ""))

    @r.delete("/api/telegram")
    def telegram_delete(request: Request) -> dict[str, Any]:
        need_confirm(request, "telegram_key_delete")
        return telegram.delete()

    @r.post("/api/telegram/find-chat")
    async def telegram_find_chat() -> dict[str, Any]:
        return await asyncio.to_thread(telegram.find_chat)

    @r.post("/api/telegram/test")
    async def telegram_test() -> dict[str, Any]:
        return await asyncio.to_thread(telegram.test_send)

    @r.put("/api/telegram/events")
    async def telegram_events(request: Request) -> dict[str, Any]:
        b = await json_body(request)
        return telegram.set_event(str(b.get("key") or ""), b.get("on") is True)

    return r
