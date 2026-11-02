"""전략 v2 블록 모델(TASKS T-21 · SPEC 4절 · ENGINE-RULES 1 · 2절 · R-X2 · R-M1).

본문(v3): {"name", "graph": {"blocks": [{"id", "stage", "match", "rows": [{"item", "op", "params", "value",
"value2", "exec"}], "x", "y"}], "edges": [{"from", "to"}]}}

- 블록 하나 = 단계 하나 + 조건 줄 목록 + 머리 토글(② ③ ⑥만 · 모두 / 하나라도) + 위치(R-G1 · R-G3).
- 경로 규칙은 v1 캔버스 그대로(R-G9 · R-G10 · R-G12): 진입 경로 = ①에서 ⑤까지, 매도 경로 = ⑤에서 끝까지.
  경로 안은 모두, 경로끼리는 하나라도. ⑥ → ⑥은 '같은 날 모두'.
- 문제 목록(R-P1 ~ R-P12)은 저장은 막지 않고 백테스트 · 모의투자 · 실전 운용 시작을 막아요.
- 실행 방식 자리 규칙(R-X2): 장중 감시 · 조건주문은 그 줄이 혼자 매도를 정할 때만. 아니면 종가 확인.
- 화면 글은 그림(V2-23)과 SPEC 4-4의 글자 그대로예요.
"""

from __future__ import annotations

import copy
import math
import re
from typing import Any

from .catalog import (
    CATALOG,
    CHOICE_NAMES,
    CIRCLE,
    EXEC_NAME,
    EXECS,
    NO_VALUE_OPS,
    OP_NAME,
    RANK_OPS,
    STAGE_CIRCLE,
    STAGE_NAME,
    STAGES,
    Item,
    Num,
)

BLOCK_MAX = 20
ROW_MAX = 10
PATH_MAX = 20
ONCE_STAGES = ("universe", "select", "buy", "weight")
TOGGLE_STAGES = ("signal", "filter", "sell")
DEFAULT_MATCH = {"signal": "all", "filter": "all", "sell": "any"}
NEW_BUY_COOLDOWN = 1  # R-G7: 새 전략 · 가져온 전략의 '판 뒤 다시 사지 않는 기간'
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
SYMBOL_RE = re.compile(r"^[0-9]{6}\Z")
MODES = {"event": "조건 충족 시 매매", "target": "목표 비중 리밸런싱", "rank": "순위 교체 리밸런싱"}

# 잇기 규칙(R-G12): 뒤에 올 수 있는 단계. ④가 있으면 ② · ③ → ⑤는 막아요.
NEXT: dict[str, set[str]] = {
    "universe": {"signal", "filter", "select", "buy"},
    "signal": {"signal", "filter", "select", "buy"},
    "filter": {"signal", "filter", "select", "buy"},
    "select": {"buy"},
    "buy": {"sell"},
    "sell": {"sell"},
    "weight": {"buy"},
}

R_UNIVERSE_IN = "유니버스 단계 앞에는 다른 단계를 연결할 수 없어요"
R_SELL = "매도 단계는 매수 단계 뒤에 이어요"
R_ENTRY = "신호 · 필터 단계는 매수 단계 앞에 이어요"
R_SELECT = "종목 선정 단계는 매수 단계 바로 앞에 하나만 놓아요"
R_WEIGHT = "비중 단계는 매수 단계에 연결해요"
R_CYCLE = "선이 이미 지나온 조건으로 돌아가면 안 돼요"
R_DUP = "이미 연결돼 있어요"
R_MANY = f"경로가 너무 많아요 · 진입 경로는 최대 {PATH_MAX}개예요"
R_MANY_SELL = f"경로가 너무 많아요 · 매도 경로는 최대 {PATH_MAX}개예요"
SELL_CHAIN_CONFIRM = (
    "이어서 연결한 매도 조건은 같은 날 모두 맞아야 해요",
    "하나라도 맞으면 팔려면 같은 단계 안으로 옮겨요",
)
EXEC_FALLBACK = "다른 조건과 함께 맞아야 해서 종가로 확인해요"
EXEC_RULE = ("장중 감시 · 조건주문(토스)은 셋이 모두 맞을 때만 골라요 · 단계가 '하나라도 맞으면'이거나 줄이 하나 · "
             "⑤ 매수 바로 뒤 · 뒤에 이어진 ⑥ 매도 없음")
MODE_CHANGED = "방식이 바뀌면 돌파 신호의 뜻도 바뀌어요"


class GraphError(ValueError):
    """본문 형식이 맞지 않아요(편집기는 만들지 않는 모양)."""


# ── 글 도우미 ────────────────────────────────────────────────────────────────


def _has_batchim(word: str) -> bool:
    ch = word.rstrip()[-1:] or "가"
    if "가" <= ch <= "힣":
        return (ord(ch) - 0xAC00) % 28 != 0
    if ch.isdigit():
        return ch in "013678"
    return ch.lower() in "lmnr"


def josa(word: str, pair: str) -> str:
    """josa('PER', '은/는') → 'PER은'. 받침이 있으면 앞, 없으면 뒤."""
    a, b = pair.split("/")
    if pair == "로/으로":
        ch = word.rstrip()[-1:]
        rieul = "가" <= ch <= "힣" and (ord(ch) - 0xAC00) % 28 == 8
        return word + ("로" if not _has_batchim(word) or rieul else "으로")
    return word + (a if _has_batchim(word) else b)


def num_text(v: float | int) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    if isinstance(v, int):
        return f"{v:,}".replace("-", "−")
    return f"{v:,}".rstrip("0").rstrip(".").replace("-", "−")


def short_name(item: Item) -> str:
    """'PER(최근 4분기 합)' → 'PER'."""
    return item.name.split("(")[0].strip()


def stage_label(stage: str) -> str:
    return f"{STAGE_CIRCLE[stage]} {STAGE_NAME[stage]}"


def value_num(item: Item, op: str) -> Num | None:
    return item.rank if op in RANK_OPS and item.rank else item.value


def _unit(item: Item, op: str) -> str:
    num = value_num(item, op)
    return num.unit if num else ""


def _with_unit(v: Any, unit: str) -> str:
    if v is None:
        return "[빈칸]"
    if isinstance(v, bool) or not isinstance(v, int | float):
        return str(v)
    return f"{num_text(v)}{unit}"


