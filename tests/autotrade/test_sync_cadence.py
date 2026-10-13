"""How often the tick looks at Toss (engine/live.py fast_sync_reason, jobs/tick.py _broker_due).

Every tick while a market is open or anything of ours moves; every 30 minutes while both markets
are closed (nights, weekends, holidays). The derived effects pinned here: a live task that reads
the sync gets a fresh look on its own tick, a cancel (live off) goes out on the next tick, money
seen late on a closed evening is dated that day (D48), and the screens do not call the slower
look late.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from autotrade.api.views.live import link_source
from autotrade.db import live_repo, repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency
from autotrade.engine import live
from autotrade.engine.common import new_money_waiting

from .fakes import World
from .helpers import kst
from .live_world import Live, make_live

D = Decimal


@pytest.fixture
def lw(tmp_path: Path, world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[Live]:
    monkeypatch.setenv("AUTOTRADE_LIVE_ORDERS", "1")
    yield from make_live(tmp_path, world)


def looked(lw: Live, when: str) -> bool:
    """Run the live ledger's tick at `when`; whether it looked at Toss (the status' time)."""
    lw.tick(when)
    return lw.status().checked_at == kst(when)


@pytest.mark.parametrize(
    ("when", "closed"),
    [
        ("2026-06-30 21:00", True),  # Tuesday: KRX shut at 15:30, NYSE opens 22:30 (EDT)
        ("2026-06-30 22:30", False),  # NYSE open
        ("2026-07-01 05:00", True),  # NYSE closed at 16:00 ET
        ("2026-07-01 08:59", True),
        ("2026-07-01 09:00", False),  # KRX open
        ("2026-07-01 15:30", True),
        ("2026-07-03 23:00", True),  # NYSE holiday (Independence Day observed)
        ("2026-07-04 12:00", True),  # Saturday
        ("2026-01-06 23:00", True),  # winter: NYSE opens 23:30 KST (EST)
        ("2026-01-06 23:30", False),
        ("2028-01-04 03:00", False),  # past the calendars: look every tick
    ],
)
def test_both_markets_closed(when: str, closed: bool) -> None:
    assert live.markets_closed(kst(when)) is closed


def test_how_old_a_look_may_be(lw: Live) -> None:
    strict, slow = lw.cfg.broker_max_age, lw.cfg.broker_max_age + lw.cfg.broker_sync_slow
    assert (strict, slow) == (timedelta(minutes=15), timedelta(minutes=45))
    assert live.sync_max_age(lw.cfg, kst("2026-07-01 10:20")) == strict  # KRX open
    assert live.sync_max_age(lw.cfg, kst("2026-06-30 21:40")) == slow  # both closed
    # For 15 minutes after an open the last night look still counts, until the tick catches up.
    assert live.sync_max_age(lw.cfg, kst("2026-07-01 09:10")) == slow
    assert live.sync_max_age(lw.cfg, kst("2026-07-01 09:15")) == strict


def test_at_night_the_tick_looks_every_30_minutes(lw: Live) -> None:
    assert looked(lw, "2026-06-30 21:00")  # never looked before
    for minute in ("05", "10", "15", "20", "25"):
        assert not looked(lw, f"2026-06-30 21:{minute}")
    assert looked(lw, "2026-06-30 21:30")
    assert not looked(lw, "2026-06-30 21:35")
    assert looked(lw, "2026-06-30 22:00")
    assert looked(lw, "2026-06-30 22:30")
    assert looked(lw, "2026-06-30 22:35")  # NYSE open: every tick
    assert looked(lw, "2026-06-30 22:40")


def test_the_screens_do_not_call_the_night_look_late(lw: Live) -> None:
    lw.sync("2026-06-30 21:00")
    at_night = link_source(lw.conn, lw.cfg, kst("2026-06-30 21:40"))
    assert at_night is not None
    assert (at_night["state"], at_night["age"]) == ("fresh", 0.89)  # 40 of 45 minutes
    missed = link_source(lw.conn, lw.cfg, kst("2026-06-30 21:50"))  # a 30-minute look missed
    assert missed is not None
    assert (missed["state"], missed["extra"]["cause"]) == ("late", "old")
    lw.sync("2026-07-01 10:00")  # KRX open: the 15 minutes as before
    by_day = link_source(lw.conn, lw.cfg, kst("2026-07-01 10:20"))
    assert by_day is not None
    assert (by_day["state"], by_day["extra"]["cause"]) == ("late", "old")


def test_the_check_tick_looks_first(lw: Live) -> None:
    """08:30 is before both opens: the check's tick looks at Toss before it reconciles and plans,
    whenever the last night look was."""
    lw.turn_on("2026-06-30 21:00")
    assert looked(lw, "2026-07-01 08:10")
    assert not looked(lw, "2026-07-01 08:25")
    lines = lw.tick("2026-07-01 08:30")
    assert lw.status().checked_at == kst("2026-07-01 08:30")
    check = [line for line in lines if line["task"] == "check"]
    assert [line["result"] for line in check] == ["rebalance"]


def test_live_off_cancels_on_the_next_tick_and_a_change_keeps_every_tick(lw: Live) -> None:
    lw.turn_on("2026-06-30 21:00")
    lw.tick("2026-07-01 08:30")
    lw.fake.fill_mode = "open"
    lw.tick("2026-07-01 09:05")  # the buy is sent and stays open past the 15:30 close
    assert [o.status for o in lw.fake.ours()] == ["PENDING"]
    # 15:40: both markets closed, but an order of ours is open at Toss: every tick.
    assert live.fast_sync_reason(lw.conn, lw.cfg, kst("2026-07-01 15:40")) == "orders"
    with transaction(lw.conn):
        live.turn_off(lw.conn, lw.at("2026-07-01 15:41"))
    assert [r.order_id for r in live.cancel_pending(lw.conn)] != []
    assert looked(lw, "2026-07-01 15:45")
    assert [o.status for o in lw.fake.ours()] == ["CANCELED"]
    assert live.cancel_pending(lw.conn) == []
    assert live_repo.broker_orders_of(lw.conn, "live", live_repo.OPEN_STATES) == []
    # Just turned off: still every tick for 30 minutes (the 16:00 snapshot looks too).
    assert live.fast_sync_reason(lw.conn, lw.cfg, kst("2026-07-01 15:50")) == "mode-changed"
    assert looked(lw, "2026-07-01 15:50")
    assert looked(lw, "2026-07-01 16:00")
    assert live.fast_sync_reason(lw.conn, lw.cfg, kst("2026-07-01 16:15")) is None
    assert not looked(lw, "2026-07-01 16:15")
    assert looked(lw, "2026-07-01 16:30")


def test_money_seen_on_a_closed_evening_is_dated_that_day(lw: Live) -> None:
    """D48: money the account shows on day D is used from the next weekday's check. From 23:30
    KST the tick looks every time, so a Sunday-evening deposit is Sunday's (Monday's check uses
    it), not Monday's after midnight (Tuesday's)."""
    lw.turn_on("2026-06-30 21:00")
    assert looked(lw, "2026-07-05 23:00")  # Sunday night: the 30-minute look
    lw.fake.deposit("KRW", D("3000000"))
    assert not looked(lw, "2026-07-05 23:15")
    assert live.fast_sync_reason(lw.conn, lw.cfg, kst("2026-07-05 23:30")) == "day-end"
    assert looked(lw, "2026-07-05 23:30")
    deposits = repo.events_of_ledger(lw.conn, "live", ["deposit"])
    assert [(e.event_date, e.amount) for e in deposits] == [(date(2026, 7, 5), D("3000000"))]
    assert new_money_waiting(lw.conn, "live", kst("2026-07-06 08:30")) == {}
    # Seen at the check's own look it would be that day's money, kept from that check (D48).
    lw.fake.deposit("KRW", D("1000000"))
    assert looked(lw, "2026-07-06 00:00")  # Monday after midnight: 30 minutes after 23:30
    assert new_money_waiting(lw.conn, "live", kst("2026-07-06 08:30")) == {
        Currency.KRW: D("1000000")
    }


def test_the_turn_on_preview_keeps_every_tick(lw: Live) -> None:
    lw.sync("2026-06-30 21:00")
    assert not looked(lw, "2026-06-30 21:15")
    with transaction(lw.conn):
        live.request_sync(lw.conn, lw.at("2026-06-30 21:16"))
    assert looked(lw, "2026-06-30 21:20")
    assert looked(lw, "2026-06-30 21:25")
    assert live.fast_sync_reason(lw.conn, lw.cfg, kst("2026-06-30 21:46")) is None


def test_without_the_first_key_every_tick_only_records_off(
    tmp_path: Path, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("AUTOTRADE_LIVE_ORDERS", raising=False)
    for lw in make_live(tmp_path, world, with_key=False):
        lw.tick("2026-06-30 21:00")
        lw.tick("2026-06-30 21:05")
        assert lw.fake.calls == []  # nothing reaches Toss


def test_the_check_matches_only_a_fresh_account_even_at_night(lw: Live) -> None:
    """08:30 is a closed-market time, where the night cadence takes a snapshot up to 45 minutes
    old. The check's reconciliation keeps the strict 15 minutes: its tick looks at Toss first, so
    a look that failed means the account is not known now, and the check fails (retried at 09:30)
    instead of planning on the account as it was at 08:00."""
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:00")  # the last look: the night's 30-minute one
    report = lw.check("2026-07-01 08:30")  # this tick's own look did not happen (Toss down)
    assert report["result"] == "failed", report
    assert repo.open_plans(lw.conn, "live") == []
    assert lw.status().reconcile_state == "busy"
    # The screens still read the 08:00 look as current (the night cadence's 45 minutes).
    assert live.sync_max_age(lw.cfg, kst("2026-07-01 08:30")) == timedelta(minutes=45)
