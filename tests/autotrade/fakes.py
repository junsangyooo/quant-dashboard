"""Fake market sources: a scripted world of daily bars, rate quotes and dividends, and for the
AI rule adjusted closes, valuation ratios and filings (no network)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from autotrade.domain.instruments import Instrument, Market
from autotrade.market.calendar import calendar_for
from autotrade.market.filings import FilingInfo, FilingSourceError
from autotrade.market.service import MarketSources
from autotrade.market.sources import SourceError
from autotrade.market.types import Bar, DividendInfo, FxQuote

KR = "KR:069500"
US = "US:SPYM"


@dataclass
class World:
    """Prices by (instrument, session date) and rates by time, plus switches to break sources."""

    bars: dict[tuple[str, date], Bar] = field(default_factory=dict)
    rates: list[tuple[datetime, Decimal]] = field(default_factory=list)
    fail_bars: set[str] = field(default_factory=set)  # instrument ids whose source errors
    fail_fx: bool = False
    calls: list[str] = field(default_factory=list)
    dividends: list[DividendInfo] = field(default_factory=list)
    fail_dividends: bool = False
    # Phase 2: adjusted closes by Yahoo symbol, ratios by symbol, filings by instrument id,
    # filing texts by receipt/accession number, and errors to raise per filing source.
    adjusted: dict[str, list[tuple[date, Decimal]]] = field(default_factory=dict)
    fail_adjusted: set[str] = field(default_factory=set)
    valuations: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    filings: dict[str, list[FilingInfo]] = field(default_factory=dict)
    filing_errors: dict[str, Exception] = field(default_factory=dict)
    texts: dict[str, str] = field(default_factory=dict)

    def bar(
        self,
        instrument_id: str,
        d: str,
        close: str,
        open_: str | None = None,
        source: str = "fake",
    ) -> None:
        day = date.fromisoformat(d)
        o = Decimal(open_) if open_ is not None else None
        self.bars[(instrument_id, day)] = Bar(instrument_id, day, o, o, o, Decimal(close), source)

    def remove_bar(self, instrument_id: str, d: str) -> None:
        self.bars.pop((instrument_id, date.fromisoformat(d)), None)

    def rate(self, at: datetime, rate: str) -> None:
        self.rates.append((at, Decimal(rate)))
        self.rates.sort()

    def dividend(
        self, instrument_id: str, ex_date: str, per_share: str, pay_date: str | None = None
    ) -> None:
        self.dividends.append(
            DividendInfo(
                instrument_id=instrument_id,
                ex_date=date.fromisoformat(ex_date),
                per_share=Decimal(per_share),
                pay_date=None if pay_date is None else date.fromisoformat(pay_date),
                source="fake-div",
            )
        )

    def series(
        self,
        symbol: str,
        market: Market,
        start: str,
        end: str,
        close: Callable[[int, date], Decimal | str] | Sequence[str] = "100",
    ) -> list[date]:
        """Adjusted closes on the market's trading days in [start, end]; `close` is one price,
        a list (one per session) or a function of (session number, day). Returns the days."""
        cal = calendar_for(market)
        first = date.fromisoformat(start)
        days = ([first] if cal.is_trading_day(first) else []) + cal.trading_days(
            first, date.fromisoformat(end)
        )
        out = []
        for i, d in enumerate(days):
            if isinstance(close, str):
                value = Decimal(close)
            elif callable(close):
                value = Decimal(str(close(i, d)))
            else:
                value = Decimal(close[i])
            out.append((d, value))
        self.adjusted[symbol] = out
        return days

    def filing(
        self,
        instrument_id: str,
        source: str,
        ref: str,
        title: str,
        filed_on: str,
        form: str | None = None,
        items: str | None = None,
        text: str | None = None,
    ) -> FilingInfo:
        info = FilingInfo(
            source=source,
            source_ref=ref,
            form=form or title,
            items=items,
            title=title,
            filed_on=date.fromisoformat(filed_on),
            url=f"https://example.test/{source}/{ref}",
        )
        self.filings.setdefault(instrument_id, []).append(info)
        if text is not None:
            self.texts[ref] = text
        return info

    def sources(self) -> MarketSources:
        return MarketSources(
            kr=FakeBars(self, "fake-kr"),
            us=FakeBars(self, "fake-us"),
            fx=FakeFx(self),
            dividends=FakeDividends(self),
            adjusted=FakeAdjusted(self),
            valuation=FakeValuation(self),
            dart=FakeFilings(self, "dart"),
            edgar=FakeFilings(self, "edgar"),
        )


class FakeBars:
    def __init__(self, world: World, name: str) -> None:
        self.world = world
        self.name = name

    def fetch_daily(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        self.world.calls.append(f"bars:{instrument.instrument_id}:{start}:{end}")
        if instrument.instrument_id in self.world.fail_bars:
            raise SourceError(f"{instrument.instrument_id}: no response")
        return sorted(
            (
                b
                for (iid, d), b in self.world.bars.items()
                if iid == instrument.instrument_id and start <= d <= end
            ),
            key=lambda b: b.session_date,
        )


class FakeFx:
    name = "fake-fx"

    def __init__(self, world: World) -> None:
        self.world = world

    def fetch_quote(self, at: datetime) -> FxQuote:
        self.world.calls.append(f"fx:{at.isoformat()}")
        if self.world.fail_fx:
            raise SourceError("KRW=X: no response")
        best = [(t, r) for t, r in self.world.rates if t <= at]
        if not best:
            raise SourceError("no quote yet")
        t, r = best[-1]
        return FxQuote(r, t, self.name)


class FakeDividends:
    name = "fake-div"

    def __init__(self, world: World) -> None:
        self.world = world

    def fetch_dividends(self, instrument: Instrument, start: date, end: date) -> list[DividendInfo]:
        self.world.calls.append(f"dividends:{instrument.instrument_id}:{start}:{end}")
        if self.world.fail_dividends:
            raise SourceError("dividends: no response")
        return [
            d
            for d in self.world.dividends
            if d.instrument_id == instrument.instrument_id and start <= d.ex_date <= end
        ]


class FakeAdjusted:
    name = "fake-adjusted"

    def __init__(self, world: World) -> None:
        self.world = world

    def fetch_adjusted(self, symbol: str, start: date, end: date) -> list[tuple[date, Decimal]]:
        self.world.calls.append(f"adjusted:{symbol}:{start}:{end}")
        if symbol in self.world.fail_adjusted:
            raise SourceError(f"{symbol}: no response")
        return [(d, c) for d, c in self.world.adjusted.get(symbol, []) if start <= d <= end]


class FakeValuation:
    name = "fake-valuation"

    def __init__(self, world: World) -> None:
        self.world = world

    def fetch_valuation(self, symbol: str) -> dict[str, Decimal]:
        self.world.calls.append(f"valuation:{symbol}")
        if symbol not in self.world.valuations:
            raise SourceError(f"{symbol}: no ratios")
        return dict(self.world.valuations[symbol])


class FakeFilings:
    def __init__(self, world: World, name: str) -> None:
        self.world = world
        self.name = name

    def fetch_filings(self, instrument: Instrument, start: date, end: date) -> list[FilingInfo]:
        self.world.calls.append(f"filings:{self.name}:{instrument.instrument_id}:{start}:{end}")
        error = self.world.filing_errors.get(self.name)
        if error is not None:
            raise error
        return [
            f
            for f in self.world.filings.get(instrument.instrument_id, [])
            if f.source == self.name and start <= f.filed_on <= end
        ]

    def fetch_text(self, filing: FilingInfo) -> str:
        self.world.calls.append(f"text:{self.name}:{filing.source_ref}")
        error = self.world.filing_errors.get(self.name)
        if error is not None:
            raise error
        if filing.source_ref not in self.world.texts:
            raise FilingSourceError(f"{filing.source_ref}: no text")
        return self.world.texts[filing.source_ref]