def row_text(row: dict[str, Any]) -> str:
    """조건 줄 하나를 칩 글로: '손절 −7%' · '익절 +15%' · 'PER 15배 이하'."""
    item = CATALOG[row["item"]]
    v = row.get("value")
    if item.id == "stop_loss":
        return f"손절 −{num_text(v)}%" if v is not None else "손절 [빈칸]"
    if item.id == "take_profit":
        return f"익절 +{num_text(v)}%" if v is not None else "익절 [빈칸]"
    if item.id == "trailing_stop":
        return f"트레일링 스톱 −{num_text(v)}%" if v is not None else "트레일링 스톱 [빈칸]"
    if item.id == "max_hold":
        return f"최대 보유 {_with_unit(v, '거래일')}"
    op = row["op"]
    name = short_name(item)
    n = (row.get("params") or {}).get("n")
    if op == "exclude" and item.id != "sector":
        return item.name
    if item.choices and op == "pick":
        picked = v if isinstance(v, list) else ([v] if v else [])
        return " · ".join(CHOICE_NAMES.get(str(c), str(c)) for c in picked) or f"{name} [빈칸]"
    if item.id == "manual_list":
        return f"{name} {len(v)}종목" if v else f"{name} [빈칸]"
    if item.id in ("ma", "ema"):
        return f"{_with_unit(n, '일')} {name} {OP_NAME[op]}"
    if op in NO_VALUE_OPS:
        return f"{name} {OP_NAME[op]}"
    if op == "between":
        return f"{name} {_with_unit(v, _unit(item, op))} ~ {_with_unit(row.get('value2'), _unit(item, op))}"
    if op == "fixed":
        return name if v is None and item.value is None else f"{name} {_with_unit(v, _unit(item, op))}"
    return f"{name} {_with_unit(v, _unit(item, op))} {OP_NAME[op]}"


# ── 모양 · 만들기 ────────────────────────────────────────────────────────────


def new_block(bid: str, stage: str, x: float = 0, y: float = 0) -> dict[str, Any]:
    """새 블록(R-G3 기본 토글 · R-G7 ⑤ 기본 1거래일 · ⑦ 동일 비중)."""
    rows: list[dict[str, Any]] = []
    if stage == "buy":
        rows = [new_row("next_open", "fixed", value=NEW_BUY_COOLDOWN)]
    elif stage == "weight":
        rows = [new_row("equal", "fixed")]
    return {"id": bid, "stage": stage, "match": DEFAULT_MATCH.get(stage, "all"), "rows": rows, "x": x, "y": y}


def new_row(item_id: str, op: str | None = None, *, value: Any = None, params: dict[str, Any] | None = None,
            exec_: str | None = None) -> dict[str, Any]:
    item = CATALOG[item_id]
    op = op or item.ops[0]
    p = {prm.key: None for prm in item.params if not prm.when_op or op in prm.when_op}
    p.update(params or {})
    if item.id == "top_n":
        p["by"] = p.get("by") or "strength"
        p["order"] = p.get("order") or "desc"
        if p.get("by") not in ("return_n", "volatility"):
            p.pop("n", None)
    if item.execs and exec_ is None:
        exec_ = "intraday" if "intraday" in item.execs else item.execs[0]
    return {"item": item_id, "op": op, "params": p, "value": value, "value2": None,
            "exec": exec_ if item.execs else None}


def blocks_of(body: dict[str, Any]) -> list[dict[str, Any]]:
    return list(body["graph"]["blocks"])


def _index(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {b["id"]: b for b in graph["blocks"]}


def add_block_reason(graph: dict[str, Any], stage: str) -> str | None:
    """이 단계 블록을 하나 더 놓을 수 없는 이유(R-G2)."""
    if len(graph["blocks"]) >= BLOCK_MAX:
        return f"단계는 {BLOCK_MAX}개까지 놓을 수 있어요"
    if stage in ONCE_STAGES and any(b["stage"] == stage for b in graph["blocks"]):
        return f"{STAGE_NAME[stage]} 단계는 하나만 놓을 수 있어요"
    return None


def add_row_reason(block: dict[str, Any], item_id: str) -> str | None:
    """이 블록에 이 조건 줄을 추가할 수 없는 이유(R-G2 · R-G4 · R-G6 · R-G8)."""
    item = CATALOG.get(item_id)
    stage = block["stage"]
    if item is None:
        return "이 앱 버전에 없는 조건이 있어요"
    if stage not in item.stages:
        return f"{josa(short_name(item), '은/는')} {stage_label(stage)} 단계에 추가할 수 없어요"
    if len(block["rows"]) >= ROW_MAX:
        return f"한 단계에 조건은 {ROW_MAX}개까지 추가할 수 있어요"
    if stage in ("select", "buy") and block["rows"]:
        return f"{STAGE_NAME[stage]} 단계에는 조건을 하나만 추가할 수 있어요"
    if stage in ("universe", "weight") and any(r["item"] == item_id for r in block["rows"]):
        return f"{josa(short_name(item), '은/는')} 하나만 추가할 수 있어요"
    return None


def normalize(raw: Any) -> dict[str, Any]:
    """저장 · 받기 전 형식 검사(모르는 단계 · 항목 · 비교 · 개수 · 토글 · 실행 방식). 맞으면 정리한 본문."""
    if not isinstance(raw, dict) or not isinstance(raw.get("graph"), dict):
        raise GraphError("전략 형식이 맞지 않아요")
    g = raw["graph"]
    blocks, edges = g.get("blocks"), g.get("edges")
    if not isinstance(blocks, list) or not isinstance(edges, list):
        raise GraphError("전략 형식이 맞지 않아요")
    if len(blocks) > BLOCK_MAX:
        raise GraphError(f"단계는 {BLOCK_MAX}개까지 놓을 수 있어요")
    out_blocks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for b in blocks:
        if not isinstance(b, dict) or not isinstance(b.get("id"), str) or not ID_RE.match(b["id"]):
            raise GraphError("단계 형식이 맞지 않아요")
        if b["id"] in seen:
            raise GraphError("같은 이름의 단계가 둘이에요")
        seen.add(b["id"])
        stage = b.get("stage")
        if stage not in STAGES:
            raise GraphError("모르는 단계가 있어요")
        reason = add_block_reason({"blocks": out_blocks}, stage)
        if reason:
            raise GraphError(reason)
        match = b.get("match", "all")
        if stage not in TOGGLE_STAGES:
            match = "all"
        elif match not in ("all", "any"):
            raise GraphError("단계 머리 토글 형식이 맞지 않아요")
        rows_in = b.get("rows")
        if not isinstance(rows_in, list):
            raise GraphError("조건 형식이 맞지 않아요")
        block = {"id": b["id"], "stage": stage, "match": match, "rows": [], "x": _num(b.get("x")),
                 "y": _num(b.get("y"))}
        for r in rows_in:
            row = _normalize_row(r)
            reason = add_row_reason(block, row["item"])
            if reason:
                raise GraphError(reason)
            block["rows"].append(row)
        out_blocks.append(block)
    out_edges = []
    pairs = set()
    for e in edges:
        if not isinstance(e, dict) or e.get("from") not in seen or e.get("to") not in seen:
            raise GraphError("없는 단계를 잇는 선이 있어요")
        key = (e["from"], e["to"])
        if key in pairs:
            raise GraphError("같은 두 단계 사이 선은 하나예요")
        pairs.add(key)
        out_edges.append({"from": e["from"], "to": e["to"]})
    name = str(raw.get("name") or "").strip()[:60] or "새 전략"
    body: dict[str, Any] = {"name": name, "graph": {"blocks": out_blocks, "edges": out_edges}}
    if isinstance(raw.get("source"), dict):
        body["source"] = raw["source"]
    return body


def _num(v: Any) -> float:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) and math.isfinite(v) else 0.0


