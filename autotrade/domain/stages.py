"""Stage plan and times: sell -> FX -> buy (ops notes step 6, 인계 3).

Times are KST and come from the exchange calendars, never hard-coded offsets:

- Korean orders: KRX open + 5 min (09:05; 10:05 on late-open days such as the first trading
  day of the year and the college entrance exam day).
- FX: 09:10 on KRX trading days, and never earlier than KRX open + 10 min.
- US orders: the NYSE open, 09:30 New York time = 22:30 KST in US daylight time, 23:30 otherwise.

A stage that waits on another runs at its market's next slot after that stage. When the slot of
the day has passed but the market is still open, it runs 5 minutes later (a Korean buy funded by a
09:10 USD->KRW conversion runs at 09:15); otherwise it rolls to the next trading day.
A stage in a closed market therefore rolls to that market's next session: only the closed market's
orders wait (ops notes step 2).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from enum import Enum
from typing import Protocol

from autotrade.domain.planner import FxDirection, Plan, StageKind
from autotrade.timeutil import ET, KST, at_kst, ceil_minute

MAX_ROLL_DAYS = 30


class StageMarket(str, Enum):
    KR = "KR"
    US = "US"
    FX = "FX"


class SessionCalendar(Protocol):
    """What scheduling needs from an exchange calendar (see autotrade/market/calendar.py)."""

    def is_trading_day(self, d: date) -> bool: ...

    def session_open(self, d: date) -> datetime: ...

    def session_close(self, d: date) -> datetime: ...

    def next_trading_day(self, d: date) -> date: ...


@dataclass(frozen=True)
class StageTimes:
    kr_order_delay: timedelta = timedelta(minutes=5)
    fx_time: time = time(9, 10)
    fx_min_after_open: timedelta = timedelta(minutes=10)
    us_order_delay: timedelta = timedelta(0)
    follow_delay: timedelta = timedelta(minutes=5)
    close_cutoff: timedelta = timedelta(minutes=10)


@dataclass(frozen=True)
class StageSpec:
    seq: int
    kind: StageKind
    market: StageMarket
    depends_on: tuple[int, ...]


class Slotter:
    """Maps 'not before t' to the next allowed order time for a stage market."""

    def __init__(
        self, krx: SessionCalendar, nyse: SessionCalendar, times: StageTimes | None = None
    ) -> None:
        self.krx = krx
        self.nyse = nyse
        self.times = times or StageTimes()

    def _calendar(self, market: StageMarket) -> SessionCalendar:
        return self.nyse if market is StageMarket.US else self.krx

    def _local_date(self, market: StageMarket, t: datetime) -> date:
        return t.astimezone(ET if market is StageMarket.US else KST).date()

    def nominal(self, market: StageMarket, d: date) -> datetime:
        """The usual order time on trading day d (d is the exchange's local date)."""
        cal = self._calendar(market)
        opening = cal.session_open(d)
        if market is StageMarket.KR:
            return opening + self.times.kr_order_delay
        if market is StageMarket.US:
            return opening + self.times.us_order_delay
        return max(at_kst(d, self.times.fx_time), opening + self.times.fx_min_after_open)

    def slot_after(self, market: StageMarket, t: datetime) -> datetime:
        cal = self._calendar(market)
        d = self._local_date(market, t)
        for _ in range(MAX_ROLL_DAYS):
            if cal.is_trading_day(d):
                nominal = self.nominal(market, d)
                if t <= nominal:
                    return nominal
                candidate = ceil_minute(t + self.times.follow_delay)
                if candidate <= cal.session_close(d) - self.times.close_cutoff:
                    return candidate
            d = cal.next_trading_day(d)
        raise RuntimeError(f"no {market.value} slot within {MAX_ROLL_DAYS} days of {t}")

    def retry_slot(self, market: StageMarket, failed_due: datetime) -> datetime:
        """'다음 날 같은 시각': the usual time on the market's next trading day."""
        cal = self._calendar(market)
        d = cal.next_trading_day(self._local_date(market, failed_due))
        return self.nominal(market, d)


def stage_specs(plan: Plan) -> list[StageSpec]:
    """Stages for a plan in execution order, with their dependencies (by seq)."""
    specs: list[StageSpec] = []
    seq_of: dict[tuple[StageKind, StageMarket], int] = {}

    def add(kind: StageKind, market: StageMarket, deps: Sequence[int]) -> None:
        seq = len(specs) + 1
        specs.append(StageSpec(seq, kind, market, tuple(deps)))
        seq_of[(kind, market)] = seq

    def dep(kind: StageKind, market: StageMarket) -> list[int]:
        found = seq_of.get((kind, market))
        return [found] if found is not None else []

    sell_markets = {o.market.value for o in plan.sells}
    buy_markets = {o.market.value for o in plan.buys}
    for m in (StageMarket.KR, StageMarket.US):
        if m.value in sell_markets:
            add(StageKind.SELL, m, [])
    if plan.fx is not None:
        if plan.fx.direction is FxDirection.KRW_TO_USD:
            add(StageKind.FX, StageMarket.FX, dep(StageKind.SELL, StageMarket.KR))
        else:
            add(StageKind.FX, StageMarket.FX, dep(StageKind.SELL, StageMarket.US))
    fx_dir = plan.fx.direction if plan.fx is not None else None
    if StageMarket.KR.value in buy_markets:
        deps = dep(StageKind.SELL, StageMarket.KR)
        if fx_dir is FxDirection.USD_TO_KRW:
            deps += dep(StageKind.FX, StageMarket.FX)
        add(StageKind.BUY, StageMarket.KR, deps)
    if StageMarket.US.value in buy_markets:
        deps = dep(StageKind.SELL, StageMarket.US)
        if fx_dir is FxDirection.KRW_TO_USD:
            deps += dep(StageKind.FX, StageMarket.FX)
        add(StageKind.BUY, StageMarket.US, deps)
    return specs


def schedule(
    specs: Sequence[StageSpec], not_before: datetime, slotter: Slotter
) -> dict[int, datetime]:
    """Due time for every stage; specs must be in dependency order."""
    due: dict[int, datetime] = {}
    for spec in specs:
        after = max([not_before, *(due[d] for d in spec.depends_on)])
        due[spec.seq] = slotter.slot_after(spec.market, after)
    return due
