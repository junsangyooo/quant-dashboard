"""토스 OpenAPI 1.2.28 명세로 가짜 요청 · 응답의 꼴을 검사해요(시험 전용 · TASKS T-10).

명세가 쓰는 JSON Schema 낱말만 다뤄요: type(배열 · null 포함) · nullable · properties · required · items ·
enum · allOf · oneOf · anyOf · format(decimal · date · date-time) · maxLength · pattern.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from functools import cache
from pathlib import Path
from typing import Any

SPEC_PATH = Path(__file__).resolve().parents[2] / "vendor" / "toss-openapi-1.2.28.json"
SPEC_SHA256 = "18fdc96fdf632e4869c765ed0cb169049c5310a1c48e10b40e47a71f52aa7a45"


@cache
def spec() -> dict[str, Any]:
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def _res(node: Any) -> Any:
    while isinstance(node, dict) and "$ref" in node:
        cur: Any = spec()
        for key in node["$ref"].lstrip("#/").split("/"):
            cur = cur[key]
        node = cur
    return node


def _type_ok(value: Any, t: str) -> bool:
    return {
        "null": value is None,
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, int | float) and not isinstance(value, bool),
        "object": isinstance(value, dict),
        "array": isinstance(value, list),
    }[t]


def errors(value: Any, schema: Any, where: str = "$") -> list[str]:
    s = _res(schema)
    if not isinstance(s, dict):
        return []
    out: list[str] = []
    for sub in s.get("allOf", []):
        out += errors(value, sub, where)
    for key in ("oneOf", "anyOf"):
        if key in s:
            passing = [sub for sub in s[key] if not errors(value, sub, where)]
            if not passing or (key == "oneOf" and len(passing) > 1 and value is not None):
                out.append(f"{where}: {key} 맞는 꼴 {len(passing)}개")
    t = s.get("type")
    if t is not None:
        types = t if isinstance(t, list) else [t]
        if s.get("nullable"):
            types = [*types, "null"]
        if not any(_type_ok(value, x) for x in types):
            return [*out, f"{where}: {types} 아님 ({type(value).__name__})"]
    if value is None:
        return out
    if "enum" in s and value not in s["enum"]:
        out.append(f"{where}: enum {s['enum']} 밖 ({value!r})")
    if isinstance(value, str):
        fmt = s.get("format")
        try:
            if fmt == "decimal":
                Decimal(value)
            elif fmt == "date":
                date.fromisoformat(value)
            elif fmt == "date-time":
                if datetime.fromisoformat(value).tzinfo is None:
                    out.append(f"{where}: 시간대 없음")
        except (InvalidOperation, ValueError):
            out.append(f"{where}: format {fmt} 아님 ({value!r})")
        if "maxLength" in s and len(value) > s["maxLength"]:
            out.append(f"{where}: maxLength {s['maxLength']} 넘음")
        if "pattern" in s and not re.search(s["pattern"], value):
            out.append(f"{where}: pattern 아님")
    if isinstance(value, dict):
        for key in s.get("required", []):
            if key not in value:
                out.append(f"{where}.{key}: 필수 필드 없음")
        for key, sub in s.get("properties", {}).items():
            if key in value:
                out += errors(value[key], sub, f"{where}.{key}")
    if isinstance(value, list) and "items" in s:
        for i, item in enumerate(value):
            out += errors(item, s["items"], f"{where}[{i}]")
    return out


def operation(method: str, path: str) -> tuple[str, dict[str, Any]]:
    """경로에 맞는 명세 항목. 고정 경로를 {…} 경로보다 먼저 골라요."""
    parts = path.strip("/").split("/")
    best: tuple[int, str, dict[str, Any]] | None = None
    for pattern, ops in spec()["paths"].items():
        p = pattern.strip("/").split("/")
        if len(p) == len(parts) and all(a == b or a.startswith("{") for a, b in zip(p, parts)):
            if method.lower() in ops:
                exact = sum(a == b for a, b in zip(p, parts))
                if best is None or exact > best[0]:
                    best = (exact, pattern, ops[method.lower()])
    if best is None:
        raise KeyError(f"{method} {path}: 명세에 없는 경로")
    return best[1], best[2]


def response_errors(method: str, path: str, status: int, body: Any) -> list[str]:
    _, op = operation(method, path)
    resp = _res(op["responses"].get(str(status)))
    if resp is None:
        return [f"{method} {path}: 명세에 없는 상태 {status}"]
    content = resp.get("content")
    if not content:
        return [] if body in (None, b"", {}) else [f"{method} {path} {status}: 본문이 없어야 해요"]
    return errors(body, content["application/json"]["schema"])


def request_errors(method: str, path: str, body: Any) -> list[str]:
    _, op = operation(method, path)
    rb = _res(op.get("requestBody"))
    if not rb:
        return []
    content = rb.get("content", {})
    if "application/json" not in content:
        return []
    return errors(body, content["application/json"]["schema"])


def query_errors(method: str, path: str, query: dict[str, str], headers: dict[str, str]) -> list[str]:
    _, op = operation(method, path)
    out = []
    names = set()
    for prm in op.get("parameters", []):
        prm = _res(prm)
        names.add(prm["name"])
        if prm["in"] == "query":
            if prm.get("required") and prm["name"] not in query:
                out.append(f"query {prm['name']} 없음")
            enum = _res(prm.get("schema", {})).get("enum")
            if enum and prm["name"] in query and query[prm["name"]] not in enum:
                out.append(f"query {prm['name']}={query[prm['name']]} enum 밖")
        if prm["in"] == "header" and prm.get("required"):
            if prm["name"].lower() not in {k.lower() for k in headers}:
                out.append(f"header {prm['name']} 없음")
    for key in query:
        if key not in names:
            out.append(f"query {key}: 명세에 없는 매개변수")
    return out
