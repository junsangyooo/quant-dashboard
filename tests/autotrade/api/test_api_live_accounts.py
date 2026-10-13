"""한국 계좌 · 미국 계좌 of the live ledger (api/views/accounts.py over engine/live.py).

The live ledger records the way paper does, so its won P&L splits exactly as paper's does:
한국 + 미국 × rate + 환율 효과 = ledger P&L. Live plans never convert (D47): the owner converts in
the Toss app, and his conversion is two events (out of one currency, into the other) that the
accounts read as a transfer; deposits the reconciliation finds are events in their own currency,
dated when they arrived; a start with dollars gives each account its own part. None of that money
moving is a gain or a loss of either account. Against the fake Toss only
(tests/autotrade/live_world.py).
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
from autotrade.db import repo
from autotrade.domain.instruments import Currency
from autotrade.domain.money import round_won
from autotrade.engine.rebuild import verify_ledger
from autotrade.jobs.tasks import adopt_job

from ..fakes import KR, World
from ..helpers import kst
from ..live_world import Live, make_live
from .support import PIN, owner_pin

D = Decimal


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


def account(home: dict[str, Any], account_id: str) -> dict[str, Any]:
    return next(a for a in home["accounts"]["list"] if a["id"] == account_id)


def cents(x: float) -> int:
    return round(x * 100)


def assert_split_adds_up(home: dict[str, Any]) -> dict[str, int]:
    """한국 + 미국 in won + 환율 효과 = the ledger's won P&L, and each part is what it says."""
    split: dict[str, int] = home["accounts"]["split"]
    rate = D(str(home["basis"]["fxRate"]))
    kr, us = account(home, "kr"), account(home, "us")
    assert split["kr"] + split["us"] + split["fx"] == home["pnl"]["amount"]
    assert split["kr"] == kr["pnl"]["amount"]
    assert split["us"] == int(round_won(D(str(us["pnl"]["amount"])) * rate))
    return split


def first_day(lw: Live) -> None:
    """Won only on the live ledger (D47): the Korean buy at 09:05 (310 shares: the limit price
    cuts the planned 312), then the owner deposits 5,000,000원 at 10:00 and converts 4,967,000원
    of it in the app at 10:05 (→ $3,567.53)."""
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    lw.fake.slip = D("160")
    lw.sync("2026-07-01 09:05")
    assert lw.stages()["result"] == "done"
    lw.fake.deposit("KRW", D("5000000"))
    lw.sync("2026-07-01 10:00")
    assert lw.reconcile()["result"] == "match"
    lw.fake.convert(D("4967000"), D("3567.53"))
    lw.sync("2026-07-01 10:05")
    assert lw.reconcile()["booked"][0]["conversion"] == "krw_to_usd"


