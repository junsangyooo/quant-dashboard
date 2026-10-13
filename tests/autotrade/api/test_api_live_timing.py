"""Money that arrives after a day's 16:00 value (the live ledger's deposits come at any hour).

Each day's value is taken at 16:00, so money counts in the period whose closing value first
holds it: after the opening value and by the closing one (api/views/series.py). A deposit at
20:00 is the next value's, never a loss of its own day; one on the evening of the month's last
weekday is the next month's; a live ledger turned on after its first day's snapshot ran is worth
its start that day. The same rule places the money of '손대지 않았을 때' (engine/snapshot.py).
Against the fake Toss only (tests/autotrade/live_world.py).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from autotrade.api.app import create_app
from autotrade.api.settings import ApiSettings
from autotrade.api.views import series
from autotrade.db import repo
from autotrade.domain.baseline import add_units, krw_unit_price, units_for_amount
from autotrade.domain.instruments import Currency
from autotrade.market.service import prefetch_fx

from ..fakes import KR, World
from ..helpers import kst
from ..live_world import Live, make_live
from .support import PIN, owner_pin

D = Decimal
USD = Currency.USD


@pytest.fixture
def lw(tmp_path: Path, world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[Live]:
    monkeypatch.setenv("AUTOTRADE_LIVE_ORDERS", "1")
    yield from make_live(tmp_path, world)


@pytest.fixture
def web(lw: Live, tmp_path: Path) -> Iterator[TestClient]:
    settings = ApiSettings(
        secret_path=tmp_path / "autotrade.secret", dist_dir=tmp_path / "dist", scrypt_n=2**10
    )
    owner_pin(lw.conn, settings)
    app = create_app(lw.cfg, settings, lw.now)
    with TestClient(app, base_url="https://testserver") as client:
        assert client.post("/api/auth/pin", json={"pin": PIN}).status_code == 204
        yield client


def first_buy(lw: Live) -> None:
    """Wednesday 7/1: the 08:30 check plans the won-only start, 09:05 buys 310 KOSPI200 ETF."""
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    lw.fake.slip = D("160")
    lw.sync("2026-07-01 09:05")
    assert lw.stages()["result"] == "done"


def flat_thursday(world: World) -> None:
    """7/2 closes where 7/1 did, the rate too: the 7/2 value moves only by money in."""
    world.rate(kst("2026-07-02 08:25"), "1392.0")
    world.bar(KR, "2026-07-02", close="32050", open_="32050")
    world.rate(kst("2026-07-02 16:00"), "1391.5")


def rows_of(history: dict[str, Any]) -> list[tuple[str, str, Any, Any, Any]]:
    return [
        (e["date"], e["kind"], e.get("amount"), e["dayChange"], e["dayTotal"])
        for m in history["months"]
        for e in m["events"]
    ]


def test_a_deposit_after_the_days_value_is_the_next_values(
    lw: Live, web: TestClient, world: World
) -> None:
    # The 09:10 rate of the start day prices '손대지 않았을 때' (the paper ledger's jobs keep it).
    world.rate(kst("2026-06-30 08:25"), "1392.0")
    prefetch_fx(lw.conn, lw.ctx.sources, kst("2026-06-30 09:10"))
    lw.turn_on("2026-06-30 21:00")
    lw.tick("2026-06-30 21:05")  # the start day's snapshot
    first_buy(lw)
    assert lw.snapshot("2026-07-01 16:05")["result"] == "ok"
    # 20:00: the owner deposits 1,000,000원, after the day's value was taken.
    lw.fake.deposit("KRW", D("1000000"))
    lw.sync("2026-07-01 20:00")
    assert lw.reconcile("2026-07-01 20:01")["booked"] == [
        {"deposit": "1000000", "currency": "KRW", "event_id": 3}
    ]
    flat_thursday(world)
    assert lw.snapshot("2026-07-02 16:05")["result"] == "ok"
    lw.at("2026-07-02 16:10")

    # 7/1: the market made 14,012원 (310 x 32,050 + 78,512 - 10,000,000); the deposit is not in
    # that day's value. 7/2: a flat market, the deposit is in the value and in the money in.
    day1 = web.get("/api/day/2026-07-01?ledger=live").json()
    assert (day1["total"], day1["change"]) == (10014012, {"amount": 14012, "pct": 0.14})
    assert [e["kind"] for e in day1["events"]] == ["deposit"]  # listed on the day it came
    day2 = web.get("/api/day/2026-07-02?ledger=live").json()
    assert (day2["total"], day2["change"]) == (11014012, {"amount": 0, "pct": 0.0})
    history = web.get("/api/history?ledger=live").json()
    assert rows_of(history)[0] == ("2026-07-01", "deposit", 1000000, 14012, 10014012)
    home = web.get("/api/home?ledger=live").json()
    assert home["pnl"]["amount"] == 14012
    assert [(m["month"], m["change"]) for m in history["months"]] == [
        ("2026-07", 14012),
        ("2026-06", 0),
    ]
    breakdown = web.get("/api/home/breakdown?ledger=live").json()
    assert {k: breakdown[k] for k in ("start", "deposit", "market", "fees", "end")} == {
        "start": 10000000,
        "deposit": 1000000,
        "market": 15500,
        "fees": -1488,
        "end": 11014012,
    }
    # '손대지 않았을 때' bought with the deposit at the 7/2 value's prices (by date it fell
    # between two values and was never added: the line read 1,000,000원 short ever after).
    s1, s2 = repo.snapshots_of_ledger(lw.conn, "live")[-2:]
    assert s1.baseline_units is not None and s2.baseline_units is not None  # noqa: PT018
    assert s2.contributions - s1.contributions == D("1000000")
    prices = {"KR:069500": D("32050"), "US:SPYM": krw_unit_price(D("66.20"), USD, D("1391.5"))}
    bought = units_for_amount(D("1000000"), {k: D("0.5") for k in prices}, prices)
    before = {k: D(v) for k, v in s1.baseline_units.items()}
    assert {k: D(v) for k, v in s2.baseline_units.items()} == add_units(before, bought)
    assert s2.baseline_krw is not None
    assert home["baseline"]["pct"] == float(
        ((s2.baseline_krw - s2.contributions) / s2.contributions * 100).quantize(D("0.01"))
    )


def test_a_deposit_on_the_months_last_evening_is_the_next_months(
    lw: Live, web: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(series, "MIN_RECORD_DAYS", 2)  # period chips from the second value
    lw.turn_on("2026-06-30 21:00")
    lw.tick("2026-06-30 21:05")  # the 6/30 snapshot (the last weekday of June)
    lw.fake.deposit("KRW", D("1000000"))
    lw.sync("2026-06-30 21:30")
    assert lw.reconcile("2026-06-30 21:31")["result"] == "match"
    first_buy(lw)
    assert lw.snapshot("2026-07-01 16:05")["result"] == "ok"
    lw.at("2026-07-01 16:10")

    history = web.get("/api/history?ledger=live").json()
    home = web.get("/api/home?ledger=live&period=1m").json()
    assert home["pnl"]["amount"] == 15413
    # June's value (21:05) was taken before the deposit: June made nothing, July all of it
    # (it was −1,000,000원 and +1,015,413원).
    assert [(m["month"], m["change"]) for m in history["months"]] == [
        ("2026-07", 15413),
        ("2026-06", 0),
    ]
    # The month's period opens with the 6/30 value: the deposit after it is the period's money in.
    assert home["trend"]["periodPnl"] == {"amount": 15413, "pct": 0.15}
    breakdown = web.get("/api/home/breakdown?ledger=live&period=1m").json()
    assert {k: breakdown[k] for k in ("from", "start", "deposit", "market", "fees", "end")} == {
        "from": "2026-06-30",
        "start": 10000000,
        "deposit": 1000000,
        "market": 17050,
        "fees": -1637,  # 7/1 bought with both (the deposit was new money of 6/30)
        "end": 11015413,
    }
    day = web.get("/api/day/2026-07-01?ledger=live").json()
    assert day["change"]["amount"] == 15413


def test_a_live_start_after_its_days_snapshot(
    lw: Live, web: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Turned on after the US open on the month's last weekday: no snapshot that day (a Friday
    before a month-end weekend is the same: no value in the start month)."""
    monkeypatch.setattr(series, "MIN_RECORD_DAYS", 1)
    lw.turn_on("2026-06-30 23:00")
    assert "snapshot" not in [line.get("task") for line in lw.tick("2026-06-30 23:05")]
    lw.at("2026-06-30 23:10")
    day = web.get("/api/day/2026-06-30?ledger=live").json()
    # Worth its start that day (not 0): nothing was revalued, nothing earned.
    assert (day["total"], day["change"]) == (10000000, None)
    first_buy(lw)
    assert lw.snapshot("2026-07-01 16:05")["result"] == "ok"
    lw.at("2026-07-01 16:10")

    history = web.get("/api/history?ledger=live").json()
    # June made nothing (it was −10,000,000원 and July +10,014,012원).
    assert [(m["month"], m["change"]) for m in history["months"]] == [
        ("2026-07", 14012),
        ("2026-06", 0),
    ]
    assert [r[4] for r in rows_of(history)] == [10000000, 10000000]  # live-on, start
    assert web.get("/api/day/2026-06-30?ledger=live").json()["total"] == 10000000
    # A period reaching back to the start opens with the start (no value on or before it).
    home = web.get("/api/home?ledger=live&period=1m").json()
    assert home["pnl"]["amount"] == 14012
    assert home["trend"]["periodPnl"] == {"amount": 14012, "pct": 0.14}
    breakdown = web.get("/api/home/breakdown?ledger=live&period=1m").json()
    assert {k: breakdown[k] for k in ("from", "start", "deposit", "market", "fees", "end")} == {
        "from": "2026-06-30",
        "start": 10000000,
        "deposit": 0,
        "market": 15500,
        "fees": -1488,
        "end": 10014012,
    }


