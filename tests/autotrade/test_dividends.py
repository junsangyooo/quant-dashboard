"""Cash dividends of the paper ledger: tax, pay dates, who is owed, booking, the baseline."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from autotrade.config import Config
from autotrade.db import repo
from autotrade.db.connection import transaction
from autotrade.db.models import DividendRow
from autotrade.domain.dividends import (
    HeldFill,
    after_tax,
    estimated_pay_date,
    qty_before_ex_date,
)
from autotrade.domain.instruments import Currency, Instrument, Kind, Market, us_etf
from autotrade.domain.ledger import Position
from autotrade.domain.money import round_won, usd_in_krw
from autotrade.engine.dividends import (
    book_dividends,
    shares_before_ex_date,
    watched_instruments,
)
from autotrade.engine.rebuild import verify_ledger
from autotrade.jobs.tasks import JobContext, check_job, dividend_job, snapshot_job, stage_job
from autotrade.market.calendar import KRX, NYSE
from autotrade.market.service import (
    DIVIDENDS_SERIES,
    MarketSources,
    default_sources,
    prefetch_dividends,
)
from autotrade.market.sources import YahooDividendSource

from .fakes import KR, US, World
from .helpers import kst, seed_ledger
from .test_engine_first_day import first_day_world

D = Decimal


# ── amounts and dates ────────────────────────────────────────────────────────────────────


def test_the_0930_example_after_tax() -> None:
    # 예시-값표 §1.4 9/30: '배당 16,243원 (세후, 120주 × 160원 − 세금)', 15.4% withheld.
    amounts = after_tax(D("160"), 120, Currency.KRW, D("0.154"))
    assert (amounts.gross, amounts.tax, amounts.net) == (D("19200"), D("2957"), D("16243"))


def test_us_dividends_lose_15_percent_in_cents() -> None:
    # 46 x $0.239 = $10.994 -> $10.99; tax $1.6485 rounds up to $1.65; net $9.34.
    amounts = after_tax(D("0.239"), 46, Currency.USD, D("0.15"))
    assert (amounts.gross, amounts.tax, amounts.net) == (D("10.99"), D("1.65"), D("9.34"))
    # The baseline holds fractional units.
    assert after_tax(D("183"), D("156.25"), Currency.KRW, D("0.154")).net == D("24190")
    with pytest.raises(ValueError, match="bad dividend"):
        after_tax(D("1"), 1, Currency.KRW, D("1"))
    with pytest.raises(ValueError, match="bad dividend"):
        after_tax(D("-1"), 1, Currency.KRW, D("0.1"))


def test_pay_dates_are_estimated_on_the_exchange_calendar() -> None:
    # KODEX 200: ex 7/30, record 7/31, paid 8/4 (two trading days after the record date).
    assert estimated_pay_date(date(2026, 7, 30), KRX, 3) == date(2026, 8, 4)
    # Across 추석 (9/24, 9/25) and a weekend: ex 9/23 -> paid 9/30, the example's date.
    assert estimated_pay_date(date(2026, 9, 23), KRX, 3) == date(2026, 9, 30)
    # SPYM: ex Friday 9/11 -> paid Tuesday 9/15.
    assert estimated_pay_date(date(2026, 9, 11), NYSE, 2) == date(2026, 9, 15)
    assert estimated_pay_date(date(2026, 9, 11), NYSE, 0) == date(2026, 9, 11)
    with pytest.raises(ValueError, match="lag_days"):
        estimated_pay_date(date(2026, 9, 11), NYSE, -1)


def test_shares_before_the_ex_date() -> None:
    fills = [HeldFill(date(2026, 9, 1), 120), HeldFill(date(2026, 10, 7), -5)]
    assert qty_before_ex_date(115, fills, date(2026, 9, 23)) == 120  # a later sale keeps it
    assert qty_before_ex_date(115, fills, date(2026, 10, 8)) == 115
    assert qty_before_ex_date(120, [HeldFill(date(2026, 9, 23), 120)], date(2026, 9, 23)) == 0
    assert qty_before_ex_date(0, [HeldFill(date(2026, 9, 24), 5)], date(2026, 9, 23)) == 0


# ── the source ───────────────────────────────────────────────────────────────────────────


class FakeTicker:
    def __init__(self, frame: pd.DataFrame | None) -> None:
        self.frame = frame
        self.kwargs: dict[str, Any] = {}

    def history(self, **kwargs: Any) -> pd.DataFrame | None:
        self.kwargs = kwargs
        return self.frame


def test_yahoo_dividends_come_by_ex_date() -> None:
    idx = pd.DatetimeIndex(["2026-09-10 00:00", "2026-09-11 00:00"]).tz_localize("America/New_York")
    frame = pd.DataFrame({"Close": [62.0, 62.1], "Dividends": [0.0, 0.239]}, index=idx)
    ticker = FakeTicker(frame)
    source = YahooDividendSource(SimpleNamespace(Ticker=lambda symbol: ticker))
    snp = us_etf("SPYM", "S&P 500 ETF")
    [div] = source.fetch_dividends(snp, date(2026, 9, 1), date(2026, 9, 30))
    assert (div.instrument_id, div.ex_date, div.per_share, div.pay_date) == (
        "US:SPYM",
        date(2026, 9, 11),
        D("0.239"),
        None,
    )
    assert (ticker.kwargs["actions"], ticker.kwargs["auto_adjust"]) == (True, False)
    assert ticker.kwargs["end"] == "2026-10-01"
    for empty in (None, frame.iloc[:0], frame[["Close"]]):
        ticker.frame = empty
        assert source.fetch_dividends(snp, date(2026, 9, 1), date(2026, 9, 30)) == []
    assert default_sources().dividends is not None


def test_prefetch_estimates_pay_dates_and_records_the_fetch(
    conn: sqlite3.Connection, cfg: Config, world: World
) -> None:
    kodex = repo.get_instrument(conn, KR)
    snp = repo.get_instrument(conn, US)
    world.dividend(KR, "2026-09-23", "160")
    world.dividend(US, "2026-09-11", "0.239", pay_date="2026-09-16")
    at = kst("2026-09-30 08:00")
    errors = prefetch_dividends(
        conn, cfg, world.sources(), [kodex, snp], date(2026, 8, 1), date(2026, 9, 30), at
    )
    assert errors == {}
    rows = repo.dividends_paid(conn, [KR, US], None, date(2026, 12, 31))
    assert [(r.instrument_id, r.pay_date, r.pay_estimated) for r in rows] == [
        (US, date(2026, 9, 16), False),  # the source's own pay date
        (KR, date(2026, 9, 30), True),  # ex 9/23 + 3 KRX trading days
    ]
    fresh = repo.get_freshness(conn, DIVIDENDS_SERIES)
    assert fresh is not None
    assert (fresh.fetched_at, fresh.error) == (at, None)

    # A known pay date is not overwritten by an estimate; an estimate gives way to a known one.
    with transaction(conn):
        repo.upsert_dividends(
            conn,
            [
                DividendRow(
                    US, date(2026, 9, 11), date(2026, 9, 15), True, D("0.239"), Currency.USD, "x"
                ),
                DividendRow(
                    KR, date(2026, 9, 23), date(2026, 10, 1), False, D("160"), Currency.KRW, "y"
                ),
            ],
            at,
        )
    rows = repo.dividends_paid(conn, [KR, US], None, date(2026, 12, 31))
    assert [(r.instrument_id, r.pay_date, r.pay_estimated) for r in rows] == [
        (US, date(2026, 9, 16), False),
        (KR, date(2026, 10, 1), False),
    ]
    assert repo.dividends_paid(conn, [], None, date(2026, 12, 31)) == []

    world.fail_dividends = True
    later = kst("2026-10-01 08:00")
    errors = prefetch_dividends(
        conn, cfg, world.sources(), [kodex], date(2026, 9, 1), date(2026, 10, 1), later
    )
    assert set(errors) == {KR}
    fresh = repo.get_freshness(conn, DIVIDENDS_SERIES)
    assert fresh is not None
    assert (fresh.attempted_at, fresh.fetched_at) == (later, at)  # the last success stays
    # No dividend source configured: nothing is fetched or recorded.
    full = world.sources()
    no_source = MarketSources(kr=full.kr, us=full.us, fx=full.fx)
    assert prefetch_dividends(conn, cfg, no_source, [kodex], date.min, date.max, later) == {}


def test_a_date_outside_the_calendar_is_an_error_not_a_crash(
    conn: sqlite3.Connection, cfg: Config, world: World
) -> None:
    world.dividend(KR, "2027-12-30", "100")  # the estimate needs 2028, past the table
    errors = prefetch_dividends(
        conn,
        cfg,
        world.sources(),
        [repo.get_instrument(conn, KR)],
        date(2027, 12, 1),
        date(2027, 12, 31),
        kst("2027-12-31 08:00"),
    )
    assert "CalendarRangeError" in errors[KR]


# ── booking ──────────────────────────────────────────────────────────────────────────────


def seed_0930(conn: sqlite3.Connection, world: World) -> None:
    seed_ledger(
        conn,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("47675"),
        usd=D("1.66"),
        positions={KR: (120, D("3840576"), D("3840576")), US: (46, D("3033.03"), D("4221675"))},
    )
    world.dividend(KR, "2026-09-23", "160")  # paid 9/30 (estimated)


def test_the_0930_dividend_is_booked_once_on_its_pay_date(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_0930(conn, world)
    before = dividend_job(ctx, "paper", kst("2026-09-29 08:00"))
    assert (before["result"], before["booked"]) == ("nothing-due", [])
    income_before = repo.load_state(conn, "paper").income_krw

    paid = dividend_job(ctx, "paper", kst("2026-09-30 08:00"))
    assert paid["result"] == "booked"
    [booked] = paid["booked"]
    assert (booked["qty"], booked["net"], booked["currency"]) == (120, D("16243"), "KRW")
    state = repo.load_state(conn, "paper")
    assert state.cash_of(Currency.KRW) == D("47675") + D("16243")
    assert state.income_krw - income_before == D("16243")  # income, not a deposit
    assert state.contributions_krw == D("10000000")
    [event] = repo.events_of_ledger(conn, "paper", ["dividend"])
    assert (event.event_date, event.amount, event.currency) == (
        date(2026, 9, 30),
        D("16243"),
        Currency.KRW,
    )
    assert event.ref == "dividend:KR:069500:2026-09-23"
    assert event.rule_id == "index_half"
    assert (event.payload["gross"], event.payload["tax"], event.payload["qty"]) == (
        "19200",
        "2957",
        120,
    )
    # The dividend is new cash for the next check (인계 4: '새 현금은 다음 확인에 투자').
    parts = {(p.currency, p.purpose.value): p.amount for p in repo.cash_parts(conn, "paper")}
    assert parts[(Currency.KRW, "new")] >= D("16243")

    again = dividend_job(ctx, "paper", kst("2026-09-30 16:00"))
    assert (again["result"], again["booked"]) == ("nothing-due", [])
    assert len(repo.events_of_ledger(conn, "paper", ["dividend"])) == 1


def test_dry_run_and_failures(ctx: JobContext, conn: sqlite3.Connection, world: World) -> None:
    seed_0930(conn, world)
    dry = dividend_job(ctx, "paper", kst("2026-09-30 08:00"), dry_run=True)
    assert dry["result"] == "booked"
    assert repo.events_of_ledger(conn, "paper", ["dividend"]) == []
    world.fail_dividends = True
    # The download fails, yet what is stored (9/23, fetched by the dry run) is still booked.
    failed_fetch = dividend_job(ctx, "paper", kst("2026-09-30 09:00"))
    assert failed_fetch["result"] == "booked"
    assert set(failed_fetch["fetch_errors"]) == {KR, US}
    nothing = dividend_job(ctx, "paper", kst("2026-10-01 09:00"))
    assert (nothing["result"], nothing["booked"]) == ("failed", [])


def test_a_ledger_that_bought_after_the_ex_date_gets_nothing(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    first_day_world(world)
    check_job(ctx, "paper", kst("2026-07-01 08:30"))
    for t in ("09:05", "09:10", "22:30"):
        stage_job(ctx, "paper", kst(f"2026-07-01 {t}"))
    kodex = repo.get_instrument(conn, KR)
    assert shares_before_ex_date(conn, "paper", kodex, date(2026, 7, 1)) == 0  # bought that day
    assert shares_before_ex_date(conn, "paper", kodex, date(2026, 7, 2)) == 156
    world.dividend(KR, "2026-06-29", "100")  # before the start: nothing was held
    world.dividend(KR, "2026-07-01", "100")  # ex-date = the first purchase's session
    assert dividend_job(ctx, "paper", kst("2026-07-08 08:00"))["booked"] == []


def test_dollar_dividends_need_a_rate_and_rebuild_to_the_won(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    first_day_world(world)
    check_job(ctx, "paper", kst("2026-07-01 08:30"))
    for t in ("09:05", "09:10", "22:30"):
        stage_job(ctx, "paper", kst(f"2026-07-01 {t}"))
    world.dividend(US, "2026-09-11", "0.239")  # 54 shares, paid 9/15
    world.dividend(KR, "2026-07-30", "183")  # 156 shares, paid 8/4
    kr = dividend_job(ctx, "paper", kst("2026-08-04 08:00"))
    [kr_booked] = kr["booked"]
    # 156 x 183 = 28,548; tax 4,396.392 -> 4,397; net 24,151.
    assert (kr_booked["qty"], kr_booked["net"]) == (156, D("24151"))

    us = dividend_job(ctx, "paper", kst("2026-09-15 08:00"))
    [us_booked] = us["booked"]
    # 54 x $0.239 = $12.906 -> $12.91; tax $1.9365 -> $1.94; net $10.97 at the stored rate.
    assert (us_booked["qty"], us_booked["net"], us_booked["currency"]) == (54, D("10.97"), "USD")
    rate = repo.fx_at(conn, kst("2026-09-15 08:00"))
    assert rate is not None
    assert us_booked["amount_krw"] == usd_in_krw(D("10.97"), rate.rate)
    state = repo.load_state(conn, "paper")
    assert state.cash_of(Currency.USD) == D("0.68") + D("10.97")
    assert verify_ledger(conn, "paper") == []  # the events rebuild the ledger to the won


def test_a_dollar_dividend_waits_for_a_rate(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_0930(conn, world)
    world.dividend(US, "2026-09-11", "0.239", pay_date="2026-09-15")
    waiting = dividend_job(ctx, "paper", kst("2026-09-15 08:00"))
    assert waiting["result"] == "nothing-due"
    assert waiting["waiting"] == [
        {"instrument_id": US, "ex_date": date(2026, 9, 11), "wait": "no-rate"}
    ]
    world.rate(kst("2026-09-15 08:30"), "1385.0")  # the job fetches the rate before booking
    later = dividend_job(ctx, "paper", kst("2026-09-15 09:00"))
    [booked] = later["booked"]
    assert (booked["net"], booked["amount_krw"]) == (D("9.34"), D("12936"))  # 9.34 x 1,385.0


def test_book_dividends_before_the_start_does_nothing(
    conn: sqlite3.Connection, cfg: Config
) -> None:
    with transaction(conn):
        assert book_dividends(conn, cfg, "paper", kst("2026-07-01 08:00")) == []


# ── the baseline ─────────────────────────────────────────────────────────────────────────


def day(world: World, d: str, kr_close: str, us_prev: str, us_close: str, rate: str) -> None:
    world.bar(KR, d, close=kr_close, open_=kr_close)
    world.bar(US, us_prev, close=us_close, open_=us_close)
    world.rate(kst(f"{d} 08:25"), rate)
    world.rate(kst(f"{d} 16:00"), rate)


def test_the_baseline_gets_the_same_dividends(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    first_day_world(world)
    check_job(ctx, "paper", kst("2026-07-01 08:30"))
    for t in ("09:05", "09:10"):
        stage_job(ctx, "paper", kst(f"2026-07-01 {t}"))
    snapshot_job(ctx, "paper", kst("2026-07-01 16:00"))
    stage_job(ctx, "paper", kst("2026-07-01 22:30"))
    world.dividend(KR, "2026-07-30", "183")  # paid 8/4

    day(world, "2026-07-29", "32500", "2026-07-28", "66.50", "1390.0")
    snapshot_job(ctx, "paper", kst("2026-07-29 16:00"))
    day(world, "2026-08-04", "32400", "2026-08-03", "66.40", "1389.0")
    dividend_job(ctx, "paper", kst("2026-08-04 08:00"))
    snapshot_job(ctx, "paper", kst("2026-08-04 16:00"))

    before = repo.get_snapshot(conn, "paper", date(2026, 7, 29))
    paid = repo.get_snapshot(conn, "paper", date(2026, 8, 4))
    assert before is not None
    assert paid is not None
    assert before.baseline_cash_krw == D("0")
    # The baseline held 156.25 KOSPI200 units (5,000,000 / 32,000): 156.25 x 183 = 28,594 after
    # rounding, tax 4,404, net 24,190 — kept as cash next to the units it does not touch.
    assert paid.baseline_cash_krw == D("24190")
    assert paid.baseline_units == before.baseline_units
    units = {k: D(v) for k, v in (paid.baseline_units or {}).items()}
    us_unit = round_won(D("66.40") * D("1389.0"))
    legs = round_won(units[KR] * D("32400")) + round_won(units[US] * us_unit)
    assert paid.baseline_krw == legs + D("24190")

    day(world, "2026-08-05", "32450", "2026-08-04", "66.45", "1388.0")
    nxt = snapshot_job(ctx, "paper", kst("2026-08-05 16:00"))
    row = repo.get_snapshot(conn, "paper", date(2026, 8, 5))
    assert row is not None
    assert row.baseline_cash_krw == D("24190")  # carried, not paid twice
    assert nxt["result"] == "ok"


def test_the_baseline_gets_dollar_dividends_and_its_first_days(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    first_day_world(world)
    check_job(ctx, "paper", kst("2026-07-01 08:30"))
    for t in ("09:05", "09:10"):
        stage_job(ctx, "paper", kst(f"2026-07-01 {t}"))
    snapshot_job(ctx, "paper", kst("2026-07-01 16:00"))
    stage_job(ctx, "paper", kst("2026-07-01 22:30"))
    world.dividend(KR, "2026-07-01", "50")  # ex on the start day: nobody held it before
    world.dividend(US, "2026-07-02", "0.239", pay_date="2026-07-06")  # held from the start
    day(world, "2026-07-06", "32100", "2026-07-02", "66.10", "1390.0")
    dividend_job(ctx, "paper", kst("2026-07-06 08:00"))
    snapshot_job(ctx, "paper", kst("2026-07-06 16:00"))
    row = repo.get_snapshot(conn, "paper", date(2026, 7, 6))
    assert row is not None
    # No snapshot before 7/2 holds units (7/1 is the start day), so the start purchase counts:
    # 5,000,000 / 91,872 units x $0.239 = $13.0068 -> $13.01, tax $1.96, net $11.05 x 1,390.0.
    assert row.baseline_cash_krw == usd_in_krw(D("11.05"), D("1390.0"))
    # The ledger got its own: 54 shares x $0.239 = $12.91 -> net $10.97.
    [event] = repo.events_of_ledger(conn, "paper", ["dividend"])
    assert (event.amount, event.currency) == (D("10.97"), Currency.USD)


def test_dividends_of_what_was_not_held_or_rounds_to_nothing(
    ctx: JobContext, conn: sqlite3.Connection, world: World, cfg: Config
) -> None:
    seed_ledger(
        conn,
        start=date(2026, 7, 1),
        start_amount=D("10000000"),
        krw=D("47675"),
        usd=D("0"),
        positions={KR: (1, D("36000"), D("36000"))},
    )
    world.dividend(US, "2026-09-11", "0.239", pay_date="2026-09-15")  # no US shares
    world.dividend(KR, "2026-09-11", "0.4", pay_date="2026-09-15")  # 1 x 0.4 won rounds to 0
    world.rate(kst("2026-09-15 07:00"), "1385.0")
    out = dividend_job(ctx, "paper", kst("2026-09-15 08:00"))
    assert (out["result"], out["booked"], out["waiting"]) == ("nothing-due", [], [])


def test_held_instruments_outside_the_rule_are_watched(
    conn: sqlite3.Connection, cfg: Config
) -> None:
    samsung = Instrument(
        "KR:005930", Market.KR, Currency.KRW, Kind.STOCK, "005930", "삼성전자", "005930.KS"
    )
    with transaction(conn):
        repo.upsert_instrument(conn, samsung, kst("2026-07-01 08:00"))
        state = repo.load_state(conn, "paper")
        positions = {"KR:005930": Position("KR:005930", Currency.KRW, 3, D("1"), D("1"))}
        repo.save_state(conn, "paper", replace(state, positions=positions), kst("2026-07-01"))
    ids = [i.instrument_id for i in watched_instruments(conn, "paper")]
    assert ids == [KR, US, "KR:005930"]


def test_a_broken_booking_is_reported(
    ctx: JobContext, conn: sqlite3.Connection, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed_0930(conn, world)

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("bad row")

    monkeypatch.setattr("autotrade.jobs.tasks.book_dividends", broken)
    out = dividend_job(ctx, "paper", kst("2026-09-30 08:00"))
    assert (out["result"], out["error"]) == ("failed", "RuntimeError: bad row")
    with pytest.raises(RuntimeError, match="bad row"):
        dividend_job(ctx, "paper", kst("2026-09-30 08:00"), dry_run=True)


def test_a_dividend_missed_during_an_outage_is_booked_on_its_pay_date(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_0930(conn, world)
    out = dividend_job(ctx, "paper", kst("2026-10-05 08:00"))  # server down 9/30 - 10/2
    [booked] = out["booked"]
    assert booked["pay_date"] == date(2026, 9, 30)
    [event] = repo.events_of_ledger(conn, "paper", ["dividend"])
    assert event.event_date == date(2026, 9, 30)  # the day it was paid
    assert event.occurred_at == kst("2026-10-05 08:00")  # when it was recorded
