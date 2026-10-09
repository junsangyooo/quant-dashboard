"""GET /api/healthz — no session needed (deploy health check)."""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends

from autotrade.api.deps import get_conn
from autotrade.api.errors import ApiError
from autotrade.db.migrations import current_version

router = APIRouter(prefix="/api")


@router.get("/healthz")
def healthz(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    try:
        version = current_version(conn)
    except sqlite3.Error as exc:
        raise ApiError(503, "db") from exc
    return {"ok": True, "schema": version}
