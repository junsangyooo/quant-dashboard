"""전략 그래프: 조건(노드)을 선으로 이은 방향 그래프(순환 없음). 규칙은 product/service/ENGINE-RULES.md(R-G · R-P · R-M).

본문: {"name", "graph": {"nodes": [{"id", "piece", "params", "x", "y"}], "edges": [{"from", "to"}]}}

- 진입 경로 = ① 유니버스에서 ⑤ 매수까지(② 신호 · ③ 필터 · ④ 종목 선정을 지난다). 경로 안은 모두(AND),
  경로끼리는 하나라도(OR).
- 매도 경로 = ⑤ 매수에서 나가 끝까지(⑥ 매도만). 매도 경로 하나라도 그 위 조건이 모두 맞으면 매도.
- ⑦ 비중은 ⑤ 매수로 들어가는 선으로만. 이어진 비중은 모두 함께 적용.
- 매매 방식은 놓은 조건으로 정해진다: ⑤에 이어진 '리밸런싱 주기'가 없으면 조건 충족 시 매매, 있으면 그
  조건의 '리밸런싱 방식'(목표 비중 · 순위 교체).

화면(web/src/screens/Editor/graph.ts)이 같은 검사를 미리 돌린다. 둘의 결과가 같은지는 시험으로 고정했다
(tests/test_graph_mirror.py가 만든 web/tests/fixtures/graph_cases.json을 web/tests/graphMirror.test.ts가 읽는다).
"""

from __future__ import annotations

import math
import re
from typing import Any

from .pieces import (
    MODES,
    ONCE_PIECES,
    ONCE_STAGES,
    PIECES,
    SLOT_CIRCLE,
    SLOT_KEYS,
    SLOT_LABEL,
    josa,
    num_text,
    piece_title,
    stage_of,
)

NODE_MAX = 40
PATH_MAX = 20
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")
SYMBOL_RE = re.compile(r"^[0-9]{6}\Z")

# 뒤에 올 수 있는 단계(ENGINE-RULES R-G12). ④가 있으면 ② · ③ → ⑤는 막는다(link_reason).
NEXT: dict[str, set[str]] = {
    "universe": {"signal", "filter", "select", "buy"},
    "signal": {"signal", "filter", "select", "buy"},
    "filter": {"signal", "filter", "select", "buy"},
    "select": {"buy"},
    "buy": {"sell"},
    "sell": {"sell"},
    "weight": {"buy"},
}
ENTRY = {"universe", "signal", "filter", "select"}

KIND_NAMES: dict[str, str] = {
    "blank": "빈칸",
    "range": "범위 밖",
    "required": "필요한 조건",
    "unusable": "못 쓰는 조건",
    "loose": "연결 없음",
    "dead": "매수까지 연결 안 됨",
    "rule": "연결 규칙",
    "many": "경로가 너무 많아요",
}

R_UNIVERSE_IN = "유니버스 앞에는 조건을 연결할 수 없어요"
R_SELL = "매도 조건은 매수 뒤에 연결해요"
R_ENTRY = "신호 · 필터는 매수 앞에 연결해요"
R_SELECT = "종목 선정은 매수 바로 앞에 하나만 놓아요"
R_WEIGHT = "비중 조건은 매수에 연결해요"
R_BUY_ONCE = "매수 조건은 하나만 놓을 수 있어요"
R_CYCLE = "선이 이미 지나온 조건으로 돌아가면 안 돼요"
R_DUP = "이미 연결돼 있어요"
R_MANY = f"경로가 너무 많아요 · 진입 경로는 최대 {PATH_MAX}개예요"
R_MANY_SELL = f"경로가 너무 많아요 · 매도 경로는 최대 {PATH_MAX}개예요"


class GraphError(ValueError):
    """그래프 형식이 맞지 않음(편집기는 만들지 않는 모양: 조건 수 · 하나만 놓는 조건 · 순환 · 겹친 선 · 경로 수)."""