def _normalize_row(r: Any) -> dict[str, Any]:
    if not isinstance(r, dict):
        raise GraphError("조건 형식이 맞지 않아요")
    item = CATALOG.get(str(r.get("item")))
    if item is None:
        raise GraphError(f"이 앱 버전에 없는 조건이 있어요 · {r.get('item')}")
    op = r.get("op")
    if op not in item.ops:
        raise GraphError(f"이 앱 버전에 없는 조건이 있어요 · {item.name}")
    params_in = r.get("params") or {}
    if not isinstance(params_in, dict):
        raise GraphError("조건 형식이 맞지 않아요")
    params: dict[str, Any] = {}
    for p in item.params:
        if p.when_op and op not in p.when_op:
            continue
        if item.id == "top_n" and p.key == "n" and params.get("by") not in ("return_n", "volatility"):
            continue
        v = params_in.get(p.key)
        if p.choices:
            params[p.key] = v if v in p.choices else None
        else:
            params[p.key] = v if v is None or isinstance(v, int | float) and not isinstance(v, bool) else v
    exec_ = r.get("exec")
    if item.execs:
        if exec_ not in EXECS or exec_ not in item.execs:
            raise GraphError(f"실행 방식 형식이 맞지 않아요 · {item.name}")
    else:
        exec_ = None
    value = r.get("value")
    if item.id in ("manual_list", "sector") and value is not None:
        if isinstance(value, str):
            value = [s for s in re.split(r"[\s,]+", value) if s]
        if not isinstance(value, list):
            raise GraphError("종목 형식이 맞지 않아요")
        value = [_clean_symbol(s) for s in value] if item.id == "manual_list" else [str(s) for s in value]
        value = list(dict.fromkeys(value))
    elif item.choices and value is not None:
        values = value if isinstance(value, list) else [value]
        value = [v for v in values if v in item.choices] if isinstance(value, list) else (
            value if value in item.choices else None)
    return {"item": item.id, "op": op, "params": params, "value": value, "value2": r.get("value2"), "exec": exec_}


def _clean_symbol(s: Any) -> str:
    text = str(s).strip().upper()
    for suf in (".KS", ".KQ"):
        if text.endswith(suf):
            text = text[: -len(suf)]
    return text


# ── 선 · 경로 ────────────────────────────────────────────────────────────────


def link_reason(src_stage: str, dst_stage: str, has_select: bool) -> str | None:
    if dst_stage == "universe":
        return R_UNIVERSE_IN
    if src_stage == "weight" or dst_stage == "weight":
        return None if (src_stage == "weight" and dst_stage == "buy") else R_WEIGHT
    if dst_stage == "sell":
        return None if src_stage in ("buy", "sell") else R_SELL
    if src_stage == "sell":
        return R_SELL
    if src_stage == "buy":
        return f"{STAGE_NAME['buy']} 단계는 하나만 놓을 수 있어요" if dst_stage == "buy" else R_ENTRY
    if src_stage == "select":
        return None if dst_stage == "buy" else R_SELECT
    if dst_stage == "buy" and has_select:
        return R_SELECT
    return None


def _key(b: dict[str, Any], i: int) -> tuple[float, float, int]:
    return (float(b.get("y") or 0), float(b.get("x") or 0), i)


def outgoing(graph: dict[str, Any]) -> dict[str, list[str]]:
    by = _index(graph)
    out: dict[str, list[tuple[tuple[float, float, int], str]]] = {k: [] for k in by}
    for i, e in enumerate(graph["edges"]):
        if e["from"] in by and e["to"] in by:
            out[e["from"]].append((_key(by[e["to"]], i), e["to"]))
    return {k: [d for _, d in sorted(v)] for k, v in out.items()}


def incoming(graph: dict[str, Any]) -> dict[str, list[str]]:
    by = _index(graph)
    inc: dict[str, list[str]] = {k: [] for k in by}
    for e in graph["edges"]:
        if e["from"] in by and e["to"] in by:
            inc[e["to"]].append(e["from"])
    return inc


def _reaches(out: dict[str, list[str]], a: str, b: str) -> bool:
    seen, stack = {a}, [a]
    while stack:
        cur = stack.pop()
        if cur == b:
            return True
        for nxt in out.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