def test_a_live_conversion_and_a_deposit_keep_the_split_exact(
    lw: Live, web: TestClient, world: World
) -> None:
    first_day(lw)
    # The owner's conversion is two events at the rate the balances show (4,967,000 ÷ 3,567.53),
    # dated when the account showed it (10:05): a transfer, not money in or out.
    rows = [
        e
        for e in repo.events_of_ledger(lw.conn, "live", ["deposit", "withdrawal"])
        if e.payload.get("reason") == "conversion"
    ]
    assert [(e.kind, e.amount, e.currency) for e in rows] == [
        ("withdrawal", D("4967000"), Currency.KRW),
        ("deposit", D("3567.53"), Currency.USD),
    ]
    assert {e.occurred_at for e in rows} == {kst("2026-07-01 10:05")}
    assert D(str(rows[1].payload["krw_rate"])) == D("1392.2798")
    assert repo.fills_of_ledger(lw.conn, "live")[0].kind == "trade"  # no fx fill: no fx order
    # A trade of ours is executed at the broker's fill time (the fake fills on arrival).
    buy = next(o for o in repo.orders_of_ledger(lw.conn, "live") if o.side == "buy")
    assert buy.executed_at == kst("2026-07-01 09:05")

    # 7/2: the owner sends $200, then 300,000원; the next looks find them. (The paper ledger's
    # jobs keep the closes and the rates; here market_data stands in for them.)
    world.rate(kst("2026-07-02 09:10"), "1395.0")
    lw.at("2026-07-02 09:50")
    lw.market_data()
    lw.fake.deposit("USD", D("200"))
    lw.sync("2026-07-02 10:00")
    seen = lw.now()
    assert lw.reconcile("2026-07-02 10:01")["result"] == "match"
    lw.fake.deposit("KRW", D("300000"))
    lw.sync("2026-07-02 10:05")
    assert lw.reconcile("2026-07-02 10:06")["result"] == "match"
    deposits = [
        e
        for e in repo.events_of_ledger(lw.conn, "live", ["deposit"])
        if e.payload.get("reason") == "unexplained-in" and e.event_date == date(2026, 7, 2)
    ]
    assert [(e.currency, e.amount) for e in deposits] == [
        (Currency.USD, D("200")),
        (Currency.KRW, D("300000")),
    ]
    usd_in = deposits[0]
    assert usd_in.occurred_at == seen  # when the money was first seen
    assert D(str(usd_in.payload["krw_rate"])) == D("1395.0")
    assert verify_ledger(lw.conn, "live") == []

    # 16:10: Korea closed higher, the dollar is weaker than at both the conversion and the deposit.
    world.bar(KR, "2026-07-02", close="32300", open_="32100")
    world.rate(kst("2026-07-02 16:00"), "1388.5")
    assert lw.snapshot("2026-07-02 16:05")["result"] == "ok"  # the day's valuation (16:00 rate)
    lw.at("2026-07-02 16:10")
    home = web.get("/api/home?ledger=live").json()
    assert home["basis"]["fxRate"] == 1388.5
    split = assert_split_adds_up(home)
    kr, us = account(home, "kr"), account(home, "us")
    # Each account: its value minus the money that came into it, in its own currency.
    # 한국: 10,000,000 + 5,000,000 deposited − 4,967,000 sent for dollars + 300,000 deposited.
    assert kr["pnl"]["amount"] == kr["total"] - 10333000
    # 미국: the $3,567.53 the conversion bought + the $200 deposited (cash only: no P&L).
    assert cents(us["pnl"]["amount"]) == cents(us["total"]) - 376753 == 0
    # 환율 효과 is what the rate did to the dollars that came in: those bought (worth 3,567.53 ×
    # 1,388.5 now, against the 4,967,000 they cost) and those deposited (booked at 1,395.0).
    rate = D("1388.5")
    expected = D("3567.53") * rate - D("4967000") + D("200") * (rate - D("1395.0"))
    assert abs(D(split["fx"]) - expected) <= 3
    # The breakdown of each account adds up and shows the conversion as a transfer.
    for account_id, transfer in (("kr", -4967000), ("us", 3567.53)):
        b = web.get(f"/api/home/breakdown?ledger=live&account={account_id}").json()
        parts = ("deposit", "withdrawal", "transfer", "market", "dividend", "fees")
        assert sum(cents(b[p]) for p in parts) == cents(b["end"]) - cents(b["start"])
        assert b["transfer"] == transfer
    b_us = web.get("/api/home/breakdown?ledger=live&account=us").json()
    assert (b_us["start"], b_us["deposit"]) == (0.0, 200.0)
    # The whole ledger: the conversion is no money in or out; the dollars count at their won.
    whole = web.get("/api/home/breakdown?ledger=live").json()
    assert whole["deposit"] == 5000000 + 279000 + 300000
    assert whole["withdrawal"] == 0
    whole_parts = ("deposit", "withdrawal", "market", "dividend", "fees")
    assert sum(whole[p] for p in whole_parts) == whole["end"] - whole["start"]