# ── 조건 하나 ────────────────────────────────────────────────────────────────


def once_reason(piece: str) -> str:
    stage = stage_of(piece)
    if stage == "universe":
        return "유니버스는 하나만 놓을 수 있어요"
    if stage == "buy":
        return R_BUY_ONCE
    if stage == "select":
        return R_SELECT
    return f"{josa(PIECES[piece]['name'], '은/는')} 하나만 놓을 수 있어요"


def add_reason(graph: dict[str, Any], piece: str) -> str | None:
    """이 조건을 하나 더 놓을 수 없는 이유(없으면 None)."""
    nodes = graph["nodes"]
    if len(nodes) >= NODE_MAX:
        return f"조건은 {NODE_MAX}개까지 놓을 수 있어요"
    stage = stage_of(piece)
    if stage in ONCE_STAGES and any(stage_of(n["piece"]) == stage for n in nodes):
        return once_reason(piece)
    if piece in ONCE_PIECES and any(n["piece"] == piece for n in nodes):
        return once_reason(piece)
    return None


# ── 선 하나 ──────────────────────────────────────────────────────────────────


def link_reason(src_stage: str, dst_stage: str, has_select: bool) -> str | None:
    """단계 순서로 이 선을 이을 수 없는 이유(ENGINE-RULES R-G12의 이유 글)."""
    if dst_stage == "universe":
        return R_UNIVERSE_IN
    if src_stage == "weight" or dst_stage == "weight":
        return None if (src_stage == "weight" and dst_stage == "buy") else R_WEIGHT
    if dst_stage == "sell":
        return None if src_stage in ("buy", "sell") else R_SELL
    if src_stage == "sell":
        return R_SELL
    if src_stage == "buy":
        return R_BUY_ONCE if dst_stage == "buy" else R_ENTRY
    if src_stage == "select":
        return None if dst_stage == "buy" else R_SELECT
    # 남은 것: ① · ② · ③ → ② · ③ · ④ · ⑤
    if dst_stage == "buy" and has_select:
        return R_SELECT
    return None


def _index(graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in graph["nodes"]}


def _key(n: dict[str, Any], idx: int) -> tuple[float, float, int]:
    y = n.get("y")
    x = n.get("x")
    return (float(y) if y is not None else 0.0, float(x) if x is not None else 0.0, idx)


def outgoing(graph: dict[str, Any]) -> dict[str, list[str]]:
    """조건마다 나가는 선의 끝(위 → 아래, 왼쪽 → 오른쪽, 그다음 선을 이은 순서)."""
    by = _index(graph)
    out: dict[str, list[tuple[tuple[float, float, int], str]]] = {nid: [] for nid in by}
    for i, e in enumerate(graph["edges"]):
        if e["from"] in by and e["to"] in by:
            out[e["from"]].append((_key(by[e["to"]], i), e["to"]))
    return {k: [d for _, d in sorted(v)] for k, v in out.items()}


def _reaches(out: dict[str, list[str]], a: str, b: str) -> bool:
    seen = {a}
    stack = [a]
    while stack:
        cur = stack.pop()
        if cur == b:
            return True
        for nxt in out.get(cur, []):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


def edge_reason(graph: dict[str, Any], src: str, dst: str) -> str | None:
    """src → dst 선을 이을 수 없는 이유(없으면 None). 화면이 잇는 중에 같은 규칙으로 표시한다."""
    by = _index(graph)
    if src not in by or dst not in by:
        return "없는 조건이에요"
    if src == dst:
        return R_CYCLE
    has_select = any(stage_of(n["piece"]) == "select" for n in graph["nodes"])
    r = link_reason(stage_of(by[src]["piece"]), stage_of(by[dst]["piece"]), has_select)
    if r:
        return r
    if any(e["from"] == src and e["to"] == dst for e in graph["edges"]):
        return R_DUP
    out = outgoing(graph)
    if _reaches(out, dst, src):
        return R_CYCLE
    g2 = {"nodes": graph["nodes"], "edges": [*graph["edges"], {"from": src, "to": dst}]}
    if len(entry_paths(g2)) > PATH_MAX:
        return R_MANY
    if len(sell_paths(g2)) > PATH_MAX:
        return R_MANY_SELL
    return None


