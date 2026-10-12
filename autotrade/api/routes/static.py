"""The built web app from web/dist, and nothing else (CONTRACT.md 세션과 보안).

- /assets/* are Vite's hashed files: cached for a year, immutable. A missing asset is 404.
- Other files in web/dist: served with no-cache.
- Any other path that is not /api: index.html (no-cache), so the app's own routes work.
- Every one of them also says no-transform: Cloudflare (quant.jsyoo.dev is proxied) otherwise
  rewrites the HTML to inject its Web Analytics beacon, which the CSP then blocks (seen on the
  live site 2026-10-12: an external script and an inline one, two console errors per page).
  no-transform tells any intermediary to pass the bytes as the app sent them.
- A path no file can have — a control character (NUL included), a segment longer than a file name
  may be (255 bytes), or more than 1,024 characters — is a plain 404: the filesystem is never
  asked about it, so it cannot fail with a 500.
- Without a build, a plain 503 page.
- On the server web/dist is a symlink to the live release (web/releases/<id>, deploy/deploy.sh).
  It is resolved per request and files are sent from the release folder itself, so a deploy that
  switches the link mid-request still sends a whole file. Each release also carries the hashed
  assets of the releases before it, so a page loaded before a deploy still finds its chunks.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from autotrade.api.deps import app_state
from autotrade.api.errors import ApiError

router = APIRouter()

IMMUTABLE = "public, max-age=31536000, immutable, no-transform"
NO_CACHE = "no-cache, no-transform"
MISSING_BUILD = (
    '<!doctype html><html lang="ko"><meta charset="utf-8"><title>quant</title>'
    "<p>quant: web/dist is not built.</p></html>"
)
MAX_PATH = 1024
MAX_SEGMENT_BYTES = 255  # NAME_MAX on Linux and macOS


def _inside(base: Path, target: Path) -> bool:
    try:
        target.relative_to(base)
    except ValueError:
        return False
    return True


def impossible_path(path: str) -> bool:
    """A path that names no file of a build: refuse it before touching the filesystem."""
    if len(path) > MAX_PATH:
        return True
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in path):
        return True
    return any(
        len(segment.encode("utf-8", "replace")) > MAX_SEGMENT_BYTES for segment in path.split("/")
    )


def _file(dist: Path, path: str) -> Path | None:
    """The file of the build at `path`, or None. Errors of the filesystem count as 'no file'."""
    try:
        target = (dist / path).resolve()
        if _inside(dist, target) and target.is_file():
            return target
    except (OSError, ValueError):
        return None
    return None


def _not_found() -> Response:
    return Response("not found", status_code=404, media_type="text/plain")


@router.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
def web_app(path: str, request: Request) -> Response:
    if path == "api" or path.startswith("api/"):
        raise ApiError(404, "not-found")
    # The whole path, not only the parameter: the route's `$` also matches before a final
    # newline, so '/%0a' arrives here with path ''.
    if impossible_path(path) or impossible_path(str(request.scope.get("path", ""))):
        return _not_found()
    dist = app_state(request).settings.dist_dir.resolve()
    index = dist / "index.html"
    if not index.is_file():
        return HTMLResponse(
            MISSING_BUILD, status_code=503, headers={"Cache-Control": "no-store, no-transform"}
        )
    if path:
        target = _file(dist, path)
        if target is not None:
            cache = IMMUTABLE if path.startswith("assets/") else NO_CACHE
            return FileResponse(target, headers={"Cache-Control": cache})
        if path.startswith("assets/"):
            return _not_found()
    return FileResponse(index, media_type="text/html", headers={"Cache-Control": NO_CACHE})
