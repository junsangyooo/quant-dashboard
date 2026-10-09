"""Public market data sources behind small interfaces (read-only, no login).

- Korean daily bars: Yahoo ('069500.KS', ~20 min delayed), falling back to pykrx (its ETF
  lookup needs a KRX login since 1.2.8, so it rarely answers; see service.default_sources).
- US daily bars: Yahoo via yfinance.
- KRW per USD: Yahoo 'KRW=X' (phase 1 source).
- Cash dividends: Yahoo's dividend column (per share by ex-date; Yahoo has no pay dates, so the
  service estimates them, autotrade/domain/dividends.py).

All network access in the engine lives in this module. Tests replace these classes with fakes
(tests/autotrade/fakes.py); the engine only sees the BarSource / FxSource protocols.
Prices are raw (not dividend-adjusted): a stored close must never change after the fact.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import math
import os
import time as _time
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol, TypeVar

from autotrade.domain.instruments import Instrument, Kind
from autotrade.domain.money import dec, normalize_price, round_rate
from autotrade.market.types import Bar, DividendInfo, FxQuote
from autotrade.timeutil import UTC, require_aware

T = TypeVar("T")


class SourceError(RuntimeError):
    """The source did not answer or answered with something unusable."""


class BarSource(Protocol):
    name: str

    def fetch_daily(self, instrument: Instrument, start: date, end: date) -> list[Bar]: ...


class FxSource(Protocol):
    name: str

    def fetch_quote(self, at: datetime) -> FxQuote: ...


class DividendSource(Protocol):
    name: str

    def fetch_dividends(
        self, instrument: Instrument, start: date, end: date
    ) -> list[DividendInfo]: ...


def with_retries(
    fn: Callable[[], T],
    attempts: int = 2,
    delay_s: float = 2.0,
    sleep: Callable[[float], None] | None = None,
) -> T:
    """Call fn, retrying once on any exception (public endpoints blip). Raises SourceError."""
    errors: list[str] = []
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # every failure becomes a SourceError
            errors.append(f"{type(exc).__name__}: {exc}")
            if i + 1 < attempts:
                (sleep or _time.sleep)(delay_s)
    raise SourceError("; ".join(errors))


def _number(value: Any) -> Decimal | None:
    """Decimal from a pandas/numpy scalar; None for NaN or missing."""
    if value is None:
        return None
    as_float = float(value)
    if math.isnan(as_float):
        return None
    return dec(as_float)


def import_pykrx_stock() -> Any:
    """pykrx's stock module, imported without KRX credentials in the environment.

    pykrx logs in to KRX at import time when KRX_ID/KRX_PW are set (ops notes §8), which
    would fight the screener cron for the same account. What it prints is swallowed: the jobs'
    stdout is JSON.
    """
    saved = {k: os.environ.pop(k) for k in ("KRX_ID", "KRX_PW") if k in os.environ}
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return importlib.import_module("pykrx.stock")
    finally:
        os.environ.update(saved)


class PykrxBarSource:
    name = "pykrx"

    def __init__(self, stock_module: Any | None = None) -> None:
        self._stock = stock_module

    def _module(self) -> Any:
        if self._stock is None:
            self._stock = import_pykrx_stock()
        return self._stock

    def fetch_daily(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        stock = self._module()
        fn = (
            stock.get_etf_ohlcv_by_date
            if instrument.kind is Kind.ETF
            else stock.get_market_ohlcv_by_date
        )
        # pykrx reports failures by printing ('Error occurred in ...') and returning an empty
        # frame. Measured 2026-10-09 with pykrx 1.2.8: the ETF path needs a KRX login now
        # ("KRX 로그인 실패 ... 'isin'"), so it fails here and the fallback (Yahoo) answers.
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(printed):
            frame = fn(start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), instrument.ticker)
        if frame is None or len(frame) == 0:
            said = " ".join(printed.getvalue().split())
            if "Error" in said or "실패" in said:
                raise SourceError(f"pykrx: {said[:300]}")
            return []
        bars: list[Bar] = []
        for idx, row in frame.iterrows():
            close = _number(row["종가"])
            if close is None or close <= 0:
                continue
            opening = _number(row["시가"])
            high = _number(row["고가"])
            low = _number(row["저가"])
            bars.append(
                Bar(
                    instrument_id=instrument.instrument_id,
                    session_date=idx.date(),
                    # KRX reports 0 for open/high/low on days without trades.
                    open=None if not opening else normalize_price(instrument.currency, opening),
                    high=None if not high else normalize_price(instrument.currency, high),
                    low=None if not low else normalize_price(instrument.currency, low),
                    close=normalize_price(instrument.currency, close),
                    source=self.name,
                )
            )
        return bars


def import_yfinance() -> Any:
    return importlib.import_module("yfinance")


class YahooBarSource:
    name = "yfinance"

    def __init__(self, yf_module: Any | None = None) -> None:
        self._yf = yf_module

    def _module(self) -> Any:
        if self._yf is None:
            self._yf = import_yfinance()
        return self._yf

    def fetch_daily(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        ticker = self._module().Ticker(instrument.yahoo_symbol)
        frame = ticker.history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=False,
        )
        if frame is None or len(frame) == 0:
            return []
        bars: list[Bar] = []
        for idx, row in frame.iterrows():
            close = _number(row["Close"])
            if close is None or close <= 0:
                continue
            opening = _number(row["Open"])
            high = _number(row["High"])
            low = _number(row["Low"])
            bars.append(
                Bar(
                    instrument_id=instrument.instrument_id,
                    # The index is in the exchange's time zone, so .date() is the session date.
                    session_date=idx.date(),
                    open=None if not opening else normalize_price(instrument.currency, opening),
                    high=None if not high else normalize_price(instrument.currency, high),
                    low=None if not low else normalize_price(instrument.currency, low),
                    close=normalize_price(instrument.currency, close),
                    source=self.name,
                )
            )
        return bars


class FallbackBarSource:
    """Ask sources in order until the newest requested session is covered.

    Earlier sources win for the dates they have; later ones only fill gaps. This also covers
    a session that is still trading: pykrx may not list today's bar until after the close while
    Yahoo already shows today's open (20-minute delay). Fails only if every source fails.
    """

    def __init__(self, sources: Sequence[BarSource]) -> None:
        if not sources:
            raise ValueError("no sources")
        self.sources = list(sources)
        self.name = "+".join(s.name for s in self.sources)

    def fetch_daily(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        errors: list[str] = []
        merged: dict[date, Bar] = {}
        for source in self.sources:
            try:
                bars = source.fetch_daily(instrument, start, end)
            except Exception as exc:  # fall through to the next source
                errors.append(f"{source.name}: {type(exc).__name__}: {exc}")
                continue
            for bar in bars:
                merged.setdefault(bar.session_date, bar)
            if end in merged:
                break
        if not merged and len(errors) == len(self.sources):
            raise SourceError("; ".join(errors))
        return [merged[d] for d in sorted(merged)]


class YahooDividendSource:
    """Cash dividends from Yahoo's daily history ('Dividends' column, by ex-date).

    Measured 2026-10-09 (yfinance 1.3): 069500.KS lists the KODEX 200 distributions on their
    ex-dates (2026-04-29 446, 2026-07-30 183 won), SPYM its quarterly dividends (2026-09-11
    $0.239). Neither has a pay date ('calendar' is empty for both ETFs).
    """

    name = "yfinance"

    def __init__(self, yf_module: Any | None = None) -> None:
        self._yf = yf_module

    def _module(self) -> Any:
        if self._yf is None:
            self._yf = import_yfinance()
        return self._yf

    def fetch_dividends(self, instrument: Instrument, start: date, end: date) -> list[DividendInfo]:
        ticker = self._module().Ticker(instrument.yahoo_symbol)
        frame = ticker.history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=True,
        )
        if frame is None or len(frame) == 0 or "Dividends" not in frame.columns:
            return []
        out: list[DividendInfo] = []
        for idx, row in frame.iterrows():
            amount = _number(row["Dividends"])
            if amount is None or amount <= 0:
                continue
            out.append(
                DividendInfo(
                    instrument_id=instrument.instrument_id,
                    ex_date=idx.date(),  # exchange time zone, like the bars
                    per_share=amount,
                    pay_date=None,
                    source=self.name,
                )
            )
        return out


class YahooFxSource:
    """KRW per USD from Yahoo 'KRW=X': the last 1-minute bar at or before `at`."""

    name = "yfinance"
    symbol = "KRW=X"

    def __init__(self, yf_module: Any | None = None) -> None:
        self._yf = yf_module

    def _module(self) -> Any:
        if self._yf is None:
            self._yf = import_yfinance()
        return self._yf

    def fetch_quote(self, at: datetime) -> FxQuote:
        require_aware(at)
        ticker = self._module().Ticker(self.symbol)
        frame = ticker.history(period="5d", interval="1m", auto_adjust=False, actions=False)
        best: tuple[datetime, Decimal] | None = None
        if frame is not None and len(frame) > 0:
            for idx, row in frame.iterrows():
                stamp: datetime = idx.to_pydatetime()
                if stamp.tzinfo is None:
                    stamp = stamp.replace(tzinfo=UTC)
                close = _number(row["Close"])
                if close is None or close <= 0 or stamp > at:
                    continue
                if best is None or stamp > best[0]:
                    best = (stamp, close)
        if best is None:
            raise SourceError(f"{self.symbol}: no quote at or before {at.isoformat()}")
        return FxQuote(rate=round_rate(best[1]), as_of=best[0].astimezone(UTC), source=self.name)


class RetryingBarSource:
    def __init__(self, inner: BarSource, attempts: int = 2, delay_s: float = 2.0) -> None:
        self.inner = inner
        self.name = inner.name
        self.attempts = attempts
        self.delay_s = delay_s

    def fetch_daily(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        return with_retries(
            lambda: self.inner.fetch_daily(instrument, start, end), self.attempts, self.delay_s
        )


class RetryingFxSource:
    def __init__(self, inner: FxSource, attempts: int = 2, delay_s: float = 2.0) -> None:
        self.inner = inner
        self.name = inner.name
        self.attempts = attempts
        self.delay_s = delay_s

    def fetch_quote(self, at: datetime) -> FxQuote:
        return with_retries(lambda: self.inner.fetch_quote(at), self.attempts, self.delay_s)


class RetryingDividendSource:
    def __init__(self, inner: DividendSource, attempts: int = 2, delay_s: float = 2.0) -> None:
        self.inner = inner
        self.name = inner.name
        self.attempts = attempts
        self.delay_s = delay_s

    def fetch_dividends(self, instrument: Instrument, start: date, end: date) -> list[DividendInfo]:
        return with_retries(
            lambda: self.inner.fetch_dividends(instrument, start, end), self.attempts, self.delay_s
        )