# ── 경로 ─────────────────────────────────────────────────────────────────────


def entry_paths(graph: dict[str, Any], limit: int = PATH_MAX + 1) -> list[dict[str, Any]]:
    """① 유니버스에서 나가는 경로들: 매수에 닿으면 complete, 닿기 전에 끊기면 complete=False."""
    by = _index(graph)
    uni = [n["id"] for n in graph["nodes"] if stage_of(n["piece"]) == "universe"]
    if not uni:
        return []
    out = outgoing(graph)
    paths: list[dict[str, Any]] = []

    def walk(path: list[str]) -> None:
        if len(paths) >= limit:
            return
        last = path[-1]
        if stage_of(by[last]["piece"]) == "buy":
            paths.append({"nodes": list(path), "complete": True})
            return
        nexts = [
            d for d in out[last]
            if d not in path and stage_of(by[d]["piece"]) in ("signal", "filter", "select", "buy")
        ]
        if not nexts:
            paths.append({"nodes": list(path), "complete": False})
            return
        for d in nexts:
            walk([*path, d])
            if len(paths) >= limit:
                return

    walk([uni[0]])
    return paths


def sell_paths(graph: dict[str, Any], limit: int = PATH_MAX + 1) -> list[dict[str, Any]]:
    """⑤ 매수에서 나가 ⑥ 매도만 지나 끝(나가는 선이 없는 매도)까지."""
    by = _index(graph)
    buys = [n["id"] for n in graph["nodes"] if stage_of(n["piece"]) == "buy"]
    if not buys:
        return []
    out = outgoing(graph)
    paths: list[dict[str, Any]] = []

    def walk(path: list[str]) -> None:
        if len(paths) >= limit:
            return
        nexts = [d for d in out[path[-1]] if d not in path and stage_of(by[d]["piece"]) == "sell"]
        if not nexts:
            if len(path) > 1:
                paths.append({"nodes": list(path)})
            return
        for d in nexts:
            walk([*path, d])
            if len(paths) >= limit:
                return

    walk([buys[0]])
    return paths


def linked_weights(graph: dict[str, Any]) -> list[str]:
    by = _index(graph)
    buys = {n["id"] for n in graph["nodes"] if stage_of(n["piece"]) == "buy"}
    out: list[str] = []
    for n in graph["nodes"]:
        if stage_of(n["piece"]) != "weight":
            continue
        if any(e["from"] == n["id"] and e["to"] in buys for e in graph["edges"]) and n["id"] in by:
            out.append(n["id"])
    return out


def mode_of(graph: dict[str, Any]) -> str | None:
    """매매 방식. ⑤에 이어진 리밸런싱 주기가 없으면 event. 있으면 그 칸의 방식(빈칸이면 None)."""
    by = _index(graph)
    for wid in linked_weights(graph):
        n = by[wid]
        if n["piece"] == "rebalance_every":
            how = (n.get("params") or {}).get("how")
            return how if how in ("target", "rank") else None
    return "event"


# ── 검사 ─────────────────────────────────────────────────────────────────────


def _problem(kind: str, node: str, field: str, slot: str, title: str, short: str,
             detail: str | None = None, hint: str = "") -> dict[str, str]:
    return {
        "kind": kind,
        "node": node,
        "field": field,
        "slot": slot,
        "title": title,
        "short": short,
        "detail": detail if detail is not None else (f"{SLOT_LABEL[slot]} · {short}" if slot else short),
        "hint": hint,
    }


