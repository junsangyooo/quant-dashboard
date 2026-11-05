"""설정 › 데이터 라우터(V2-53 · T-53 · TASKS P1-09): 현황 · 백업 내려받기 · 복원 · 앱 데이터 삭제 · 기록 CSV · 업데이트 상태.

일은 쓰기 일 `services/data_admin.py` · `services/updates.py`예요. 복원 · 삭제는 비밀번호를 다시 받고(SPEC 7-4), 끝나면
세션 쿠키를 지워 다시 로그인하게 해요(계정 · 비밀번호가 백업 것으로 바뀌거나 사라져서).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Request, Response
from pydantic import Field

from ..domain.markets.kr import KST
from ..security.vault import Vault
from ..services import data_admin as dm
from ..services import updates
from ..services.connect import Connections
from ..store.db import DB
from .http import ERRORS, NeedConfirm, OkOut, clear_session_cookies
from .models import ApiModel, Bool, Int, Num, Str


class BarsInfo(ApiModel):
    model_config = {"populate_by_name": True}

    symbols: Int
    from_: Str | None = Field(alias="from")
    to: Str | None
    fetched_at: Num | None


class DartCounts(ApiModel):
    financials: Int
    disclosures: Int
    shares: Int


class DataView(ApiModel):
    bars: BarsInfo
    dart: DartCounts
    strategies: Int
    live_running: Bool
    restore_line: Str


class RestoreOut(ApiModel):
    ok: Bool
    line: Str


class UpdateStep(ApiModel):
    key: Str
    title: Str
    state: Literal["wait", "now", "done", "failed"]


class UpdateStatus(ApiModel):
    updating: Bool
    chip: Str | None
    version: Any  # 설치기가 `update.json`에 적은 판 글(그대로 · 없으면 null)
    state: Str | None
    steps: list[UpdateStep]


# 파일 내려받기(백업 · 기록 CSV)는 JSON이 아니라 응답 모델 대신 몸통 꼴만 적어요
FILE_BODY: dict[int | str, dict[str, Any]] = {200: {"content": {"application/octet-stream": {}}, "description": "file"}}
CSV_BODY: dict[int | str, dict[str, Any]] = {200: {"content": {"text/csv": {}}, "description": "csv"}}


def data_router(*, db: DB, data: Path, vault: Vault, conns: Connections, need_confirm: NeedConfirm, now: Callable[[], datetime],
                now_iso: Callable[[], str]) -> APIRouter:
    r = APIRouter(responses=ERRORS)

    @r.get("/api/data", response_model=DataView, response_model_exclude_unset=True)
    def data_view() -> dict[str, Any]:
        return dm.overview(db)

    @r.get("/api/data/backup", response_class=Response, responses=FILE_BODY)
    async def data_backup() -> Response:
        raw = await asyncio.to_thread(dm.backup_bytes, db)
        name = dm.backup_name(now().astimezone(KST).date().isoformat())
        return Response(raw, media_type="application/octet-stream",
                        headers={"content-disposition": f'attachment; filename="{name}"'})

    @r.post("/api/data/restore", response_model=RestoreOut, response_model_exclude_unset=True)
    async def data_restore(request: Request, response: Response) -> dict[str, Any]:
        need_confirm(request, "restore")
        raw = await request.body()
        await asyncio.to_thread(dm.restore, db, raw, now_iso=now_iso())
        vault.reload()  # 계정 · 비밀번호가 백업 것으로 바뀌어요: 다시 로그인
        conns.drop()
        clear_session_cookies(response)
        return {"ok": True, "line": dm.RESTORE_LINE}

    @r.delete("/api/data", response_model=OkOut, response_model_exclude_unset=True)
    def data_delete(request: Request, response: Response) -> dict[str, Any]:
        if dm.live_running(db):
            raise dm.DataError(dm.RUNNING_LIVE, 409)  # 비밀번호 창보다 먼저 알려요
        need_confirm(request, "data_delete")
        vault.forget_keyfile()
        dm.delete_all(db)
        vault.reload()
        conns.drop()
        clear_session_cookies(response)
        return {"ok": True}

    @r.get("/api/history/csv", response_class=Response, responses=CSV_BODY)
    def history_csv(run_id: int | None = None) -> Response:
        name = f"quant-history-{now().astimezone(KST).date().isoformat().replace('-', '')}.csv"
        return Response(dm.history_csv(db, run_id), media_type="text/csv; charset=utf-8",
                        headers={"content-disposition": f'attachment; filename="{name}"'})

    @r.get("/api/update", response_model=UpdateStatus, response_model_exclude_unset=True)
    def update_status() -> dict[str, Any]:
        return updates.status(data)

    return r
