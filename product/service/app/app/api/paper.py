"""모의투자 v2 라우터(T-40 · T-41 · TASKS P1-09): 목록 · 시작 전 확인 · 시작 · 보기 · 멈추기 · 확인 돌리기.

일은 실행 흐름 `run/paper.py`(`PaperV2` · 20:10 확인 · 다음 거래일 일봉 시가 체결)예요.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request

from ..run.paper import PaperV2
from ..security.vault import VaultError
from .http import json_body


def paper_router(*, paper2: PaperV2) -> APIRouter:
    r = APIRouter()

    @r.get("/api/v2/paper")
    def paper2_list() -> dict[str, Any]:
        return {"runs": paper2.list()}

    @r.post("/api/v2/paper/start")
    async def paper2_start(request: Request) -> dict[str, Any]:
        b = await json_body(request)
        try:
            vid = int(b.get("version_id"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise VaultError("전략 버전을 골라 주세요") from None
        return await asyncio.to_thread(paper2.start, vid, b.get("cash"))

    @r.get("/api/v2/paper/preview")
    def paper2_preview(version_id: int) -> dict[str, Any]:
        return paper2.preview(version_id)

    @r.get("/api/v2/paper/{rid}")
    def paper2_view(rid: int) -> dict[str, Any]:
        return paper2.view(rid)

    @r.post("/api/v2/paper/{rid}/stop")
    def paper2_stop(rid: int) -> dict[str, Any]:
        return paper2.stop(rid)

    @r.post("/api/v2/paper/check")
    async def paper2_check() -> dict[str, Any]:
        return {"advanced": await asyncio.to_thread(paper2.tick)}

    return r