def field_problem(piece: str, p: dict[str, Any], value: Any) -> tuple[str, str] | None:
    """숫자 칸 하나의 문제: (kind, 짧은 글). 없으면 None. 화면의 입력 칸 아래 글과 같다."""
    if p.get("kind") == "choice":
        if value not in p["options"]:
            return ("blank", f"{josa(p['label'], '을/를')} 골라 주세요")
        return None
    if p.get("kind") == "symbols":
        syms = value or []
        if not syms:
            return ("blank", f"{josa(p['label'], '을/를')} 입력해 주세요")
        bad = [s for s in syms if not SYMBOL_RE.match(str(s))]
        if bad:
            return ("range", f"한국 종목 6자리 코드가 아니에요: {', '.join(str(b) for b in bad[:5])}")
        if len(syms) > p["max"]:
            return ("range", f"종목은 {p['max']}개까지 입력할 수 있어요")
        return None
    rng = f"{num_text(p['min'])}~{num_text(p['max'])}{p['unit']}"
    if value is None:
        return ("blank", f"{josa(p['label'], '을/를')} 입력해 주세요")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return ("range", f"{p['label']}에 숫자를 입력해 주세요 ({rng})")
    if not (p["min"] <= value <= p["max"]):
        return ("range", f"{josa(p['label'], '은/는')} {rng} 사이로 입력해 주세요")
    if p["integer"] and float(value) != int(value):
        return ("range", f"{josa(p['label'], '은/는')} 정수로 입력해 주세요")
    return None


def label_of(n: dict[str, Any]) -> str:
    """'② 20일 최고가 돌파'."""
    return f"{SLOT_CIRCLE[stage_of(n['piece'])]} {piece_title(n)}"