def entry_paths(graph: dict[str, Any], limit: int = PATH_MAX + 1) -> list[dict[str, Any]]:
    by = _index(graph)
    uni = [b["id"] for b in graph["blocks"] if b["stage"] == "universe"]
    if not uni:
        return []
    out = outgoing(graph)
    paths: list[dict[str, Any]] = []

    def walk(path: list[str]) -> None:
        if len(paths) >= limit:
            return
        last = path[-1]
        if by[last]["stage"] == "buy":
            paths.append({"blocks": list(path), "complete": True})
            return
        nexts = [d for d in out[last] if d not in path and by[d]["stage"] in ("signal", "filter", "select", "buy")]
        if not nexts:
            paths.append({"blocks": list(path), "complete": False})
            return
        for d in nexts:
            walk([*path, d])
            if len(paths) >= limit:
                return

    walk([uni[0]])
    return paths


def sell_paths(graph: dict[str, Any], limit: int = PATH_MAX + 1) -> list[dict[str, Any]]:
    by = _index(graph)
    buys = [b["id"] for b in graph["blocks"] if b["stage"] == "buy"]
    if not buys:
        return []
    out = outgoing(graph)
    paths: list[dict[str, Any]] = []

    def walk(path: list[str]) -> None:
        if len(paths) >= limit:
            return
        nexts = [d for d in out[path[-1]] if d not in path and by[d]["stage"] == "sell"]
        if not nexts:
            if len(path) > 1:
                paths.append({"blocks": list(path)})
            return
        for d in nexts:
            walk([*path, d])
            if len(paths) >= limit:
                return

    walk([buys[0]])
    return paths


def edge_reason(graph: dict[str, Any], src: str, dst: str) -> str | None:
    """src → dst 선을 이을 수 없는 이유(R-G12). ⑥ → ⑥은 이유 없음(이을 때 확인 창 · `needs_confirm`)."""
    by = _index(graph)
    if src not in by or dst not in by:
        return "없는 단계예요"
    if src == dst:
        return R_CYCLE
    has_select = any(b["stage"] == "select" for b in graph["blocks"])
    r = link_reason(by[src]["stage"], by[dst]["stage"], has_select)
    if r:
        return r
    if any(e["from"] == src and e["to"] == dst for e in graph["edges"]):
        return R_DUP
    if _reaches(outgoing(graph), dst, src):
        return R_CYCLE
    g2 = {"blocks": graph["blocks"], "edges": [*graph["edges"], {"from": src, "to": dst}]}
    if len(entry_paths(g2)) > PATH_MAX:
        return R_MANY
    if len(sell_paths(g2)) > PATH_MAX:
        return R_MANY_SELL
    return None


def needs_confirm(graph: dict[str, Any], src: str, dst: str) -> tuple[str, ...] | None:
    """⑥ → ⑥ 잇기 확인 창 글(SPEC 4-4). 그렇게 이으면 장중 감시 줄이 종가 확인으로 바뀌는 것도 알려요."""
    by = _index(graph)
    if by.get(src, {}).get("stage") != "sell" or by.get(dst, {}).get("stage") != "sell":
        return None
    g2 = {"blocks": graph["blocks"], "edges": [*graph["edges"], {"from": src, "to": dst}]}
    lines = list(SELL_CHAIN_CONFIRM)
    changed = []
    for b in (by[src], by[dst]):
        for i, row in enumerate(b["rows"]):
            if row.get("exec") in ("intraday", "broker") and exec_of(g2, b["id"], i) == "close":
                changed.append(row_text(row))
    if changed:
        others = [row_text(r) for b in (by[src], by[dst]) for r in b["rows"] if row_text(r) not in changed]
        tail = f"그래도 연결하면 {' · '.join(changed)}{'는' if not _has_batchim(changed[-1]) else '은'} 종가 확인으로 바뀌고"
        if others:
            tail += f", {' · '.join(others)}{'와' if not _has_batchim(others[-1]) else '과'} 같은 날 맞아야 팔려요"
        lines.append(tail)
    return tuple(lines)


def linked_weight(graph: dict[str, Any]) -> dict[str, Any] | None:
    by = _index(graph)
    buys = {b["id"] for b in graph["blocks"] if b["stage"] == "buy"}
    for e in graph["edges"]:
        if e["to"] in buys and by.get(e["from"], {}).get("stage") == "weight":
            return by[e["from"]]
    return None


def mode_of(graph: dict[str, Any]) -> str | None:
    """R-M1: ⑤에 이어진 ⑦에 리밸런싱 주기 줄이 없으면 event, 있으면 그 방식(빈칸이면 None)."""
    w = linked_weight(graph)
    for row in (w or {}).get("rows", []):
        if row["item"] == "rebalance_every":
            how = (row.get("params") or {}).get("how")
            return how if how in ("target", "rank") else None
    return "event"


def mode_change_note(before: dict[str, Any], after: dict[str, Any]) -> str | None:
    a, b = mode_of(before), mode_of(after)
    if a != b and a is not None and b is not None:
        return MODE_CHANGED
    return None


# ── 실행 방식 자리 규칙 (R-X2) ───────────────────────────────────────────────


def exec_place_ok(graph: dict[str, Any], block_id: str) -> bool:
    """이 ⑥ 블록의 줄이 '혼자 매도를 정하는' 자리인가: ① 하나라도이거나 줄 하나 ② 들어오는 선이 모두 ⑤에서
    바로 옴(⑤에서도 오고 다른 ⑥을 거쳐서도 오면 아님) ③ 뒤에 이어진 ⑥ 없음."""
    by = _index(graph)
    b = by[block_id]
    if b["stage"] != "sell":
        return False
    if not (b["match"] == "any" or len(b["rows"]) <= 1):
        return False
    inc = incoming(graph)[block_id]
    if not inc or any(by[s]["stage"] != "buy" for s in inc):
        return False
    return not any(by[d]["stage"] == "sell" for d in outgoing(graph)[block_id])


def exec_of(graph: dict[str, Any], block_id: str, row_index: int) -> str | None:
    """실제로 쓰는 실행 방식. 자리가 안 맞으면 장중 감시 · 조건주문도 종가 확인."""
    by = _index(graph)
    row = by[block_id]["rows"][row_index]
    ex = row.get("exec")
    if ex in ("intraday", "broker") and not exec_place_ok(graph, block_id):
        return "close"
    return ex


