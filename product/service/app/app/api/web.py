"""화면 파일 내주기(web/dist · TASKS P1-09): `/api/` 밖의 모든 경로. 맨 마지막에 등록해요(다른 라우트가 먼저 맞게).

`assets/`는 이름에 내용 해시가 있어 오래 캐시하고, 나머지는 늘 다시 확인해요. 없는 경로는 화면 첫 장(`index.html`)이에요
(화면 안 주소). `dist` 밖의 파일은 내주지 않아요.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse, Response

from .http import ERRORS, err

# 화면 파일(HTML · JS · CSS · 그림)은 JSON이 아니라 응답 모델 대신 몸통 꼴만 적어요
WEB_BODY: dict[int | str, dict[str, Any]] = {200: {"content": {"text/html": {}}, "description": "web file"}}


def web_router(*, dist: Path) -> APIRouter:
    r = APIRouter(responses=ERRORS)

    def _index() -> Response:
        index = dist / "index.html"
        if not index.is_file():
            return err("화면 파일이 없어요 · start.sh로 다시 켜 주세요", 503)
        return FileResponse(index, headers={"cache-control": "no-store"})

    @r.get("/{path:path}", response_class=Response, responses=WEB_BODY)
    def web(path: str) -> Response:
        if path.startswith("api/") or path == "api":
            return err("없는 주소예요", 404)
        if path:
            base = dist.resolve()
            target = (base / path).resolve()
            if target.is_file() and target.is_relative_to(base):
                cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
                return FileResponse(target, headers={"cache-control": cache})
        return _index()

    return r
