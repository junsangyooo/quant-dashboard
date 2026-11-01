"""모의투자를 가짜 시계로 하루씩 돌려 체결을 모은다(회귀 기준과 시험이 같이 쓴다)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.connect import Connections
from app.db import DB
from app.market import KST, Market
from app.paper import Paper
from app.vault import Vault


class _Bars:
    def __init__(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self.data = {f"{s}.KS": rows for s, rows in data.items()}

    def daily(self, ysym: str, start, end):  # type: ignore[no-untyped-def]
        rows = self.data.get(ysym, [])
        return [dict(b) for b in rows if start.isoformat() <= b["d"] <= end.isoformat()]


class _Now:
    def __init__(self) -> None:
        self.t = datetime(2000, 1, 3, 17, tzinfo=KST)

    def __call__(self) -> datetime:
        return self.t


def paper_replay(body: dict[str, Any], bars: dict[str, list[dict[str, Any]]], first: int, last: int,
                 folder: Path, cash: float = 10_000_000.0) -> dict[str, Any]:
    """days[first] 17:00에 시작하고 days[last]까지 날마다 17:00에 신호 확인. 체결 · 마지막 자산."""
    days = sorted({b["d"] for rows in bars.values() for b in rows})
    folder.mkdir(parents=True, exist_ok=True)
    db = DB(folder / "app.db")
    vault = Vault(db, scrypt_n=2**12)
    clock = {"t": 1e9}
    now = _Now()
    market = Market(db, _Bars(bars), clock=lambda: clock["t"])
    conns = Connections(db, vault, lambda: (lambda r: (_ for _ in ()).throw(RuntimeError("no toss"))))
    paper = Paper(db, market, conns, now=now)
    sid = db.run("INSERT INTO strategies(name,template,source,created_at) VALUES(?,?,?,?)",
                 ("회귀", str(body.get("template") or "event"), None, "t"))
    vid = db.run("INSERT INTO versions(strategy_id,no,body,problems,created_at) VALUES(?,?,?,?,?)",
                 (sid, 1, json.dumps(body, ensure_ascii=False), 0, "t"))
    now.t = datetime.fromisoformat(days[first] + "T17:00:00").replace(tzinfo=KST)
    paper.start(vid, cash)
    for d in days[first + 1 : last + 1]:
        now.t = datetime.fromisoformat(d + "T17:00:00").replace(tzinfo=KST)
        clock["t"] += 3600
        paper.judge("auto")
    rows = db.all("SELECT d, symbol, side, qty, price, amount, cost, pnl FROM paper_trades ORDER BY id")
    trades = [
        {"d": r["d"], "sym": r["symbol"], "side": r["side"], "qty": r["qty"], "price": r["price"],
         "amount": r["amount"], "cost": r["cost"], "pnl": r["pnl"]}
        for r in rows
    ]
    eq = db.one("SELECT equity FROM paper_equity ORDER BY d DESC LIMIT 1")
    db.conn.close()
    return {"trades": trades, "final": float(eq["equity"]) if eq else cash}
