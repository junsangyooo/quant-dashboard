"""시세 · 장 달력을 토스에서(TASKS T-11 · ENGINE-RULES R-O1).

- 일봉 · 코스피 지수는 토스(가짜 서버)에서 받아요. 야후는 0.
- 그날 일봉은 20:00 뒤 확정.
- 장 시간은 market-calendar: 개장 지연일(수능일 10:00)은 08:30 점검 · 08:35 주문이 09:30 · 09:35로 옮겨지고,
  휴장일은 거래일이 아니에요.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.store.db import DB
from app.domain.markets.kr import KST, complete_until
from app.market import INDEX, Calendar, Market, MarketDataError, TossSource
from app.adapters.toss import RateLimiter, TossClient, TossCredentials
from tests.conftest import make_bars
from tests.fake_toss import ACCOUNT_NO, CLIENT_ID, CLIENT_SECRET, FakeTossServer, holiday, regular_day

SUNEUNG = date(2026, 11, 19)  # 목요일 · 1시간 늦게 열어요
HOLIDAY = date(2026, 11, 20)  # 금요일 · 휴장(시험용 가정)


def special(d: date) -> dict[str, Any]:
    if d == SUNEUNG:
        return regular_day(d, (10, 0), (16, 30))
    if d == HOLIDAY or d.weekday() >= 5:
        return holiday(d)
    return regular_day(d)


@pytest.fixture
def server() -> FakeTossServer:
    s = FakeTossServer()
    s.bars = {"005930": make_bars([70000 + 10 * i for i in range(300)], start=date(2025, 6, 2))}
    s.index_bars = {"KOSPI": make_bars([2500.0 + i for i in range(300)], start=date(2025, 6, 2))}
    s.calendar = special
    return s


@pytest.fixture
def market(tmp_path: Path, server: FakeTossServer) -> Market:
    client = TossClient(TossCredentials(CLIENT_ID, CLIENT_SECRET, ACCOUNT_NO), transport=server,
                        limiter=RateLimiter(sleep=lambda s: None))
    return Market(DB(tmp_path / "m.db"), TossSource(lambda: client))


def test_bars_and_index_from_toss(market: Market, server: FakeTossServer) -> None:
    bars = market.bars("005930", date(2025, 6, 2), date(2026, 7, 1))
    assert bars[0] == {"d": "2025-06-02", "o": 70000.0, "h": 70000.0, "l": 70000.0, "c": 70000.0, "v": 1000000.0}
    assert bars == [b for b in server.bars["005930"] if b["d"] <= "2026-07-01"]
    kospi = market.bars(INDEX, date(2025, 6, 2), date(2025, 6, 30))
    assert INDEX == "KOSPI" and kospi[0]["c"] == 2500.0
    paths = {p for _, p in server.calls}
    assert "/api/v1/candles" in paths and "/api/v1/market-indicators/KOSPI/candles" in paths
    assert server.spec_errors == []
    # 두 번째는 담아 둔 것(일봉 요청이 늘지 않아요)
    n = len(server.calls)
    market.bars("005930", date(2025, 7, 1), date(2025, 8, 1))
    assert len(server.calls) == n


def test_unknown_code_and_no_connection(market: Market, server: FakeTossServer, tmp_path: Path) -> None:
    with pytest.raises(MarketDataError) as e:
        market.many(["005930", "999999"], date(2025, 6, 2), date(2025, 7, 1))
    assert e.value.kind == "symbol" and e.value.symbols == ["999999"]
    server.down = True
    with pytest.raises(MarketDataError) as e:
        market.many(["000660"], date(2025, 6, 2), date(2025, 7, 1))
    assert e.value.kind == "network"
    offline = Market(DB(tmp_path / "o.db"), TossSource(lambda: None))
    with pytest.raises(MarketDataError) as e:
        offline.many(["005930"], date(2025, 6, 2), date(2025, 7, 1))
    assert e.value.kind == "toss" and e.value.message == "토스 연결이 필요해요 · 시세와 계좌를 토스에서 받아요"


def test_bar_is_final_after_20(market: Market) -> None:
    cal = market.calendar
    mon = date(2026, 11, 2)
    assert complete_until(datetime(2026, 11, 2, 19, 59, tzinfo=KST), cal) == date(2026, 10, 30)  # 앞 거래일(금)
    assert complete_until(datetime(2026, 11, 2, 20, 0, tzinfo=KST), cal) == mon
    assert complete_until(datetime(2026, 11, 2, 23, 0, tzinfo=KST), cal) == mon
    assert complete_until(datetime(2026, 11, 3, 8, 30, tzinfo=KST), cal) == mon
    # 휴장일 · 주말 밤에도 마지막 거래일
    assert complete_until(datetime(2026, 11, 20, 21, 0, tzinfo=KST), cal) == SUNEUNG
    assert complete_until(datetime(2026, 11, 22, 21, 0, tzinfo=KST), cal) == SUNEUNG


def test_late_open_day_moves_check_and_order(market: Market) -> None:
    day = market.calendar.day(SUNEUNG)
    assert day.open and day.known
    assert day.shift.seconds == 3600
    assert day.at(8, 30).strftime("%H:%M") == "09:30"  # 장 시작 전 점검
    assert day.at(8, 35).strftime("%H:%M") == "09:35"  # 시가 단일가 주문
    normal = market.calendar.day(date(2026, 11, 18))
    assert normal.shift.seconds == 0 and normal.at(8, 35).strftime("%H:%M") == "08:35"


def test_holiday_is_skipped(market: Market, server: FakeTossServer) -> None:
    cal = market.calendar
    assert cal.is_open(HOLIDAY) is False
    assert cal.next_open(SUNEUNG) == date(2026, 11, 23)
    assert cal.prev_open(date(2026, 11, 23)) == SUNEUNG
    # 담아 둔 달력은 다시 묻지 않아요
    n = len([p for _, p in server.calls if p.endswith("market-calendar/KR")])
    cal.is_open(HOLIDAY)
    assert len([p for _, p in server.calls if p.endswith("market-calendar/KR")]) == n
    assert server.spec_errors == []


def test_without_calendar_weekdays_are_trading_days(tmp_path: Path) -> None:
    cal = Calendar(DB(tmp_path / "c.db"), None)
    assert cal.is_open(HOLIDAY) is True and cal.day(HOLIDAY).known is False
    assert cal.is_open(date(2026, 11, 21)) is False
    assert complete_until(datetime(2026, 11, 23, 9, 0, tzinfo=KST)) == HOLIDAY
