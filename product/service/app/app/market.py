"""일봉: 야후 금융(yfinance)에서 받아 SQLite에 담아 둔다.

참고: 이 레포의 autotrade/market/sources.py YahooBarSource.
한국 종목은 '.KS'로 먼저 받고, 비면 '.KQ'로 받는다. 코스피 지수는 '^KS11'.
auto_adjust=False: 체결 가격은 실제 시가 · 종가 그대로(분할만 야후가 맞춰 준다).
"""

from __future__ import annotations

import importlib
import logging
import os
import time
import warnings
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any, Protocol

from .db import DB

KST = timezone(timedelta(hours=9))
INDEX = "^KS11"
# 장 마감(15:30) 뒤 야후가 그날 일봉을 굳히는 때. 이전이면 오늘 일봉은 아직 덜 된 것으로 본다.
BAR_FINAL_AT = (15, 50)
REFRESH_S = 30 * 60


class MarketDataError(Exception):
    """kind: network(받지 못함) · symbol(그 코드로는 일봉이 없음)."""

    def __init__(
        self, message: str = "시세를 받지 못했어요", kind: str = "network", symbols: list[str] | None = None
    ) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.symbols = symbols or []


# 바깥 라이브러리의 경고 · 오류 글은 server.log에 쓰지 않는다(접속 주소와 상태 코드만 남긴다)
for _name in ("yfinance", "peewee", "urllib3"):
    logging.getLogger(_name).setLevel(logging.CRITICAL)
    logging.getLogger(_name).propagate = False


class BarSource(Protocol):
    def daily(self, yahoo_symbol: str, start: date, end: date) -> list[dict[str, Any]]: ...


