"""GET /api/healthz — no session needed (deploy health check).

200 {ok: true, schema} only when the database is at the code's schema version; otherwise 503
{error: 'schema', detail: {stored, code}} (or 503 {error: 'db'} when it cannot be read), so a
deploy that restarted onto an unmigrated or newer database fails its health check.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Depends

from autotrade.api.deps import get_conn
from autotrade.api.schema import code_version

router = APIRouter(prefix="/api")


@router.get("/healthz")
def healthz(conn: sqlite3.Connection = Depends(get_conn)) -> dict[str, Any]:
    # get_conn has already refused a database at another schema version (503 schema).
    return {"ok": True, "schema": code_version()}
