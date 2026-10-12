"""The Toss sync's edges (jobs/live_tasks.py): keys missing, the link refused, errors in each
step, the resend window, cancels that cannot finish, daily facts, the read-only check and the
CLI commands. Against the fake Toss only."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from autotrade.broker.toss import client_order_id
from autotrade.broker.toss_api import OrderRequest
from autotrade.db import live_repo, repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency
from autotrade.engine import live
from autotrade.jobs import cli
from autotrade.jobs.live_tasks import broker_job, reconcile_job, toss_check

from .fakes import World
from .live_world import SECRETS, Live, make_live

D = Decimal


@pytest.fixture
def lw(tmp_path: Path, world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[Live]:
    monkeypatch.setenv("AUTOTRADE_LIVE_ORDERS", "1")
    yield from make_live(tmp_path, world)


def planned(lw: Live) -> dict[tuple[str, str], int]:
    lw.turn_on("2026-06-30 21:00")
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    return {(o.side, o.market): o.order_id for o in repo.orders_of_ledger(lw.conn, "live")}


def intent(lw: Live, order_id: int, when: str) -> OrderRequest:
    order = repo.get_order(lw.conn, order_id)
    request = OrderRequest(
        client_order_id(order.idem_key), "069500", "BUY", 156, D("32160"), Currency.KRW
    )
    with transaction(lw.conn):
        live_repo.insert_intent(
            lw.conn, order_id=order_id, ledger_id="live", request=request, at=lw.at(when)
        )
    return request


def test_missing_keys_and_a_refused_link_are_recorded_once(lw: Live) -> None:
    lw.cfg.secrets_env.write_text("TOSS_CLIENT_ID=only-the-id\n")  # type: ignore[union-attr]
    first = lw.sync("2026-06-30 21:00")
    assert (first["result"], lw.status().state) == ("no-key", "no-key")
    assert lw.sync("2026-06-30 21:05")["result"] == "quiet"  # the same news is not news again
    lw.cfg.secrets_env.write_text(SECRETS)  # type: ignore[union-attr]
    lw.fake.ip_allowed = False
    assert lw.sync("2026-06-30 21:10")["result"] == "ip"
    assert live.link_check(lw.conn, lw.cfg, lw.now()).cause == "ip"
    lw.fake.ip_allowed = True
    assert lw.sync("2026-06-30 21:15")["result"] == "synced"
    assert live.link_check(lw.conn, lw.cfg, lw.now()).ok


def test_an_error_in_the_middle_of_a_sync_names_the_link(lw: Live) -> None:
    lw.sync("2026-06-30 21:00")
    lw.fake.fail_next = [(500, "maintenance")] * 8
    report = lw.sync("2026-06-30 21:05")
    assert report["result"] == "maintenance"
    assert lw.status().state == "maintenance"
    assert lw.status().ok_at is not None  # the last good look is kept


def test_a_tradable_check_that_fails_blocks_live(lw: Live) -> None:
    for status, cause in (
        ({"status": "DELISTED"}, "inactive"),
        ({"koreanMarketDetail": {"liquidationTrading": True}}, "liquidation"),
        ({"koreanMarketDetail": {"krxTradingSuspended": True}}, "suspended"),
        ({"currency": "USD"}, "currency"),
        ({"status": "GONE"}, "not-found"),
    ):
        lw.fake.stock_status = {"069500": status}
        with transaction(lw.conn):
            lw.conn.execute("DELETE FROM broker_status")
        lw.sync("2026-06-30 21:00")
        assert lw.status().tradable["KR:069500"] == cause
        assert live.link_check(lw.conn, lw.cfg, lw.now()).cause == "not-tradable"


def test_poll_errors_are_kept_and_the_rest_goes_on(lw: Live) -> None:
    ids = planned(lw)
    lw.fake.fill_mode = "open"
    lw.sync("2026-07-01 09:05")
    lw.fake.orders.clear()  # the broker no longer knows it (order-not-found)
    report = lw.sync("2026-07-01 09:06")
    assert "order-not-found" in report["error"]
    row = live_repo.get_broker_order(lw.conn, ids[("buy", "KR")])
    assert row is not None and row.state == "sent"  # noqa: PT018


def test_an_unknown_order_without_its_request_is_lost(lw: Live) -> None:
    ids = planned(lw)
    with transaction(lw.conn):
        lw.conn.execute(
            "INSERT INTO broker_orders (order_id, ledger_id, client_order_id, state, request,"
            " updated_at) VALUES (?, 'live', 'at-x', 'unknown', '{}', '2026-07-01T00:00:00+00:00')",
            (ids[("buy", "KR")],),
        )
    lw.sync("2026-07-01 09:05")
    row = live_repo.get_broker_order(lw.conn, ids[("buy", "KR")])
    assert row is not None and (row.state, row.error_code) == ("not-sent", "lost")  # noqa: PT018


def test_an_unknown_order_is_searched_not_resent_once_the_mode_is_paper(lw: Live) -> None:
    ids = planned(lw)
    intent(lw, ids[("buy", "KR")], "2026-07-01 09:05")
    with transaction(lw.conn):
        repo.set_setting(lw.conn, "mode", "paper", lw.now())
    lw.sync("2026-07-01 09:07")  # within 9 minutes, but no permit: look, do not send
    row = live_repo.get_broker_order(lw.conn, ids[("buy", "KR")])
    assert row is not None and row.state == "sending"  # noqa: PT018
    assert lw.fake.ours() == []
    lw.fake.down = True
    lw.sync("2026-07-01 09:20")  # the search cannot run: nothing decided
    row = live_repo.get_broker_order(lw.conn, ids[("buy", "KR")])
    assert row is not None and row.state == "sending"  # noqa: PT018


def test_cancels_that_cannot_finish_now(lw: Live) -> None:
    ids = planned(lw)
    lw.fake.fill_mode = "open"
    lw.sync("2026-07-01 09:05")
    lw.turn_off("2026-07-01 09:06")
    lw.fake.refuse["cancel"] = (409, "already-processing", {})
    lw.sync("2026-07-01 09:07")
    row = live_repo.get_broker_order(lw.conn, ids[("buy", "KR")])
    assert row is not None and row.cancel_state == "requested"  # noqa: PT018
    del lw.fake.refuse["cancel"]

    def no_answer(request: Any) -> Any:
        if request.url.endswith("/cancel"):
            from autotrade.broker.toss_api import TransportError

            raise TransportError("timeout")
        return lw.fake(request)

    lw.ctx = replace(lw.ctx, toss_transport=no_answer)
    broker_job(
        lw.conn,
        lw.cfg,
        lw.at("2026-07-01 09:08"),
        transport=no_answer,
        now=lw.now,
        sleep=lambda s: None,
    )
    row = live_repo.get_broker_order(lw.conn, ids[("buy", "KR")])
    assert row is not None and row.cancel_state == "failed"  # noqa: PT018


def test_nothing_is_sent_while_the_account_does_not_match(lw: Live) -> None:
    planned(lw)
    status = lw.status()
    with transaction(lw.conn):
        live_repo.save_status(lw.conn, replace(status, reconcile_state="mismatch"), lw.now())
    lw.sync("2026-07-01 09:05")
    assert lw.fake.ours() == []


def test_a_missing_price_sends_nothing(lw: Live) -> None:
    ids = planned(lw)
    lw.fake.prices = {}
    report = lw.sync("2026-07-01 09:05")
    assert "price 069500: none" in report["error"]
    assert live_repo.get_broker_order(lw.conn, ids[("buy", "KR")]) is None
    lw.fake.prices = {"069500": D("32000"), "SPYM": D("66.00")}
    lw.fake.fail_next = [(500, "internal-error")]
    report = lw.sync("2026-07-01 09:06")
    assert "price 069500" in report["error"]


@pytest.mark.parametrize(
    ("status", "code", "state", "error"),
    [
        (500, "internal-error", "unknown", "internal-error"),
        (409, "request-in-progress", "unknown", "request-in-progress"),
        (403, "forbidden", "not-sent", "link"),
        (422, "idempotency-key-conflict", "rejected", "idempotency-key-conflict"),
        (409, "opposite-pending-order-exists", "rejected", "opposite-pending-order-exists"),
    ],
)
def test_each_refusal_lands_where_it_belongs(
    lw: Live, status: int, code: str, state: str, error: str
) -> None:
    ids = planned(lw)
    lw.fake.refuse_once = [(status, code, {})]
    lw.sync("2026-07-01 09:05")
    row = live_repo.get_broker_order(lw.conn, ids[("buy", "KR")])
    assert row is not None
    assert (row.state, row.error_code) == (state, error)


def test_a_link_refusal_is_sent_again_next_time(lw: Live) -> None:
    ids = planned(lw)
    lw.fake.refuse_once = [(403, "forbidden", {})]
    lw.sync("2026-07-01 09:05")
    lw.sync("2026-07-01 09:10")
    row = live_repo.get_broker_order(lw.conn, ids[("buy", "KR")])
    assert row is not None and row.state == "done"  # noqa: PT018
    assert len(lw.fake.ours()) == 1


def test_the_account_is_not_quiet_while_an_order_is_open(lw: Live) -> None:
    lw.sync("2026-06-30 21:00")
    lw.fake.fill_mode = "open"
    lw.fake._create(
        {"symbol": "069500", "side": "BUY", "orderType": "LIMIT", "quantity": "1", "price": "1"}
    )
    lw.sync("2026-06-30 21:05")
    snap = live_repo.latest_snapshot(lw.conn)
    assert snap is not None and not snap.quiet  # noqa: PT018
    data = live.preview_data(lw.conn, lw.cfg, lw.now())
    assert isinstance(data, live.NotComputable)


def test_the_read_only_check(lw: Live) -> None:
    lw.fake.hold("069500", D("3"), D("31000"), name="KODEX 200")
    out = toss_check(lw.cfg, lw.conn, transport=lw.fake)
    assert out["result"] == "ok"
    assert out["account"] == {"seq": 7, "tail": "8901", "type": "BROKERAGE"}
    assert out["cash"] == {"KRW": "10000000", "USD": "0"}
    assert out["holdings"] == [{"id": "KR:069500", "name": "KODEX 200", "qty": "3"}]
    assert out["openOrders"] == 0
    assert out["instruments"]["US:SPYM"]["tradable"] is True
    assert out["fx"] == {"rate": "1392.0", "midRate": "1391.0"}
    assert not [c for c in lw.fake.calls if c == ("POST", "/api/v1/orders")]
    text = json.dumps(out)
    assert "s3cret" not in text and "tok-" not in text  # noqa: PT018
    lw.fake.ip_allowed = False
    bad = toss_check(lw.cfg, lw.conn, transport=lw.fake)
    assert (bad["result"], bad["cause"]) == ("failed", "ip")


def test_the_cli_commands(lw: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    lines: list[str] = []
    env = {"AUTOTRADE_SECRETS_ENV": str(lw.cfg.secrets_env), "AUTOTRADE_LIVE_ORDERS": "1"}
    db = str(lw.cfg.db_path)
    # The CLI reaches the network through the default transport: the fake stands in for it
    # (and the conftest blocks sockets anyway).
    monkeypatch.setattr("autotrade.jobs.live_tasks.urllib_transport", lw.fake)

    def run(*args: str) -> tuple[int, dict[str, Any]]:
        code = cli.main([*args, "--db", db, "--at", "2026-06-30T21:00"], env=env, out=lines.append)
        return code, json.loads(lines[-1])

    code, out = run("toss-check")
    assert (code, out["result"]) == (0, "ok")
    code, out = run("broker")
    assert (code, out["result"]) == (0, "synced")
    code, out = run("reconcile")
    assert (code, out["result"], out["reason"]) == (0, "skipped", "not-started")
    code, out = run("adopt-broker", "--note", "checked")
    assert out["result"] == "not-started"
    with pytest.raises(SystemExit):
        cli.main(["adopt-broker", "--db", db], env=env, out=lines.append)


def test_a_dry_reconcile_writes_nothing(lw: Live) -> None:
    lw.turn_on("2026-06-30 21:00")
    lw.fake.deposit("KRW", D("1000"))
    lw.sync("2026-06-30 21:05")
    report = reconcile_job(lw.conn, lw.cfg, lw.now(), dry_run=True)
    assert report["result"] == "match"
    assert repo.events_of_ledger(lw.conn, "live", ["deposit"]) == []


def test_an_empty_account_cannot_start(lw: Live) -> None:
    lw.fake.cash["KRW"] = D("0")
    lw.sync("2026-06-30 21:00")
    lw.market_data()
    data = live.preview_data(lw.conn, lw.cfg, lw.now())
    assert isinstance(data, live.NotComputable)
    assert data.detail.startswith("empty")
