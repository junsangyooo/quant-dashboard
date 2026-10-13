"""The live money path after the audit of 2026-10-13: each finding as the auditor found it, now
asserting the right behavior. Against the fake Toss (tests/autotrade/live_world.py).

3. A partly filled order that ends in the CLOSED list with PARTIAL_FILLED.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest

from autotrade.db import live_repo, repo
from autotrade.domain.instruments import Currency
from autotrade.engine import live
from autotrade.engine.rebuild import verify_ledger

from .fakes import KR, US, World
from .helpers import kst
from .live_world import Live, make_live

D = Decimal
KRW, USD = Currency.KRW, Currency.USD


@pytest.fixture
def lw(tmp_path: Path, world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[Live]:
    monkeypatch.setenv("AUTOTRADE_LIVE_ORDERS", "1")
    for d in ("2026-07-02", "2026-07-03"):
        world.bar(KR, d, close="32050", open_="32050")
        world.bar(US, d, close="66.20", open_="66.20")
    for t in ("2026-07-02 08:25", "2026-07-03 08:25", "2026-07-06 08:25"):
        world.rate(kst(t), "1392.0")
    yield from make_live(tmp_path, world)


def invested(lw: Live) -> None:
    """Live from Tuesday evening with 10,000,000 won; Wednesday 09:05 buys 310 shares at the
    32,160 limit, which leaves 28,905 won."""
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    lw.sync("2026-07-01 09:05")
    lw.stages()
    lw.sync("2026-07-01 09:10")
    assert lw.reconcile()["result"] in ("match", "quiet")
    assert lw.state().cash_of(KRW) == D("28905")


def events(lw: Live, *kinds: str) -> list[tuple[str, Decimal | None, Currency | None, str]]:
    rows = repo.events_of_ledger(lw.conn, "live", list(kinds))
    return [(e.kind, e.amount, e.currency, str(e.payload.get("reason"))) for e in rows]


# ── 3. a partial fill that ends PARTIAL_FILLED in the CLOSED list ────────────────────────


@pytest.mark.parametrize("canceled_at", [False, True])
def test_a_partial_fill_closed_as_partial_filled_is_booked(lw: Live, canceled_at: bool) -> None:
    """openapi.json 1.2.24 lists PARTIAL_FILLED among the CLOSED statuses too: a day order whose
    rest lapsed may keep it. Over when the CLOSED list has it or it has a cancel time; the 100
    shares that filled are booked, the rest is dropped and the next check plans again."""
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    lw.fake.fill_mode = "partial"
    lw.fake.partial_qty = D("100")
    lw.sync("2026-07-01 09:05")
    assert lw.stages()["result"] == "quiet"  # PARTIAL_FILLED in the OPEN list: it still trades
    row = live_repo.broker_orders_of(lw.conn, "live")[0]
    assert (row.state, row.status, row.filled_qty) == ("sent", "PARTIAL_FILLED", D("100"))
    lw.fake.close_partial(canceled_at=canceled_at)  # 15:30: the rest lapses
    lw.sync("2026-07-01 16:05")
    row = live_repo.broker_orders_of(lw.conn, "live")[0]
    assert (row.state, row.status, row.filled_qty) == ("done", "PARTIAL_FILLED", D("100"))
    assert row.cancel_state is None  # nothing left to cancel: no request, no retry every tick
    assert lw.stages()["result"] == "done"
    fill = repo.fill_of_order(lw.conn, row.order_id)
    assert fill is not None and (fill.qty, fill.gross) == (100, D("3216000"))  # noqa: PT018
    assert repo.get_plan(lw.conn, repo.get_order(lw.conn, row.order_id).plan_id).status == "done"
    assert lw.reconcile()["result"] in ("match", "quiet")
    assert lw.status().reconcile_state == "match"
    assert lw.state().qty_of(KR) == lw.fake.holdings["069500"].qty == 100
    assert live.cancel_pending(lw.conn) == []
    assert verify_ledger(lw.conn, "live") == []
    # The next morning plans the cash that did not buy.
    lw.sync("2026-07-02 08:29")
    assert lw.check("2026-07-02 08:30")["result"] == "rebalance"


def test_a_partial_fill_in_the_open_list_is_not_over(lw: Live) -> None:
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    lw.check("2026-07-01 08:30")
    lw.fake.fill_mode = "partial"
    lw.fake.partial_qty = D("100")
    lw.sync("2026-07-01 09:05")
    lw.sync("2026-07-01 12:00")
    row = live_repo.broker_orders_of(lw.conn, "live")[0]
    assert (row.state, row.cancel_state) == ("sent", None)
    assert lw.reconcile()["result"] == "quiet"  # an open order keeps the account busy
    assert lw.status().reconcile_state == "busy"


def test_a_cancel_of_a_partial_fill_that_closed_meanwhile_finishes(lw: Live) -> None:
    """Live off while a partly filled order trades: the cancel request meets an order that has
    left the OPEN list (409 already-canceled). It is over: the cancel is done (it used to be
    asked again every tick and keep live from being turned on again), the fill is booked."""
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    lw.check("2026-07-01 08:30")
    lw.fake.fill_mode = "partial"
    lw.fake.partial_qty = D("100")
    lw.sync("2026-07-01 09:05")
    off = lw.turn_off("2026-07-01 10:00")
    [order_id] = off.cancel_requested
    lw.fake.close_partial()
    lw.sync("2026-07-01 10:05")
    row = live_repo.get_broker_order(lw.conn, order_id)
    assert row is not None and (row.state, row.cancel_state) == ("done", "done")  # noqa: PT018
    assert live.cancel_pending(lw.conn) == [] and live.cancel_failed(lw.conn) == []  # noqa: PT018
    result = lw.reconcile()
    assert {"late_fill": order_id, "qty": 100} in result["booked"]
    assert lw.state().qty_of(KR) == 100
    assert verify_ledger(lw.conn, "live") == []
