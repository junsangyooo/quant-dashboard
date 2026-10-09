"""Fake market sources: a scripted world of daily bars and rate quotes (no network)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from autotrade.domain.instruments import Instrument
from autotrade.market.service import MarketSources
from autotrade.market.sources import SourceError
from autotrade.market.types import Bar, FxQuote

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

    def sources(self) -> MarketSources:
        return MarketSources(
            kr=FakeBars(self, "fake-kr"), us=FakeBars(self, "fake-us"), fx=FakeFx(self)
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
