"""모의투자: 엔진 상태를 SQLite에 두고, 새 일봉이 생길 때마다 이어서 돌린다.

- 시작: 마지막 일봉으로 확인해 계획을 만든다(체결 없음).
- 신호 확인: 지난 확인 뒤로 새 일봉이 생긴 날마다 '시가 체결 → 종가 평가 → 종가 확인'.
  새 일봉이 없으면 아무것도 바꾸지 않는다.
- 평가: 토스가 연결돼 있으면 토스 현재가, 아니면 마지막 종가.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from .connect import Connections
from .db import DB
from .engine_mvp import Engine, Series, universe_of, warmup_calendar_days
from .market import KST, Market, now_kst
from .strategy import SLOT_LABEL, reason_rows, stock_name
from .vault import VaultError

MIN_CASH = 100_000
MAX_CASH = 10_000_000_000


OPEN_AT = time(9, 0)
BAR_FINAL = time(15, 50)  # market.BAR_FINAL_AT
AUTO_CHECK = "16:30"


def complete_until(now: datetime) -> date:
    """v1 모의투자 시각(15:50 뒤 그날 일봉). T-40(모의투자 v2 · 20:10)에서 market.complete_until로 바꿔요."""
    local = now.astimezone(KST)
    if local.time() >= BAR_FINAL:
        return local.date()
    return local.date() - timedelta(days=1)


def next_weekday(d: date) -> date:
    """다음 평일(휴장일은 앱이 모른다)."""
    d = d + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def first_open_after(now: datetime) -> date:
    """시작 시각 뒤에 처음 열리는 시가의 날(평일 09:00; 휴장일은 앱이 모른다)."""
    local = now.astimezone(KST)
    d = local.date()
    if d.weekday() < 5 and datetime.combine(d, OPEN_AT, KST) > local:
        return d
    return next_weekday(d)


def first_schedule(now: datetime, last: date) -> dict[str, Any]:
    """모의투자 첫 확인 · 첫 모의 체결. 미리 보기와 시작이 같은 실제 일봉(last)으로 쓴다.

    첫 체결은 시작한 시각 뒤에 처음 열리는 시가다. 첫 확인 시각은 시작 시각보다 앞서지 않는다.
    - 평일 09:00~15:50에 시작했고 오늘 일봉이 아직 없으면: 시작 때는 계획을 만들지 않고
      오늘 일봉으로 첫 확인(16:30 자동 확인, 또는 15:50 뒤 지금 신호 확인) → 다음 거래일 시가.
    - 그 밖(09:00 전 · 15:50 뒤 · 주말, 그리고 마지막 일봉 뒤로 빠진 평일이 있을 때 —
      휴장이나 일봉 지연): 받은 마지막 일봉으로 바로 확인 → 시작 시각 뒤 첫 시가.
    """
    local = now.astimezone(KST)
    today = local.date()
    intraday = today.weekday() < 5 and OPEN_AT <= local.time() < BAR_FINAL
    if intraday and last < today:
        return {
            "check_now": False,
            "check_d": today.isoformat(),
            "check_time": AUTO_CHECK,
            "bar_d": today.isoformat(),
            "fill_d": next_weekday(today).isoformat(),
        }
    return {
        "check_now": True,
        "check_d": today.isoformat(),
        "check_time": local.strftime("%H:%M"),
        "bar_d": last.isoformat(),
        "fill_d": first_open_after(local).isoformat(),
    }


def plan_view(p: dict[str, Any]) -> dict[str, Any]:
    return {
        "sym": p["sym"],
        "name": stock_name(p["sym"]),
        "side": p["side"],
        "qty": p.get("qty"),
        "value": p.get("value"),
        "reason": p["reason"],
        "judged": p["judged"],
    }


class Paper:
    def __init__(
        self,
        db: DB,
        market: Market,
        connections: Connections,
        *,
        now: Callable[[], datetime] = now_kst,
    ) -> None:
        self.db = db
        self.market = market
        self.connections = connections
        self.now = now
        self.lock = threading.Lock()

    def _stamp(self) -> str:
        """시각 기록(시작 · 끝 · 확인)은 앱의 시계(now)로: 시험의 가짜 시계와도 맞는다."""
        return self.now().astimezone(timezone.utc).isoformat(timespec="seconds")

    def _version(self, version_id: int) -> tuple[Any, dict[str, Any]]:
        row = self.db.one(
            "SELECT v.*, s.name AS sname FROM versions v JOIN strategies s ON s.id=v.strategy_id "
            "WHERE v.id=?",
            (version_id,),
        )
        if row is None:
            raise VaultError("그 전략 버전이 없어요", 404)
        return row, json.loads(row["body"])

    def active(self) -> Any:
        return self.db.one("SELECT * FROM paper_runs WHERE status='running' ORDER BY id DESC LIMIT 1")

    def _series(self, body: dict[str, Any], since: date) -> dict[str, Series]:
        end = complete_until(self.now())
        start = since - timedelta(days=warmup_calendar_days(body))
        bars = self.market.many(universe_of(body), start, end)
        return {s: Series(b) for s, b in bars.items() if b}

    # ── 시작 · 끝 ──────────────────────────────────────────────────────────

    def start(self, version_id: int, cash: Any) -> dict[str, Any]:
        try:
            cash_f = float(cash)
        except (TypeError, ValueError):
            raise VaultError("시작 금액을 숫자로 입력해 주세요") from None
        if not (MIN_CASH <= cash_f <= MAX_CASH):
            raise VaultError("시작 금액은 10만 원 ~ 100억 원 사이로 입력해 주세요")
        row, body = self._version(version_id)
        if int(row["problems"]) > 0:
            raise VaultError("문제가 있는 버전은 모의투자를 시작할 수 없어요 · 편집에서 수정해 주세요")
        with self.lock:
            series, last = self._last_bar(body)
            eng = Engine(body, series, cash_f)
            first = first_schedule(self.now(), date.fromisoformat(last))
            plans = eng.judge(last) if first["check_now"] else []
            with self.db.tx():
                self.db.run(
                    "UPDATE paper_runs SET status='ended', ended_at=? WHERE status='running'",
                    (self._stamp(),),
                )
                run_id = self.db.run(
                    "INSERT INTO paper_runs(version_id,cash0,state,status,started_at,last_date) "
                    "VALUES(?,?,?,?,?,?)",
                    (version_id, cash_f, json.dumps(eng.state), "running", self._stamp(), last),
                )
                self.db.run(
                    "INSERT INTO paper_equity(run_id,d,equity,cash) VALUES(?,?,?,?)",
                    (run_id, last, cash_f, cash_f),
                )
                if first["check_now"]:
                    self.db.run(
                        "INSERT INTO paper_judgements(run_id,d,made_at,plans,how) VALUES(?,?,?,?,?)",
                        (run_id, last, self._stamp(), json.dumps(plans, ensure_ascii=False), "start"),
                    )
                self.db.set_meta(f"paper.first.{run_id}", json.dumps(first))
        return {"run_id": run_id, "judged": last, "plans": [plan_view(p) for p in plans], "first": first}

    def _last_bar(self, body: dict[str, Any]) -> tuple[dict[str, Series], str]:
        series = self._series(body, self.now().date() - timedelta(days=10))
        last = max((s.d[-1] for s in series.values() if s.d), default=None)
        if last is None:
            raise VaultError("일봉을 받지 못했어요", 502)
        return series, last

    def preview(self, version_id: int) -> dict[str, Any]:
        """시작 확인 창의 첫 확인 · 첫 모의 체결: 시작과 같은 함수 · 같은 실제 일봉으로 계산한다.

        받은 일봉은 SQLite에 담겨서 바로 뒤 시작 때 다시 받지 않는다.
        """
        _, body = self._version(version_id)
        _, last = self._last_bar(body)
        return first_schedule(self.now(), date.fromisoformat(last))

    def _fill_from(self, run_id: int) -> str:
        return str((self.first_of(run_id) or {}).get("fill_d") or "")

    def first_of(self, run_id: int) -> dict[str, Any] | None:
        raw = self.db.get_meta(f"paper.first.{run_id}")
        return json.loads(raw) if raw else None

    def stop(self) -> dict[str, Any]:
        run = self.active()
        if run is None:
            raise VaultError("실행 중인 모의투자가 없어요", 404)
        self.db.run("UPDATE paper_runs SET status='ended', ended_at=? WHERE id=?", (self._stamp(), run["id"]))
        return self.run_view(int(run["id"]))

    # ── 신호 확인 ──────────────────────────────────────────────────────────

    def judge(self, how: str = "button") -> dict[str, Any]:
        with self.lock:
            run = self.active()
            if run is None:
                raise VaultError("실행 중인 모의투자가 없어요", 404)
            _, body = self._version(int(run["version_id"]))
            first = self.db.one(
                "SELECT MIN(d) AS d FROM paper_equity WHERE run_id=?", (run["id"],)
            )["d"]
            series = self._series(body, date.fromisoformat(first))
            last_date = str(run["last_date"])
            days = sorted({d for s in series.values() for d in s.d if d > last_date})
            eng = Engine(body, series, float(run["cash0"]), json.loads(run["state"]))
            sched = self.first_of(int(run["id"])) or {}
            fill_from = str(sched.get("fill_d") or "")
            if not days and not sched.get("check_now", True) and self._last_judgement(int(run["id"])) is None:
                # 첫 확인을 기다렸는데 그날 일봉이 끝내 없다(휴장 · 일봉 지연): 받은 마지막 일봉으로
                # 지금 확인하고, 체결은 지금 뒤 첫 시가로 미룬다.
                if complete_until(self.now()) >= date.fromisoformat(str(sched.get("check_d"))):
                    return self._late_first_check(run, eng, last_date, how)
            if not days:
                return {
                    "new_days": 0,
                    "first": None,
                    "judged": last_date,
                    "message": f"새 일봉이 아직 없어요 · 마지막 확인 {last_date}",
                    "trades": [],
                    "plans": [plan_view(p) for p in eng.plans],
                }
            all_trades: list[dict[str, Any]] = []
            with self.db.tx():
                for d in days:
                    # 첫 체결은 시작 시각 뒤 첫 시가: 그 앞의 날(늦게 온 일봉)은 체결하지 않는다
                    trades = eng.fill(d) if not fill_from or d >= fill_from else []
                    for t in trades:
                        self.db.run(
                            "INSERT INTO paper_trades(run_id,d,symbol,side,qty,price,amount,cost,pnl,reason)"
                            " VALUES(?,?,?,?,?,?,?,?,?,?)",
                            (
                                run["id"],
                                t["d"],
                                t["sym"],
                                t["side"],
                                t["qty"],
                                t["price"],
                                t["amount"],
                                t["cost"],
                                t["pnl"],
                                json.dumps(t["reason"], ensure_ascii=False),
                            ),
                        )
                    all_trades.extend(trades)
                    self.db.run(
                        "INSERT OR REPLACE INTO paper_equity(run_id,d,equity,cash) VALUES(?,?,?,?)",
                        (run["id"], d, eng.equity(d), eng.cash),
                    )
                    plans = eng.judge(d)
                    self.db.run(
                        "INSERT INTO paper_judgements(run_id,d,made_at,plans,how) VALUES(?,?,?,?,?)",
                        (run["id"], d, self._stamp(), json.dumps(plans, ensure_ascii=False), how),
                    )
                self.db.run(
                    "UPDATE paper_runs SET state=?, last_date=? WHERE id=?",
                    (json.dumps(eng.state), days[-1], run["id"]),
                )
            return {
                "new_days": len(days),
                "days": days,
                "first": days[0],
                "judged": days[-1],
                "message": f"{len(days)}거래일을 이어서 확인했어요 · 마지막 일봉 {days[-1]}",
                "trades": [
                    {**t, "name": stock_name(t["sym"])} for t in all_trades
                ],
                "plans": [plan_view(p) for p in eng.plans],
            }

    def _late_first_check(self, run: Any, eng: Engine, last_date: str, how: str) -> dict[str, Any]:
        plans = eng.judge(last_date)
        sched = first_schedule(self.now(), date.fromisoformat(last_date))
        sched = {**sched, "check_now": True, "late": True}
        with self.db.tx():
            self.db.run(
                "INSERT INTO paper_judgements(run_id,d,made_at,plans,how) VALUES(?,?,?,?,?)",
                (run["id"], last_date, self._stamp(), json.dumps(plans, ensure_ascii=False), how),
            )
            self.db.run("UPDATE paper_runs SET state=? WHERE id=?", (json.dumps(eng.state), run["id"]))
            self.db.set_meta(f"paper.first.{run['id']}", json.dumps(sched))
        return {
            "new_days": 0,
            "first": None,
            "judged": last_date,
            "message": f"새 일봉이 아직 없어요 · 마지막 일봉 {last_date} 기준으로 확인했어요",
            "trades": [],
            "plans": [plan_view(p) for p in eng.plans],
        }

    # ── 보기 ────────────────────────────────────────────────────────────────

    def _last_judgement(self, run_id: int) -> Any:
        return self.db.one(
            "SELECT d, made_at, plans, how FROM paper_judgements WHERE run_id=? ORDER BY id DESC LIMIT 1",
            (run_id,),
        )

    def _close_on(self, sym: str, d: str) -> float | None:
        row = self.db.one("SELECT c FROM bars WHERE symbol=? AND d<=? ORDER BY d DESC LIMIT 1", (sym, d))
        return float(row["c"]) if row else None

    def plan_detail(
        self, body: dict[str, Any], state: dict[str, Any], p: dict[str, Any], fill_from: str = ""
    ) -> dict[str, Any]:
        """계획 하나와 그 이유(단계 번호 · 단계 이름 · 글). fill_d: 이 계획이 체결될 시가의 날."""
        out = plan_view(p)
        nxt = next_weekday(date.fromisoformat(p["judged"])).isoformat()
        out["fill_d"] = max(nxt, fill_from) if fill_from else nxt
        rows = reason_rows(body, list(p.get("reason") or []))
        if p["side"] == "buy":
            close = self._close_on(p["sym"], p["judged"])
            for r in rows:
                if r["slot"] == "signal" and close is not None:
                    r["close"] = close  # type: ignore[assignment]
            # 이유 글에는 통과한 진입 경로의 ② 신호 · ③ 필터가 들어 있다(엔진 · ENGINE-RULES R-M8)
            if p.get("rank"):
                rank_text = f"신호 강도 {int(p['rank'])}위"
                rows.append(
                    {"slot": "select", "label": SLOT_LABEL["select"], "circle": "④", "name": "종목 선정",
                     "text": rank_text, "special": True, "display": f"종목 선정 · {rank_text}",
                     "rank": int(p["rank"])}
                )
        else:
            pos = state["pos"].get(p["sym"])
            out["entry_d"] = pos["entry_d"] if pos else None
            out["held_qty"] = pos["qty"] if pos else None
        out["reasons"] = rows
        return out

    def plan(self) -> dict[str, Any]:
        run = self.active()
        if run is None:
            return {"running": False}
        vrow, body = self._version(int(run["version_id"]))
        state = json.loads(run["state"])
        last = self._last_judgement(int(run["id"]))
        selling = {p["sym"] for p in state["plans"] if p["side"] == "sell"}
        keep = [s for s in state["pos"] if s not in selling]
        return {
            "running": True,
            "run_id": run["id"],
            "strategy": vrow["sname"],
            "strategy_id": vrow["strategy_id"],
            "version_no": vrow["no"],
            "last_judged": run["last_date"],
            "last": {"d": last["d"], "made_at": last["made_at"], "how": last["how"]} if last else None,
            "plans": [self.plan_detail(body, state, p, self._fill_from(int(run["id"]))) for p in state["plans"]],
            "keep": [{"sym": s, "name": stock_name(s)} for s in keep],
            "held": len(state["pos"]),
            "started_at": run["started_at"],
            "first": self.first_of(int(run["id"])),
        }

    def run_view(self, run_id: int) -> dict[str, Any]:
        """실행 하나의 요약 · 거래 내역 · 자산(지금 실행 / 지난 실행 모두)."""
        run = self.db.one(
            "SELECT r.*, v.no AS vno, v.strategy_id, v.body, s.name AS sname FROM paper_runs r "
            "JOIN versions v ON v.id=r.version_id JOIN strategies s ON s.id=v.strategy_id WHERE r.id=?",
            (run_id,),
        )
        if run is None:
            raise VaultError("그 모의투자 기록이 없어요", 404)
        body = json.loads(run["body"])
        trades = self.db.all("SELECT * FROM paper_trades WHERE run_id=? ORDER BY d DESC, id DESC", (run_id,))
        eq = self.db.all("SELECT d, equity, cash FROM paper_equity WHERE run_id=? ORDER BY d", (run_id,))
        sells = [t for t in trades if t["side"] == "sell"]
        cash0 = float(run["cash0"])
        final = float(eq[-1]["equity"]) if eq else cash0
        first_d = str(eq[0]["d"]) if eq else None
        return {
            "id": run["id"],
            "status": run["status"],
            "strategy": run["sname"],
            "strategy_id": run["strategy_id"],
            "version_no": run["vno"],
            "started_at": run["started_at"],
            "ended_at": run["ended_at"],
            "first_d": first_d,
            "last_d": run["last_date"],
            "cash0": cash0,
            "final": final,
            "ret": final / cash0 - 1 if cash0 else None,
            "realized": sum(float(t["pnl"] or 0) for t in sells),
            "trades_count": len(trades),
            "buys": len(trades) - len(sells),
            "sells": len(sells),
            "costs": sum(float(t["cost"]) for t in trades),
            "first": self.first_of(run_id),
            **self._end_info(run_id),
            "curve": [[r["d"], r["equity"]] for r in eq],
            "trades": [
                {
                    "d": t["d"],
                    "sym": t["symbol"],
                    "name": stock_name(t["symbol"]),
                    "side": t["side"],
                    "qty": t["qty"],
                    "price": t["price"],
                    "amount": t["amount"],
                    "cost": t["cost"],
                    "pnl": t["pnl"],
                    "reasons": reason_rows(body, json.loads(t["reason"])),
                }
                for t in trades
            ],
        }

    def runs(self, strategy_id: int | None = None) -> list[dict[str, Any]]:
        """실행 목록(최근 것부터). 버전 · 기간 · 수익률 · 거래 횟수."""
        where, args = ("WHERE v.strategy_id=?", (strategy_id,)) if strategy_id is not None else ("", ())
        rows = self.db.all(
            "SELECT r.id, r.status, r.started_at, r.ended_at, r.cash0, r.last_date, v.no, v.strategy_id, "
            "s.name FROM paper_runs r JOIN versions v ON v.id=r.version_id "
            f"JOIN strategies s ON s.id=v.strategy_id {where} ORDER BY r.id DESC",
            args,
        )
        out = []
        for r in rows:
            eq = self.db.all("SELECT d, equity FROM paper_equity WHERE run_id=? ORDER BY d", (r["id"],))
            n = self.db.one("SELECT COUNT(*) AS n FROM paper_trades WHERE run_id=?", (r["id"],))["n"]
            final = float(eq[-1]["equity"]) if eq else float(r["cash0"])
            out.append(
                {
                    "id": r["id"],
                    "status": r["status"],
                    "strategy": r["name"],
                    "strategy_id": r["strategy_id"],
                    "version_no": r["no"],
                    "started_at": r["started_at"],
                    "ended_at": r["ended_at"],
                    "first_d": str(eq[0]["d"]) if eq else None,
                    "last_d": r["last_date"],
                    "cash0": float(r["cash0"]),
                    "final": final,
                    "ret": final / float(r["cash0"]) - 1,
                    "trades_count": int(n),
                }
            )
        return out

    def _recent_trades(self, run_id: int, n: int = 5, body: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """모의 체결 최근 n건(최근 것부터). body를 주면 이유 글(단계 번호)도."""
        rows = self.db.all(
            "SELECT d, symbol, side, qty, price, amount, reason FROM paper_trades WHERE run_id=? "
            "ORDER BY d DESC, id DESC LIMIT ?",
            (run_id, n),
        )
        return [
            {"d": r["d"], "sym": r["symbol"], "name": stock_name(r["symbol"]), "side": r["side"],
             "qty": r["qty"], "price": r["price"], "amount": r["amount"],
             "reasons": reason_rows(body, json.loads(r["reason"])) if body is not None else []}
            for r in rows
        ]

    def _closes(self, sym: str, since: str, until: str) -> list[tuple[str, float]]:
        rows = self.db.all(
            "SELECT d, c FROM bars WHERE symbol=? AND d>=? AND d<=? ORDER BY d", (sym, since, until)
        )
        return [(str(r["d"]), float(r["c"])) for r in rows]

    def _prev_close(self, sym: str, before: str) -> float | None:
        row = self.db.one("SELECT c FROM bars WHERE symbol=? AND d<? ORDER BY d DESC LIMIT 1", (sym, before))
        return float(row["c"]) if row else None

    def _entry_reason(self, run_id: int, sym: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        row = self.db.one(
            "SELECT reason FROM paper_trades WHERE run_id=? AND symbol=? AND side='buy' ORDER BY d DESC, id DESC LIMIT 1",
            (run_id, sym),
        )
        return reason_rows(body, json.loads(row["reason"])) if row else []

    def home(self) -> dict[str, Any]:
        """자산 화면: 총자산 · 오늘 손익(전날 종가 대비) · 평가손익 · 현금 · 평가금액 · 기여 상위 3 ·
        자산 추이 · 보유 목록(30일 작은 그래프 · 매입금액 · 보유 이유) · 구성 · 최근 거래 5 · 오늘 계획."""
        run = self.active()
        if run is None:
            last = self.db.one("SELECT id FROM paper_runs ORDER BY id DESC LIMIT 1")
            out: dict[str, Any] = {"running": False, "had_run": last is not None, "last_run": None}
            if last is not None:
                rid = int(last["id"])
                out["last_run"] = {**self.runs()[0], **self._end_info(rid)}
                view = self.run_view(rid)
                out["last_run"].update({
                    "realized": view["realized"], "buys": view["buys"], "sells": view["sells"],
                    "costs": view["costs"], "curve": view["curve"],
                })
                out["recent"] = self._recent_trades(rid)
            return out
        vrow, body = self._version(int(run["version_id"]))
        state = json.loads(run["state"])
        run_id = int(run["id"])
        syms = list(state["pos"])
        live = self.connections.live_prices(syms) if syms else None
        rows = self.db.all(
            "SELECT d, equity, cash FROM paper_equity WHERE run_id=? ORDER BY d", (run["id"],)
        )
        holdings = []
        stock_value = 0.0
        price_dates: list[str] = []
        today_key = self.now().astimezone(KST).date().isoformat()
        for sym, p in state["pos"].items():
            price = live.get(sym) if live else None
            src = "토스 현재가"
            price_d = today_key
            if price is None:
                bar = self.db.one(
                    "SELECT d, c FROM bars WHERE symbol=? ORDER BY d DESC LIMIT 1", (sym,)
                )
                price = float(bar["c"]) if bar else p["avg"]
                src = "종가"
                if bar:
                    price_dates.append(str(bar["d"]))
                    price_d = str(bar["d"])
            value = p["qty"] * price
            stock_value += value
            prev = self._prev_close(sym, price_d)
            since = (date.fromisoformat(price_d) - timedelta(days=30)).isoformat()
            spark = [c for _, c in self._closes(sym, since, price_d)]
            if live and price is not None:
                spark = [*spark, float(price)]
            holdings.append(
                {
                    "sym": sym,
                    "name": stock_name(sym),
                    "qty": p["qty"],
                    "avg": p["avg"],
                    "price": price,
                    "price_d": price_d,
                    "prev_close": prev,
                    "day_pnl": (price - prev) * p["qty"] if prev is not None else None,
                    "day_pct": price / prev - 1 if prev else None,
                    "value": value,
                    "cost": p["qty"] * p["avg"],
                    "pnl": value - p["qty"] * p["avg"],
                    "pnl_pct": price / p["avg"] - 1 if p["avg"] else None,
                    "entry_d": p["entry_d"],
                    "price_source": src,
                    "spark": spark,
                    "reasons": self._entry_reason(run_id, sym, body),
                }
            )
        holdings.sort(key=lambda h: -h["value"])
        for h in holdings:
            h["weight"] = h["value"] / stock_value if stock_value else None
        total = float(state["cash"]) + stock_value
        cash0 = float(run["cash0"])
        price_source = "토스 현재가" if live else (
            f"야후 종가 {max(price_dates)}" if price_dates else "보유 없음"
        )
        last_j = self._last_judgement(run_id)
        price_as_of: dict[str, Any] = (
            {"kind": "toss", "at": self._stamp()}
            if live
            else {"kind": "close", "d": max(price_dates) if price_dates else run["last_date"]}
        )
        day_known = [h for h in holdings if h["day_pnl"] is not None]
        prev_value = sum(float(h["prev_close"]) * h["qty"] for h in day_known)
        last_d = str(rows[-1]["d"]) if rows else None
        sold_today = 0
        if last_d:
            sold_today = int(self.db.one(
                "SELECT COUNT(*) AS n FROM paper_trades WHERE run_id=? AND d=? AND side='sell'", (run_id, last_d)
            )["n"])
        return {
            "running": True,
            "run_id": run["id"],
            "strategy": vrow["sname"],
            "strategy_id": vrow["strategy_id"],
            "version_no": vrow["no"],
            "version_id": vrow["id"],
            "started_at": run["started_at"],
            "last_judged": run["last_date"],
            "cash0": cash0,
            "cash": float(state["cash"]),
            "stock_value": stock_value,
            "cost": sum(h["cost"] for h in holdings),
            "total": total,
            "pnl": total - cash0,
            "pnl_pct": total / cash0 - 1,
            "day_pnl": sum(h["day_pnl"] for h in day_known) if day_known else None,
            "day_pct": (sum(h["day_pnl"] for h in day_known) / prev_value) if prev_value else None,
            "equity_change": (float(rows[-1]["equity"]) - float(rows[-2]["equity"])) if len(rows) >= 2 else None,
            "sold_today": sold_today,
            "price_source": price_source,
            "curve": [[r["d"], r["equity"]] for r in rows],
            "holdings": holdings,
            "plans": [self.plan_detail(body, state, p, self._fill_from(run_id)) for p in state["plans"]],
            "last": {"d": last_j["d"], "made_at": last_j["made_at"], "how": last_j["how"]} if last_j else None,
            "first": self.first_of(run_id),
            "price_as_of": price_as_of,
            "recent": self._recent_trades(run_id, 5, body),
            "trades_count": int(self.db.one("SELECT COUNT(*) AS n FROM paper_trades WHERE run_id=?", (run_id,))["n"]),
        }

    def _end_info(self, run_id: int) -> dict[str, Any]:
        """끝낸 실행: 마지막 평가(그날까지 확인한 일봉 종가) · 끝낼 때 보유하던 종목 수(정리하지 않고 기록에 남는다)."""
        run = self.db.one("SELECT state, last_date FROM paper_runs WHERE id=?", (run_id,))
        state = json.loads(run["state"]) if run else {"pos": {}}
        eq = self.db.one("SELECT d FROM paper_equity WHERE run_id=? ORDER BY d DESC LIMIT 1", (run_id,))
        return {"last_eval_d": str(eq["d"]) if eq else (run["last_date"] if run else None),
                "held_end": len(state.get("pos") or {})}

    def history(self) -> dict[str, Any]:
        trades = self.db.all(
            "SELECT t.*, r.version_id FROM paper_trades t JOIN paper_runs r ON r.id=t.run_id "
            "ORDER BY t.d DESC, t.id DESC LIMIT 500"
        )
        judgements = self.db.all(
            "SELECT run_id, d, made_at, plans, how FROM paper_judgements ORDER BY id DESC LIMIT 60"
        )
        runs = self.db.all(
            "SELECT r.id, r.status, r.started_at, r.ended_at, r.cash0, v.no, s.name FROM paper_runs r "
            "JOIN versions v ON v.id=r.version_id JOIN strategies s ON s.id=v.strategy_id "
            "ORDER BY r.id DESC"
        )
        return {
            "trades": [
                {
                    "run_id": t["run_id"],
                    "d": t["d"],
                    "sym": t["symbol"],
                    "name": stock_name(t["symbol"]),
                    "side": t["side"],
                    "qty": t["qty"],
                    "price": t["price"],
                    "amount": t["amount"],
                    "cost": t["cost"],
                    "pnl": t["pnl"],
                    "reason": json.loads(t["reason"]),
                }
                for t in trades
            ],
            "judgements": [
                {
                    "run_id": j["run_id"],
                    "d": j["d"],
                    "how": j["how"],
                    "plans": [plan_view(p) for p in json.loads(j["plans"])],
                }
                for j in judgements
            ],
            "runs": [dict(r) for r in runs],
        }