class YahooSource:
    def __init__(self, yf_module: Any | None = None, cache_dir: str | None = None) -> None:
        self._yf = yf_module
        self._cache_dir = cache_dir

    def _module(self) -> Any:
        if self._yf is None:
            yf = importlib.import_module("yfinance")
            if self._cache_dir:
                # 야후 캐시(시간대 · 쿠키)도 데이터 폴더 안에 둔다
                os.makedirs(self._cache_dir, exist_ok=True)
                yf.set_tz_cache_location(self._cache_dir)
            self._yf = yf
        return self._yf

    def daily(self, yahoo_symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        ticker = self._module().Ticker(yahoo_symbol)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            frame = ticker.history(
                start=start.isoformat(),
                end=(end + timedelta(days=1)).isoformat(),
                interval="1d",
                auto_adjust=False,
                actions=False,
            )
        if frame is None or len(frame) == 0:
            return []
        out = []
        for idx, row in frame.iterrows():
            close = _f(row.get("Close"))
            if close is None or close <= 0:
                continue
            out.append(
                {
                    "d": idx.date().isoformat(),
                    "o": _f(row.get("Open")) or close,
                    "h": _f(row.get("High")) or close,
                    "l": _f(row.get("Low")) or close,
                    "c": close,
                    "v": _f(row.get("Volume")) or 0.0,
                }
            )
        return out


def _f(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:  # NaN
        return None
    return out


def now_kst() -> datetime:
    return datetime.now(KST)


def complete_until(now: datetime) -> date:
    """판단에 쓸 수 있는 마지막 일봉 날짜(오늘 일봉은 장 마감 뒤에만)."""
    local = now.astimezone(KST)
    if (local.hour, local.minute) >= BAR_FINAL_AT:
        return local.date()
    return local.date() - timedelta(days=1)


class Market:
    def __init__(
        self,
        db: DB,
        source: BarSource,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.db = db
        self.source = source
        self.clock = clock

    def _covered(self, symbol: str, start: date, end: date) -> bool:
        """요청한 범위를 이미 받았는가. 끝이 최근(7일 안)이면 30분이 지나면 다시 받는다."""
        row = self.db.one("SELECT * FROM bar_meta WHERE symbol=?", (symbol,))
        if row is None or not row["from_d"]:
            return False
        if row["from_d"] > start.isoformat() or row["to_d"] < end.isoformat():
            return False
        if end < now_kst().date() - timedelta(days=7):
            return True
        return (self.clock() - float(row["fetched_at"] or 0)) < REFRESH_S

    def _fetch(self, symbol: str, start: date, end: date) -> None:
        if symbol.startswith("^"):
            candidates = [symbol]
        else:
            row = self.db.one("SELECT yahoo FROM bar_meta WHERE symbol=?", (symbol,))
            known = row["yahoo"] if row and row["yahoo"] else None
            candidates = [known] if known else [f"{symbol}.KS", f"{symbol}.KQ"]
        bars: list[dict[str, Any]] = []
        used = None
        for ysym in candidates:
            try:
                bars = self.source.daily(ysym, start, end)
            except Exception:  # yfinance는 네트워크 오류를 여러 모양으로 던진다
                bars = []
            if bars:
                used = ysym
                break
        if not bars:
            raise MarketDataError(f"시세를 받지 못했어요 · {symbol}", "network", [symbol])
        self.db.many(
            "INSERT INTO bars(symbol,d,o,h,l,c,v) VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(symbol,d) DO UPDATE SET o=excluded.o,h=excluded.h,l=excluded.l,"
            "c=excluded.c,v=excluded.v",
            [(symbol, b["d"], b["o"], b["h"], b["l"], b["c"], b["v"]) for b in bars],
        )
        old = self.db.one("SELECT from_d, to_d FROM bar_meta WHERE symbol=?", (symbol,))
        from_d = start.isoformat()
        to_d = end.isoformat()
        if old and old["from_d"]:
            # 가운데가 비지 않을 때만 범위를 넓힌다
            if old["from_d"] <= to_d and old["to_d"] >= from_d:
                from_d = min(from_d, old["from_d"])
                to_d = max(to_d, old["to_d"])
        self.db.run(
            "INSERT INTO bar_meta(symbol,yahoo,from_d,to_d,fetched_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(symbol) DO UPDATE SET yahoo=excluded.yahoo, from_d=excluded.from_d,"
            "to_d=excluded.to_d, fetched_at=excluded.fetched_at",
            (symbol, used, from_d, to_d, self.clock()),
        )

    def bars(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        if not self._covered(symbol, start, end):
            self._fetch(symbol, start, end)
        rows = self.db.all(
            "SELECT d,o,h,l,c,v FROM bars WHERE symbol=? AND d>=? AND d<=? ORDER BY d",
            (symbol, start.isoformat(), end.isoformat()),
        )
        return [dict(r) for r in rows]

    def many(self, symbols: list[str], start: date, end: date) -> dict[str, list[dict[str, Any]]]:
        out: dict[str, list[dict[str, Any]]] = {}
        failed: list[str] = []
        for s in symbols:
            try:
                out[s] = self.bars(s, start, end)
            except MarketDataError:
                failed.append(s)
        if failed:
            raise self._why_failed(failed, end)
        return out

    def _why_failed(self, failed: list[str], end: date) -> MarketDataError:
        """일봉이 없는 종목 코드인지, 받지 못한 것인지 가른다.

        야후는 없는 코드와 끊긴 네트워크를 똑같이 '빈 응답'으로 돌려준다. 그래서 늘 있는 코스피 지수를
        한 번 받아 본다: 지수는 받히면 코드 문제, 지수도 안 받히면 네트워크 문제.
        """
        try:
            probe = self.source.daily(INDEX, end - timedelta(days=14), end)
        except Exception:  # 네트워크 오류는 여러 모양으로 온다
            probe = []
        if probe:
            codes = ", ".join(failed)
            return MarketDataError(
                f"일봉이 없는 종목 코드가 있어요 · {codes} · 종목 코드를 확인해 주세요", "symbol", failed
            )
        return MarketDataError(f"시세를 받지 못했어요 · {', '.join(failed)}", "network", failed)
