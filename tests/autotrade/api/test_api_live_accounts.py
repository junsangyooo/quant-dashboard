"""한국 계좌 · 미국 계좌 of the live ledger (api/views/accounts.py over engine/live.py).

The live ledger records the way paper does, so its won P&L splits exactly as paper's does:
한국 + 미국 × rate + 환율 효과 = ledger P&L. A conversion the plan asked for (the owner makes it in
the Toss app) is the fx fill of its fx order, executed when the account showed it; deposits the
reconciliation finds are events in their own currency, dated when they arrived; a start with
dollars gives each account its own part. None of that money moving is a gain or a loss of either
account. Against the fake Toss only (tests/autotrade/live_world.py).
"""

from __future__ import annotations

from collections.abc import Iterator
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
    """예시-값표 §4 on the live ledger: the Korean buy at 09:05, the owner's conversion in the
    app at 22:31 (4,967,000원 → $3,567.53), the US buy at 22:36 (as in test_live_flow.py)."""
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    lw.fake.slip = D("160")
    lw.sync("2026-07-01 09:05")
    assert lw.stages()["result"] == "done"
    lw.sync("2026-07-01 09:10")
    lw.stages()
    lw.fake.convert(D("4967000"), D("3567.53"))
    lw.sync("2026-07-01 22:31")
    assert lw.reconcile()["result"] == "match"
    lw.fake.slip = D("0.33")
    lw.sync("2026-07-01 22:36")
    assert lw.stages()["result"] == "done"
    assert lw.reconcile()["result"] in ("match", "quiet")


def test_a_live_conversion_and_a_deposit_keep_the_split_exact(
    lw: Live, web: TestClient, world: World
) -> None:
    first_day(lw)
    orders = {o.side: o for o in repo.orders_of_ledger(lw.conn, "live") if o.market != "US"}

    # The conversion is the fx fill of the plan's fx order, like paper's: won paid, dollars
    # credited, executed when the account showed it (22:31), not when the tick booked it.
    fx = repo.get_order(lw.conn, orders["fx"].order_id)
    fill = repo.fill_of_order(lw.conn, fx.order_id)
    assert fill is not None
    assert (fill.kind, fill.fx_direction, fill.gross, fill.received) == (
        "fx",
        "krw_to_usd",
        D("4967000"),
        D("3567.53"),
    )
    assert fx.executed_at == kst("2026-07-01 22:31")
    # A trade of ours is executed at the broker's fill time too (the fake fills on arrival).
    buy = repo.get_order(lw.conn, orders["buy"].order_id)
    assert buy.executed_at == kst("2026-07-01 09:05")

    # 7/2: the owner sends $200 and 300,000원 to the account; the next look finds them. (The
    # paper ledger's jobs keep the closes and the rates; here market_data stands in for them.)
    world.rate(kst("2026-07-02 09:10"), "1395.0")
    lw.at("2026-07-02 09:50")
    lw.market_data()
    lw.fake.deposit("USD", D("200"))
    lw.fake.deposit("KRW", D("300000"))
    lw.sync("2026-07-02 10:00")
    seen = lw.now()
    assert lw.reconcile("2026-07-02 10:01")["result"] == "match"
    deposits = repo.events_of_ledger(lw.conn, "live", ["deposit"])
    assert sorted((e.currency.value, e.amount) for e in deposits if e.currency) == [
        ("KRW", D("300000")),
        ("USD", D("200")),
    ]
    assert {e.occurred_at for e in deposits} == {seen}  # when the money was first seen
    usd_in = next(e for e in deposits if e.currency is Currency.USD)
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
    # 한국: 10,000,000 − 4,967,000 sent for dollars + 300,000 deposited.
    assert kr["pnl"]["amount"] == kr["total"] - 5333000
    # 미국: the $3,567.53 the conversion bought + the $200 deposited.
    assert cents(us["pnl"]["amount"]) == cents(us["total"]) - 376753
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


def test_an_outside_conversion_is_a_transfer_between_the_accounts(
    lw: Live, web: TestClient
) -> None:
    first_day(lw)
    # 7/2: the owner sends 2,000,000원, then converts 1,392,000원 of it on their own (no plan
    # asked for it): money in for 한국 계좌, then a transfer to 미국 계좌.
    lw.fake.deposit("KRW", D("2000000"))
    lw.sync("2026-07-02 09:00")
    assert lw.reconcile("2026-07-02 09:01")["booked"][0]["deposit"] == "2000000"
    lw.fake.convert(D("1392000"), D("1000.00"))
    lw.sync("2026-07-02 10:00")
    assert lw.reconcile("2026-07-02 10:01")["booked"][0]["conversion"] == "krw_to_usd"
    lw.at("2026-07-02 10:05")
    home = web.get("/api/home?ledger=live").json()
    assert_split_adds_up(home)
    kr, us = account(home, "kr"), account(home, "us")
    assert kr["pnl"]["amount"] == kr["total"] - (5033000 + 2000000 - 1392000)
    assert cents(us["pnl"]["amount"]) == cents(us["total"]) - (356753 + 100000)
    b_us = web.get("/api/home/breakdown?ledger=live&account=us").json()
    assert (b_us["transfer"], b_us["deposit"]) == (4567.53, 0.0)


def test_adopted_dollar_shares_are_money_into_the_us_account(lw: Live, web: TestClient) -> None:
    first_day(lw)
    # 7/2: 5 more S&P 500 ETF shares arrive from another broker. The ledger cannot explain them
    # (a mismatch: no order); the owner checks the app and adopts the account's numbers.
    lw.fake.holdings["SPYM"].qty += D("5")
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
