"""엔진 v2(TASKS T-23): 백테스트 · 모의투자 · 실전 확인이 같은 판정을 써요. 전략은 v3 블록 본문(`blocks.py`).

규칙: ENGINE-RULES 3절(R-J1 ~ R-J10) · 4절(R-M1 ~ R-M12) · 5절 R-X4 · 9절(R-B1 ~ R-B3) · R-O2 · R-O4 · R-O7.

하루 순서(일봉 기준):
1. 시가: 전날 확인으로 만든 계획을 체결해요(매도 먼저, 그다음 매수). **그날 판 돈은 그날 매수에 쓰지 않아요**
   (R-O2). 그 돈이 있어야 살 수 있던 매수는 다음 거래일 시가로 한 번 넘겨요(OPEN-QUESTIONS Q-N3).
2. 장중: 장중 감시 · 조건주문 줄은 그날 저가 · 고가가 감시가에 닿으면 감시가에 팔아요(시가가 이미 넘었으면
   시가 · 같은 날 손절과 익절이 둘 다 닿으면 손절 · R-X4 · R-J8).
3. 종가: 자산을 평가하고, 확인해서 다음 거래일 시가 계획을 만들어요.

비용 · 수량은 v1 식 그대로(R-B1 · R-B3): 수수료 0.015%, 매도 세금 0.18%, 수량 = ⌊min(목표, 쓸 수 있는 현금) ÷
(시가 × (1 + 수수료))⌋. 변환한 v1 전략은 동점 · 강도를 v1 규칙으로 셈해요(R-J6 · R-M5).
"""

from __future__ import annotations

import copy
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from . import blocks as bk
from .catalog import CATALOG, STAGE_CIRCLE, start_date
from .copytext import V1_MARK, read_body
from .indicators import Series

__all__ = ["Series", "Engine", "MarketData", "run_backtest", "universe_of", "warmup_calendar_days", "BacktestError"]

FEE = 0.00015
SELL_TAX = 0.0018
PLAN_TRIES = 3  # 그 종목 일봉이 없는 날(거래 정지 등)은 계획을 넘기되, 세 번까지(v1)
GAP_LIMIT = 0.10  # 실전 지정가 상한 · 하한 ±10%(R-O3 · R-O5 · R-O7)
PROTECT_ITEMS = ("stop_loss", "trailing_stop", "disclosure")  # 보호 줄(R-O4)
SURVIVOR_LINE = "과거 결과는 앞으로의 수익을 뜻하지 않아요 · 상장폐지된 종목은 포함되지 않아요 · 실제보다 좋게 나올 수 있어요"


class BacktestError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass
class MarketData:
    """엔진이 보는 데이터. 판정 시점 규칙(R-J3 어제 확정 · R-J9 접수일 다음 거래일)은 제공하는 쪽이 지켜요."""

    series: dict[str, Series]
    index: dict[str, Series] = field(default_factory=dict)  # KOSPI · KOSDAQ
    info: dict[str, dict[str, Any]] = field(default_factory=dict)  # 종목 정보(시장 · 유형 · 우선주 · 섹터 · 상장일)
    fundamentals: Callable[[str, str], dict[str, Any]] | None = None  # (종목, 날짜) → 그날 쓸 수 있는 가치 · 재무 값
    disclosures: Callable[[str, str], list[dict[str, Any]]] | None = None  # (종목, 날짜) → [{kind, usable_from}]
    investor: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # 종목 → 날짜순 수급
    dart: bool = True  # DART 키가 있나(R-J10 · 잠긴 줄)
    live: bool = False  # 실전 · 모의(백테스트는 False · '실전에서만 적용' 줄)


def as_v3(body: dict[str, Any]) -> dict[str, Any]:
    """v3 블록 본문은 그대로, v1(일곱 칸 · 그래프 노드)은 변환해서(R-C8)."""
    if isinstance(body.get("graph"), dict) and "blocks" in body["graph"]:
        return body
    return read_body(body)


# ── 전략 모양을 엔진이 쓰는 꼴로 ────────────────────────────────────────────


@dataclass
class Compiled:
    mode: str
    universe: dict[str, Any] | None
    entry: list[list[dict[str, Any]]]  # 완성된 진입 경로마다 블록(① · ⑤ 빼고 · ② ③ ④)
    sells: list[list[dict[str, Any]]]  # 매도 경로마다 ⑥ 블록
    select: dict[str, Any] | None  # ④ 줄
    top_n: int | None
    max_pct: float | None
    every: int | None
    cooldown: int
    converted: bool
    has_signal: bool
    intraday: list[tuple[dict[str, Any], int]]  # 장중 감시 · 조건주문으로 정하는 (블록, 줄)
    graph: dict[str, Any]


