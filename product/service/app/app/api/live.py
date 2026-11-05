"""실전 운용 화면 모양(ARCHITECTURE 2절 API 층 · TASKS P1-08).

실전 상태는 주인(`run/live.py`의 `Live`)만 바꿔요. 여기는 주인과 저장 층(읽기 쿼리)에서 읽어 화면이 받는 모양으로 묶기만 해요:
- `summary(live)`: 운용 요약(`GET /api/live` · 실전 조작 라우트가 돌려주는 값).
- `screen(live)`: 자산 · 계획 · 기록 · 할 일 화면(V2-10 ~ V2-13)이 한 번에 받는 값(`GET /api/live/screen`).
라우트는 아직 `main.py`에 있어요(기능별 라우터로 나누는 일은 P1-09). 키 · 값 · 순서는 옮기기 전 `Live.view` · `Live.screen` 그대로예요.
"""

from __future__ import annotations

import json
from typing import Any

from ..datamgmt import history_rows
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
