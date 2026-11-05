"""설정 › 데이터 라우터(V2-53 · T-53 · TASKS P1-09): 현황 · 백업 내려받기 · 복원 · 앱 데이터 삭제 · 기록 CSV · 업데이트 상태.

일은 쓰기 일 `services/data_admin.py` · `services/updates.py`예요. 복원 · 삭제는 비밀번호를 다시 받고(SPEC 7-4), 끝나면
세션 쿠키를 지워 다시 로그인하게 해요(계정 · 비밀번호가 백업 것으로 바뀌거나 사라져서).
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from ..domain.markets.kr import KST
from ..security.vault import Vault
from ..services import data_admin as dm
from ..services import updates
from ..services.connect import Connections
from ..store.db import DB
from .http import NeedConfirm, clear_session_cookies


def data_router(*, db: DB, data: Path, vault: Vault, conns: Connections, need_confirm: NeedConfirm, now: Callable[[], datetime],
                now_iso: Callable[[], str]) -> APIRouter:
    r = APIRouter()

    @r.get("/api/data")
    def data_view() -> dict[str, Any]:
        return dm.overview(db)

    @r.get("/api/data/backup")
    async def data_backup() -> Response:
        raw = await asyncio.to_thread(dm.backup_bytes, db)
        name = dm.backup_name(now().astimezone(KST).date().isoformat())
        return Response(raw, media_type="application/octet-stream",
                        headers={"content-disposition": f'attachment; filename="{name}"'})

    @r.post("/api/data/restore")
    async def data_restore(request: Request) -> Response:
        need_confirm(request, "restore")
        raw = await request.body()
        await asyncio.to_thread(dm.restore, db, raw, now_iso=now_iso())
        vault.reload()  # 계정 · 비밀번호가 백업 것으로 바뀌어요: 다시 로그인
        conns.drop()
        resp = JSONResponse({"ok": True, "line": dm.RESTORE_LINE})
        clear_session_cookies(resp)
        return resp

    @r.delete("/api/data")
    def data_delete(request: Request) -> Response:
        if dm.live_running(db):
            raise dm.DataError(dm.RUNNING_LIVE, 409)  # 비밀번호 창보다 먼저 알려요
        need_confirm(request, "data_delete")
        vault.forget_keyfile()
        dm.delete_all(db)
        vault.reload()
        conns.drop()
        resp = JSONResponse({"ok": True})
        clear_session_cookies(resp)
        return resp

    @r.get("/api/history/csv")
    def history_csv(run_id: int | None = None) -> Response:
        name = f"quant-history-{now().astimezone(KST).date().isoformat().replace('-', '')}.csv"
        return Response(dm.history_csv(db, run_id), media_type="text/csv; charset=utf-8",
                        headers={"content-disposition": f'attachment; filename="{name}"'})

    @r.get("/api/update")
    def update_status() -> dict[str, Any]:
        return updates.status(data)

    return r