def exec_chip(graph: dict[str, Any], block_id: str, row_index: int) -> dict[str, str] | None:
    """칩 글: '장중 감시' / '종가 확인 · 다른 조건과 함께 맞아야 해서 종가로 확인해요'."""
    by = _index(graph)
    row = by[block_id]["rows"][row_index]
    if row.get("exec") is None:
        return None
    eff = exec_of(graph, block_id, row_index)
    forced = eff != row.get("exec")
    return {"exec": str(eff), "name": EXEC_NAME[str(eff)], "reason": EXEC_FALLBACK if forced else ""}


def has_stop(graph: dict[str, Any]) -> bool:
    """R-X10: 혼자 매도를 정하는 손절 · 트레일링 줄이 있나."""
    for b in graph["blocks"]:
        if b["stage"] == "sell" and exec_place_ok(graph, b["id"]):
            if any(r["item"] in ("stop_loss", "trailing_stop") for r in b["rows"]):
                return True
    return False


# ── 블록 · 경로 판정 (R-G9 · R-G10) ──────────────────────────────────────────


def block_pass(block: dict[str, Any], row_results: list[bool]) -> bool:
    if not row_results:
        return False
    return all(row_results) if block["match"] == "all" else any(row_results)


def paths_pass(paths: list[dict[str, Any]], passed: dict[str, bool], *, skip: tuple[str, ...] = ()) -> list[int]:
    """통과한 경로 번호(0부터). 경로 위 블록이 모두 통과해야 그 경로가 통과해요."""
    out = []
    for i, p in enumerate(paths):
        ids = [bid for bid in p["blocks"] if bid not in skip]
        if p.get("complete", True) and all(passed.get(bid, False) for bid in ids):
            out.append(i)
    return out


def universe_symbols(block: dict[str, Any], info: dict[str, dict[str, Any]]) -> list[str]:
    """R-G5: 종목 직접 지정이 있으면 나머지 줄은 그 목록을 다시 걸러요(info: 종목 → 시장 · 유형 · 우선주 등)."""
    pick = next((r for r in block["rows"] if r["item"] == "manual_list"), None)
    symbols = list(pick["value"] or []) if pick else list(info)
    out = []
    for s in symbols:
        meta = info.get(s, {})
        ok = True
        for r in block["rows"]:
            if r["item"] == "market" and r["value"]:
                ok &= meta.get("market") in r["value"]
            elif r["item"] == "security_type" and r["value"]:
                ok &= meta.get("security_type") in r["value"]
            elif r["item"] == "exclude_preferred":
                ok &= meta.get("common", True)
            elif r["item"] == "exclude_leveraged":
                ok &= not meta.get("leverage")
        if ok:
            out.append(s)
    return out


# ── 문제 목록 (R-P1 ~ R-P12) ─────────────────────────────────────────────────


def _problem(kind: str, title: str, detail: str = "", block: str = "", row: int | None = None,
             stage: str = "") -> dict[str, Any]:
    return {"kind": kind, "title": title, "detail": detail, "block": block, "row": row, "stage": stage}


def _range_text(item: Item, num: Num) -> str:
    return f"{num_text(num.lo)}~{num_text(num.hi)}{num.unit}"


def _value_problem(item: Item, op: str, v: Any, *, label: str | None = None) -> tuple[str, str] | None:
    """(kind, 글). blank → '값이 비어 있어요', range → '…로 입력해요'(지금 값)."""
    name = label or short_name(item)
    num = value_num(item, op)
    if num is None:
        return None
    if v is None:
        return ("blank", f"{name} 값이 비어 있어요")
    rng = _range_text(item, num)
    if isinstance(v, bool) or not isinstance(v, int | float) or not math.isfinite(float(v)) \
            or not (num.lo <= v <= num.hi) or (num.integer and float(v) != int(v)):
        return ("range", f"{josa(name, '은/는')} {josa(rng, '로/으로')} 입력해요")
    return None


def _row_problems(block: dict[str, Any], i: int, row: dict[str, Any], dart: bool) -> list[dict[str, Any]]:
    item = CATALOG[row["item"]]
    stage = block["stage"]
    where = stage_label(stage)
    out: list[dict[str, Any]] = []
    mk = lambda kind, title, detail: out.append(  # noqa: E731
        _problem(kind, title, detail, block["id"], i, stage))
    if item.lock == "dart" and not dart:
        mk("locked", f"{josa(short_name(item), '은/는')} DART를 연결해야 써요 · 연결 ›", where)
    # 매개변수(기간 등)
    for p in item.params:
        if p.key not in row["params"]:
            continue
        v = row["params"][p.key]
        if p.choices:
            if v is None:
                label = p.label if " " in p.label else f"{short_name(item)} {p.label}"
                mk("blank", f"{label} 값이 비어 있어요", f"{where} · {josa(p.label, '을/를')} 골라요")
            continue
        if p.num is None:
            continue
        pseudo = Item(item.id, item.name, item.category, item.ops, item.stages, value=p.num)
        found = _value_problem(pseudo, "gte", v, label=f"{short_name(item)} {p.label}")
        if found:
            kind, text = found
            rng = f"{num_text(p.num.lo)}~{num_text(p.num.hi)}{p.num.unit}"
            mk(kind, text, f"{where} · {short_name(item)} {p.label}은 {rng}로 입력해요" if kind == "blank"
               else f"{where} · 지금 {_with_unit(v, p.num.unit)}")
    # 값
    v = row.get("value")
    if item.id == "manual_list":
        if not v:
            mk("blank", "종목 직접 지정 값이 비어 있어요", f"{where} · 1~30종목")
        else:
            bad = [s for s in v if not SYMBOL_RE.match(str(s))]
            if bad:
                mk("range", f"한국 종목 6자리 코드가 아니에요 · {', '.join(bad[:5])}", where)
            elif len(v) > 30:
                mk("range", "종목은 30개까지 입력할 수 있어요", where)
    elif item.choices or item.id == "sector":
        if not v:
            mk("blank", f"{short_name(item)} 값이 비어 있어요", f"{where} · 값을 골라요")
    elif row["op"] not in NO_VALUE_OPS and value_num(item, row["op"]) is not None:
        label = None
        if item.id == "top_n":  # ④는 정렬 항목 이름으로(그림 V2-23 빈 캔버스: '신호 강도 값이 비어 있어요')
            by = (row.get("params") or {}).get("by") or "strength"
            label = "신호 강도" if by == "strength" else short_name(CATALOG[by])
        found = _value_problem(item, row["op"], v, label=label)
        if found:
            kind, text = found
            num = value_num(item, row["op"])
            assert num is not None
            if kind == "blank" and item.id == "top_n":
                detail = f"{where} · {_range_text(item, num)}"
            elif kind == "blank":
                detail = f"{where} · {josa(short_name(item), '은/는')} {josa(_range_text(item, num), '로/으로')} 입력해요"
            else:
                detail = f"{where} · 지금 {_with_unit(v, num.unit)}"
            mk(kind, text, detail)
        if row["op"] == "between":
            v2 = row.get("value2")
            found2 = _value_problem(item, row["op"], v2)
            if found2:
                mk(found2[0], found2[1], where)
            elif found is None and isinstance(v, int | float) and isinstance(v2, int | float) and v > v2:
                mk("order", "앞 값이 뒤 값보다 커요", f"{where} · {row_text(row)}")
    return out


