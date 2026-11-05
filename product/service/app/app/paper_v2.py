"""모의투자 v2(TASKS T-40 · SPEC 6절 · ENGINE-RULES 8절 R-V1 ~ R-V5).

- 확인 시각 20:10(그날 일봉이 확정된 뒤 · kr.complete_until), 체결은 다음 거래일 일봉 시가(R-V2).
- 실전과 같은 규칙 층(`rules.RuleLayer`: 가격 상한 · 하한, 하루 손실 한도, 종목당 한도, 주문 크기, 하루 40건)과
  매도 대금 규칙(R-O2)을 써요(R-V1). 장중 감시 · 조건주문은 그날 고가 · 저가로 계산해요(엔진 R-X4).
- 전략마다 하나(여러 전략을 함께 · R-V3). 가상 시작 금액 10만 원 ~ 100억 원. 직접 관리 종목 없음. 비밀번호 없음.
- 앱이 꺼져 있던 날은 다음 확인에서 하루씩 이어서 채워요(R-V4 · 실전은 지난 날 주문 없음).
- 모의 숫자는 모의투자 탭 밖에 0건(R-V5): 실전 표(runs · positions · orders · todos)를 건드리지 않고, 알림은
  `alerts.live = 0`으로만 남겨요.
- 저장: paper_runs(status `v2-running` / `v2-ended` · MVP 모의투자와 섞이지 않게) · paper_trades · paper_equity ·
  paper_judgements.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from .domain import blocks as bk
from .domain.copytext import read_body
from .db import DB
from .domain.engine import Engine, MarketData, universe_of, warmup_calendar_days
from .domain.indicators import Series
from .domain.markets.kr import KST, complete_until
from .market import Market
from .ports import Clock
from .domain.rules import RuleLayer

MIN_CASH, MAX_CASH = 100_000, 10_000_000_000
CHECK_AT = time(20, 10)
RUNNING, ENDED = "v2-running", "v2-ended"
ALREADY = "이 전략은 이미 모의투자 중이에요"
DIFF_LINE = ("실전과 다른 점 · 체결은 일봉 시가로 계산해요(실제로는 호가에 따라 달라요) · 앱이 꺼진 날도 이어서 "
             "채워요 · 장중 손절은 고가 · 저가로 계산해요")
START_LINE = "평일 20:10에 확인하고 다음 거래일 시가로 모의 체결해요 · 실제 돈은 움직이지 않아요"
LIMITS_LINE = "한도 · 기본값 · 하루 손실 −3% · 종목당 40% · 주문 크기 2,000만 원"
DAYS = "월화수목금토일"


def md(d: date) -> str:
    return f"{d.month}/{d.day}({DAYS[d.weekday()]})"


class PaperError(Exception):
    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def _now_iso(now: datetime) -> str:
    return now.astimezone(timezone.utc).isoformat(timespec="seconds")


class PaperV2:
    def __init__(self, db: DB, market: Market, *, now: Clock,
                 info: Callable[[], dict[str, dict[str, Any]]] | None = None,
                 data_extra: Callable[[dict[str, Any], MarketData], None] | None = None) -> None:
        self.db = db
        self.market = market
        self.now = now
        self.info = info or (lambda: {})
        self.data_extra = data_extra  # DART 재무 · 공시를 붙이는 쪽(앱이 줘요)

    # ── 읽기 ────────────────────────────────────────────────────────────────

    def _run(self, rid: int) -> Any:
        r = self.db.one("SELECT * FROM paper_runs WHERE id=? AND status IN (?,?)", (rid, RUNNING, ENDED))
        if r is None:
            raise PaperError("그 모의투자가 없어요", 404)
        return r

    def _body(self, version_id: int) -> tuple[dict[str, Any], Any]:
        v = self.db.one("SELECT * FROM versions WHERE id=?", (version_id,))
        if v is None:
            raise PaperError("그 버전이 없어요", 404)
        return read_body(json.loads(v["body"])), v

    def running_for(self, strategy_id: int) -> Any:
        return self.db.one(
            "SELECT r.* FROM paper_runs r JOIN versions v ON v.id=r.version_id "
            "WHERE v.strategy_id=? AND r.status=?", (strategy_id, RUNNING))

    # ── 시작 · 끝 ───────────────────────────────────────────────────────────

    def start(self, version_id: int, cash: Any) -> dict[str, Any]:
        try:
            amount = float(cash)
        except (TypeError, ValueError):
            raise PaperError("가상 시작 금액을 숫자로 입력해요") from None
        if not (MIN_CASH <= amount <= MAX_CASH):
            raise PaperError("가상 시작 금액은 10만 원 ~ 100억 원 사이로 입력해요")
        body, v = self._body(version_id)
        if bk.analyze(body["graph"])["problems"]:
            raise PaperError("문제가 있는 버전은 모의투자를 시작할 수 없어요")
        if self.running_for(int(v["strategy_id"])) is not None:
            raise PaperError(ALREADY, 409)
        now = self.now()
        cal = self.market.calendar
        today = now.astimezone(KST).date()
        state = {"cash": amount, "pos": {}, "plans": [], "day_no": 0, "sold": {}}
        rid = self.db.run(
            "INSERT INTO paper_runs(version_id,cash0,state,status,started_at,last_date) VALUES(?,?,?,?,?,?)",
            (version_id, amount, json.dumps(state), RUNNING, _now_iso(now), None),
        )
        if cal.is_open(today) and now.astimezone(KST).time() < CHECK_AT:
            # 거래일 20:10 전에 시작: 그날 20:10이 첫 확인(R-L11과 같은 꼴)
            first = cal.prev_open(today)
            self.db.run("UPDATE paper_runs SET last_date=? WHERE id=?", (first.isoformat(), rid))
            self._equity(rid, first.isoformat(), amount, amount)
        else:
            last = complete_until(now - timedelta(minutes=10), cal)
            self.db.run("UPDATE paper_runs SET last_date=? WHERE id=?", ((last - timedelta(days=1)).isoformat(), rid))
            self._advance(rid, upto=last, first_judge_only=True)
        return self.view(rid)

    def stop(self, rid: int) -> dict[str, Any]:
        self._run(rid)
        self.db.run("UPDATE paper_runs SET status=?, ended_at=? WHERE id=?", (ENDED, _now_iso(self.now()), rid))
        return self.view(rid)

    # ── 20:10 확인 ──────────────────────────────────────────────────────────

    def tick(self) -> list[int]:
        """모든 실행 중 모의투자를 그날 20:10 확인까지(놓친 날은 하루씩 · R-V4)."""
        # 20:10 확인: 일봉 확정(20:00)에서 10분 뒤
        target = complete_until(self.now() - timedelta(minutes=10), self.market.calendar)
        done = []
        for r in self.db.all("SELECT * FROM paper_runs WHERE status=? ORDER BY id", (RUNNING,)):
            if r["last_date"] is None or r["last_date"] < target.isoformat():
                self._advance(int(r["id"]), upto=target)
                done.append(int(r["id"]))
        return done

    def _engine(self, r: Any, upto: date) -> tuple[Engine, MarketData]:
        body, _ = self._body(int(r["version_id"]))
        info = self.info()
        syms = universe_of(body, info)
        start = date.fromisoformat(r["last_date"]) if r["last_date"] else upto
        warm = start - timedelta(days=warmup_calendar_days(body) + 10)
        bars = self.market.many(syms, warm, upto)
        data = MarketData(series={s: Series(b) for s, b in bars.items() if b}, info=info, live=True)
        if self.data_extra is not None:
            self.data_extra(body, data)
        cal = sorted({d for s in data.series.values() for d in s.d})
        eng = Engine(body, data, float(r["cash0"]), state=json.loads(r["state"]), calendar=cal,
                     rules=RuleLayer(amount=float(r["cash0"])))
        return eng, data

    def _advance(self, rid: int, *, upto: date, first_judge_only: bool = False) -> None:
        r = self._run(rid)
        eng, data = self._engine(r, upto)
        days = sorted({d for s in data.series.values() for d in s.d
                       if (r["last_date"] or "") < d <= upto.isoformat()})
        new_trades = []
        for d in days:
            if not first_judge_only:
                trades = eng.fill(d)
                for t in trades:
                    self.db.run(
                        "INSERT INTO paper_trades(run_id,d,symbol,side,qty,price,amount,cost,pnl,reason) "
                        "VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (rid, t["d"], t["sym"], t["side"], int(t["qty"]), float(t["price"]), float(t["amount"]),
                         float(t["cost"]), t["pnl"], json.dumps(t["reason"], ensure_ascii=False)))
                new_trades += trades
            self._equity(rid, d, eng.equity(d), eng.cash)
            plans = eng.judge(d)
            self.db.run("INSERT INTO paper_judgements(run_id,d,made_at,plans,how) VALUES(?,?,?,?,?)",
                        (rid, d, _now_iso(self.now()), json.dumps(plans, ensure_ascii=False),
                         "start" if first_judge_only else "auto"))
        self.db.run("UPDATE paper_runs SET state=?, last_date=? WHERE id=?",
                    (json.dumps(eng.state), (days[-1] if days else upto.isoformat()), rid))
        if new_trades:
            self.db.run("INSERT INTO alerts(at, live, kind, title, body) VALUES(?,?,?,?,?)",
                        (_now_iso(self.now()), 0, "paper_fill", f"모의 · 모의 체결 {len(new_trades)}건", None))

    def _equity(self, rid: int, d: str, equity: float, cash: float) -> None:
        self.db.run("INSERT INTO paper_equity(run_id,d,equity,cash) VALUES(?,?,?,?) "
                    "ON CONFLICT(run_id,d) DO UPDATE SET equity=excluded.equity, cash=excluded.cash",
                    (rid, d, equity, cash))

    # ── 화면 ────────────────────────────────────────────────────────────────

    def view(self, rid: int) -> dict[str, Any]:
        r = self._run(rid)
        state = json.loads(r["state"])
        v = self.db.one("SELECT v.no, v.strategy_id, s.name FROM versions v JOIN strategies s ON s.id=v.strategy_id "
                        "WHERE v.id=?", (r["version_id"],))
        curve = [(x["d"], x["equity"]) for x in self.db.all(
            "SELECT d, equity FROM paper_equity WHERE run_id=? ORDER BY d", (rid,))]
        trades = [dict(x) | {"reason": json.loads(x["reason"])} for x in self.db.all(
            "SELECT * FROM paper_trades WHERE run_id=? ORDER BY id", (rid,))]
        total = curve[-1][1] if curve else float(r["cash0"])
        return {
            "id": rid, "status": "running" if r["status"] == RUNNING else "ended",
            "strategy_id": v["strategy_id"] if v else None, "name": v["name"] if v else "",
            "version_no": v["no"] if v else None, "cash0": r["cash0"], "cash": state["cash"],
            "total": total, "return": total / float(r["cash0"]) - 1,
            "holdings": [{"sym": s, **p} for s, p in state["pos"].items()],
            "plans": state["plans"], "trades": trades, "curve": curve, "last_date": r["last_date"],
            "started_at": r["started_at"], "ended_at": r["ended_at"], "diff_line": DIFF_LINE,
            "first_check": self.first_times(datetime.fromisoformat(r["started_at"]))["line"]
            if not trades and len(curve) <= 1 else "",
            "bench_return": self._bench(curve),
        }

    def _bench(self, curve: list[tuple[str, float]]) -> float | None:
        if len(curve) < 2:
            return None
        try:
            ks = self.market.bars("KOSPI", date.fromisoformat(curve[0][0]), date.fromisoformat(curve[-1][0]))
        except Exception:  # 지수를 못 받으면 '—'
            return None
        return ks[-1]["c"] / ks[0]["c"] - 1 if len(ks) >= 2 and ks[0]["c"] else None

    def first_times(self, now: datetime | None = None) -> dict[str, str]:
        """시작 창(그림 V2-42): '첫 확인 11/3(화) 20:10 · 첫 모의 체결 11/4(수) 시가'."""
        now = now or self.now()
        cal = self.market.calendar
        local = now.astimezone(KST)
        today = local.date()
        if cal.is_open(today):
            # 거래일: 20:10 전이면 그날 20:10, 뒤면 시작하자마자(그날 20:10 확인을 바로) · 체결은 다음 거래일
            fill = cal.next_open(today)
            return {"check": today.isoformat(), "fill": fill.isoformat(),
                    "line": f"첫 확인 {md(today)} 20:10 · 첫 모의 체결 {md(fill)} 시가"}
        # 휴장일: 시작하자마자 마지막 일봉으로 확인(R-L11과 같은 꼴) · 체결은 다음 거래일
        fill = cal.next_open(today)
        return {"check": today.isoformat(), "fill": fill.isoformat(),
                "line": f"첫 확인 시작하면 바로 · 첫 모의 체결 {md(fill)} 시가"}

    def preview(self, version_id: int) -> dict[str, Any]:
        _, v = self._body(version_id)
        s = self.db.one("SELECT name FROM strategies WHERE id=?", (v["strategy_id"],))
        running = self.running_for(int(v["strategy_id"]))
        ft = self.first_times()
        return {"name": s["name"] if s else "", "version_no": v["no"], "limits": LIMITS_LINE, "line": START_LINE,
                "already": ALREADY if running is not None else "", "running_id": running["id"] if running else None,
                "check": ft["check"], "fill": ft["fill"], "first_line": ft["line"]}

    def list(self) -> list[dict[str, Any]]:
        rows = self.db.all("SELECT id FROM paper_runs WHERE status IN (?,?) ORDER BY id DESC", (RUNNING, ENDED))
        return [self.view(int(x["id"])) for x in rows]
