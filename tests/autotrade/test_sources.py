"""Public source adapters, exercised with stand-in pykrx / yfinance modules (no network)."""

from __future__ import annotations

import importlib
import os
import time
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from autotrade.domain.instruments import Currency, Instrument, Kind, Market, kr_etf, us_etf
from autotrade.market import sources as src
from autotrade.market.service import default_sources
from autotrade.market.sources import (
    FallbackBarSource,
    PykrxBarSource,
    RetryingBarSource,
    RetryingFxSource,
    SourceError,
    YahooBarSource,
    YahooFxSource,
    with_retries,
)
from autotrade.market.types import Bar, FxQuote

from .helpers import kst

D = Decimal
KOSPI = kr_etf("069500", "KOSPI200 ETF")
SNP = us_etf("SPYM", "S&P 500 ETF")
SAMSUNG = Instrument(
    "KR:005930", Market.KR, Currency.KRW, Kind.STOCK, "005930", "삼성전자", "005930.KS"
)


def krx_frame() -> pd.DataFrame:
    idx = pd.to_datetime(["2026-10-06", "2026-10-07", "2026-10-08"])
    return pd.DataFrame(
        {
            "시가": [36300.0, 36380.0, 0.0],
            "고가": [36500.0, 36400.0, 0.0],
            "저가": [36200.0, 36100.0, 0.0],
            "종가": [36360.0, 36250.0, 36250.0],
            "거래량": [1, 2, 0],
        },
        index=idx,
    )


def test_pykrx_adapter_reads_etf_and_stock_frames() -> None:
    calls: list[tuple[str, str, str, str]] = []

    def etf(start: str, end: str, ticker: str) -> pd.DataFrame:
        calls.append(("etf", start, end, ticker))
        return krx_frame()

    def stock(start: str, end: str, ticker: str) -> pd.DataFrame:
        calls.append(("stock", start, end, ticker))
        return krx_frame().iloc[:0]

    module = SimpleNamespace(get_etf_ohlcv_by_date=etf, get_market_ohlcv_by_date=stock)
    bars = PykrxBarSource(module).fetch_daily(KOSPI, date(2026, 10, 6), date(2026, 10, 8))
    assert calls[0] == ("etf", "20261006", "20261008", "069500")
    assert [(b.session_date, b.open, b.close, b.source) for b in bars] == [
        (date(2026, 10, 6), D("36300"), D("36360"), "pykrx"),
        (date(2026, 10, 7), D("36380"), D("36250"), "pykrx"),
        (date(2026, 10, 8), None, D("36250"), "pykrx"),  # no trades: open reported as 0
    ]
    assert PykrxBarSource(module).fetch_daily(SAMSUNG, date(2026, 10, 6), date(2026, 10, 8)) == []
    assert calls[-1][0] == "stock"


def test_pykrx_is_imported_without_krx_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_import(name: str) -> Any:
        seen["name"] = name
        seen["krx_id"] = os.environ.get("KRX_ID")
        return SimpleNamespace()

    monkeypatch.setenv("KRX_ID", "someone")
    monkeypatch.setenv("KRX_PW", "secret")
    monkeypatch.setattr(importlib, "import_module", fake_import)
    src.import_pykrx_stock()
    assert seen == {"name": "pykrx.stock", "krx_id": None}
    assert os.environ["KRX_ID"] == "someone"  # restored afterwards


class FakeTicker:
    def __init__(self, frame: pd.DataFrame | None) -> None:
        self.frame = frame
        self.kwargs: dict[str, Any] = {}

    def history(self, **kwargs: Any) -> pd.DataFrame | None:
        self.kwargs = kwargs
        return self.frame


def yahoo(frame: pd.DataFrame | None) -> tuple[SimpleNamespace, FakeTicker]:
    ticker = FakeTicker(frame)
    return SimpleNamespace(Ticker=lambda symbol: ticker), ticker


def test_yahoo_daily_bars_use_exchange_dates_and_raw_prices() -> None:
    idx = pd.DatetimeIndex(["2026-10-06 00:00", "2026-10-07 00:00"]).tz_localize("America/New_York")
    frame = pd.DataFrame(
        {
            "Open": [62.10000228881836, 62.5],
            "High": [62.6, 62.9],
            "Low": [61.9, 62.2],
            "Close": [62.400001525878906, float("nan")],
        },
        index=idx,
    )
    module, ticker = yahoo(frame)
    bars = YahooBarSource(module).fetch_daily(SNP, date(2026, 10, 6), date(2026, 10, 7))
    assert [(b.session_date, b.open, b.close) for b in bars] == [
        (date(2026, 10, 6), D("62.10"), D("62.40"))
    ]
    assert ticker.kwargs["auto_adjust"] is False
    assert ticker.kwargs["end"] == "2026-10-08"
    module, _ = yahoo(None)
    assert YahooBarSource(module).fetch_daily(SNP, date(2026, 10, 6), date(2026, 10, 7)) == []