def compile_body(body: dict[str, Any]) -> Compiled:
    body = as_v3(body)
    g = body["graph"]
    by = {b["id"]: b for b in g["blocks"]}
    mode = bk.mode_of(g) or "event"
    uni = next((b for b in g["blocks"] if b["stage"] == "universe"), None)
    entry = [[by[i] for i in p["blocks"] if by[i]["stage"] in ("signal", "filter", "select")]
             for p in bk.entry_paths(g)[: bk.PATH_MAX] if p["complete"]]
    sells = [[by[i] for i in p["blocks"][1:]] for p in bk.sell_paths(g)[: bk.PATH_MAX]]
    sel = next((b for b in g["blocks"] if b["stage"] == "select"), None)
    select_row = sel["rows"][0] if sel and sel["rows"] else None
    w = bk.linked_weight(g)
    wrows = {r["item"]: r for r in (w or {}).get("rows", [])}
    buy = next((b for b in g["blocks"] if b["stage"] == "buy"), None)
    cooldown = int((buy or {}).get("rows", [{}])[0].get("value") or 0) if buy and buy["rows"] else 0
    intraday = []
    for b in g["blocks"]:
        if b["stage"] != "sell":
            continue
        for i, _row in enumerate(b["rows"]):
            if bk.exec_of(g, b["id"], i) in ("intraday", "broker"):
                intraday.append((b, i))
    top = select_row.get("value") if select_row else None
    every = (wrows.get("rebalance_every") or {}).get("value")
    mx = (wrows.get("max_per_stock") or {}).get("value")
    return Compiled(
        mode=mode, universe=uni, entry=entry, sells=sells, select=select_row,
        top_n=int(top) if top else None, max_pct=float(mx) if mx else None, every=int(every) if every else None,
        cooldown=cooldown, converted=body.get("converted") == V1_MARK,
        has_signal=any(b["stage"] == "signal" for b in g["blocks"]), intraday=intraday, graph=g,
    )