def _required_rows(graph: dict[str, Any], block_ids: list[str]) -> list[tuple[str, int, dict[str, Any]]]:
    """경로 위에서 '같은 날 모두' 맞아야 하는 줄: 모두 블록의 줄 + 줄 하나짜리 하나라도 블록의 줄."""
    by = _index(graph)
    out = []
    for bid in block_ids:
        b = by[bid]
        if b["match"] == "all" or len(b["rows"]) == 1:
            out += [(bid, i, r) for i, r in enumerate(b["rows"])]
    return out


def _conflict(a: dict[str, Any], b: dict[str, Any]) -> bool:
    items = {a["item"], b["item"]}
    if items == {"stop_loss", "take_profit"}:
        return True
    if a["item"] != b["item"] or (a.get("params") or {}) != (b.get("params") or {}):
        return False
    if {a["op"], b["op"]} == {"above", "below"}:
        return True
    lo, hi = (a, b) if a["op"] == "gte" and b["op"] == "lte" else (b, a)
    if lo["op"] == "gte" and hi["op"] == "lte":
        va, vb = lo.get("value"), hi.get("value")
        return isinstance(va, int | float) and isinstance(vb, int | float) and va > vb
    return False


def analyze(graph: dict[str, Any], *, dart: bool = True) -> dict[str, Any]:
    """경로 · 매매 방식 · 문제 · 경고. 저장 · 백테스트 · 모의투자 · 화면이 같이 써요."""
    blocks = graph["blocks"]
    by = _index(graph)
    entry = entry_paths(graph)
    sells = sell_paths(graph)
    too_many = len(entry) > PATH_MAX or len(sells) > PATH_MAX
    entry, sells = entry[:PATH_MAX], sells[:PATH_MAX]
    mode = mode_of(graph)
    problems: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    # R-P3 빈 단계 · R-P1 빈칸 · 범위 밖 · R-P2 사이 순서 · R-P4 잠긴 조건 · R-P9 리밸런싱 방식 빈칸
    for b in blocks:
        if not b["rows"]:
            problems.append(_problem("empty", "조건이 없는 단계예요 · 조건을 추가하거나 단계를 삭제해요",
                                     stage_label(b["stage"]), b["id"], None, b["stage"]))
        for i, row in enumerate(b["rows"]):
            problems += _row_problems(b, i, row, dart)

    # R-P7 꼭 있어야 하는 단계
    def required(stage: str, text: str) -> None:
        problems.append(_problem("required", f"필요한 조건 · {text}", stage_label(stage), "", None, stage))

    stages = {b["stage"] for b in blocks}
    if "universe" not in stages:
        required("universe", "유니버스 단계가 있어야 해요")
    if "buy" not in stages:
        required("buy", "매수 단계가 있어야 해요")
    weight = next((b for b in blocks if b["stage"] == "weight"), None)
    if weight is None or not any(r["item"] == "equal" for r in weight["rows"]):
        required("weight", "동일 비중 조건이 있어야 해요")
    select = next((b for b in blocks if b["stage"] == "select"), None)
    if mode in ("event", "rank") and select is None:
        required("select", f"{MODES[mode]}에는 종목 선정 단계가 있어야 해요")
    if mode == "event" and not sells:
        problems.append(_problem("required", "매도 경로가 없어요", "⑥ 매도를 ⑤ 매수 뒤에 이어요", "", None, "sell"))

    # R-P6 진입 경로에 신호 없음(조건 충족 시 매매 · 순위 교체는 ④ 정렬이 신호 강도일 때만)
    sort_by = ((select or {}).get("rows") or [{}])[0].get("params", {}).get("by") if select else None
    need_signal = mode == "event" or (mode == "rank" and (select is None or sort_by in (None, "strength")))
    if need_signal:
        for k, p in enumerate(entry, 1):
            if p["complete"] and not any(by[i]["stage"] == "signal" for i in p["blocks"]):
                problems.append(_problem("no_signal", f"진입 경로 {k}에 신호가 없어요",
                                         "신호 없이 연결하면 매일 모든 종목이 매수 후보가 돼요", "", None, "signal"))

    # R-P8 방식에 못 쓰는 단계
    if mode == "target":
        for b in blocks:
            if b["stage"] == "sell":
                problems.append(_problem("unusable", "목표 비중 리밸런싱에서는 매도 단계를 쓰지 않아요",
                                         stage_label("sell"), b["id"], None, "sell"))

    # R-P5 같은 날 함께 맞을 수 없는 조건(같은 경로나 '모두' 블록)
    seen_pairs: set[tuple[tuple[str, int], tuple[str, int]]] = set()
    groups: list[tuple[list[str], str]] = [(p["blocks"][1:], "팔지") for p in sells]
    groups += [(p["blocks"], "사지") for p in entry if p["complete"]]
    groups += [([b["id"]], "팔지" if b["stage"] == "sell" else "사지") for b in blocks if b["match"] == "all"]
    for ids, verb in groups:
        rows = _required_rows(graph, ids)
        for x in range(len(rows)):
            for y in range(x + 1, len(rows)):
                (ba, ia, ra), (bb, ib, rb) = rows[x], rows[y]
                key = ((ba, ia), (bb, ib))
                if key in seen_pairs or not _conflict(ra, rb):
                    continue
                seen_pairs.add(key)
                ta, tb = row_text(ra), row_text(rb)
                problems.append(_problem("conflict", "같은 날 함께 맞을 수 없는 조건이에요",
                                         f"{ta}{'과' if _has_batchim(ta) else '와'} {tb} · 이 경로로는 {verb} 않아요",
                                         ba, ia, by[ba]["stage"]))

    # R-P11 경고: 손절 · 트레일링이 다른 줄과 같은 날 맞아야 할 때
    for p in sells:
        ids = p["blocks"][1:]
        for bid in ids:
            b = by[bid]
            together = len(ids) > 1 or (b["match"] == "all" and len(b["rows"]) > 1)
            if not together:
                continue
            for i, r in enumerate(b["rows"]):
                if r["item"] in ("stop_loss", "trailing_stop") and not any(
                        w["block"] == bid and w["row"] == i for w in warnings):
                    v = r.get("value")
                    pct = f"−{num_text(v)}%" if isinstance(v, int | float) else "[빈칸]"
                    warnings.append(_problem("stop_together", "손절이 다른 조건과 같은 날 맞아야 팔려요",
                                             f"{pct}보다 내려가도 안 팔릴 수 있어요", bid, i, "sell"))

    # R-P10 연결 없음 · 매수까지 연결 안 됨
    on = {i for p in entry for i in p["blocks"]} | {i for p in sells for i in p["blocks"]}
    w = linked_weight(graph)
    if w:
        on.add(w["id"])
    for b in blocks:
        if b["id"] not in on:
            problems.append(_problem("loose", "선으로 연결해야 전략에 들어가요", stage_label(b["stage"]), b["id"],
                                     None, b["stage"]))
    target = stage_label("select") if select else stage_label("buy")
    for k, p in enumerate(entry, 1):
        if not p["complete"]:
            last = by[p["blocks"][-1]]
            problems.append(_problem("dead", "매수까지 연결 안 됨",
                                     f"진입 경로 {k} · {stage_label(last['stage'])} 뒤를 {target}에 연결해요",
                                     last["id"], None, last["stage"]))
    # 잇기 규칙에 맞지 않는 선(④를 나중에 놓아 ② · ③ → ⑤가 남은 때 등)
    for e in graph["edges"]:
        a, b2 = by.get(e["from"]), by.get(e["to"])
        if a and b2:
            r = link_reason(a["stage"], b2["stage"], select is not None)
            if r:
                problems.append(_problem("rule", r, f"{stage_label(a['stage'])} → {stage_label(b2['stage'])}",
                                         b2["id"], None, b2["stage"]))
    if too_many:
        problems.append(_problem("many", "경로가 너무 많아요", f"진입 경로 · 매도 경로는 {PATH_MAX}개까지예요"))

    blanks = sum(1 for p in problems if p["kind"] == "blank")
    return {"mode": mode, "mode_name": MODES.get(mode or "", ""), "entry": entry, "sell": sells,
            "weight": w["id"] if w else None, "problems": problems, "warnings": warnings,
            "summary": summary_line(len(problems) - blanks, blanks, len(warnings),
                                    missing=[k for k in ("signal", "sell") if any(
                                        p["kind"] in ("no_signal", "required") and p["stage"] == k
                                        for p in problems)]),
            "has_stop": has_stop(graph)}