def test_a_start_with_dollars_gives_each_account_its_own(lw: Live, web: TestClient) -> None:
    lw.fake.cash["USD"] = D("500")
    lw.turn_on("2026-06-30 21:00")
    start = repo.start_event(lw.conn, "live")
    assert start is not None
    # The start amount is the ledger's, in won ($500 at 1,392.0); each currency keeps its part.
    assert (start.currency, start.amount) == (Currency.KRW, D("10696000"))
    assert start.payload["by_currency"] == {"KRW": "10000000", "USD": "500"}
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    lw.fake.slip = D("160")
    lw.sync("2026-07-01 09:05")
    assert lw.stages()["result"] == "done"

    assert lw.snapshot("2026-07-01 16:05")["result"] == "ok"  # valued at the 16:00 rate
    lw.at("2026-07-01 16:10")
    home = web.get("/api/home?ledger=live").json()
    assert home["basis"]["fxRate"] == 1391.5
    split = assert_split_adds_up(home)
    kr, us = account(home, "kr"), account(home, "us")
    # 미국 계좌 began with its $500 (no gain, no loss); 한국 계좌 with its 10,000,000원.
    assert (us["total"], us["pnl"]["amount"]) == (500.0, 0.0)
    assert kr["pnl"]["amount"] == kr["total"] - 10000000
    # The rate moved 1,392.0 → 1,391.5 on the start's dollars: −250원 of 환율 효과.
    assert abs(split["fx"] - (-250)) <= 1
    b_us = web.get("/api/home/breakdown?ledger=live&account=us").json()
    assert (b_us["start"], b_us["deposit"], b_us["end"]) == (500.0, 0.0, 500.0)
    b_kr = web.get("/api/home/breakdown?ledger=live&account=kr").json()
    assert b_kr["start"] == 10000000


def test_a_deposit_and_a_conversion_in_one_look_keep_the_split_exact(
    lw: Live, web: TestClient
) -> None:
    first_day(lw)
    # 7/2 09:00: the owner sends 3,000,000원 and converts 1,000,000원 of it before the next look
    # (won +2,000,000, dollars +$718.39): a deposit and a conversion, at the market rate.
    lw.fake.deposit("KRW", D("3000000"))
    lw.fake.convert(D("1000000"), D("718.39"))
    lw.sync("2026-07-02 09:00")
    booked = lw.reconcile("2026-07-02 09:01")["booked"]
    assert booked[0] == {"deposit": "2999999", "currency": "KRW", "event_id": booked[0]["event_id"]}
    assert booked[1]["conversion"] == "krw_to_usd"
    assert (booked[1]["from"], booked[1]["to"]) == ("999999", "718.39")
    lw.at("2026-07-02 09:05")
    home = web.get("/api/home?ledger=live").json()
    assert_split_adds_up(home)
    kr, us = account(home, "kr"), account(home, "us")
    assert kr["pnl"]["amount"] == kr["total"] - (10033000 + 2000000)
    assert cents(us["pnl"]["amount"]) == cents(us["total"]) - (356753 + 71839)
    b_us = web.get("/api/home/breakdown?ledger=live&account=us").json()
    assert (b_us["transfer"], b_us["deposit"]) == (4285.92, 0.0)


def test_adopted_dollar_shares_are_money_into_the_us_account(lw: Live, web: TestClient) -> None:
    first_day(lw)
    # 7/2: 5 S&P 500 ETF shares arrive from another broker. The ledger cannot explain them
    # (a mismatch: no order); the owner checks the app and adopts the account's numbers.
    lw.fake.hold("SPYM", D("5"), D("66.00"), market="US")
    lw.sync("2026-07-02 10:00")
    assert lw.reconcile("2026-07-02 10:01")["result"] == "mismatch"
    lw.sync("2026-07-02 10:05")
    adopted = adopt_job(lw.ctx, lw.now(), note="입고 확인")
    assert adopted["result"] == "adopted"
    [event] = [
        e
        for e in repo.events_of_ledger(lw.conn, "live", ["deposit"])
        if e.payload.get("source") == "adopt-broker"
    ]
    # The event is the net won; each currency keeps its own: 5 × $66.00 into 미국 계좌.
    assert event.payload["by_currency"] == {"KRW": "0", "USD": "330.00"}
    lw.at("2026-07-02 10:10")
    home = web.get("/api/home?ledger=live").json()
    assert_split_adds_up(home)
    us = account(home, "us")
    assert cents(us["pnl"]["amount"]) == cents(us["total"]) - (356753 + 33000)
    b_us = web.get("/api/home/breakdown?ledger=live&account=us").json()
    assert (b_us["deposit"], b_us["transfer"]) == (330.0, 3567.53)
