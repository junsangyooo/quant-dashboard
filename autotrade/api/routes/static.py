"""The built web app from web/dist, and nothing else (CONTRACT.md 세션과 보안).

- /assets/* are Vite's hashed files: cached for a year, immutable. A missing asset is 404.
- Other files in web/dist: served with no-cache.
- Any other path that is not /api: index.html (no-cache), so the app's own routes work.
- Without a build, a plain 503 page.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from autotrade.api.deps import app_state
from autotrade.api.errors import ApiError

router = APIRouter()

IMMUTABLE = "public, max-age=31536000, immutable"
NO_CACHE = "no-cache"
MISSING_BUILD = (
    '<!doctype html><html lang="ko"><meta charset="utf-8"><title>quant</title>'
    "<p>quant: web/dist is not built.</p></html>"
)


def _inside(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
    except ValueError:
        return False
    return True


@router.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def web_app(path: str, request: Request) -> Response:
    if path == "api" or path.startswith("api/"):
        raise ApiError(404, "not-found")
    dist = app_state(request).settings.dist_dir.resolve()
    index = dist / "index.html"
    if not index.is_file():
        return HTMLResponse(MISSING_BUILD, status_code=503, headers={"Cache-Control": "no-store"})
    if path:
        target = (dist / path).resolve()
        if _inside(dist, target) and target.is_file():
            cache = IMMUTABLE if path.startswith("assets/") else NO_CACHE
            return FileResponse(target, headers={"Cache-Control": cache})
        if path.startswith("assets/"):
            return Response("not found", status_code=404, media_type="text/plain")
    return FileResponse(index, media_type="text/html", headers={"Cache-Control": NO_CACHE})
