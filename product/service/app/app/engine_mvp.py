"""MVP v1 실행 엔진(지금 화면 · 모의투자가 써요 · T-40 · T-31에서 v2 `engine.py`로 바꾸고 지워요).

확인 엔진: 백테스트와 모의투자가 같은 코드를 쓴다. 전략은 그래프(graph.py)로 받는다.

하루 순서(일봉 기준):
1. 시가: 전날 판단으로 만든 계획을 체결한다(매도 먼저, 그다음 매수).
2. 종가: 자산을 평가한다.
3. 종가: 판단해서 다음 거래일 시가에 할 계획을 만든다.

비용(한국): 수수료 0.015%(사고팔 때 모두), 매도 세금 0.18%.
손절 · 익절도 종가로 판단하고 다음 날 시가에 판다(장중 가격은 보지 않는다).
"""

from __future__ import annotations

import bisect
import copy
import math
from datetime import date
from typing import Any

from .graph import compile_graph
from .pieces import PIECES, piece_title, stage_of
from .strategy import as_graph

FEE = 0.00015
SELL_TAX = 0.0018
PLAN_TRIES = 3  # 그 종목 일봉이 없는 날(거래 정지 등)은 계획을 넘기되, 세 번까지


class Series:
    def __init__(self, bars: list[dict[str, Any]]) -> None:
        bars = sorted(bars, key=lambda b: b["d"])
        self.d = [b["d"] for b in bars]
        self.o = [float(b["o"] or b["c"]) for b in bars]
        self.h = [float(b["h"] or b["c"]) for b in bars]
        self.l = [float(b["l"] or b["c"]) for b in bars]
        self.c = [float(b["c"]) for b in bars]
        self.v = [float(b.get("v") or 0) for b in bars]
        self.idx = {d: i for i, d in enumerate(self.d)}
        self._cache: dict[tuple[str, int], list[float | None]] = {}

    def close_on_or_before(self, d: str) -> float | None:
        i = bisect.bisect_right(self.d, d) - 1
        return None if i < 0 else self.c[i]

    def last_date_on_or_before(self, d: str) -> str | None:
        i = bisect.bisect_right(self.d, d) - 1
        return None if i < 0 else self.d[i]

    def sma(self, n: int) -> list[float | None]:
        key = ("sma", n)
        if key not in self._cache:
            out: list[float | None] = [None] * len(self.c)
            total = 0.0
            for i, c in enumerate(self.c):
                total += c
                if i >= n:
                    total -= self.c[i - n]
                if i >= n - 1:
                    out[i] = total / n
            self._cache[key] = out
        return self._cache[key]

    def rsi(self, period: int) -> list[float | None]:
        """Wilder RSI."""
        key = ("rsi", period)
        if key not in self._cache:
            out: list[float | None] = [None] * len(self.c)
            if len(self.c) > period:
                gains = losses = 0.0
                for i in range(1, period + 1):
                    ch = self.c[i] - self.c[i - 1]
                    gains += max(ch, 0)
                    losses += max(-ch, 0)
                ag, al = gains / period, losses / period
                out[period] = _rsi(ag, al)
                for i in range(period + 1, len(self.c)):
                    ch = self.c[i] - self.c[i - 1]
                    ag = (ag * (period - 1) + max(ch, 0)) / period
                    al = (al * (period - 1) + max(-ch, 0)) / period
                    out[i] = _rsi(ag, al)
            self._cache[key] = out
        return self._cache[key]

    def prior_high(self, n: int) -> list[float | None]:
        """직전 n일(오늘 빼고) 고가의 최고치."""
        key = ("ph", n)
        if key not in self._cache:
            out: list[float | None] = [None] * len(self.c)
            for i in range(n, len(self.c)):
                out[i] = max(self.h[i - n : i])
            self._cache[key] = out
        return self._cache[key]


def _rsi(ag: float, al: float) -> float:
    if al == 0:
        return 100.0 if ag > 0 else 50.0
    rs = ag / al
    return 100.0 - 100.0 / (1.0 + rs)


def universe_of(body: dict[str, Any]) -> list[str]:
    return list(compile_graph(as_graph(body))["universe"])


