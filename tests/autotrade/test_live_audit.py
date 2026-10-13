"""The live money path after the audit of 2026-10-13: each finding as the auditor found it, now
asserting the right behavior. Against the fake Toss (tests/autotrade/live_world.py).

3. A partly filled order that ends in the CLOSED list with PARTIAL_FILLED.
5. The closed orders the reconciliation reads start at its last match, not its last attempt.
9. The commission rate a buy is sized with is the one in force.
10. An armed 조건주문 on the account blocks turning live on.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from autotrade.db import live_repo, repo
from autotrade.domain.instruments import Currency
from autotrade.engine import live
from autotrade.engine.common import new_money_waiting
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


# ── 5. the closed orders start at the last match ─────────────────────────────────────────


def test_an_app_sale_during_a_long_busy_spell_is_still_an_app_sale(
    lw: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Days without a usable look at the account (the first key out of cron) must not let the
    owner's app fills drop out of the closed orders the next look reads: a sale's proceeds would
    come back as new money, invested from the next weekday with no wait for the withdrawal."""
    lw.fake.hold("005930", D("10"), D("70000"), name="Samsung")  # outside the rules
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-06-30 21:05")
    assert lw.reconcile()["result"] in ("match", "quiet")
    matched = lw.status().matched_at
    assert matched == kst("2026-06-30 21:05")
    monkeypatch.delenv("AUTOTRADE_LIVE_ORDERS")  # the owner takes key 1 out of cron
    lw.at("2026-07-01 10:00")
    lw.fake.app_trade(
        "005930",
        "SELL",
        D("10"),
        D("71000"),
        commission=D("106"),
        tax=D("1420"),
        settlement=date(2026, 7, 3),
    )  # ... and sells the outside stock in the app, to withdraw it
    for t in ("2026-07-01 10:05", "2026-07-02 10:05", "2026-07-03 10:05"):
        lw.sync(t)
        assert lw.reconcile(t)["result"] == "quiet"
        status = lw.status()
        assert (status.reconcile_state, status.reconciled_at) == ("busy", kst(t))
        assert status.matched_at == matched  # a busy pass booked nothing: the window stays
    monkeypatch.setenv("AUTOTRADE_LIVE_ORDERS", "1")  # key 1 back
    lw.sync("2026-07-03 10:10")
    result = lw.reconcile()
    assert result["result"] == "match", result
    assert events(lw, "deposit") == [("deposit", D("708474"), KRW, "outside-sell")]
    waits = repo.withdraw_waits(lw.conn, "live")
    # Settlement 7/3 + 2 Korean trading days = 7/7: it waits for the withdrawal.
    assert [(w.amount, w.until) for w in waits] == [(D("708474"), date(2026, 7, 7))]
    assert new_money_waiting(lw.conn, "live", lw.now()) == {}  # sale proceeds are not new money
    assert lw.status().matched_at == kst("2026-07-03 10:10")


# ── 9. the commission in force ───────────────────────────────────────────────────────────


def test_the_sync_keeps_the_commission_in_force(lw: Live) -> None:
    lw.fake.commission_rows = [
        {"marketCountry": "KR", "commissionRate": "0.00015", "startDate": None, "endDate": None},
        {"marketCountry": "US", "commissionRate": "0.0025", "startDate": None, "endDate": None},
        {
            "marketCountry": "US",
            "commissionRate": "0.001",
            "startDate": None,
            "endDate": "2026-06-29",
        },  # an expired promotion, listed last
    ]
    lw.sync("2026-06-30 21:00")
    assert lw.status().commissions == {"KR": D("0.00015"), "US": D("0.0025")}


# ── 10. an armed 조건주문 ────────────────────────────────────────────────────────────────


def test_an_armed_conditional_order_blocks_turning_live_on(lw: Live) -> None:
    from autotrade.api.views import mode as mode_view
    from autotrade.api.views.context import LedgerContext
    from autotrade.api.views.live import todos

    cid = lw.fake.arm_conditional("069500", "SELL", D("10"))  # the old quant's stop
    lw.sync("2026-06-30 21:00")
    lw.market_data()
    assert [c["id"] for c in lw.status().conditional or []] == [cid]
    assert live.link_check(lw.conn, lw.cfg, lw.now()).cause == "conditional"
    found = mode_view.checks(LedgerContext(lw.conn, lw.cfg, "paper", lw.now()), lw.now())
    link = next(r for r in found.preflight if r["id"] == "toss-link")
    assert (link["ok"], link["facts"]) == (False, {"cause": "conditional"})
    assert found.can_turn_on == {"ok": False, "cause": "checks"}
    # The owner cancels it in the Toss app: the next look lets live on.
    lw.fake.conditional.clear()
    lw.sync("2026-06-30 21:05")
    assert lw.status().conditional == []
    assert live.link_check(lw.conn, lw.cfg, lw.now()).ok
    # Armed again while live: a red manual to-do; live orders go on (its fills are the owner's).
    lw.turn_on("2026-06-30 21:10")
    lw.fake.arm_conditional("005930", "BUY", D("1"))
    lw.sync("2026-06-30 21:15")
    [card] = [t for t in todos(lw.conn, lw.cfg, lw.now()) if t["kind"] == "toss-link"]
    assert (card["severity"], card["facts"], card["action"], card["effect"]) == (
        "red",
        {"cause": "conditional"},
        {"kind": "manual"},
        "other",
    )


def test_conditional_orders_that_cannot_be_read_keep_live_off_not_the_snapshot(lw: Live) -> None:
    lw.fake.fail_paths["/api/v1/conditional-orders"] = (500, "internal-error")
    report = lw.sync("2026-06-30 21:00")
    assert report["result"] == "unreachable"
    assert live_repo.latest_snapshot(lw.conn) is not None  # the account was still read
    assert live.link_check(lw.conn, lw.cfg, lw.now()).cause == "unreachable"
    del lw.fake.fail_paths["/api/v1/conditional-orders"]
    lw.sync("2026-06-30 21:05")
    assert live.link_check(lw.conn, lw.cfg, lw.now()).ok


def test_the_read_only_check_lists_conditional_orders(lw: Live) -> None:
    from autotrade.jobs.live_tasks import toss_check

    out = toss_check(lw.cfg, lw.conn, transport=lw.fake, today=date(2026, 6, 30))
    assert (out["openOrders"], out["conditionalOrders"]) == (0, 0)
    assert "conditional" not in out
    lw.fake.arm_conditional("SPYM", "SELL", D("3"), market="US", kind="OCO")
    out = toss_check(lw.cfg, lw.conn, transport=lw.fake, today=date(2026, 6, 30))
    assert out["conditionalOrders"] == 1
    assert out["conditional"] == [
        {"symbol": "SPYM", "market": "US", "type": "OCO", "status": "WATCHING"}
    ]
    writes = [c for c in lw.fake.calls if c[0] != "GET" and c[1] != "/oauth2/token"]
    assert writes == []  # reads only
