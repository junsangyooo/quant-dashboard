"""v2 전략 API(블록 본문 · TASKS T-30 · T-31 · T-32 · P1-09에서 `app/api_v2.py` → 이 자리). 화면 편집기 · 목록 · 붙여 넣기 ·
백테스트가 써요.

- 본문은 v3 블록(`domain/blocks.py`). 저장된 v1 본문(일곱 칸 · 그래프 노드)은 읽을 때 v3로 바꿔요(R-C3 · R-C8).
- 문제 목록 · 경고 · 실행 방식 칩 · 문장으로 보기는 서버가 셈해서 돌려줘요(화면과 같은 규칙 하나).
- 저장은 문제가 있어도 돼요(R-P 머리). 버전 꼴은 `format = blocks`. 저장 · 지우기 · 백테스트 기록은 쓰기 일
  `services/strategies.py`예요.
- 백테스트 기본 기간의 '오늘'(`today`)은 1단계 예외(지금 시계 그대로 · ARCHITECTURE 6절)이고 기준선 시계 고정 자리
  (`app/api_v2.py` · Q-N24)라 조립이 그 함수를 넘겨요.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import Field

from ..domain import blocks as bk
from ..domain import catalog as cat
from ..domain import copytext as ct
from ..domain.markets.kr import KST
from ..services import strategies as strategy_jobs
from ..store import strategies as strategy_store
from ..store.db import DB
from .errors import ApiError
from .http import ERRORS, OkOut
from .models import ApiModel, Bool, Int, Num, Str, opt

# ── 응답 모델(지금 모양 그대로 · 블록 본문은 편집기가 보내는 꼴과 같음) ──────────────────────────────

StageId = Literal["universe", "signal", "filter", "select", "buy", "sell", "weight"]
ExecId = Literal["intraday", "broker", "close"]


class Row(ApiModel):
    item: Str
    op: Str
    params: dict[Str, Num | Str | None]
    value: Num | Str | list[Str] | None
    value2: Num | None
    exec: ExecId | None


class Block(ApiModel):
    id: Str
    stage: StageId
    match: Literal["all", "any"]
    rows: list[Row]
    x: Num
    y: Num


class Edge(ApiModel):
    from_: Str = Field(alias="from")
    to: Str


class Graph(ApiModel):
    blocks: list[Block]
    edges: list[Edge]


class Body(ApiModel):
    name: Str
    graph: Graph
    converted: Str = opt()  # 옛 v1 본문을 바꿔 읽었으면 "v1"
    source: dict[Str, Str] = opt()  # 붙여 넣은 복사 글의 출처(가져오기 확인에서만)


class StrategyPath(ApiModel):
    blocks: list[Str]
    complete: Bool = opt()


class Problem(ApiModel):
    kind: Str
    title: Str
    detail: Str
    block: Str
    row: Int | None
    stage: StageId | Literal[""]


class SummaryLine(ApiModel):
    title: Str
    line: Str


class Analysis(ApiModel):
    mode: Literal["event", "target", "rank"] | None
    mode_name: Str
    entry: list[StrategyPath]
    sell: list[StrategyPath]
    weight: Str | None
    problems: list[Problem]
    warnings: list[Problem]
    summary: SummaryLine
    has_stop: Bool


class ExecChip(ApiModel):
    exec: ExecId
    name: Str
    reason: Str


class StartDate(ApiModel):
    date: Str
    reason: Str


class Analyzed(ApiModel):
    """편집 중인 본문의 셈(`body` 먼저 · 그 뒤 `view` 키 차례 그대로)."""

    body: Body
    analysis: Analysis
    sentence: Str
    chips: dict[Str, list[ExecChip | None]]
    row_texts: dict[Str, list[Str]]
    block_lines: dict[Str, list[Str]]
    start: StartDate | None


class VersionView(ApiModel):
    id: Int
    no: Int
    problems: Int
    created_at: Str
    saved_day: Str
    saved_hm: Str
    backtested: Bool
    backtested_hm: Str


class Running(ApiModel):
    kind: Literal["paper"]
    version_no: Int
    run_id: Int


class StrategyCard(ApiModel):
    id: Int
    name: Str
    mode_name: Str
    problems: Int
    version: VersionView
    running: Running | None


class StrategyList(ApiModel):
    strategies: list[StrategyCard]


class StrategyDetail(ApiModel):
    id: Int
    name: Str
    version: VersionView
    versions: list[VersionView]
    body: Body
    running: Running | None
    deletable: Bool
    analysis: Analysis
    sentence: Str
    chips: dict[Str, list[ExecChip | None]]
    row_texts: dict[Str, list[Str]]
    block_lines: dict[Str, list[Str]]
    start: StartDate | None


class SavedVersion(ApiModel):
    version_id: Int
    no: Int
    problems: Int


class Created(ApiModel):
    id: Int
    name: Str
    version_id: Int
    no: Int
    problems: Int


class ImportCard(ApiModel):
    id: Str
    stage: StageId
    match: Literal["all", "any"]
    lines: list[Str]


class ImportPreview(ApiModel):
    body: Body
    notes: list[Str]
    name: Str
    stages: Int
    entry: Int
    sell: Int
    rows: Int
    blanks: Int
    blank_kinds: list[Str]
    cards: list[ImportCard]
    others: list[StageId]


class ExportFile(ApiModel):
    name: Str
    text: Str


class CopyText(ApiModel):
    text: Str


class CatalogParam(ApiModel):
    key: Str
    label: Str
    choices: list[Str]
    min: Num | None
    max: Num | None
    integer: Bool | None
    when_op: list[Str]


class ValueRange(ApiModel):
    min: Num
    max: Num
    unit: Str
    integer: Bool


class RankRange(ApiModel):
    min: Num
    max: Num


class CatalogItem(ApiModel):
    id: Str
    name: Str
    category: Str
    ops: list[Str]
    op_names: list[Str]
    stages: list[StageId]
    sortable: Bool
    lock: Str | None
    backtest: Literal["yes", "partial", "no"]
    chips: list[Str]
    execs: list[ExecId]
    unit: Str
    source: Str
    start: Str | None
    start_reason: Str | None
    params: list[CatalogParam]
    value: ValueRange | None
    rank: RankRange | None
    choices: list[Str]
    help: Str
    source_display: Str
    backtest_display: Str
    short: Str


class CatalogStage(ApiModel):
    id: StageId
    circle: Str
    name: Str
    once: Bool
    toggle: Bool


class Catalog(ApiModel):
    items: list[CatalogItem]
    stages: list[CatalogStage]
    ops: dict[Str, Str]
    execs: dict[ExecId, Str]
    categories: list[Str]
    dart: Bool


class BacktestRange(ApiModel):
    start: Str
    end: Str
    first: Str
    reason: Str


class BacktestInput(ApiModel):
    version: VersionView
    strategy_id: Int
    name: Str
    range: BacktestRange
    chips: list[Str]
    judge_line: Str


class BacktestTrade(ApiModel):
    d: Str
    sym: Str
    side: Literal["buy", "sell"]
    qty: Int
    price: Num
    amount: Num
    cost: Num
    pnl: Num | None
    reason: list[Str]
    judged: Str
    kind: Str = opt()
    name: Str


class OpenPosition(ApiModel):
    sym: Str
    qty: Int
    avg: Num


class LiveCounts(ApiModel):
    no_buy: Int
    no_sell: Int


class BacktestResult(ApiModel):
    start: Str
    end: Str
    final: Num
    total: Num | None
    cagr: Num | None
    mdd: Num | None
    trades: list[BacktestTrade]
    buys: Int
    sells: Int
    win_rate: Num | None
    costs: Num
    curve: list[tuple[Str, Num]]
    bench_curve: list[tuple[Str, Num]]
    bench_total: Num | None
    bench_cagr: Num | None
    bench_mdd: Num | None
    open: list[OpenPosition]
    skipped: list[dict[str, Any]]  # 체결 못 한 계획(계획 값 + 날짜 · 까닭)
    notes: dict[Str, list[Str]]  # 종목 → 값 없음 기록(R-J1)
    live_note: Str
    live_counts: LiveCounts
    survivor_line: Str
    wide_universe: Bool
    recent: list[BacktestTrade]
    trade_count: Int
    chips: list[Str]
    judge_line: Str
    wide_title: Str
    ran_at: Str
    ran_day: Str
    ran_hm: Str


def catalog_view() -> dict[str, Any]:
    items = []
    for d in cat.describe():
        it = cat.item(d["id"])
        d["help"] = cat.HELP[it.id]
        d["source_display"] = cat.SOURCE_DISPLAY.get(it.id, it.text_source)
        d["backtest_display"] = cat.backtest_display(it)
        d["short"] = bk.short_name(it)
        items.append(d)
    stages = [{"id": s, "circle": cat.STAGE_CIRCLE[s], "name": cat.STAGE_NAME[s],
               "once": s in bk.ONCE_STAGES, "toggle": s in bk.TOGGLE_STAGES} for s in cat.STAGES]
    return {"items": items, "stages": stages, "ops": cat.OP_NAME, "execs": cat.EXEC_NAME,
            "categories": list(dict.fromkeys(i.category for i in cat.ITEMS))}


DAYS = "월화수목금토일"
DELETE_BLOCKED = "실전 운용이나 모의투자 기록이 있는 전략은 삭제할 수 없어요"


def md_day(iso: str | None) -> str:
    """'11/1(일)'(KST)."""
    if not iso:
        return ""
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        return ""
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    k = t.astimezone(KST)
    return f"{k.month}/{k.day}({DAYS[k.weekday()]})"


def hm(iso: str | None) -> str:
    if not iso:
        return ""
    t = datetime.fromisoformat(iso)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(KST).strftime("%H:%M")


def view(body: dict[str, Any], *, dart: bool) -> dict[str, Any]:
    """본문 하나의 화면용 셈: 분석 · 문장 · 실행 방식 칩 · 줄 글 · 카드 줄."""
    g = body["graph"]
    a = bk.analyze(g, dart=dart)
    chips: dict[str, list[dict[str, str] | None]] = {}
    texts: dict[str, list[str]] = {}
    lines: dict[str, list[str]] = {}
    for b in g["blocks"]:
        chips[b["id"]] = [bk.exec_chip(g, b["id"], i) for i in range(len(b["rows"]))]
        texts[b["id"]] = [bk.row_text(r) for r in b["rows"]]
        lines[b["id"]] = bk.block_lines(g, b)
    return {"analysis": a, "sentence": bk.sentence(body), "chips": chips, "row_texts": texts,
            "block_lines": lines, "start": _start(body)}


def import_summary(body: dict[str, Any], *, dart: bool) -> dict[str, Any]:
    """가져오기 확인(그림 V2-22): 이름 · 단계 · 조건 줄 · 비운 칸 · 숫자가 빈 블록 카드."""
    g = body["graph"]
    a = bk.analyze(g, dart=dart)
    blanks = [p for p in a["problems"] if p["kind"] == "blank"]
    rows = sum(len(b["rows"]) for b in g["blocks"])
    blank_kinds = []
    if any(p["row"] is not None for p in blanks):
        blank_kinds.append("숫자")
    if any("기간" in p["detail"] or "기간" in p["title"] for p in blanks) or any(
            any(v is None and k in ("n", "period", "short", "long") for k, v in (r.get("params") or {}).items())
            for b in g["blocks"] for r in b["rows"]):
        blank_kinds.append("기간")
    shown = [b for b in g["blocks"] if b["stage"] in ("signal", "filter", "buy", "sell")]
    others = [b for b in g["blocks"] if b["stage"] not in ("signal", "filter", "buy", "sell")]
    return {
        "name": body["name"], "stages": len(g["blocks"]), "entry": len(a["entry"]), "sell": len(a["sell"]),
        "rows": rows, "blanks": len(blanks), "blank_kinds": blank_kinds,
        "cards": [{"id": b["id"], "stage": b["stage"], "match": b["match"], "lines": bk.block_lines(g, b)}
                  for b in shown],
        "others": [b["stage"] for b in others],
    }


def _start(body: dict[str, Any]) -> dict[str, str] | None:
    items = [r["item"] for b in body["graph"]["blocks"] for r in b["rows"]]
    got = cat.start_date(items)
    return {"date": got[0].isoformat(), "reason": got[1]} if got else None


def stored_body(row: Any) -> dict[str, Any]:
    raw = json.loads(row["body"])
    return ct.read_body(raw)


def strategies_router(db: DB, *, dart: Callable[[], bool], now: Callable[[], str], today: Callable[[], date],
                running: Callable[[int], dict[str, Any] | None], used: Callable[[int], bool] | None = None,
                backtester: Any = None) -> APIRouter:
    r = APIRouter(prefix="/api/v2", responses=ERRORS)

    async def body_of(request: Request) -> dict[str, Any]:
        try:
            data = await request.json()
        except ValueError:
            raise ApiError("요청 형식이 맞지 않아요") from None
        if not isinstance(data, dict):
            raise ApiError("요청 형식이 맞지 않아요")
        return data

    def normalize(raw: Any) -> dict[str, Any]:
        try:
            return bk.normalize(raw)
        except bk.GraphError as exc:
            raise ApiError(str(exc)) from None

    def backtested(vid: int) -> str | None:
        return strategy_store.last_backtest_at(db, vid)

    def version_view(v: Any) -> dict[str, Any]:
        ran = backtested(int(v["id"]))
        return {"id": v["id"], "no": v["no"], "problems": v["problems"], "created_at": v["created_at"],
                "saved_day": md_day(v["created_at"]), "saved_hm": hm(v["created_at"]),
                "backtested": ran is not None, "backtested_hm": hm(ran) if ran else ""}

    @r.get("/strategies", response_model=StrategyList, response_model_exclude_unset=True)
    def strategies() -> dict[str, Any]:
        out = []
        for s_ in strategy_store.list_strategies(db):
            v = strategy_store.latest_version(db, s_["id"])
            if v is None:
                continue
            try:
                body = stored_body(v)
            except ct.FormatError:
                continue
            a = bk.analyze(body["graph"], dart=dart())
            out.append({"id": s_["id"], "name": s_["name"], "mode_name": a["mode_name"],
                        "problems": len(a["problems"]), "version": version_view(v), "running": running(s_["id"])})
        return {"strategies": out}

    @r.post("/import/preview", response_model=ImportPreview, response_model_exclude_unset=True)
    async def import_preview(request: Request) -> dict[str, Any]:
        data = await body_of(request)
        body, notes = ct.parse_copy_text(str(data.get("text") or ""))
        return {"body": body, "notes": notes, **import_summary(body, dart=dart())}

    @r.post("/import/accept", response_model=Created, response_model_exclude_unset=True)
    async def import_accept(request: Request) -> dict[str, Any]:
        data = await body_of(request)
        body, _ = ct.parse_copy_text(str(data.get("text") or ""))
        return strategy_jobs.create(db, body, source=body.pop("source", None), dart=dart(), now=now)

    @r.post("/import/file", response_model=Created, response_model_exclude_unset=True)
    async def import_file(request: Request) -> dict[str, Any]:
        data = await body_of(request)
        body = ct.read_file(str(data.get("text") or ""))
        body.pop("converted", None)
        return strategy_jobs.create(db, body, source=None, dart=dart(), now=now)

    @r.get("/strategies/{sid}/file", response_model=ExportFile, response_model_exclude_unset=True)
    def export_file(sid: int) -> dict[str, Any]:
        v = strategy_store.latest_version(db, sid)
        if v is None:
            raise ApiError("그 전략이 없어요", 404)
        body = stored_body(v)
        body.pop("converted", None)
        return {"name": f"{body['name']}.json", "text": ct.to_file(body)}

    @r.delete("/strategies/{sid}", response_model=OkOut, response_model_exclude_unset=True)
    def delete(sid: int) -> dict[str, Any]:
        if not strategy_store.has_strategy(db, sid):
            raise ApiError("그 전략이 없어요", 404)
        if used is not None and used(sid):
            raise ApiError(DELETE_BLOCKED, 409)
        strategy_jobs.delete(db, sid)
        return {"ok": True}

    @r.get("/versions/{vid}/backtest", response_model=BacktestInput, response_model_exclude_unset=True)
    def backtest_input(vid: int) -> dict[str, Any]:
        v = strategy_store.version(db, vid)
        if v is None:
            raise ApiError("그 버전이 없어요", 404)
        body = stored_body(v)
        s_ = strategy_store.strategy_name_row(db, v["strategy_id"])
        from ..backtest_v2 import CHIPS, JUDGE_LINE, default_range

        return {"version": version_view(v), "strategy_id": v["strategy_id"], "name": s_["name"] if s_ else "",
                "range": default_range(body, today()), "chips": CHIPS, "judge_line": JUDGE_LINE}

    @r.post("/backtest", response_model=BacktestResult, response_model_exclude_unset=True)
    async def backtest(request: Request) -> dict[str, Any]:
        import asyncio

        data = await body_of(request)
        try:
            vid = int(data.get("version_id"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ApiError("전략 버전을 골라 주세요") from None
        v = strategy_store.version(db, vid)
        if v is None:
            raise ApiError("그 버전이 없어요", 404)
        body = stored_body(v)
        try:
            start = datetime.strptime(str(data.get("start")), "%Y-%m-%d").date()
            end = datetime.strptime(str(data.get("end")), "%Y-%m-%d").date()
            cash = float(data.get("cash"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ApiError("기간과 시작 금액 형식이 맞지 않아요") from None
        if backtester is None:
            raise ApiError("백테스트를 할 수 없어요", 503)
        res = await asyncio.to_thread(backtester, body, start, end, cash)
        strategy_jobs.record_backtest(db, vid, now(), start, end, cash)
        res["ran_day"] = md_day(res["ran_at"])
        res["ran_hm"] = hm(res["ran_at"])
        return res

    @r.get("/catalog", response_model=Catalog, response_model_exclude_unset=True)
    def catalog() -> dict[str, Any]:
        return {**catalog_view(), "dart": dart()}

    @r.post("/analyze", response_model=Analyzed, response_model_exclude_unset=True)
    async def analyze(request: Request) -> dict[str, Any]:
        data = await body_of(request)
        body = normalize(data.get("body"))
        return {"body": body, **view(body, dart=dart())}

    @r.get("/strategies/{sid}", response_model=StrategyDetail, response_model_exclude_unset=True)
    def strategy(sid: int) -> dict[str, Any]:
        s = strategy_store.strategy(db, sid)
        if s is None:
            raise ApiError("그 전략이 없어요", 404)
        v = strategy_store.latest_version(db, sid)
        if v is None:
            raise ApiError("그 전략이 없어요", 404)
        body = stored_body(v)
        body["name"] = s["name"]
        versions = [version_view(x)
                    for x in strategy_store.versions_of(db, sid)]
        return {"id": sid, "name": s["name"], "version": version_view(v), "versions": versions,
                "body": body, "running": running(sid), "deletable": not (used is not None and used(sid)),
                **view(body, dart=dart())}

    @r.post("/strategies", response_model=Created, response_model_exclude_unset=True)
    async def create(request: Request) -> dict[str, Any]:
        data = await body_of(request)
        body = normalize(data.get("body"))
        body.pop("source", None)
        return strategy_jobs.create(db, body, source=None, dart=dart(), now=now)

    @r.post("/strategies/{sid}/versions", response_model=SavedVersion, response_model_exclude_unset=True)
    async def new_version(sid: int, request: Request) -> dict[str, Any]:
        if not strategy_store.has_strategy(db, sid):
            raise ApiError("그 전략이 없어요", 404)
        data = await body_of(request)
        body = normalize(data.get("body"))
        return strategy_jobs.save_version(db, sid, body, dart=dart(), now=now)

    @r.get("/strategies/{sid}/copytext", response_model=CopyText, response_model_exclude_unset=True)
    def copytext(sid: int) -> dict[str, Any]:
        v = strategy_store.latest_version(db, sid)
        if v is None:
            raise ApiError("그 전략이 없어요", 404)
        body = stored_body(v)
        body.pop("converted", None)
        return {"text": ct.to_copy_text(body)}

    return r
