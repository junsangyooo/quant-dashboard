"""T-60 ~ T-63 실전 운용(가짜 토스로만): SPEC 11-2 '실전(가짜 토스)' · ENGINE-RULES 5 · 6 · 7절 시험 예.

토스는 `tests/fake_toss.py`의 가짜 서버예요(OpenAPI 1.2.28 꼴 검사 · 바깥으로 나가지 않음). 계좌번호 · 키는 지어낸 값.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.store.db import DB
from app.domain.markets.kr import KST, lower_limit, ticks_below
from app.domain.rules import buy_cap, sell_floor
from app.live import Live, LiveError
from app.run.data import Market
from app.adapters.toss import TossClient, TossCredentials, TossSource
from app.adapters.transport import HttpRequest, HttpResponse, TransportError
from tests.conftest import make_bars
from tests.fake_toss import ACCOUNT_NO, CLIENT_ID, CLIENT_SECRET, FakeTossServer, holiday, regular_day, stock_row
from tests.test_blocks import B, G, R

SYM, SYM2 = "005930", "000660"
MON = date(2026, 11, 2)


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t

    def at(self, d: date, hh: int, mm: int = 0) -> None:
        self.t = datetime(d.year, d.month, d.day, hh, mm, tzinfo=KST)


def body(sell: list[dict[str, Any]] | None = None, syms: list[str] | None = None, top: int = 1) -> dict[str, Any]:
    g = G([B("u", "universe", [R("manual_list", value=syms or [SYM])]), B("s", "signal", [R("price", "gte", 1)]),
           B("k", "select", [R("top_n", value=top)]), B("b", "buy"),
           B("x", "sell", sell or [R("max_hold", value=50)]), B("w", "weight")],
          ("u", "s"), ("s", "k"), ("k", "b"), ("b", "x"), ("w", "b"))
    return {"name": "실전", "graph": g}


class World:
    def __init__(self, tmp_path: Path, *, closes: dict[str, list[float]] | None = None, today: date = MON,
                 cash: str = "100000000") -> None:
        self.server = s = FakeTossServer()
        closes = closes or {SYM: [10_000.0] * 60}
        start = today - timedelta(days=98)  # 70거래일 → 바로 전 거래일까지
        s.bars = {k: make_bars([v[0]] * (70 - len(v)) + v, start=start) for k, v in closes.items()}
        last = {k: v[-1]["d"] for k, v in s.bars.items()}
        self.last_d = max(last.values())
        s.index_bars = {"KOSPI": make_bars([2500.0] * 70, start=start)}
        s.stocks = {k: stock_row(k, f"종목{k[-2:]}") for k in closes}
        s.prices = {k: str(v[-1]) for k, v in closes.items()}
        s.cash = cash
        s.today = today
        self.flaky: list[str] = []  # 'lost' = 토스는 받았지만 응답이 끊김 · 'drop' = 보내기 전에 끊김
        self.client = TossClient(TossCredentials(CLIENT_ID, CLIENT_SECRET, ACCOUNT_NO), transport=self.transport)
        self.db = DB(tmp_path / "live.db")
        self.market = Market(self.db, TossSource(lambda: self.client))
        self.clock = Clock(datetime(today.year, today.month, today.day, 21, 0, tzinfo=KST))
        self.sent: list[tuple[str, str]] = []
        self.dps: dict[str, float] = {}
        self.live = Live(self.db, self.market, lambda: self.client, now=self.clock,
                         notify=lambda e, t: self.sent.append((e, t)),
                         info=lambda: {k: {"name": f"종목{k[-2:]}"} for k in closes},
                         dps=lambda sym: self.dps.get(sym))

    def transport(self, req: HttpRequest) -> HttpResponse:
        if self.flaky and req.method == "POST" and req.url.endswith("/api/v1/orders"):
            how = self.flaky.pop(0)
            if how == "lost":
                self.server(req)
                raise TransportError("lost")
            if how == "drop":
                raise TransportError("drop")
        return self.server(req)

    def version(self, b: dict[str, Any], backtested: bool = True) -> int:
        sid = self.db.run("INSERT INTO strategies(name,template,source,created_at) VALUES(?,?,?,?)",
                          ("실전", "event", None, "t"))
        vid = self.db.run("INSERT INTO versions(strategy_id,no,body,problems,created_at,format) VALUES(?,?,?,?,?,?)",
                          (sid, 1, json.dumps(b), 0, "t", "blocks"))
        if backtested:
            self.db.run("INSERT INTO backtest_runs(version_id,ran_at,start_d,end_d,cash) VALUES(?,?,?,?,?)",
                        (vid, "t", "2021-01-04", "2026-10-30", 10_000_000))
        return vid

    def orders(self) -> list[dict[str, Any]]:
        return [dict(o) for o in self.db.all("SELECT * FROM orders ORDER BY id")]

    def todos(self) -> list[tuple[str, str | None]]:
        return [(t["kind"], t["symbol"]) for t in self.db.all("SELECT * FROM todos WHERE status='open' ORDER BY id")]

    def holding(self, sym: str, qty: int, avg: float, sellable: int | None = None) -> None:
        self.server.holdings[sym] = {"quantity": str(qty), "avg": str(avg), "sellable": str(sellable or qty)}


def running(w: World, b: dict[str, Any] | None = None, amount: float = 10_000_000) -> int:
    vid = w.version(b or body())
    return w.live.start(vid, amount)


def morning(w: World, d: date) -> list[dict[str, Any]]:
    """다음 거래일 08:30 점검 → 08:35 주문."""
    rid = int(w.live.run()["id"])
    w.server.today = d
    w.clock.at(d, 8, 30)
    assert w.live.precheck(rid)
    w.clock.at(d, 8, 35)
    return w.live.open_orders(rid)


def give_pos(w: World, rid: int, sym: str, qty: int, avg: float, peak: float | None = None) -> None:
    st = w.live.state(rid)
    st["pos"][sym] = {"qty": qty, "avg": avg, "entry_d": "2026-10-01", "peak": peak or avg}
    w.live.save(rid, st)
    w.holding(sym, qty, avg)


# ── T-60 하루 흐름 ──────────────────────────────────────────────────────────


def test_day_flow_buy_size_cap_and_fill(tmp_path: Path) -> None:
    """R-L11 → 계획 → 08:30 점검 → 08:35 시가 지정가(상한 = 종가 × 1.1 내림 · 수량 = ⌊목표 ÷ 상한⌋) → 체결 대조."""
    w = World(tmp_path)
    rid = running(w)  # 월 21:00 시작 = 20:10 뒤 → 바로 확인(R-L11)
    nxt = w.live.state(rid)["next"]
    assert nxt["for_d"] == "2026-11-03" and [p["side"] for p in nxt["plans"]] == ["buy"]
    assert ("check_done", "확인 끝 · 내일 주문 1건") in w.sent
    out = morning(w, date(2026, 11, 3))
    o = w.orders()[0]
    cap = buy_cap(10_000)
    assert cap == 11_000 and o["price"] == 11_000 and o["qty"] == int(nxt["plans"][0]["value"] // cap)
    assert o["client_order_id"] == f"q{rid}-20261103-{SYM}-B-1" and o["round"] == 1
    assert out[0]["status"] == "sent" and w.server.spec_errors == []
    body_sent = [b for m, p, b in w.server.bodies if p == "/api/v1/orders"][0]
    assert body_sent["orderType"] == "LIMIT" and body_sent["price"] == "11000"
    assert ("precheck", "장 시작 전 점검 · 통과 · 08:35 주문 1건") in w.sent
    # 09:00 체결
    toss_id = o["toss_order_id"]
    w.server.fill(toss_id, str(o["qty"]), "10100")
    w.clock.at(date(2026, 11, 3), 9, 1)
    w.live.after_open(rid)
    st = w.live.state(rid)
    assert st["pos"][SYM]["qty"] == o["qty"] and w.orders()[0]["status"] == "filled"
    assert st["cash"] == pytest.approx(10_000_000 - o["qty"] * 10_100 * (1 + 0.00015))
    assert ("fills", "실전 · 체결 1건 · 앱에서 보기") in w.sent


def test_cash_binds_buy_quantity(tmp_path: Path) -> None:
    """묶이는 돈 ≤ 운용 현금(R-O3)."""
    w = World(tmp_path)
    rid = running(w, amount=500_000)
    st = w.live.state(rid)
    st["next"]["plans"] = [{"sym": SYM, "side": "buy", "value": 1_000_000, "close": 10_000.0, "reason": []}]
    w.live.save(rid, st)
    morning(w, date(2026, 11, 3))
    o = w.orders()[0]
    assert o["qty"] * o["price"] * (1 + 0.00015) <= 500_000 and o["qty"] == 45


def test_protect_sell_has_no_floor_normal_sell_has_floor(tmp_path: Path) -> None:
    """R-O4 · R-O5: 보호 매도 = 하한가 지정가(사실상 시가) · 일반 매도 = 종가 × 0.9 올림."""
    w = World(tmp_path)
    rid = running(w)
    give_pos(w, rid, SYM, 20, 10_000)
    st = w.live.state(rid)
    st["next"] = {"judged": "2026-11-02", "for_d": "2026-11-03", "plans": [
        {"sym": SYM, "side": "sell", "qty": 20, "kind": "protect", "close": 10_000.0, "reason": ["손절"]}]}
    w.live.save(rid, st)
    morning(w, date(2026, 11, 3))
    assert w.orders()[-1]["price"] == lower_limit(10_000) == 7_000
    w2 = World(tmp_path / "b")
    rid2 = running(w2)
    give_pos(w2, rid2, SYM, 20, 10_000)
    st = w2.live.state(rid2)
    st["next"] = {"judged": "2026-11-02", "for_d": "2026-11-03", "plans": [
        {"sym": SYM, "side": "sell", "qty": 20, "kind": "normal", "close": 10_000.0, "reason": ["최대 보유"]}]}
    w2.live.save(rid2, st)
    morning(w2, date(2026, 11, 3))
    assert w2.orders()[-1]["price"] == sell_floor(10_000) == 9_000


def test_huge_and_too_big_orders_become_todos(tmp_path: Path) -> None:
    """R-O9: 1억 이상 → 할 일 · R-O8: 주문 하나 2,000만 넘음 → 할 일 · 둘 다 보내지 않아요."""
    w = World(tmp_path, cash="500000000")
    rid = running(w, amount=300_000_000)
    st = w.live.state(rid)
    st["next"]["plans"] = [{"sym": SYM, "side": "buy", "value": 120_000_000, "close": 10_000.0, "reason": []}]
    w.live.save(rid, st)
    morning(w, date(2026, 11, 3))
    assert w.orders() == [] and ("huge", SYM) in w.todos()
    w2 = World(tmp_path / "b", cash="500000000")
    rid2 = running(w2, amount=100_000_000)
    st = w2.live.state(rid2)
    st["next"]["plans"] = [{"sym": SYM, "side": "buy", "value": 30_000_000, "close": 10_000.0, "reason": []}]
    w2.live.save(rid2, st)
    morning(w2, date(2026, 11, 3))
    assert w2.orders() == [] and ("too_big", SYM) in w2.todos()


def test_missed_days_keep_only_sells(tmp_path: Path) -> None:
    """R-L1: 3거래일 꺼짐 → 지난 날 매수 0 · 매도 신호만 다음 시가."""
    closes = [10_000.0] * 60
    w = World(tmp_path, closes={SYM: closes, SYM2: closes}, today=date(2026, 11, 6))
    vid = w.version(body(sell=[R("max_hold", value=1)], syms=[SYM, SYM2], top=2))
    w.clock.at(date(2026, 10, 30), 15, 0)  # 금요일 20:10 전 시작 · 첫 확인은 그날 20:10
    rid = w.live.start(vid, 10_000_000)
    w.live.set_meta(rid, "last_check", "2026-10-30")
    give_pos(w, rid, SYM, 10, 10_000)
    w.clock.at(date(2026, 11, 5), 21, 0)  # 월 · 화 · 수 · 목을 놓치고 목 21:00에 켬
    res = w.live.check(rid)
    sides = sorted((p["side"], p["sym"]) for p in res["plans"])
    assert ("sell", SYM) in sides
    assert res["for_d"] == "2026-11-06"


def test_first_check_on_holiday(tmp_path: Path) -> None:
    """R-L11: 휴장일 20:30 시작 → 마지막 거래일 종가로 바로 확인 → 다음 거래일 08:35 주문."""
    w = World(tmp_path)
    w.server.calendar = lambda d: holiday(d) if d == date(2026, 11, 3) or d.weekday() >= 5 else regular_day(d)
    w.clock.at(date(2026, 11, 3), 20, 30)
    rid = running(w)
    nxt = w.live.state(rid)["next"]
    assert nxt["judged"] == "2026-11-02" and nxt["for_d"] == "2026-11-04"


def test_precheck_fail_then_pass_and_late_open(tmp_path: Path) -> None:
    """R-L3: 08:30 점검 실패 → 주문 0 · 08:40 통과 → 그때 보내요. R-L2: 08:50 뒤 켜지면 시가 주문 건너뜀 + 할 일."""
    w = World(tmp_path)
    rid = running(w)
    d = date(2026, 11, 3)
    w.server.today = d
    w.server.ip_allowed = False
    w.clock.at(d, 8, 30)
    assert w.live.precheck(rid) is False
    w.clock.at(d, 8, 35)
    assert w.live.open_orders(rid) == [] and w.orders() == []
    assert ("precheck", None) in w.todos()
    assert any(t.startswith("장 시작 전 점검 · 실패") for _, t in w.sent)
    w.server.ip_allowed = True
    w.clock.at(d, 8, 40)
    assert w.live.precheck(rid)
    assert w.live.open_orders(rid)[0]["status"] == "sent"
    w2 = World(tmp_path / "b")
    rid2 = running(w2)
    w2.server.today = d
    w2.clock.at(d, 9, 10)
    w2.live.precheck(rid2)
    assert w2.live.open_orders(rid2) == [] and ("missed_open", None) in w2.todos()


def test_late_open_day_shifts(tmp_path: Path) -> None:
    """개장이 1시간 늦은 날: 09:40에도 시가 주문을 보내요(08:50 → 09:50)."""
    w = World(tmp_path)
    w.server.calendar = lambda d: regular_day(d, open_at=(10, 0)) if d == date(2026, 11, 3) else (
        regular_day(d) if d.weekday() < 5 else holiday(d))
    rid = running(w)
    d = date(2026, 11, 3)
    w.server.today = d
    w.clock.at(d, 9, 30)
    assert w.live.precheck(rid)
    w.clock.at(d, 9, 40)
    assert w.live.open_orders(rid)[0]["status"] == "sent"


def test_intraday_stop_widens_to_market(tmp_path: Path) -> None:
    """R-X5 · R-O6: 현재가 −7.1% → −2호가 지정가 → 3분 뒤 −5호가 → 3분 뒤 시장가."""
    w = World(tmp_path)
    rid = running(w, body(sell=[R("stop_loss", value=7, exec_="intraday")]))
    give_pos(w, rid, SYM, 10, 10_000)
    d = date(2026, 11, 3)
    w.server.today = d
    w.server.prices[SYM] = "9290"
    w.clock.at(d, 10, 0)
    out = w.live.intraday_tick(rid)
    assert out and out[0]["status"] == "sent"
    o = w.orders()[-1]
    assert o["kind"] == "intraday_protect" and o["price"] == ticks_below(9290, 2) == 9270
    w.clock.at(d, 10, 3)
    assert w.live.widen(rid) == [o["id"]]
    assert w.orders()[-1]["price"] == ticks_below(9290, 5)
    w.clock.at(d, 10, 6)
    w.live.widen(rid)
    body_last = [b for m, p, b in w.server.bodies if p.endswith("/modify")][-1]
    assert body_last["orderType"] == "MARKET"


def test_intraday_take_profit_never_below_floor(tmp_path: Path) -> None:
    w = World(tmp_path)
    rid = running(w, body(sell=[R("take_profit", value=10, exec_="intraday")]))
    give_pos(w, rid, SYM, 10, 9_000)
    d = date(2026, 11, 3)
    w.server.today = d
    w.server.prices[SYM] = "9910"
    w.clock.at(d, 10, 0)
    w.live.intraday_tick(rid)
    o = w.orders()[-1]
    assert o["kind"] == "intraday_take"
    w.server.prices[SYM] = "8800"  # 하한(전날 종가 10,000 × 0.9 = 9,000) 아래로
    w.clock.at(d, 10, 3)
    w.live.widen(rid)
    assert w.orders()[-1]["price"] == 9_000
    w.clock.at(d, 10, 7)
    assert w.live.widen(rid) == []  # 시장가 단계는 없어요


def test_cond_orders_oco_cancel_first_renew_and_trigger(tmp_path: Path) -> None:
    """R-X6 OCO 하나 · R-X7 취소가 매도보다 먼저 · R-X8 30일 전 다시 · R-X9 발동 16분 뒤 미체결 → 취소 + 보호 매도."""
    w = World(tmp_path)
    b = body(sell=[R("stop_loss", value=7, exec_="broker")])
    b["graph"]["blocks"].append(B("y", "sell", [R("take_profit", value=20, exec_="broker")]))
    b["graph"]["edges"].append({"from": "b", "to": "y"})
    rid = running(w, b)
    give_pos(w, rid, SYM, 10, 10_000)
    d = date(2026, 11, 3)
    w.server.today = d
    w.clock.at(d, 9, 1)
    assert len(w.live.place_conds(rid)) == 1
    c = list(w.server.conds.values())[0]
    assert c["type"] == "OCO" and c["first"]["triggerPrice"] == "9300" and c["second"]["triggerPrice"] == "12000"
    assert c["first"]["orderPrice"] == str(int(9300 * 0.97 // 10 * 10))
    assert w.live.place_conds(rid) == []  # 바뀐 것 없으면 그대로
    # 만료 29일 남음 → 다시 걸기
    w.db.run("UPDATE cond_orders SET expire=? WHERE run_id=?", ((d + timedelta(days=29)).isoformat(), rid))
    assert len(w.live.place_conds(rid)) == 1
    # 발동(ORDERED) 뒤 16분 동안 체결 없음 → 취소 + 보호 매도
    cid = w.db.one("SELECT toss_cond_id FROM cond_orders WHERE status='watching'")["toss_cond_id"]
    w.server.conds[cid]["first"]["status"] = "ORDERED"
    w.clock.at(d, 10, 0)
    w.live.watch_conds(rid)
    w.clock.at(d, 10, 16)
    assert w.live.watch_conds(rid) == [SYM]
    assert w.server.conds[cid]["status"] == "EXPIRED"
    w.server.prices[SYM] = "9200"
    calls_before = len(w.server.calls)
    w.live.intraday_tick(rid)
    assert w.orders()[-1]["kind"] == "intraday_protect"
    assert ("POST", "/api/v1/orders") in w.server.calls[calls_before:]


def test_single_cond_and_cancel_before_intraday_sell(tmp_path: Path) -> None:
    w = World(tmp_path)
    b = body(sell=[R("stop_loss", value=7, exec_="broker")])
    b["graph"]["blocks"].append(B("y", "sell", [R("trailing_stop", value=5, exec_="intraday")]))
    b["graph"]["edges"].append({"from": "b", "to": "y"})
    rid = running(w, b)
    give_pos(w, rid, SYM, 10, 10_000, peak=11_000)
    d = date(2026, 11, 3)
    w.server.today = d
    w.clock.at(d, 9, 1)
    w.live.place_conds(rid)
    assert list(w.server.conds.values())[0]["type"] == "SINGLE"
    w.server.prices[SYM] = "10400"  # 최고가 11,000 × 0.95 = 10,450 아래 → 트레일링(장중) 발동
    n = len(w.server.calls)
    w.live.intraday_tick(rid)
    calls = [c for c in w.server.calls[n:] if c[0] in ("DELETE", "POST")]
    assert calls[0][0] == "DELETE" and calls[0][1].startswith("/api/v1/conditional-orders/")
    assert calls[-1] == ("POST", "/api/v1/orders")


# ── T-61 결과 모름 · 거부 · 일부 체결 · 응답 이상 ────────────────────────────


def test_unknown_result_found_in_history(tmp_path: Path) -> None:
    """응답이 끊겼지만 토스가 받은 주문 → 내역에서 찾아 기록(중복 주문 0)."""
    w = World(tmp_path)
    rid = running(w)
    w.flaky = ["lost"]
    morning(w, date(2026, 11, 3))
    assert len(w.server.orders) == 1
    o = w.orders()[0]
    assert o["status"] == "sent" and o["toss_order_id"] == "ord-1" and o["round"] == 1
    assert w.todos() == []
    del rid


def test_unknown_result_retries_with_next_round_then_todo(tmp_path: Path) -> None:
    """내역에 없음 → 회차 2로 다시 · 둘 다 모름 → 그 종목 새 주문 0 + 할 일 1."""
    w = World(tmp_path)
    rid = running(w)
    w.flaky = ["drop"]
    morning(w, date(2026, 11, 3))
    rounds = [(o["round"], o["status"]) for o in w.orders()]
    assert rounds == [(1, "absent"), (2, "sent")]
    assert w.orders()[1]["client_order_id"].endswith("-B-2")
    w2 = World(tmp_path / "b")
    rid2 = running(w2)
    w2.flaky = ["drop", "drop"]
    morning(w2, date(2026, 11, 3))
    assert [o["status"] for o in w2.orders()] == ["absent", "unknown"]
    assert w2.todos() == [("unknown", SYM)]
    assert w2.live.state(rid2)["blocked"][SYM] == "결과 모르는 주문"
    # 그 종목 새 주문 0: 다음 날 계획이 있어도 보내지 않아요
    st = w2.live.state(rid2)
    st["next"] = {"judged": "2026-11-03", "for_d": "2026-11-04", "plans": [
        {"sym": SYM, "side": "buy", "value": 1_000_000, "close": 10_000.0, "reason": []}]}
    w2.live.save(rid2, st)
    out = morning(w2, date(2026, 11, 4))
    assert out == [{"sym": SYM, "skip": "결과 모르는 주문"}]
    # 사람이 '주문이 없어요' → 풀려요
    w2.live.resolve_unknown(rid2, w2.orders()[1]["id"])
    assert SYM not in w2.live.state(rid2)["blocked"] and w2.todos() == []
    del rid


def test_partial_fill_cancels_rest(tmp_path: Path) -> None:
    """17주 중 10주 체결 → 기록 '일부 체결 10/17주' · 7주 취소."""
    w = World(tmp_path)
    rid = running(w)
    st = w.live.state(rid)
    st["next"]["plans"] = [{"sym": SYM, "side": "buy", "value": 17 * 11_000, "close": 10_000.0, "reason": []}]
    w.live.save(rid, st)
    morning(w, date(2026, 11, 3))
    o = w.orders()[0]
    assert o["qty"] == 17
    w.server.fill(o["toss_order_id"], "10", "10050")
    w.clock.at(date(2026, 11, 3), 9, 2)
    w.live.after_open(rid)
    o = w.orders()[0]
    assert o["status"] == "partial_closed" and json.loads(o["reason"])["note"] == "일부 체결 10/17주"
    assert w.server.orders[o["toss_order_id"]]["status"] == "CANCELED"
    assert w.live.state(rid)["pos"][SYM]["qty"] == 10


def test_rejected_orders(tmp_path: Path) -> None:
    """거부된 매수는 그날 안 사요 · 보호 매도는 장중 다시 내기 · 같은 매도가 이틀 실패하면 할 일."""
    w = World(tmp_path)
    rid = running(w)
    morning(w, date(2026, 11, 3))
    o = w.orders()[0]
    w.server.orders[o["toss_order_id"]]["status"] = "REJECTED"
    w.live.sync_fills(rid)
    assert w.orders()[0]["status"] == "failed" and len(w.orders()) == 1
    assert ("order_failed", "실전 · 주문 실패 1건 · 앱에서 보기") in w.sent
    give_pos(w, rid, SYM, 10, 10_000)
    for d in (date(2026, 11, 4), date(2026, 11, 5)):
        st = w.live.state(rid)
        st["next"] = {"judged": "x", "for_d": d.isoformat(), "plans": [
            {"sym": SYM, "side": "sell", "qty": 10, "kind": "protect", "close": 10_000.0, "reason": ["손절"]}]}
        w.live.save(rid, st)
        morning(w, d)
        w.server.orders[w.orders()[-1]["toss_order_id"]]["status"] = "REJECTED"
        w.live.sync_fills(rid)
    assert ("sell_fail2", SYM) in w.todos()
    assert w.live.state(rid)["retry_protect"][SYM] is True


def test_price_anomaly_skips_symbol_and_shape_halts(tmp_path: Path) -> None:
    """R-O14: 가격 0 · ±30% 초과 → 그 종목 0 · 응답 꼴이 다르면 전체 멈춤."""
    w = World(tmp_path)
    rid = running(w, body(sell=[R("stop_loss", value=7, exec_="intraday")]))
    give_pos(w, rid, SYM, 10, 10_000)
    d = date(2026, 11, 3)
    w.server.today = d
    w.clock.at(d, 10, 0)
    w.server.prices[SYM] = "0"
    assert w.live.intraday_tick(rid) == []
    w.server.prices[SYM] = "6000"  # −40%
    assert w.live.intraday_tick(rid) == []
    w.server.prices[SYM] = "9000"
    w.server.mangle["/api/v1/prices"] = lambda p: {"result": {"oops": True}}
    assert w.live.intraday_tick(rid) == []
    assert w.live.halted == "응답 이상" and ("shape", None) in w.todos()
    assert w.orders() == []


# ── T-62 대조 · 배당 · 기업 행동 ─────────────────────────────────────────────


def test_account_less_than_app_is_mismatch_and_manual_never_traded(tmp_path: Path) -> None:
    """계좌 수량 < 앱 수량 → 불일치 · 주문 0. 직접 관리 종목은 사지도 팔지도 않아요(판 적 0)."""
    w = World(tmp_path, closes={SYM: [10_000.0] * 60, SYM2: [20_000.0] * 60})
    w.holding(SYM2, 5, 18_000)  # 시작 전부터 있던 보유 → 직접 관리 종목
    rid = running(w)
    assert w.live.state(rid)["manual"] == [SYM2]
    give_pos(w, rid, SYM, 10, 10_000)
    w.holding(SYM, 8, 10_000)
    st = w.live.state(rid)
    st["next"] = {"judged": "x", "for_d": "2026-11-03", "plans": [
        {"sym": SYM, "side": "sell", "qty": 10, "kind": "normal", "close": 10_000.0, "reason": []},
        {"sym": SYM2, "side": "sell", "qty": 5, "kind": "protect", "close": 20_000.0, "reason": []},
        {"sym": SYM2, "side": "buy", "value": 1_000_000, "close": 20_000.0, "reason": []}]}
    w.live.save(rid, st)
    morning(w, date(2026, 11, 3))
    assert w.orders() == [] or all(o["symbol"] != SYM2 for o in w.orders())
    assert all(o["symbol"] != SYM for o in w.orders()) and ("mismatch", SYM) in w.todos()
    assert not [b for m, p, b in w.server.bodies if p == "/api/v1/orders" and b["symbol"] == SYM2]
    rec = w.live.reconcile(rid)
    assert rec["mismatch"] == [SYM]


def test_corp_action_split(tmp_path: Path) -> None:
    """1:5 분할 → 그 종목 0 + 할 일 · 사람이 맞추면 수량 ×5 · 단가 ÷5 · 조건주문 다시."""
    w = World(tmp_path)
    rid = running(w, body(sell=[R("stop_loss", value=7, exec_="broker")]))
    give_pos(w, rid, SYM, 10, 10_000)
    w.clock.at(date(2026, 11, 3), 9, 1)
    w.server.today = date(2026, 11, 3)
    w.live.place_conds(rid)
    w.holding(SYM, 50, 2_000)
    rec = w.live.reconcile(rid)
    assert rec["corp"] == [SYM] and ("corp", SYM) in w.todos()
    assert w.live.state(rid)["blocked"][SYM] == "권리 변동"
    w.live.apply_corp(rid, SYM)
    p = w.live.state(rid)["pos"][SYM]
    assert p["qty"] == 50 and p["avg"] == pytest.approx(2_000)
    watching = w.db.all("SELECT * FROM cond_orders WHERE status='watching'")
    assert len(watching) == 1 and watching[0]["qty"] == 50 and watching[0]["stop_trigger"] == 1_860


def test_dividend_and_cash_cut(tmp_path: Path) -> None:
    """100주 × 1,000원 배당 → 운용 현금 +84,600원(R-L7) · 운용 현금 > 계좌 현금 → 깎고 정보 할 일."""
    w = World(tmp_path, cash="20000000")
    rid = running(w)
    give_pos(w, rid, SYM, 100, 10_000)
    w.dps[SYM] = 1_000
    w.live.reconcile(rid)  # 처음: 계좌 현금 기록
    before = w.live.state(rid)["cash"]
    w.server.cash = str(20_000_000 + 84_600)
    rec = w.live.reconcile(rid)
    assert rec["dividend"] == pytest.approx(84_600) and w.live.state(rid)["cash"] == pytest.approx(before + 84_600)
    w.server.cash = "1000000"
    rec = w.live.reconcile(rid)
    assert rec["cut"] > 0 and w.live.state(rid)["cash"] == 1_000_000 and ("cash_cut", None) in w.todos()


def test_unknown_order_number_halts(tmp_path: Path) -> None:
    """기록에 없는 주문이 있으면 주문 0 + 할 일(R-L6)."""
    w = World(tmp_path)
    rid = running(w)
    give_pos(w, rid, SYM, 10, 10_000)
    w.client.create_order(symbol=SYM, side="SELL", quantity=3, price=9_000, client_order_id="someone-else")
    rec = w.live.reconcile(rid)
    assert rec["unknown_orders"] == 1 and w.live.halted and ("unknown_order_no", None) in w.todos()


def test_daily_loss_blocks_next_day_buys(tmp_path: Path) -> None:
    """하루 손실 −3.1%(운용 자산 기준) → 다음 거래일 새 매수 0 · 매도 계속(R-O8 · 엔진 규칙 층)."""
    closes = [10_000.0] * 59 + [9_690.0]
    w = World(tmp_path, closes={SYM: closes, SYM2: [10_000.0] * 60})
    vid = w.version(body(syms=[SYM, SYM2], top=2))
    w.clock.at(date(2026, 10, 30), 21, 0)
    rid = w.live.start(vid, 1_000_000)
    st = w.live.state(rid)
    st["cash"] = 0.0
    st["pos"] = {SYM: {"qty": 100, "avg": 10_000, "entry_d": "2026-10-01", "peak": 10_000}}
    w.live.save(rid, st)
    w.clock.at(date(2026, 11, 2), 21, 0)
    res = w.live.check(rid)
    assert [p for p in res["plans"] if p["side"] == "buy"] == []


# ── T-63 멈추기 셋 · 전략 변경 · 계좌번호 ────────────────────────────────────


def test_pause_new_buys(tmp_path: Path) -> None:
    w = World(tmp_path)
    rid = running(w)
    morning(w, date(2026, 11, 3))
    assert w.live.pause_new_buys("telegram") is True
    assert w.orders()[0]["status"] == "canceled"
    assert w.server.orders[w.orders()[0]["toss_order_id"]]["status"] == "CANCELED"
    assert w.live.pause_new_buys() is False
    w.clock.at(date(2026, 11, 3), 21, 0)
    w.live.set_meta(rid, "last_check", None)
    res = w.live.check(rid)
    assert [p for p in res["plans"] if p["side"] == "buy"] == []


def test_end_keeps_holdings_and_cancels_conds(tmp_path: Path) -> None:
    w = World(tmp_path)
    rid = running(w, body(sell=[R("stop_loss", value=7, exec_="broker")]))
    give_pos(w, rid, SYM, 10, 10_000)
    w.clock.at(date(2026, 11, 3), 9, 1)
    w.server.today = date(2026, 11, 3)
    w.live.place_conds(rid)
    w.live.end(rid)
    assert all(c["status"] == "EXPIRED" for c in w.server.conds.values())
    assert w.live.run(rid)["status"] == "ended" and SYM in w.live.state(rid)["manual"]
    assert w.live.run() is None


def test_sell_all_in_session_and_after_close(tmp_path: Path) -> None:
    """장중이면 바로 보호 매도 길 · 장 밖이면 다음 거래일 08:35 시가(하한 없음) · 불일치 종목은 팔지 않아요."""
    w = World(tmp_path, closes={SYM: [10_000.0] * 60, SYM2: [20_000.0] * 60})
    rid = running(w, body(syms=[SYM, SYM2], top=2))
    give_pos(w, rid, SYM, 10, 10_000)
    give_pos(w, rid, SYM2, 4, 20_000)
    w.holding(SYM2, 3, 20_000)  # 계좌 3 < 앱 4
    d = date(2026, 11, 3)
    w.server.today = d
    w.clock.at(d, 11, 0)
    out = w.live.sell_all_and_end(rid)
    assert {o.get("sym"): o.get("status") or o.get("skip") for o in out} == {SYM: "sent", SYM2: "계좌 불일치"}
    assert w.orders()[-1]["kind"] == "stop_all"
    w2 = World(tmp_path / "b")
    rid2 = running(w2)
    give_pos(w2, rid2, SYM, 10, 10_000)
    w2.clock.at(d, 18, 0)
    out = w2.live.sell_all_and_end(rid2)
    assert out == [{"sym": SYM, "planned": "2026-11-04"}]
    morning(w2, date(2026, 11, 4))
    assert w2.orders()[-1]["price"] == lower_limit(10_000)


def test_change_strategy_and_account_lock(tmp_path: Path) -> None:
    w = World(tmp_path)
    rid = running(w, body(sell=[R("stop_loss", value=7, exec_="broker")]))
    give_pos(w, rid, SYM, 10, 10_000)
    w.clock.at(date(2026, 11, 3), 9, 1)
    w.server.today = date(2026, 11, 3)
    w.live.place_conds(rid)
    nb = w.version(body(sell=[R("stop_loss", value=5, exec_="broker")]), backtested=False)
    with pytest.raises(LiveError):
        w.live.change_strategy(rid, nb)
    nb2 = w.version(body(sell=[R("stop_loss", value=5, exec_="broker")]))
    assert w.live.change_strategy(rid, nb2) == "2026-11-03"
    watching = w.db.all("SELECT * FROM cond_orders WHERE status='watching'")
    assert len(watching) == 1 and watching[0]["stop_trigger"] == 9_500  # 새 규칙으로 다시 걸었어요
    with pytest.raises(LiveError) as e:
        w.live.check_account_change("98765432109")
    assert e.value.status == 409
    w.live.check_account_change(ACCOUNT_NO)  # 같은 계좌는 괜찮아요


def test_start_guards(tmp_path: Path) -> None:
    w = World(tmp_path, cash="1000000")
    vid = w.version(body(), backtested=False)
    with pytest.raises(LiveError, match="백테스트"):
        w.live.start(vid, 500_000)
    vid = w.version(body())
    with pytest.raises(LiveError, match="매수 가능 금액"):
        w.live.start(vid, 5_000_000)
    w.live.start(vid, 500_000)
    with pytest.raises(LiveError) as e:
        w.live.start(vid, 500_000)
    assert e.value.status == 409


def test_no_real_transport_used(tmp_path: Path) -> None:
    w = World(tmp_path)
    running(w)
    morning(w, date(2026, 11, 3))
    assert w.server.spec_errors == []


def test_tick_runs_the_day_in_order(tmp_path: Path) -> None:
    """앱 루프(30초): 08:20 대조 → 08:30 점검 → 08:35 주문 → 09:01 체결 대조 · 미체결 취소 → 장중 1분마다."""
    from app.live import tick

    w = World(tmp_path)
    running(w, body(sell=[R("stop_loss", value=7, exec_="intraday")]))
    d = date(2026, 11, 3)
    w.server.today = d
    w.clock.at(d, 8, 25)
    assert tick(w.live) == ["reconcile"]
    w.clock.at(d, 8, 30)
    assert tick(w.live) == ["precheck"]
    w.clock.at(d, 8, 35)
    assert tick(w.live) == ["open"] and len(w.orders()) == 1
    w.server.fill(w.orders()[0]["toss_order_id"], str(w.orders()[0]["qty"]), "10000")
    w.holding(SYM, w.orders()[0]["qty"], 10_000)
    w.clock.at(d, 9, 1)
    assert tick(w.live) == ["after_open", "intraday"]
    assert w.live.state(int(w.live.run()["id"]))["pos"][SYM]["qty"] == w.orders()[0]["qty"]
    assert tick(w.live) == []  # 같은 1분에는 한 번
    w.server.prices[SYM] = "9200"  # −8% → 장중 손절
    w.clock.at(d, 9, 2)
    assert tick(w.live) == ["intraday"] and w.orders()[-1]["kind"] == "intraday_protect"
    w.clock.at(date(2026, 11, 7), 10, 0)  # 토요일: 아무것도
    assert tick(w.live) == []


def test_forty_orders_sells_first_then_buy_rank() -> None:
    """R-O9: 매도 10 + 매수 후보 35 → 매수 30건만(순위 순) · 나머지 '매수 안 함 · 하루 주문 40건'."""
    from app.domain.engine import Engine
    from app.domain.indicators import Series
    from app.domain.rules import RuleLayer

    eng = Engine(body(), {SYM: Series(make_bars([10_000.0] * 5))}, 10_000_000, rules=RuleLayer(amount=10_000_000))
    new = ([{"sym": f"S{i}", "side": "sell", "qty": 1} for i in range(10)]
           + [{"sym": f"B{i}", "side": "buy", "value": 1, "rank": i + 1} for i in range(35)])
    out = eng._apply_day_limits("2026-11-02", 10_000_000, new)
    assert [p["side"] for p in out].count("sell") == 10
    assert [p["sym"] for p in out if p["side"] == "buy"] == [f"B{i}" for i in range(30)]
    assert {s["why"] for s in eng.skipped} == {"매수 안 함 · 하루 주문 40건"} and len(eng.skipped) == 5


def test_screen_view(tmp_path: Path) -> None:
    w = World(tmp_path)
    rid = running(w, body(sell=[R("stop_loss", value=7, exec_="intraday")]))
    sc = w.live.screen()
    assert sc["running"] and sc["strategy"]["version_no"] == 1 and sc["account"]["cash"] == 100_000_000
    row = sc["plan_rows"][0]
    assert row["side"] == "buy" and row["cap"] == 11_000 and row["max"] == row["qty"] * 11_000
    morning(w, date(2026, 11, 3))
    o = w.orders()[0]
    w.server.fill(o["toss_order_id"], str(o["qty"]), "10000")
    w.clock.at(date(2026, 11, 3), 9, 1)
    w.live.after_open(rid)
    sc = w.live.screen()
    assert sc["recent"][0]["side"] == "buy" and sc["holdings"][0]["sym"] == SYM
    assert sc["watch"][0]["levels"][0]["item"] == "stop_loss" and sc["history"][0]["status"] == "체결"