def analyze(graph: dict[str, Any]) -> dict[str, Any]:
    """경로 · 매매 방식 · 문제 목록. 저장 · 백테스트 · 모의투자 · 화면이 모두 이 결과를 쓴다."""
    nodes = graph["nodes"]
    by = _index(graph)
    stages = {n["id"]: stage_of(n["piece"]) for n in nodes}
    entry = entry_paths(graph)
    sells = sell_paths(graph)
    too_many = len(entry) > PATH_MAX or len(sells) > PATH_MAX
    entry = entry[:PATH_MAX]
    sells = sells[:PATH_MAX]
    weights = linked_weights(graph)
    mode = mode_of(graph)
    problems: list[dict[str, str]] = []

    # 1. 숫자 칸(조건 순서대로)
    for n in nodes:
        spec = PIECES[n["piece"]]
        slot = stages[n["id"]]
        for p in spec["params"]:
            found = field_problem(n["piece"], p, (n.get("params") or {}).get(p["key"]))
            if found is None:
                continue
            kind, short = found
            title = f"빈칸 · {spec['name']}" if kind == "blank" else f"범위 밖 · {piece_title(n)}"
            problems.append(_problem(kind, n["id"], p["key"], slot, title, short))

    # 2. 꼭 있어야 하는 조건
    def has_stage(s: str) -> bool:
        return any(v == s for v in stages.values())

    def required(slot: str, short: str, hint: str = "") -> None:
        problems.append(_problem("required", "", "", slot, f"필요한 조건 · {SLOT_LABEL[slot]}", short, short, hint))

    if not has_stage("universe"):
        required("universe", "종목 직접 지정 조건이 있어야 해요")
    if not has_stage("buy"):
        required("buy", "다음 날 시가 매수 조건이 있어야 해요")
    if not any(n["piece"] == "equal" for n in nodes):
        required("weight", "동일 비중 조건이 있어야 해요")
    if mode in ("event", "rank"):
        mname = MODES[mode]["name"]
        if not has_stage("select"):
            required("select", f"{mname}에는 신호 강도 상위 n종목이 있어야 해요",
                     "목록에서 ④ 종목 선정을 끌어 와 매수 바로 앞 선 위에 놓아 주세요")
        for k, path in enumerate(entry, 1):
            if not path["complete"]:
                continue
            if any(stages[i] == "signal" for i in path["nodes"]):
                continue
            nxt = path["nodes"][1] if len(path["nodes"]) > 1 else path["nodes"][0]
            required(
                "signal",
                f"진입 경로 {k}에 신호가 없어요 · 신호 없이 연결하면 매일 모든 종목이 매수 후보가 돼요",
                f"목록에서 신호 조건을 끌어 와 ①과 {SLOT_CIRCLE[stages[nxt]]} 사이 선 위에 놓아 주세요",
            )
    if mode == "event" and not sells:
        required("sell", f"{MODES['event']['name']}에는 매도 경로가 하나 이상 있어야 해요",
                 "⑥ 매도 조건을 끌어 와 ⑤ 매수 뒤에 연결해 주세요")

    # 3. 지금 매매 방식에서 못 쓰는 조건(경로 위에 있는 것)
    on_sell = {i for p in sells for i in p["nodes"][1:]}
    if mode is not None:
        for n in nodes:
            if n["id"] in on_sell and mode not in PIECES[n["piece"]]["modes"]:
                problems.append(_problem(
                    "unusable", n["id"], "", stages[n["id"]], f"못 쓰는 조건 · {piece_title(n)}",
                    f"{MODES[mode]['name']}에서는 {SLOT_LABEL[stages[n['id']]]} 조건을 쓸 수 없어요 · "
                    "순위 교체를 고르거나 이 조건을 삭제해 주세요",
                ))

    # 4. 연결 없음: 어느 경로에도 없는 조건
    on = {i for p in entry for i in p["nodes"]} | {i for p in sells for i in p["nodes"]} | set(weights)
    for n in nodes:
        if n["id"] not in on:
            problems.append(_problem("loose", n["id"], "", stages[n["id"]], f"연결 없음 · {piece_title(n)}",
                                     "선으로 연결해야 전략에 들어가요"))

    # 5. 매수까지 연결 안 됨
    sel = next((n for n in nodes if stages[n["id"]] == "select"), None)
    target = label_of(sel) if sel is not None else "⑤ 매수"
    for k, path in enumerate(entry, 1):
        if path["complete"]:
            continue
        last = by[path["nodes"][-1]]
        short = f"진입 경로 {k} · {label_of(last)} 뒤를 {target}에 연결해 주세요"
        problems.append(_problem("dead", last["id"], "", "", "매수까지 연결 안 됨", short, short))

    # 6. 규칙에 맞지 않는 선(④를 나중에 놓아 ② · ③ → ⑤가 남은 때 등)
    has_select = sel is not None
    for e in graph["edges"]:
        a, b = by.get(e["from"]), by.get(e["to"])
        if a is None or b is None:
            continue
        r = link_reason(stages[a["id"]], stages[b["id"]], has_select)
        if r:
            problems.append(_problem("rule", b["id"], "", stages[b["id"]],
                                     f"연결 규칙 · {label_of(a)} → {label_of(b)}", r, r))

    # 7. 경로 수
    if too_many:
        short = f"진입 경로 · 매도 경로는 {PATH_MAX}개까지예요"
        problems.append(_problem("many", "", "", "", KIND_NAMES["many"], short, short))

    counts: dict[str, int] = {}
    for kind in KIND_NAMES:
        c = sum(1 for p in problems if p["kind"] == kind)
        if c:
            counts[kind] = c
    return {
        "mode": mode,
        "entry": entry,
        "sell": sells,
        "weights": weights,
        "problems": problems,
        "counts": counts,
        "too_many": too_many,
    }


# ── 형식 ─────────────────────────────────────────────────────────────────────


def _clean_symbols(value: Any) -> list[str]:
    if isinstance(value, str):
        value = re.split(r"[\s,]+", value)
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for v in value:
        s = str(v).strip().upper()
        for suf in (".KS", ".KQ"):
            if s.endswith(suf):
                s = s[: -len(suf)]
        if s and s not in out:
            out.append(s)
    return out


