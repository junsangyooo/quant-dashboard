"""The live ledger's first day against the fake Toss, end to end (PHASE3.md 2.3-2.6):
turn on -> 08:30 check (reconcile first) -> 09:05 Korean buy at the broker -> 09:10 the owner
converts in the app -> the reconciliation books it -> 22:30 US buy -> the ledger equals the
account and its own records, to the won and the cent."""

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
from autotrade.timeutil import KST

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

    # 08:30: the account is read and matched first, then the plan (§4 numbers).
    assert lw.sync("2026-07-01 08:29")["result"] in ("synced", "quiet")
    report = lw.check("2026-07-01 08:30")
    assert report["result"] == "rebalance", report
    assert report["details"]["reconcile"] == {"state": "match", "reason": None}
    orders = {(o.side, o.market): o for o in repo.orders_of_ledger(lw.conn, "live")}
    assert orders[("buy", "KR")].qty == 156
    assert orders[("fx", "FX")].est_amount == D("4967000")
    assert orders[("buy", "US")].qty == 54

    # 09:00: nothing is due; nothing leaves.
    lw.sync("2026-07-01 09:00")
    assert lw.fake.ours() == []

    # 09:05: the Korean buy goes out as a limit order 0.5% over the price, on the 5-won tick.
    lw.fake.slip = D("160")  # it fills at 32,000
    sync = lw.sync("2026-07-01 09:05")
    sent = [c for c in sync["changes"] if "sent" in c]
    assert sent == [
        {"order_id": orders[("buy", "KR")].order_id, "sent": "ord-0001", "qty": 156, "price": "32160", "resend": False}
    ]
    assert lw.fake.ours()[0].body["price"] == "32160"
    stage = lw.stages()
    assert stage["result"] == "done", stage
    fill = repo.fill_of_order(lw.conn, orders[("buy", "KR")].order_id)
    assert fill is not None
    assert (fill.qty, fill.gross, fill.fee, fill.executor) == (156, D("4992000"), D("749"), "toss")
    assert fill.price_source == "toss:ord-0001"

    # 09:10: the conversion is the owner's (the API has none). A manual to-do with the numbers.
    lw.sync("2026-07-01 09:10")
    assert lw.stages()["result"] == "quiet"  # nothing but waiting: no run written
    todos = [t for t in open_todos(lw.conn, "live") if t.kind == "fx-manual"]
    assert [(t.facts["amount"], t.facts["est_received"]) for t in todos] == [
        (D("4967000"), D("3568.24"))
    ]
    fx_due = live.fx_todos(lw.conn, lw.now())
    assert len(fx_due) == 1
    assert fx_due[0].by is not None
    assert fx_due[0].by.astimezone(KST).strftime("%H:%M") == "22:30"
    # The US buy is not sent while the dollars are missing.
    lw.sync("2026-07-01 22:30")
    assert len(lw.fake.ours()) == 1

    # The owner converts at the app's rate; the next look at the account books it.
    lw.fake.convert(D("4967000"), D("3567.53"))
    lw.sync("2026-07-01 22:31")
    booked = lw.reconcile()
    assert booked["result"] == "match"
    assert booked["booked"][0]["conversion"] == "krw_to_usd"
    fx_fill = repo.fill_of_order(lw.conn, orders[("fx", "FX")].order_id)
    assert fx_fill is not None
    assert (fx_fill.gross, fx_fill.received, fx_fill.krw_rate) == (
        D("4967000"),
        D("3567.53"),
        D("1392.2798"),  # 4,967,000 ÷ 3,567.53
    )
    assert live.fx_todos(lw.conn, lw.now()) == []
    us_stage = [s for s in repo.stages_of(lw.conn, orders[("buy", "US")].plan_id) if s.market == "US"]
    assert us_stage[0].due_at.astimezone(KST).strftime("%m-%d %H:%M") == "07-01 22:30"  # due already: the next sync sends it

    # The US buy: a dollar limit 0.5% over, cut to the dollars there are (53, not 54).
    lw.fake.slip = D("0.33")
    lw.sync("2026-07-01 22:36")
    us_order = lw.fake.ours()[1]
    assert (us_order.body["price"], us_order.body["quantity"]) == ("66.33", "53")
    assert lw.stages()["result"] == "done"
    assert lw.reconcile()["result"] in ("match", "quiet")
    state = lw.state()
    assert state.qty_of("KR:069500") == 156
    assert state.qty_of("US:SPYM") == 53
    assert state.cash_of(Currency.KRW) == lw.fake.cash["KRW"] == D("40251")
    assert state.cash_of(Currency.USD) == lw.fake.cash["USD"] == D("66.03")
    assert verify_ledger(lw.conn, "live") == []
    plan = repo.get_plan(lw.conn, orders[("buy", "KR")].plan_id)
    assert plan.status == "done"
    assert lw.status().reconcile_state == "match"


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