def summary_line(problems: int, blanks: int, warnings: int, missing: list[str] | None = None) -> dict[str, str]:
    """편집기 머리 글(그림 V2-23): '문제 2 · 빈칸 1'(빈칸은 따로 셈) / '백테스트를 할 수 없어요 · 경고 1' /
    '② 신호와 ⑥ 매도를 더해요'(빠진 단계가 있을 때)."""
    if problems == 0 and blanks == 0:
        line = "저장하면 백테스트할 수 있어요" + (f" · 경고 {warnings}" if warnings else "")
        return {"title": "문제 없음 · 모두 채웠어요", "line": line}
    title = " · ".join(x for x in (f"문제 {problems}" if problems else "", f"빈칸 {blanks}" if blanks else "") if x)
    if missing:
        names = [stage_label(m) for m in missing]
        line = (f"{josa(names[0], '과/와')} {names[1]}" if len(names) == 2 else names[0]) + \
            ("를 더해요" if not _has_batchim(STAGE_NAME[missing[-1]]) else "을 더해요")
    else:
        line = "백테스트를 할 수 없어요" + (f" · 경고 {warnings}" if warnings else "")
    return {"title": title, "line": line}


def backtest_wait(loading: dict[str, int] | None) -> str | None:
    """R-P12: 데이터 받는 중이면 문제가 아니라 백테스트 단추 옆 글."""
    if not loading:
        return None
    if "dart" in loading:
        return f"DART 재무를 받는 중이에요 · {loading['dart']}% · 끝나면 백테스트할 수 있어요"
    if "bars" in loading:
        return f"시세를 받는 중이에요 · {loading['bars']}% · 끝나면 백테스트할 수 있어요"
    return None


# ── 문장으로 보기 ────────────────────────────────────────────────────────────

# 줄 하나의 글: (말 줄기, 꼴). 꼴: 'ha'(하다) · 'iss'(있다) · 'cop'(이다) · 'dah'(닿다) · 'jina'(지나다)
_ENDINGS = {
    "ha": {"and": "하고", "or": "하거나", "adn": "한", "if": "하면"},
    "iss": {"and": "있고", "or": "있거나", "adn": "있는", "if": "있으면"},
    "cop": {"and": "이고", "or": "이거나", "adn": "인", "if": "이면"},
    "dah": {"and": "닿고", "or": "닿거나", "adn": "닿은", "if": "닿으면"},
    "jina": {"and": "지나고", "or": "지나거나", "adn": "지난", "if": "지나면"},
}


def _v(v: Any, unit: str) -> str:
    return "[빈칸]" if v is None else _with_unit(v, unit)


