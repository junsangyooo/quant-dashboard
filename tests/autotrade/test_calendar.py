"""Exchange calendars against known dates (예시-값표 §0 and the official 2025-2027 lists)."""

from __future__ import annotations

from datetime import date, time

import pytest

from autotrade.domain.instruments import Market
from autotrade.market.calendar import (
    KRX,
    KRX_HOLIDAYS,
    NYSE,
    NYSE_HOLIDAYS,
    CalendarRangeError,
    ExchangeCalendar,
    SpecialHours,
    calendar_for,
)
from autotrade.timeutil import ET, KST


@pytest.mark.parametrize(
    "d",
    [
        "2026-08-17",  # 광복절 대체 (§0)
        "2026-09-24",  # 추석 (§0)
        "2026-09-25",  # 추석 (§0)
        "2026-10-05",  # 개천절 대체 (§0)
        "2026-10-09",  # 한글날 (§0)
        "2026-07-17",  # 제헌절, a public holiday again from 2026
        "2026-06-03",  # local elections
        "2026-05-01",  # 노동절
        "2026-12-31",  # year-end closing day
        "2025-01-27",  # temporary holiday
        "2025-10-08",  # 추석 substitute
        "2027-02-09",  # 설 substitute (provisional 2027 list)
        "2027-12-31",
    ],
)
def test_krx_holidays(d: str) -> None:
    assert not KRX.is_trading_day(date.fromisoformat(d))


@pytest.mark.parametrize(
    "d",
    [
        "2026-09-28",  # Monday after 추석: Saturday overlap gives no substitute day
        "2025-10-10",  # not designated
        "2026-10-07",
        "2026-12-30",  # last trading day of 2026
        "2026-07-03",  # US holiday, Korea open
    ],
)
def test_krx_trading_days(d: str) -> None:
    assert KRX.is_trading_day(date.fromisoformat(d))


@pytest.mark.parametrize(
    "d", ["2026-07-03", "2026-09-07", "2025-01-09", "2027-12-24", "2027-06-18"]
)
def test_nyse_holidays(d: str) -> None:
    assert not NYSE.is_trading_day(date.fromisoformat(d))


@pytest.mark.parametrize("d", ["2026-09-25", "2026-10-09", "2027-12-31", "2026-07-02"])
def test_nyse_trading_days(d: str) -> None:
    assert NYSE.is_trading_day(date.fromisoformat(d))


def test_weekends_never_trade() -> None:
    assert not KRX.is_trading_day(date(2026, 10, 10))  # Saturday
    assert not NYSE.is_trading_day(date(2026, 10, 11))  # Sunday


def test_table_sizes_match_the_official_lists() -> None:
    def count(table: dict[date, str], year: int) -> int:
        return sum(1 for d in table if d.year == year)

    assert (count(KRX_HOLIDAYS, 2025), count(KRX_HOLIDAYS, 2026), count(KRX_HOLIDAYS, 2027)) == (
        19,
        17,
        16,
    )
    assert (count(NYSE_HOLIDAYS, 2025), count(NYSE_HOLIDAYS, 2026), count(NYSE_HOLIDAYS, 2027)) == (
        11,
        10,
        10,
    )


def test_us_open_in_kst_follows_daylight_time() -> None:
    # October (EDT): 09:30 ET = 22:30 KST; after DST ends on 2026-11-01: 23:30 KST.
    assert NYSE.session_open(date(2026, 10, 7)).astimezone(KST).time() == time(22, 30)
    assert NYSE.session_open(date(2026, 11, 2)).astimezone(KST).time() == time(23, 30)
    assert NYSE.session_open(date(2026, 3, 6)).astimezone(KST).time() == time(23, 30)
    assert NYSE.session_open(date(2026, 3, 9)).astimezone(KST).time() == time(22, 30)
    assert NYSE.session_open(date(2026, 3, 9)).tzinfo is ET


def test_half_days_and_late_opens() -> None:
    assert NYSE.session_close(date(2026, 11, 27)).time() == time(13, 0)
    assert NYSE.session_close(date(2026, 11, 25)).time() == time(16, 0)
    assert KRX.session_open(date(2026, 11, 19)).time() == time(10, 0)  # 수능
    assert KRX.session_close(date(2026, 11, 19)).time() == time(16, 30)
    assert KRX.session_open(date(2026, 1, 2)).time() == time(10, 0)  # first trading day
    assert KRX.session_open(date(2026, 1, 5)).time() == time(9, 0)
    with pytest.raises(ValueError, match="closed"):
        KRX.hours(date(2026, 10, 9))


def test_navigation() -> None:
    assert KRX.next_trading_day(date(2026, 9, 23)) == date(2026, 9, 28)
    assert KRX.previous_trading_day(date(2026, 10, 6)) == date(2026, 10, 2)
    assert KRX.latest_trading_day(date(2026, 10, 5)) == date(2026, 10, 2)
    assert KRX.latest_trading_day(date(2026, 10, 6)) == date(2026, 10, 6)
    assert NYSE.next_trading_day(date(2026, 7, 2)) == date(2026, 7, 6)
    # '미국 시세 10/02 기준 · 2거래일째': US sessions after 10/02 up to 10/06.
    assert NYSE.trading_days(date(2026, 10, 2), date(2026, 10, 6)) == [
        date(2026, 10, 5),
        date(2026, 10, 6),
    ]
    assert KRX.holiday_name(date(2026, 10, 9)) == "한글날"
    assert calendar_for(Market.KR) is KRX
    assert calendar_for(Market.US) is NYSE


def test_out_of_range_dates_raise() -> None:
    with pytest.raises(CalendarRangeError):
        KRX.is_trading_day(date(2028, 1, 3))
    with pytest.raises(CalendarRangeError):
        NYSE.is_trading_day(date(2024, 12, 31))


def test_table_validation() -> None:
    with pytest.raises(ValueError, match="both closed and special"):
        ExchangeCalendar(
            Market.KR,
            KST,
            time(9, 0),
            time(15, 30),
            {date(2026, 1, 2): "x"},
            {date(2026, 1, 2): SpecialHours(time(10, 0), time(15, 30), "y")},
        )
    with pytest.raises(CalendarRangeError):
        ExchangeCalendar(Market.KR, KST, time(9, 0), time(15, 30), {date(2030, 1, 1): "x"}, {})
