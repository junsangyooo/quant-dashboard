"""복사 글 v3 · 전략 파일 · 옛 전략 변환(TASKS T-22 · SPEC 4-8 · ENGINE-RULES R-C1 ~ R-C9 · 11절).

- 복사 글 `quant-strategy/3`: 첫 줄 `quant-strategy/3 app>=1.0`, 본문 JSON(`indent=2` · `ensure_ascii=False` ·
  키 순서 11-1), 끝 줄 `check: <SHA-256 앞 12자리>`(11-4 · 적힌 그대로 셈).
- 비우는 것(R-C2): 모든 숫자(기간 포함) · 종목 직접 지정의 종목 · 섹터 선택 → `null`. 남기는 것: 항목 · 비교 ·
  실행 방식 · 연결 · 이름 · 위치 · 고르기 값.
- 받기(R-C3): v3는 그대로, v1(`slots` · `quant-strategy/1`)과 v2(`graph` 노드 · `quant-strategy/2`)는 별칭대로
  v3로 바꿔요(R-C8 · R-C9). 가져온 전략의 ⑤ '판 뒤 다시 사지 않는 기간'은 1(R-C6), v1 변환은 0(R-J5).
- 전략 파일(.json · R-C7): 본문과 같은 꼴, 숫자를 비우지 않아요.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from . import blocks as bk
from .catalog import CATALOG, V1_ALIASES

APP_V2 = (1, 0)
HEADER = f"quant-strategy/3 app>={APP_V2[0]}.{APP_V2[1]}"
HEADER_RE = re.compile(r"^quant-strategy/(\d+)\s+app>=(\d+)\.(\d+)$")
CHECK_RE = re.compile(r"^check:\s*([0-9a-f]{12})$")
MAX_BYTES = 64 * 1024
NOT_COPY = "복사한 전략 글이 아니에요"
NEED_NEWER = "앱을 새 버전으로 바꿔야 가져올 수 있어요"
UNKNOWN_ITEM = "이 앱 버전에 없는 조건이 있어요"
BAD_LINKS = "복사한 전략 글의 연결이 맞지 않아요"
IMPORT_NOTE = "실험실 결과는 이 앱의 백테스트와 다를 수 있어요 · 숫자는 직접 정해요"
V1_MARK = "v1"  # 본문의 "converted" 값: 변환한 v1 전략(R-J6 · R-M5 · R-B3)


class FormatError(ValueError):
    def __init__(self, message: str, kind: str = "copy", detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.detail = detail


# ── 쓰기 ─────────────────────────────────────────────────────────────────────


def check_of(body_text: str) -> str:
    """11-4: 줄마다 끝 공백을 지우고 \\n으로 이은 글자의 SHA-256 앞 12자리."""
    text = "\n".join(line.rstrip() for line in body_text.split("\n"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _ordered(body: dict[str, Any]) -> dict[str, Any]:
    """11-1의 키 순서."""
    blocks = []
    for b in body["graph"]["blocks"]:
        rows = [{"item": r["item"], "op": r["op"], "params": dict(r.get("params") or {}), "value": r.get("value"),
                 "value2": r.get("value2"), "exec": r.get("exec")} for r in b["rows"]]
        blocks.append({"id": b["id"], "stage": b["stage"], "match": b["match"], "rows": rows, "x": _xy(b.get("x")),
                       "y": _xy(b.get("y"))})
    out: dict[str, Any] = {"name": body["name"], "graph": {"blocks": blocks, "edges": [
        {"from": e["from"], "to": e["to"]} for e in body["graph"]["edges"]]}}
    if body.get("source"):
        out["source"] = {k: body["source"][k] for k in ("from", "id", "title", "version") if k in body["source"]}
    return out


def _xy(v: Any) -> int | float:
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v if isinstance(v, int | float) and not isinstance(v, bool) else 0


def blank_numbers(body: dict[str, Any]) -> dict[str, Any]:
    """R-C2: 숫자 · 종목 · 섹터는 null, 고르기 값 · 실행 방식 · 연결 · 위치는 남겨요."""
    out = copy.deepcopy(body)
    for b in out["graph"]["blocks"]:
        for r in b["rows"]:
            item = CATALOG[r["item"]]
            for p in item.params:
                if p.key in r["params"] and p.blankable:
                    r["params"][p.key] = None
            if item.choices and item.id not in ("manual_list", "sector"):
                continue  # 시장 · 종목 유형 · 흑자 같은 고르기 값은 남겨요
            r["value"] = None
            r["value2"] = None
    return out


def to_copy_text(body: dict[str, Any], source: dict[str, str] | None = None) -> str:
    data = _ordered(blank_numbers(body))
    if source:
        data["source"] = source
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return f"{HEADER}\n{text}\ncheck: {check_of(text)}\n"


def to_file(body: dict[str, Any]) -> str:
    """R-C7 전략 파일: 본문 꼴 그대로, 숫자를 비우지 않아요."""
    return json.dumps(_ordered(body), ensure_ascii=False, indent=2) + "\n"


# ── 받기 ─────────────────────────────────────────────────────────────────────


def _check_links(graph: dict[str, Any]) -> None:
    """R-C5: 잇기 규칙(단계 순서 · 순환 · 개수)을 어기면 거절. 끊긴 선 · 빈칸은 받아요."""
    by = {b["id"]: b for b in graph["blocks"]}
    has_select = any(b["stage"] == "select" for b in graph["blocks"])
    for e in graph["edges"]:
        r = bk.link_reason(by[e["from"]]["stage"], by[e["to"]]["stage"], has_select)
        if r:
            raise FormatError(f"{BAD_LINKS} · {r}", "graph", r)
    out = bk.outgoing(graph)
    for e in graph["edges"]:
        if bk._reaches(out, e["to"], e["from"]):  # noqa: SLF001
            raise FormatError(f"{BAD_LINKS} · {bk.R_CYCLE}", "graph", bk.R_CYCLE)
    if len(bk.entry_paths(graph)) > bk.PATH_MAX:
        raise FormatError(f"{BAD_LINKS} · {bk.R_MANY}", "graph", bk.R_MANY)
    if len(bk.sell_paths(graph)) > bk.PATH_MAX:
        raise FormatError(f"{BAD_LINKS} · {bk.R_MANY_SELL}", "graph", bk.R_MANY_SELL)


def _v3(data: dict[str, Any]) -> dict[str, Any]:
    try:
        body = bk.normalize(data)
    except bk.GraphError as exc:
        msg = str(exc)
        if msg.startswith(UNKNOWN_ITEM):
            raise FormatError(msg, "copy") from None
        raise FormatError(f"{BAD_LINKS} · {msg}", "graph", msg) from None
    _check_links(body["graph"])
    return body


def read_body(data: Any) -> dict[str, Any]:
    """본문(v3 블록 · v2 그래프 노드 · v1 일곱 칸)을 v3로. 변환한 v1 전략에는 "converted": "v1"."""
    if not isinstance(data, dict):
        raise FormatError(NOT_COPY)
    graph = data.get("graph")
    if isinstance(graph, dict) and "blocks" in graph:
        body = _v3(data)
        if data.get("converted") == V1_MARK:
            body["converted"] = V1_MARK
        return body
    if "slots" in data or (isinstance(graph, dict) and "nodes" in graph):
        return convert_v1(data)
    raise FormatError(NOT_COPY)


def parse_copy_text(text: str) -> tuple[dict[str, Any], list[str]]:
    """(v3 본문, 알림). 형식이 아니면 FormatError."""
    if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > MAX_BYTES:
        raise FormatError(NOT_COPY)
    lines = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n").split("\n")
    lines = [ln.rstrip() for ln in lines]
    while lines and not lines[-1]:
        lines.pop()
    if len(lines) < 3:
        raise FormatError(NOT_COPY)
    head = HEADER_RE.match(lines[0].strip())
    check = CHECK_RE.match(lines[-1].strip())
    if not head or not check:
        raise FormatError(NOT_COPY)
    fmt = int(head.group(1))
    need = (int(head.group(2)), int(head.group(3)))
    if fmt not in (1, 2, 3):
        raise FormatError(NOT_COPY)
    if fmt == 3 and need > APP_V2:
        raise FormatError(NEED_NEWER)
    body_text = "\n".join(lines[1:-1])
    if check_of(body_text) != check.group(1):
        raise FormatError(NOT_COPY)
    try:
        data = json.loads(body_text)
    except ValueError:
        raise FormatError(NOT_COPY) from None
    if not isinstance(data, dict):
        raise FormatError(NOT_COPY)
    if fmt == 1 and "slots" not in data or fmt == 2 and "nodes" not in (data.get("graph") or {}) \
            or fmt == 3 and "blocks" not in (data.get("graph") or {}):
        raise FormatError(NOT_COPY)
    body = read_body(data)
    body.pop("converted", None)  # 복사 글로 받은 전략은 새 전략(R-C6)
    body = blank_numbers(body)
    fill_cooldown(body, bk.NEW_BUY_COOLDOWN)
    if isinstance(data.get("source"), dict):
        body["source"] = {k: str(data["source"][k])[:80] for k in ("from", "id", "title", "version")
                          if k in data["source"]}
    return body, [IMPORT_NOTE]


def fill_cooldown(body: dict[str, Any], n: int) -> None:
    for b in body["graph"]["blocks"]:
        for r in b["rows"]:
            if r["item"] == "next_open":
                r["value"] = n


def read_file(text: str) -> dict[str, Any]:
    """R-C7 전략 파일 가져오기(숫자 그대로)."""
    try:
        data = json.loads(text)
    except ValueError:
        raise FormatError("전략 파일 형식이 맞지 않아요") from None
    return read_body(data)


# ── 옛 전략 변환 (R-C8 · R-C9) ───────────────────────────────────────────────

V1_STAGE = {"manual_list": "universe", "ma_cross_up": "signal", "rsi_below": "signal", "high_breakout": "signal",
            "min_turnover": "filter", "min_price": "filter", "top_n": "select", "next_open": "buy",
            "stop_loss": "sell", "take_profit": "sell", "max_hold": "sell", "ma_break_down": "sell",
            "equal": "weight", "max_per_stock": "weight", "rebalance_every": "weight"}


def v1_row(piece: str, params: dict[str, Any]) -> dict[str, Any]:
    """v1 조건 하나 → v3 줄(별칭 · 11-3)."""
    if piece not in V1_ALIASES:
        raise FormatError(f"{UNKNOWN_ITEM} · {piece}")
    p = params or {}
    if piece == "manual_list":
        return bk.new_row("manual_list", "pick", value=list(p.get("symbols") or []) or None)
    if piece == "ma_cross_up":
        return bk.new_row("ma", "cross_up", params={"n": p.get("n")})
    if piece == "ma_break_down":
        return bk.new_row("ma", "below", params={"n": p.get("n")})
    if piece == "rsi_below":
        return bk.new_row("rsi", "lt", value=p.get("level"), params={"period": p.get("period")})
    if piece == "high_breakout":
        return bk.new_row("high_n", "cross_up", params={"n": p.get("n")})
    if piece == "min_turnover":
        return bk.new_row("turnover", "gte", value=p.get("n"))
    if piece == "min_price":
        return bk.new_row("price", "gte", value=p.get("n"))
    if piece == "top_n":
        return bk.new_row("top_n", "top_n", value=p.get("n"), params={"by": "strength", "order": "desc"})
    if piece == "next_open":
        return bk.new_row("next_open", "fixed", value=0)  # v1 동작(R-J5 · Q-D2)
    if piece in ("stop_loss", "take_profit"):
        return bk.new_row(piece, "fixed", value=p.get("pct"), exec_="close")
    if piece == "max_hold":
        return bk.new_row("max_hold", "fixed", value=p.get("n"), exec_="close")
    if piece == "max_per_stock":
        return bk.new_row("max_per_stock", "fixed", value=p.get("pct"))
    if piece == "rebalance_every":
        return bk.new_row("rebalance_every", "fixed", value=p.get("n"), params={"how": p.get("how")})
    return bk.new_row(piece, "fixed")  # equal


def _slots_graph(data: dict[str, Any]) -> dict[str, Any]:
    """v1 일곱 칸 → v1 그래프 노드(v1 `from_slots`와 같은 꼴: ① → ② → ③ → ④ → ⑤ 한 줄, 매도는 ⑤에서 갈래)."""
    slots = data.get("slots")
    template = data.get("template")
    if not isinstance(slots, dict):
        raise FormatError(NOT_COPY)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    def add(it: Any) -> str:
        if not isinstance(it, dict):
            raise FormatError(NOT_COPY)
        nid = f"n{len(nodes) + 1}"
        params = dict(it.get("params") or {})
        if it.get("piece") == "rebalance_every":
            params["how"] = template if template in ("target", "rank") else None
        nodes.append({"id": nid, "piece": it.get("piece"), "params": params, "x": 0, "y": 0})
        return nid

    chain = [add(it) for key in ("universe", "signal", "filter", "select") for it in slots.get(key) or []]
    buys = [add(it) for it in slots.get("buy") or []]
    chain += buys[:1]
    edges += [{"from": a, "to": b} for a, b in zip(chain, chain[1:])]
    for it in slots.get("sell") or []:
        sid = add(it)
        if buys:
            edges.append({"from": buys[0], "to": sid})
    for it in slots.get("weight") or []:
        wid = add(it)
        if buys:
            edges.append({"from": wid, "to": buys[0]})
    return {"nodes": nodes, "edges": edges}


def convert_v1(data: dict[str, Any]) -> dict[str, Any]:
    """v1(일곱 칸 · 그래프 노드) → v3 블록. 노드 하나 = 줄 하나짜리 '모두' 블록, ⑦ 노드는 블록 하나로(R-C9)."""
    graph = _slots_graph(data) if "slots" in data else data.get("graph")
    if not isinstance(graph, dict) or not isinstance(graph.get("nodes"), list):
        raise FormatError(NOT_COPY)
    blocks: list[dict[str, Any]] = []
    weight_ids: list[str] = []
    weight_block: dict[str, Any] | None = None
    for n in graph["nodes"]:
        if not isinstance(n, dict):
            raise FormatError(NOT_COPY)
        piece = str(n.get("piece"))
        row = v1_row(piece, n.get("params") or {})
        stage = V1_STAGE[piece]
        if stage == "weight":
            weight_ids.append(str(n.get("id")))
            if weight_block is None:
                weight_block = {"id": str(n.get("id")), "stage": "weight", "match": "all", "rows": [],
                                "x": n.get("x") or 0, "y": n.get("y") or 0}
                blocks.append(weight_block)
            weight_block["rows"].append(row)
            continue
        blocks.append({"id": str(n.get("id")), "stage": stage, "match": "all", "rows": [row],
                       "x": n.get("x") or 0, "y": n.get("y") or 0})
    edges: list[dict[str, str]] = []
    for e in graph.get("edges") or []:
        if not isinstance(e, dict):
            raise FormatError(NOT_COPY)
        src = str(e.get("from"))
        dst = str(e.get("to"))
        if src in weight_ids and weight_block is not None:
            src = weight_block["id"]
        if dst in weight_ids and weight_block is not None:
            dst = weight_block["id"]
        if {"from": src, "to": dst} not in edges:
            edges.append({"from": src, "to": dst})
    body = _v3({"name": data.get("name") or "새 전략", "graph": {"blocks": blocks, "edges": edges}})
    if isinstance(data.get("source"), dict):
        body["source"] = data["source"]
    body["converted"] = V1_MARK
    return body
