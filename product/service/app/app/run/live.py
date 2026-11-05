"""실전 운용 하루 흐름 · 실전 상태의 주인(T-60 ~ T-63 · ENGINE-RULES 5 · 6 · 7절 · SPEC 5절 · TASKS P1-08). **가짜 토스로만 시험해요.**

- 20:10 확인(R-O1): 놓친 거래일은 하루씩 다시 돌려 매도 신호만 남기고(R-L1), 마지막 거래일 계획이 다음 거래일 시가 주문.
  시작 직후 첫 확인(R-L11)도 여기로.
- 08:30 점검(R-L3) → 08:35 시가 단일가 주문(R-O3 · R-O5 · R-O8 · R-O9 · R-O10) → 체결 대조(R-O13) →
  장중 감시(R-X5 · R-O6) · 조건주문(R-X6 ~ R-X9).
- 결과 모르는 주문(R-O11 · R-O12) · 응답 이상(R-O14) · 대조 · 배당 · 기업 행동(R-L6 ~ R-L8) · 멈추기 셋(R-L9) ·
  전략 변경 · 계좌번호 잠금(R-L10).
- 엔진 상태(현금 · 보유 · 계획)는 `live_state`에 두고, 진짜 체결이 올 때만 바꿔요. 주문 · 체결 · 조건주문 · 할 일은 표에.
- 증권사는 `client()`가 주는 `Broker` 포트(`ports.py` · 조립이 토스 어댑터를 넣어 줌)만 써요(기본 가짜 · T-00). 이 파일은 소켓을 쓰지 않아요.
- 주문 값 바꾸기(수량 · 지정가 · 넓히기 · 조건주문 다리 · 미체결 처리)는 순수 함수 `orders/transform.py`, 일 시각은 `run/scheduler.py`의
  시각 표 하나예요(장 시작이 늦은 날은 `DayHours.at`으로 그만큼 늦춰요).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from ..domain import blocks as bk
from ..domain.catalog import CATALOG
from ..domain.copytext import read_body
from ..domain.costs import DIVIDEND_WITHHOLDING, FEE, SELL_TAX
from ..domain.engine import PROTECT_ITEMS, Engine, MarketData, universe_of, warmup_calendar_days
from ..domain.indicators import Series
from ..domain.markets.kr import BASE_OPEN, KST, complete_until
from ..domain.rules import ORDER_HUGE, RuleLayer, buy_cap, sell_floor
from ..orders import transform as tf
from ..ports import (
    Broker,
    BrokerBadAnswer,
    BrokerError,
    BrokerRejected,
    BrokerUnreachable,
    Clock,
    NoAnswer,
    Notifier,
)
from ..store import runs as run_store
from ..store import strategies as strategy_store
from ..store import todos as todo_store
from ..store.db import DB
from .data import Market
from .scheduler import (
    DAILY_CHECK_TIME,
    INTRADAY_FROM,
    INTRADAY_UNTIL,
    LATE_OPEN,
    ORDER_AT,
    PRECHECK_AT,
    PRECHECK_EVERY,
    RECONCILE_AT,
)

DART_ITEMS = {i for i, it in CATALOG.items() if it.lock == "dart"}
RUNNING = "running"
ENDED = "ended"

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
    """실전 상태의 주인(ARCHITECTURE 6절 '동시성'): 실전 상태(`live_state` · 주문 · 할 일 · `meta live.*`)는 이 객체만 바꿔요.

    사용자 실전 조작 12개는 공개 메서드예요(API · 텔레그램은 이것만 불러요): 시작 `start` · 끝내기 `end` · 전부 팔고 끝내기
    `sell_all_and_end` · 운용 금액 `set_amount` · 한도 `set_limits` · 전략 바꾸기 `change_strategy` · 새 매수 멈춤 `pause_new_buys` ·
    다시 켜기 `resume_new_buys` · 할 일: 결과 모르는 주문 기록 `resolve_unknown` · 권리 변동 맞추기 `apply_corp` · 계좌에 맞추기
    `match_account` · 큰 주문 보내기 `send_big`. 하루 흐름(20:10 `check` · 08:30 `precheck` · 08:35 `open_orders` · 장중)은
    앱 루프의 `tick`(아래)이 시각 표(`run/scheduler.py`)대로 불러요. 화면 모양은 `api/live.py`예요.
    """

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
            return run_store.run_with_status(self.db, RUNNING)
        r = run_store.run_by_id(self.db, rid)
        if r is None:
            raise LiveError("그 실전 운용이 없어요", 404)
        return r

    def state(self, rid: int) -> dict[str, Any]:
        row = run_store.state_row(self.db, rid)
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
        run_store.save_state(self.db, rid, json.dumps(keep, ensure_ascii=False), _iso(self.now()), st.get("pos", {}))

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
        open_ = todo_store.open_todo_id(self.db, kind, symbol)
        if open_ is not None:
            return open_
        sev, title = TODO[kind]
        name = self.info().get(symbol or "", {}).get("name") or symbol or ""
        d = data or {}
        amount = f"{round(float(d['qty']) * float(d['cap'])):,}원" if "qty" in d and "cap" in d else ""
        text = title.format(name=name, why=body or "원인 모름", amount=amount)
        tid = todo_store.add_todo(self.db, rid, kind, sev, symbol, text, SCOPE.get(kind, body),
                                  json.dumps(d, ensure_ascii=False), _iso(self.now()))
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
        eng_state: dict[str, Any] = {k: st[k] for k in ("cash", "pos", "plans", "day_no", "sold", "loss_block_d",
                                                         "unsettled", "last_equity") if k in st}
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
        rid = run_store.add_run(self.db, v["strategy_id"], version_id, RUNNING, float(amount), json.dumps(settings or {}),
                                acc[-4:], _iso(now))
        run_store.add_run_version(self.db, rid, version_id, now.astimezone(KST).date().isoformat())
        run_store.add_cash(self.db, rid, now.astimezone(KST).date().isoformat(), "start", float(amount), None, _iso(now))
        # 시작할 때 계좌에 있던 보유는 모두 직접 관리 종목(R-O10)
        manual = sorted(h.symbol for h in c.holdings())
        self.save(rid, {"cash": float(amount), "pos": {}, "plans": [], "day_no": 0, "sold": {}, "manual": manual,
                        "blocked": {}, "next": None, "sell_fail": {}})
        # R-L11: 거래일 20:10 뒤 · 휴장일이면 바로 마지막 완성 일봉으로 확인
        local = now.astimezone(KST)
        cal = self.market.calendar
        if not cal.is_open(local.date()) or local.time() >= DAILY_CHECK_TIME:
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
        run_store.put_equity(self.db, rid, upto.isoformat(), eng.equity(upto.isoformat()), float(st["cash"]))
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
            mine = run_store.run_toss_ids(self.db, rid)
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
            todo_store.resolve_open(self.db, _iso(self.now()), "precheck", "toss_down")
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
        for co in run_store.watching_conds(self.db, rid, sym):
            c.cancel_conditional_order(co["toss_cond_id"])
            run_store.set_cond_status(self.db, co["id"], "canceled")

    def _open_sell(self, rid: int, st: dict[str, Any], c: Broker, p: dict[str, Any], holdings: dict[str, Any],
                   today: str) -> dict[str, Any]:
        sym = p["sym"]
        if sym in st["blocked"]:
            return {"sym": sym, "skip": st["blocked"][sym]}
        app_qty = int(st["pos"].get(sym, {}).get("qty", 0))
        acct = int(holdings[sym].qty) if sym in holdings else 0
        if acct < app_qty:  # R-O10 · 불일치: 팔지 않아요
            self.block(rid, sym, "계좌 불일치")
            st["blocked"][sym] = "계좌 불일치"
            self.todo(rid, "mismatch", sym, data={"app": app_qty, "account": acct})
            return {"sym": sym, "skip": "계좌 불일치"}
        sellable = int(c.sellable_quantity(sym))
        qty = min(int(p["qty"]), app_qty, sellable)
        if qty <= 0:
            return {"sym": sym, "skip": "팔 수량 없음"}
        self._cancel_conds(rid, c, sym)  # R-X7
        close = float(p.get("close") or st["pos"][sym]["avg"])
        protect = p.get("kind") == "protect"
        price = tf.open_sell_price(close, protect)
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
        qty = tf.buy_quantity(value, cap, cash)  # R-O3: 수량 = ⌊목표 ÷ 상한⌋ · 묶이는 돈 ≤ 운용 현금
        if qty <= 0:
            return {"sym": sym, "skip": "운용 현금 부족"}
        order_value = qty * cap
        if order_value >= ORDER_HUGE:  # R-O9: 1억 이상은 나눠 내지 않고 할 일
            self.todo(rid, "huge", sym, data={"qty": qty, "cap": cap})
            return {"sym": sym, "skip": "큰 주문 · 할 일"}
        settings = json.loads(self.run(rid)["settings"] or "{}")
        if order_value > float(settings.get("order_max", tf.ORDER_MAX_DEFAULT)):  # R-O8 주문 크기 한도
            self.todo(rid, "too_big", sym, data={"qty": qty, "cap": cap})
            return {"sym": sym, "skip": "주문 크기 한도"}
        res = self._send(rid, today, sym, "BUY", qty, cap, "open_buy", p.get("reason") or [])
        res["reserved"] = order_value
        return res

    # ── 보내기 · 결과 모름(R-O11 · R-O12) ──────────────────────────────────

    def client_id(self, rid: int, d: str, sym: str, side: str, rnd: int) -> str:
        return tf.client_order_id(rid, d, sym, side, rnd)

    def _send(self, rid: int, d: str, sym: str, side: str, qty: int, price: float | None, kind: str,
              reason: list[str], *, order_type: str = "LIMIT", rnd: int | None = None) -> dict[str, Any]:
        c = self._need()
        if rnd is None:
            rnd = run_store.last_round(self.db, rid, d, sym, side.lower()) + 1
        cid = self.client_id(rid, d, sym, side, rnd)
        oid = run_store.add_order(self.db, rid, d, sym, side.lower(), rnd, cid, None, kind, qty, price, "DAY", "sending",
                                  json.dumps({"why": reason, "step": 1}, ensure_ascii=False), _iso(self.now()))
        try:
            toss_id = c.create_order(symbol=sym, side=side, quantity=qty, order_type=order_type,
                                     price=None if order_type == "MARKET" else Decimal(str(int(price or 0))),
                                     client_order_id=cid)
        except BrokerBadAnswer:
            self._halt(rid, "응답 이상")
            run_store.set_order_status(self.db, oid, "unknown")
            return {"sym": sym, "status": "unknown", "order": oid}
        except (NoAnswer, BrokerUnreachable, BrokerRejected) as exc:
            if isinstance(exc, BrokerRejected) and exc.status < 500:
                run_store.set_order_status_at(self.db, oid, "failed", _iso(self.now()))
                return {"sym": sym, "status": "failed", "order": oid}
            return self._unknown(rid, oid)
        run_store.mark_order_sent(self.db, oid, toss_id, _iso(self.now()))
        return {"sym": sym, "status": "sent", "order": oid, "qty": qty, "price": price}

    def _find(self, c: Broker, o: Any) -> str | None:
        """같은 날 · 종목 · 방향 · 수량 · 가격의 토스 주문 가운데 이 앱 기록에 없는 것."""
        known = run_store.known_toss_ids(self.db)
        for status in ("OPEN", "CLOSED"):
            rows, _ = c.orders(status, symbol=o["symbol"])
            for t in rows:
                if (t.order_id not in known and t.side == o["side"].upper() and int(t.qty) == int(o["qty"])
                        and (o["price"] is None or t.price is None or float(t.price) == float(o["price"]))):
                    return t.order_id
        return None

    def _unknown(self, rid: int, oid: int) -> dict[str, Any]:
        """R-O12: 내역에서 3번 찾기 → 있으면 기록 · 없으면 회차 +1 · 그래도 모르면 그 종목 0 + 할 일."""
        o = run_store.order(self.db, oid)
        c = self._need()
        for _ in range(tf.LOOKUPS):
            try:
                found = self._find(c, o)
            except (NoAnswer, BrokerError):
                continue
            if found:
                run_store.mark_order_sent(self.db, oid, found, _iso(self.now()))
                return {"sym": o["symbol"], "status": "sent", "order": oid, "found": True}
            run_store.set_order_status_at(self.db, oid, "absent", _iso(self.now()))
            if int(o["round"]) >= 2:
                break
            reason = json.loads(o["reason"] or "{}").get("why", [])
            return self._send(rid, o["d"], o["symbol"], o["side"].upper(), int(o["qty"]), o["price"], o["kind"],
                              reason, rnd=int(o["round"]) + 1)
        run_store.set_order_status_at(self.db, oid, "unknown", _iso(self.now()))
        self.block(rid, o["symbol"], "결과 모르는 주문")
        self.todo(rid, "unknown", o["symbol"], data={"order": oid})
        return {"sym": o["symbol"], "status": "unknown", "order": oid}

    def resolve_unknown(self, rid: int, order_id: int, *, filled_qty: int = 0, price: float = 0.0) -> None:
        """사람이 정해요: '체결됐어요(수량 · 가격)' / '주문이 없어요'(비밀번호 · 결과 모르는 주문 기록)."""
        o = run_store.run_order(self.db, order_id, rid)
        if o is None or o["status"] != "unknown":
            raise LiveError("결과 모르는 주문이 아니에요")
        st = self.state(rid)
        if filled_qty > 0:
            self._apply_fill(rid, st, o, filled_qty, price, 0.0, 0.0, note="사람이 기록")
            run_store.set_order_status(self.db, order_id, "filled")
        else:
            run_store.set_order_status(self.db, order_id, "absent")
        self.unblock(rid, o["symbol"])
        self.save(rid, st)
        todo_store.resolve_open_for(self.db, _iso(self.now()), "unknown", o["symbol"])

    # ── 체결 대조(R-O13) ───────────────────────────────────────────────────

    def _apply_fill(self, rid: int, st: dict[str, Any], o: Any, qty: int, price: float, commission: float,
                    tax: float, *, note: str | None = None) -> None:
        if qty <= 0:
            return
        sym = o["symbol"]
        run_store.add_fill(self.db, o["id"], qty, price, commission, tax, _iso(self.now()), note)
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
            run_store.add_cash(self.db, rid, o["d"], "buy", -(qty * price + cost), str(o["id"]), _iso(self.now()))
        else:
            p = st["pos"].get(sym)
            if p:
                p["qty"] -= qty
                if p["qty"] <= 0:
                    del st["pos"][sym]
                    st["sold"][sym] = o["d"]
            st["cash"] = float(st["cash"]) + qty * price - cost
            run_store.add_cash(self.db, rid, o["d"], "sell", qty * price - cost, str(o["id"]), _iso(self.now()))

    def sync_fills(self, rid: int) -> dict[str, int]:
        c = self._need()
        st = self.state(rid)
        done = {"filled": 0, "partial": 0, "failed": 0}
        for o in run_store.open_orders(self.db, rid):
            try:
                t = c.order(o["toss_order_id"])
            except BrokerBadAnswer:
                self._halt(rid, "응답 이상")
                break
            except (NoAnswer, BrokerError):
                continue
            ex = t.execution
            filled = int(ex.filled_qty or 0)
            before = run_store.filled_qty(self.db, o["id"])
            new_qty = filled - before
            if new_qty > 0:
                self._apply_fill(rid, st, o, new_qty, float(ex.avg_price or o["price"] or 0),
                                 float(ex.commission or 0) * new_qty / max(filled, 1),
                                 float(ex.tax or 0) * new_qty / max(filled, 1))
            if t.status == "FILLED":
                run_store.set_order_status_at(self.db, o["id"], "filled", _iso(self.now()))
                done["filled"] += 1
                if o["side"] == "sell":
                    st["sell_fail"].pop(o["symbol"], None)
            elif t.status in ("REJECTED", "CANCELED", "EXPIRED"):
                run_store.set_order_status_at(self.db, o["id"], tf.closed_status(filled), _iso(self.now()))
                done["failed"] += 1
                if o["side"] == "sell":
                    self._sell_failed(rid, st, o)
            elif t.status == "PARTIAL_FILLED":
                run_store.set_order_status_at(self.db, o["id"], "partial", _iso(self.now()))
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
        for o in run_store.open_buys_on(self.db, rid, today):
            try:
                c.cancel_order(o["toss_order_id"])
            except BrokerError:
                continue
            filled = run_store.filled_qty(self.db, o["id"])
            status, note = tf.unfilled_buy_close(filled, o["qty"])
            reason = json.loads(o["reason"] or "{}")
            reason["note"] = note
            run_store.close_order(self.db, o["id"], status, json.dumps(reason, ensure_ascii=False), _iso(self.now()))
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
            if run_store.has_pending_sell(self.db, rid, sym):
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
            res = self._send(rid, today.isoformat(), sym, "SELL", qty, tf.intraday_sell_price(price),
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
        for o in run_store.open_intraday(self.db, rid):
            last = datetime.fromisoformat(o["updated_at"] or o["created_at"])
            if now - last < tf.STEP_WAIT:
                continue
            reason = json.loads(o["reason"] or "{}")
            step = int(reason.get("step", 1))
            q = c.prices([o["symbol"]]).get(o["symbol"])
            if q is None:
                continue
            price = float(q.price)
            floor = sell_floor(float(self._prev_close(rid, o["symbol"]) or price)) if o["kind"] == "intraday_take" else 0.0
            move = tf.widen_step(o["kind"], step, price, floor)
            if move is None:
                continue
            order_type, new_price = move
            if new_price is None:
                c.modify_order(o["toss_order_id"], order_type=order_type)
            else:
                c.modify_order(o["toss_order_id"], order_type=order_type, price=Decimal(str(int(new_price))))
            reason["step"] = step + 1
            run_store.move_order(self.db, o["id"], new_price, json.dumps(reason, ensure_ascii=False), _iso(now))
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
            cur = run_store.watching_cond(self.db, rid, sym)
            if stop is None and take is None:
                if cur:
                    self._cancel_conds(rid, c, sym)
                continue
            stop_t, take_t = tf.cond_triggers(stop, take)
            renew = cur and tf.cond_renew_due(cur["expire"], today)
            if cur and int(cur["qty"]) == int(p["qty"]) and cur["stop_trigger"] == stop_t and \
                    cur["take_trigger"] == take_t and not renew:
                continue
            if cur:
                self._cancel_conds(rid, c, sym)
            kind, legs = tf.cond_legs(stop_t, take_t)
            expire = tf.cond_expire(today)
            try:
                cid = c.create_conditional_order(symbol=sym, kind=kind, quantity=int(p["qty"]), expire=expire,
                                                 first=legs[0], second=legs[1] if len(legs) > 1 else None)
            except (BrokerError, NoAnswer):
                self.todo(rid, "cond_fail", sym)
                continue
            run_store.add_cond(self.db, rid, sym, cid, kind, int(p["qty"]), stop_t, take_t, expire.isoformat(), "watching",
                               _iso(self.now()))
            made.append(cid)
        return made

    def watch_conds(self, rid: int) -> list[str]:
        """R-X9: 발동 뒤 15분 안에 체결이 없으면 취소 + 보호 매도 길. 체결되면 기록."""
        c = self._need()
        st = self.state(rid)
        now = self.now()
        out = []
        for co in run_store.live_conds(self.db, rid):
            t = c.conditional_order(co["toss_cond_id"])
            legs = [x for x in (t.first, t.second) if x is not None]
            fired = [x for x in legs if x.status in ("ORDERING", "ORDERED", "COMPLETED")]
            if not fired:
                continue
            if co["status"] == "watching":
                run_store.trigger_cond(self.db, co["id"], _iso(now))
                co = run_store.cond(self.db, co["id"])
            leg = fired[0]
            filled = 0
            if leg.triggered_order_id:
                o = c.order(leg.triggered_order_id)
                filled = int(o.execution.filled_qty or 0)
                if filled:
                    oid = run_store.add_order(
                        self.db, rid, now.astimezone(KST).date().isoformat(), co["symbol"], "sell", 1,
                        f"cond-{co['toss_cond_id']}", leg.triggered_order_id, "cond", filled,
                        float(o.execution.avg_price or 0), "DAY", "filled",
                        json.dumps({"why": ["조건주문 체결"]}, ensure_ascii=False), _iso(now))
                    row = run_store.order(self.db, oid)
                    self._apply_fill(rid, st, row, filled, float(o.execution.avg_price or 0), 0, 0)
                    run_store.set_cond_status(self.db, co["id"], "filled")
                    out.append(co["symbol"])
                    continue
            if now - datetime.fromisoformat(co["triggered_at"]) > tf.TRIGGER_WAIT:
                c.cancel_conditional_order(co["toss_cond_id"])
                run_store.set_cond_status(self.db, co["id"], "canceled")
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
                self.block(rid, sym, "권리 변동")
                st["blocked"][sym] = "권리 변동"
                self.todo(rid, "corp", sym, data={"ratio": ratio, "qty": acct, "avg": p["avg"] / ratio})
                run_store.add_corp_action(self.db, rid, sym, "split", ratio, _iso(self.now()),
                                          json.dumps({"from": app, "to": acct}))
                out["corp"].append(sym)
            elif acct < app:
                self.block(rid, sym, "계좌 불일치")
                st["blocked"][sym] = "계좌 불일치"
                self.todo(rid, "mismatch", sym, data={"app": app, "account": acct})
                out["mismatch"].append(sym)
        mine = run_store.known_toss_ids(self.db)
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
            div = sum(int(p["qty"]) * (self.dps(s) or 0) * (1 - DIVIDEND_WITHHOLDING) for s, p in st["pos"].items())
            if inc > 0 and div > 0 and abs(inc - div) <= max(1.0, div * 0.01):
                st["cash"] = float(st["cash"]) + div
                out["dividend"] = div
                run_store.add_cash(self.db, rid, self.now().astimezone(KST).date().isoformat(), "dividend", div, None,
                                   _iso(self.now()))
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
        ca = run_store.pending_corp_action(self.db, rid, sym)
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
        run_store.apply_corp_action(self.db, ca["id"], _iso(self.now()))
        todo_store.resolve_open_for(self.db, _iso(self.now()), "corp", sym)
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
            for o in run_store.open_buys(self.db, r["id"]):
                if c is not None:
                    try:
                        c.cancel_order(o["toss_order_id"])
                    except BrokerError:
                        continue
                run_store.set_order_status(self.db, o["id"], "canceled")
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
        for o in run_store.open_orders(self.db, rid):
            try:
                c.cancel_order(o["toss_order_id"])
            except BrokerError:
                pass
            run_store.set_order_status(self.db, o["id"], "canceled")
        st["manual"] = sorted(set(st["manual"]) | set(st["pos"]))
        self.save(rid, st)
        run_store.end_run(self.db, rid, ENDED, _iso(self.now()), "keep")
        self.notify("info", "운용을 끝냈어요 · 보유는 직접 관리 종목이 돼요")

    def sell_all_and_end(self, rid: int) -> list[dict[str, Any]]:
        """전부 팔고 끝내기: 장중이면 바로 보호 매도 길 · 장 밖이면 다음 거래일 08:35 시가(하한 없음).
        계좌 수량 < 앱 수량이면 팔지 않고 불일치로 남겨요. 다 팔릴 때까지 손절은 계속."""
        c = self._need()
        st = self.state(rid)
        now = self.now().astimezone(KST)
        day = self.market.calendar.day(now.date())
        holdings = {h.symbol: h for h in c.holdings()}
        in_session = day.open and day.start is not None and day.at(*BASE_OPEN) <= now <= day.at(*INTRADAY_UNTIL)
        out = []
        self.db.set_meta(f"live.{rid}.ending", "sell_all")
        sells = []
        for sym, p in st["pos"].items():
            acct = int(holdings[sym].qty) if sym in holdings else 0
            if acct < int(p["qty"]):
                self.block(rid, sym, "계좌 불일치")
                st["blocked"][sym] = "계좌 불일치"
                self.todo(rid, "mismatch", sym, data={"app": int(p["qty"]), "account": acct})
                out.append({"sym": sym, "skip": "계좌 불일치"})
                continue
            self._cancel_conds(rid, c, sym)
            if in_session:
                q = c.prices([sym]).get(sym)
                price = float(q.price) if q else float(p["avg"])
                out.append(self._send(rid, now.date().isoformat(), sym, "SELL", int(p["qty"]), tf.intraday_sell_price(price),
                                      "stop_all", ["전부 팔고 끝내기"]))
            else:
                sells.append({"sym": sym, "side": "sell", "qty": int(p["qty"]), "kind": "protect",
                              "close": self._prev_close(rid, sym) or p["avg"], "reason": ["전부 팔고 끝내기"]})
        if not in_session:
            for_d = (now.date() if day.open and now < day.at(*ORDER_AT) else self.market.calendar.next_open(now.date()))
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
        run_store.end_run(self.db, rid, ENDED, _iso(self.now()), "sell_all")
        return True

    def change_strategy(self, rid: int, version_id: int) -> str:
        """다음 20:10 확인부터 · 보유는 이어받고 · 조건주문은 새 규칙으로 다시 · 이 앱에서 백테스트한 버전만."""
        if not strategy_store.was_backtested(self.db, version_id):
            raise LiveError("이 버전으로 백테스트를 안 했어요 · 이 앱에서 백테스트한 버전만 운용해요")
        cal = self.market.calendar
        now = self.now().astimezone(KST)
        from_d = now.date() if cal.is_open(now.date()) and now.time() < DAILY_CHECK_TIME else cal.next_open(now.date())
        run_store.put_run_version(self.db, rid, version_id, from_d.isoformat())
        run_store.set_run_version(self.db, rid, version_id)
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
        run_store.set_run_amount(self.db, rid, float(amount))
        run_store.add_cash(self.db, rid, self.now().astimezone(KST).date().isoformat(), "amount_change", diff, None,
                           _iso(self.now()))

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
        run_store.set_run_settings(self.db, rid, json.dumps(settings))
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
        todo_store.resolve_open_for(self.db, _iso(self.now()), "mismatch", sym)

    def send_big(self, rid: int, todo_id: int) -> dict[str, Any]:
        """큰 주문 보내기(비밀번호): 할 일에 남긴 수량 · 상한 그대로 한 번에 보내요(1억 이상도 나눠 내지 않아요)."""
        t = todo_store.open_big_order(self.db, todo_id)
        if t is None:
            raise LiveError("보낼 큰 주문이 없어요")
        data = json.loads(t["data"] or "{}")
        res = self._send(rid, self.now().astimezone(KST).date().isoformat(), t["symbol"], "BUY", int(data["qty"]),
                         float(data["cap"]), "open_buy", ["큰 주문 · 사람이 보냄"])
        todo_store.resolve_todo(self.db, todo_id, _iso(self.now()))
        return res

    def account(self) -> tuple[dict[str, Any] | None, dict[str, float]]:
        """화면이 보는 토스 계좌(총액 · 현금 · 보유)와 종목별 현재가. 토스가 안 되면 (None, {}) · 저장한 값만 보여요."""
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
        return account, prices

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
    """앱 루프가 30초마다 불러요(R-O1 · 그날 장 시간에 맞춰 옮김). 한 일의 이름을 돌려줘요.

    창 방식(시각 표 `run/scheduler.py`): 08:20 대조(그날 한 번) → 08:30 ~ 08:50(양 끝 포함) 점검 창 · 점검이 실패하면(False)
    5분마다 다시 · 통과하면 08:35부터 시가 주문 → 08:50이 지나면 그날 시가 주문은 놓침(할 일) → 09:01 ~ 15:20 체결 대조 ·
    미체결 취소(그날 한 번) · 장중 감시 1분마다."""
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
    if live.meta(rid, "reconciled") != today and now >= day.at(*RECONCILE_AT):
        live.reconcile(rid)  # 켤 때 · 매일 대조를 끝낸 뒤 주문(R-L6)
        live.set_meta(rid, "reconciled", today)
        done.append("reconcile")
    if live.halted:
        return done
    if day.at(*PRECHECK_AT) <= now <= day.at(*LATE_OPEN):
        pre = json.loads(live.meta(rid, "precheck") or "{}")
        last = datetime.fromisoformat(pre["at"]) if pre.get("at") else None
        if not pre.get("ok") or pre.get("at", "")[:10] != today:
            if last is None or last.date() != now.date() or now - last >= PRECHECK_EVERY:
                live.precheck(rid)
                done.append("precheck")
        if now >= day.at(*ORDER_AT) and live.open_orders(rid):
            done.append("open")
    elif now > day.at(*LATE_OPEN) and (live.state(rid).get("next") or {}).get("for_d") == today:
        live.open_orders(rid)  # 놓친 시가 주문 → 할 일(R-L2)
    if day.at(*INTRADAY_FROM) <= now <= day.at(*INTRADAY_UNTIL):
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
