"""pytest 플러그인(`-p tests.baseline.plugin`): 시계 고정 + 시험 전체에서 오간 HTTP 응답의 모양 수집.

    cd product/service/app && QUANT_BASELINE_API_OUT=<파일> .venv/bin/python -m pytest -p tests.baseline.plugin

- `tests/conftest.py`와 있던 시험은 바꾸지 않아요. `TestClient.request`를 감싸 응답을 보고, 라우트 틀(메서드 + 경로 ·
  경로 변수는 `{id}` 꼴)은 `app.routes`에서 맞춰요. 미들웨어가 먼저 돌려보낸 401 · 403도 같은 틀에 쌓여요.
- autouse 픽스처가 `tests/baseline/clock.py`의 시계 · 씨앗을 모든 시험에 끼워요.
- 관측은 `PYTEST_CURRENT_TEST`로 어느 시험이 냈는지 보고 '남는 시험 / 지울 시험'(`scope.test_is_kept`)으로 나눠요.
- 세션이 끝나면 `QUANT_BASELINE_API_OUT`(없으면 적지 않음)에 원 관측(라우트 × 상태 × 남는/지울 → 모양)을 적어요.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.baseline import clock, shapes
from tests.baseline.scope import test_is_kept

# (method, template, status) → {"kept": Node | None, "deleted": Node | None, "media": set}
OBSERVED: dict[tuple[str, str, int], dict[str, Any]] = {}
ROUTES_SEEN: dict[str, list[str]] = {}  # 앱마다 라우트 목록(같아야 함 · 첫 앱 것을 써요)
_orig_request = TestClient.request


def _current_test_kept() -> bool:
    cur = os.environ.get("PYTEST_CURRENT_TEST", "")
    nodeid = cur.rsplit(" ", 1)[0] if cur else ""
    return test_is_kept(nodeid) if nodeid else True


def flat_routes(app: Any) -> list[Any]:
    """`app.routes`를 펼쳐요(포함된 라우터는 그 안의 라우트로 · 경로는 접두어가 붙은 전체 경로)."""
    out: list[Any] = []

    def walk(routes: Any) -> None:
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None and hasattr(inner, "routes"):
                walk(inner.routes)
            elif hasattr(route, "path_regex") and hasattr(route, "path"):
                out.append(route)
            elif hasattr(route, "routes"):
                walk(route.routes)

    walk(getattr(app, "routes", []))
    return out


def route_template(app: Any, method: str, path: str) -> str:
    partial = None
    for route in flat_routes(app):
        if not route.path_regex.match(path):
            continue
        methods = getattr(route, "methods", None)
        if not methods or method.upper() in methods:
            return str(route.path)
        if partial is None:
            partial = str(route.path)
    return partial or "(no route)"


def route_list(app: Any) -> list[str]:
    out = []
    for route in flat_routes(app):
        for m in sorted(getattr(route, "methods", None) or []):
            if m in ("HEAD", "OPTIONS"):
                continue
            out.append(f"{m} {route.path}")
    return sorted(out)


def observe(app: Any, method: str, response: Any) -> None:
    path = response.request.url.path if getattr(response, "request", None) is not None else "?"
    template = route_template(app, method, path)
    key = (method.upper(), template, int(response.status_code))
    slot = OBSERVED.setdefault(key, {"kept": None, "deleted": None, "media": set()})
    cls = "kept" if _current_test_kept() else "deleted"
    media = (response.headers.get("content-type") or "").split(";")[0].strip()
    slot["media"].add(media or "(none)")
    body: Any
    if media == "application/json":
        try:
            body = response.json()
        except ValueError:
            body = {"<unparsable json>": True}
    else:
        body = {"<non-json>": media or "(none)"}
    if slot[cls] is None:
        slot[cls] = shapes.new_node()
    shapes.add(slot[cls], body)
    if "routes" not in ROUTES_SEEN:
        ROUTES_SEEN["routes"] = route_list(app)


def _request(self: TestClient, method: str, url: Any, **kw: Any) -> Any:
    response = _orig_request(self, method, url, **kw)
    try:
        observe(self.app, method, response)
    except Exception as exc:  # 수집이 시험을 깨뜨리면 안 돼요
        OBSERVED.setdefault(("?", f"(observe failed: {type(exc).__name__})", 0), {"kept": None, "deleted": None,
                                                                                "media": set()})
    return response


def pytest_configure(config: pytest.Config) -> None:
    TestClient.request = _request  # type: ignore[method-assign]


@pytest.fixture(autouse=True)
def _baseline_frozen_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    clock.freeze(monkeypatch)


def as_record() -> dict[str, Any]:
    entries: dict[str, Any] = {}
    for (method, template, status), slot in sorted(OBSERVED.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2])):
        rec: dict[str, Any] = {"media": sorted(slot["media"])}
        rec["shape"] = shapes.to_record(slot["kept"]) if slot["kept"] is not None else None
        if slot["deleted"] is not None:
            rec["shape_with_deleted_tests"] = shapes.to_record(slot["deleted"])
        entries[f"{method} {template} {status}"] = rec
    return {"routes": ROUTES_SEEN.get("routes", []), "observations": entries}


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    out = os.environ.get("QUANT_BASELINE_API_OUT")
    if not out:
        return
    with open(out, "w", encoding="utf-8") as f:
        json.dump(as_record(), f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
