"""Fetch public data into the store, and read it back with its freshness.

Fetching (network) happens before a job opens its write transaction; every value is stored with
its source and the time it was fetched. Reading never touches the network.

A bar for a session that has not closed yet can be stored (the paper executor needs today's open),
so closes are always read up to the latest session that has closed by the reading time.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal

from autotrade.config import Config
from autotrade.db import repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Instrument, Market
from autotrade.market.calendar import calendar_for
from autotrade.market.freshness import (
    Freshness,
    Series,
    expected_session,
    fx_freshness,
    quote_freshness,
)
from autotrade.market.sources import (
    BarSource,
    FallbackBarSource,
    FxSource,
    PykrxBarSource,
    RetryingBarSource,
    RetryingFxSource,
    YahooBarSource,
    YahooFxSource,
)
from autotrade.market.types import Bar, FxQuote
from autotrade.timeutil import require_aware

SERIES_OF_MARKET = {Market.KR: Series.KR_QUOTES, Market.US: Series.US_QUOTES}


@dataclass(frozen=True)
class MarketSources:
    kr: BarSource
    us: BarSource
    fx: FxSource


def default_sources() -> MarketSources:
    """The phase-1 public sources: Yahoo for Korea (pykrx as fallback), the US and the rate.

    Yahoo first (owner's decision 2026-10-09): pykrx's ETF lookup needs a KRX login, and logging
    in would share the screener cron's KRX session (ops notes §8).
    """
    return MarketSources(
        kr=FallbackBarSource(
            [RetryingBarSource(YahooBarSource()), RetryingBarSource(PykrxBarSource())]
        ),
        us=RetryingBarSource(YahooBarSource()),
        fx=RetryingFxSource(YahooFxSource()),
    )


@dataclass
class FetchErrors:
    """What could not be fetched in this job (instrument id -> error, and the rate)."""

    bars: dict[str, str] = field(default_factory=dict)
    fx: str | None = None

    def for_market(self, market: Market, instruments: Iterable[Instrument]) -> str | None:
        msgs = [
            self.bars[i.instrument_id]
            for i in instruments
            if i.market is market and i.instrument_id in self.bars
        ]
        return "; ".join(msgs) if msgs else None


def _lag(cfg: Config, market: Market) -> timedelta:
    return cfg.kr_publication_lag if market is Market.KR else cfg.us_publication_lag


def prefetch_bars(
    conn: sqlite3.Connection,
    sources: MarketSources,
    instruments: Iterable[Instrument],
    start: date,
    end: date,
    at: datetime,
) -> dict[str, str]:
    """Download daily bars and store them. Returns errors by instrument id."""
    errors: dict[str, str] = {}
    for inst in instruments:
        source = sources.kr if inst.market is Market.KR else sources.us
        bars: list[Bar] = []
        error: str | None = None
        try:
            bars = source.fetch_daily(inst, start, end)
        except Exception as exc:  # any source failure is recorded, never raised
            error = f"{type(exc).__name__}: {exc}"
            errors[inst.instrument_id] = error
        with transaction(conn):
            repo.upsert_bars(conn, bars, at)
            repo.record_fetch(
                conn,
                SERIES_OF_MARKET[inst.market].value,
                attempted_at=at,
                source=bars[0].source if bars else None,
                error=error,
            )
    return errors


def prefetch_fx(conn: sqlite3.Connection, sources: MarketSources, at: datetime) -> str | None:
    """Download the rate at `at` and store it. Returns the error, if any."""
    quote: FxQuote | None = None
    error: str | None = None
    try:
        quote = sources.fx.fetch_quote(at)
    except Exception as exc:  # recorded, never raised
        error = f"{type(exc).__name__}: {exc}"
    with transaction(conn):
        if quote is not None:
            repo.insert_fx(conn, quote, at)
        repo.record_fetch(
            conn,
            Series.FX.value,
            attempted_at=at,
            source=None if quote is None else quote.source,
            error=error,
        )
    return error


@dataclass(frozen=True)
class Close:
    instrument_id: str
    session_date: date
    price: Decimal
    source: str


def latest_close(
    conn: sqlite3.Connection, cfg: Config, inst: Instrument, at: datetime
) -> Close | None:
    """The newest close of a session that had closed (and been published) by `at`."""
    require_aware(at)
    cal = calendar_for(inst.market)
    last_closed = expected_session(cal, at, _lag(cfg, inst.market))
    bar = repo.latest_bar(conn, inst.instrument_id, last_closed)
    if bar is None:
        return None
    return Close(inst.instrument_id, bar.session_date, bar.close, bar.source)


def market_freshness(
    conn: sqlite3.Connection,
    cfg: Config,
    market: Market,
    instruments: Iterable[Instrument],
    at: datetime,
) -> Freshness:
    """Freshness of one market = its stalest instrument."""
    cal = calendar_for(market)
    latest: date | None = None
    any_missing = False
    seen = False
    for inst in instruments:
        if inst.market is not market:
            continue
        seen = True
        close = latest_close(conn, cfg, inst, at)
        if close is None:
            any_missing = True
            continue
        latest = close.session_date if latest is None else min(latest, close.session_date)
    if not seen:
        raise ValueError(f"no {market.value} instruments")
    return quote_freshness(
        SERIES_OF_MARKET[market], cal, None if any_missing else latest, at, _lag(cfg, market)
    )


def rate_freshness(
    conn: sqlite3.Connection, cfg: Config, at: datetime
) -> tuple[Freshness, FxQuote | None]:
    quote = repo.fx_at(conn, at)
    return fx_freshness(None if quote is None else quote.as_of, at, cfg.fx_max_age), quote


def record_freshness(conn: sqlite3.Connection, fresh: Freshness, at: datetime) -> None:
    repo.record_state(
        conn,
        fresh.series.value,
        state=fresh.state.value,
        basis=fresh.basis,
        expected=fresh.expected,
        missing_sessions=fresh.missing_sessions,
        at=at,
    )