def universe_of(body: dict[str, Any], info: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """① 유니버스의 종목(R-G5: 직접 지정이 있으면 그 목록을 나머지 줄이 다시 걸러요)."""
    c = compile_body(body)
    if c.universe is None:
        return []
    return bk.universe_symbols(c.universe, info or {})


def warmup_bars(body: dict[str, Any]) -> int:
    need = 2
    for b in as_v3(body)["graph"]["blocks"]:
        for r in b["rows"]:
            p = r.get("params") or {}
            for key in ("n", "period", "short", "long", "slow", "n1", "n2", "n3"):
                v = p.get(key)
                if isinstance(v, int | float):
                    mult = 5 if key == "period" else 1
                    need = max(need, int(v) * mult + 2)
            if r["item"] in ("from_52w_high",):
                need = max(need, 252)
            if r["item"] == "macd":
                need = max(need, int((p.get("slow") or 26) + (p.get("signal") or 9)) * 3)
    return need


def warmup_calendar_days(body: dict[str, Any]) -> int:
    return int(warmup_bars(body) * 1.5) + 15


# ── 줄 판정 ──────────────────────────────────────────────────────────────────


@dataclass
class RowResult:
    ok: bool
    strength: float | None = None
    value: float | None = None
    missing: bool = False  # R-J1 값 없음


NONE = RowResult(False, missing=True)


def _cmp(op: str, x: float | None, row: dict[str, Any]) -> RowResult:
    if x is None:
        return NONE
    v, v2 = row.get("value"), row.get("value2")
    if op == "gte":
        return RowResult(v is not None and x >= v, value=x)
    if op in ("lte",):
        return RowResult(v is not None and x <= v, value=x)
    if op == "lt":
        return RowResult(v is not None and x < v, value=x)
    if op == "between":
        return RowResult(v is not None and v2 is not None and v <= x <= v2, value=x)
    return RowResult(False, value=x)


def _cross(series: list[float | None], line: list[float | None] | None, line_value: float | None, s_c: list[float],
           i: int, up: bool, rebalance: bool) -> tuple[bool, float | None, float | None]:
    """(맞음, 오늘 값, 오늘 선). 선은 배열(line) 또는 고정값. 같은 값은 '아래'(R-J2)."""
    now = series[i]
    ln = line[i] if line is not None else line_value
    if now is None or ln is None:
        return False, now, ln
    above = now > ln if up else now < ln
    if rebalance:  # 리밸런싱 방식: 위(아래)에 있는 날 모두(R-M2)
        return above, now, ln
    if i < 1:
        return False, now, ln
    prev = series[i - 1]
    pln = line[i - 1] if line is not None else line_value
    if prev is None or pln is None:
        return False, now, ln
    was = prev <= pln if up else prev >= pln
    return above and was, now, ln


class Judge:
    """한 종목 · 한 날의 줄 판정. 강도 식은 R-M3 표(catalog.Item.strength)."""

    def __init__(self, data: MarketData, rebalance: bool) -> None:
        self.data = data
        self.rebalance = rebalance

    def row(self, row: dict[str, Any], sym: str, d: str, pos: dict[str, Any] | None = None,
            ranks: dict[int, dict[str, bool]] | None = None, rid: int | None = None) -> RowResult:
        item = CATALOG[row["item"]]
        op = row["op"]
        p = row.get("params") or {}
        s = self.data.series.get(sym)
        i = s.idx.get(d) if s else None
        if ranks is not None and rid is not None and rid in ranks:
            got = ranks[rid].get(sym)
            return NONE if got is None else RowResult(got)
        if s is None or i is None:
            return NONE
        c = s.c[i]
        iid = item.id
        strength_kind = item.strength.get(op)

        def st(val: float | None) -> float | None:
            return val if strength_kind else None

        if iid == "price":
            return _cmp(op, c, row)
        if iid == "change_pct":
            return _cmp(op, s.change_pct(i), row)
        if iid == "return_n":
            r = s.ret(i, int(p.get("n") or 1))
            res = _cmp(op, r, row)
            if op == "gte" and res.ok and r is not None and row.get("value") is not None:
                res.strength = (r - float(row["value"])) / 100
            return res
        if iid in ("high_n", "low_n"):
            n = int(p.get("n") or 1)
            line = s.prior_high(n) if iid == "high_n" else s.prior_low(n)
            ok, now, ln = _cross(s.c, line, None, s.c, i, iid == "high_n", self.rebalance)
            if ln is None or now is None:
                return NONE
            strength = now / ln - 1 if iid == "high_n" else 1 - now / ln
            return RowResult(ok, st(strength), now)
        if iid == "from_52w_high":
            return _cmp(op, s.from_high_52w(i), row)
        if iid == "gap":
            g = s.gap_pct(i)
            if g is None:
                return NONE
            g = g if p.get("dir") != "down" else -g
            return _cmp("gte", g, row)
        if iid == "volume":
            return _cmp(op, s.v[i], row)
        if iid == "turnover":
            return _cmp(op, s.turnover(i), row)
        if iid == "volume_ratio":
            return _cmp(op, s.volume_ratio(i, int(p.get("n") or 2)), row)
        if iid == "volatility":
            return _cmp(op, s.volatility(i, int(p.get("n") or 5)), row)
        if iid in ("ma", "ema"):
            n = int(p.get("n") or 2)
            line = s.sma(n) if iid == "ma" else s.ema(n)
            if op in ("cross_up", "cross_down"):
                ok, now, ln = _cross(s.c, line, None, s.c, i, op == "cross_up", self.rebalance)
            else:
                ln = line[i]
                ok = ln is not None and (c > ln if op == "above" else c < ln)
                now = c
            if ln is None:
                return NONE
            strength = c / ln - 1 if op in ("cross_up", "above") else 1 - c / ln
            return RowResult(ok, st(strength), c)
        if iid == "ma_cross":
            short, long_ = s.sma(int(p.get("short") or 2)), s.sma(int(p.get("long") or 2))
            ok, a, b = _cross(short, long_, None, s.c, i, op == "cross_up", self.rebalance)
            if a is None or b is None:
                return NONE
            return RowResult(ok, st(a / b - 1 if op == "cross_up" else 1 - a / b))
        if iid == "ma_align":
            lines = [s.sma(int(p.get(k) or 2))[i] for k in ("n1", "n2", "n3")]
            if any(x is None for x in lines):
                return NONE
            a, b, cc = lines  # type: ignore[misc]
            return RowResult(a > b > cc if op == "aligned_up" else a < b < cc)
        if iid == "disparity":
            ln = s.sma(int(p.get("n") or 2))[i]
            return NONE if ln is None else _cmp(op, c / ln * 100, row)
        if iid == "rsi":
            series = s.rsi(int(p.get("period") or 14))
            r = series[i]
            if r is None:
                return NONE
            lvl = row.get("value")
            if op in ("cross_up", "cross_down"):
                ok, _, _ = _cross(series, None, lvl, s.c, i, op == "cross_up", self.rebalance)
            else:
                ok = _cmp(op, r, row).ok
            strength = None
            if lvl:
                strength = (r - lvl) / lvl if op == "cross_up" else (lvl - r) / lvl
            return RowResult(ok, st(strength), r)
        if iid == "macd":
            line, sig = s.macd(int(p.get("fast") or 12), int(p.get("slow") or 26), int(p.get("signal") or 9))
            zero = p.get("line") == "zero"
            ok, m, sg = _cross(line, None if zero else sig, 0.0 if zero else None, s.c, i, op == "cross_up",
                               self.rebalance)
            if m is None or sg is None:
                return NONE
            diff = (m - sg) if op == "cross_up" else (sg - m)
            return RowResult(ok, st(diff / c))
        if iid == "bollinger":
            up, lo = s.bollinger(int(p.get("n") or 20), float(p.get("k") or 2))
            band = up if op == "cross_up" else lo
            ok, _, b = _cross(s.c, band, None, s.c, i, op == "cross_up", self.rebalance)
            if b is None:
                return NONE
            return RowResult(ok, st(c / b - 1 if op == "cross_up" else 1 - c / b))
        if iid == "streak":
            n = s.streak(i, p.get("dir") != "down")
            return RowResult(row.get("value") is not None and n >= row["value"], value=float(n))
        if iid == "listed_days":
            ld = (self.data.info.get(sym) or {}).get("list_date")
            if not ld:
                return NONE
            return _cmp(op, float((date.fromisoformat(d) - date.fromisoformat(ld)).days), row)
        if iid == "sector":
            secs = set((self.data.info.get(sym) or {}).get("sectors") or [])
            hit = bool(secs & set(row.get("value") or []))
            return RowResult(hit if op == "pick" else not hit)
        if iid == "exclude_warning":
            if not self.data.live:
                return RowResult(True)  # 실전에서만 적용(R-J10)
            return RowResult(not (self.data.info.get(sym) or {}).get("warnings"))
        if item.lock == "dart" and iid != "disclosure":
            f = self.data.fundamentals(sym, d) if self.data.fundamentals else {}
            if iid == "profit_state":
                state = (f.get("profit_state") or {}).get(p.get("line") or "op_income")
                if state is None:
                    return NONE
                picks = row.get("value") or []
                return RowResult(state in (picks if isinstance(picks, list) else [picks]))
            key = iid if iid != "profit_growth" else f"profit_growth_{p.get('line') or 'op_income'}"
            return _cmp(op, f.get(key), row)
        if iid == "disclosure":
            rows = self.data.disclosures(sym, d) if self.data.disclosures else []
            n = int(row.get("value") or 0)
            days = self._days_back(sym, d, n)
            hit = any(x.get("kind") == p.get("kind") and days <= x["usable_from"] <= d for x in rows)
            return RowResult(hit if op == "within_days" else not hit)
        if iid == "net_buy":
            return self._net_buy(row, sym, d, s, i)
        if iid == "foreign_ratio":
            hist = [x for x in self.data.investor.get(sym, []) if x["d"] < d]  # 어제 확정치(R-J3)
            if not hist or hist[-1].get("foreign_rate") is None:
                return NONE
            if op == "consec":
                n = int(p.get("n") or 2)
                tail = [x.get("foreign_rate") for x in hist[-(n + 1):]]
                if len(tail) < n + 1 or any(t is None for t in tail):
                    return NONE
                return RowResult(all(b > a for a, b in zip(tail, tail[1:])))  # type: ignore[operator]
            return _cmp(op, float(hist[-1]["foreign_rate"]), row)
        if iid == "index_ma":
            ix = self.data.index.get(p.get("index") or "KOSPI")
            if ix is None:
                return NONE
            j = ix.index_on_or_before(d)
            if j is None:
                return NONE
            line = ix.sma(int(p.get("n") or 2))
            if op in ("cross_up", "cross_down"):
                ok, _, ln = _cross(ix.c, line, None, ix.c, j, op == "cross_up", self.rebalance)
            else:
                ln = line[j]
                ok = ln is not None and (ix.c[j] > ln if op == "above" else ix.c[j] < ln)
            return NONE if ln is None else RowResult(ok)
        if iid in ("stop_loss", "take_profit", "trailing_stop", "max_hold"):
            return self._holding(row, s, i, pos)
        return RowResult(True)  # 고정 줄(⑤ ⑦)

    def _days_back(self, sym: str, d: str, n: int) -> str:
        s = self.data.series.get(sym)
        i = s.idx.get(d) if s else None
        if s is None or i is None:
            return d
        return s.d[max(0, i - n + 1)]

    def _net_buy(self, row: dict[str, Any], sym: str, d: str, s: Series, i: int) -> RowResult:
        p = row.get("params") or {}
        who = {"foreign": "foreign", "institution": "institution", "individual": "individual"}.get(
            p.get("who") or "foreign", "foreign")
        hist = [x for x in self.data.investor.get(sym, []) if x["d"] < d]  # 어제까지(R-J3)
        if row["op"] == "consec":
            k = 0
            for x in reversed(hist):
                v = x.get(who)
                if v is None or (v <= 0 if p.get("side", "buy") == "buy" else v >= 0):
                    break
                k += 1
            return RowResult(row.get("value") is not None and k >= row["value"], value=float(k))
        n = int(p.get("n") or 1)
        tail = hist[-n:]
        if len(tail) < n or any(x.get(who) is None for x in tail):
            return NONE
        total = sum(float(x[who]) for x in tail)
        if p.get("unit") == "pct_volume":
            vol = sum(s.v[s.idx[x["d"]]] for x in tail if x["d"] in s.idx)
            if vol <= 0:
                return NONE
            total = total / vol * 100
        return _cmp(row["op"], total, row)

    @staticmethod
    def _holding(row: dict[str, Any], s: Series, i: int, pos: dict[str, Any] | None) -> RowResult:
        if pos is None:
            return RowResult(False)
        v = row.get("value")
        if v is None:
            return RowResult(False)
        c = s.c[i]
        if row["item"] == "stop_loss":
            return RowResult(c <= pos["avg"] * (1 - float(v) / 100))
        if row["item"] == "take_profit":
            return RowResult(c >= pos["avg"] * (1 + float(v) / 100))
        if row["item"] == "trailing_stop":
            peak = pos.get("peak") or pos["avg"]
            return RowResult(c <= peak * (1 - float(v) / 100))
        j = s.idx.get(pos["entry_d"])
        return RowResult(j is not None and i - j >= int(v))


# ── 블록 · 경로 ──────────────────────────────────────────────────────────────


def block_result(block: dict[str, Any], results: list[RowResult]) -> tuple[bool, float | None]:
    """(통과, 강도). 모두 = 강도 있는 줄의 평균, 하나라도 = 맞은 줄 가운데 강도 있는 줄의 최댓값(R-M5)."""
    passed = bk.block_pass(block, [r.ok for r in results])
    if not passed:
        return False, None
    if block["match"] == "all":
        vals = [r.strength for r in results if r.strength is not None]
        return True, (sum(vals) / len(vals)) if vals else None
    vals = [r.strength for r in results if r.ok and r.strength is not None]
    return True, max(vals) if vals else None


def _fmt(v: float) -> str:
    if abs(v) >= 100 or float(v).is_integer():
        return f"{v:,.0f}"
    return f"{v:,.1f}"


def reason_text(block: dict[str, Any], row: dict[str, Any], res: RowResult) -> str:
    """R-M8 이유 글: '③ PER 12.3배 · 15배 이하'(값이 있는 비교) · '② 20일 이동평균선 상향 돌파'."""
    circle = STAGE_CIRCLE[block["stage"]]
    item = CATALOG[row["item"]]
    if res.value is not None and row["op"] in ("gte", "lte", "lt", "between") and row.get("value") is not None:
        unit = bk.value_num(item, row["op"]).unit if bk.value_num(item, row["op"]) else ""  # type: ignore[union-attr]
        name = bk.short_name(item)
        thr = bk.row_text(row).removeprefix(name).strip()
        return f"{circle} {name} {_fmt(res.value)}{unit} · {thr}"
    return f"{circle} {bk.row_text(row)}"


# ── 엔진 ─────────────────────────────────────────────────────────────────────


class Engine:
    def __init__(self, body: dict[str, Any], data: MarketData | dict[str, Series], cash: float,
                 state: dict[str, Any] | None = None, calendar: list[str] | None = None,
                 rules: Any = None) -> None:
        self.rules = rules  # 실전 · 모의 규칙 층(rules.RuleLayer · R-V1). 백테스트는 None
        self.data = data if isinstance(data, MarketData) else MarketData(series=data)
        self.c = compile_body(body)
        self.judge_rows = Judge(self.data, self.c.mode in ("target", "rank"))
        self.universe = bk.universe_symbols(self.c.universe, self.data.info) if self.c.universe else []
        self.calendar = calendar or sorted({d for s in self.data.series.values() for d in s.d})
        self.cal_idx = {d: i for i, d in enumerate(self.calendar)}
        if state is None:
            state = {"cash": float(cash), "pos": {}, "plans": [], "day_no": 0, "sold": {}}
        self.state = copy.deepcopy(state)
        self.state.setdefault("sold", {})
        self.skipped: list[dict[str, Any]] = []
        self.notes: dict[str, list[str]] = {}  # 값 없음 기록(R-J1)
        self.live_counts = {"no_buy": 0, "no_sell": 0}  # R-O7
        self._intraday_keys = {(id(b), k) for b, k in self.c.intraday}

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
                s = self.data.series.get(sym)
                price = s.close_on_or_before(d) if s else None
            total += p["qty"] * (price if price is not None else p["avg"])
        return total

    # ── 1 · 2. 시가 체결 · 장중 ────────────────────────────────────────────

    def _sell(self, d: str, sym: str, qty: int, price: float, reason: list[str], judged: str, kind: str) -> dict:  # type: ignore[type-arg]
        pos = self.pos[sym]
        gross = qty * price
        cost = gross * (FEE + SELL_TAX)
        proceeds = gross - cost
        pnl = proceeds - qty * pos["avg"]
        self.state["cash"] = self.cash + proceeds
        self.state["unsettled"] = float(self.state.get("unsettled", 0.0)) + proceeds
        pos["qty"] -= qty
        if pos["qty"] <= 0:
            del self.pos[sym]
            self.state["sold"][sym] = d
        return {"d": d, "sym": sym, "side": "sell", "qty": qty, "price": price, "amount": gross, "cost": cost,
                "pnl": pnl, "reason": reason, "judged": judged, "kind": kind}

    def fill(self, d: str) -> list[dict[str, Any]]:
        trades: list[dict[str, Any]] = []
        keep: list[dict[str, Any]] = []
        self.state["unsettled"] = 0.0
        ordered = [p for p in self.plans if p["side"] == "sell"] + [p for p in self.plans if p["side"] == "buy"]
        for plan in ordered:
            s = self.data.series.get(plan["sym"])
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
            close = plan.get("close")
            if plan["side"] == "sell":
                pos = self.pos.get(sym)
                if not pos:
                    continue
                qty = min(int(plan["qty"]), int(pos["qty"]))
                if qty <= 0:
                    continue
                if plan.get("kind") == "normal" and close and price < close * (1 - GAP_LIMIT):
                    self.live_counts["no_sell"] += 1
                if self.rules is not None and close:
                    why = self.rules.sell_block(plan.get("kind", "normal"), price, close)
                    if why:
                        self.skipped.append({**plan, "d": d, "why": why})
                        continue
                trades.append(self._sell(d, sym, qty, price, plan["reason"], plan["judged"], plan.get("kind", "normal")))
                continue
            if self.rules is not None and close:
                why = self.rules.buy_block(price, close, float(plan["value"]))
                if why:
                    self.skipped.append({**plan, "d": d, "why": why})
                    continue
            unit = price * (1 + FEE)
            settled = self.cash - float(self.state["unsettled"])
            budget_v1 = min(float(plan["value"]), self.cash)
            budget = min(float(plan["value"]), settled)
            if budget < budget_v1 and not plan.get("deferred"):
                # 그날 판 돈이 있어야 살 수 있던 매수: 다음 거래일 시가로 넘겨요(R-O2)
                keep.append({**plan, "deferred": True})
                continue
            qty = int(budget // unit) if unit > 0 else 0
            if qty <= 0:
                self.skipped.append({**plan, "d": d, "why": "매수 안 함 · 1주도 못 사요"})
                continue
            if close and price > close * (1 + GAP_LIMIT):
                self.live_counts["no_buy"] += 1
            gross = qty * price
            cost = gross * FEE
            self.state["cash"] = self.cash - gross - cost
            pos = self.pos.get(sym)
            if pos:
                total_cost = pos["qty"] * pos["avg"] + gross + cost
                pos["qty"] += qty
                pos["avg"] = total_cost / pos["qty"]
            else:
                self.pos[sym] = {"qty": qty, "avg": (gross + cost) / qty, "entry_d": d, "peak": price}
            trades.append({"d": d, "sym": sym, "side": "buy", "qty": qty, "price": price, "amount": gross,
                           "cost": cost, "pnl": None, "reason": plan["reason"], "judged": plan["judged"]})
        self.state["plans"] = keep
        trades += self._intraday(d)
        for sym, pos in self.pos.items():  # 트레일링 최고가는 전날까지(R-J8): 오늘 고가는 판단 뒤에 반영
            s = self.data.series.get(sym)
            i = s.idx.get(d) if s else None
            if s is not None and i is not None:
                pos["peak"] = max(float(pos.get("peak") or 0), s.h[i])
        return trades

    def _intraday(self, d: str) -> list[dict[str, Any]]:
        """R-X4: 장중 감시 · 조건주문 줄. 시가가 넘었으면 시가, 아니면 감시가. 손절 먼저(R-J8)."""
        if not self.c.intraday:
            return []
        out = []
        for sym in list(self.pos):
            s = self.data.series.get(sym)
            i = s.idx.get(d) if s else None
            if s is None or i is None:
                continue
            pos = self.pos[sym]
            o, h, lo = s.o[i], s.h[i], s.l[i]
            best: tuple[int, float, dict[str, Any], dict[str, Any]] | None = None
            for block, k in self.c.intraday:
                row = block["rows"][k]
                v = row.get("value")
                if v is None:
                    continue
                v = float(v)
                if row["item"] in ("stop_loss", "trailing_stop"):
                    base = pos["avg"] if row["item"] == "stop_loss" else float(pos.get("peak") or pos["avg"])
                    trig = base * (1 - v / 100)
                    if lo <= trig:
                        price = o if o <= trig else trig
                        cand = (0, price, block, row)
                        if best is None or cand[0] < best[0]:
                            best = cand
                elif row["item"] == "take_profit":
                    trig = pos["avg"] * (1 + v / 100)
                    if h >= trig:
                        price = o if o >= trig else trig
                        if best is None:
                            best = (1, price, block, row)
            if best:
                _, price, block, row = best
                kind = "protect" if row["item"] in PROTECT_ITEMS else "normal"
                reason = [reason_text(block, row, RowResult(True))]
                out.append(self._sell(d, sym, int(pos["qty"]), price, reason, d, kind))
        return out

    # ── 3. 종가 확인 ────────────────────────────────────────────────────────

    def _ranks(self, d: str, syms: list[str]) -> dict[int, dict[str, bool]]:
        """상위 n · 상위 n% · 하위 n% 줄: 그날 유니버스 안에서 순위로 맞음 / 아님."""
        out: dict[int, dict[str, bool]] = {}
        for path in self.c.entry:
            for b in path:
                for row in b["rows"]:
                    if row["op"] not in ("top_n", "top_pct", "bottom_pct") or b["stage"] == "select":
                        continue
                    vals: dict[str, float] = {}
                    plain = {**row, "op": "gte", "value": -math.inf}
                    for sym in syms:
                        res = self.judge_rows.row(plain, sym, d)
                        if res.value is not None:
                            vals[sym] = res.value
                    k = row.get("value") or 0
                    order = sorted(vals, key=lambda x: vals[x], reverse=row["op"] != "bottom_pct")
                    take = int(k) if row["op"] == "top_n" else math.ceil(len(order) * float(k) / 100)
                    picked = set(order[:take])
                    out[id(row)] = {sym: (sym in picked) for sym in vals}
        return out

    def _value_for(self, row: dict[str, Any], sym: str, d: str) -> float | None:
        plain = {**row, "op": "gte", "value": -math.inf}
        return self.judge_rows.row(plain, sym, d).value

    def _entry(self, sym: str, d: str, ranks: dict[int, dict[str, bool]]) -> tuple[bool, float | None, list[str], str]:
        """(통과, 강도, 이유 글, 안 된 이유). 통과한 경로 가운데 강도가 가장 큰 경로(같으면 앞 경로 · R-M6)."""
        best: tuple[float | None, list[str]] | None = None
        why = "신호 미충족"
        for path in self.c.entry:
            ok_path = True
            sig_strengths: list[float] = []
            reasons: list[str] = []
            for b in path:
                if b["stage"] == "select":
                    continue
                results = [self.judge_rows.row(r, sym, d, ranks=ranks, rid=id(r)) for r in b["rows"]]
                for r, res in zip(b["rows"], results, strict=True):
                    if res.missing:
                        self.notes.setdefault(sym, []).append(f"{STAGE_CIRCLE[b['stage']]} "
                                                              f"{bk.short_name(CATALOG[r['item']])} 값 없음")
                passed, strength = block_result(b, results)
                if not passed:
                    ok_path = False
                    if b["stage"] == "filter" and why != "":
                        why = "필터 미충족"
                    break
                if b["stage"] == "signal" and strength is not None:
                    sig_strengths.append(strength)
                reasons += [reason_text(b, r, res) for r, res in zip(b["rows"], results, strict=True) if res.ok]
            if not ok_path:
                continue
            strength = sum(sig_strengths) / len(sig_strengths) if sig_strengths else None
            if self.c.converted and strength is None:
                strength = 0.0  # v1: 신호 없는 경로의 강도는 0
            if best is None or _gt(strength, best[0]):
                best = (strength, reasons)
        if best is None:
            return False, None, [], why
        return True, best[0], best[1], ""

    def _exit(self, sym: str, d: str) -> tuple[list[str], str]:
        """종가 확인 매도: 맞은 매도 경로(위 블록이 모두 통과)의 맞은 줄 · 매도 분류(R-O4)."""
        pos = self.pos[sym]
        out: list[str] = []
        protect = False
        for path in self.c.sells:
            ok = True
            hits: list[str] = []
            path_protect = False
            for b in path:
                results = []
                for k, r in enumerate(b["rows"]):
                    if (id(b), k) in self._intraday_keys:
                        results.append(RowResult(False))  # 장중에 정하는 줄은 종가 확인에서 보지 않아요
                    else:
                        results.append(self.judge_rows.row(r, sym, d, pos=pos))
                if not bk.block_pass(b, [x.ok for x in results]):
                    ok = False
                    break
                hits += [reason_text(b, r, x) for r, x in zip(b["rows"], results, strict=True) if x.ok]
                path_protect |= any(r["item"] in PROTECT_ITEMS for r in b["rows"])
            if ok and path:
                protect |= path_protect
                for h in hits:
                    if h not in out:
                        out.append(h)
        return out, "protect" if protect else "normal"

    def _cap(self, value: float, equity: float) -> float:
        if self.c.max_pct is not None:
            value = min(value, equity * self.c.max_pct / 100)
        if self.rules is not None:
            value = self.rules.cap_target(value)  # 종목당 한도(R-O8)
        return value

    def _cooling(self, sym: str, d: str) -> bool:
        """R-J5: 매도 체결일(그날 포함)부터 n거래일의 확인에서 후보가 아니에요."""
        sold = self.state["sold"].get(sym)
        if not sold or self.c.cooldown <= 0:
            return False
        a, b = self.cal_idx.get(sold), self.cal_idx.get(d)
        if a is None or b is None:
            return False
        return b - a < self.c.cooldown

    def _order(self, cands: list[str], rows: dict[str, tuple[Any, ...]], d: str) -> list[str]:
        """④ 정렬: 강도(또는 ④ 항목) 순 · 값 없음은 맨 뒤(R-M7) · 동점은 거래대금 → 코드, v1 변환은 유니버스 순서(R-J6)."""
        sel = self.c.select
        by_key = ((sel or {}).get("params") or {}).get("by") or "strength"
        desc = ((sel or {}).get("params") or {}).get("order", "desc") != "asc"
        if by_key == "strength":
            key_val = {s: rows[s][1] for s in cands}
        else:
            row = {"item": by_key, "op": "gte", "params": {"n": ((sel or {}).get("params") or {}).get("n")},
                   "value": -math.inf}
            key_val = {s: self._value_for(row, s, d) for s in cands}
        order = list(cands)
        if not self.c.converted:
            def tie(s: str) -> tuple[float, str]:
                ser = self.data.series.get(s)
                i = ser.idx.get(d) if ser else None
                return (-(ser.turnover(i) if ser is not None and i is not None else 0.0), s)

            order.sort(key=tie)
        with_v = [s for s in order if key_val[s] is not None]
        without = [s for s in order if key_val[s] is None]
        with_v.sort(key=lambda s: key_val[s], reverse=desc)  # type: ignore[arg-type,return-value]
        return with_v + without

    def judge(self, d: str) -> list[dict[str, Any]]:
        equity = self.equity(d)
        syms = [s for s in self.universe if self.data.series.get(s) and d in self.data.series[s].idx]
        ranks = self._ranks(d, syms)
        rows: dict[str, tuple[bool, float | None, list[str], str]] = {}
        for sym in syms:
            rows[sym] = self._entry(sym, d, ranks)
        pending = {p["sym"] for p in self.plans}
        new: list[dict[str, Any]] = []
        mode = self.c.mode

        def close_of(sym: str) -> float | None:
            s = self.data.series.get(sym)
            return s.close_on_or_before(d) if s else None

        def sell(sym: str, qty: int, reason: list[str], kind: str = "normal") -> None:
            new.append({"sym": sym, "side": "sell", "qty": int(qty), "reason": reason, "judged": d, "kind": kind,
                        "close": close_of(sym)})

        def buy(sym: str, value: float, reason: list[str], rank: int | None = None) -> None:
            if value > 0:
                plan: dict[str, Any] = {"sym": sym, "side": "buy", "value": value, "reason": reason, "judged": d,
                                        "close": close_of(sym)}
                if rank is not None:
                    plan["rank"] = rank
                new.append(plan)

        for sym in list(self.pos):
            s = self.data.series.get(sym)
            if s is None or d not in s.idx or sym in pending:
                continue
            why, kind = self._exit(sym, d)
            if why:
                sell(sym, self.pos[sym]["qty"], why, kind)
        selling = {p["sym"] for p in new}
        every = self.c.every
        rebalance_day = bool(every) and self.state["day_no"] % int(every or 1) == 0

        def eligible(sym: str) -> bool:
            return rows[sym][0] and not self._cooling(sym, d)

        if mode == "event":
            n = int(self.c.top_n or 1)
            held_after = len([s for s in self.pos if s not in selling]) + len(
                [p for p in self.plans if p["side"] == "buy"])
            free = n - held_after
            cands = [s for s in rows if eligible(s) and s not in self.pos and s not in pending]
            for k, sym in enumerate(self._order(cands, rows, d)[: max(0, free)]):
                buy(sym, self._cap(equity / n, equity), rows[sym][2], k + 1)
        elif mode == "rank" and rebalance_day:
            n = int(self.c.top_n or 1)
            ranked = self._order([s for s in rows if eligible(s)], rows, d)[:n]
            for sym in list(self.pos):
                if sym in rows and sym not in ranked and sym not in selling and sym not in pending:
                    sell(sym, self.pos[sym]["qty"], [f"상위 {n}종목 이탈"])
            for k, sym in enumerate(ranked):
                if sym not in self.pos and sym not in pending and sym not in selling:
                    buy(sym, self._cap(equity / n, equity), [f"상위 {n}종목 안", *rows[sym][2]], k + 1)
        elif mode == "target" and rebalance_day:
            chosen = [s for s in self.universe if s in rows and eligible(s)]
            if self.c.has_signal or (self.c.select and (self.c.select.get("params") or {}).get("by") != "strength"):
                chosen = self._order(chosen, rows, d)
            if self.c.top_n:
                chosen = chosen[: self.c.top_n]
            weight = 1 / len(chosen) if chosen else 0.0
            if self.c.max_pct is not None:
                weight = min(weight, self.c.max_pct / 100)
            for sym in list(self.pos):
                if sym in rows and sym not in chosen and sym not in pending:
                    why = rows[sym][3] or f"상위 {self.c.top_n}종목 이탈"
                    sell(sym, self.pos[sym]["qty"], [why])
            for sym in chosen:
                if sym in pending:
                    continue
                s = self.data.series[sym]
                close = s.c[s.idx[d]]
                held = self.pos.get(sym, {}).get("qty", 0)
                diff = equity * weight - held * close
                if diff <= -close:
                    sell(sym, int(-diff // close), ["리밸런싱"])
                elif diff >= close:
                    buy(sym, diff, ["리밸런싱" if held else "리밸런싱 · 동일 비중", *rows[sym][2]])

        if self.rules is not None:
            new = self._apply_day_limits(d, equity, new)
        self.state["day_no"] = int(self.state["day_no"]) + 1
        self.plans.extend(new)
        return new

    def _apply_day_limits(self, d: str, equity: float, new: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """하루 손실 한도(다음 거래일 새 매수 0 · R-O8) · 하루 주문 40건(매도 먼저 · 매수는 순위 순 · R-O9)."""
        prev = self.state.get("last_equity")
        self.state["last_equity"] = equity
        sells = [p for p in new if p["side"] == "sell"]
        buys = [p for p in new if p["side"] == "buy"]
        if self.rules.loss_blocked(prev, equity):
            for p in buys:
                self.skipped.append({**p, "d": d, "why": "매수 안 함 · 하루 손실 한도"})
            self.state["loss_block_d"] = d
            return sells
        room = max(0, self.rules.daily_orders - len(sells))
        for p in buys[room:]:
            self.skipped.append({**p, "d": d, "why": "매수 안 함 · 하루 주문 40건"})
        return sells + buys[:room]


def _gt(a: float | None, b: float | None) -> bool:
    """강도 비교: 강도 없음은 어떤 숫자보다 작아요(R-M6)."""
    if a is None:
        return False
    if b is None:
        return True
    return a > b


# ── 백테스트 ─────────────────────────────────────────────────────────────────


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


def live_note(counts: dict[str, int]) -> str:
    """R-O7 '실전이었다면' 줄."""
    return (f"시가가 종가보다 10% 넘게 높아 실전에서 안 샀을 매수 {counts['no_buy']}회 · "
            f"10% 넘게 낮아 안 팔렸을 매도 {counts['no_sell']}회예요 · 손절은 가격 하한 없이 팔아요")


def check_runnable(body: dict[str, Any], data: MarketData, start: str) -> None:
    """R-J10: 잠긴 줄이 있으면 거절 · 시작 가능 날짜보다 앞이면 거절 · 문제가 있으면 거절."""
    v3 = as_v3(body)
    a = bk.analyze(v3["graph"], dart=data.dart)
    if any(p["kind"] == "locked" for p in a["problems"]):
        raise BacktestError("DART를 연결해야 쓸 수 있는 조건이 있어요 · 연결 ›")
    if a["problems"]:
        raise BacktestError(f"문제 {len(a['problems'])} · 편집 ›")
    items = [r["item"] for b in v3["graph"]["blocks"] for r in b["rows"]]
    first = start_date(items)
    if first and date.fromisoformat(start) < first[0]:
        raise BacktestError(f"이 전략은 {first[0].isoformat()}부터 볼 수 있어요 · {first[1]}")


def run_backtest(body: dict[str, Any], bars: dict[str, list[dict[str, Any]]] | MarketData,
                 bench: list[dict[str, Any]] | None, start: str, end: str, cash: float,
                 *, check: bool = True) -> dict[str, Any]:
    if isinstance(bars, MarketData):
        data = bars
    else:
        data = MarketData(series={s: Series(b) for s, b in bars.items() if b})
    if check:
        check_runnable(body, data, start)
    dates = sorted({d for s in data.series.values() for d in s.d if start <= d <= end})
    if not dates:
        raise BacktestError("기간 안에 일봉이 없어요")
    calendar = sorted({d for s in data.series.values() for d in s.d})
    eng = Engine(body, data, cash, calendar=calendar)
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
    wide = eng.c.universe is not None and not any(r["item"] == "manual_list" for r in eng.c.universe["rows"])
    return {
        "start": dates[0], "end": dates[-1], "final": curve[-1][1], "total": m["total"], "cagr": m["cagr"],
        "mdd": m["mdd"], "trades": trades, "buys": len(trades) - len(sells), "sells": len(sells),
        "win_rate": (len(wins) / len(sells)) if sells else None,
        "costs": sum(t["cost"] for t in trades), "curve": curve, "bench_curve": bench_curve,
        "bench_total": bm["total"], "bench_cagr": bm["cagr"], "bench_mdd": bm["mdd"],
        "open": [{"sym": s, "qty": p["qty"], "avg": p["avg"]} for s, p in eng.pos.items()],
        "skipped": eng.skipped, "notes": eng.notes,
        "live_note": live_note(eng.live_counts), "live_counts": dict(eng.live_counts),
        "survivor_line": SURVIVOR_LINE, "wide_universe": wide,
    }
