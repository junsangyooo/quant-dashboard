"""The live money path after the audit of 2026-10-13: each finding as the auditor found it, now
asserting the right behavior. Against the fake Toss (tests/autotrade/live_world.py).

1. Money that came in and an app buy it paid for, in one look at the account.
2. Live turned on in the day runs no check before the next weekday's 08:30.
3. A partly filled order that ends in the CLOSED list with PARTIAL_FILLED.
4. An order two of the account's orders could be: settled with the owner's pick.
5. The closed orders the reconciliation reads start at its last match, not its last attempt.
6. A one-share top-up the send's limit price cannot pay.
7. A conversion caps the cash waiting for a withdrawal; a live wait holds its own money only.
8. A deposit made while a dividend is due stays a deposit.
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
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency
from autotrade.engine import live
from autotrade.engine.common import new_money_waiting
from autotrade.engine.rebuild import verify_ledger
from autotrade.jobs.tasks import adopt_job
from autotrade.market.service import prefetch_dividends

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


# ── 1. money in and an app buy in one look ───────────────────────────────────────────────


def test_a_deposit_that_paid_for_an_app_buy_is_booked_before_it(lw: Live) -> None:
    invested(lw)
    lw.at("2026-07-01 10:01")
    lw.fake.deposit("KRW", D("5000000"))
    lw.fake.app_trade("005930", "BUY", D("70"), D("70000"), commission=D("735"))
    lw.sync("2026-07-01 10:05")
    result = lw.reconcile()
    assert result["result"] == "match", result
    # The deposit comes first, dated the fill's time (it paid for it); the buy outside the rules
    # takes its money out of the ledger.
    assert events(lw, "deposit", "withdrawal") == [
        ("deposit", D("5000000"), KRW, "unexplained-in"),
        ("withdrawal", D("4900735"), KRW, "outside-buy"),
    ]
    deposit = repo.events_of_ledger(lw.conn, "live", ["deposit"])[0]
    assert (deposit.occurred_at, deposit.event_date) == (kst("2026-07-01 10:01"), date(2026, 7, 1))
    assert lw.state().cash_of(KRW) == lw.fake.cash["KRW"] == D("128170")
    assert verify_ledger(lw.conn, "live") == []  # the rebuild takes the same steps
    assert lw.status().reconcile_state == "match"
    # D48: the owner's money of the day, held back from today's checks and sends.
    assert new_money_waiting(lw.conn, "live", lw.now()) == {KRW: D("5000000")}


def test_dollars_converted_to_pay_for_an_app_buy_of_the_us_etf(lw: Live) -> None:
    invested(lw)
    lw.fake.deposit("KRW", D("2000000"))
    lw.sync("2026-07-01 22:00")
    assert lw.reconcile()["result"] == "match"
    lw.at("2026-07-01 23:31")
    lw.fake.convert(D("1392000"), D("999.80"))  # the owner converts in the app ...
    lw.fake.app_trade("SPYM", "BUY", D("15"), D("66.00"), market="US", commission=D("0.99"))
    lw.sync("2026-07-01 23:35")  # ... and buys the rule's US ETF with it before the tick looks
    result = lw.reconcile()
    assert result["result"] == "match", result
    assert [b.get("conversion") for b in result["booked"] if "conversion" in b] == ["krw_to_usd"]
    state = lw.state()
    assert (state.qty_of("US:SPYM"), state.cash_of(USD)) == (15, D("8.81"))
    assert state.cash_of(KRW) == lw.fake.cash["KRW"] == D("636905")
    # The dollars came in before the buy they paid for (its fill time); the won left when the
    # account showed it.
    dollars = next(
        e for e in repo.events_of_ledger(lw.conn, "live", ["deposit"]) if e.currency is USD
    )
    assert dollars.occurred_at == kst("2026-07-01 23:31")
    assert verify_ledger(lw.conn, "live") == []


def test_money_in_is_dated_before_a_late_fill_of_ours_it_paid_for(lw: Live) -> None:
    """Our 09:05 order is still open when the owner deposits 8,000,000 won (09:58) and buys
    outside the rules in the app (09:59); ours fills at 10:05 and is booked late, in this same
    pass. Followed in time order, the cash runs short at our fill: the deposit is dated just
    before it, and the rebuild (time order) agrees with the ledger."""
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    lw.fake.fill_mode = "open"
    lw.sync("2026-07-01 09:05")
    lw.at("2026-07-01 09:58")
    lw.fake.deposit("KRW", D("8000000"))
    lw.at("2026-07-01 09:59")
    lw.fake.app_trade("005930", "BUY", D("100"), D("70000"), commission=D("1050"))
    lw.at("2026-07-01 10:05")
    lw.fake.fill_open(lw.fake.ours()[0].order_id, price=D("32000"))
    lw.sync("2026-07-01 10:10")
    result = lw.reconcile()
    assert result["result"] == "match", result
    assert result["booked"][0]["late_fill"] == repo.orders_of_ledger(lw.conn, "live")[0].order_id
    deposit = repo.events_of_ledger(lw.conn, "live", ["deposit"])[0]
    assert (deposit.amount, deposit.occurred_at) == (D("8000000"), kst("2026-07-01 10:05"))
    assert lw.state().cash_of(KRW) == lw.fake.cash["KRW"]
    assert verify_ledger(lw.conn, "live") == []


def test_an_app_buy_nothing_paid_for_is_still_a_mismatch(lw: Live) -> None:
    invested(lw)
    lw.at("2026-07-01 10:01")
    lw.fake.app_trade("005930", "BUY", D("70"), D("70000"), commission=D("735"))
    lw.sync("2026-07-01 10:05")
    result = lw.reconcile()
    assert (result["result"], result["reason"]) == ("mismatch", "cash")
    assert events(lw, "deposit", "withdrawal") == []  # nothing written


# ── 2. live turned on in the day ─────────────────────────────────────────────────────────


def test_live_turned_on_at_two_waits_for_the_next_morning(lw: Live, world: World) -> None:
    """Tuesday 14:00 (10,000,000 won only): no 'missed-check' plan minutes later. The first
    check is Wednesday 08:30, the one the preview showed."""
    world.rate(kst("2026-06-30 13:55"), "1392.0")
    data = lw.turn_on("2026-06-30 14:00")
    assert data.first_check == kst("2026-07-01 08:30")
    assert set(data.due.values()) == {kst("2026-07-01 09:05")}
    assert live.first_live_check(lw.conn, lw.cfg) == kst("2026-07-01 08:30")
    for t in ("2026-06-30 14:05", "2026-06-30 14:10", "2026-06-30 15:25"):
        lines = lw.tick(t)
        assert not [line for line in lines if line["task"] in ("check", "retry")], lines
    assert lw.fake.ours() == []
    assert repo.plans_of_ledger(lw.conn, "live") == []
    assert lw.check("2026-06-30 15:00")["result"] == "not-yet"  # by hand, too
    # Wednesday: the first check plans, and 09:05 sends.
    lines = lw.tick("2026-07-01 08:30")
    assert [(x["task"], x["result"]) for x in lines if x["task"] == "check"] == [
        ("check", "rebalance")
    ]
    lw.tick("2026-07-01 09:05")
    assert [o.symbol for o in lw.fake.ours()] == ["069500"]


def test_live_turned_on_before_the_check_time_plans_that_morning(lw: Live) -> None:
    lw.turn_on("2026-06-30 21:00")
    assert live.first_live_check(lw.conn, lw.cfg) == kst("2026-07-01 08:30")
    lw.at("2026-07-01 08:00")
    lw.turn_off("2026-07-01 08:05")
    data = lw.turn_on("2026-07-01 08:10")  # off and on again before 08:30: today's check
    assert data.first_check == kst("2026-07-01 08:30")
    assert live.first_live_check(lw.conn, lw.cfg) == kst("2026-07-01 08:30")
    lines = lw.tick("2026-07-01 08:30")
    assert ("check", "rebalance") in [(x["task"], x.get("result")) for x in lines]


def test_off_and_on_again_after_the_check_waits_for_the_next_morning(lw: Live) -> None:
    invested(lw)
    lw.turn_off("2026-07-01 10:00")
    lw.sync("2026-07-01 10:05")
    lw.turn_on("2026-07-01 10:10")
    assert live.first_live_check(lw.conn, lw.cfg) == kst("2026-07-02 08:30")
    lines = lw.tick("2026-07-01 10:15")  # today's check ran before: no retry after it either
    assert not [x for x in lines if x["task"] in ("check", "retry")], lines


def test_a_preview_shown_before_the_check_time_is_changed_after_it(lw: Live) -> None:
    """The preview binds its first check: shown at 08:25 (first orders today 09:05), turned on
    at 08:35 (they would go tomorrow), it is another preview (인계 13: 409 preview-changed)."""
    lw.sync("2026-07-01 08:20")
    shown = lw.preview()
    lw.at("2026-07-01 08:25")
    again = lw.preview()
    assert (shown.first_check, again.first_check) == (kst("2026-07-01 08:30"),) * 2
    with transaction(lw.conn):
        live.store_preview(lw.conn, shown, {})
    stored = live_repo.get_preview(lw.conn, shown.hash)
    assert not live.preview_changed(stored, again)
    lw.sync("2026-07-01 08:35")
    later = lw.preview()
    assert later.first_check == kst("2026-07-02 08:30")
    assert later.signature == shown.signature  # the same orders, a day later
    assert live.preview_changed(stored, later)


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


# ── 4. an order two of the account's orders could be ─────────────────────────────────────


def ambiguous(lw: Live) -> int:
    """09:05: our intent is committed, the request is lost, and two orders of the owner's with
    the same symbol, side, quantity and price are in the account. At 09:20, past the resend
    window, the search finds both: our order waits for a person. Returns its id."""
    from autotrade.broker.toss import client_order_id
    from autotrade.broker.toss_api import OrderRequest

    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    order = repo.orders_of_ledger(lw.conn, "live")[0]
    lw.fake.fill_mode = "open"
    request = OrderRequest(
        client_order_id(order.idem_key), "069500", "BUY", 156, D("32160"), Currency.KRW
    )
    lw.at("2026-07-01 09:05")
    with transaction(lw.conn):
        live_repo.insert_intent(
            lw.conn, order_id=order.order_id, ledger_id="live", request=request, at=lw.now()
        )
    body = {**request.body(), "clientOrderId": "app-1"}
    lw.fake._create(body)
    lw.fake._create({**body, "clientOrderId": "app-2"})
    lw.sync("2026-07-01 09:20")
    row = live_repo.get_broker_order(lw.conn, order.order_id)
    assert row is not None and (row.state, row.error_code) == ("unknown", "ambiguous")  # noqa: PT018
    assert [c["order"]["order_id"] for c in row.candidates] == ["ord-0001", "ord-0002"]
    return order.order_id


def settle(lw: Live, order_id: int, pick: str | None) -> dict[str, object]:
    from autotrade.jobs.tasks import resolve_job

    return resolve_job(
        lw.ctx, "live", f"broker-mismatch:order:{order_id}", lw.now(), note="앱 확인", pick=pick
    )


def test_an_ambiguous_order_none_of_whose_candidates_is_ours(lw: Live) -> None:
    from autotrade.engine.todos import open_todos

    order_id = ambiguous(lw)
    lw.fake.expire_open()  # the session ends: both of the owner's orders lapse unfilled
    lw.sync("2026-07-01 16:30")
    assert lw.reconcile()["result"] == "quiet"
    assert lw.status().reconcile_state == "busy"  # it keeps the account busy until settled
    [todo] = open_todos(lw.conn, "live")
    assert todo.todo_id == f"broker-mismatch:order:{order_id}"
    assert [c["id"] for c in todo.facts["candidates"]] == ["ord-0001", "ord-0002"]
    # A pick is needed, and it must be one of the candidates (or none).
    assert settle(lw, order_id, None)["result"] == "bad-pick"
    assert settle(lw, order_id, "ord-9999")["result"] == "bad-pick"
    done = settle(lw, order_id, "none")
    assert (done["result"], done["settled"]) == ("resolved", "none")
    assert settle(lw, order_id, "none")["result"] == "already-resolved"
    row = live_repo.get_broker_order(lw.conn, order_id)
    assert row is not None and (row.state, row.error_code) == ("not-sent", "lost")  # noqa: PT018
    assert live.unknown_orders(lw.conn) == [] and open_todos(lw.conn, "live") == []  # noqa: PT018
    # Our order never reached Toss: its stage fails and goes again the next trading day.
    assert lw.stages()["result"] == "failed"
    assert [o.attempt for o in repo.orders_of_ledger(lw.conn, "live")] == [1, 2]
    assert lw.reconcile()["result"] in ("match", "quiet")
    assert lw.status().reconcile_state == "match"
    assert verify_ledger(lw.conn, "live") == []


def test_an_ambiguous_order_whose_candidate_is_ours(lw: Live) -> None:
    order_id = ambiguous(lw)
    lw.fake.fill_open("ord-0002", price=D("32000"))  # the one that is ours fills
    lw.fake.expire_open()
    lw.sync("2026-07-01 16:30")
    assert settle(lw, order_id, "ord-0002")["settled"] == "ord-0002"
    row = live_repo.get_broker_order(lw.conn, order_id)
    assert row is not None and (row.state, row.broker_order_id) == ("sent", "ord-0002")  # noqa: PT018
    lw.sync("2026-07-01 16:35")  # the next sync reads it: filled
    assert lw.stages()["result"] == "done"
    fill = repo.fill_of_order(lw.conn, order_id)
    assert fill is not None and (fill.qty, fill.gross) == (156, D("4992000"))  # noqa: PT018
    assert lw.reconcile()["result"] in ("match", "quiet")
    assert lw.status().reconcile_state == "match"
    assert lw.state().qty_of(KR) == 156
    assert verify_ledger(lw.conn, "live") == []


def test_turning_live_off_with_an_ambiguous_order_settles_the_cancel_too(lw: Live) -> None:
    from autotrade.api.views import mode as mode_view
    from autotrade.api.views.context import LedgerContext

    order_id = ambiguous(lw)
    lw.fake.expire_open()  # 15:30: the owner's two orders lapse
    off = lw.turn_off("2026-07-01 16:40")
    assert off.cancel_requested == [order_id]
    for t in ("2026-07-01 16:45", "2026-07-02 08:30"):
        lw.sync(t)
    assert [r.order_id for r in live.cancel_pending(lw.conn)] == [order_id]  # nothing to cancel yet
    settle(lw, order_id, "none")
    assert live.cancel_pending(lw.conn) == []
    assert repo.get_order(lw.conn, order_id).status == "cancelled"  # its plan was closed
    lw.sync("2026-07-02 08:35")
    lw.market_data()
    found = mode_view.checks(LedgerContext(lw.conn, lw.cfg, "paper", lw.now()), lw.now())
    assert found.can_turn_on == {"ok": True}


def test_the_owners_pick_through_the_cli(lw: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    import json

    from autotrade.jobs import cli

    order_id = ambiguous(lw)
    lw.fake.expire_open()
    lines: list[str] = []
    env = {"AUTOTRADE_SECRETS_ENV": str(lw.cfg.secrets_env)}
    base = ["--db", str(lw.cfg.db_path), "--at", "2026-07-01T16:30", "--ledger", "live"]
    code = cli.main(["todos", *base], env=env, out=lines.append)
    [todo] = json.loads(lines[-1])["todos"]
    assert (code, todo["id"], [c["id"] for c in todo["candidates"]]) == (
        0,
        f"broker-mismatch:order:{order_id}",
        ["ord-0001", "ord-0002"],
    )
    code = cli.main(["resolve", todo["id"], *base], env=env, out=lines.append)
    assert (code, json.loads(lines[-1])["result"]) == (1, "bad-pick")
    code = cli.main(
        ["resolve", todo["id"], "--pick", "none", "--note", "앱 확인", *base],
        env=env,
        out=lines.append,
    )
    assert (code, json.loads(lines[-1])["result"]) == (0, "resolved")
    with pytest.raises(SystemExit):
        cli.main(["todos", "--pick", "none", *base], env=env, out=lines.append)


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


@pytest.mark.parametrize(
    ("symbol", "price"),
    [("069500", D("32000")), ("005930", D("70000"))],  # a rule instrument, one outside the rules
)
def test_the_fills_an_adoption_took_in_are_not_booked_again(
    lw: Live, symbol: str, price: Decimal
) -> None:
    """adopt-broker takes the account as it was read, the owner's app fills included, while the
    closed orders are still read from the last match: those fills must not come back as new ones
    (the ledger would never match again, and a second adoption finds nothing to adopt)."""
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-06-30 21:30")
    assert lw.reconcile()["result"] == "match"
    lw.at("2026-07-01 10:00")
    lw.fake.hold("069500", D("5"), D("32000"), name="KODEX 200")  # moved in from another broker
    lw.sync("2026-07-01 10:05")
    assert lw.reconcile()["result"] == "mismatch"
    lw.at("2026-07-01 11:00")
    lw.fake.app_trade(symbol, "BUY", D("3"), price, commission=D("5"))
    lw.sync("2026-07-01 11:05")
    assert lw.reconcile()["result"] == "mismatch"
    lw.sync("2026-07-03 09:00")
    assert adopt_job(lw.ctx, lw.now(), note="checked in the app")["result"] == "adopted"
    held = lw.state().qty_of("KR:069500")
    cash = lw.state().cash_of(KRW)
    assert cash == lw.fake.cash["KRW"]
    for t in ("2026-07-03 09:05", "2026-07-06 09:00"):
        lw.sync(t)
        lw.reconcile(t)
        assert lw.status().reconcile_state == "match"
    assert (lw.state().qty_of("KR:069500"), lw.state().cash_of(KRW)) == (held, cash)
    # Only the adoption's own money (outside the rules the buy came back as money out plus as
    # much 'unexplained' money in).
    booked = repo.events_of_ledger(lw.conn, "live", ["deposit", "withdrawal"])
    assert [e.payload.get("source") for e in booked] == ["adopt-broker"]
    assert held == (8 if symbol == "069500" else 5)


@pytest.mark.parametrize("extra", [D("0"), D("20000000")])  # and with money it never booked
def test_an_adoption_books_our_late_fill_first(lw: Live, extra: Decimal) -> None:
    """Our buy filled after live was turned off; before the reconciliation booked it, shares
    moved in from another broker (a mismatch, so that reconciliation rolled back with the fill).
    The adoption books our fill as the trade it is, then takes the rest of the account: the next
    reconciliations match and the fill is booked once (it used to come back on top of the
    adopted numbers: 625 shares against 315, or a cash error that undid the adoption)."""
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    lw.fake.fill_mode = "open"
    lw.sync("2026-07-01 09:05")  # our buy is sent and stays open
    ours = lw.fake.ours()[0].order_id
    lw.turn_off("2026-07-01 09:50")  # the plan closes, a cancel is requested
    lw.at("2026-07-01 09:55")
    lw.fake.fill_open(ours, price=D("32000"))  # it fills before the cancel reaches Toss
    lw.at("2026-07-01 10:00")
    held = lw.fake.holdings["069500"].qty
    lw.fake.hold("069500", held + D("5"), D("32000"), name="KODEX 200")
    if extra:
        lw.fake.deposit("KRW", extra)
    lw.sync("2026-07-01 10:05")
    assert lw.reconcile()["result"] == "mismatch"
    lw.sync("2026-07-03 09:00")
    adopted = adopt_job(lw.ctx, lw.now(), note="checked in the app")
    assert adopted["result"] == "adopted"
    assert [f["qty"] for f in adopted["lateFills"]] == [310]
    assert [(c["from"], c["to"]) for c in adopted["positions"]] == [(310, 315)]
    for t in ("2026-07-03 09:05", "2026-07-06 09:00"):
        lw.sync(t)
        lw.reconcile(t)
        assert lw.status().reconcile_state == "match"
    assert lw.state().qty_of("KR:069500") == 315
    assert len(repo.fills_of_ledger(lw.conn, "live")) == 1


# ── 6. a one-share top-up ────────────────────────────────────────────────────────────────


def top_up(lw: Live, cash: str) -> None:
    """After the first buy (28,905 won left), the owner adds money so the cash is `cash`."""
    invested(lw)
    lw.at("2026-07-01 10:00")
    lw.fake.deposit("KRW", D(cash) - lw.state().cash_of(KRW))
    lw.sync("2026-07-01 10:05")
    lw.reconcile()
    assert lw.state().cash_of(KRW) == D(cash)


def test_a_share_the_send_could_not_pay_is_never_planned(lw: Live) -> None:
    """32,100 won buys one share at the 32,050 close but not at the send's limit (32,210 on the
    tick, plus the fee: 32,214.8): the plan sizes buys as the send pays, so nothing is planned
    and the cash waits below one share. It used to be planned, refused twice ('no-cash') and
    become a to-do that blocked every later plan."""
    top_up(lw, "32100")
    lw.fake.prices["069500"] = D("32050")  # a flat market
    lw.sync("2026-07-02 08:29")
    report = lw.check("2026-07-02 08:30")
    assert report["result"] == "in-range"
    assert repo.open_plans(lw.conn, "live") == []
    parts = {(p.currency, p.purpose.value): p.amount for p in repo.cash_parts(lw.conn, "live")}
    assert parts == {(KRW, "sub_share"): D("32100")}
    # More money: the next check plans with all of it.
    lw.fake.deposit("KRW", D("5000000"))
    lw.sync("2026-07-02 12:00")
    lw.reconcile()
    lw.sync("2026-07-03 08:29")
    assert lw.check("2026-07-03 08:30")["result"] == "rebalance"


def test_a_buy_the_price_outran_ends_with_nothing_bought(lw: Live) -> None:
    """32,300 won pays one share at the 32,050 close's limit; at 09:05 the price is 32,400 and
    the limit (32,560) leaves the cash short: the order ends with nothing bought, its stage
    and plan complete, nothing waits for a person, and the next check plans again."""
    from autotrade.engine.todos import open_todos

    top_up(lw, "32300")
    lw.sync("2026-07-02 08:29")
    report = lw.check("2026-07-02 08:30")
    assert report["details"]["planned"]["buys"] == [("KR:069500", 1)]
    lw.fake.prices["069500"] = D("32400")
    lw.sync("2026-07-02 09:05")
    order = repo.orders_of_ledger(lw.conn, "live")[-1]
    row = live_repo.get_broker_order(lw.conn, order.order_id)
    assert row is not None and (row.state, row.error_code) == ("not-sent", "nothing-to-buy")  # noqa: PT018
    assert lw.stages()["result"] == "done"
    order = repo.get_order(lw.conn, order.order_id)
    assert (order.status, order.manual, order.retry_at) == ("cancelled", False, None)
    assert repo.get_plan(lw.conn, order.plan_id).status == "done"
    assert open_todos(lw.conn, "live") == []
    assert len(lw.fake.ours()) == 1  # only the first day's order ever reached Toss
    assert lw.state().cash_of(KRW) == D("32300")  # it waits
    # The next morning (a flat 32,050 again) plans it again.
    lw.fake.prices["069500"] = D("32050")
    lw.sync("2026-07-03 08:29")
    assert lw.check("2026-07-03 08:30")["result"] == "rebalance"


def test_the_plan_screens_leave_out_an_order_that_bought_nothing(lw: Live) -> None:
    from autotrade.api.views.orders import plan_stages

    top_up(lw, "32300")
    lw.sync("2026-07-02 08:29")
    plan_id = lw.check("2026-07-02 08:30")["plan_id"]
    lw.fake.prices["069500"] = D("32400")
    lw.sync("2026-07-02 09:05")
    lw.stages()
    instruments = live.rule_instruments(lw.conn)
    assert plan_stages(lw.conn, plan_id, instruments, "live") == []  # no '직접 할 일' on screen
    # Nor a rebalance that bought nothing: no history row, no marker, no rebalance day (it could
    # come back each morning the price opens above the plan's).
    from autotrade.api.views import history
    from autotrade.api.views.context import LedgerContext
    from autotrade.api.views.series import event_markers

    event = repo.event_of_plan(lw.conn, plan_id)
    assert event is not None and event.payload.get("untraded") is True  # noqa: PT018
    ctx = LedgerContext(lw.conn, lw.cfg, "live", lw.at("2026-07-02 16:10"))
    assert [e.kind for e in ctx.events if e.event_date == date(2026, 7, 2)] == []
    assert all(m["date"] != "2026-07-02" for m in event_markers(ctx))
    assert history.DayData(ctx).calendar_state(date(2026, 7, 2)) == "normal"


def test_a_first_plan_that_bought_nothing_is_no_rebalance_day(lw: Live) -> None:
    """The live ledger's first plan hangs on its start event (engine/check.py): when it buys
    nothing, the start stays listed and the day is no rebalance day on the calendar either."""
    from autotrade.api.views import history
    from autotrade.api.views.context import LedgerContext

    lw.fake.cash["KRW"] = D("32300")
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    plan_id = lw.check("2026-07-01 08:30")["plan_id"]
    lw.fake.prices["069500"] = D("32400")
    lw.sync("2026-07-01 09:05")
    assert lw.stages()["result"] == "done"
    event = repo.event_of_plan(lw.conn, plan_id)
    assert event is not None and (event.kind, event.payload.get("untraded")) == ("start", True)  # noqa: PT018
    ctx = LedgerContext(lw.conn, lw.cfg, "live", lw.at("2026-07-01 16:10"))
    assert "start" in [e.kind for e in ctx.listed_events]
    assert history.DayData(ctx).calendar_state(date(2026, 7, 1)) == "normal"


# ── 7. withdraw waits: a conversion caps them, a live wait holds its own money ───────────


def sold_in_the_app(lw: Live, cash: str = "10000000") -> None:
    """The account: 20 KODEX 200 and `cash` won. Wednesday 08:10 the owner sells 14 in the app
    to withdraw 447,933 won on settlement (7/2 + 2 trading days = 7/6)."""
    lw.fake.cash["KRW"] = D(cash)
    lw.fake.hold("069500", D("20"), D("30000"), name="KODEX 200")
    lw.turn_on("2026-06-30 21:00")
    lw.at("2026-07-01 08:10")
    lw.fake.app_trade(
        "069500", "SELL", D("14"), D("32000"), commission=D("67"), settlement=date(2026, 7, 2)
    )
    lw.sync("2026-07-01 08:20")
    assert lw.reconcile()["result"] == "match"
    assert [(w.amount, w.until) for w in repo.withdraw_waits(lw.conn, "live")] == [
        (D("447933"), date(2026, 7, 6))
    ]


def test_converting_money_that_was_already_there_keeps_the_sale_waiting(lw: Live) -> None:
    sold_in_the_app(lw)
    lw.at("2026-07-01 11:00")
    lw.fake.convert(D("500000"), D("359.19"))  # 500,000 of the 10,447,933 won, not the proceeds
    lw.sync("2026-07-01 11:05")
    assert lw.reconcile()["booked"][0]["conversion"] == "krw_to_usd"
    # 9,947,933 won are left beyond the day's new money (none): the wait stays whole.
    assert [w.amount for w in repo.withdraw_waits(lw.conn, "live")] == [D("447933")]
    # Thursday: the wait holds its own money only; the rest is planned, the proceeds are not:
    # floor(9,500,000 / (32,210 x 1.00015)) = 294, and the dollars floor(359.19 / (66.53 x
    # 1.001)) = 5.
    lw.sync("2026-07-02 08:29")
    report = lw.check("2026-07-02 08:30")
    assert report["result"] == "rebalance"
    assert report["details"]["withdraw_held"] == {"KRW": D("447933")}
    assert report["details"]["planned"]["buys"] == [("KR:069500", 294), ("US:SPYM", 5)]
    lw.sync("2026-07-02 09:05")
    lw.stages()
    assert lw.state().cash_of(KRW) >= D("447933")  # the proceeds were not spent
    assert [w.amount for w in repo.withdraw_waits(lw.conn, "live")] == [D("447933")]


def test_converting_the_proceeds_releases_what_was_converted(lw: Live) -> None:
    sold_in_the_app(lw, cash="0")  # the proceeds are the only won
    lw.fake.convert(D("200000"), D("143.67"))
    lw.sync("2026-07-01 08:25")
    lw.reconcile()
    # 247,933 won are left: the wait is capped at them.
    assert [w.amount for w in repo.withdraw_waits(lw.conn, "live")] == [D("247933")]
    lw.fake.convert(D("247933"), D("178.11"))
    lw.sync("2026-07-01 08:28")
    lw.reconcile()
    assert repo.withdraw_waits(lw.conn, "live") == []


def test_converting_the_days_deposit_keeps_the_sale_waiting(lw: Live) -> None:
    sold_in_the_app(lw, cash="0")
    lw.fake.deposit("KRW", D("1000000"))
    lw.sync("2026-07-01 08:25")
    lw.reconcile()
    lw.fake.convert(D("1000000"), D("718.39"))  # he converts what he has just deposited
    lw.sync("2026-07-01 08:28")
    lw.reconcile()
    assert [w.amount for w in repo.withdraw_waits(lw.conn, "live")] == [D("447933")]


def test_a_live_wait_shows_on_the_money_not_as_stopped_orders(lw: Live) -> None:
    from autotrade.api.views import plan as plan_view
    from autotrade.api.views.context import LedgerContext
    from autotrade.domain.status import RuleStatus

    sold_in_the_app(lw)
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"  # not 'withdraw-wait'
    ctx = LedgerContext(lw.conn, lw.cfg, "live", lw.at("2026-07-01 08:31"))
    assert ctx.status is not RuleStatus.WITHDRAW_WAIT
    assert ctx.next_action["kind"] != "withdraw-wait"
    chips = [r.chip for r in ctx.composition.rows if r.chip]
    assert {"kind": "withdraw-wait", "until": "2026-07-06"} in chips  # the money and its date
    items = plan_view.schedule(ctx)["items"]
    assert "withdraw-wait" not in [i["kind"] for i in items]  # no '주문 0건' line


# ── 8. a deposit made while a dividend is due ────────────────────────────────────────────


def dividend_due(lw: Live, world: World) -> None:
    """100 KODEX 200 held before the 7/1 ex-date of a 160-won distribution paid 7/3: gross
    16,000, 15.4% tax 2,464 estimated, net 13,536."""
    lw.fake.hold("069500", D("100"), D("30000"), name="KODEX 200")
    lw.turn_on("2026-06-30 21:00")
    world.dividend(KR, "2026-07-01", "160", pay_date="2026-07-03")
    prefetch_dividends(
        lw.conn,
        lw.cfg,
        lw.ctx.sources,
        [repo.get_instrument(lw.conn, KR)],
        date(2026, 6, 1),
        date(2026, 7, 3),
        lw.at("2026-07-02 08:00"),
    )


def test_a_deposit_while_a_dividend_is_due_stays_a_deposit(lw: Live, world: World) -> None:
    dividend_due(lw, world)
    lw.at("2026-07-02 10:00")
    lw.fake.deposit("KRW", D("1000000"))  # the owner adds money
    lw.sync("2026-07-02 10:05")
    lw.reconcile()
    lw.at("2026-07-03 08:00")
    lw.fake.deposit("KRW", D("13536"))  # the dividend, net of tax
    lw.sync("2026-07-03 08:05")
    lw.reconcile()
    assert [(e.kind, e.amount) for e in repo.events_of_ledger(lw.conn, "live", ["deposit"])] == [
        ("deposit", D("1000000"))
    ]
    assert [(e.kind, e.amount) for e in repo.events_of_ledger(lw.conn, "live", ["dividend"])] == [
        ("dividend", D("13536"))
    ]
    state = lw.state()
    assert state.income_krw == D("13536")
    assert verify_ledger(lw.conn, "live") == []


@pytest.mark.parametrize(
    ("paid", "kind"),
    [
        ("13540", "dividend"),  # the broker cuts each part of the tax to 10 won: 2,240 + 220
        ("13515", "dividend"),  # within the 21-won rounding of the tax
        ("13514", "deposit"),
        ("13558", "deposit"),
        ("16000", "deposit"),  # the gross is no longer taken for the dividend
    ],
)
def test_a_dividend_is_its_net_within_the_rounding_of_the_tax(
    lw: Live, world: World, paid: str, kind: str
) -> None:
    dividend_due(lw, world)
    lw.at("2026-07-03 08:00")
    lw.fake.deposit("KRW", D(paid))
    lw.sync("2026-07-03 08:05")
    lw.reconcile()
    rows = repo.events_of_ledger(lw.conn, "live", ["deposit", "dividend"])
    assert [(e.kind, e.amount) for e in rows] == [(kind, D(paid))]


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
