"""업데이트 상태(T-53 · SPEC 5-10): 설치기(T-56)가 데이터 폴더의 `update.json`에 단계를 적고, 앱은 읽어서 보여줘요.

단계: 스케줄러 멈춤 → 백업 → 데이터 구조 바꿈 → 다시 켬 → 대조. 앱 안 업데이트 단추는 없어요.
끝나면(대조까지 done) 텔레그램 '업데이트 끝 · 버전 n'을 한 번 보내요.

    update.json = {"version": "1.1", "step": "backup", "state": "running" | "done" | "failed", "at": "..."}
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .db import DB

FILE = "update.json"
STEPS: list[tuple[str, str]] = [
    ("stop", "스케줄러 멈춤"),
    ("backup", "백업"),
    ("migrate", "데이터 구조 바꿈"),
    ("restart", "다시 켬"),
    ("reconcile", "대조"),
]
CHIP = "업데이트 중"


def read(data: Path) -> dict[str, Any] | None:
    p = data / FILE
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def status(data: Path) -> dict[str, Any]:
    raw = read(data)
    keys = [k for k, _ in STEPS]
    if not raw or raw.get("step") not in keys:
        return {"updating": False, "chip": None, "version": None, "state": None,
                "steps": [{"key": k, "title": t, "state": "wait"} for k, t in STEPS]}
    at = keys.index(str(raw["step"]))
    state = str(raw.get("state") or "running")
    finished = state == "done" and at == len(keys) - 1
    steps = []
    for i, (k, t) in enumerate(STEPS):
        if i < at or finished:
            s = "done"
        elif i == at:
            s = "failed" if state == "failed" else ("done" if state == "done" else "now")
        else:
            s = "wait"
        steps.append({"key": k, "title": t, "state": s})
    updating = not finished and state != "failed"
    return {"updating": updating, "chip": CHIP if updating else None, "version": raw.get("version"),
            "state": "done" if finished else state, "steps": steps}


def done_message(version: str) -> str:
    return f"업데이트 끝 · 버전 {version}"


def announce(data: Path, db: DB, send: Callable[[str], object]) -> bool:
    """업데이트가 끝났으면 버전마다 한 번 알려요."""
    st = status(data)
    v = st["version"]
    if st["state"] != "done" or not v or db.get_meta("update.notified") == str(v):
        return False
    send(done_message(str(v)))
    db.set_meta("update.notified", str(v))
    return True