def test_money_booked_late_with_an_earlier_time_enters_the_next_value_once(
    lw: Live, world: World
) -> None:
    """The account is not read between an app buy and the day's value (Toss did not answer): the
    next day's reconciliation books the money that paid for it at the buy's time, before that
    value, dated the day the account showed it (engine/live.py _book_in_order). The value it first
    enters takes it in its money in, and '손대지 않았을 때' moves by it there, once."""
    world.rate(kst("2026-06-30 08:25"), "1392.0")
    prefetch_fx(lw.conn, lw.ctx.sources, kst("2026-06-30 09:10"))
    lw.turn_on("2026-06-30 21:00")
    lw.tick("2026-06-30 21:05")
    first_buy(lw)
    lw.at("2026-07-01 15:00")
    lw.fake.deposit("KRW", D("5000000"))
    lw.fake.app_trade("005930", "BUY", D("70"), D("70000"), commission=D("735"))
    assert lw.snapshot("2026-07-01 16:05")["result"] == "ok"
    flat_thursday(world)
    lw.sync("2026-07-02 09:00")
    assert lw.reconcile("2026-07-02 09:01")["result"] == "match"
    # Both at the buy's time, before the 7/1 value; the money in dated the day the account showed
    # it (D48), the buy's money out its own day: neither date says it came after that value.
    booked = repo.events_of_ledger(lw.conn, "live", ["deposit", "withdrawal"])
    assert [(e.kind, e.occurred_at, e.event_date, e.created_at) for e in booked] == [
        ("deposit", kst("2026-07-01 15:00"), date(2026, 7, 2), kst("2026-07-02 09:01")),
        ("withdrawal", kst("2026-07-01 15:00"), date(2026, 7, 1), kst("2026-07-02 09:01")),
    ]
    assert lw.snapshot("2026-07-02 16:05")["result"] == "ok"
    world.bar(KR, "2026-07-03", close="32050", open_="32050")
    world.rate(kst("2026-07-03 16:00"), "1391.5")
    assert lw.snapshot("2026-07-03 16:05")["result"] == "ok"

    s1, s2, s3 = repo.snapshots_of_ledger(lw.conn, "live")[-3:]
    # In 5,000,000원, out the 4,900,735원 of the buy outside the rules.
    assert s2.contributions - s1.contributions == D("99265")
    assert s1.baseline_units is not None and s2.baseline_units is not None  # noqa: PT018
    prices = {"KR:069500": D("32050"), "US:SPYM": krw_unit_price(D("66.20"), USD, D("1391.5"))}
    targets = {k: D("0.5") for k in prices}
    before = {k: D(v) for k, v in s1.baseline_units.items()}
    moved = add_units(before, units_for_amount(D("5000000"), targets, prices))
    moved = add_units(moved, units_for_amount(D("4900735"), targets, prices), -1)
    assert {k: D(v) for k, v in s2.baseline_units.items()} == moved
    # 7/3: that money is the 7/2 value's already.
    assert s3.contributions == s2.contributions
    assert s3.baseline_units == s2.baseline_units
