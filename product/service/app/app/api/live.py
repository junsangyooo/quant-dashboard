"""실전 운용 라우터와 화면 모양(ARCHITECTURE 2절 API 층 · TASKS P1-08 · P1-09 · T-60 ~ T-63 · SPEC 7-2 · 7-4).

실전 상태는 주인(`run/live.py`의 `Live`)만 바꿔요. 라우트는 주인의 공개 메서드를 부르고, 화면이 받는 모양은 주인과 저장 층
(읽기 쿼리)에서 읽어 묶기만 해요:
- `summary(live)`: 운용 요약(`GET /api/live` · 실전 조작 라우트가 돌려주는 값).
- `screen(live)`: 자산 · 계획 · 기록 · 할 일 화면(V2-10 ~ V2-13)이 한 번에 받는 값(`GET /api/live/screen`).
- `live_router`: 운용 보기 · 시작 전 확인 · 시작 · 새 매수 멈춤 · 다시 켜기 · 끝내기 · 전부 팔기 · 금액 · 한도 · 전략 바꾸기 ·
  할 일 처리(결과 모르는 주문 · 권리 변동 · 계좌에 맞추기 · 큰 주문). 새 매수 멈춤만 로그인만이고 나머지는 비밀번호를 다시 받아요.
키 · 값 · 순서는 옮기기 전 `Live.view` · `Live.screen` 그대로예요.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Request

from ..domain import blocks as bkm
from ..domain.copytext import read_body
from ..run.live import LiveError
from ..services import access
from ..services.connect import Connections
from ..services.data_admin import history_rows
from ..services.telegram import Telegram
from ..store.db import DB
from .http import NeedConfirm, json_body
from ..domain.markets.kr import KST
from ..domain.rules import buy_cap
from ..run.live import Live
from ..store import runs as run_store
from ..store import strategies as strategy_store
from ..store import todos as todo_store


def summary(live: Live) -> dict[str, Any]:
    r = live.run()
    todos = [dict(t) for t in todo_store.open_todos(live.db)]
    if r is None:
        return {"running": False, "paused": live.paused, "halted": live.halted, "todos": todos}
    rid = int(r["id"])
    st = live.state(rid)
    return {
        "running": True, "id": rid, "version_id": r["version_id"], "amount": r["amount"],
        "account_tail": r["account_tail"], "started_at": r["started_at"], "cash": st.get("cash"),
        "positions": st.get("pos", {}), "manual": st["manual"], "blocked": st["blocked"],
        "next": st.get("next"), "paused": live.paused, "halted": live.halted,
        "settings": json.loads(r["settings"] or "{}"), "todos": todos,
        "last_check": live.meta(rid, "last_check"),
    }


def screen(live: Live) -> dict[str, Any]:
    """화면(V2-10 자산 · V2-11 계획 · V2-12 기록 · V2-13 할 일)이 한 번에 받는 값. 토스가 안 되면 저장한 값만."""
    base = summary(live)
    names = {k: v.get("name") or k for k, v in live.info().items()}
    account, prices = live.account()
    base["account"] = account
    base["names"] = names
    alerts = [dict(a) for a in todo_store.recent_alerts(live.db)]
    base["alerts"] = alerts
    if not base["running"]:
        last = run_store.latest_run(live.db)
        base["last_run"] = dict(last) if last else None
        return base
    rid = int(base["id"])
    r = live.run(rid)
    v = strategy_store.version_no_name(live.db, r["version_id"])
    base["strategy"] = {"name": v["name"] if v else "", "version_no": int(v["no"]) if v else 0}
    pos = []
    value = 0.0
    for sym, p in base["positions"].items():
        price = prices.get(sym) or float(p["avg"])
        value += int(p["qty"]) * price
        pos.append({"sym": sym, "name": names.get(sym, sym), "qty": int(p["qty"]), "avg": float(p["avg"]),
                    "price": price, "value": int(p["qty"]) * price, "pnl": int(p["qty"]) * (price - float(p["avg"])),
                    "entry_d": p.get("entry_d")})
    base["holdings"] = pos
    base["eval"] = value
    base["equity"] = value + float(base["cash"] or 0)
    base["curve"] = [(x["d"], x["equity"]) for x in run_store.equity_curve(live.db, rid)]
    plans = []
    for pl in (base.get("next") or {}).get("plans", []):
        row = {"sym": pl["sym"], "name": names.get(pl["sym"], pl["sym"]), "side": pl["side"],
               "reason": pl.get("reason") or [], "close": pl.get("close"), "kind": pl.get("kind")}
        if pl["side"] == "buy" and pl.get("close"):
            cap = buy_cap(float(pl["close"]))
            qty = int(float(pl["value"]) // cap)
            row |= {"cap": cap, "qty": qty, "max": qty * cap, "est": qty * float(pl["close"])}
        else:
            row |= {"qty": int(pl.get("qty") or 0)}
        plans.append(row)
    base["plan_rows"] = plans
    hist = [h for h in history_rows(live.db, rid)]
    base["history"] = list(reversed(hist))
    fills = run_store.recent_fills(live.db, rid)
    base["recent"] = [{"d": f["d"], "sym": f["symbol"], "name": names.get(f["symbol"], f["symbol"]),
                       "side": f["side"], "qty": int(f["qty"]), "price": float(f["price"])} for f in fills]
    base["realized"] = sum(h["pnl"] or 0 for h in hist)
    base["trades"] = len([h for h in hist if h["status"] in ("체결", "일부 체결")])
    base["orders_n"] = len(hist)
    try:
        eng = live.engine(r, live.now().astimezone(KST).date())
        base["watch"] = [{"sym": sym, "name": names.get(sym, sym), "levels": live.watch_levels(eng, sym),
                          "price": prices.get(sym)} for sym in base["positions"]]
    except Exception:
        base["watch"] = []
    return base


def live_router(*, db: DB, live: Live, conns: Connections, telegram: Telegram, need_confirm: NeedConfirm) -> APIRouter:
    r = APIRouter()

    def _rid() -> int:
        run = live.run()
        if run is None:
            raise LiveError("실전 운용 중이 아니에요", 409)
        return int(run["id"])

    @r.get("/api/live")
    def live_view() -> dict[str, Any]:
        return summary(live)

    @r.get("/api/live/screen")
    async def live_screen() -> dict[str, Any]:
        return await asyncio.to_thread(screen, live)

    @r.get("/api/live/preview")
    def live_preview(version_id: int) -> dict[str, Any]:
        """V2-30 ① 확인할 것: 토스 연결 · 백테스트 함 · 다른 운용 없음 · 텔레그램 · 설치 위치 · 손절 없음(R-X10)."""
        v = strategy_store.version_with_name(db, version_id)
        if v is None:
            raise LiveError("그 버전이 없어요", 404)
        body = json.loads(v["body"])
        g = read_body(body)["graph"]
        stop = any(r["item"] in ("stop_loss", "trailing_stop") and bkm.exec_of(g, b["id"], i) in ("intraday", "broker")
                   for b in g["blocks"] if b["stage"] == "sell" for i, r in enumerate(b["rows"]))
        view = conns.view()["toss"]
        tg = telegram.view()
        checks = [
            {"key": "toss", "ok": bool(view["saved"] and (view.get("last_check") or {}).get("ok"))},
            {"key": "account", "ok": bool(view.get("account_tail")), "tail": view.get("account_tail")},
            {"key": "backtest", "ok": strategy_store.was_backtested(db, version_id)},
            {"key": "single", "ok": live.run() is None},
            {"key": "telegram", "ok": bool(tg["saved"] and tg["chat"])},
            {"key": "place", "ok": bool(access.place(db)), "place": access.place(db)},
        ]
        return {"name": v["name"], "version_no": v["no"], "checks": checks, "has_stop": stop,
                "ok": all(c["ok"] for c in checks)}

    @r.post("/api/live/start")
    async def live_start(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_start")
        b = await json_body(request)
        try:
            vid, amount = int(b.get("version_id")), float(b.get("amount"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise LiveError("버전과 운용 금액을 정해 주세요") from None
        await asyncio.to_thread(live.start, vid, amount)
        return summary(live)

    @r.post("/api/live/pause")
    def live_pause() -> dict[str, Any]:
        live.pause_new_buys("app")  # 로그인만(SPEC 7-4)
        return summary(live)

    @r.post("/api/live/resume")
    def live_resume(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_resume_buys")
        live.resume_new_buys()
        return summary(live)

    @r.post("/api/live/end")
    def live_end(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_end")
        live.end(_rid())
        return summary(live)

    @r.post("/api/live/sell-all")
    def live_sell_all(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_sell_all_end")
        return {"orders": live.sell_all_and_end(_rid()), **summary(live)}

    @r.put("/api/live/amount")
    async def live_amount(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_amount")
        b = await json_body(request)
        live.set_amount(_rid(), float(b.get("amount") or 0))
        return summary(live)

    @r.put("/api/live/limits")
    async def live_limits(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_limits")
        b = await json_body(request)
        live.set_limits(_rid(), b)
        return summary(live)

    @r.put("/api/live/strategy")
    async def live_strategy(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_strategy")
        b = await json_body(request)
        from_d = live.change_strategy(_rid(), int(b.get("version_id") or 0))
        return {"from": from_d, **summary(live)}

    @r.post("/api/todos/{tid}/unknown")
    async def todo_unknown(tid: int, request: Request) -> dict[str, Any]:
        need_confirm(request, "unknown_order_record")
        b = await json_body(request)
        t = todo_store.todo_of_kind(db, tid, "unknown")
        if t is None:
            raise LiveError("그 할 일이 없어요", 404)
        live.resolve_unknown(_rid(), int(json.loads(t["data"])["order"]), filled_qty=int(b.get("filled_qty") or 0),
                             price=float(b.get("price") or 0))
        return summary(live)

    @r.post("/api/todos/{tid}/corp")
    def todo_corp(tid: int, request: Request) -> dict[str, Any]:
        need_confirm(request, "todo_corp_action")
        t = todo_store.todo_of_kind(db, tid, "corp")
        if t is None:
            raise LiveError("그 할 일이 없어요", 404)
        live.apply_corp(_rid(), t["symbol"])
        return summary(live)

    @r.post("/api/todos/{tid}/match")
    def todo_match(tid: int, request: Request) -> dict[str, Any]:
        need_confirm(request, "todo_match_account")
        t = todo_store.todo_of_kind(db, tid, "mismatch")
        if t is None:
            raise LiveError("그 할 일이 없어요", 404)
        live.match_account(_rid(), t["symbol"])
        return summary(live)

    @r.post("/api/todos/{tid}/big-order")
    def todo_big(tid: int, request: Request) -> dict[str, Any]:
        need_confirm(request, "todo_big_order")
        return {"order": live.send_big(_rid(), tid), **summary(live)}

    return r
