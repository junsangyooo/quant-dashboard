"""v2 전략 API(블록 본문 · TASKS T-30 · T-31 · T-32). 화면 편집기 · 목록 · 붙여 넣기 · 백테스트가 써요.

- 본문은 v3 블록(`blocks.py`). 저장된 v1 본문(일곱 칸 · 그래프 노드)은 읽을 때 v3로 바꿔요(R-C3 · R-C8).
- 문제 목록 · 경고 · 실행 방식 칩 · 문장으로 보기는 서버가 셈해서 돌려줘요(화면과 같은 규칙 하나).
- 저장은 문제가 있어도 돼요(R-P 머리). 버전 꼴은 `format = blocks`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Request

from . import blocks as bk
from . import catalog as cat
from . import copytext as ct
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


def view(body: dict[str, Any], *, dart: bool) -> dict[str, Any]:
    """본문 하나의 화면용 셈: 분석 · 문장 · 실행 방식 칩 · 줄 글."""
    g = body["graph"]
    a = bk.analyze(g, dart=dart)
    chips: dict[str, list[dict[str, str] | None]] = {}
    texts: dict[str, list[str]] = {}
    for b in g["blocks"]:
        chips[b["id"]] = [bk.exec_chip(g, b["id"], i) for i in range(len(b["rows"]))]
        texts[b["id"]] = [bk.row_text(r) for r in b["rows"]]
    return {"analysis": a, "sentence": bk.sentence(body), "chips": chips, "row_texts": texts,
            "start": _start(body)}


def _start(body: dict[str, Any]) -> dict[str, str] | None:
    items = [r["item"] for b in body["graph"]["blocks"] for r in b["rows"]]
    got = cat.start_date(items)
    return {"date": got[0].isoformat(), "reason": got[1]} if got else None


def stored_body(row: Any) -> dict[str, Any]:
    raw = json.loads(row["body"])
    return ct.read_body(raw)


def make_router(db: DB, *, dart: Callable[[], bool], unique_name: Callable[[str], str],
                now: Callable[[], str], running: Callable[[int], dict[str, Any] | None]) -> APIRouter:
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
        versions = [{"id": x["id"], "no": x["no"], "problems": x["problems"], "created_at": x["created_at"]}
                    for x in db.all("SELECT * FROM versions WHERE strategy_id=? ORDER BY no", (sid,))]
        return {"id": sid, "name": s["name"], "version": {"id": v["id"], "no": v["no"]}, "versions": versions,
                "body": body, "running": running(sid), **view(body, dart=dart())}

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
