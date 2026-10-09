"""KRX and NYSE trading calendars, 2025-2027, as static tables.

A date outside the table raises CalendarRangeError instead of guessing: extend the table before
2027-12 (the US and Korean holiday lists for 2028 are published in late 2026 / December 2027).

Sources (read 2026-10-09):

NYSE
- https://www.nyse.com/markets/hours-calendars (shows 2026-2028 with footnotes)
- ICE press release 2024-11-08, "NYSE Group Announces 2025, 2026 and 2027 Holiday and Early
  Closings Calendar":
  https://ir.theice.com/press/news-details/2024/NYSE-Group-Announces-2025-2026-and-2027-Holiday-and-Early-Closings-Calendar/default.aspx
- Unscheduled closure 2025-01-09 (national day of mourning, President Carter), ICE 2024-12-30:
  https://ir.theice.com/press/news-details/2024/The-New-York-Stock-Exchange-Will-Close-Markets-on-January-9-to-Honor-the-Passing-of-Former-President-Jimmy-Carter-on-National-Day-of-Mourning/default.aspx

KRX
- KRX 휴장일 조회 (2025, 2026 and the 2027 list KRX already serves):
  https://open.krx.co.kr/contents/MKD/01/0110/01100305/MKD01100305.jsp
  https://global.krx.co.kr/contents/GLB/05/0501/0501110000/GLB0501110000.jsp
- 관공서의 공휴일에 관한 규정 (2026-05-11 version; 노동절 and 제헌절 became public holidays
  with substitute days): https://www.law.go.kr/LSW/lsInfoP.do?lsiSeq=285779&efYd=20260511
- 우주항공청 2027 월력요항 (2026-06-29):
  https://www.kasa.go.kr/prog/plcyBrf/brief/kor/sub01_01_04/view.do?plcyBrfNo=431
- Year-end closing day: 유가증권시장 업무규정 제5조 (Dec 31; the previous trading day when Dec 31
  is a holiday or Saturday).
- Late opens (10:00): first trading day of the year (2025-01-02, 2026-01-02) and the college
  entrance exam day (2025-11-13, 10:00-16:30):
  https://news.nate.com/view/20250102n05243
  https://www.newsis.com/view/NISX20251231_0003460546
  https://www.koreatimes.co.kr/economy/20251030/financial-markets-to-open-1-hour-later-on-college-entrance-exam-day
  Exam dates: 2026-11-19 (https://www.korea.kr/briefing/policyBriefingView.do?newsId=156752001),
  2027-11-18 (교육부 2025-06-01).

Marked PROVISIONAL below: the KRX hours for 2026-11-19, 2027-01-04 and 2027-11-18 are not
announced yet (customary 10:00 open), and the 2027 KRX list becomes official in December 2026.
Ad-hoc holidays (임시공휴일) can still be added by the government.

Half-day closes matter here only for data freshness (the close time); orders go at the open.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from autotrade.domain.instruments import Market
from autotrade.timeutil import ET, KST, at_zone

COVERAGE_START = date(2025, 1, 1)
COVERAGE_END = date(2027, 12, 31)


class CalendarRangeError(LookupError):
    """The date is outside the static table."""


@dataclass(frozen=True)
class SpecialHours:
    open: time
    close: time
    reason: str
    provisional: bool = False


class ExchangeCalendar:
    def __init__(
        self,
        market: Market,
        tz: ZoneInfo,
        regular_open: time,
        regular_close: time,
        holidays: Mapping[date, str],
        special: Mapping[date, SpecialHours],
        first_day: date = COVERAGE_START,
        last_day: date = COVERAGE_END,
    ) -> None:
        self.market = market
        self.tz = tz
        self.regular_open = regular_open
        self.regular_close = regular_close
        self.holidays = dict(holidays)
        self.special = dict(special)
        self.first_day = first_day
        self.last_day = last_day
        for d in [*self.holidays, *self.special]:
            self._check(d)
        overlap = set(self.holidays) & set(self.special)
        if overlap:
            raise ValueError(f"dates both closed and special: {sorted(overlap)}")

    def _check(self, d: date) -> None:
        if not self.first_day <= d <= self.last_day:
            raise CalendarRangeError(
                f"{self.market.value} calendar covers {self.first_day}..{self.last_day}, not {d}"
            )

    def is_trading_day(self, d: date) -> bool:
        self._check(d)
        return d.weekday() < 5 and d not in self.holidays

    def holiday_name(self, d: date) -> str | None:
        self._check(d)
        return self.holidays.get(d)

    def hours(self, d: date) -> tuple[time, time]:
        if not self.is_trading_day(d):
            raise ValueError(f"{self.market.value} is closed on {d}")
        sp = self.special.get(d)
        if sp is not None:
            return sp.open, sp.close
        return self.regular_open, self.regular_close

    def session_open(self, d: date) -> datetime:
        return at_zone(d, self.hours(d)[0], self.tz)

    def session_close(self, d: date) -> datetime:
        return at_zone(d, self.hours(d)[1], self.tz)

    def next_trading_day(self, d: date) -> date:
        cur = d + timedelta(days=1)
        while not self.is_trading_day(cur):
            cur += timedelta(days=1)
        return cur

    def previous_trading_day(self, d: date) -> date:
        cur = d - timedelta(days=1)
        while not self.is_trading_day(cur):
            cur -= timedelta(days=1)
        return cur

    def latest_trading_day(self, d: date) -> date:
        """d itself when it trades, else the trading day before it."""
        return d if self.is_trading_day(d) else self.previous_trading_day(d)

    def trading_days(self, start: date, end: date) -> list[date]:
        """Trading days with start < day <= end."""
        out: list[date] = []
        cur = start + timedelta(days=1)
        while cur <= end:
            if self.is_trading_day(cur):
                out.append(cur)
            cur += timedelta(days=1)
        return out


def _d(text: str) -> date:
    return date.fromisoformat(text)


# ── KRX (Korea Exchange) ─────────────────────────────────────────────────────────────────
# Weekend days are omitted, as KRX omits them.
KRX_HOLIDAYS: dict[date, str] = {
    # 2025 (KRX list, 19 days). 2025-10-10 was NOT a holiday.
    _d("2025-01-01"): "신정",
    _d("2025-01-27"): "임시공휴일",
    _d("2025-01-28"): "설날 연휴",
    _d("2025-01-29"): "설날",
    _d("2025-01-30"): "설날 연휴",
    _d("2025-03-03"): "삼일절 대체공휴일",
    _d("2025-05-01"): "근로자의 날",
    _d("2025-05-05"): "어린이날·부처님오신날",
    _d("2025-05-06"): "어린이날 대체공휴일",
    _d("2025-06-03"): "임시공휴일(대통령선거)",
    _d("2025-06-06"): "현충일",
    _d("2025-08-15"): "광복절",
    _d("2025-10-03"): "개천절",
    _d("2025-10-06"): "추석",
    _d("2025-10-07"): "추석 연휴",
    _d("2025-10-08"): "추석 대체공휴일",
    _d("2025-10-09"): "한글날",
    _d("2025-12-25"): "성탄절",
    _d("2025-12-31"): "연말 휴장일",
    # 2026 (KRX list, 17 days). 09-26 (Sat) gives no substitute day for 추석, so 09-28 trades.
    _d("2026-01-01"): "신정",
    _d("2026-02-16"): "설날 연휴",
    _d("2026-02-17"): "설날",
    _d("2026-02-18"): "설날 연휴",
    _d("2026-03-02"): "삼일절 대체공휴일",
    _d("2026-05-01"): "노동절",
    _d("2026-05-05"): "어린이날",
    _d("2026-05-25"): "부처님오신날 대체공휴일",
    _d("2026-06-03"): "전국동시지방선거",
    _d("2026-07-17"): "제헌절",
    _d("2026-08-17"): "광복절 대체공휴일",
    _d("2026-09-24"): "추석 연휴",
    _d("2026-09-25"): "추석",
    _d("2026-10-05"): "개천절 대체공휴일",
    _d("2026-10-09"): "한글날",
    _d("2026-12-25"): "성탄절",
    _d("2026-12-31"): "연말 휴장일",
    # 2027 (PROVISIONAL: KRX list as served on 2026-10-09 = 월력요항 + rules, 16 days).
    _d("2027-01-01"): "신정",
    _d("2027-02-08"): "설날 연휴",
    _d("2027-02-09"): "설날 대체공휴일",
    _d("2027-03-01"): "삼일절",
    _d("2027-05-03"): "노동절 대체공휴일",
    _d("2027-05-05"): "어린이날",
    _d("2027-05-13"): "부처님오신날",
    _d("2027-07-19"): "제헌절 대체공휴일",
    _d("2027-08-16"): "광복절 대체공휴일",
    _d("2027-09-14"): "추석 연휴",
    _d("2027-09-15"): "추석",
    _d("2027-09-16"): "추석 연휴",
    _d("2027-10-04"): "개천절 대체공휴일",
    _d("2027-10-11"): "한글날 대체공휴일",
    _d("2027-12-27"): "성탄절 대체공휴일",
    _d("2027-12-31"): "연말 휴장일",
}

KRX_SPECIAL: dict[date, SpecialHours] = {
    _d("2025-01-02"): SpecialHours(time(10, 0), time(15, 30), "새해 첫 거래일"),
    _d("2025-11-13"): SpecialHours(time(10, 0), time(16, 30), "수능"),
    _d("2026-01-02"): SpecialHours(time(10, 0), time(15, 30), "새해 첫 거래일"),
    _d("2026-11-19"): SpecialHours(time(10, 0), time(16, 30), "수능", provisional=True),
    _d("2027-01-04"): SpecialHours(time(10, 0), time(15, 30), "새해 첫 거래일", provisional=True),
    _d("2027-11-18"): SpecialHours(time(10, 0), time(16, 30), "수능", provisional=True),
}

# ── NYSE ─────────────────────────────────────────────────────────────────────────────────
NYSE_HOLIDAYS: dict[date, str] = {
    _d("2025-01-01"): "New Year's Day",
    _d("2025-01-09"): "National Day of Mourning (President Carter)",
    _d("2025-01-20"): "Martin Luther King Jr. Day",
    _d("2025-02-17"): "Washington's Birthday",
    _d("2025-04-18"): "Good Friday",
    _d("2025-05-26"): "Memorial Day",
    _d("2025-06-19"): "Juneteenth",
    _d("2025-07-04"): "Independence Day",
    _d("2025-09-01"): "Labor Day",
    _d("2025-11-27"): "Thanksgiving Day",
    _d("2025-12-25"): "Christmas Day",
    _d("2026-01-01"): "New Year's Day",
    _d("2026-01-19"): "Martin Luther King Jr. Day",
    _d("2026-02-16"): "Washington's Birthday",
    _d("2026-04-03"): "Good Friday",
    _d("2026-05-25"): "Memorial Day",
    _d("2026-06-19"): "Juneteenth",
    _d("2026-07-03"): "Independence Day (observed)",
    _d("2026-09-07"): "Labor Day",
    _d("2026-11-26"): "Thanksgiving Day",
    _d("2026-12-25"): "Christmas Day",
    _d("2027-01-01"): "New Year's Day",
    _d("2027-01-18"): "Martin Luther King Jr. Day",
    _d("2027-02-15"): "Washington's Birthday",
    _d("2027-03-26"): "Good Friday",
    _d("2027-05-31"): "Memorial Day",
    _d("2027-06-18"): "Juneteenth (observed)",
    _d("2027-07-05"): "Independence Day (observed)",
    _d("2027-09-06"): "Labor Day",
    _d("2027-11-25"): "Thanksgiving Day",
    _d("2027-12-24"): "Christmas Day (observed)",
    # 2028-01-01 is a Saturday and is not observed on 2027-12-31, which trades.
}

NYSE_SPECIAL: dict[date, SpecialHours] = {
    _d("2025-07-03"): SpecialHours(time(9, 30), time(13, 0), "early close"),
    _d("2025-11-28"): SpecialHours(time(9, 30), time(13, 0), "early close"),
    _d("2025-12-24"): SpecialHours(time(9, 30), time(13, 0), "early close"),
    _d("2026-11-27"): SpecialHours(time(9, 30), time(13, 0), "early close"),
    _d("2026-12-24"): SpecialHours(time(9, 30), time(13, 0), "early close"),
    _d("2027-11-26"): SpecialHours(time(9, 30), time(13, 0), "early close"),
}

KRX = ExchangeCalendar(Market.KR, KST, time(9, 0), time(15, 30), KRX_HOLIDAYS, KRX_SPECIAL)
NYSE = ExchangeCalendar(Market.US, ET, time(9, 30), time(16, 0), NYSE_HOLIDAYS, NYSE_SPECIAL)


def calendar_for(market: Market) -> ExchangeCalendar:
    return KRX if market is Market.KR else NYSE
