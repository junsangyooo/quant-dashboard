"""백테스트 v2(TASKS T-32 · SPEC 4-7 · 7-3 V2-26 · ENGINE-RULES 9절).

- 시세는 토스(`adapters.toss.TossSource` · `run.data.Market`), 비교 기준은 코스피(토스 지수 일봉).
- 가치 · 재무 · 공시는 `Disclosures` 포트(조립이 DART 저장 `DartStore`를 넣어 줌 · 접수일 다음 거래일)에서,
  시가총액은 수정 종가 × 주식 수(수정 계수는 수정 전 일봉을 따로 받기 전에는 1 · '주식 수 근사' 칩).
- 막는 것: 문제 있음 · 잠긴 조건(DART 없음) · 시작 가능 날짜보다 앞 · 토스 연결 없음 · DART 받는 중(R-P12).
- 결과는 버전마다 남겨요(`backtest_runs` · 상세의 '백테스트 함').
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from .domain import blocks as bk
from .domain import fundamentals as fu
from .domain.catalog import CATALOG, start_date
from .store import dart as dart_store
from .store.db import DB
from .domain.engine import FEE, SELL_TAX, BacktestError, MarketData, run_backtest, warmup_calendar_days
from .domain.indicators import Series
from .run.data import INDEX, Market, MarketDataError
from .ports import Disclosures

MIN_CASH, MAX_CASH = 100_000, 10_000_000_000
CHIPS = [
    f"거래비용 반영 · 수수료 {FEE * 100:.3f}% · 매도 세금 {SELL_TAX * 100:.2f}%",
    "토스 일봉(수정주가)",
    "판 돈은 다음 거래일 매수부터",
    "비교 기준 코스피",
]
JUDGE_LINE = "확인은 그날 종가로, 체결은 다음 거래일 시가로 해요"


def uses_dart(body: dict[str, Any]) -> bool:
    return any(CATALOG[r["item"]].lock == "dart" for b in body["graph"]["blocks"] for r in b["rows"])


def default_range(body: dict[str, Any], today: date) -> dict[str, str]:
    items = [r["item"] for b in body["graph"]["blocks"] for r in b["rows"]]
    first = start_date(items)
    start = date(today.year - 4, 1, 4)
    if first and start < first[0]:
        start = first[0]
    return {"start": start.isoformat(), "end": today.isoformat(),
            "first": first[0].isoformat() if first else "", "reason": first[1] if first else ""}


def make_data(body: dict[str, Any], market: Market, db: DB, dart: Disclosures | None, *, has_dart: bool,
              start: date, end: date, info: dict[str, dict[str, Any]]) -> MarketData:
    from .domain.engine import universe_of

    syms = universe_of(body, info)
    if not syms:
        raise BacktestError("유니버스에 종목이 없어요 · 편집에서 종목을 정해요")
    warm = start - timedelta(days=warmup_calendar_days(body))
    bars = market.many(syms, warm, end)
    try:
        index = {INDEX: Series(market.bars(INDEX, warm, end))}
    except MarketDataError:
        index = {}
    series = {s: Series(b) for s, b in bars.items() if b}
    cal = market.calendar

    fundamentals: Callable[[str, str], dict[str, Any]] | None = None
    disclosures: Callable[[str, str], list[dict[str, Any]]] | None = None
    if dart is not None and uses_dart(body):
        store = dart

        def fund(sym: str, d: str) -> dict[str, Any]:
            on = date.fromisoformat(d)
            rows = store.financial_rows(sym, on, cal.next_open)
            sh = dart_store.shares_before(db, sym, d)
            dv = dart_store.dps_before(db, sym, d)
            s = series.get(sym)
            close = s.close_on_or_before(d) if s else None
            if close is None:
                return {}
            return fu.values(rows, close, float(sh["shares"]) if sh and sh["shares"] else None, 1.0,
                             float(dv["dps"]) if dv and dv["dps"] else None)

        def disc(sym: str, d: str) -> list[dict[str, Any]]:
            return store.disclosures_on(sym, date.fromisoformat(d), cal.next_open)

        fundamentals, disclosures = fund, disc
    return MarketData(series=series, index=index, info=info, fundamentals=fundamentals, disclosures=disclosures,
                      dart=has_dart)


def run(body: dict[str, Any], *, market: Market, db: DB, dart: Disclosures | None, has_dart: bool,
        toss_ready: bool, start: date, end: date, cash: float, info: dict[str, dict[str, Any]],
        names: Callable[[str], str]) -> dict[str, Any]:
    a = bk.analyze(body["graph"], dart=has_dart)
    if a["problems"]:
        raise BacktestError(f"문제 {len(a['problems'])} · 편집 ›")
    if not toss_ready:
        raise BacktestError("토스 연결이 필요해요 · 시세와 계좌를 토스에서 받아요 · 연결 ›")
    if uses_dart(body) and dart is not None:
        p = dart.progress()
        if not p.fast_done:
            raise BacktestError(bk.backtest_wait({"dart": p.pct}) or "")
    if start >= end:
        raise BacktestError("시작 날짜가 끝 날짜보다 앞이어야 해요")
    if not (MIN_CASH <= cash <= MAX_CASH):
        raise BacktestError("시작 금액은 10만 원 ~ 100억 원 사이로 입력해요")
    data = make_data(body, market, db, dart, has_dart=has_dart, start=start, end=end, info=info)
    bench = [{"d": d, "o": c, "h": c, "l": c, "c": c, "v": 0} for d, c in
             zip(data.index[INDEX].d, data.index[INDEX].c, strict=True)] if INDEX in data.index else None
    res = run_backtest(body, data, bench, start.isoformat(), end.isoformat(), cash)
    for t in res["trades"]:
        t["name"] = names(t["sym"])
    res["recent"] = list(reversed(res["trades"][-5:]))
    res["trade_count"] = len(res["trades"])
    res["chips"] = CHIPS
    res["judge_line"] = JUDGE_LINE
    res["wide_title"] = ("코스피 · 코스닥 전체에서 고른 전략이에요" if res["wide_universe"] else "")
    res["ran_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return res
