"""The live ledger against the account (PHASE3.md 2.5): deposits, withdrawals, the owner's
trades in the app (sale proceeds wait for the withdrawal, 인계 5), conversions, dividends, a
mismatch (nothing written, no order), a busy account, late fills, adopting the broker's numbers.
And the rule that never trades on what it cannot explain: 0 orders."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from autotrade.db import live_repo, repo
from autotrade.db.connection import transaction
from autotrade.domain.cash import Purpose
from autotrade.domain.instruments import Currency
from autotrade.engine import live
from autotrade.engine.live import NotComputable, withdraw_until
from autotrade.engine.rebuild import rebuild_state, verify_ledger
from autotrade.jobs.tasks import adopt_job

from .fakes import KR, World
from .live_world import Live, make_live

D = Decimal


@pytest.fixture
def lw(tmp_path: Path, world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[Live]:
    monkeypatch.setenv("AUTOTRADE_LIVE_ORDERS", "1")
    yield from make_live(tmp_path, world)


def on(lw: Live) -> None:
    lw.turn_on("2026-06-30 21:00")


def events(lw: Live, *kinds: str) -> list[tuple[str, Decimal | None, str | None]]:
    rows = repo.events_of_ledger(lw.conn, "live", list(kinds))
    return [(e.kind, e.amount, None if e.currency is None else e.currency.value) for e in rows]


def test_a_deposit_and_a_withdrawal_are_seen_in_the_cash(lw: Live) -> None:
    on(lw)
    lw.fake.deposit("KRW", D("2000000"))
    lw.sync("2026-06-30 22:00")
    assert lw.reconcile()["result"] == "match"
    assert events(lw, "deposit") == [("deposit", D("2000000"), "KRW")]
    assert lw.state().cash_of(Currency.KRW) == D("12000000")
    assert lw.state().contributions_krw == D("12000000")
    lw.fake.withdraw("KRW", D("500000"))
    lw.sync("2026-06-30 22:05")
    lw.reconcile()
    assert events(lw, "withdrawal") == [("withdrawal", D("500000"), "KRW")]
    lw.fake.deposit("USD", D("100.00"))
    lw.sync("2026-06-30 22:10")
    lw.reconcile()
    usd = repo.events_of_ledger(lw.conn, "live", ["deposit"])[-1]
    assert (usd.amount, usd.currency, usd.payload["krw_rate"]) == (
        D("100.00"),
        Currency.USD,
        "1392.0",
    )
    assert verify_ledger(lw.conn, "live") == []
    assert lw.reconcile("2026-06-30 22:11")["result"] == "quiet"  # nothing new: nothing written


def test_a_sale_in_the_app_waits_for_its_withdrawal(lw: Live) -> None:
    lw.fake.hold("069500", D("20"), D("30000"), name="KODEX 200")
    on(lw)
    assert lw.state().qty_of(KR) == 20
    lw.at("2026-07-01 08:10")
    lw.fake.app_trade(
        "069500", "SELL", D("14"), D("32000"), commission=D("67"), settlement=date(2026, 7, 2)
    )
    lw.sync("2026-07-01 08:20")
    result = lw.reconcile()
    assert result["result"] == "match"
    assert lw.state().qty_of(KR) == 6
    waits = repo.withdraw_waits(lw.conn, "live")
    # Settlement 7/2 + 2 Korean trading days = 7/6 (7/4·7/5 a weekend).
    assert [(w.amount, w.until) for w in waits] == [(D("447933"), date(2026, 7, 6))]
    ext = live_repo.externals_of(lw.conn, "live")
    assert [(e.kind, e.treatment, e.side, e.qty, e.gross, e.fee) for e in ext] == [
        ("trade", "ledger", "sell", 14, D("448000"), D("67"))
    ]
    assert verify_ledger(lw.conn, "live") == []
    # On the live ledger the wait holds its own money only (audit 2026-10-13): the check plans
    # the rest as usual, floor(10,000,000 / (32,160 x 1.00015)) = 310 shares, and the 447,933
    # won stay for the withdrawal (the paper ledger still stops: test_engine_invariants).
    report = lw.check("2026-07-01 08:30")
    assert report["result"] == "rebalance"
    assert report["details"]["withdraw_held"] == {"KRW": D("447933")}
    assert report["details"]["withdraw_held_until"] == date(2026, 7, 6)
    assert [o.qty for o in repo.orders_of_ledger(lw.conn, "live")] == [310]
    # The owner withdraws the proceeds: a net withdrawal that takes the waiting cash first.
    lw.fake.withdraw("KRW", D("447933"))
    lw.sync("2026-07-01 08:45")
    lw.reconcile()
    assert repo.withdraw_waits(lw.conn, "live") == []
    assert events(lw, "withdrawal") == [("withdrawal", D("447933"), "KRW")]


def test_the_owners_outside_trades_move_money_in_and_out(lw: Live) -> None:
    on(lw)
    lw.at("2026-06-30 21:50")
    lw.fake.app_trade("005930", "BUY", D("10"), D("70000"), commission=D("105"))
    lw.sync("2026-06-30 22:00")
    lw.reconcile()
    assert events(lw, "withdrawal") == [("withdrawal", D("700105"), "KRW")]
    lw.at("2026-06-30 22:02")
    lw.fake.app_trade("005930", "SELL", D("10"), D("71000"), commission=D("106"), tax=D("1420"))
    lw.sync("2026-06-30 22:05")
    lw.reconcile()
    assert events(lw, "deposit") == [("deposit", D("708474"), "KRW")]
    waits = repo.withdraw_waits(lw.conn, "live")
    assert [w.amount for w in waits] == [D("708474")]
    outside = live_repo.externals_of(lw.conn, "live", "outside")
    assert [(e.side, e.gross) for e in outside] == [("buy", D("700000")), ("sell", D("710000"))]
    assert lw.state().positions == {}  # never the ledger's
    assert verify_ledger(lw.conn, "live") == []


def test_a_conversion_nobody_asked_for_moves_money_between_the_accounts(lw: Live) -> None:
    on(lw)
    lw.fake.convert(D("1392000"), D("999.80"))
    lw.sync("2026-06-30 22:00")
    seen = lw.now()
    result = lw.reconcile("2026-06-30 22:01")
    assert result["booked"][0]["conversion"] == "krw_to_usd"
    # The owner's own conversion: out of 한국 계좌, into 미국 계좌, each in its currency, dated
    # when the account showed it, marked as a conversion (api/views/accounts.py: a transfer).
    rows = repo.events_of_ledger(lw.conn, "live", ["deposit", "withdrawal"])
    assert sorted((e.kind, e.amount, e.currency, e.occurred_at) for e in rows) == [
        ("deposit", D("999.80"), Currency.USD, seen),
        ("withdrawal", D("1392000"), Currency.KRW, seen),
    ]
    assert {e.payload["reason"] for e in rows} == {"conversion"}
    assert live_repo.externals_of(lw.conn, "live") == []
    state = lw.state()
    assert state.cash_of(Currency.USD) == D("999.80")
    # Booked at the rate it was made: the ledger's money in does not move (a won of rounding).
    assert abs(state.contributions_krw - D("10000000")) <= 1
    assert verify_ledger(lw.conn, "live") == []
    # At a rate no market gives (100,000원 for $999.80) won came in too: the owner deposited and
    # converted within the same five minutes. The dollars are his conversion at the market rate
    # (1,392.0: 1,391,722원), the rest of the won his deposit (1,291,722원).
    lw.fake.convert(D("100000"), D("999.80"))
    lw.sync("2026-06-30 22:05")
    lw.reconcile()
    later = [
        (e.kind, e.amount, e.currency, e.payload["reason"])
        for e in repo.events_of_ledger(lw.conn, "live", ["deposit", "withdrawal"])
        if e.occurred_at == lw.now()
    ]
    assert later == [
        ("deposit", D("1291722"), Currency.KRW, "unexplained-in"),
        ("withdrawal", D("1391722"), Currency.KRW, "conversion"),
        ("deposit", D("999.80"), Currency.USD, "conversion"),
    ]
    assert verify_ledger(lw.conn, "live") == []


def test_a_dividend_is_income_not_a_deposit(lw: Live, world: World) -> None:
    lw.fake.hold("069500", D("100"), D("30000"), name="KODEX 200")
    on(lw)
    world.dividend(KR, "2026-07-01", "160", pay_date="2026-07-03")
    from autotrade.market.service import prefetch_dividends

    prefetch_dividends(
        lw.conn,
        lw.cfg,
        lw.ctx.sources,
        [repo.get_instrument(lw.conn, KR)],
        date(2026, 6, 1),
        date(2026, 7, 3),
        lw.at("2026-07-03 08:00"),
    )
    lw.fake.deposit("KRW", D("13536"))  # the broker's net (its tax differs from the estimate)
    lw.sync("2026-07-03 08:10")
    lw.reconcile()
    assert events(lw, "dividend") == [("dividend", D("13536"), "KRW")]
    assert events(lw, "deposit") == []
    assert lw.state().income_krw == D("13536")
    # Booked once: the same dividend again is a deposit.
    lw.fake.deposit("KRW", D("13536"))
    lw.sync("2026-07-03 08:15")
    lw.reconcile()
    assert events(lw, "deposit") == [("deposit", D("13536"), "KRW")]


def test_a_mismatch_writes_nothing_and_stops_the_orders(lw: Live) -> None:
    on(lw)
    lw.fake.deposit("KRW", D("1000"))
    lw.fake.hold("069500", D("5"), D("32000"), name="KODEX 200")  # shares nothing explains
    lw.sync("2026-07-01 08:20")
    result = lw.reconcile()
    assert (result["result"], result["reason"]) == ("mismatch", "positions")
    assert result["detail"]["positions"] == [{"instrument_id": KR, "ledger": "0", "broker": "5"}]
    assert events(lw, "deposit") == []  # the deposit waits too: all or nothing
    assert lw.status().reconcile_state == "mismatch"
    check = lw.check("2026-07-01 08:30")
    assert (check["result"], check["error"]) == ("failed", "mismatch: positions")
    assert repo.open_plans(lw.conn, "live") == []
    assert live.link_check(lw.conn, lw.cfg, lw.now()).cause == "mismatch"
    # The owner checked the app: the broker is right. Adopt it (on a fresh look at the account).
    lw.sync("2026-07-01 09:00")
    adopted = adopt_job(lw.ctx, lw.now(), note="입고 확인")
    assert adopted["result"] == "adopted"
    assert lw.state().qty_of(KR) == 5
    assert lw.status().reconcile_state == "match"
    assert verify_ledger(lw.conn, "live") == []
    assert rebuild_state(lw.conn, "live").qty_of(KR) == 5
    assert (
        adopt_job(lw.ctx, lw.at("2026-07-01 09:01"), note="again")["result"] == "nothing-to-adopt"
    )


def test_cash_that_vanished_beyond_the_ledgers_is_a_mismatch(lw: Live) -> None:
    on(lw)
    lw.fake.withdraw("KRW", D("10000001"))
    lw.sync("2026-06-30 22:00")
    result = lw.reconcile()
    assert (result["result"], result["reason"]) == ("mismatch", "cash")


def test_an_open_order_anywhere_makes_the_account_busy(lw: Live) -> None:
    on(lw)
    lw.fake.fill_mode = "open"
    lw.fake._create(
        {"symbol": "069500", "side": "BUY", "orderType": "LIMIT", "quantity": "1", "price": "32000"}
    )
    lw.sync("2026-07-01 08:20")
    assert live_repo.latest_snapshot(lw.conn) is not None
    assert lw.reconcile()["result"] == "quiet"  # busy is not news
    assert lw.status().reconcile_state == "busy"
    check = lw.check("2026-07-01 08:30")
    assert (check["result"], check["error"]) == ("failed", "broker: orders-open")


def test_an_old_snapshot_is_not_the_truth(lw: Live) -> None:
    on(lw)
    report = lw.check("2026-07-01 08:30")  # the last look at the account was at 21:00
    assert (report["result"], report["error"]) == ("failed", "broker: old-snapshot")
    late = lw.check("2026-07-01 09:31")
    assert late["result"] == "todo"


def test_stale_quotes_and_holidays_mean_no_live_order(lw: Live, world: World) -> None:
    on(lw)
    world.fail_bars.update({KR, "US:SPYM"})
    world.remove_bar(KR, "2026-06-30")
    with transaction(lw.conn):
        lw.conn.execute("DELETE FROM market_prices WHERE session_date = '2026-06-30'")
    lw.sync("2026-07-01 08:29")
    report = lw.check("2026-07-01 08:30")
    assert report["result"] in ("quote-wait", "failed")
    assert repo.open_plans(lw.conn, "live") == []


def test_a_fill_after_live_off_is_still_booked(lw: Live) -> None:
    on(lw)
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    lw.fake.fill_mode = "open"
    lw.sync("2026-07-01 09:05")
    off = lw.turn_off("2026-07-01 09:06")
    assert len(off.cancel_requested) == 1
    sent = lw.fake.ours()[0]
    lw.fake.fill_open(sent.order_id, price=D("32000"))  # it filled before the cancel arrived
    lw.sync("2026-07-01 09:07")
    row = live_repo.broker_orders_of(lw.conn, "live")[0]
    assert (row.state, row.cancel_state) == ("done", "done")
    result = lw.reconcile()
    assert {"late_fill": row.order_id, "qty": 310} in result["booked"]
    assert lw.state().qty_of(KR) == 310
    assert repo.get_order(lw.conn, row.order_id).status == "filled"
    assert lw.status().reconcile_state == "match"
    assert verify_ledger(lw.conn, "live") == []


def test_a_cancel_that_fails_stays_visible_and_is_tried_again(lw: Live) -> None:
    on(lw)
    lw.sync("2026-07-01 08:29")
    lw.check("2026-07-01 08:30")
    lw.fake.fill_mode = "open"
    lw.sync("2026-07-01 09:05")
    lw.turn_off("2026-07-01 09:06")
    assert [r.order_id for r in live.cancel_pending(lw.conn)]
    lw.fake.refuse["cancel"] = (422, "cancel-restricted", {})
    lw.sync("2026-07-01 09:07")
    failed = live.cancel_failed(lw.conn)
    assert len(failed) == 1
    assert failed[0].cancel_error is not None and "cancel-restricted" in failed[0].cancel_error  # noqa: PT018
    with transaction(lw.conn):
        assert live.retry_cancels(lw.conn, lw.at("2026-07-01 09:08")) == [failed[0].order_id]
    assert live.cancel_failed(lw.conn) == []
    del lw.fake.refuse["cancel"]
    lw.sync("2026-07-01 09:09")
    assert live.cancel_pending(lw.conn) == []
    assert lw.fake.ours()[0].status == "CANCELED"


def test_a_fractional_rule_holding_cannot_start(lw: Live) -> None:
    lw.fake.hold("SPYM", D("1.5"), D("60"), market="US")
    lw.sync("2026-06-30 21:00")
    lw.market_data()
    data = live.preview_data(lw.conn, lw.cfg, lw.now())
    assert isinstance(data, NotComputable)
    assert data.detail.startswith("fractional")


def test_withdraw_until_counts_korean_trading_days() -> None:
    assert withdraw_until(date(2026, 7, 2), date(2026, 6, 30)) == date(2026, 7, 6)
    assert withdraw_until(None, date(2026, 7, 1)) == date(2026, 7, 7)  # T+2, then + 2


def test_the_reconciliation_waits_for_orders_in_flight(lw: Live) -> None:
    on(lw)
    lw.sync("2026-07-01 08:29")
    lw.check("2026-07-01 08:30")
    lw.fake.lose_response = True
    lw.sync("2026-07-01 09:05")  # the order's fate is unknown
    assert lw.reconcile()["result"] == "quiet"
    assert lw.status().reconcile_state == "busy"
    parts = [p.purpose for p in repo.cash_parts(lw.conn, "live")]
    assert Purpose.WITHDRAW_WAIT not in parts