def _phrase(graph: dict[str, Any], block: dict[str, Any], i: int) -> tuple[str, str]:
    row = block["rows"][i]
    item = CATALOG[row["item"]]
    op, v, p = row["op"], row.get("value"), row.get("params") or {}
    name = short_name(item)
    if item.id in ("stop_loss", "take_profit", "trailing_stop"):
        ex = exec_of(graph, block["id"], i)
        tag = f"({EXEC_NAME[ex]})" if ex else ""
        return f"{row_text(row)}{tag}에 ", "dah"
    if item.id == "max_hold":
        return f"{_v(v, '거래일')}이 ", "jina"
    if item.id in ("ma", "ema", "index_ma"):
        line = f"{_v(p.get('n'), '일')} {name}"
        if item.id == "index_ma":
            line = f"{'코스닥' if p.get('index') == 'KOSDAQ' else '코스피'} 지수 {_v(p.get('n'), '일')} 이동평균선"
        if op in ("cross_up", "cross_down"):
            return f"{josa(line, '을/를')} {OP_NAME[op]}", "ha"
        return f"{line} {OP_NAME[op]}에 ", "iss"
    if item.id == "high_n":
        return f"{_v(p.get('n'), '일')} 최고가를 상향 돌파", "ha"
    if item.id == "low_n":
        return f"{_v(p.get('n'), '일')} 최저가를 하향 돌파", "ha"
    if item.id == "rsi":
        lead = f"RSI({_v(p.get('period'), '일')})"
        if op in ("cross_up", "cross_down"):
            return f"{lead}가 {_v(v, '')}을 {OP_NAME[op]}", "ha"
        return f"{lead}가 {_v(v, '')} {OP_NAME[op]}", "cop"
    if op in NO_VALUE_OPS or op in ("pick", "aligned_up", "aligned_down", "consec", "within_days",
                                    "not_within_days", "fixed"):
        return row_text(row), "cop"
    unit = _unit(item, op)
    if op == "between":
        return f"{josa(name, '이/가')} {_v(v, unit)} ~ {_v(row.get('value2'), unit)} 사이", "cop"
    if op in RANK_OPS:
        return f"{name} {OP_NAME[op].replace('n', _v(v, '').strip())}", "cop"
    return f"{josa(name, '이/가')} {_v(v, unit)} {OP_NAME[op]}", "cop"


def _join(parts: list[tuple[str, str]], how: str) -> tuple[str, str]:
    """줄 글을 '하고 · 이거나'로 잇고 마지막 꼴을 돌려줘요."""
    if not parts:
        return "", "cop"
    text = ""
    for k, (stem, form) in enumerate(parts):
        if k < len(parts) - 1:
            text += stem + _ENDINGS[form][how] + " "
        else:
            text += stem
    return text, parts[-1][1]


def _block_clause(graph: dict[str, Any], block: dict[str, Any]) -> tuple[str, str]:
    parts = [_phrase(graph, block, i) for i in range(len(block["rows"]))]
    return _join(parts, "or" if block["match"] == "any" else "and")


def sentence(body: dict[str, Any]) -> str:
    """문장으로 보기(SPEC 4-1): 전략 전체를 한 문단으로. 빈칸은 [빈칸]."""
    graph = body["graph"]
    by = _index(graph)
    mode = mode_of(graph)
    uni = next((b for b in graph["blocks"] if b["stage"] == "universe"), None)
    # 유니버스
    head = ""
    if uni:
        words = []
        for r in uni["rows"]:
            if r["item"] == "manual_list":
                words.append(f"직접 고른 {len(r['value'] or [])}종목" if r["value"] else "직접 고른 [빈칸]종목")
            elif r["item"] == "market":
                words.append(" · ".join("코스피" if m == "KOSPI" else "코스닥" for m in (r["value"] or [])) or "[빈칸]")
        common = any(r["item"] == "exclude_preferred" for r in uni["rows"])
        head = " ".join(w for w in [" ".join(words), "보통주" if common else ""] if w) or "모든 종목"
        head += " 가운데 "
    # 진입 경로(② · ③): 경로마다 '하고'로, 경로끼리 '거나'로
    paths = []
    for p in entry_paths(graph)[:PATH_MAX]:
        if not p["complete"]:
            continue
        clauses = [_block_clause(graph, by[i]) for i in p["blocks"] if by[i]["stage"] in ("signal", "filter")]
        clauses = [c for c in clauses if c[0]]
        if clauses:
            paths.append(_join(clauses, "and"))
    cond = ""
    if paths:
        text, form = _join(paths, "or")
        cond = f"{text}{_ENDINGS[form]['adn']} 종목을, "
    else:
        cond = "종목을, "
    sel = next((b for b in graph["blocks"] if b["stage"] == "select"), None)
    pick = ""
    if sel and sel["rows"]:
        r = sel["rows"][0]
        by_key = (r.get("params") or {}).get("by") or "strength"
        order = "높은" if (r.get("params") or {}).get("order", "desc") == "desc" else "낮은"
        by_name = "신호 강도" if by_key == "strength" else short_name(CATALOG[by_key])
        pick = f"{josa(by_name, '이/가')} {order} 순으로 {_v(r.get('value'), '종목')}까지 "
    if mode == "event":
        buy = f"{head}{cond}{pick}다음 날 시가에 사요."
    else:
        w = linked_weight(graph)
        reb = next((r for r in (w or {}).get("rows", []) if r["item"] == "rebalance_every"), None)
        every = _v(reb.get("value") if reb else None, "거래일")
        verb = "목표 비중으로 맞춰요" if mode == "target" else "순위대로 바꿔요"
        buy = f"{head}{cond}{pick}{every}마다 다음 날 시가에 {verb}."
    # 매도
    sell_text = ""
    sps = sell_paths(graph)[:PATH_MAX]
    if sps and mode != "target":
        clauses = []
        for p in sps:
            parts = [_block_clause(graph, by[i]) for i in p["blocks"][1:]]
            parts = [c for c in parts if c[0]]
            if parts:
                clauses.append(_join(parts, "and"))
        if clauses:
            text, form = _join(clauses, "or")
            sell_text = f" {text}{_ENDINGS[form]['if']} 팔아요."
    # 비중
    wtext = ""
    w = linked_weight(graph)
    if w:
        bits = []
        if any(r["item"] == "equal" for r in w["rows"]):
            bits.append("같은 금액으로 나눠 사요")
        mx = next((r for r in w["rows"] if r["item"] == "max_per_stock"), None)
        if mx:
            bits.append(f"한 종목에 {_v(mx.get('value'), '%')}까지만 사요")
        if bits:
            wtext = " " + " · ".join(bits) + "."
    return f"{buy}{sell_text}{wtext}".strip()


def copy_body(body: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(body)