def clean_params(piece: str, params_in: Any) -> dict[str, Any]:
    if not isinstance(params_in, dict):
        raise GraphError("조건 숫자 형식이 맞지 않아요")
    params: dict[str, Any] = {}
    for p in PIECES[piece]["params"]:
        v = params_in.get(p["key"])
        if p.get("kind") == "symbols":
            params[p["key"]] = _clean_symbols(v)
        elif p.get("kind") == "choice":
            params[p["key"]] = v if v in p["options"] else None
        elif v is None or v == "":
            params[p["key"]] = None
        elif isinstance(v, bool):
            params[p["key"]] = v
        elif isinstance(v, (int, float)):
            params[p["key"]] = v if math.isfinite(float(v)) else None
        else:
            try:
                f = float(str(v).replace(",", ""))
                params[p["key"]] = f if math.isfinite(f) else str(v)[:40]
            except ValueError:
                params[p["key"]] = str(v)[:40]
    return params


def _coord(v: Any) -> float | None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
        return None
    return round(max(-100000.0, min(100000.0, float(v))), 1)


def normalize_graph(raw: Any, strict: bool = False) -> dict[str, Any]:
    """형식을 맞춘다. 편집기가 만들지 않는 모양은 GraphError(조건 수 · 하나만 놓는 조건 · 겹친 선 · 순환 · 경로 수).
    strict(붙여 넣은 글): 단계 순서를 어긴 선도 GraphError."""
    if not isinstance(raw, dict):
        raise GraphError("전략 그래프가 아니에요")
    rnodes = raw.get("nodes")
    redges = raw.get("edges") or []
    if not isinstance(rnodes, list) or not isinstance(redges, list):
        raise GraphError("전략 그래프가 아니에요")
    if len(rnodes) > NODE_MAX:
        raise GraphError(f"조건은 {NODE_MAX}개까지예요 · 지금 {len(rnodes)}개")
    nodes: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rn in rnodes:
        if not isinstance(rn, dict) or rn.get("piece") not in PIECES:
            pid = rn.get("piece") if isinstance(rn, dict) else rn
            raise GraphError(f"이 앱에서 모르는 조건이 있어요: {str(pid)[:40]}")
        nid = str(rn.get("id") or "")
        if not ID_RE.match(nid) or nid in seen:
            raise GraphError("조건 번호가 맞지 않아요")
        seen.add(nid)
        piece = rn["piece"]
        if (stage_of(piece) in ONCE_STAGES and any(stage_of(n["piece"]) == stage_of(piece) for n in nodes)) or (
            piece in ONCE_PIECES and any(n["piece"] == piece for n in nodes)
        ):
            raise GraphError(once_reason(piece))
        nodes.append({"id": nid, "piece": piece, "params": clean_params(piece, rn.get("params") or {}),
                      "x": _coord(rn.get("x")), "y": _coord(rn.get("y"))})
    edges: list[dict[str, str]] = []
    if len(redges) > NODE_MAX * NODE_MAX:
        raise GraphError("선이 너무 많아요")
    for re_ in redges:
        if not isinstance(re_, dict):
            raise GraphError("선 형식이 맞지 않아요")
        a, b = str(re_.get("from") or ""), str(re_.get("to") or "")
        if a not in seen or b not in seen:
            raise GraphError("없는 조건을 가리키는 선이 있어요")
        if a == b:
            raise GraphError(R_CYCLE)
        if any(e["from"] == a and e["to"] == b for e in edges):
            raise GraphError("같은 두 조건 사이 선은 하나예요")
        edges.append({"from": a, "to": b})
    graph = {"nodes": nodes, "edges": edges}
    if strict:
        bad = strict_error(graph)
        if bad:
            raise GraphError(bad)
    out = outgoing(graph)
    for e in edges:
        if _reaches(out, e["to"], e["from"]):
            raise GraphError(R_CYCLE)
    if len(entry_paths(graph)) > PATH_MAX:
        raise GraphError(R_MANY)
    if len(sell_paths(graph)) > PATH_MAX:
        raise GraphError(R_MANY_SELL)
    return graph


