"""하루 흐름 기록(P1-01 · QUALITY T4): 실전 tick(`live.tick`)과 스케줄러(`schedule.Scheduler`)를 고정 시계로
30초 간격으로 하루 돌려 일어난 일의 순서를 남겨요.

- 가짜 토스 · 가짜 시계는 `tests/test_live.py`의 `World`(가짜 토스는 `tests/fake_toss.py`)를 그대로 써요.
- 앱 루프(`main._auto_loop`)와 같은 차례로 돌려요: (켤 때 한 번 모의투자 v2 확인) → 스케줄러 `run_due` → `live.tick`.
  스케줄러 일은 조립(`app.py` · 옛 `main.py`)과 같이 `paper_check`(20:10) · `live_check`(20:10)예요.
- 걸음마다 기록하는 것: 시각 · 스케줄러가 돈 일 · tick이 한 일 · 가짜 토스로 간 요청 · 텔레그램(가짜)로 간 글 ·
  DB 변화(orders · fills · todos · cond_orders · alerts · run_cash · run_equity · runs · live_state · meta).
  아무 일도 없는 걸음은 적지 않아요.
- 6가지 날: 정상 날 · 08:30 점검 실패 뒤 08:40 회복 · 08:50까지 끝까지 실패(창의 끝 · `<=` 경계) · 늦게 여는 날 · 08:55에 켬 ·
  장중에 다시 켬.
- 일봉 캐시의 시계(`Market.clock`)도 모의 시각으로 바꿔 끼워 바깥 시계가 섞이지 않게 해요.
"""

from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.run.live import Live, tick
from app.domain.markets.kr import KST
from app.run.paper import PaperV2
from app.run.scheduler import Scheduler
from app.adapters.toss import RateLimiter
from tests.baseline.mask import mask_values
from tests.fake_toss import holiday, regular_day
from tests.test_blocks import R
from tests.test_live import SYM, World, body, running

MON = date(2026, 11, 2)
DAY = date(2026, 11, 3)  # 화요일
STEP = timedelta(seconds=30)
SCENARIOS = ("normal", "precheck_fail_recover", "precheck_exhausted", "late_open", "start_0855", "restart_intraday")
SCENARIO_LINES = {
    "normal": "정상 날 · 09:00 시가 체결 · 11:00 −8% 장중 손절 → 3분마다 넓힘 → 11:07 체결 · 20:10 확인",
    "precheck_fail_recover": "08:25 허용 IP 막힘 · 08:30 점검 실패 → 08:35 다시 실패 → 08:38 복구 → 08:40 통과 · 주문",
    "precheck_exhausted": "08:25 허용 IP 막힘 · 08:30 ~ 08:50 점검 5번 모두 실패(창의 끝 · 그날 시가 주문 0) · 09:30 복구 · 보유가 없어 장중 감시할 것이 없음",
    "late_open": "장이 10:00에 여는 날 · 점검 · 주문 · 체결 대조가 1시간 밀림 · 12:00 장중 손절",
    "start_0855": "08:55에 켬 · 08:50이 지나 시가 주문을 놓침(할 일) · 09:01부터 장중",
    "restart_intraday": "09:30에 끔 · 12:00 −8% · 13:00에 다시 켬(새 Live · 새 스케줄러) → 바로 장중 손절",
}
TABLES = {
    "orders": ("id",), "fills": ("id",), "todos": ("id",), "cond_orders": ("id",), "alerts": ("id",),
    "run_cash": ("id",), "run_equity": ("run_id", "d"), "runs": ("id",), "live_state": ("run_id",),
    "positions": ("run_id", "symbol"), "meta": ("k",),
}


def _at(d: date, hh: int, mm: int, ss: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hh, mm, ss, tzinfo=KST)


