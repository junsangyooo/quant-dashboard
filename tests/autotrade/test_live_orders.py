"""Live orders through the fake Toss (PHASE3.md 2.1, 2.3): both keys, no duplicate order across
retries, crashes and lost answers, partial fills, refusals and order hours, the cash a buy may
use. Every order the fake receives is counted: 'no duplicate' means exactly one at the broker."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from autotrade.broker.base import Failed, FailureReason, TradeRequest, Waiting
from autotrade.broker.toss import (
    TossExecutor,
    client_order_id,
    limit_price,
    on_tick,
    permit_for,
    tick_size,
)
from autotrade.broker.toss_api import OrderRequest
from autotrade.db import live_repo, repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency, Kind, kr_etf, us_etf
from autotrade.domain.planner import Side
from autotrade.engine import live
from autotrade.engine.rebuild import verify_ledger
from autotrade.timeutil import KST

from .fakes import World
from .live_world import Live, make_live

D = Decimal


@pytest.fixture
def lw(tmp_path: Path, world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[Live]:
    monkeypatch.setenv("AUTOTRADE_LIVE_ORDERS", "1")
    yield from make_live(tmp_path, world)


def planned(lw: Live) -> dict[tuple[str, str], int]:
    """Live on the evening before, the 08:30 plan of the first day: order ids by (side, market)."""
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    return {(o.side, o.market): o.order_id for o in repo.orders_of_ledger(lw.conn, "live")}


def kr_rows(lw: Live) -> list[live_repo.BrokerOrderRow]:
    return [r for r in live_repo.broker_orders_of(lw.conn, "live") if r.request and r.request.symbol == "069500"]


# ── the two keys ─────────────────────────────────────────────────────────────────────────


def test_without_the_first_key_toss_is_never_called(
    tmp_path: Path, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    for env, key in ((False, True), (True, False)):
        if env:
            monkeypatch.setenv("AUTOTRADE_LIVE_ORDERS", "1")
        else:
            monkeypatch.delenv("AUTOTRADE_LIVE_ORDERS", raising=False)
        holder = make_live(tmp_path / f"{env}{key}", world, with_key=key)
        lw = next(holder)
        report = lw.sync("2026-07-01 09:05")
        assert report["result"] == "quiet"
        assert lw.fake.calls == []
        status = lw.status()
        assert (status.state, status.env_live) == ("off", False)
        check = live.link_check(lw.conn, lw.cfg, lw.now())
        assert (check.ok, check.cause) == (False, "env-off")
        holder.close()


def test_the_permit_needs_both_keys(lw: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    at = lw.at("2026-07-01 09:05")
    assert permit_for(lw.conn, lw.cfg, "live", at) is None  # the mode is paper
    assert permit_for(lw.conn, lw.cfg, "live", at, purpose="cancel") is not None
    assert permit_for(lw.conn, lw.cfg, "paper", at, purpose="cancel") is None
    with transaction(lw.conn):
        repo.set_setting(lw.conn, "mode", "live", at)
    assert permit_for(lw.conn, lw.cfg, "live", at) is not None
    monkeypatch.delenv("AUTOTRADE_LIVE_ORDERS")
    assert permit_for(lw.conn, lw.cfg, "live", at) is None
    assert permit_for(lw.conn, lw.cfg, "live", at, purpose="cancel") is None
    with pytest.raises(ValueError, match="purpose"):
        permit_for(lw.conn, lw.cfg, "live", at, purpose="other", env={"AUTOTRADE_LIVE_ORDERS": "1"})


def test_no_order_leaves_once_the_mode_is_paper(lw: Live) -> None:
    planned(lw)
    off = lw.turn_off("2026-07-01 09:00")
    assert off.changed and not off.cancel_requested
    assert len(off.cancelled) == 3  # nothing had left: cancelled in the database
    lw.sync("2026-07-01 09:05")
    assert lw.fake.ours() == []
    assert all(o.status == "cancelled" for o in repo.orders_of_ledger(lw.conn, "live"))
    events = [e.kind for e in repo.events_of_ledger(lw.conn, "live")]
    assert events[-1] == "live-off"
    assert lw.turn_off("2026-07-01 09:06").changed is False  # idempotent


def test_no_order_leaves_when_the_key_goes_away(lw: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    planned(lw)
    monkeypatch.delenv("AUTOTRADE_LIVE_ORDERS")
    assert lw.sync("2026-07-01 09:05")["result"] == "off"
    assert lw.fake.ours() == []
    todos = live.link_check(lw.conn, lw.cfg, lw.now())
    assert todos.cause == "env-off"


# ── no duplicate order ───────────────────────────────────────────────────────────────────


def test_running_twice_sends_once(lw: Live) -> None:
    planned(lw)
    lw.fake.fill_mode = "open"
    lw.sync("2026-07-01 09:05")
    lw.sync("2026-07-01 09:05")
    lw.sync("2026-07-01 09:07")
    assert len(lw.fake.ours()) == 1
    assert kr_rows(lw)[0].state == "sent"


def test_a_lost_answer_is_resent_with_the_same_id_and_gives_the_first_order(lw: Live) -> None:
    ids = planned(lw)
    lw.fake.lose_response = True
    report = lw.sync("2026-07-01 09:05")
    assert {"order_id": ids[("buy", "KR")], "sent": "unknown"} in report["changes"]
    assert kr_rows(lw)[0].state == "unknown"
    assert lw.stages()["result"] in ("quiet", "waiting")  # never failed while unknown
    lw.sync("2026-07-01 09:10")  # 5 minutes later: the same client order id again
    assert len(lw.fake.ours()) == 1
    row = kr_rows(lw)[0]
    assert (row.state, row.broker_order_id) == ("done", "ord-0001")
    assert lw.stages("2026-07-01 09:10")["result"] in ("done", "waiting")
    assert repo.fill_of_order(lw.conn, ids[("buy", "KR")]) is not None


def test_a_crash_before_the_request_left_is_found_and_sent_again_the_next_day(lw: Live) -> None:
    ids = planned(lw)
    order = repo.get_order(lw.conn, ids[("buy", "KR")])
    request = OrderRequest(client_order_id(order.idem_key), "069500", "BUY", 156, D("32160"), Currency.KRW)
    with transaction(lw.conn):  # the intent committed, then the process died
        live_repo.insert_intent(lw.conn, order_id=order.order_id, ledger_id="live", request=request, at=lw.at("2026-07-01 09:05"))
    report = lw.sync("2026-07-01 09:20")  # past the 9 minutes: never resent blindly
    assert {"order_id": order.order_id, "lost": True} in report["changes"]
    assert lw.fake.ours() == []
    failed = lw.stages()
    assert failed["result"] == "failed"  # '다음 날 같은 시각'
    retry = [o for o in repo.orders_of_ledger(lw.conn, "live") if o.retry_of == order.order_id]
    assert len(retry) == 1
    lw.sync("2026-07-02 09:05")
    sent = lw.fake.ours()
    assert len(sent) == 1
    assert sent[0].client_order_id == client_order_id(retry[0].idem_key) != request.client_order_id


def test_a_crash_after_the_broker_took_it_is_adopted_not_resent(lw: Live) -> None:
    ids = planned(lw)
    lw.fake.fill_mode = "open"
    order = repo.get_order(lw.conn, ids[("buy", "KR")])
    request = OrderRequest(client_order_id(order.idem_key), "069500", "BUY", 156, D("32160"), Currency.KRW)
    lw.at("2026-07-01 09:05")
    with transaction(lw.conn):
        live_repo.insert_intent(lw.conn, order_id=order.order_id, ledger_id="live", request=request, at=lw.now())
    # The order reached Toss, the answer was lost and the server was down for 15 minutes.
    lw.fake._create(request.body())
    lw.sync("2026-07-01 09:20")
    assert len(lw.fake.ours()) == 1
    row = kr_rows(lw)[0]
    assert (row.state, row.broker_order_id) == ("sent", "ord-0001")


def test_two_candidates_wait_for_a_person(lw: Live) -> None:
    ids = planned(lw)
    lw.fake.fill_mode = "open"
    order = repo.get_order(lw.conn, ids[("buy", "KR")])
    request = OrderRequest(client_order_id(order.idem_key), "069500", "BUY", 156, D("32160"), Currency.KRW)
    lw.at("2026-07-01 09:05")
    with transaction(lw.conn):
        live_repo.insert_intent(lw.conn, order_id=order.order_id, ledger_id="live", request=request, at=lw.now())
    body = {**request.body(), "clientOrderId": "app-1"}
    lw.fake._create(body)
    lw.fake._create({**body, "clientOrderId": "app-2"})
    lw.sync("2026-07-01 09:20")
    row = kr_rows(lw)[0]
    assert (row.state, row.error_code) == ("unknown", "ambiguous")
    assert [r.order_id for r in live.unknown_orders(lw.conn)] == [order.order_id]
    lw.sync("2026-07-01 09:30")
    assert len(lw.fake.orders) == 2  # nothing more was sent


# ── what comes back ──────────────────────────────────────────────────────────────────────


def test_a_partial_fill_books_what_filled_and_drops_the_rest(lw: Live) -> None:
    ids = planned(lw)
    lw.fake.fill_mode = "partial"
    lw.fake.partial_qty = D("100")
    lw.sync("2026-07-01 09:05")
    assert lw.stages()["result"] == "quiet"  # still open at the broker
    lw.fake.expire_open()  # the session ends: the rest is cancelled
    lw.sync("2026-07-01 15:40")
    assert lw.stages()["result"] in ("done", "waiting")
    fill = repo.fill_of_order(lw.conn, ids[("buy", "KR")])
    assert fill is not None
    assert (fill.qty, fill.gross) == (100, D("3216000"))
    assert not [o for o in repo.orders_of_ledger(lw.conn, "live") if o.retry_of]
    assert lw.state().qty_of("KR:069500") == 100
    lw.reconcile()
    assert lw.status().reconcile_state == "match"
    assert verify_ledger(lw.conn, "live") == []


def test_a_day_order_still_open_after_its_session_is_cancelled(lw: Live) -> None:
    planned(lw)
    lw.fake.fill_mode = "open"
    lw.sync("2026-07-01 09:05")
    lw.sync("2026-07-01 15:50")  # within 30 minutes of the close: Toss ends day orders itself
    assert lw.fake.ours()[0].status == "PENDING"
    lw.sync("2026-07-01 16:05")  # past the close + 30 minutes and still open: cancel it
    assert lw.fake.ours()[0].status == "CANCELED"
    row = kr_rows(lw)[0]
    assert (row.state, row.cancel_state) == ("done", "done")
    assert lw.stages()["result"] == "failed"  # nothing filled: tried again the next day


def test_a_refused_order_is_a_manual_action_never_retried(lw: Live) -> None:
    ids = planned(lw)
    lw.fake.refuse["069500"] = (422, "prerequisite-required", {})
    report = lw.sync("2026-07-01 09:05")
    assert {"order_id": ids[("buy", "KR")], "refused": "prerequisite-required", "outcome": "rejected"} in report["changes"]
    assert lw.stages()["result"] == "failed"
    order = repo.get_order(lw.conn, ids[("buy", "KR")])
    assert (order.status, order.failure_reason, order.manual) == ("failed", "broker-rejected", True)
    assert not [o for o in repo.orders_of_ledger(lw.conn, "live") if o.retry_of]
    plan = repo.get_plan(lw.conn, order.plan_id)
    assert plan.status == "todo"
    lw.sync("2026-07-02 09:05")
    assert lw.fake.ours() == []  # nothing sent again


def test_a_rejection_after_acceptance_is_a_manual_action(lw: Live) -> None:
    ids = planned(lw)
    lw.fake.fill_mode = "reject-later"
    lw.sync("2026-07-01 09:05")
    assert lw.stages()["result"] == "failed"
    order = repo.get_order(lw.conn, ids[("buy", "KR")])
    assert (order.failure_reason, order.manual) == ("broker-rejected", True)


def test_order_hours_closed_waits_for_the_time_toss_names(lw: Live) -> None:
    ids = planned(lw)
    lw.fake.refuse_once = [(422, "order-hours-closed", {"retryAfterAt": "2026-07-01T09:10:00+09:00"})]
    lw.sync("2026-07-01 09:05")
    row = kr_rows(lw)[0]
    assert (row.state, row.error_code) == ("not-sent", "order-hours-closed")
    assert row.retry_after is not None
    assert lw.stages()["result"] in ("quiet", "waiting", "done")
    lw.sync("2026-07-01 09:07")
    assert lw.fake.ours() == []  # not before the time
    lw.sync("2026-07-01 09:10")
    sent = lw.fake.ours()
    assert len(sent) == 1
    assert sent[0].client_order_id != client_order_id(repo.get_order(lw.conn, ids[("buy", "KR")]).idem_key)
    assert lw.stages()["result"] in ("done", "waiting")


def test_a_buy_uses_only_the_rules_cash_and_the_brokers(lw: Live) -> None:
    ids = planned(lw)
    lw.fake.cash["KRW"] = D("3000000")  # the account has less than the ledger thinks
    lw.sync("2026-07-01 09:05")
    sent = lw.fake.ours()
    assert sent[0].quantity == D("93")  # floor(3,000,000 / (32,160 x 1.00015))
    lw.fake.cash["KRW"] = D("0")
    order_id = ids[("buy", "KR")]
    row = live_repo.get_broker_order(lw.conn, order_id)
    assert row is not None


def test_no_cash_at_all_is_not_sent_and_tried_again_the_next_day(lw: Live) -> None:
    planned(lw)
    lw.fake.cash["KRW"] = D("100")
    lw.sync("2026-07-01 09:05")
    assert lw.fake.ours() == []
    row = kr_rows(lw)[0]
    assert (row.state, row.error_code) == ("not-sent", "no-cash")
    assert lw.stages()["result"] == "failed"


def test_an_order_over_the_limit_is_never_sent(lw: Live) -> None:
    planned(lw)
    lw.ctx = type(lw.ctx)(**{**lw.ctx.__dict__, "cfg": lw.cfg.__class__(**{**lw.cfg.__dict__, "live_max_order_krw": D("1000000")})})
    lw.sync("2026-07-01 09:05")
    assert lw.fake.ours() == []
    assert kr_rows(lw)[0].error_code == "over-limit"
    lw.stages()
    order = [o for o in repo.orders_of_ledger(lw.conn, "live") if o.market == "KR"][0]
    assert (order.failure_reason, order.manual) == ("broker-rejected", True)


def test_a_sell_respects_the_sellable_quantity(lw: Live) -> None:
    lw.fake.cash["KRW"] = D("0")
    lw.fake.hold("069500", D("300"), D("30000"), name="KODEX 200")
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    sells = [o for o in repo.orders_of_ledger(lw.conn, "live") if o.side == "sell"]
    assert sells and sells[0].instrument_id == "KR:069500"
    lw.fake.holdings["069500"].qty = D("300")
    lw.sync("2026-07-01 09:05")
    sold = [o for o in lw.fake.ours() if o.side == "SELL"]
    assert sold[0].price == D("31840")  # 32,000 x 0.995 on the 5-won tick
    assert lw.stages()["result"] in ("done", "waiting")


def test_executor_outcomes_from_the_records(lw: Live) -> None:
    ids = planned(lw)
    executor = TossExecutor(lw.conn)
    inst = repo.get_instrument(lw.conn, "KR:069500")
    at = lw.at("2026-07-01 09:05")
    req = TradeRequest(ids[("buy", "KR")], inst, Side.BUY, 156, at.date(), at, D(0), 0, None, False)
    assert isinstance(executor.trade(req), Waiting)
    late = TradeRequest(ids[("buy", "KR")], inst, Side.BUY, 156, at.date(), at, D(0), 0, None, True)
    outcome = executor.trade(late)
    assert isinstance(outcome, Failed) and outcome.reason is FailureReason.OTHER  # noqa: PT018
    with transaction(lw.conn):
        live_repo.record_not_sent(lw.conn, order_id=ids[("buy", "KR")], ledger_id="live", client_order_id="x", code="no-quote", detail="", at=at)
    outcome = executor.trade(req)
    assert isinstance(outcome, Failed) and outcome.reason is FailureReason.NO_QUOTE  # noqa: PT018
    with transaction(lw.conn):
        live_repo.record_not_sent(lw.conn, order_id=ids[("buy", "KR")], ledger_id="live", client_order_id="x", code="strange", detail="", at=at)
    assert executor.trade(req) == Failed(FailureReason.BROKER_REJECTED, "not sent: strange")
    with transaction(lw.conn):
        live_repo.mark_rejected(lw.conn, ids[("buy", "KR")], "order-hours-closed", "late", at)
    outcome = executor.trade(req)
    assert isinstance(outcome, Failed) and outcome.retryable  # noqa: PT018


# ── prices on the tick ───────────────────────────────────────────────────────────────────


def test_ticks_and_limits() -> None:
    etf = kr_etf("069500", "KODEX 200")
    stock = kr_etf("005930", "삼성전자")
    stock = type(stock)(**{**stock.__dict__, "kind": Kind.STOCK})
    spym = us_etf("SPYM", "S&P 500 ETF")
    assert tick_size(etf, D("1999")) == D(1)
    assert tick_size(etf, D("105650")) == D(5)
    assert [tick_size(stock, D(p)) for p in ("1500", "4000", "15000", "30000", "70000", "300000", "600000")] == [
        D(1), D(5), D(10), D(50), D(100), D(500), D(1000)
    ]  # fmt: skip
    assert tick_size(spym, D("0.5")) == D("0.0001")
    assert limit_price(etf, Side.BUY, D("105650"), D("0.005")) == D("106175")
    assert limit_price(etf, Side.SELL, D("105650"), D("0.005")) == D("105125")
    assert limit_price(stock, Side.BUY, D("49800"), D("0.005")) == D("50000")  # crosses a tier
    assert on_tick(stock, D("199990"), up=True) == D("200000")
    assert limit_price(spym, Side.BUY, D("66.00"), D("0.005")) == D("66.33")
    with pytest.raises(ValueError, match="positive"):
        limit_price(spym, Side.BUY, D(0), D("0.005"))
    assert client_order_id("live:2026-07-01:index_half:buy:KR:KR:069500:a1").startswith("at-")
    assert len(client_order_id("x")) == 35


def test_send_records_are_stamped_with_the_wall_clock(lw: Live) -> None:
    planned(lw)
    lw.fake.fill_mode = "open"
    lw.sync("2026-07-01 09:05")
    row = kr_rows(lw)[0]
    assert row.sent_at is not None
    assert row.sent_at.astimezone(KST).strftime("%H:%M") == "09:05"
    assert lw.now() - row.sent_at < timedelta(seconds=1)
