"""The live ledger's first day against the fake Toss, end to end (PHASE3.md 2.3-2.6): turn on
with won only -> 08:30 check (reconcile first) -> 09:05 Korean buy at the broker -> nothing in
dollars: the live ledger never converts (D47) -> the ledger equals the account and its own
records, to the won."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest

from autotrade.db import live_repo, repo
from autotrade.domain.instruments import Currency
from autotrade.engine import live
from autotrade.engine.rebuild import verify_ledger
from autotrade.engine.todos import open_todos

from .fakes import World
from .live_world import Live, make_live

D = Decimal


@pytest.fixture
def lw(tmp_path: Path, world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[Live]:
    monkeypatch.setenv("AUTOTRADE_LIVE_ORDERS", "1")
    yield from make_live(tmp_path, world)


def test_turning_on_adopts_the_account(lw: Live) -> None:
    lw.fake.hold("005930", D("3"), D("70000"), name="삼성전자")  # outside the rules: untouched
    data = lw.turn_on("2026-06-30 21:00")
    start = repo.start_event(lw.conn, "live")
    assert start is not None
    assert start.amount == D("10000000")
    assert start.occurred_at == data.snapshot.taken_at
    assert start.payload["opening"]["cash"] == {"KRW": "10000000", "USD": "0"}
    assert [h["symbol"] for h in start.payload["outside"]] == ["005930"]
    state = lw.state()
    assert (state.cash_of(Currency.KRW), state.positions) == (D("10000000"), {})
    assert live.mode_of(lw.conn) == "live"
    kinds = [e.kind for e in repo.events_of_ledger(lw.conn, "live")]
    assert kinds == ["start", "live-on"]
    assert verify_ledger(lw.conn, "live") == []
    # Turning on again starts nothing new (인계 15: the same ledger goes on).
    with pytest.raises(live.LiveStartError):
        live.start_live(lw.conn, lw.cfg, data.snapshot, lw.now())


def test_the_first_day(lw: Live) -> None:
    lw.turn_on("2026-06-30 21:00")

    # 08:30: the account is read and matched first, then the plan. Won only: all of it buys
    # the Korean ETF (D47); there is no conversion and no US order.
    assert lw.sync("2026-07-01 08:29")["result"] in ("synced", "quiet")
    report = lw.check("2026-07-01 08:30")
    assert report["result"] == "rebalance", report
    assert report["details"]["reconcile"] == {"state": "match", "reason": None}
    assert report["details"]["planned"]["fx"] is None
    orders = {(o.side, o.market): o for o in repo.orders_of_ledger(lw.conn, "live")}
    assert list(orders) == [("buy", "KR")]
    # Sized as the send will pay at the 32,000 close: the limit 0.5% over it on the 5-won tick
    # (32,160) plus the fee, floor(10,000,000 / (32,160 x 1.00015)) = 310.
    assert orders[("buy", "KR")].qty == 310
    stages = repo.stages_of(lw.conn, orders[("buy", "KR")].plan_id)
    assert [(s.kind, s.market) for s in stages] == [("buy", "KR")]

    # 09:00: nothing is due; nothing leaves.
    lw.sync("2026-07-01 09:00")
    assert lw.fake.ours() == []

    # 09:05: the Korean buy goes out as a limit order 0.5% over the price, on the 5-won tick:
    # the price has not moved, so the cash pays all 310 at that limit.
    lw.fake.slip = D("160")  # it fills at 32,000
    sync = lw.sync("2026-07-01 09:05")
    sent = [c for c in sync["changes"] if "sent" in c]
    assert sent == [
        {
            "order_id": orders[("buy", "KR")].order_id,
            "sent": "ord-0001",
            "qty": 310,
            "price": "32160",
            "resend": False,
        }
    ]
    assert lw.fake.ours()[0].body["price"] == "32160"
    stage = lw.stages()
    assert stage["result"] == "done", stage
    fill = repo.fill_of_order(lw.conn, orders[("buy", "KR")].order_id)
    assert fill is not None
    assert (fill.qty, fill.gross, fill.fee, fill.executor) == (310, D("9920000"), D("1488"), "toss")
    assert fill.price_source == "toss:ord-0001"
    plan = repo.get_plan(lw.conn, orders[("buy", "KR")].plan_id)
    assert plan.status == "done"

    # Nothing to convert, nothing to do by hand; 22:30 sends nothing.
    assert [t.kind for t in open_todos(lw.conn, "live")] == []
    lw.sync("2026-07-01 22:30")
    assert len(lw.fake.ours()) == 1
    assert lw.reconcile()["result"] in ("match", "quiet")
    state = lw.state()
    assert state.qty_of("KR:069500") == 310
    assert state.qty_of("US:SPYM") == 0
    # The won the limit left over (78,512) is the next check's to buy.
    assert state.cash_of(Currency.KRW) == lw.fake.cash["KRW"] == D("78512")
    assert state.cash_of(Currency.USD) == lw.fake.cash["USD"] == D("0")
    assert verify_ledger(lw.conn, "live") == []
    assert lw.status().reconcile_state == "match"
    assert live_repo.broker_orders_of(lw.conn, "live", live_repo.OPEN_STATES) == []


def test_the_tick_runs_the_live_turn_quietly(lw: Live) -> None:
    lw.turn_on("2026-06-30 21:00")
    first = lw.tick("2026-07-01 08:30")
    # The first match is news; the check reconciles again (no change) and plans.
    assert [(line["task"], line["result"]) for line in first] == [
        ("reconcile", "match"),
        ("check", "rebalance"),
    ]
    lw.fake.slip = D("160")
    second = lw.tick("2026-07-01 09:05")
    assert [(line["task"], line["result"]) for line in second] == [
        ("broker", "synced"),
        ("stages", "done"),
    ]
    assert lw.tick("2026-07-01 09:06") == []  # nothing changed: nothing written
    assert live_repo.get_status(lw.conn) is not None
