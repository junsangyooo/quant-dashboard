"""시험 도우미: 옛 일곱 칸 본문(읽을 때 그래프로 바뀌는 모양)과 API로 새 전략 만들기."""

from __future__ import annotations

from typing import Any

from app import strategy as st


def _blank(piece: str) -> dict[str, Any]:
    params: dict[str, Any] = {}
    for p in st.PIECES[piece]["params"]:
        if p.get("kind") == "choice":
            continue
        params[p["key"]] = [] if p.get("kind") == "symbols" else None
    return {"piece": piece, "params": params}


def legacy(template: str, name: str) -> dict[str, Any]:
    """옛 '템플릿' 빈 본문(일곱 칸). 숫자 없는 조건만 미리 놓여 있다 — 지금 앱은 이 모양을 읽을 때 그래프로 바꾼다."""
    slots: dict[str, list[dict[str, Any]]] = {k: [] for k in st.SLOT_KEYS}
    slots["universe"] = [_blank("manual_list")]
    slots["buy"] = [_blank("next_open")]
    slots["weight"] = [_blank("equal")]
    if template in ("target", "rank"):
        slots["weight"].append(_blank("rebalance_every"))
    if template in ("event", "rank"):
        slots["select"] = [_blank("top_n")]
    if template == "event":
        slots["sell"] = [_blank("stop_loss")]
    return {"name": name, "template": template, "slots": slots}


def new_strategy(client: Any, name: str, template: str = "event") -> int:
    r = client.post("/api/strategies", json={"body": legacy(template, name)})
    assert r.status_code == 200, r.text
    return int(r.json()["id"])