def strict_error(graph: dict[str, Any]) -> str | None:
    """붙여 넣은 글만 더 엄격하게: 단계 순서(ENGINE-RULES R-G12)를 어긴 선이 있으면 그 글."""
    by = _index(graph)
    has_select = any(stage_of(n["piece"]) == "select" for n in graph["nodes"])
    for e in graph["edges"]:
        a, b = by[e["from"]], by[e["to"]]
        r = link_reason(stage_of(a["piece"]), stage_of(b["piece"]), has_select)
        if r:
            b_text = SLOT_LABEL[stage_of(b["piece"])]
            if stage_of(b["piece"]) not in ("buy",):
                b_text = label_of(b)
            return f"{josa(label_of(a), '이/가')} {b_text} 앞에 연결돼 있어요 · {r}"
    return None


# ── 옛 일곱 칸 본문 ───────────────────────────────────────────────────────────


def from_slots(body: dict[str, Any]) -> dict[str, Any]:
    """옛 본문(slots + template)을 그래프로: ① → ② 모두 → ③ 모두 → ④ → ⑤ 한 줄,
    매도는 ⑤에서 갈래(하나라도), 비중은 ⑤로. 템플릿 target · rank는 리밸런싱 방식 값으로."""
    slots = body.get("slots") or {}
    template = body.get("template")
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []

    def add(item: dict[str, Any]) -> str:
        nid = f"n{len(nodes) + 1}"
        params = dict(item.get("params") or {})
        if item.get("piece") == "rebalance_every":
            params["how"] = template if template in ("target", "rank") else None
        nodes.append({"id": nid, "piece": item.get("piece"), "params": params, "x": None, "y": None})
        return nid

    chain: list[str] = []
    for key in ("universe", "signal", "filter", "select"):
        for it in slots.get(key) or []:
            chain.append(add(it))
    buy = [add(it) for it in slots.get("buy") or []]
    chain.extend(buy[:1])
    for a, b in zip(chain, chain[1:]):
        edges.append({"from": a, "to": b})
    for it in slots.get("sell") or []:
        sid = add(it)
        if buy:
            edges.append({"from": buy[0], "to": sid})
    for it in slots.get("weight") or []:
        wid = add(it)
        if buy:
            edges.append({"from": wid, "to": buy[0]})
    return {"nodes": nodes, "edges": edges}


# ── 엔진에 넘길 모양 ──────────────────────────────────────────────────────────


def compile_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """엔진이 쓰는 모양: 진입 경로마다 신호 · 필터 목록, 매도 경로마다 매도 목록, 숫자 몇 개."""
    by = _index(graph)

    def items(ids: list[str], stage: str) -> list[dict[str, Any]]:
        return [by[i] for i in ids if stage_of(by[i]["piece"]) == stage]

    def param(piece: str, key: str) -> Any:
        for n in graph["nodes"]:
            if n["piece"] == piece:
                return (n.get("params") or {}).get(key)
        return None

    universe: list[str] = []
    for n in graph["nodes"]:
        if stage_of(n["piece"]) == "universe":
            for s in (n.get("params") or {}).get("symbols") or []:
                if s not in universe:
                    universe.append(s)
    entry = [
        {"signals": items(p["nodes"], "signal"), "filters": items(p["nodes"], "filter")}
        for p in entry_paths(graph)
        if p["complete"]
    ]
    sells = [items(p["nodes"], "sell") for p in sell_paths(graph)]
    return {
        "mode": mode_of(graph) or "event",
        "universe": universe,
        "entry": entry,
        "sells": sells,
        "signals": [n for n in graph["nodes"] if stage_of(n["piece"]) == "signal"],
        "sell_items": [n for n in graph["nodes"] if stage_of(n["piece"]) == "sell"],
        "top_n": param("top_n", "n"),
        "max_pct": param("max_per_stock", "pct"),
        "every": param("rebalance_every", "n"),
    }


STAGE_ORDER = {k: i for i, k in enumerate(SLOT_KEYS)}
