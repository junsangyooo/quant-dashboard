"""Is a price or a rate fresh enough to trade on? (ops notes step 1, 인계 8)

A market's closes are stale when the latest stored close is older than the latest session that
should be published by now, counted on that market's own calendar: at 10/07 16:10 KST the
expected US close is 10/06 (ET); a book stuck at 10/02 is '2거래일째 갱신 없음' (10/05, 10/06).

The rate is stale when its quote is older than a limit counted in weekday hours (the FX market
does not trade on weekends, so a Friday-night quote is still fresh on Monday morning).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum

from autotrade.market.calendar import ExchangeCalendar
from autotrade.timeutil import KST, require_aware


class FreshState(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"  # nothing stored yet


class Series(str, Enum):
    KR_QUOTES = "kr-quotes"
    US_QUOTES = "us-quotes"
    FX = "fx"


@dataclass(frozen=True)
class Freshness:
    series: Series
    state: FreshState
    basis: str | None  # close date (YYYY-MM-DD) or quote time (ISO)
    expected: str | None  # the close date (or 'now') that should be there
    missing_sessions: int  # quotes: sessions without a close; fx: 0

    @property
    def usable(self) -> bool:
        return self.state is FreshState.FRESH


def expected_session(cal: ExchangeCalendar, at: datetime, lag: timedelta) -> date:
    """Latest session whose close (+ publication lag) has passed at `at`."""
    require_aware(at)
    d = cal.latest_trading_day(at.astimezone(cal.tz).date())
    while cal.session_close(d) + lag > at:
        d = cal.previous_trading_day(d)
    return d


def quote_freshness(
    series: Series, cal: ExchangeCalendar, latest: date | None, at: datetime, lag: timedelta
) -> Freshness:
    exp = expected_session(cal, at, lag)
    if latest is None:
        return Freshness(series, FreshState.UNKNOWN, None, exp.isoformat(), 0)
    if latest >= exp:
        return Freshness(series, FreshState.FRESH, latest.isoformat(), exp.isoformat(), 0)
    missing = len(cal.trading_days(latest, exp))
    return Freshness(series, FreshState.STALE, latest.isoformat(), exp.isoformat(), missing)


def weekday_age(as_of: datetime, at: datetime) -> timedelta:
    """Time from as_of to at, not counting Saturdays and Sundays (KST)."""
    require_aware(as_of)
    require_aware(at)
    if at <= as_of:
        return timedelta(0)
    total = timedelta(0)
    cur = as_of.astimezone(KST)
    end = at.astimezone(KST)
    while cur < end:
        next_midnight = datetime.combine(cur.date() + timedelta(days=1), datetime.min.time(), KST)
        stop = min(next_midnight, end)
        if cur.weekday() < 5:
            total += stop - cur
        cur = stop
    return total


def fx_freshness(as_of: datetime | None, at: datetime, max_age: timedelta) -> Freshness:
    if as_of is None:
        return Freshness(Series.FX, FreshState.UNKNOWN, None, None, 0)
    state = FreshState.FRESH if weekday_age(as_of, at) <= max_age else FreshState.STALE
    return Freshness(Series.FX, state, as_of.isoformat(), None, 0)