def _snapshot(db: Any) -> dict[str, dict[str, dict[str, Any]]]:
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for table, keys in TABLES.items():
        rows = {}
        for r in db.all(f"SELECT * FROM {table}"):
            row = dict(r)
            if table == "live_state":
                row["state"] = json.loads(row["state"])
            if table == "meta" and row["k"].startswith("cal."):
                continue  # 달력 캐시는 요청 목록(toss)에 보여요
            rows["|".join(str(row[k]) for k in keys)] = row
        out[table] = rows
    return out


def _diff(before: dict[str, dict[str, dict[str, Any]]], after: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for table in TABLES:
        b, a = before.get(table, {}), after.get(table, {})
        added = [mask_values(a[k]) for k in a if k not in b]
        removed = [k for k in b if k not in a]
        changed = []
        for k in a:
            if k in b and a[k] != b[k]:
                fields = {col: [b[k].get(col), a[k][col]] for col in a[k] if a[k][col] != b[k].get(col)}
                changed.append({"key": k, "fields": mask_values(fields)})
        if added or removed or changed:
            entry: dict[str, Any] = {}
            if added:
                entry["added"] = added
            if changed:
                entry["changed"] = changed
            if removed:
                entry["removed"] = removed
            out[table] = entry
    return out


class Sim:
    """한 날의 모의 세계: World + 스케줄러 + 기록."""

    def __init__(self, tmp: Path, *, calendar: Any = None) -> None:
        self.w = World(tmp, today=DAY)
        if calendar is not None:
            self.w.server.calendar = calendar
        sim_epoch = lambda: self.w.clock.t.timestamp()  # noqa: E731
        self.w.market.clock = sim_epoch  # 일봉 캐시 30분 규칙도 모의 시각으로
        self.w.client.wall_clock = sim_epoch  # 토큰 만료도 모의 시각으로
        self.w.client.limiter = RateLimiter(clock=sim_epoch, sleep=lambda s: None)  # 요청 한도 대기는 잠자지 않음
        self.w.clock.t = _at(MON, 21, 0)
        self.rid = running(self.w, body(sell=[R("stop_loss", value=7, exec_="intraday")]))
        self.events: list[dict[str, Any]] = []
        self.first_lap = True
        self.n_toss = len(self.w.server.calls)
        self.n_sent = len(self.w.sent)
        self.snap = _snapshot(self.w.db)
        self.sched = self._scheduler(self.w.live)
        self.events.append(self._event("start", {"note": "월요일 21:00 실전 시작(R-L11 · 20:10 뒤라 바로 확인)"}))

    def _scheduler(self, live: Live) -> Scheduler:
        sched = Scheduler(self.w.db, self.w.market.calendar, self.w.clock)
        paper2 = PaperV2(self.w.db, self.w.market, now=self.w.clock)
        sched.add("paper_check", 20, 10, paper2.tick)

        def live_check() -> None:
            r = live.run()
            if r is not None:
                live.check(int(r["id"]))

        sched.add("live_check", 20, 10, live_check)
        self.paper2 = paper2
        return sched

    def restart(self) -> None:
        """앱을 다시 켠 것처럼 Live · 스케줄러를 새로 만들어요(상태는 DB에 · 시계는 그대로)."""
        w = self.w
        w.live = Live(w.db, w.market, lambda: w.client, now=w.clock, notify=lambda e, t: w.sent.append((e, t)),
                      info=lambda: {SYM: {"name": f"종목{SYM[-2:]}"}}, dps=lambda sym: w.dps.get(sym))
        self.sched = self._scheduler(w.live)
        self.first_lap = True

    def _event(self, kind: str, extra: dict[str, Any]) -> dict[str, Any]:
        now = self.w.clock.t
        toss = [f"{m} {p}" for m, p in self.w.server.calls[self.n_toss:]]
        sent = [{"event": e, "text": t} for e, t in self.w.sent[self.n_sent:]]
        self.n_toss, self.n_sent = len(self.w.server.calls), len(self.w.sent)
        snap = _snapshot(self.w.db)
        db = _diff(self.snap, snap)
        self.snap = snap
        ev: dict[str, Any] = {"t": now.strftime("%H:%M:%S"), "kind": kind, **extra}
        if toss:
            ev["toss"] = toss
        if sent:
            ev["telegram"] = sent
        if db:
            ev["db"] = db
        return ev

    def lap(self) -> None:
        extra: dict[str, Any] = {"sched": [], "tick": []}
        try:  # `main._auto_loop`처럼 예외는 삼키고 30초 뒤 다시(기록에는 종류만)
            if self.first_lap:
                self.first_lap = False
                extra["first_lap_paper_tick"] = self.paper2.tick()
            extra["sched"] = self.sched.run_due()
            extra["tick"] = tick(self.w.live)
        except Exception as exc:
            extra["error"] = type(exc).__name__
        ev = self._event("lap", extra)
        if any(k in ev for k in ("toss", "telegram", "db", "error", "first_lap_paper_tick")) or ev["sched"] or ev["tick"]:
            self.events.append(ev)

    def hook(self, name: str, fn: Any) -> None:
        fn()
        self.events.append(self._event("hook", {"hook": name}))

    # ── 시험 세계를 움직이는 손(가짜 토스 상태) ─────────────────────────────

    def fill_open(self, side: str, price: str) -> None:
        for o in self.w.orders():
            if o["side"] == side and o["status"] in ("sent", "partial") and o["toss_order_id"]:
                self.w.server.fill(o["toss_order_id"], str(o["qty"]), price)
                if side == "buy":
                    self.w.holding(o["symbol"], o["qty"], float(price))
                else:
                    self.w.server.holdings.pop(o["symbol"], None)

    def set_price(self, price: str) -> None:
        self.w.server.prices[SYM] = price

    def close_bar(self) -> None:
        """15:30: 그날 일봉을 가짜 토스에 더해요(20:10 확인이 그날 종가를 보게)."""
        price = float(self.w.server.prices[SYM])
        bars = self.w.server.bars[SYM]
        bars.append({"d": DAY.isoformat(), "o": 10_000.0, "h": max(10_000.0, price), "l": min(10_000.0, price),
                     "c": price, "v": 1_000_000})


def run_day(name: str, tmp: Path) -> dict[str, Any]:
    hooks: dict[datetime, list[tuple[str, Any]]] = {}

    def at(hh: int, mm: int, ss: int, label: str, fn: Any) -> None:
        hooks.setdefault(_at(DAY, hh, mm, ss), []).append((label, fn))

    start = _at(DAY, 0, 0)
    off: tuple[datetime, datetime] | None = None
    calendar = None
    if name == "late_open":
        calendar = lambda d: (regular_day(d, open_at=(10, 0)) if d == DAY  # noqa: E731
                              else (regular_day(d) if d.weekday() < 5 else holiday(d)))
    if name == "start_0855":
        start = _at(DAY, 8, 55)
    if name == "restart_intraday":
        off = (_at(DAY, 9, 30, 30), _at(DAY, 12, 59, 30))

    sim = Sim(tmp, calendar=calendar)
    s = sim
    if name == "normal":
        at(9, 0, 0, "09:00 시가 매수 체결(10,000원)", lambda: s.fill_open("buy", "10000"))
        at(11, 0, 0, "11:00 현재가 9,200원(−8%)", lambda: s.set_price("9200"))
        at(11, 7, 0, "11:07 장중 매도 체결(9,150원)", lambda: s.fill_open("sell", "9150"))
        at(15, 30, 0, "15:30 그날 일봉 확정", s.close_bar)
    elif name == "precheck_fail_recover":
        at(8, 25, 0, "08:25 허용 IP 막힘(08:20 대조 뒤)", lambda: setattr(s.w.server, "ip_allowed", False))
        at(8, 38, 0, "08:38 허용 IP 복구", lambda: setattr(s.w.server, "ip_allowed", True))
        at(9, 0, 0, "09:00 시가 매수 체결(10,000원)", lambda: s.fill_open("buy", "10000"))
        at(15, 30, 0, "15:30 그날 일봉 확정", s.close_bar)
    elif name == "precheck_exhausted":
        at(8, 25, 0, "08:25 허용 IP 막힘(08:20 대조 뒤)", lambda: setattr(s.w.server, "ip_allowed", False))
        at(9, 30, 0, "09:30 허용 IP 복구(창이 끝난 뒤 · 그날 주문 없음)", lambda: setattr(s.w.server, "ip_allowed", True))
        at(15, 30, 0, "15:30 그날 일봉 확정", s.close_bar)
    elif name == "late_open":
        at(10, 0, 0, "10:00 시가 매수 체결(10,000원)", lambda: s.fill_open("buy", "10000"))
        at(12, 0, 0, "12:00 현재가 9,200원(−8%)", lambda: s.set_price("9200"))
        at(12, 7, 0, "12:07 장중 매도 체결(9,150원)", lambda: s.fill_open("sell", "9150"))
        at(16, 30, 0, "16:30 그날 일봉 확정(1시간 늦음)", s.close_bar)
    elif name == "start_0855":
        at(15, 30, 0, "15:30 그날 일봉 확정", s.close_bar)
    elif name == "restart_intraday":
        at(9, 0, 0, "09:00 시가 매수 체결(10,000원)", lambda: s.fill_open("buy", "10000"))
        at(12, 0, 0, "12:00 현재가 9,200원(−8%) · 앱은 꺼져 있음", lambda: s.set_price("9200"))
        at(13, 0, 0, "13:00 앱을 다시 켬", s.restart)
        at(13, 7, 0, "13:07 장중 매도 체결(9,150원)", lambda: s.fill_open("sell", "9150"))
        at(15, 30, 0, "15:30 그날 일봉 확정", s.close_bar)

    t = start
    end = _at(DAY, 23, 59, 30)
    laps = 0
    while t <= end:
        sim.w.clock.t = t
        for label, fn in hooks.get(t, []):
            sim.hook(label, fn)
        if off is None or not (off[0] <= t <= off[1]):
            sim.lap()
            laps += 1
        t += STEP
    return {"scenario": name, "line": SCENARIO_LINES[name], "day": DAY.isoformat(), "step_seconds": 30,
            "loop_from": start.strftime("%H:%M:%S"), "off": [x.strftime("%H:%M:%S") for x in off] if off else None,
            "laps": laps, "events": sim.events, "summary": summarize(sim.events)}


def summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    ticks: dict[str, list[str]] = {}
    sched: dict[str, list[str]] = {}
    prechecks = []
    for ev in events:
        for name in ev.get("tick", []):
            ticks.setdefault(name, []).append(ev["t"])
        for name in ev.get("sched", []):
            sched.setdefault(name, []).append(ev["t"])
        for m in ev.get("telegram", []):
            if m["event"] == "precheck":
                prechecks.append({"t": ev["t"], "text": m["text"]})
    intraday = ticks.get("intraday", [])
    return {
        "events": len(events),
        "tick_counts": {k: len(v) for k, v in sorted(ticks.items())},
        "tick_first_last": {k: [v[0], v[-1]] for k, v in sorted(ticks.items())},
        "precheck_times": ticks.get("precheck", []),
        "precheck_messages": prechecks,
        "intraday_minutes": len(intraday),
        "sched": sched,
        "telegram": sum(len(ev.get("telegram", [])) for ev in events),
        "toss_calls": sum(len(ev.get("toss", [])) for ev in events),
    }


def run_all() -> dict[str, Any]:
    out = {}
    with tempfile.TemporaryDirectory(prefix="quant-baseline-dayflow-") as d:
        for name in SCENARIOS:
            out[name] = run_day(name, Path(d) / name)
    return out


if __name__ == "__main__":
    import sys

    from tests.baseline.clock import freeze_plain

    freeze_plain()
    res = run_all()
    for name, day in res.items():
        print(name, day["laps"], "laps", json.dumps(day["summary"], ensure_ascii=False))
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