def warmup_bars(body: dict[str, Any]) -> int:
    need = 1
    for it in as_graph(body)["nodes"]:
        if stage_of(it["piece"]) not in ("signal", "sell"):
            continue
        p = it["params"]
        if it["piece"] in ("ma_cross_up", "ma_break_down", "high_breakout"):
            need = max(need, int(p["n"]) + 2)
        elif it["piece"] == "rsi_below":
            need = max(need, int(p["period"]) * 5 + 2)
    return need


def warmup_calendar_days(body: dict[str, Any]) -> int:
    return int(warmup_bars(body) * 1.5) + 15


class Engine:
    def __init__(
        self,
        body: dict[str, Any],
        series: dict[str, Series],
        cash: float,
        state: dict[str, Any] | None = None,
    ) -> None:
        self.body = body
        self.series = series
        c = compile_graph(as_graph(body))
        self.template = c["mode"]
        self.universe = c["universe"]
        # 진입 경로마다 신호 · 필터(경로 안은 모두, 경로끼리는 하나라도), 매도 경로마다 매도 조건
        self.entry: list[dict[str, list[dict[str, Any]]]] = c["entry"]
        self.signals = c["signals"]
        self.sell_paths: list[list[dict[str, Any]]] = c["sells"]
        top_n = c["top_n"]
        self.top_n = int(top_n) if top_n else None
        max_pct = c["max_pct"]
        self.max_pct = float(max_pct) if max_pct else None
        every = c["every"]
        self.every = int(every) if every else None
        if state is None:
            state = {"cash": float(cash), "pos": {}, "plans": [], "day_no": 0}
        self.state = copy.deepcopy(state)
        self.skipped: list[dict[str, Any]] = []

    # ── 상태 ────────────────────────────────────────────────────────────────

    @property
    def cash(self) -> float:
        return float(self.state["cash"])

    @property
    def pos(self) -> dict[str, dict[str, Any]]:
        return self.state["pos"]

    @property
    def plans(self) -> list[dict[str, Any]]:
        return self.state["plans"]

    def equity(self, d: str, prices: dict[str, float] | None = None) -> float:
        total = self.cash
        for sym, p in self.pos.items():
            price = (prices or {}).get(sym)
            if price is None:
                s = self.series.get(sym)
                price = s.close_on_or_before(d) if s else None
            total += p["qty"] * (price if price is not None else p["avg"])
        return total

    # ── 1. 시가 체결 ────────────────────────────────────────────────────────

    def fill(self, d: str) -> list[dict[str, Any]]:
        trades: list[dict[str, Any]] = []
        keep: list[dict[str, Any]] = []
        ordered = [p for p in self.plans if p["side"] == "sell"] + [
            p for p in self.plans if p["side"] == "buy"
        ]
        for plan in ordered:
            s = self.series.get(plan["sym"])
            i = s.idx.get(d) if s else None
            if i is None or s is None:
                plan["tries"] = plan.get("tries", 0) + 1
                if plan["tries"] < PLAN_TRIES:
                    keep.append(plan)
                else:
                    self.skipped.append({**plan, "d": d, "why": "일봉이 없어 체결하지 못했어요"})
                continue
            price = s.o[i]
            sym = plan["sym"]
            if plan["side"] == "sell":
                pos = self.pos.get(sym)
                if not pos:
                    continue
                qty = min(int(plan["qty"]), int(pos["qty"]))
                if qty <= 0:
                    continue
                gross = qty * price
                cost = gross * (FEE + SELL_TAX)
                proceeds = gross - cost
                pnl = proceeds - qty * pos["avg"]
                self.state["cash"] = self.cash + proceeds
                pos["qty"] -= qty
                if pos["qty"] <= 0:
                    del self.pos[sym]
                trades.append(
                    {
                        "d": d,
                        "sym": sym,
                        "side": "sell",
                        "qty": qty,
                        "price": price,
                        "amount": gross,
                        "cost": cost,
                        "pnl": pnl,
                        "reason": plan["reason"],
                        "judged": plan["judged"],
                    }
                )
            else:
                unit = price * (1 + FEE)
                budget = min(float(plan["value"]), self.cash)
                qty = int(budget // unit) if unit > 0 else 0
                if qty <= 0:
                    self.skipped.append({**plan, "d": d, "why": "현금이 모자라 사지 못했어요"})
                    continue
                gross = qty * price
                cost = gross * FEE
                self.state["cash"] = self.cash - gross - cost
                pos = self.pos.get(sym)
                if pos:
                    total_cost = pos["qty"] * pos["avg"] + gross + cost
                    pos["qty"] += qty
                    pos["avg"] = total_cost / pos["qty"]
                else:
                    self.pos[sym] = {"qty": qty, "avg": (gross + cost) / qty, "entry_d": d}
                trades.append(
                    {
                        "d": d,
                        "sym": sym,
                        "side": "buy",
                        "qty": qty,
                        "price": price,
                        "amount": gross,
                        "cost": cost,
                        "pnl": None,
                        "reason": plan["reason"],
                        "judged": plan["judged"],
                    }
                )
        self.state["plans"] = keep
        return trades

    # ── 3. 종가 판단 ────────────────────────────────────────────────────────

    def _signals_ok(self, signals: list[dict[str, Any]], s: Series, i: int) -> tuple[bool, float, list[str]]:
        """경로 하나의 신호가 모두 맞는가 · 신호 강도(평균) · 이유 글. 신호가 없는 경로는 (참, 0)."""
        if not signals:
            return True, 0.0, []
        event = self.template == "event"
        strengths: list[float] = []
        reasons: list[str] = []
        c = s.c[i]
        for it in signals:
            p = it["params"]
            pid = it["piece"]
            ok = False
            strength = 0.0
            if pid == "ma_cross_up":
                sma = s.sma(int(p["n"]))
                now = sma[i]
                if now is not None:
                    above = c > now
                    if event:
                        prev = sma[i - 1] if i >= 1 else None
                        ok = above and prev is not None and s.c[i - 1] <= prev
                    else:
                        ok = above
                    strength = c / now - 1
            elif pid == "high_breakout":
                ph = s.prior_high(int(p["n"]))
                now = ph[i]
                if now is not None:
                    above = c > now
                    if event:
                        prev = ph[i - 1] if i >= 1 else None
                        ok = above and prev is not None and s.c[i - 1] <= prev
                    else:
                        ok = above
                    strength = c / now - 1
            elif pid == "rsi_below":
                r = s.rsi(int(p["period"]))[i]
                level = float(p["level"])
                if r is not None:
                    ok = r < level
                    strength = (level - r) / level
            if not ok:
                return False, 0.0, []
            strengths.append(strength)
            reasons.append(piece_title(it))
        return True, sum(strengths) / len(strengths), reasons

    @staticmethod
    def _filters_ok(filters: list[dict[str, Any]], s: Series, i: int) -> bool:
        for it in filters:
            n = float(it["params"]["n"])
            if it["piece"] == "min_turnover" and s.c[i] * s.v[i] < n * 1e8:
                return False
            if it["piece"] == "min_price" and s.c[i] < n:
                return False
        return True

    def _entry(self, s: Series, i: int) -> tuple[bool, float, list[str], bool]:
        """(신호가 맞는 경로가 있나, 신호 강도, 이유 글, 통과한 경로가 있나).

        통과 = 경로 하나의 신호 · 필터가 모두 맞음. 신호 강도는 통과한 경로마다 그 경로 신호 강도의
        평균을 내고 가장 큰 값(같으면 앞 경로). 이유 글은 그 경로 위 ② · ③ 조건(ENGINE-RULES R-M8)."""
        sig_any = False
        best: tuple[float, list[str]] | None = None
        for path in self.entry:
            ok, strength, sig_reasons = self._signals_ok(path["signals"], s, i)
            if not ok:
                continue
            sig_any = True
            if not self._filters_ok(path["filters"], s, i):
                continue
            if best is None or strength > best[0]:
                best = (strength, [*sig_reasons, *(piece_title(f) for f in path["filters"])])
        if best is None:
            return sig_any, 0.0, [], False
        return sig_any, best[0], best[1], True

    def _exit_reasons(self, sym: str, s: Series, i: int) -> list[str]:
        """맞은 매도 경로(그 위 조건이 같은 날 모두 맞음)의 조건 모두(겹치면 한 번)."""
        pos = self.pos[sym]
        c = s.c[i]

        def hit(it: dict[str, Any]) -> bool:
            p = it["params"]
            pid = it["piece"]
            if pid == "stop_loss":
                return c <= pos["avg"] * (1 - float(p["pct"]) / 100)
            if pid == "take_profit":
                return c >= pos["avg"] * (1 + float(p["pct"]) / 100)
            if pid == "max_hold":
                j = s.idx.get(pos["entry_d"])
                return j is not None and i - j >= int(p["n"])
            if pid == "ma_break_down":
                sma = s.sma(int(p["n"]))[i]
                return sma is not None and c < sma
            return False

        out: list[str] = []
        for path in self.sell_paths:
            if path and all(hit(it) for it in path):
                for it in path:
                    title = piece_title(it)
                    if title not in out:
                        out.append(title)
        return out

    def _cap(self, value: float, equity: float) -> float:
        if self.max_pct is not None:
            value = min(value, equity * self.max_pct / 100)
        return value

    def judge(self, d: str) -> list[dict[str, Any]]:
        equity = self.equity(d)
        rows: dict[str, tuple[int, bool, float, list[str], bool]] = {}
        for sym in self.universe:
            s = self.series.get(sym)
            i = s.idx.get(d) if s else None
            if s is None or i is None:
                continue
            ok, strength, reasons, passed = self._entry(s, i)
            rows[sym] = (i, ok, strength, reasons, passed)
        pending = {p["sym"] for p in self.plans}
        new: list[dict[str, Any]] = []

        def sell(sym: str, qty: int, reason: list[str]) -> None:
            new.append({"sym": sym, "side": "sell", "qty": int(qty), "reason": reason, "judged": d})

        def buy(sym: str, value: float, reason: list[str], rank: int | None = None) -> None:
            if value > 0:
                plan: dict[str, Any] = {"sym": sym, "side": "buy", "value": value, "reason": reason, "judged": d}
                if rank is not None:
                    plan["rank"] = rank  # 화면 '신호 강도 n위'용. 숫자 계산에는 쓰지 않는다
                new.append(plan)

        # 매도 조각(손절 · 익절 · 최대 보유 · 이탈)은 날마다 본다
        for sym in list(self.pos):
            s = self.series.get(sym)
            i = s.idx.get(d) if s else None
            if s is None or i is None or sym in pending:
                continue
            why = self._exit_reasons(sym, s, i)
            if why:
                sell(sym, self.pos[sym]["qty"], why)
        selling = {p["sym"] for p in new}
        rebalance_day = bool(self.every) and self.state["day_no"] % int(self.every or 1) == 0

        if self.template == "event":
            n = int(self.top_n or 1)
            held_after = len([s for s in self.pos if s not in selling]) + len(
                [p for p in self.plans if p["side"] == "buy"]
            )
            free = n - held_after
            cands = [
                sym
                for sym, (_, ok, _, _, fok) in rows.items()
                if ok and fok and sym not in self.pos and sym not in pending
            ]
            cands.sort(key=lambda s: -rows[s][2])
            for k, sym in enumerate(cands[: max(0, free)]):
                buy(sym, self._cap(equity / n, equity), rows[sym][3], k + 1)

        elif self.template == "rank" and rebalance_day:
            n = int(self.top_n or 1)
            ranked = [sym for sym, (_, ok, _, _, fok) in rows.items() if ok and fok]
            ranked.sort(key=lambda s: -rows[s][2])
            ranked = ranked[:n]
            for sym in list(self.pos):
                if sym in rows and sym not in ranked and sym not in selling and sym not in pending:
                    sell(sym, self.pos[sym]["qty"], [f"상위 {n}종목 이탈"])
            for k, sym in enumerate(ranked):
                if sym not in self.pos and sym not in pending and sym not in selling:
                    buy(sym, self._cap(equity / n, equity), [f"상위 {n}종목 안", *rows[sym][3]], k + 1)

        elif self.template == "target" and rebalance_day:
            chosen = [sym for sym in self.universe if sym in rows and rows[sym][1] and rows[sym][4]]
            if self.signals:
                chosen.sort(key=lambda s: -rows[s][2])
            if self.top_n:
                chosen = chosen[: self.top_n]
            weight = 1 / len(chosen) if chosen else 0.0
            if self.max_pct is not None:
                weight = min(weight, self.max_pct / 100)
            for sym in list(self.pos):
                if sym in rows and sym not in chosen and sym not in pending:
                    # 이유 글만 가른다(매도 여부 · 수량은 그대로)
                    if not rows[sym][1]:
                        why = "신호 미충족"
                    elif not rows[sym][4]:
                        why = "필터 미충족"
                    else:
                        why = f"상위 {self.top_n}종목 이탈"
                    sell(sym, self.pos[sym]["qty"], [why])
            for sym in chosen:
                if sym in pending:
                    continue
                close = self.series[sym].c[rows[sym][0]]
                held = self.pos.get(sym, {}).get("qty", 0)
                diff = equity * weight - held * close
                if diff <= -close:
                    sell(sym, int(-diff // close), ["리밸런싱"])
                elif diff >= close:
                    label = "리밸런싱" if held else "리밸런싱 · 동일 비중"
                    buy(sym, diff, [label, *rows[sym][3]])

        self.state["day_no"] = int(self.state["day_no"]) + 1
        self.plans.extend(new)
        return new


# ── 백테스트 ──────────────────────────────────────────────────────────────────


class BacktestError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def metrics(curve: list[tuple[str, float]], cash: float) -> dict[str, float | None]:
    if not curve:
        return {"total": None, "cagr": None, "mdd": None}
    final = curve[-1][1]
    total = final / cash - 1
    days = (date.fromisoformat(curve[-1][0]) - date.fromisoformat(curve[0][0])).days
    cagr = None
    if days > 0 and final > 0:
        cagr = (final / cash) ** (365.25 / days) - 1
    peak = -math.inf
    mdd = 0.0
    for _, v in curve:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1)
    return {"total": total, "cagr": cagr, "mdd": mdd}


def run_backtest(
    body: dict[str, Any],
    bars: dict[str, list[dict[str, Any]]],
    bench: list[dict[str, Any]] | None,
    start: str,
    end: str,
    cash: float,
) -> dict[str, Any]:
    series = {s: Series(b) for s, b in bars.items() if b}
    dates = sorted({d for s in series.values() for d in s.d if start <= d <= end})
    if not dates:
        raise BacktestError("기간 안에 일봉이 없어요")
    eng = Engine(body, series, cash)
    curve: list[tuple[str, float]] = []
    trades: list[dict[str, Any]] = []
    for d in dates:
        trades.extend(eng.fill(d))
        curve.append((d, eng.equity(d)))
        eng.judge(d)
    m = metrics(curve, cash)
    sells = [t for t in trades if t["side"] == "sell"]
    wins = [t for t in sells if (t["pnl"] or 0) > 0]
    bench_curve: list[tuple[str, float]] = []
    if bench:
        bs = Series(bench)
        base = bs.close_on_or_before(dates[0]) or (bs.c[0] if bs.c else None)
        if base:
            for d in dates:
                c = bs.close_on_or_before(d)
                if c is not None:
                    bench_curve.append((d, cash * c / base))
    bm = metrics(bench_curve, cash) if bench_curve else {"total": None, "cagr": None, "mdd": None}
    return {
        "start": dates[0],
        "end": dates[-1],
        "days": len(dates),
        "cash": cash,
        "final": curve[-1][1],
        "total": m["total"],
        "cagr": m["cagr"],
        "mdd": m["mdd"],
        "trades_count": len(trades),
        "buys": len(trades) - len(sells),
        "sells": len(sells),
        "win_rate": (len(wins) / len(sells)) if sells else None,
        "costs": sum(t["cost"] for t in trades),
        "curve": curve,
        "bench": bench_curve,
        "bench_total": bm["total"],
        "bench_cagr": bm["cagr"],
        "bench_mdd": bm["mdd"],
        "trades": trades,
        "open": [
            {"sym": s, "qty": p["qty"], "avg": p["avg"], "entry_d": p["entry_d"]}
            for s, p in eng.pos.items()
        ],
        "skipped": len(eng.skipped),
    }


def piece_names_used(body: dict[str, Any]) -> list[str]:
    return [PIECES[it["piece"]]["name"] for it in as_graph(body)["nodes"]]
