"""전략 본문 · 검사 · 복사한 전략 글 · 예시 전략 4개.

본문(JSON): {"name": "...", "graph": {"nodes": [{"id", "piece", "params", "x", "y"}], "edges": [{"from", "to"}]}}
매매 방식은 저장하지 않고 늘 계산한다(graph.mode_of). 옛 일곱 칸 본문(slots + template)은 읽을 때 그래프로 바꾼다.

문제가 있는 버전도 저장되지만 백테스트 · 모의투자에는 쓰지 못한다.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from typing import Any

from . import APP_VERSION
from . import graph as gr
from .pieces import (  # noqa: F401  (다른 모듈이 strategy에서 가져다 쓴다)
    CIRCLED,
    HOW_OPTIONS,
    MODES,
    NAMES,
    PIECES,
    SLOT_CIRCLE,
    SLOT_KEYS,
    SLOT_LABEL,
    SLOT_NAMES,
    SLOTS,
    josa,
    num_text,
    piece_title,
    stage_of,
    stock_name,
    symbols_short,
    symbols_text,
)

DEFAULT_NAME = "새 전략"


class FormatError(ValueError):
    """kind: copy(복사한 전략 글이 아님) · graph(연결이 맞지 않음) · body(본문 형식)."""

    def __init__(self, message: str, kind: str = "body", detail: str = "") -> None:
        super().__init__(message)
        self.kind = kind
        self.detail = detail


# ── 본문 ─────────────────────────────────────────────────────────────────────


def _normalize_slots(body: dict[str, Any]) -> dict[str, Any]:
    """옛 일곱 칸 본문의 형식 검사(모르는 단계 · 조건 · 단계에 맞지 않는 조건은 FormatError)."""
    if body.get("template") not in MODES:
        raise FormatError("전략 본문이 아니에요")
    raw_slots = body.get("slots")
    if not isinstance(raw_slots, dict):
        raise FormatError("단계가 없어요")
    unknown = set(raw_slots) - set(SLOT_KEYS)
    if unknown:
        raise FormatError(f"모르는 단계가 있어요: {', '.join(sorted(unknown))}")
    slots: dict[str, list[dict[str, Any]]] = {}
    for key in SLOT_KEYS:
        items = raw_slots.get(key) or []
        if not isinstance(items, list) or len(items) > 10:
            raise FormatError(f"{SLOT_LABEL[key]} 단계 형식이 맞지 않아요")
        out = []
        for it in items:
            if not isinstance(it, dict) or it.get("piece") not in PIECES:
                pid = it.get("piece") if isinstance(it, dict) else it
                raise FormatError(f"이 앱에서 모르는 조건이 있어요: {pid}")
            if stage_of(it["piece"]) != key:
                raise FormatError(f"{PIECES[it['piece']]['name']} 조건은 {SLOT_LABEL[key]} 단계에 놓을 수 없어요")
            out.append({"piece": it["piece"], "params": it.get("params") or {}})
        slots[key] = out
    return {"template": body["template"], "slots": slots}


def as_graph(body: dict[str, Any]) -> dict[str, Any]:
    """저장된 본문(그래프 또는 옛 일곱 칸)의 그래프."""
    if isinstance(body.get("graph"), dict):
        return body["graph"]
    return gr.from_slots(body)


def normalize(body: Any) -> dict[str, Any]:
    """형식을 맞춘 본문 {"name", "graph"(, "source")}. 값 검사는 validate · graph.analyze가 한다."""
    if not isinstance(body, dict):
        raise FormatError("전략 본문이 아니에요")
    if "graph" in body:
        raw = body["graph"]
    elif "slots" in body:
        raw = gr.from_slots(_normalize_slots(body))
    else:
        raise FormatError("전략 본문이 아니에요")
    try:
        graph = gr.normalize_graph(raw)
    except gr.GraphError as exc:
        raise FormatError(str(exc), "graph", str(exc)) from None
    name = str(body.get("name") or "").strip()[:60] or DEFAULT_NAME
    result: dict[str, Any] = {"name": name, "graph": graph}
    if isinstance(body.get("source"), dict):
        src = body["source"]
        result["source"] = {k: str(src[k])[:80] for k in ("from", "id", "title", "version") if k in src}
    return result


def analyze(body: dict[str, Any]) -> dict[str, Any]:
    return gr.analyze(as_graph(body))


def validate(body: dict[str, Any]) -> list[dict[str, str]]:
    """문제 목록(graph.analyze의 problems). 옛 본문도 받는다."""
    if "graph" not in body:
        body = normalize(body)
    return analyze(body)["problems"]


def mode_of(body: dict[str, Any]) -> str | None:
    return gr.mode_of(as_graph(body))


def mode_name(mode: str | None) -> str:
    return MODES[mode]["name"] if mode in MODES else "리밸런싱 방식 빈칸"


def blank_numbers(body: dict[str, Any]) -> dict[str, Any]:
    """숫자를 모두 비운 사본(복사한 전략에는 구조와 조건만 담는다). 종목 · 리밸런싱 방식 · 위치는 남긴다."""
    out = copy.deepcopy(body)
    for n in as_graph(out)["nodes"]:
        for p in PIECES[n["piece"]]["params"]:
            if p.get("kind") not in ("symbols", "choice"):
                n["params"][p["key"]] = None
    return out


def count_blanks(body: dict[str, Any]) -> int:
    return analyze(body)["counts"].get("blank", 0)


def blanks_by_slot(body: dict[str, Any]) -> list[dict[str, Any]]:
    """빈칸이 있는 단계만: [{"key","label","count"}](단계 순서)."""
    probs = [p for p in analyze(body)["problems"] if p["kind"] == "blank"]
    out = []
    for key in SLOT_KEYS:
        c = sum(1 for p in probs if p["slot"] == key)
        if c:
            out.append({"key": key, "label": SLOT_LABEL[key], "count": c})
    return out


def summary(body: dict[str, Any]) -> dict[str, Any]:
    """목록 · 카드용 요약: 조건 수 · 진입 경로 수 · 매도 경로 수 · 매매 방식."""
    g = as_graph(body)
    a = gr.analyze(g)
    return {
        "nodes": len(g["nodes"]),
        "entry": len(a["entry"]),
        "sell": len(a["sell"]),
        "mode": a["mode"],
        "mode_name": mode_name(a["mode"]),
        "problems": len(a["problems"]),
        "blanks": a["counts"].get("blank", 0),
    }


def reason_rows(body: dict[str, Any], reasons: list[str]) -> list[dict[str, Any]]:
    """엔진이 남긴 이유 글마다 그 이유를 낸 단계 번호를 붙인다(화면 '② 신호 · …').

    display: 단계 번호 뒤에 그대로 쓰는 글. 조건 제목이면 조건 제목('② 20일 최고가 돌파'),
    엔진이 지은 이유면 단계 이름을 앞에 붙인다('④ 종목 선정 · 상위 3종목 안', '③ 필터 미충족').
    """
    by_title: dict[str, str] = {}
    for n in as_graph(body)["nodes"]:
        by_title.setdefault(piece_title(n), stage_of(n["piece"]))
    out: list[dict[str, Any]] = []
    for text in reasons:
        key = by_title.get(text)
        special = key is None
        if key is None:
            if text.startswith("상위 "):
                key = "select"
            elif text.startswith("리밸런싱"):
                key = "weight"
            elif text == "필터 미충족":
                key = "filter"
            elif text == "신호 미충족":
                key = "signal"
        name = SLOT_NAMES.get(key or "", "")
        if not special:
            display = text
        elif text.startswith(name):
            display = text
        else:
            display = f"{name} · {text}" if name else text
        out.append(
            {
                "slot": key or "",
                "label": SLOT_LABEL.get(key or "", ""),
                "circle": SLOT_CIRCLE[key] if key else "",
                "name": name,
                "text": text,
                "special": special,
                "display": display,
            }
        )
    return out


# ── 새 전략 · 예시 전략 ────────────────────────────────────────────────────────

BIG10 = ["005930", "000660", "373220", "207940", "005380", "000270", "068270", "035420", "105560", "005490"]


def _n(nid: str, piece: str, x: float, y: float, **params: Any) -> dict[str, Any]:
    full: dict[str, Any] = {}
    for p in PIECES[piece]["params"]:
        full[p["key"]] = params.get(p["key"], [] if p.get("kind") == "symbols" else None)
    return {"id": nid, "piece": piece, "params": full, "x": x, "y": y}


def _e(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"from": a, "to": b} for a, b in pairs]


def blank_body(name: str = "") -> dict[str, Any]:
    """빈 캔버스: ① 종목 직접 지정 → ④ 신호 강도 상위 n종목 → ⑤ 다음 날 시가 매수 ← ⑦ 동일 비중(숫자 · 종목 비움)."""
    return {
        "name": name.strip()[:60] or DEFAULT_NAME,
        "graph": {
            "nodes": [
                _n("u1", "manual_list", 81, 330),
                _n("k1", "top_n", 341, 330),
                _n("b1", "next_open", 601, 330),
                _n("w1", "equal", 341, 500),
            ],
            "edges": _e(("u1", "k1"), ("k1", "b1"), ("w1", "b1")),
        },
    }


EXAMPLES: list[dict[str, Any]] = [
    {
        "id": "breakout",
        "name": "대형주 돌파",
        "line": "대형주 10종목 중 20일 최고가를 돌파하고 거래대금이 100억 원 이상인 종목을 매수해요",
        "graph": {
            "nodes": [
                _n("u1", "manual_list", 25, 188, symbols=BIG10),
                _n("s1", "high_breakout", 241, 196, n=20),
                _n("f1", "min_turnover", 457, 196, n=100),
                _n("k1", "top_n", 673, 196, n=5),
                _n("b1", "next_open", 241, 520),
                _n("x1", "stop_loss", 457, 430, pct=7),
                _n("x2", "take_profit", 457, 520, pct=15),
                _n("x3", "max_hold", 457, 610, n=40),
                _n("w1", "equal", 25, 610),
            ],
            "edges": _e(("u1", "s1"), ("s1", "f1"), ("f1", "k1"), ("k1", "b1"), ("b1", "x1"), ("b1", "x2"),
                        ("b1", "x3"), ("w1", "b1")),
        },
    },
    {
        "id": "either",
        "name": "돌파 둘 중 하나",
        "line": "20일 최고가 돌파나 60일 이동평균선 상향 돌파 중 하나라도 맞으면 매수 후보가 돼요",
        "graph": {
            "nodes": [
                _n("u1", "manual_list", 25, 196, symbols=BIG10),
                _n("s1", "high_breakout", 241, 132, n=20),
                _n("s2", "ma_cross_up", 241, 256, n=60),
                _n("f1", "min_turnover", 457, 256, n=100),
                _n("k1", "top_n", 673, 196, n=5),
                _n("b1", "next_open", 241, 520),
                _n("x1", "stop_loss", 457, 470, pct=8),
                _n("x2", "max_hold", 457, 590, n=30),
                _n("w1", "equal", 25, 610),
            ],
            "edges": _e(("u1", "s1"), ("u1", "s2"), ("s1", "k1"), ("s2", "f1"), ("f1", "k1"), ("k1", "b1"),
                        ("b1", "x1"), ("b1", "x2"), ("w1", "b1")),
        },
    },
    {
        "id": "equal",
        "name": "대형주 동일 비중",
        "line": "대형주 5종목을 같은 금액으로 보유하고 20거래일마다 비중을 맞춰요",
        "graph": {
            "nodes": [
                _n("u1", "manual_list", 25, 196, symbols=BIG10[:5]),
                _n("b1", "next_open", 241, 196),
                _n("w1", "equal", 25, 330),
                _n("w2", "rebalance_every", 25, 450, n=20, how="target"),
            ],
            "edges": _e(("u1", "b1"), ("w1", "b1"), ("w2", "b1")),
        },
    },
    {
        "id": "trend",
        "name": "추세 상위 교체",
        "line": "10종목 중 60일 이동평균선 위에 있는 종목에서 신호 강도 상위 3종목을 20거래일마다 다시 골라요",
        "graph": {
            "nodes": [
                _n("u1", "manual_list", 25, 260, symbols=BIG10),
                _n("s1", "ma_cross_up", 241, 260, n=60),
                _n("k1", "top_n", 457, 260, n=3),
                _n("b1", "next_open", 241, 550),
                _n("x1", "stop_loss", 457, 550, pct=10),
                _n("w1", "equal", 25, 490),
                _n("w2", "rebalance_every", 25, 610, n=20, how="rank"),
            ],
            "edges": _e(("u1", "s1"), ("s1", "k1"), ("k1", "b1"), ("b1", "x1"), ("w1", "b1"), ("w2", "b1")),
        },
    },
]
EXAMPLE_BY_ID = {e["id"]: e for e in EXAMPLES}


def example_body(eid: str) -> dict[str, Any]:
    ex = EXAMPLE_BY_ID[eid]
    return {"name": ex["name"], "graph": copy.deepcopy(ex["graph"])}


def example_view(eid: str) -> dict[str, Any]:
    ex = EXAMPLE_BY_ID[eid]
    body = example_body(eid)
    return {"id": eid, "name": ex["name"], "line": ex["line"], "body": body, "summary": summary(body),
            "analysis": analyze(body)}


def catalog() -> dict[str, Any]:
    return {
        "slots": [
            {"key": k, "name": n, "group": g, "label": SLOT_LABEL[k], "circle": SLOT_CIRCLE[k]}
            for k, n, g in SLOTS
        ],
        "pieces": {pid: {"id": pid, **p} for pid, p in PIECES.items()},
        "modes": [{"id": mid, **m} for mid, m in MODES.items()],
        "how": HOW_OPTIONS,
        "next": {k: sorted(v, key=SLOT_KEYS.index) for k, v in gr.NEXT.items()},
        "limits": {"nodes": gr.NODE_MAX, "paths": gr.PATH_MAX},
        "names": NAMES,
        "blank": blank_body(),
        "kinds": gr.KIND_NAMES,
    }


# ── 복사한 전략 글 ────────────────────────────────────────────────────────────────────

HEADER_RE = re.compile(r"^quant-strategy/([12]) app>=(\d+)\.(\d+)$")
CHECK_RE = re.compile(r"^check:\s*([0-9a-f]{12})$")
MAX_COPY = 64 * 1024
NOT_COPY = "복사한 전략 글이 아니에요"
BAD_GRAPH = "복사한 전략 글의 연결이 맞지 않아요"


def check_of(body_text: str) -> str:
    return hashlib.sha256(body_text.encode("utf-8")).hexdigest()[:12]


def to_copy_text(body: dict[str, Any], source: dict[str, str] | None = None) -> str:
    """quant-strategy/2: 그래프(숫자 비움). 첫 줄 형식 이름, JSON, check: sha256 앞 12자리."""
    data: dict[str, Any] = {"name": body.get("name") or DEFAULT_NAME, "graph": blank_numbers({"graph": as_graph(body)})["graph"]}
    if source:
        data["source"] = source
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return f"quant-strategy/2 app>={APP_VERSION[0]}.{APP_VERSION[1]}\n{text}\ncheck: {check_of(text)}\n"


def parse_copy_text(text: str) -> tuple[dict[str, Any], list[str]]:
    """(정규화한 본문 {"name","graph","source"?}, 알림). quant-strategy/1(일곱 칸)도 받아 그래프로 바꾼다.

    형식이 아니면 FormatError(NOT_COPY …, kind='copy'). 연결이 규칙을 어기면 FormatError(BAD_GRAPH · …, kind='graph').
    끊긴 선 · 빈칸만 있는 글은 받고 문제로 보인다."""
    if not isinstance(text, str) or not text.strip():
        raise FormatError(NOT_COPY, "copy")
    if len(text) > MAX_COPY:
        raise FormatError(f"{NOT_COPY} · 너무 길어요", "copy")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").strip("\n").split("\n")
    lines = [ln.rstrip() for ln in lines]
    while lines and not lines[-1]:
        lines.pop()
    if len(lines) < 3:
        raise FormatError(NOT_COPY, "copy")
    head = HEADER_RE.match(lines[0].strip())
    check = CHECK_RE.match(lines[-1].strip())
    if not head or not check:
        raise FormatError(NOT_COPY, "copy")
    fmt = int(head.group(1))
    need = (int(head.group(2)), int(head.group(3)))
    if need > APP_VERSION:
        raise FormatError(f"이 전략은 앱 {need[0]}.{need[1]} 이상이 필요해요", "copy")
    body_text = "\n".join(lines[1:-1])
    if check_of(body_text) != check.group(1):
        raise FormatError(f"{NOT_COPY} · 검사 값이 맞지 않아요(글이 잘렸거나 바뀌었어요)", "copy")
    try:
        data = json.loads(body_text)
    except ValueError:
        raise FormatError(NOT_COPY, "copy") from None
    if not isinstance(data, dict):
        raise FormatError(NOT_COPY, "copy")
    if fmt == 1:
        if "slots" not in data:
            raise FormatError(NOT_COPY, "copy")
        raw_graph = gr.from_slots(_normalize_slots(data))
    else:
        raw_graph = data.get("graph")
        if not isinstance(raw_graph, dict):
            raise FormatError(NOT_COPY, "copy")
    try:
        graph = gr.normalize_graph(raw_graph, strict=True)
    except gr.GraphError as exc:
        if str(exc).startswith("이 앱에서 모르는 조건"):
            raise FormatError(str(exc), "copy") from None
        raise FormatError(f"{BAD_GRAPH} · {exc}", "graph", str(exc)) from None
    body: dict[str, Any] = {"name": str(data.get("name") or "").strip()[:60] or DEFAULT_NAME, "graph": graph}
    if isinstance(data.get("source"), dict):
        src = data["source"]
        body["source"] = {k: str(src[k])[:80] for k in ("from", "id", "title", "version") if k in src}
    notes: list[str] = []
    stripped = blank_numbers(body)
    if stripped != body:
        notes.append("복사한 전략에는 구조만 담겨요 · 숫자는 직접 정해요")
    return stripped, notes
