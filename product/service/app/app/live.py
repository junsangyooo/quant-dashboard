"""실전 운용 하루 흐름(T-60 ~ T-63 · ENGINE-RULES 5 · 6 · 7절 · SPEC 5절). **가짜 토스로만 시험해요.**

- 20:10 확인(R-O1): 놓친 거래일은 하루씩 다시 돌려 매도 신호만 남기고(R-L1), 마지막 거래일 계획이 다음 거래일 시가 주문.
  시작 직후 첫 확인(R-L11)도 여기로.
- 08:30 점검(R-L3) → 08:35 시가 단일가 주문(R-O3 · R-O5 · R-O8 · R-O9 · R-O10) → 체결 대조(R-O13) →
  장중 감시(R-X5 · R-O6) · 조건주문(R-X6 ~ R-X9).
- 결과 모르는 주문(R-O11 · R-O12) · 응답 이상(R-O14) · 대조 · 배당 · 기업 행동(R-L6 ~ R-L8) · 멈추기 셋(R-L9) ·
  전략 변경 · 계좌번호 잠금(R-L10).
- 엔진 상태(현금 · 보유 · 계획)는 `live_state`에 두고, 진짜 체결이 올 때만 바꿔요. 주문 · 체결 · 조건주문 · 할 일은 표에.
- 증권사는 `client()`가 주는 `Broker` 포트(`ports.py` · 조립이 토스 어댑터를 넣어 줌)만 써요(기본 가짜 · T-00). 이 파일은 소켓을 쓰지 않아요.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any

from .domain import blocks as bk
from .domain.catalog import CATALOG
from .domain.copytext import read_body
from .store import strategies as strategy_store
from .store.db import DB
from .domain.engine import FEE, PROTECT_ITEMS, SELL_TAX, Engine, MarketData, universe_of, warmup_calendar_days
from .domain.indicators import Series
from .domain.markets.kr import KST, complete_until, lower_limit, tick_round, ticks_below
from .domain.rules import ORDER_HUGE, RuleLayer, buy_cap, sell_floor
from .market import Market
from .ports import (
    Broker,
    BrokerBadAnswer,
    BrokerError,
    BrokerRejected,
    BrokerUnreachable,
    Clock,
    NoAnswer,
    Notifier,
)

DART_ITEMS = {i for i, it in CATALOG.items() if it.lock == "dart"}
RUNNING = "running"
ENDED = "ended"
CHECK_AT = time(20, 10)
PRECHECK_AT = (8, 30)
ORDER_AT = (8, 35)
LATE_OPEN = (8, 50)  # R-L2 · R-L3: 이 뒤로는 그날 시가 주문을 건너뛰어요
STEP_WAIT = timedelta(minutes=3)  # R-O6
TRIGGER_WAIT = timedelta(minutes=15)  # R-X9
COND_RENEW_DAYS = 30  # R-X8
COND_STOP_GAP = 0.03  # R-X6: 손절 지정가 = 감시가 −3%(가정)
LOOKUPS = 3  # R-O12: 2분 동안 3번

# 할 일 제목(SPEC 5-5 · 화면 · 텔레그램은 [종목] 뺌)
TODO = {
    # 빨강
    "precheck": ("red", "장 시작 전 점검 실패 · {why}"),
    "toss_down": ("red", "토스 연결이 끊겼어요"),
    "other_user": ("red", "다른 곳에서 같은 키를 쓰고 있어요"),
    "check_fail": ("red", "오늘 확인 실패"),
    "unknown": ("red", "결과 모르는 주문 · [{name}]"),
    "mismatch": ("red", "계좌 불일치 · [{name}]"),
    "corp": ("red", "권리 변동 · [{name}]"),
    "shape": ("red", "토스 응답이 예상과 달라요"),
    "sell_fail2": ("red", "안 팔린 종목 · [{name}]"),
    "unknown_order_no": ("red", "모르는 주문 번호가 있어요"),
    # 노랑
    "missed_open": ("yellow", "시가 주문을 놓쳤어요 · 앱이 꺼져 있었어요"),
    "loss_limit": ("yellow", "하루 손실 한도 · 내일 새 매수 멈춤"),
    "huge": ("yellow", "큰 주문 확인 · [{name}] [{amount}]"),
    "too_big": ("yellow", "큰 주문 확인 · [{name}] [{amount}]"),
    "cond_fail": ("yellow", "조건주문 다시 걸기 실패 · [{name}]"),
    "dart_error": ("yellow", "DART 연결 오류"),
    "cash_cut": ("yellow", "운용 현금이 줄었어요(출금)"),
}
# SPEC 5-6 '막히는 범위'
SCOPE = {
    "precheck": "그날 주문 0", "toss_down": "실전 주문 전부 0 · 장중 감시도 멈춤", "other_user": "실전 주문 전부 0",
    "check_fail": "다음 거래일 새 매수 0", "unknown": "그 종목 새 주문 0", "mismatch": "그 종목 0",
    "corp": "그 종목 0", "shape": "실전 주문 전부 0 · 장중 감시도 멈춤", "missed_open": "그날 매수 0",
    "loss_limit": "다음 거래일 매수 0", "huge": "그 주문", "too_big": "그 주문",
    "dart_error": "재무 조건이 든 전략의 새 매수 0",
}


class LiveError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _iso(dt: datetime) -> str:
    return dt.astimezone(KST).isoformat(timespec="seconds")


class Live:
    def __init__(self, db: DB, market: Market, client: Callable[[], Broker | None], *,
                 now: Clock, notify: Notifier | None = None,
                 info: Callable[[], dict[str, dict[str, Any]]] | None = None,
                 dps: Callable[[str], float | None] | None = None) -> None:
        self.db = db
        self.market = market
        self.client = client
        self.now = now
        self.notify = notify or (lambda event, text: None)
        self.info = info or (lambda: {})
        self.dps = dps or (lambda sym: None)  # DART 주당 배당금(R-L7)

    # ── 읽기 · 쓰기 ─────────────────────────────────────────────────────────

    def run(self, rid: int | None = None) -> Any:
        if rid is None:
            return self.db.one("SELECT * FROM runs WHERE status=? ORDER BY id DESC LIMIT 1", (RUNNING,))
        r = self.db.one("SELECT * FROM runs WHERE id=?", (rid,))
        if r is None:
            raise LiveError("그 실전 운용이 없어요", 404)
        return r

    def state(self, rid: int) -> dict[str, Any]:
        row = self.db.one("SELECT state FROM live_state WHERE run_id=?", (rid,))
        st = json.loads(row["state"]) if row else {}
        st.setdefault("manual", [])  # 직접 관리 종목(R-O10)
        st["blocked"] = json.loads(self.meta(rid, "blocked") or "{}")  # 그 종목 주문 0(결과 모름 · 불일치 · 권리 변동)
        st.setdefault("next", None)  # 다음 거래일 시가 계획 {for_d, plans}
        st.setdefault("sell_fail", {})
        return st

    def block(self, rid: int, sym: str, why: str) -> None:
        """그 종목 주문 0. 상태 저장과 따로 둬서(meta) 한 흐름 안에서 덮어쓰이지 않아요."""
        b = json.loads(self.meta(rid, "blocked") or "{}")
        b[sym] = why
        self.set_meta(rid, "blocked", json.dumps(b, ensure_ascii=False))

    def unblock(self, rid: int, sym: str) -> None:
        b = json.loads(self.meta(rid, "blocked") or "{}")
        b.pop(sym, None)
        self.set_meta(rid, "blocked", json.dumps(b, ensure_ascii=False) if b else None)

    def save(self, rid: int, st: dict[str, Any]) -> None:
        keep = {k: v for k, v in st.items() if k != "blocked"}
        self.db.run("INSERT INTO live_state(run_id,state,updated_at) VALUES(?,?,?) ON CONFLICT(run_id) DO UPDATE "
                    "SET state=excluded.state, updated_at=excluded.updated_at",
                    (rid, json.dumps(keep, ensure_ascii=False), _iso(self.now())))
        self.db.run("DELETE FROM positions WHERE run_id=?", (rid,))
        for sym, p in st.get("pos", {}).items():
            self.db.run("INSERT INTO positions(run_id,symbol,qty,avg_price,first_d,peak) VALUES(?,?,?,?,?,?)",
                        (rid, sym, int(p["qty"]), float(p["avg"]), p.get("entry_d"), p.get("peak")))

    def meta(self, rid: int, key: str) -> str | None:
        return self.db.get_meta(f"live.{rid}.{key}")

    def set_meta(self, rid: int, key: str, value: str | None) -> None:
        self.db.set_meta(f"live.{rid}.{key}", value)

    @property
    def paused(self) -> bool:
        return self.db.get_meta("live.new_buys_paused") == "1"

    def todo(self, rid: int | None, kind: str, symbol: str | None = None, body: str = "",
             data: dict[str, Any] | None = None) -> int:
        """같은 종류 · 종목의 열린 할 일이 있으면 그대로 둬요."""
        open_ = self.db.one("SELECT id FROM todos WHERE kind=? AND IFNULL(symbol,'')=? AND status='open'",
                            (kind, symbol or ""))
        if open_:
            return int(open_["id"])
        sev, title = TODO[kind]
        name = self.info().get(symbol or "", {}).get("name") or symbol or ""
        d = data or {}
        amount = f"{round(float(d['qty']) * float(d['cap'])):,}원" if "qty" in d and "cap" in d else ""
        text = title.format(name=name, why=body or "원인 모름", amount=amount)
        tid = self.db.run("INSERT INTO todos(run_id,kind,severity,symbol,title,body,data,status,created_at) "
                          "VALUES(?,?,?,?,?,?,?, 'open', ?)",
                          (rid, kind, sev, symbol, text, SCOPE.get(kind, body),
                           json.dumps(d, ensure_ascii=False), _iso(self.now())))
        plain = re.sub(r"\s*·?\s*\[[^\]]*\]", "", text).strip()  # 텔레그램은 [종목] · [금액]을 빼요
        self.notify("todo_red" if sev == "red" else "todo_yellow", f"{plain} · 앱에서 보기")
        return tid

    # ── 엔진 ────────────────────────────────────────────────────────────────

    def _body(self, version_id: int) -> dict[str, Any]:
        v = strategy_store.version_body(self.db, version_id)
        if v is None:
            raise LiveError("그 버전이 없어요", 404)
        return read_body(json.loads(v["body"]))

    def engine(self, r: Any, upto: date, *, extra_bar: dict[str, dict[str, float]] | None = None) -> Engine:
        body = self._body(int(r["version_id"]))
        info = self.info()
        syms = sorted(set(universe_of(body, info)) | set(self.state(int(r["id"])).get("pos", {})))
        warm = upto - timedelta(days=warmup_calendar_days(body) + 10)
        entries = [p.get("entry_d") for p in self.state(int(r["id"])).get("pos", {}).values() if p.get("entry_d")]
        if entries:  # 보유 기간 · 최고가는 산 날부터 셈해요
            warm = min(warm, date.fromisoformat(min(entries)) - timedelta(days=5))
        bars = self.market.many(syms, warm, upto)
        if extra_bar:  # 장중 감시: 오늘 막대(현재가) 하나를 붙여 엔진 규칙 그대로 판정
            for sym, b in extra_bar.items():
                bars[sym] = [*(bars.get(sym) or []), b]
        data = MarketData(series={s: Series(b) for s, b in bars.items() if b}, info=info, live=True)
        st = self.state(int(r["id"]))
        eng_state = {k: st[k] for k in ("cash", "pos", "plans", "day_no", "sold", "loss_block_d", "unsettled", "last_equity")
                     if k in st}
        cal = sorted({d for s in data.series.values() for d in s.d})
        settings = json.loads(r["settings"] or "{}")
        rules = RuleLayer(amount=float(r["amount"]), **{k: settings[k] for k in
                                                        ("daily_loss", "per_stock", "order_max") if k in settings})
        return Engine(body, data, float(st.get("cash", r["amount"])), state=eng_state or None, calendar=cal,
                      rules=rules)

    # ── 시작(V2-30 · R-L11) ────────────────────────────────────────────────

    def start(self, version_id: int, amount: float, *, settings: dict[str, Any] | None = None) -> int:
        if self.run() is not None:
            raise LiveError("이미 실전 운용 중이에요 · 하나만 운용해요", 409)
        v = strategy_store.version(self.db, version_id)
        if v is None:
            raise LiveError("그 버전이 없어요", 404)
        if not strategy_store.was_backtested(self.db, version_id):
            raise LiveError("이 버전으로 백테스트를 안 했어요 · 이 앱에서 백테스트한 버전만 운용해요")
        body = self._body(version_id)
        if bk.analyze(body["graph"])["problems"]:
            raise LiveError("문제가 있는 버전은 운용할 수 없어요")
        c = self._need()
        power = float(c.buying_power())
        if amount > power:
            raise LiveError("운용 금액이 토스 매수 가능 금액보다 커요")
        acc = c.credentials.account_no or ""
        now = self.now()
        rid = self.db.run("INSERT INTO runs(strategy_id,version_id,status,amount,settings,account_tail,started_at) "
                          "VALUES(?,?,?,?,?,?,?)", (v["strategy_id"], version_id, RUNNING, float(amount),
                                                    json.dumps(settings or {}), acc[-4:], _iso(now)))
        self.db.run("INSERT INTO run_versions(run_id,version_id,from_d) VALUES(?,?,?)",
                    (rid, version_id, now.astimezone(KST).date().isoformat()))
        self.db.run("INSERT INTO run_cash(run_id,d,kind,amount,ref,at) VALUES(?,?,?,?,?,?)",
                    (rid, now.astimezone(KST).date().isoformat(), "start", float(amount), None, _iso(now)))
        # 시작할 때 계좌에 있던 보유는 모두 직접 관리 종목(R-O10)
        manual = sorted(h.symbol for h in c.holdings())
        self.save(rid, {"cash": float(amount), "pos": {}, "plans": [], "day_no": 0, "sold": {}, "manual": manual,
                        "blocked": {}, "next": None, "sell_fail": {}})
        # R-L11: 거래일 20:10 뒤 · 휴장일이면 바로 마지막 완성 일봉으로 확인
        local = now.astimezone(KST)
        cal = self.market.calendar
        if not cal.is_open(local.date()) or local.time() >= CHECK_AT:
            self.check(rid)
        return rid

    def _need(self) -> Broker:
        c = self.client()
        if c is None:
            raise LiveError("토스 연결이 필요해요 · 시세와 계좌를 토스에서 받아요 · 연결 ›")
        return c

    # ── 20:10 확인(R-O1 · R-L1 · R-L4) ────────────────────────────────────

    def check(self, rid: int, *, now: datetime | None = None) -> dict[str, Any]:
        now = now or self.now()
        r = self.run(rid)
        if r["status"] != RUNNING:
            return {"plans": []}
        upto = complete_until(now - timedelta(minutes=10), self.market.calendar)
        last = self.meta(rid, "last_check")
        if last and last >= upto.isoformat():
            return {"plans": (self.state(rid).get("next") or {}).get("plans", [])}
        try:
            eng = self.engine(r, upto)
        except Exception as exc:  # R-L4: 다음 거래일 새 매수 0 · 10분마다 다시
            self.set_meta(rid, "check_failed", _iso(now))
            self.todo(rid, "check_fail", body=type(exc).__name__)
            raise
        st = self.state(rid)
        start_d = r["started_at"][:10]
        days = [d for d in eng.calendar if (last or "") < d <= upto.isoformat() and d >= _prev(start_d, eng.calendar)]
        if not days:
            days = [upto.isoformat()]
        sells: list[dict[str, Any]] = []
        latest: list[dict[str, Any]] = []
        for d in days:
            eng.state["plans"] = []
            plans = eng.judge(d)
            if d == days[-1]:
                latest = plans
            else:  # 지난 날 매수는 내지 않아요 · 매도 신호만(R-L1)
                sells += [p for p in plans if p["side"] == "sell"]
        merged = {p["sym"]: p for p in sells}
        for p in latest:  # 마지막 거래일: 매도는 덮어쓰고, 매수는 같은 종목 매도가 없을 때만
            if p["side"] == "sell" or p["sym"] not in merged:
                merged[p["sym"]] = p
        plans = [p for p in merged.values() if p["sym"] not in st["manual"]]
        if self.paused:  # 새 매수 멈춤
            plans = [p for p in plans if p["side"] == "sell"]
        for_d = self.market.calendar.next_open(upto).isoformat()
        if eng.state.get("loss_block_d") == upto.isoformat():
            self.todo(rid, "loss_limit")
        if self.db.get_meta("dart.error") and any(
                r_["item"] in DART_ITEMS for b_ in eng.c.graph["blocks"] for r_ in b_["rows"]):
            plans = [p for p in plans if p["side"] == "sell"]  # DART 연결 오류: 재무 조건 전략 새 매수 0
            self.todo(rid, "dart_error")
        st.update({k: eng.state[k] for k in ("day_no", "sold", "loss_block_d", "last_equity") if k in eng.state})
        st["plans"] = []
        st["next"] = {"judged": upto.isoformat(), "for_d": for_d, "plans": plans}
        self.save(rid, st)
        self.set_meta(rid, "last_check", upto.isoformat())
        self.set_meta(rid, "check_failed", None)
        self.db.run("INSERT INTO run_equity(run_id,d,equity,cash) VALUES(?,?,?,?) ON CONFLICT(run_id,d) DO UPDATE "
                    "SET equity=excluded.equity, cash=excluded.cash",
                    (rid, upto.isoformat(), eng.equity(upto.isoformat()), float(st["cash"])))
        self.notify("check_done", f"확인 끝 · 내일 주문 {len(plans)}건")
        return {"plans": plans, "for_d": for_d}

    # ── 08:30 점검(R-L3) ───────────────────────────────────────────────────

    def precheck(self, rid: int) -> bool:
        st = self.state(rid)
        nxt = st.get("next") or {}
        why = ""
        try:
            c = self._need()
            why = "토큰"
            c.token(force=True)
            why = "계좌"
            c.account(force=True)
            why = "잔고"
            c.buying_power()
            why = "미체결"
            opened, _ = c.orders("OPEN")
            mine = {o["toss_order_id"] for o in self.db.all("SELECT toss_order_id FROM orders WHERE run_id=?", (rid,))}
            strange = [o for o in opened if o.order_id not in mine]
            ok = True
            if strange and any(o.symbol in {p["sym"] for p in nxt.get("plans", [])} for o in strange):
                ok = False
        except BrokerRejected as exc:
            ok = False
            if exc.status == 403:
                why = "허용 IP"
            if why in ("토큰", "허용 IP"):  # 매도 주문도 못 내요 → 장중 감시도 멈춤(조건주문만)
                self.set_meta(rid, "watch_off", self.now().astimezone(KST).date().isoformat())
            if exc.status == 401 and why != "토큰":
                self.todo(rid, "other_user")
        except (BrokerError, LiveError, NoAnswer):
            ok = False
            if why == "토큰":
                self.set_meta(rid, "watch_off", self.now().astimezone(KST).date().isoformat())
                self.todo(rid, "toss_down")
        if ok:
            self.set_meta(rid, "watch_off", None)
            self.db.run("UPDATE todos SET status='resolved', resolved_at=? WHERE kind IN ('precheck','toss_down') "
                        "AND status='open'", (_iso(self.now()),))
        self.set_meta(rid, "precheck", json.dumps({"at": _iso(self.now()), "ok": ok}))
        n = len(nxt.get("plans", []))
        self.notify("precheck", f"장 시작 전 점검 · {'통과' if ok else '실패'} · "
                    + (f"08:35 주문 {n}건" if ok else "오늘 주문 멈춤 · 앱에서 보기"))
        if not ok:
            self.todo(rid, "precheck", body=why)
        return ok

    # ── 08:35 시가 주문(R-O3 · R-O5 · R-O8 · R-O9 · R-O10 · R-X7) ─────────

    def open_orders(self, rid: int) -> list[dict[str, Any]]:
        now = self.now().astimezone(KST)
        st = self.state(rid)
        nxt = st.get("next")
        if not nxt or nxt.get("sent"):
            return []
        today = now.date().isoformat()
        if nxt["for_d"] != today:
            return []
        day = self.market.calendar.day(now.date())
        if now > day.at(*LATE_OPEN):  # R-L2(개장이 늦은 날은 그만큼 늦춰요 · R-O1)
            nxt["sent"] = True
            self.save(rid, st)
            self.todo(rid, "missed_open")
            return []
        pre = json.loads(self.meta(rid, "precheck") or "{}")
        if not pre.get("ok") or pre.get("at", "")[:10] != today:
            return []  # 점검 통과 전에는 0(R-L3 · 5분마다 다시 점검)
        c = self._need()
        r = self.run(rid)
        out: list[dict[str, Any]] = []
        plans = nxt["plans"]
        sells = [p for p in plans if p["side"] == "sell"]
        buys = sorted([p for p in plans if p["side"] == "buy"], key=lambda p: p.get("rank") or 0)
        holdings = {h.symbol: h for h in c.holdings()}
        cash = float(st["cash"])
        for p in sells:
            out.append(self._open_sell(rid, st, c, p, holdings, today))
        check_failed = bool(self.meta(rid, "check_failed"))
        for p in buys:
            if check_failed:  # 오늘 확인 실패: 다음 거래일 새 매수 0(R-L4)
                out.append({"sym": p["sym"], "skip": "오늘 확인 실패"})
                continue
            if self.paused:
                out.append({"sym": p["sym"], "skip": "새 매수 멈춤"})
                continue
            res = self._open_buy(rid, st, c, p, cash, today, float(r["amount"]))
            if res.get("reserved"):
                cash -= res["reserved"]
            out.append(res)
        nxt["sent"] = True
        self.save(rid, st)
        return out

    def _cancel_conds(self, rid: int, c: Broker, sym: str) -> None:
        for co in self.db.all("SELECT * FROM cond_orders WHERE run_id=? AND symbol=? AND status='watching'",
                              (rid, sym)):
            c.cancel_conditional_order(co["toss_cond_id"])
            self.db.run("UPDATE cond_orders SET status='canceled' WHERE id=?", (co["id"],))

    def _open_sell(self, rid: int, st: dict[str, Any], c: Broker, p: dict[str, Any], holdings: dict[str, Any],
                   today: str) -> dict[str, Any]:
        sym = p["sym"]
        if sym in st["blocked"]:
            return {"sym": sym, "skip": st["blocked"][sym]}
        app_qty = int(st["pos"].get(sym, {}).get("qty", 0))
        acct = int(holdings[sym].qty) if sym in holdings else 0
        if acct < app_qty:  # R-O10 · 불일치: 팔지 않아요
            self.block(rid, sym, "계좌 불일치"); st["blocked"][sym] = "계좌 불일치"
            self.todo(rid, "mismatch", sym, data={"app": app_qty, "account": acct})
            return {"sym": sym, "skip": "계좌 불일치"}
        sellable = int(c.sellable_quantity(sym))
        qty = min(int(p["qty"]), app_qty, sellable)
        if qty <= 0:
            return {"sym": sym, "skip": "팔 수량 없음"}
        self._cancel_conds(rid, c, sym)  # R-X7
        close = float(p.get("close") or st["pos"][sym]["avg"])
        protect = p.get("kind") == "protect"
        price = lower_limit(close) if protect else sell_floor(close)
        return self._send(rid, today, sym, "SELL", qty, price, "open_sell_protect" if protect else "open_sell",
                          p.get("reason") or [])

    def _open_buy(self, rid: int, st: dict[str, Any], c: Broker, p: dict[str, Any], cash: float, today: str,
                  amount: float) -> dict[str, Any]:
        sym = p["sym"]
        if sym in st["blocked"] or sym in st["manual"]:
            return {"sym": sym, "skip": "직접 관리 종목" if sym in st["manual"] else st["blocked"][sym]}
        close = float(p["close"])
        cap = buy_cap(close)
        value = float(p["value"])
        qty = int(value // cap)  # R-O3: 수량 = ⌊목표 ÷ 상한⌋
        while qty > 0 and qty * cap * (1 + FEE) > cash:  # 묶이는 돈 ≤ 운용 현금
            qty -= 1
        if qty <= 0:
            return {"sym": sym, "skip": "운용 현금 부족"}
        order_value = qty * cap
        if order_value >= ORDER_HUGE:  # R-O9: 1억 이상은 나눠 내지 않고 할 일
            self.todo(rid, "huge", sym, data={"qty": qty, "cap": cap})
            return {"sym": sym, "skip": "큰 주문 · 할 일"}
        settings = json.loads(self.run(rid)["settings"] or "{}")
        if order_value > float(settings.get("order_max", 20_000_000)):  # R-O8 주문 크기 한도
            self.todo(rid, "too_big", sym, data={"qty": qty, "cap": cap})
            return {"sym": sym, "skip": "주문 크기 한도"}
        res = self._send(rid, today, sym, "BUY", qty, cap, "open_buy", p.get("reason") or [])
        res["reserved"] = order_value
        return res

    # ── 보내기 · 결과 모름(R-O11 · R-O12) ──────────────────────────────────

    def client_id(self, rid: int, d: str, sym: str, side: str, rnd: int) -> str:
        return f"q{rid}-{d.replace('-', '')}-{sym}-{side[0]}-{rnd}"

    def _send(self, rid: int, d: str, sym: str, side: str, qty: int, price: float | None, kind: str,
              reason: list[str], *, order_type: str = "LIMIT", rnd: int | None = None) -> dict[str, Any]:
        c = self._need()
        if rnd is None:
            last = self.db.one("SELECT MAX(round) AS r FROM orders WHERE run_id=? AND d=? AND symbol=? AND side=?",
                               (rid, d, sym, side.lower()))
            rnd = int(last["r"] or 0) + 1
        cid = self.client_id(rid, d, sym, side, rnd)
        oid = self.db.run("INSERT INTO orders(run_id,d,symbol,side,round,client_order_id,kind,qty,price,tif,status,"
                          "reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                          (rid, d, sym, side.lower(), rnd, cid, kind, qty, price, "DAY", "sending",
                           json.dumps({"why": reason, "step": 1}, ensure_ascii=False), _iso(self.now())))
        try:
            toss_id = c.create_order(symbol=sym, side=side, quantity=qty, order_type=order_type,
                                     price=None if order_type == "MARKET" else Decimal(str(int(price or 0))),
                                     client_order_id=cid)
        except BrokerBadAnswer:
            self._halt(rid, "응답 이상")
            self.db.run("UPDATE orders SET status='unknown' WHERE id=?", (oid,))
            return {"sym": sym, "status": "unknown", "order": oid}
        except (NoAnswer, BrokerUnreachable, BrokerRejected) as exc:
            if isinstance(exc, BrokerRejected) and exc.status < 500:
                self.db.run("UPDATE orders SET status='failed', updated_at=? WHERE id=?", (_iso(self.now()), oid))
                return {"sym": sym, "status": "failed", "order": oid}
            return self._unknown(rid, oid)
        self.db.run("UPDATE orders SET toss_order_id=?, status='sent', updated_at=? WHERE id=?",
                    (toss_id, _iso(self.now()), oid))
        return {"sym": sym, "status": "sent", "order": oid, "qty": qty, "price": price}

    def _find(self, c: Broker, o: Any) -> str | None:
        """같은 날 · 종목 · 방향 · 수량 · 가격의 토스 주문 가운데 이 앱 기록에 없는 것."""
        known = {x["toss_order_id"] for x in self.db.all("SELECT toss_order_id FROM orders WHERE toss_order_id "
                                                           "IS NOT NULL")}
        for status in ("OPEN", "CLOSED"):
            rows, _ = c.orders(status, symbol=o["symbol"])
            for t in rows:
                if (t.order_id not in known and t.side == o["side"].upper() and int(t.qty) == int(o["qty"])
                        and (o["price"] is None or t.price is None or float(t.price) == float(o["price"]))):
                    return t.order_id
        return None

    def _unknown(self, rid: int, oid: int) -> dict[str, Any]:
        """R-O12: 내역에서 3번 찾기 → 있으면 기록 · 없으면 회차 +1 · 그래도 모르면 그 종목 0 + 할 일."""
        o = self.db.one("SELECT * FROM orders WHERE id=?", (oid,))
        c = self._need()
        for _ in range(LOOKUPS):
            try:
                found = self._find(c, o)
            except (NoAnswer, BrokerError):
                continue
            if found:
                self.db.run("UPDATE orders SET toss_order_id=?, status='sent', updated_at=? WHERE id=?",
                            (found, _iso(self.now()), oid))
                return {"sym": o["symbol"], "status": "sent", "order": oid, "found": True}
            self.db.run("UPDATE orders SET status='absent', updated_at=? WHERE id=?", (_iso(self.now()), oid))
            if int(o["round"]) >= 2:
                break
            reason = json.loads(o["reason"] or "{}").get("why", [])
            return self._send(rid, o["d"], o["symbol"], o["side"].upper(), int(o["qty"]), o["price"], o["kind"],
                              reason, rnd=int(o["round"]) + 1)
        self.db.run("UPDATE orders SET status='unknown', updated_at=? WHERE id=?", (_iso(self.now()), oid))
        self.block(rid, o["symbol"], "결과 모르는 주문")
        self.todo(rid, "unknown", o["symbol"], data={"order": oid})
        return {"sym": o["symbol"], "status": "unknown", "order": oid}

    def resolve_unknown(self, rid: int, order_id: int, *, filled_qty: int = 0, price: float = 0.0) -> None:
        """사람이 정해요: '체결됐어요(수량 · 가격)' / '주문이 없어요'(비밀번호 · 결과 모르는 주문 기록)."""
        o = self.db.one("SELECT * FROM orders WHERE id=? AND run_id=?", (order_id, rid))
        if o is None or o["status"] != "unknown":
            raise LiveError("결과 모르는 주문이 아니에요")
        st = self.state(rid)
        if filled_qty > 0:
            self._apply_fill(rid, st, o, filled_qty, price, 0.0, 0.0, note="사람이 기록")
            self.db.run("UPDATE orders SET status='filled' WHERE id=?", (order_id,))
        else:
            self.db.run("UPDATE orders SET status='absent' WHERE id=?", (order_id,))
        self.unblock(rid, o["symbol"])
        self.save(rid, st)
        self.db.run("UPDATE todos SET status='resolved', resolved_at=? WHERE kind='unknown' AND symbol=? AND "
                    "status='open'", (_iso(self.now()), o["symbol"]))

    # ── 체결 대조(R-O13) ───────────────────────────────────────────────────

    def _apply_fill(self, rid: int, st: dict[str, Any], o: Any, qty: int, price: float, commission: float,
                    tax: float, *, note: str | None = None) -> None:
        if qty <= 0:
            return
        sym = o["symbol"]
        self.db.run("INSERT INTO fills(order_id,qty,price,commission,tax,filled_at,note) VALUES(?,?,?,?,?,?,?)",
                    (o["id"], qty, price, commission, tax, _iso(self.now()), note))
        cost = commission + tax
        if not commission and not tax:
            cost = qty * price * (FEE + (SELL_TAX if o["side"] == "sell" else 0))
        if o["side"] == "buy":
            p = st["pos"].get(sym, {"qty": 0, "avg": 0.0, "entry_d": o["d"], "peak": price})
            total = p["qty"] * p["avg"] + qty * price + cost
            p["qty"] += qty
            p["avg"] = total / p["qty"]
            p["peak"] = max(float(p.get("peak") or price), price)
            st["pos"][sym] = p
            st["cash"] = float(st["cash"]) - qty * price - cost
            self.db.run("INSERT INTO run_cash(run_id,d,kind,amount,ref,at) VALUES(?,?,?,?,?,?)",
                        (rid, o["d"], "buy", -(qty * price + cost), str(o["id"]), _iso(self.now())))
        else:
            p = st["pos"].get(sym)
            if p:
                p["qty"] -= qty
                if p["qty"] <= 0:
                    del st["pos"][sym]
                    st["sold"][sym] = o["d"]
            st["cash"] = float(st["cash"]) + qty * price - cost
            self.db.run("INSERT INTO run_cash(run_id,d,kind,amount,ref,at) VALUES(?,?,?,?,?,?)",
                        (rid, o["d"], "sell", qty * price - cost, str(o["id"]), _iso(self.now())))

    def sync_fills(self, rid: int) -> dict[str, int]:
        c = self._need()
        st = self.state(rid)
        done = {"filled": 0, "partial": 0, "failed": 0}
        for o in self.db.all("SELECT * FROM orders WHERE run_id=? AND status IN ('sent','partial')", (rid,)):
            try:
                t = c.order(o["toss_order_id"])
            except BrokerBadAnswer:
                self._halt(rid, "응답 이상")
                break
            except (NoAnswer, BrokerError):
                continue
            ex = t.execution
            filled = int(ex.filled_qty or 0)
            before = int(self.db.one("SELECT IFNULL(SUM(qty),0) AS q FROM fills WHERE order_id=?", (o["id"],))["q"])
            new_qty = filled - before
            if new_qty > 0:
                self._apply_fill(rid, st, o, new_qty, float(ex.avg_price or o["price"] or 0),
                                 float(ex.commission or 0) * new_qty / max(filled, 1),
                                 float(ex.tax or 0) * new_qty / max(filled, 1))
            if t.status == "FILLED":
                self.db.run("UPDATE orders SET status='filled', updated_at=? WHERE id=?", (_iso(self.now()), o["id"]))
                done["filled"] += 1
                if o["side"] == "sell":
                    st["sell_fail"].pop(o["symbol"], None)
            elif t.status in ("REJECTED", "CANCELED", "EXPIRED"):
                status = "partial" if filled else "failed"
                self.db.run("UPDATE orders SET status=?, updated_at=? WHERE id=?",
                            (f"{status}_closed" if filled else "failed", _iso(self.now()), o["id"]))
                done["failed"] += 1
                if o["side"] == "sell":
                    self._sell_failed(rid, st, o)
            elif t.status == "PARTIAL_FILLED":
                self.db.run("UPDATE orders SET status='partial', updated_at=? WHERE id=?",
                            (_iso(self.now()), o["id"]))
                done["partial"] += 1
        self.save(rid, st)
        if done["filled"] or done["partial"]:
            self.notify("fills", f"실전 · 체결 {done['filled'] + done['partial']}건 · 앱에서 보기")
        if done["failed"]:
            self.notify("order_failed", f"실전 · 주문 실패 {done['failed']}건 · 앱에서 보기")
        return done

    def _sell_failed(self, rid: int, st: dict[str, Any], o: Any) -> None:
        """보호 매도는 장중 다시 내기 길(R-O6), 일반 매도는 다음 확인. 같은 매도가 이틀 실패하면 할 일(R-O13)."""
        sym = o["symbol"]
        days = sorted(set(st["sell_fail"].get(sym, [])) | {o["d"]})
        st["sell_fail"][sym] = days
        if len(days) >= 2:
            self.todo(rid, "sell_fail2", sym)
        if o["kind"] in ("open_sell_protect", "intraday_protect", "stop_all"):
            st.setdefault("retry_protect", {})[sym] = True

    def after_open(self, rid: int) -> None:
        """09:00 체결 뒤: 미체결 매수 취소 · 일부 체결은 남은 매수 취소(R-O13)."""
        self.sync_fills(rid)
        c = self._need()
        today = self.now().astimezone(KST).date().isoformat()
        for o in self.db.all("SELECT * FROM orders WHERE run_id=? AND d=? AND side='buy' AND status IN "
                             "('sent','partial')", (rid, today)):
            try:
                c.cancel_order(o["toss_order_id"])
            except BrokerError:
                continue
            filled = int(self.db.one("SELECT IFNULL(SUM(qty),0) AS q FROM fills WHERE order_id=?", (o["id"],))["q"])
            note = f"일부 체결 {filled}/{o['qty']}주" if filled else "미체결 · 취소"
            reason = json.loads(o["reason"] or "{}")
            reason["note"] = note
            self.db.run("UPDATE orders SET status=?, reason=?, updated_at=? WHERE id=?",
                        ("partial_closed" if filled else "canceled", json.dumps(reason, ensure_ascii=False),
                         _iso(self.now()), o["id"]))
        self.place_conds(rid)

    # ── 응답 이상(R-O14) ──────────────────────────────────────────────────

    def _halt(self, rid: int, why: str) -> None:
        self.db.set_meta("live.halt", why)
        self.todo(rid, "shape", body=why)

    @property
    def halted(self) -> str | None:
        return self.db.get_meta("live.halt")

    # ── 장중 감시(R-X5 · R-O6) ─────────────────────────────────────────────

    def watch_levels(self, eng: Engine, sym: str) -> list[dict[str, Any]]:
        p = eng.pos.get(sym)
        if not p:
            return []
        out = []
        for block, k in eng.c.intraday:
            row = block["rows"][k]
            v = row.get("value")
            if v is None:
                continue
            v = float(v)
            ex = bk.exec_of(eng.c.graph, block["id"], k)
            if row["item"] == "stop_loss":
                out.append({"item": "stop_loss", "exec": ex, "trigger": p["avg"] * (1 - v / 100), "side": "down"})
            elif row["item"] == "trailing_stop":
                out.append({"item": "trailing_stop", "exec": ex,
                            "trigger": float(p.get("peak") or p["avg"]) * (1 - v / 100), "side": "down"})
            elif row["item"] == "take_profit":
                out.append({"item": "take_profit", "exec": ex, "trigger": p["avg"] * (1 + v / 100), "side": "up"})
        return out

    def intraday_tick(self, rid: int) -> list[dict[str, Any]]:
        """장중 1분마다: 현재가가 장중 감시 줄에 닿으면 장중 매도 길. 응답 이상 종목은 0, 꼴이 다르면 전체 멈춤."""
        if self.halted or self.meta(rid, "watch_off") == self.now().astimezone(KST).date().isoformat():
            return []  # 응답 이상 · 토큰 · 허용 IP 실패: 장중 감시 멈춤(조건주문만 동작)
        r = self.run(rid)
        st = self.state(rid)
        held = [s for s in st["pos"] if s not in st["blocked"]]
        if not held:
            return []
        c = self._need()
        today = self.now().astimezone(KST).date()
        try:
            eng = self.engine(r, today)
        except Exception:
            return []
        prev = {s: eng.data.series[s].close_on_or_before(today.isoformat()) for s in held if s in eng.data.series}
        try:
            checked = c.prices_checked(held, prev_close=prev)
        except BrokerBadAnswer:
            self._halt(rid, "응답 이상")
            return []
        out = []
        for sym in held:
            if sym in checked.anomalies:
                continue  # 그 종목 주문 0(R-O14)
            q = checked.items.get(sym)
            if q is None:
                continue
            price = float(q.price)
            pos = st["pos"][sym]
            pos["peak"] = max(float(pos.get("peak") or pos["avg"]), price)
            if self.db.one("SELECT 1 FROM orders WHERE run_id=? AND symbol=? AND side='sell' AND status IN "
                           "('sent','partial','sending')", (rid, sym)):
                continue
            hits = [w for w in self.watch_levels(eng, sym) if w["exec"] == "intraday" and (
                price <= w["trigger"] if w["side"] == "down" else price >= w["trigger"])]
            retry = st.get("retry_protect", {}).pop(sym, False)
            if not hits and not retry:
                continue
            stop = any(w["item"] in PROTECT_ITEMS for w in hits) or retry
            self._cancel_conds(rid, c, sym)  # R-X7: 취소가 매도보다 먼저
            qty = min(int(pos["qty"]), int(c.sellable_quantity(sym)))
            if qty <= 0:
                continue
            res = self._send(rid, today.isoformat(), sym, "SELL", qty, ticks_below(price, 2),
                             "intraday_protect" if stop else "intraday_take",
                             ["장중 감시 · " + ("손절" if stop else "익절")])
            out.append(res)
        self.save(rid, st)
        return out

    def widen(self, rid: int) -> list[int]:
        """R-O6: 3분 뒤 미체결이면 −5호가 → 3분 뒤 시장가(보호). 익절은 지정가 하한 아래로 안 내려가요."""
        c = self._need()
        now = self.now()
        moved = []
        for o in self.db.all("SELECT * FROM orders WHERE run_id=? AND kind IN ('intraday_protect','intraday_take',"
                             "'stop_all') AND status IN ('sent','partial')", (rid,)):
            last = datetime.fromisoformat(o["updated_at"] or o["created_at"])
            if now - last < STEP_WAIT:
                continue
            reason = json.loads(o["reason"] or "{}")
            step = int(reason.get("step", 1))
            q = c.prices([o["symbol"]]).get(o["symbol"])
            if q is None:
                continue
            price = float(q.price)
            if o["kind"] == "intraday_take":
                floor = sell_floor(float(self._prev_close(rid, o["symbol"]) or price))
                if step >= 2:
                    continue
                new_price = max(ticks_below(price, 5), floor)
                c.modify_order(o["toss_order_id"], order_type="LIMIT", price=Decimal(str(int(new_price))))
            elif step == 1:
                new_price = ticks_below(price, 5)
                c.modify_order(o["toss_order_id"], order_type="LIMIT", price=Decimal(str(int(new_price))))
            elif step == 2:
                new_price = None
                c.modify_order(o["toss_order_id"], order_type="MARKET")
            else:
                continue
            reason["step"] = step + 1
            self.db.run("UPDATE orders SET price=?, reason=?, updated_at=? WHERE id=?",
                        (new_price, json.dumps(reason, ensure_ascii=False), _iso(now), o["id"]))
            moved.append(int(o["id"]))
        return moved

    def _prev_close(self, rid: int, sym: str) -> float | None:
        today = self.now().astimezone(KST).date()
        bars = self.market.bars(sym, today - timedelta(days=10), today - timedelta(days=1))
        return float(bars[-1]["c"]) if bars else None

    # ── 조건주문(R-X6 ~ R-X9) ──────────────────────────────────────────────

    def place_conds(self, rid: int) -> list[str]:
        """'조건주문' 줄: 같은 종목 손절 + 익절이면 OCO 하나, 하나면 SINGLE. 수량이나 감시가가 바뀌면 다시 걸어요."""
        r = self.run(rid)
        st = self.state(rid)
        if not st["pos"]:
            return []
        c = self._need()
        today = self.now().astimezone(KST).date()
        eng = self.engine(r, today)
        made = []
        for sym, p in st["pos"].items():
            if sym in st["blocked"]:
                continue
            levels = [w for w in self.watch_levels(eng, sym) if w["exec"] == "broker"]
            stop = next((w["trigger"] for w in levels if w["item"] == "stop_loss"), None)
            take = next((w["trigger"] for w in levels if w["item"] == "take_profit"), None)
            cur = self.db.one("SELECT * FROM cond_orders WHERE run_id=? AND symbol=? AND status='watching'", (rid, sym))
            if stop is None and take is None:
                if cur:
                    self._cancel_conds(rid, c, sym)
                continue
            stop_t = tick_round(stop) if stop else None
            take_t = tick_round(take) if take else None
            renew = cur and cur["expire"] and date.fromisoformat(cur["expire"]) - today <= timedelta(days=COND_RENEW_DAYS)
            if cur and int(cur["qty"]) == int(p["qty"]) and cur["stop_trigger"] == stop_t and \
                    cur["take_trigger"] == take_t and not renew:
                continue
            if cur:
                self._cancel_conds(rid, c, sym)
            legs = []
            if stop_t:
                legs.append({"side": "SELL", "trigger": int(stop_t), "price": int(tick_round(stop_t * (1 - COND_STOP_GAP)))})
            if take_t:
                legs.append({"side": "SELL", "trigger": int(take_t), "price": int(take_t)})
            kind = "OCO" if len(legs) == 2 else "SINGLE"
            expire = today + timedelta(days=364)
            try:
                cid = c.create_conditional_order(symbol=sym, kind=kind, quantity=int(p["qty"]), expire=expire,
                                                 first=legs[0], second=legs[1] if len(legs) > 1 else None)
            except (BrokerError, NoAnswer):
                self.todo(rid, "cond_fail", sym)
                continue
            self.db.run("INSERT INTO cond_orders(run_id,symbol,toss_cond_id,kind,qty,stop_trigger,take_trigger,expire,"
                        "status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (rid, sym, cid, kind, int(p["qty"]), stop_t, take_t, expire.isoformat(), "watching",
                         _iso(self.now())))
            made.append(cid)
        return made

    def watch_conds(self, rid: int) -> list[str]:
        """R-X9: 발동 뒤 15분 안에 체결이 없으면 취소 + 보호 매도 길. 체결되면 기록."""
        c = self._need()
        st = self.state(rid)
        now = self.now()
        out = []
        for co in self.db.all("SELECT * FROM cond_orders WHERE run_id=? AND status IN ('watching','triggered')",
                              (rid,)):
            t = c.conditional_order(co["toss_cond_id"])
            legs = [x for x in (t.first, t.second) if x is not None]
            fired = [x for x in legs if x.status in ("ORDERING", "ORDERED", "COMPLETED")]
            if not fired:
                continue
            if co["status"] == "watching":
                self.db.run("UPDATE cond_orders SET status='triggered', triggered_at=? WHERE id=?", (_iso(now), co["id"]))
                co = self.db.one("SELECT * FROM cond_orders WHERE id=?", (co["id"],))
            leg = fired[0]
            filled = 0
            if leg.triggered_order_id:
                o = c.order(leg.triggered_order_id)
                filled = int(o.execution.filled_qty or 0)
                if filled:
                    oid = self.db.run(
                        "INSERT INTO orders(run_id,d,symbol,side,round,client_order_id,toss_order_id,kind,qty,price,tif,"
                        "status,reason,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rid, now.astimezone(KST).date().isoformat(), co["symbol"], "sell", 1,
                         f"cond-{co['toss_cond_id']}", leg.triggered_order_id, "cond", filled,
                         float(o.execution.avg_price or 0), "DAY", "filled",
                         json.dumps({"why": ["조건주문 체결"]}, ensure_ascii=False), _iso(now)))
                    row = self.db.one("SELECT * FROM orders WHERE id=?", (oid,))
                    self._apply_fill(rid, st, row, filled, float(o.execution.avg_price or 0), 0, 0)
                    self.db.run("UPDATE cond_orders SET status='filled' WHERE id=?", (co["id"],))
                    out.append(co["symbol"])
                    continue
            if now - datetime.fromisoformat(co["triggered_at"]) > TRIGGER_WAIT:
                c.cancel_conditional_order(co["toss_cond_id"])
                self.db.run("UPDATE cond_orders SET status='canceled' WHERE id=?", (co["id"],))
                st.setdefault("retry_protect", {})[co["symbol"]] = True
                out.append(co["symbol"])
        self.save(rid, st)
        return out

    # ── 대조 · 배당 · 기업 행동(R-L6 ~ R-L8) · 하루 손실 ────────────────────

    def reconcile(self, rid: int) -> dict[str, Any]:
        """켤 때 · 매일: 토스 보유 · 오늘 주문 · 현금을 이 앱 기록과 맞춰요."""
        c = self._need()
        st = self.state(rid)
        out: dict[str, Any] = {"mismatch": [], "corp": [], "unknown_orders": 0, "dividend": 0.0, "cut": 0.0}
        holdings = {h.symbol: h for h in c.holdings()}
        for sym, p in list(st["pos"].items()):
            acct = int(holdings[sym].qty) if sym in holdings else 0
            app = int(p["qty"])
            if acct == app:
                continue
            ratio = acct / app if app else 0
            if acct > app and ratio == int(ratio) and ratio >= 2:  # 분할 · 무상증자 꼴(R-L8)
                self.block(rid, sym, "권리 변동"); st["blocked"][sym] = "권리 변동"
                self.todo(rid, "corp", sym, data={"ratio": ratio, "qty": acct, "avg": p["avg"] / ratio})
                self.db.run("INSERT INTO corp_actions(run_id,symbol,kind,ratio,detected_at,data) VALUES(?,?,?,?,?,?)",
                            (rid, sym, "split", ratio, _iso(self.now()), json.dumps({"from": app, "to": acct})))
                out["corp"].append(sym)
            elif acct < app:
                self.block(rid, sym, "계좌 불일치"); st["blocked"][sym] = "계좌 불일치"
                self.todo(rid, "mismatch", sym, data={"app": app, "account": acct})
                out["mismatch"].append(sym)
        mine = {o["toss_order_id"] for o in self.db.all("SELECT toss_order_id FROM orders WHERE toss_order_id IS NOT NULL")}
        opened, _ = c.orders("OPEN")
        for t in opened:
            if t.order_id not in mine and t.symbol in st["pos"]:
                out["unknown_orders"] += 1
        if out["unknown_orders"]:
            self.db.set_meta("live.halt", "모르는 주문 번호")
            self.todo(rid, "unknown_order_no")
        # 현금(R-L7): 운용 현금이 계좌 현금보다 크면 깎고 정보 할 일 · 설명되지 않는 증가가 배당과 맞으면 더해요
        acct_cash = float(c.buying_power())
        last_cash = self.meta(rid, "acct_cash")
        if last_cash is not None:
            inc = acct_cash - float(last_cash)
            div = sum(int(p["qty"]) * (self.dps(s) or 0) * (1 - 0.154) for s, p in st["pos"].items())
            if inc > 0 and div > 0 and abs(inc - div) <= max(1.0, div * 0.01):
                st["cash"] = float(st["cash"]) + div
                out["dividend"] = div
                self.db.run("INSERT INTO run_cash(run_id,d,kind,amount,ref,at) VALUES(?,?,?,?,?,?)",
                            (rid, self.now().astimezone(KST).date().isoformat(), "dividend", div, None,
                             _iso(self.now())))
                self.notify("info", "배당 입금 · 앱에서 보기")
        if float(st["cash"]) > acct_cash:
            out["cut"] = float(st["cash"]) - acct_cash
            st["cash"] = acct_cash
            self.todo(rid, "cash_cut")
        self.set_meta(rid, "acct_cash", str(acct_cash))
        self.save(rid, st)
        return out

    def apply_corp(self, rid: int, sym: str) -> None:
        """사람이 맞추면(비밀번호) 새 수량 · 단가 · 감시가로 바꾸고 조건주문을 다시 걸어요(R-L8)."""
        st = self.state(rid)
        ca = self.db.one("SELECT * FROM corp_actions WHERE run_id=? AND symbol=? AND applied_at IS NULL "
                         "ORDER BY id DESC LIMIT 1", (rid, sym))
        if ca is None:
            raise LiveError("맞출 권리 변동이 없어요")
        ratio = float(ca["ratio"])
        p = st["pos"][sym]
        p["qty"] = int(round(p["qty"] * ratio))
        p["avg"] = p["avg"] / ratio
        if p.get("peak"):
            p["peak"] = p["peak"] / ratio
        self.unblock(rid, sym)
        self.save(rid, st)
        self.db.run("UPDATE corp_actions SET applied_at=? WHERE id=?", (_iso(self.now()), ca["id"]))
        self.db.run("UPDATE todos SET status='resolved', resolved_at=? WHERE kind='corp' AND symbol=? AND "
                    "status='open'", (_iso(self.now()), sym))
        self.place_conds(rid)

    # ── 멈추기 셋 · 전략 변경 · 계좌번호(R-L9 · R-L10) ──────────────────────

    def pause_new_buys(self, source: str = "app") -> bool:
        if self.paused:
            return False
        self.db.set_meta("live.new_buys_paused", "1")
        self.db.set_meta("live.new_buys_paused_by", source)
        r = self.run()
        if r is not None:  # 미체결 매수 취소 · 오늘 계획의 매수 빼기
            c = self.client()
            for o in self.db.all("SELECT * FROM orders WHERE run_id=? AND side='buy' AND status IN ('sent','partial')",
                                 (r["id"],)):
                if c is not None:
                    try:
                        c.cancel_order(o["toss_order_id"])
                    except BrokerError:
                        continue
                self.db.run("UPDATE orders SET status='canceled' WHERE id=?", (o["id"],))
            st = self.state(int(r["id"]))
            if st.get("next"):
                st["next"]["plans"] = [p for p in st["next"]["plans"] if p["side"] == "sell"]
                self.save(int(r["id"]), st)
        self.notify("info", "새 매수를 멈췄어요 · 매도 · 손절은 그대로 나가요")
        return True

    def resume_new_buys(self) -> None:
        """다시 켜기(비밀번호 · 앱에서만)."""
        self.db.set_meta("live.new_buys_paused", None)
        self.db.set_meta("live.new_buys_paused_by", None)

    def end(self, rid: int) -> None:
        """운용 끝내기 · 보유 그대로: 손절 · 익절 멈춤 · 조건주문 취소 · 보유 → 직접 관리 종목."""
        c = self._need()
        st = self.state(rid)
        for sym in list(st["pos"]):
            self._cancel_conds(rid, c, sym)
        for o in self.db.all("SELECT * FROM orders WHERE run_id=? AND status IN ('sent','partial')", (rid,)):
            try:
                c.cancel_order(o["toss_order_id"])
            except BrokerError:
                pass
            self.db.run("UPDATE orders SET status='canceled' WHERE id=?", (o["id"],))
        st["manual"] = sorted(set(st["manual"]) | set(st["pos"]))
        self.save(rid, st)
        self.db.run("UPDATE runs SET status=?, ended_at=?, end_kind=? WHERE id=?",
                    (ENDED, _iso(self.now()), "keep", rid))
        self.notify("info", "운용을 끝냈어요 · 보유는 직접 관리 종목이 돼요")

    def sell_all_and_end(self, rid: int) -> list[dict[str, Any]]:
        """전부 팔고 끝내기: 장중이면 바로 보호 매도 길 · 장 밖이면 다음 거래일 08:35 시가(하한 없음).
        계좌 수량 < 앱 수량이면 팔지 않고 불일치로 남겨요. 다 팔릴 때까지 손절은 계속."""
        c = self._need()
        st = self.state(rid)
        now = self.now().astimezone(KST)
        day = self.market.calendar.day(now.date())
        holdings = {h.symbol: h for h in c.holdings()}
        in_session = day.open and day.start is not None and day.at(9, 0) <= now <= day.at(15, 20)
        out = []
        self.db.set_meta(f"live.{rid}.ending", "sell_all")
        sells = []
        for sym, p in st["pos"].items():
            acct = int(holdings[sym].qty) if sym in holdings else 0
            if acct < int(p["qty"]):
                self.block(rid, sym, "계좌 불일치"); st["blocked"][sym] = "계좌 불일치"
                self.todo(rid, "mismatch", sym, data={"app": int(p["qty"]), "account": acct})
                out.append({"sym": sym, "skip": "계좌 불일치"})
                continue
            self._cancel_conds(rid, c, sym)
            if in_session:
                q = c.prices([sym]).get(sym)
                price = float(q.price) if q else float(p["avg"])
                out.append(self._send(rid, now.date().isoformat(), sym, "SELL", int(p["qty"]), ticks_below(price, 2),
                                      "stop_all", ["전부 팔고 끝내기"]))
            else:
                sells.append({"sym": sym, "side": "sell", "qty": int(p["qty"]), "kind": "protect",
                              "close": self._prev_close(rid, sym) or p["avg"], "reason": ["전부 팔고 끝내기"]})
        if not in_session:
            for_d = (now.date() if day.open and now < day.at(8, 35) else self.market.calendar.next_open(now.date()))
            st["next"] = {"judged": now.date().isoformat(), "for_d": for_d.isoformat(), "plans": sells}
            out += [{"sym": s["sym"], "planned": for_d.isoformat()} for s in sells]
        self.save(rid, st)
        return out

    def finish_if_sold(self, rid: int) -> bool:
        if self.db.get_meta(f"live.{rid}.ending") != "sell_all":
            return False
        st = self.state(rid)
        if any(s not in st["blocked"] for s in st["pos"]):
            return False
        self.db.run("UPDATE runs SET status=?, ended_at=?, end_kind=? WHERE id=?",
                    (ENDED, _iso(self.now()), "sell_all", rid))
        return True

    def change_strategy(self, rid: int, version_id: int) -> str:
        """다음 20:10 확인부터 · 보유는 이어받고 · 조건주문은 새 규칙으로 다시 · 이 앱에서 백테스트한 버전만."""
        if not strategy_store.was_backtested(self.db, version_id):
            raise LiveError("이 버전으로 백테스트를 안 했어요 · 이 앱에서 백테스트한 버전만 운용해요")
        cal = self.market.calendar
        now = self.now().astimezone(KST)
        from_d = now.date() if cal.is_open(now.date()) and now.time() < CHECK_AT else cal.next_open(now.date())
        self.db.run("INSERT INTO run_versions(run_id,version_id,from_d) VALUES(?,?,?) ON CONFLICT(run_id,from_d) DO "
                    "UPDATE SET version_id=excluded.version_id", (rid, version_id, from_d.isoformat()))
        self.db.run("UPDATE runs SET version_id=? WHERE id=?", (version_id, rid))
        self.place_conds(rid)
        return from_d.isoformat()

    def set_amount(self, rid: int, amount: float) -> None:
        """운용 금액 변경: 다음 20:10 확인부터(R-L10). 차이는 운용 현금에 더하거나 빼요."""
        r = self.run(rid)
        if amount <= 0:
            raise LiveError("운용 금액을 입력해 주세요")
        st = self.state(rid)
        diff = float(amount) - float(r["amount"])
        st["cash"] = float(st["cash"]) + diff
        self.save(rid, st)
        self.db.run("UPDATE runs SET amount=? WHERE id=?", (float(amount), rid))
        self.db.run("INSERT INTO run_cash(run_id,d,kind,amount,ref,at) VALUES(?,?,?,?,?,?)",
                    (rid, self.now().astimezone(KST).date().isoformat(), "amount_change", diff, None,
                     _iso(self.now())))

    def set_limits(self, rid: int, limits: dict[str, Any]) -> dict[str, Any]:
        r = self.run(rid)
        settings = json.loads(r["settings"] or "{}")
        if "daily_loss" in limits:
            v = float(limits["daily_loss"])
            if not -0.2 <= v < 0:
                raise LiveError("하루 손실 한도는 −0.1% ~ −20% 사이로 정해요")
            settings["daily_loss"] = v
        if "per_stock" in limits:
            v = float(limits["per_stock"])
            if not 0 < v <= 1:
                raise LiveError("종목당 한도는 1% ~ 100% 사이로 정해요")
            settings["per_stock"] = v
        if "order_max" in limits:
            v = float(limits["order_max"])
            if not 0 < v <= 99_990_000:
                raise LiveError("주문 하나는 9,999만 원까지 정할 수 있어요")
            settings["order_max"] = v
        self.db.run("UPDATE runs SET settings=? WHERE id=?", (json.dumps(settings), rid))
        return settings

    def match_account(self, rid: int, sym: str) -> None:
        """계좌에 맞추기(비밀번호): 앱 수량을 계좌 수량으로 맞추고 다시 운용해요."""
        c = self._need()
        st = self.state(rid)
        holdings = {h.symbol: h for h in c.holdings()}
        acct = int(holdings[sym].qty) if sym in holdings else 0
        if acct <= 0:
            st["pos"].pop(sym, None)
        elif sym in st["pos"]:
            st["pos"][sym]["qty"] = acct
        self.unblock(rid, sym)
        self.save(rid, st)
        self.db.run("UPDATE todos SET status='resolved', resolved_at=? WHERE kind='mismatch' AND symbol=? AND "
                    "status='open'", (_iso(self.now()), sym))

    def send_big(self, rid: int, todo_id: int) -> dict[str, Any]:
        """큰 주문 보내기(비밀번호): 할 일에 남긴 수량 · 상한 그대로 한 번에 보내요(1억 이상도 나눠 내지 않아요)."""
        t = self.db.one("SELECT * FROM todos WHERE id=? AND kind IN ('huge','too_big') AND status='open'", (todo_id,))
        if t is None:
            raise LiveError("보낼 큰 주문이 없어요")
        data = json.loads(t["data"] or "{}")
        res = self._send(rid, self.now().astimezone(KST).date().isoformat(), t["symbol"], "BUY", int(data["qty"]),
                         float(data["cap"]), "open_buy", ["큰 주문 · 사람이 보냄"])
        self.db.run("UPDATE todos SET status='resolved', resolved_at=? WHERE id=?", (_iso(self.now()), todo_id))
        return res

    def view(self) -> dict[str, Any]:
        r = self.run()
        todos = [dict(t) for t in self.db.all("SELECT id,kind,severity,symbol,title,body,created_at FROM todos "
                                               "WHERE status='open' ORDER BY id DESC")]
        if r is None:
            return {"running": False, "paused": self.paused, "halted": self.halted, "todos": todos}
        rid = int(r["id"])
        st = self.state(rid)
        return {
            "running": True, "id": rid, "version_id": r["version_id"], "amount": r["amount"],
            "account_tail": r["account_tail"], "started_at": r["started_at"], "cash": st.get("cash"),
            "positions": st.get("pos", {}), "manual": st["manual"], "blocked": st["blocked"],
            "next": st.get("next"), "paused": self.paused, "halted": self.halted,
            "settings": json.loads(r["settings"] or "{}"), "todos": todos,
            "last_check": self.meta(rid, "last_check"),
        }

    def screen(self) -> dict[str, Any]:
        """화면(V2-10 자산 · V2-11 계획 · V2-12 기록 · V2-13 할 일)이 한 번에 받는 값. 토스가 안 되면 저장한 값만."""
        from .datamgmt import history_rows

        base = self.view()
        names = {k: v.get("name") or k for k, v in self.info().items()}
        account: dict[str, Any] | None = None
        prices: dict[str, float] = {}
        c = self.client()
        if c is not None:
            try:
                hs = c.holdings()
                cash = float(c.buying_power())
                prices = {h.symbol: float(h.last_price) for h in hs}
                account = {"total": cash + sum(float(h.qty) * float(h.last_price) for h in hs), "cash": cash,
                           "holdings": [{"sym": h.symbol, "name": h.name, "qty": int(h.qty), "avg": float(h.avg_price),
                                         "price": float(h.last_price)} for h in hs]}
            except (BrokerError, NoAnswer):
                account = None
        base["account"] = account
        base["names"] = names
        alerts = [dict(a) for a in self.db.all("SELECT id,at,live,kind,title,read FROM alerts ORDER BY id DESC LIMIT 50")]
        base["alerts"] = alerts
        if not base["running"]:
            last = self.db.one("SELECT * FROM runs ORDER BY id DESC LIMIT 1")
            base["last_run"] = dict(last) if last else None
            return base
        rid = int(base["id"])
        r = self.run(rid)
        v = strategy_store.version_no_name(self.db, r["version_id"])
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
        base["curve"] = [(x["d"], x["equity"]) for x in self.db.all(
            "SELECT d, equity FROM run_equity WHERE run_id=? ORDER BY d", (rid,))]
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
        hist = [h for h in history_rows(self.db, rid)]
        base["history"] = list(reversed(hist))
        fills = self.db.all("SELECT o.d, o.symbol, o.side, f.qty, f.price FROM fills f JOIN orders o ON o.id=f.order_id "
                            "WHERE o.run_id=? ORDER BY f.id DESC LIMIT 5", (rid,))
        base["recent"] = [{"d": f["d"], "sym": f["symbol"], "name": names.get(f["symbol"], f["symbol"]),
                           "side": f["side"], "qty": int(f["qty"]), "price": float(f["price"])} for f in fills]
        base["realized"] = sum(h["pnl"] or 0 for h in hist)
        base["trades"] = len([h for h in hist if h["status"] in ("체결", "일부 체결")])
        base["orders_n"] = len(hist)
        try:
            eng = self.engine(r, self.now().astimezone(KST).date())
            base["watch"] = [{"sym": sym, "name": names.get(sym, sym), "levels": self.watch_levels(eng, sym),
                              "price": prices.get(sym)} for sym in base["positions"]]
        except Exception:
            base["watch"] = []
        return base

    def check_account_change(self, account_no: str | None) -> None:
        """운용 중 계좌번호 변경 거절(R-L10)."""
        r = self.run()
        if r is None or account_no is None:
            return
        digits = "".join(ch for ch in account_no if ch.isdigit())
        if r["account_tail"] and not digits.endswith(r["account_tail"]):
            raise LiveError("실전 운용 중에는 계좌번호를 바꿀 수 없어요 · 먼저 운용을 끝내요", 409)


def _prev(d: str, cal: list[str]) -> str:
    before = [x for x in cal if x < d]
    return before[-1] if before else d


def tick(live: Live) -> list[str]:
    """앱 루프가 30초마다 불러요(R-O1 · 그날 장 시간에 맞춰 옮김). 한 일의 이름을 돌려줘요."""
    r = live.run()
    if r is None:
        return []
    rid = int(r["id"])
    now = live.now().astimezone(KST)
    day = live.market.calendar.day(now.date())
    if not day.open or day.start is None:
        return []
    done: list[str] = []
    today = now.date().isoformat()
    if live.meta(rid, "reconciled") != today and now >= day.at(8, 20):
        live.reconcile(rid)  # 켤 때 · 매일 대조를 끝낸 뒤 주문(R-L6)
        live.set_meta(rid, "reconciled", today)
        done.append("reconcile")
    if live.halted:
        return done
    if day.at(*PRECHECK_AT) <= now <= day.at(*LATE_OPEN):
        pre = json.loads(live.meta(rid, "precheck") or "{}")
        last = datetime.fromisoformat(pre["at"]) if pre.get("at") else None
        if not pre.get("ok") or pre.get("at", "")[:10] != today:
            if last is None or last.date() != now.date() or now - last >= timedelta(minutes=5):
                live.precheck(rid)
                done.append("precheck")
        if now >= day.at(*ORDER_AT) and live.open_orders(rid):
            done.append("open")
    elif now > day.at(*LATE_OPEN) and (live.state(rid).get("next") or {}).get("for_d") == today:
        live.open_orders(rid)  # 놓친 시가 주문 → 할 일(R-L2)
    if day.at(9, 1) <= now <= day.at(15, 20):
        if live.meta(rid, "after_open") != today:
            live.after_open(rid)
            live.set_meta(rid, "after_open", today)
            done.append("after_open")
        minute = now.strftime("%H:%M")
        if live.meta(rid, "minute") != f"{today} {minute}":
            live.set_meta(rid, "minute", f"{today} {minute}")
            live.sync_fills(rid)
            live.watch_conds(rid)
            live.intraday_tick(rid)
            live.widen(rid)
            live.finish_if_sold(rid)
            done.append("intraday")
    return done
