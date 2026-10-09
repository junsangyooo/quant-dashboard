"""Freshness by each market's calendar ('미국 시세 10/02 기준 · 2거래일째 갱신 없음')."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from autotrade.market.calendar import KRX, NYSE
from autotrade.market.freshness import (
    FreshState,
    Series,
    expected_session,
    fx_freshness,
    quote_freshness,
    weekday_age,
)
from autotrade.timeutil import KST

KR_LAG = timedelta(minutes=20)
US_LAG = timedelta(hours=1)


def kst(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=KST)


def test_expected_sessions_at_the_0830_check() -> None:
    at = kst("2026-10-07 08:30")
    assert expected_session(KRX, at, KR_LAG) == date(2026, 10, 6)  # '한국 10/06 종가'
    assert expected_session(NYSE, at, US_LAG) == date(2026, 10, 6)  # '미국 10/06 종가(ET)'


def test_expected_sessions_at_the_1600_snapshot() -> None:
    at = kst("2026-10-07 16:00")
    assert expected_session(KRX, at, KR_LAG) == date(2026, 10, 7)  # Korea today
    assert expected_session(NYSE, at, US_LAG) == date(2026, 10, 6)  # US the night before


def test_holidays_do_not_make_data_stale() -> None:
    # 10/09 is a Korean holiday; at 10/12 08:30 the newest Korean close is 10/08.
    assert expected_session(KRX, kst("2026-10-12 08:30"), KR_LAG) == date(2026, 10, 8)
    assert expected_session(NYSE, kst("2026-07-06 08:30"), US_LAG) == date(2026, 7, 2)


def test_us_closes_stuck_at_1002() -> None:
    f = quote_freshness(Series.US_QUOTES, NYSE, date(2026, 10, 2), kst("2026-10-07 16:10"), US_LAG)
    assert f.state is FreshState.STALE
    assert f.basis == "2026-10-02"
    assert f.expected == "2026-10-06"
    assert f.missing_sessions == 2
    assert not f.usable


def test_fresh_and_unknown() -> None:
    fresh = quote_freshness(
        Series.KR_QUOTES, KRX, date(2026, 10, 6), kst("2026-10-07 08:30"), KR_LAG
    )
    assert fresh.state is FreshState.FRESH
    assert fresh.usable
    unknown = quote_freshness(Series.KR_QUOTES, KRX, None, kst("2026-10-07 08:30"), KR_LAG)
    assert unknown.state is FreshState.UNKNOWN
    assert not unknown.usable


def test_weekday_age_skips_weekends() -> None:
    friday_night = kst("2026-10-09 23:00")
    monday = kst("2026-10-12 08:30")
    assert weekday_age(friday_night, monday) == timedelta(hours=9, minutes=30)
    assert weekday_age(monday, friday_night) == timedelta(0)


def test_fx_freshness() -> None:
    at = kst("2026-10-07 08:30")
    assert fx_freshness(kst("2026-10-07 08:29"), at, timedelta(hours=24)).state is FreshState.FRESH
    assert fx_freshness(kst("2026-10-05 08:00"), at, timedelta(hours=24)).state is FreshState.STALE
    assert fx_freshness(None, at, timedelta(hours=24)).state is FreshState.UNKNOWN