def test_yahoo_rate_is_the_last_minute_at_or_before() -> None:
    idx = pd.DatetimeIndex(
        ["2026-10-07 00:08", "2026-10-07 00:09", "2026-10-07 00:11"]
    ).tz_localize("UTC")
    frame = pd.DataFrame({"Close": [1380.5, 1380.63999, 1381.0]}, index=idx)
    module, _ = yahoo(frame)
    quote = YahooFxSource(module).fetch_quote(kst("2026-10-07 09:10"))
    assert quote == FxQuote(
        D("1380.6"), datetime(2026, 10, 7, 0, 9, tzinfo=timezone.utc), "yfinance"
    )
    with pytest.raises(SourceError):
        YahooFxSource(module).fetch_quote(kst("2026-10-07 09:00"))
    naive = pd.DataFrame({"Close": [1380.0]}, index=pd.DatetimeIndex(["2026-10-07 00:05"]))
    module, _ = yahoo(naive)
    assert YahooFxSource(module).fetch_quote(kst("2026-10-07 09:10")).rate == D("1380.0")


class Flaky:
    name = "flaky"

    def __init__(self, failures: int, bars: list[Bar]) -> None:
        self.failures = failures
        self.bars = bars

    def fetch_daily(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        if self.failures > 0:
            self.failures -= 1
            raise ConnectionError("reset")
        return self.bars


def test_fallback_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    bar = Bar(KOSPI.instrument_id, date(2026, 10, 6), None, None, None, D("1"), "b")
    assert FallbackBarSource([Flaky(1, []), Flaky(0, [bar])]).fetch_daily(
        KOSPI, date.min, date.max
    ) == [bar]
    assert (
        FallbackBarSource([Flaky(0, []), Flaky(0, [])]).fetch_daily(KOSPI, date.min, date.max) == []
    )
    with pytest.raises(SourceError, match="flaky"):
        FallbackBarSource([Flaky(1, []), Flaky(1, [])]).fetch_daily(KOSPI, date.min, date.max)
    with pytest.raises(ValueError, match="no sources"):
        FallbackBarSource([])

    slept: list[float] = []
    attempts: list[int] = []

    def fn() -> int:
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("x")
        return 7

    assert with_retries(fn, sleep=slept.append) == 7
    assert slept == [2.0]
    with pytest.raises(SourceError, match="RuntimeError: no"):
        with_retries(lambda: (_ for _ in ()).throw(RuntimeError("no")), sleep=slept.append)

    monkeypatch.setattr(time, "sleep", lambda s: None)
    assert RetryingBarSource(Flaky(1, [bar])).fetch_daily(KOSPI, date.min, date.max) == [bar]

    class FxOnce:
        name = "fx"
        calls = 0

        def fetch_quote(self, at: datetime) -> FxQuote:
            FxOnce.calls += 1
            if FxOnce.calls == 1:
                raise TimeoutError
            return FxQuote(D("1"), at, "fx")

    assert RetryingFxSource(FxOnce()).fetch_quote(kst("2026-10-07 09:10")).rate == D("1")


def test_default_sources_import_nothing_until_used() -> None:
    sources = default_sources()
    assert sources.kr.name == "yfinance+pykrx"
    assert sources.us.name == "yfinance"
    assert sources.fx.name == "yfinance"


def test_fallback_fills_only_the_dates_the_first_source_lacks() -> None:
    def bar(d: int, source: str) -> Bar:
        return Bar(KOSPI.instrument_id, date(2026, 10, d), D("1"), None, None, D("1"), source)

    class Fixed:
        def __init__(self, name: str, bars: list[Bar]) -> None:
            self.name = name
            self.bars = bars

        def fetch_daily(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
            return self.bars

    # pykrx has 10/06 but not today's 10/07 during the session; Yahoo fills 10/07 only.
    merged = FallbackBarSource(
        [
            Fixed("pykrx", [bar(6, "pykrx")]),
            Fixed("yfinance", [bar(6, "yfinance"), bar(7, "yfinance")]),
        ]
    ).fetch_daily(KOSPI, date(2026, 10, 1), date(2026, 10, 7))
    assert [(b.session_date.day, b.source) for b in merged] == [(6, "pykrx"), (7, "yfinance")]
    # When the first source covers the newest session, the second is not asked.
    covered = FallbackBarSource([Fixed("pykrx", [bar(7, "pykrx")]), Flaky(5, [])]).fetch_daily(
        KOSPI, date(2026, 10, 1), date(2026, 10, 7)
    )
    assert [b.source for b in covered] == ["pykrx"]


def test_pykrx_printed_errors_become_source_errors(capsys: pytest.CaptureFixture[str]) -> None:
    def etf(start: str, end: str, ticker: str) -> pd.DataFrame:
        print("KRX 로그인 실패: KRX_ID 또는 KRX_PW 환경 변수가 설정되지 않았습니다.")  # noqa: T201
        print("Error occurred in get_etf_ohlcv_by_date: 'isin'")  # noqa: T201
        return pd.DataFrame()

    def quiet(start: str, end: str, ticker: str) -> pd.DataFrame:
        return pd.DataFrame()

    with pytest.raises(SourceError, match="isin"):
        PykrxBarSource(SimpleNamespace(get_etf_ohlcv_by_date=etf)).fetch_daily(
            KOSPI, date(2026, 10, 6), date(2026, 10, 8)
        )
    assert capsys.readouterr().out == ""  # nothing leaks into the JSON output
    assert (
        PykrxBarSource(SimpleNamespace(get_etf_ohlcv_by_date=quiet)).fetch_daily(
            KOSPI, date(2026, 10, 6), date(2026, 10, 8)
        )
        == []
    )
