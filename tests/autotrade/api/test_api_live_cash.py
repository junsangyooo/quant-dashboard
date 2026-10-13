"""What the screens show of the live ledger's money (D47·D48, 2026-10-13), through the web API.

- The rule card: the '환전 제안' chip and how much to convert for 50:50 when the won and the
  dollars are off the targets by more than the band; nothing within it. Information only: it is
  never a to-do and blocks nothing.
- The money the owner brought today: '새로 들어온 돈 · 다음 거래일 08:30부터', on the plan's 예정,
  the mode screen (live on, or the preview when turning on again) and the health screen.
- The owner's conversion is money moving between his accounts: the whole ledger's lists do not
  show it as a deposit or a withdrawal.
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

from ..fakes import World
from ..helpers import kst
from ..live_world import Live, make_live
from .support import PIN, owner_pin

D = Decimal
TARGET = {"kr": 50.0, "us": 50.0}


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
    """Won only, live from Tuesday evening; Wednesday 09:05 buys 310 KOSPI200 ETF shares."""
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    lw.fake.slip = D("160")
    lw.sync("2026-07-01 09:05")
    assert lw.stages()["result"] == "done"


def items_of(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {i["kind"]: i for i in plan["schedule"]["items"]}


def test_the_plan_shows_the_mix_and_the_money_that_waits(lw: Live, web: TestClient) -> None:
    first_buy(lw)
    lw.fake.deposit("KRW", D("3000000"))
    lw.sync("2026-07-01 10:00")
    assert lw.reconcile()["result"] == "match"
    lw.at("2026-07-01 10:01")
    plan = web.get("/api/plan?ledger=live").json()
    card = plan["rules"][0]
    # All in Korea: 310 x 32,000 + 3,078,512 cash = 12,998,512; half of it to dollars.
    assert card["status"] == "fx-suggest"
    assert card["fxSuggestion"] == {
        "direction": "krw-usd",
        "krw": 6499000,
        "usd": 4668.82,
        "rate": 1392.0,
        "now": {"kr": 100.0, "us": 0.0},
        "target": TARGET,
    }
    items = items_of(plan)
    # D48: the deposit of today waits for Thursday's check; it is not '새 현금 · 다음 확인'.
    assert items["new-money-wait"] == {
        "kind": "new-money-wait",
        "krw": 3000000,
        "usd": 0.0,
        "from": "2026-07-02T08:30:00+09:00",
    }
    assert "new-cash" not in items
    assert items["sub-share-cash"]["krw"] == 78512
    home = web.get("/api/home?ledger=live").json()
    assert home["planChip"]["status"] == home["planCard"]["status"] == "fx-suggest"

    # 10:30: the owner converts all of it. Still more won than dollars; the money of today is
    # now in dollars (and waits all the same).
    lw.fake.convert(D("3000000"), D("2155.17"))
    lw.sync("2026-07-01 10:30")
    assert lw.reconcile()["booked"][0]["conversion"] == "krw_to_usd"
    lw.at("2026-07-01 10:31")
    plan = web.get("/api/plan?ledger=live").json()
    assert items_of(plan)["new-money-wait"] == {
        "kind": "new-money-wait",
        "krw": 0,
        "usd": 2155.17,
        "from": "2026-07-02T08:30:00+09:00",
    }
    suggestion = plan["rules"][0]["fxSuggestion"]
    assert (suggestion["direction"], suggestion["krw"], suggestion["now"]) == (
        "krw-usd",
        3499000,
        {"kr": 76.9, "us": 23.1},
    )
    # The gauge reads the same mix (the dollars wait as cash: the instruments' weights alone
    # would still say 100 : 0).
    assert plan["rules"][0]["gauge"]["needle"] == {
        "now": {"kr": 76.9, "us": 23.1},
        "deviation": 26.9,
        "toThreshold": 0.0,
    }

    # The mode and health screens say the same while live is on, beside the to-dos.
    mode = web.get("/api/mode").json()
    assert mode["liveCash"]["newMoney"] == {
        "krw": 0,
        "usd": 2155.17,
        "from": "2026-07-02T08:30:00+09:00",
    }
    assert mode["liveCash"]["fxSuggestion"] == suggestion
    health = web.get("/api/health").json()
    assert health["liveCash"] == mode["liveCash"]
    assert health["todos"] == []
    assert (health["summary"]["kind"], health["summary"]["todoCount"]) == ("ok", 0)
    assert web.get("/api/shell").json()["status"]["kind"] == "ok"

    # The whole ledger's record lists the deposit, not the conversion's two halves.
    history = web.get("/api/history?ledger=live").json()
    kinds = [e["kind"] for m in history["months"] for e in m["events"]]
    assert kinds.count("deposit") == 1 and "withdrawal" not in kinds  # noqa: PT018
    counts = {k["kind"]: k["count"] for k in history["filters"]["kinds"]}
    assert (counts["deposit"], counts["withdrawal"]) == (1, 0)
    day = web.get("/api/day/2026-07-01?ledger=live").json()
    assert [e["kind"] for e in day["events"] if e["kind"] in ("deposit", "withdrawal")] == [
        "deposit"
    ]


def test_the_suggestion_goes_once_the_mix_is_back_in_the_band(lw: Live, web: TestClient) -> None:
    lw.fake.cash["USD"] = D("3592.00")
    lw.fake.cash["KRW"] = D("5000000")
    data = lw.turn_on("2026-06-30 21:00")
    assert data.suggestion is None  # 5,000,000원 and $3,592.00: 50.0 : 50.0
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    lw.fake.slip = D("160")
    lw.sync("2026-07-01 09:05")
    lw.stages()
    lw.fake.slip = D("0.33")
    lw.sync("2026-07-01 22:30")
    assert lw.stages()["result"] == "done"
    lw.reconcile()
    lw.at("2026-07-01 22:35")
    card = web.get("/api/plan?ledger=live").json()["rules"][0]
    assert (card["status"], card["fxSuggestion"]) == ("in-range", None)

    # 7/2 10:00: 1,000,000원 more: 54.6% in Korea, beyond the band.
    lw.fake.deposit("KRW", D("1000000"))
    lw.sync("2026-07-02 10:00")
    lw.reconcile()
    lw.at("2026-07-02 10:01")
    card = web.get("/api/plan?ledger=live").json()["rules"][0]
    assert card["status"] == "fx-suggest"
    assert (card["fxSuggestion"]["krw"], card["fxSuggestion"]["usd"]) == (502000, 360.63)
    # It blocks nothing: no to-do, and the next check plans as usual.
    assert web.get("/api/health").json()["summary"]["todoCount"] == 0

    # The owner converts what it says: back within the band, the chip and the line are gone.
    lw.fake.convert(D("502000"), D("360.63"))
    lw.sync("2026-07-02 10:30")
    assert lw.reconcile()["booked"][0]["conversion"] == "krw_to_usd"
    lw.at("2026-07-02 10:31")
    card = web.get("/api/plan?ledger=live").json()["rules"][0]
    assert (card["status"], card["fxSuggestion"]) == ("in-range", None)


def test_turning_on_again_leaves_the_money_of_the_check_day_for_the_next(
    lw: Live, web: TestClient, world: World
) -> None:
    lw.turn_on("2026-06-30 21:00")
    lw.turn_off("2026-06-30 21:30")
    # Wednesday 07:00, live off: the owner deposits; the tick's look books it all the same.
    lw.fake.deposit("KRW", D("1000000"))
    lw.sync("2026-07-01 07:00")
    assert lw.reconcile()["result"] == "match"
    lw.at("2026-07-01 07:05")
    lw.market_data()
    mode = web.get("/api/mode").json()
    assert mode["liveCash"] is None  # live is off
    preview = mode["preview"]
    assert preview["kind"] == "ok", preview
    # The 08:30 check would leave Wednesday's deposit for Thursday: 312 shares, not 343.
    assert [(o["instrument"]["id"], o["qty"]) for o in preview["stages"][0]["orders"]] == [
        ("KR:069500", 312)
    ]
    assert preview["newMoney"] == {"krw": 1000000, "usd": 0.0, "from": "2026-07-02T08:30:00+09:00"}
    assert preview["fxSuggestion"]["krw"] == 5500000
    assert kst("2026-07-01 07:05") == lw.now()


def test_no_amount_from_old_prices(lw: Live, web: TestClient, world: World) -> None:
    first_buy(lw)
    # Friday's check finds Thursday's closes missing (no source error, just nothing new):
    # '시세 대기'. The rows show '—', and no amount to convert comes from old numbers either
    # (the deposit of the day still waits, in won).
    world.rate(kst("2026-07-02 08:25"), "1392.0")
    lw.fake.deposit("KRW", D("1000000"))
    lw.sync("2026-07-03 08:29")  # Friday: Thursday's closes never came
    assert lw.reconcile()["result"] == "match"  # the tick's own look books the deposit
    assert lw.check("2026-07-03 08:30")["result"] == "quote-wait"
    lw.at("2026-07-03 08:31")
    plan = web.get("/api/plan?ledger=live").json()
    card = plan["rules"][0]
    assert (card["status"], card["fxSuggestion"]) == ("quote-wait", None)
    assert items_of(plan)["new-money-wait"]["krw"] == 1000000


def test_the_rule_picture_of_the_live_ledger_has_no_conversion(lw: Live, web: TestClient) -> None:
    first_buy(lw)
    lw.at("2026-07-01 09:10")
    # The rules screen reads the ledger of the mode (live here); paper keeps sell -> fx -> buy.
    live = web.get("/api/rules/index_half").json()
    assert live["display"]["action"] == {"stages": ["buy"]}
    assert live["status"] == "fx-suggest"
    # The band on live is where a conversion is suggested: the tile reads the mix (all won, 50%p
    # over), and nothing from the check (its drift is the whole rule's, across the currencies).
    assert live["display"]["mix"] is True
    assert live["display"]["condition"]["deviation"] == {"now": 50.0, "atCheck": None}


def test_no_live_screen_promises_a_rebalance_across_the_currencies(
    lw: Live, web: TestClient, world: World
) -> None:
    """D47: the live ledger never trades won into dollars. Where paper says how far a weight is
    from the band that rebalances ('리밸런싱까지'), live shows its won and dollars against the
    targets with the same band as the conversion's threshold ('환전 제안까지')."""
    first_buy(lw)
    lw.at("2026-07-01 10:01")
    plan = web.get("/api/plan?ledger=live").json()
    card = plan["rules"][0]
    mix_gauge = {
        "kind": "mix",
        "threshold": 2.0,
        "needle": {"now": {"kr": 100.0, "us": 0.0}, "deviation": 50.0, "toThreshold": 0.0},
    }
    assert (card["status"], card["gauge"]) == ("fx-suggest", mix_gauge)
    assert [(r["weight"], r["target"], r["toThreshold"]) for r in card["rows"]] == [
        (100.0, 50.0, None),
        (0.0, 50.0, None),
    ]
    assert web.get("/api/home?ledger=live").json()["planCard"]["gauge"] == mix_gauge
    assert lw.snapshot("2026-07-01 16:05")["result"] == "ok"
    lw.at("2026-07-01 16:10")
    drift = web.get("/api/plan?ledger=live").json()["drift"]
    assert drift["mix"] is True
    assert drift["lines"][0]["points"][-1] == {"date": "2026-07-01", "value": 50.0}

    # 16:20 the owner deposits; 7/2's check invests it in Korea: a plan of the rule that the
    # whole-rule drift (+50%p) did not cause. The day and the record leave that drift out.
    lw.fake.deposit("KRW", D("1000000"))
    lw.sync("2026-07-01 16:20")
    assert lw.reconcile()["result"] == "match"
    flat = {"2026-07-02 08:25": "1392.0", "2026-07-02 16:00": "1391.5"}
    for at, rate in flat.items():
        world.rate(kst(at), rate)
    lw.sync("2026-07-02 08:29")
    assert lw.check("2026-07-02 08:30")["result"] == "rebalance"
    lw.at("2026-07-02 08:40")
    day = web.get("/api/day/2026-07-02?ledger=live").json()
    assert (day["check"]["result"], day["check"]["band"]) == ("rebalance", None)
    assert {"instrument", "weight", "toThreshold", "over"}.isdisjoint(day["check"])
    history = web.get("/api/history?ledger=live").json()
    plans = [e for m in history["months"] for e in m["events"] if e["kind"] == "in-progress"]
    assert len(plans) == 1 and "deviation" not in plans[0]  # noqa: PT018
