"""JSON 응답의 키 · 타입 구조(값은 빼고 · 배열은 원소 구조 합집합 · 선택 키 표시).

관측 누적(`Node`)과 직렬화(`to_record`)를 나눴어요. 같은 라우트 × 상태 코드로 들어온 응답을 모두 `add`하면
키가 늘 있는지(`optional`) · 타입이 여럿인지(`types`)가 쌓여요. 가릴 키(`mask.MASKED`)는 타입 대신 `masked`.
"""

from __future__ import annotations

from typing import Any

from tests.baseline.mask import MASKED


def new_node() -> dict[str, Any]:
    return {"scalars": set(), "obj": None, "req": None, "arr": None, "arr_empty": False, "n": 0}


def _scalar_name(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    return type(v).__name__


def add(node: dict[str, Any], v: Any) -> None:
    node["n"] += 1
    if isinstance(v, dict):
        node["obj"] = node["obj"] if node["obj"] is not None else {}
        for k, x in v.items():
            child = node["obj"].setdefault(k, new_node())
            if k in MASKED:
                child["n"] += 1
                child["scalars"].add("masked" if x is not None else "null")
            else:
                add(child, x)
        keys = set(v)
        node["req"] = keys if node["req"] is None else node["req"] & keys
    elif isinstance(v, list):
        node["arr"] = node["arr"] if node["arr"] is not None else new_node()
        if not v:
            node["arr_empty"] = True
        for x in v:
            add(node["arr"], x)
    else:
        node["scalars"].add(_scalar_name(v))


def to_record(node: dict[str, Any]) -> dict[str, Any]:
    """결정적인(키 정렬) 기록 꼴."""
    out: dict[str, Any] = {}
    types = sorted(node["scalars"])
    if node["obj"] is not None:
        types.append("object")
    if node["arr"] is not None:
        types.append("array")
    out["types"] = types
    if node["obj"] is not None:
        req = node["req"] or set()
        keys: dict[str, Any] = {}
        for k in sorted(node["obj"]):
            rec = to_record(node["obj"][k])
            if k not in req:
                rec["optional"] = True
            keys[k] = rec
        out["keys"] = keys
    if node["arr"] is not None:
        out["items"] = to_record(node["arr"]) if node["arr"]["n"] else "empty"
        if node["arr_empty"] and node["arr"]["n"]:
            out["items_may_be_empty"] = True
    return out


def shape_of(value: Any) -> dict[str, Any]:
    node = new_node()
    add(node, value)
    return to_record(node)
