"""화면 API 시간(자산 · 계획 · 기록 화면이 부르는 라우트 · 가짜 자료 · 로컬 TestClient).

실전 화면 셋(자산 · 계획 · 기록 · `web/src/screens/Live/LiveScreens.tsx`)은 `/api/live/screen` 하나를 불러요(앱 상태는
`/api/state`). 기록 화면의 CSV 내려받기는 `/api/history/csv`. 가짜 토스(`tests/fake_toss.py`)로 실전 운용을 시작해
계획 · 주문 · 체결이 든 상태에서 재요. 시간은 기준선 본체 밖(`timing.json`)에만 남겨요.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.main import create_app
from app.domain.markets.kr import KST
from app.adapters.toss import RateLimiter
from tests.baseline.clock import FIXED_NOW
from tests.conftest import CsrfClient, FakeIp, confirm, setup_owner
from tests.fake_toss import ACCOUNT_NO, CLIENT_ID, CLIENT_SECRET, FakeTossServer, stock_row
from tests.test_blocks import B, G, R

SYM = "005930"
ROUTES = ["/api/state", "/api/live/screen", "/api/history/csv", "/api/v2/strategies", "/api/v2/paper", "/api/about"]


def _body() -> dict[str, Any]:
    g = G([B("u", "universe", [R("manual_list", value=[SYM])]), B("s", "signal", [R("price", "gte", 1)]),
           B("k", "select", [R("top_n", value=1)]), B("b", "buy"),
           B("x", "sell", [R("stop_loss", value=7, exec_="intraday"), R("max_hold", value=50)]), B("w", "weight")],
          ("u", "s"), ("s", "k"), ("k", "b"), ("b", "x"), ("w", "b"))
    return {"name": "실전 화면", "graph": g}


class _Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


def make_world(tmp: Path) -> tuple[Any, dict[str, Any]]:
    """가짜 토스로 실전 운용을 시작한 앱 클라이언트와 준비 과정 기록."""
    from tests.conftest import make_bars

    server = FakeTossServer()
    today = date(2026, 11, 3)
    start = date(2026, 7, 27)
    server.bars = {SYM: make_bars([10_000.0] * 70, start=start)}
    server.index_bars = {"KOSPI": make_bars([2500.0] * 70, start=start)}
    server.stocks = {SYM: stock_row(SYM, "종목30")}
    server.prices = {SYM: "10000"}
    server.today = today
    clock = _Clock(datetime(2026, 11, 2, 21, 0, tzinfo=KST))
    epoch = lambda: clock.t.timestamp()  # noqa: E731
    app = create_app(tmp / "data", toss_transport=lambda: server, ip_fetch=FakeIp(), scrypt_n=2**12,
                     scheduler=False, now=clock, keyfile=False)
    app.state.market.clock = epoch
    client = CsrfClient(app)
    log: dict[str, Any] = {}
    setup_owner(client)
    r = client.put("/api/connect/toss", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                                               "account_no": ACCOUNT_NO})
    log["connect"] = r.status_code
    toss = app.state.connections.client()
    if toss is not None:
        toss.wall_clock = epoch
        toss.limiter = RateLimiter(clock=epoch, sleep=lambda s: None)
    r = client.post("/api/v2/strategies", json={"body": _body()})
    sid = r.json()["id"]
    vid = client.get(f"/api/v2/strategies/{sid}").json()["version"]["id"]
    r = client.post("/api/v2/backtest", json={"version_id": vid, "start": "2026-08-03", "end": "2026-10-30",
                                              "cash": 10_000_000})
    log["backtest"] = r.status_code
    r = client.post("/api/live/start", json={"version_id": vid, "amount": 10_000_000},
                    headers=confirm(client, "live_start"))
    log["live_start"] = r.status_code
    if r.status_code != 200:
        log["live_start_error"] = r.json().get("error")
    # 아침: 점검 → 주문 → 체결 → 대조(화면에 계획 · 주문 · 보유가 보이게)
    live = app.state.live
    run = live.run()
    if run is not None:
        rid = int(run["id"])
        clock.t = datetime(2026, 11, 3, 8, 30, tzinfo=KST)
        log["precheck"] = live.precheck(rid)
        clock.t = datetime(2026, 11, 3, 8, 35, tzinfo=KST)
        out = live.open_orders(rid)
        log["open_orders"] = [o.get("status") for o in out]
        for o in app.state.db.all("SELECT * FROM orders WHERE status='sent'"):
            server.fill(o["toss_order_id"], str(o["qty"]), "10000")
            server.holdings[SYM] = {"quantity": str(o["qty"]), "avg": "10000", "sellable": str(o["qty"])}
        clock.t = datetime(2026, 11, 3, 9, 1, tzinfo=KST)
        live.after_open(rid)
        clock.t = FIXED_NOW
    return client, log


def measure(client: Any, n: int = 30) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for path in ROUTES:
        took = []
        status = None
        size = 0
        for _ in range(n):
            t0 = time.perf_counter()
            r = client.get(path)
            took.append((time.perf_counter() - t0) * 1000)
            status = r.status_code
            size = len(r.content)
        took.sort()
        out[path] = {"status": status, "bytes": size, "n": n, "p50_ms": round(took[len(took) // 2], 2),
                     "p95_ms": round(took[min(len(took) - 1, int(len(took) * 0.95))], 2),
                     "max_ms": round(took[-1], 2)}
    return out


def run_all(tmp: Path) -> dict[str, Any]:
    client, log = make_world(tmp)
    with client:
        timing = measure(client)
        screen = client.get("/api/live/screen").json()
    return {"setup": log, "timing": timing,
            "screen_summary": {"running": bool(screen.get("running")), "plan_rows": len(screen.get("plan_rows", [])),
                               "holdings": len(screen.get("holdings", [])), "history": len(screen.get("history", [])),
                               "recent": len(screen.get("recent", []))}}


if __name__ == "__main__":
    import tempfile

    from tests.baseline.clock import freeze_plain

    freeze_plain()
    with tempfile.TemporaryDirectory(prefix="quant-baseline-screen-") as d:
        print(json.dumps(run_all(Path(d)), ensure_ascii=False, indent=1))
