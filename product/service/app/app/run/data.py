"""읽어 오며 저장하기: 일봉 · 장 달력을 `MarketFeed` 포트에서 받아 SQLite에 담아 둬요(TASKS T-11 · P1-08 · SPEC 11-1 순서 2 ·
ENGINE-RULES R-O1 · ARCHITECTURE 2-1 `market` 줄).

- 출처: 조립이 넣어 주는 `MarketFeed`(기본은 토스 어댑터 `adapters.toss.TossSource` · 수정주가 · 지수 `KOSPI` · `KOSDAQ`).
  야후는 쓰지 않아요.
- 캐시 판단(이미 받은 범위인가 · 끝이 최근이면 30분마다 다시) → 받기(포트) → 저장(`store/market.py`)을 여기서 해요.
- 확정: 그날 일봉은 **20:00 뒤**에 확정으로 봐요(20:10 확인이 써요). 그 전에는 앞 거래일까지만 써요.
- 장 시간: 토스 market-calendar(KR)로 그날 열리는지 · 정규장 시작이 몇 시인지 알아요. 정규장이
  09:00보다 늦게 열리는 날(수능일 · 새해 첫 거래일)은 08:30 점검 · 08:35 주문도 같은 만큼 늦춰요(R-O1).
  달력을 받지 못하면 평일 = 거래일로 보고 시각은 그대로예요. 한국 시간 · 장 시간 · 확정 시각 · 휴장 규칙의 정의는
  `domain/markets/kr.py` 한 곳이고, 이 파일은 받아서 담아 두는 일만 해요.
- 일봉 캐시 판단의 '오늘'은 1단계 예외(ARCHITECTURE 6절 · 지금 시계 그대로)라 `app.market.now_kst`를 불러요(기준선 시계 고정
  자리 `tests/baseline/clock.py`가 그 모듈에 닿아요 · Q-N24).
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from ..copy import texts as T
from ..domain.markets.kr import DayHours, weekday_hours
from ..market import now_kst
from ..ports import BrokerError, FeedNotConnected, MarketFeed, SymbolNotFound
from ..store import market as market_store
from ..store.db import DB

INDEX = "KOSPI"
REFRESH_S = 30 * 60
TOSS_NEEDED = "토스 연결이 필요해요 · 시세와 계좌를 토스에서 받아요"
log = logging.getLogger("quant-market")


class MarketDataError(Exception):
    """kind: network(받지 못함) · symbol(그 코드로는 일봉이 없음) · toss(토스 연결 필요)."""

    def __init__(
        self, message: str = "시세를 받지 못했어요", kind: str = "network", symbols: list[str] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.symbols = symbols or []


# ── 장 달력 ──────────────────────────────────────────────────────────────────


class Calendar:
    """토스 market-calendar(KR)를 날짜마다 담아 두고 거래일 · 장 시작을 알려줘요.

    `fetch`는 `MarketFeed` 구현의 `calendar`(토스 어댑터 `MarketCalendar`: today · previous · next 하루씩)예요."""

    def __init__(self, db: DB, fetch: Callable[[date], Any] | None) -> None:
        self.db = db
        self.fetch = fetch

    def _store(self, md: Any) -> None:
        start = md.regular.start.isoformat() if md.regular else None
        self.db.set_meta(f"cal.{md.d.isoformat()}", json.dumps({"open": md.open, "start": start}))

    def _load(self, d: date) -> DayHours | None:
        raw = self.db.get_meta(f"cal.{d.isoformat()}")
        if not raw:
            return None
        data = json.loads(raw)
        start = datetime.fromisoformat(data["start"]) if data.get("start") else None
        return DayHours(d, bool(data["open"]), start, True)

    def day(self, d: date) -> DayHours:
        got = self._load(d)
        if got:
            return got
        if self.fetch is not None:
            try:
                cal = self.fetch(d)
            except (BrokerError, FeedNotConnected, MarketDataError) as exc:
                log.info("market calendar: %s", type(exc).__name__)
            else:
                for md in (cal.today, cal.previous, cal.next):
                    self._store(md)
                got = self._load(d)
                if got:
                    return got
        return weekday_hours(d)

    def is_open(self, d: date) -> bool:
        return self.day(d).open

    def prev_open(self, d: date) -> date:
        d -= timedelta(days=1)
        for _ in range(30):
            if self.is_open(d):
                return d
            d -= timedelta(days=1)
        return d

    def next_open(self, d: date) -> date:
        d += timedelta(days=1)
        for _ in range(30):
            if self.is_open(d):
                return d
            d += timedelta(days=1)
        return d


# ── 일봉 캐시 ────────────────────────────────────────────────────────────────


class Market:
    def __init__(
        self,
        db: DB,
        source: MarketFeed,
        *,
        clock: Callable[[], float] = time.time,
        calendar: Calendar | None = None,
    ) -> None:
        self.db = db
        self.source = source
        self.clock = clock
        self.calendar = calendar or Calendar(db, getattr(source, "calendar", None))

    def _covered(self, symbol: str, start: date, end: date) -> bool:
        """요청한 범위를 이미 받았는가. 끝이 최근(7일 안)이면 30분이 지나면 다시 받는다."""
        row = market_store.bar_meta(self.db, symbol)
        if row is None or not row["from_d"]:
            return False
        if row["from_d"] > start.isoformat() or row["to_d"] < end.isoformat():
            return False
        if end < now_kst().date() - timedelta(days=7):
            return True
        return (self.clock() - float(row["fetched_at"] or 0)) < REFRESH_S

    def _fetch(self, symbol: str, start: date, end: date) -> None:
        try:
            bars = self.source.daily(symbol, start, end)
        except SymbolNotFound:
            raise MarketDataError(
                T.symbol_no_bars.format(codes=symbol), "symbol", [symbol]
            ) from None
        except FeedNotConnected:
            raise MarketDataError(TOSS_NEEDED, "toss") from None
        except MarketDataError:
            raise
        except Exception:  # 전송 오류는 여러 모양으로 와요(응답 없음 · 응답 이상 · 한도)
            bars = []
        if not bars:
            raise MarketDataError(T.market_fetch_failed_for.format(codes=symbol), "network", [symbol])
        market_store.put_bars(self.db, symbol, bars)
        old = market_store.bar_range(self.db, symbol)
        from_d = start.isoformat()
        to_d = end.isoformat()
        if old and old["from_d"]:
            # 가운데가 비지 않을 때만 범위를 넓힌다
            if old["from_d"] <= to_d and old["to_d"] >= from_d:
                from_d = min(from_d, old["from_d"])
                to_d = max(to_d, old["to_d"])
        market_store.put_bar_meta(self.db, symbol, "toss", from_d, to_d, self.clock())

    def bars(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        if not self._covered(symbol, start, end):
            self._fetch(symbol, start, end)
        return market_store.bars_between(self.db, symbol, start.isoformat(), end.isoformat())

    def many(self, symbols: list[str], start: date, end: date) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        failed: list[str] = []
        unknown: list[str] = []
        for s in symbols:
            try:
                out[s] = self.bars(s, start, end)
            except MarketDataError as exc:
                if exc.kind == "toss":
                    raise
                (unknown if exc.kind == "symbol" else failed).append(s)
        if unknown:
            codes = ", ".join(unknown)
            return_err = MarketDataError(
                T.symbol_no_bars.format(codes=codes), "symbol", unknown
            )
            raise return_err
        if failed:
            raise MarketDataError(T.market_fetch_failed_for.format(codes=', '.join(failed)), "network", failed)
        return out
