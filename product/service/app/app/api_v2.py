"""v2 전략 API(블록 본문 · TASKS T-30 · T-31 · T-32). 화면 편집기 · 목록 · 붙여 넣기 · 백테스트가 써요.

- 본문은 v3 블록(`blocks.py`). 저장된 v1 본문(일곱 칸 · 그래프 노드)은 읽을 때 v3로 바꿔요(R-C3 · R-C8).
- 문제 목록 · 경고 · 실행 방식 칩 · 문장으로 보기는 서버가 셈해서 돌려줘요(화면과 같은 규칙 하나).
- 저장은 문제가 있어도 돼요(R-P 머리). 버전 꼴은 `format = blocks`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Request

from .domain import blocks as bk
from .domain import catalog as cat
from .domain import copytext as ct
from .db import DB


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, **extra: Any) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra


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


KST = timezone(timedelta(hours=9))
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


def make_router(db: DB, *, dart: Callable[[], bool], unique_name: Callable[[str], str],
                now: Callable[[], str], running: Callable[[int], dict[str, Any] | None],
                used: Callable[[int], bool] | None = None, backtester: Any = None) -> APIRouter:
    r = APIRouter(prefix="/api/v2")

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

    def save(sid: int, body: dict[str, Any]) -> dict[str, Any]:
        a = bk.analyze(body["graph"], dart=dart())
        with db.tx():
            row = db.one("SELECT COALESCE(MAX(no),0)+1 AS n FROM versions WHERE strategy_id=?", (sid,))
            no = int(row["n"])
            text = json.dumps(body, ensure_ascii=False)
            vid = db.run("INSERT INTO versions(strategy_id,no,body,problems,created_at,format) VALUES(?,?,?,?,?,?)",
                         (sid, no, text, len(a["problems"]), now(), "blocks"))
            db.run("UPDATE strategies SET name=?, template=? WHERE id=?", (body["name"], a["mode"] or "", sid))
        return {"version_id": vid, "no": no, "problems": len(a["problems"])}

    def backtested(vid: int) -> str | None:
        row = db.one("SELECT ran_at FROM backtest_runs WHERE version_id=? ORDER BY id DESC LIMIT 1", (vid,))
        return str(row["ran_at"]) if row else None

    def version_view(v: Any) -> dict[str, Any]:
        ran = backtested(int(v["id"]))
        return {"id": v["id"], "no": v["no"], "problems": v["problems"], "created_at": v["created_at"],
                "saved_day": md_day(v["created_at"]), "saved_hm": hm(v["created_at"]),
                "backtested": ran is not None, "backtested_hm": hm(ran) if ran else ""}

    @r.get("/strategies")
    def strategies() -> dict[str, Any]:
        out = []
        for s_ in db.all("SELECT * FROM strategies ORDER BY id"):
            v = db.one("SELECT * FROM versions WHERE strategy_id=? ORDER BY no DESC LIMIT 1", (s_["id"],))
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

    @r.post("/import/preview")
    async def import_preview(request: Request) -> dict[str, Any]:
        data = await body_of(request)
        body, notes = ct.parse_copy_text(str(data.get("text") or ""))
        return {"body": body, "notes": notes, **import_summary(body, dart=dart())}

    @r.post("/import/accept")
    async def import_accept(request: Request) -> dict[str, Any]:
        data = await body_of(request)
        body, _ = ct.parse_copy_text(str(data.get("text") or ""))
        return create_from(body, source=body.pop("source", None))

    @r.post("/import/file")
    async def import_file(request: Request) -> dict[str, Any]:
        data = await body_of(request)
        body = ct.read_file(str(data.get("text") or ""))
        body.pop("converted", None)
        return create_from(body, source=None)

    def create_from(body: dict[str, Any], source: Any) -> dict[str, Any]:
        body["name"] = unique_name(body["name"])
        sid = db.run("INSERT INTO strategies(name,template,source,created_at) VALUES(?,?,?,?)",
                     (body["name"], bk.mode_of(body["graph"]) or "", json.dumps(source, ensure_ascii=False)
                      if source else None, now()))
        return {"id": sid, "name": body["name"], **save(sid, body)}

    @r.get("/strategies/{sid}/file")
    def export_file(sid: int) -> dict[str, Any]:
        v = db.one("SELECT * FROM versions WHERE strategy_id=? ORDER BY no DESC LIMIT 1", (sid,))
        if v is None:
            raise ApiError("그 전략이 없어요", 404)
        body = stored_body(v)
        body.pop("converted", None)
        return {"name": f"{body['name']}.json", "text": ct.to_file(body)}

    @r.delete("/strategies/{sid}")
    def delete(sid: int) -> dict[str, Any]:
        if db.one("SELECT id FROM strategies WHERE id=?", (sid,)) is None:
            raise ApiError("그 전략이 없어요", 404)
        if used is not None and used(sid):
            raise ApiError(DELETE_BLOCKED, 409)
        with db.tx():
            db.run("DELETE FROM versions WHERE strategy_id=?", (sid,))
            db.run("DELETE FROM strategies WHERE id=?", (sid,))
        return {"ok": True}

    @r.get("/versions/{vid}/backtest")
    def backtest_input(vid: int) -> dict[str, Any]:
        v = db.one("SELECT * FROM versions WHERE id=?", (vid,))
        if v is None:
            raise ApiError("그 버전이 없어요", 404)
        body = stored_body(v)
        s_ = db.one("SELECT name FROM strategies WHERE id=?", (v["strategy_id"],))
        from .backtest_v2 import CHIPS, JUDGE_LINE, default_range

        return {"version": version_view(v), "strategy_id": v["strategy_id"], "name": s_["name"] if s_ else "",
                "range": default_range(body, datetime.now(KST).date()), "chips": CHIPS, "judge_line": JUDGE_LINE}

    @r.post("/backtest")
    async def backtest(request: Request) -> dict[str, Any]:
        import asyncio

        data = await body_of(request)
        try:
            vid = int(data.get("version_id"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise ApiError("전략 버전을 골라 주세요") from None
        v = db.one("SELECT * FROM versions WHERE id=?", (vid,))
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
        db.run("INSERT INTO backtest_runs(version_id, ran_at, start_d, end_d, cash) VALUES(?,?,?,?,?)",
               (vid, now(), start.isoformat(), end.isoformat(), cash))
        res["ran_day"] = md_day(res["ran_at"])
        res["ran_hm"] = hm(res["ran_at"])
        return res

    @r.get("/catalog")
    def catalog() -> dict[str, Any]:
        return {**catalog_view(), "dart": dart()}

    @r.post("/analyze")
    async def analyze(request: Request) -> dict[str, Any]:
        data = await body_of(request)
        body = normalize(data.get("body"))
        return {"body": body, **view(body, dart=dart())}

    @r.get("/strategies/{sid}")
    def strategy(sid: int) -> dict[str, Any]:
        s = db.one("SELECT * FROM strategies WHERE id=?", (sid,))
        if s is None:
            raise ApiError("그 전략이 없어요", 404)
        v = db.one("SELECT * FROM versions WHERE strategy_id=? ORDER BY no DESC LIMIT 1", (sid,))
        if v is None:
            raise ApiError("그 전략이 없어요", 404)
        body = stored_body(v)
        body["name"] = s["name"]
        versions = [version_view(x)
                    for x in db.all("SELECT * FROM versions WHERE strategy_id=? ORDER BY no DESC", (sid,))]
        return {"id": sid, "name": s["name"], "version": version_view(v), "versions": versions,
                "body": body, "running": running(sid), "deletable": not (used is not None and used(sid)),
                **view(body, dart=dart())}

    @r.post("/strategies")
    async def create(request: Request) -> dict[str, Any]:
        data = await body_of(request)
        body = normalize(data.get("body"))
        body.pop("source", None)
        body["name"] = unique_name(body["name"])
        sid = db.run("INSERT INTO strategies(name,template,source,created_at) VALUES(?,?,?,?)",
                     (body["name"], bk.mode_of(body["graph"]) or "", None, now()))
        return {"id": sid, "name": body["name"], **save(sid, body)}

    @r.post("/strategies/{sid}/versions")
    async def new_version(sid: int, request: Request) -> dict[str, Any]:
        if db.one("SELECT id FROM strategies WHERE id=?", (sid,)) is None:
            raise ApiError("그 전략이 없어요", 404)
        data = await body_of(request)
        body = normalize(data.get("body"))
        return save(sid, body)

    @r.get("/strategies/{sid}/copytext")
    def copytext(sid: int) -> dict[str, Any]:
        v = db.one("SELECT * FROM versions WHERE strategy_id=? ORDER BY no DESC LIMIT 1", (sid,))
        if v is None:
            raise ApiError("그 전략이 없어요", 404)
        body = stored_body(v)
        body.pop("converted", None)
        return {"text": ct.to_copy_text(body)}

    return r
