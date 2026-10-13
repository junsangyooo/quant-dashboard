"""The mode switch and the Toss rows through the web API (PHASE3.md 2.6-2.7).

The API only reads what the tick recorded; the tick's side runs against the fake Toss
(tests/autotrade/live_world.py)."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from autotrade.api.app import create_app
from autotrade.api.settings import ApiSettings
from autotrade.db import live_repo, repo
from autotrade.engine import live

from ..fakes import World
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


def ready(lw: Live, when: str = "2026-06-30 21:00") -> None:
    """The tick looked at Toss and the paper ledger's jobs have the closes and the rate."""
    lw.sync(when)
    lw.market_data()


def turn_on(web: TestClient, preview_hash: str, pin: str = PIN) -> Any:
    return web.post(
        "/api/mode/live", json={"pin": pin, "confirm": True, "previewHash": preview_hash}
    )


def test_the_mode_screen_before_turning_on(lw: Live, web: TestClient) -> None:
    ready(lw)
    mode = web.get("/api/mode").json()
    assert mode["mode"] == "paper"
    rows = {r["id"]: r for r in mode["preflight"]}
    assert rows["toss-link"] == {
        "id": "toss-link",
        "ok": True,
        "facts": {"checkedAt": "2026-06-30T21:00:00+09:00", "account": "8901"},
    }
    assert rows["freshness"]["ok"] is True
    assert rows["freshness"]["facts"]["balanceAt"] == "2026-06-30T21:00:00+09:00"
    assert rows["push"] == {"id": "push", "ok": True, "warn": True, "facts": {"devices": 0}}
    assert mode["canTurnOn"] == {"ok": True}
    preview = mode["preview"]
    assert preview["kind"] == "ok"
    assert preview["current"] == [{"label": "krw-cash", "krw": 10000000}]
    assert [(t["instrument"]["id"], t["pct"]) for t in preview["target"]] == [
        ("KR:069500", 50.0),
        ("US:SPYM", 50.0),
    ]
    # Won only: all of it buys the Korean ETF (D47). No conversion stage, no US order. Sized as
    # the send will pay: floor(10,000,000 / (32,160 x 1.00015)) = 310, the limit 0.5% over the
    # 32,000 close on its tick, plus the fee.
    assert [s["kind"] for s in preview["stages"]] == ["buy"]
    buys = preview["stages"][0]["orders"]
    assert [(o["instrument"]["id"], o["qty"]) for o in buys] == [("KR:069500", 310)]
    assert buys[0]["at"] == "2026-07-01T09:05:00+09:00"
    assert preview["outside"] == []
    # What the owner could convert for 50:50: half of the won, at the 21:00 rate.
    assert preview["fxSuggestion"] == {
        "direction": "krw-usd",
        "krw": 5000000,
        "usd": 3591.95,
        "rate": 1392.0,
        "now": {"kr": 100.0, "us": 0.0},
        "target": {"kr": 50.0, "us": 50.0},
    }
    assert preview["newMoney"] is None  # a first start: the account is the start, not new money
    assert live_repo.get_preview(lw.conn, preview["hash"]) is not None
    health = web.get("/api/health").json()
    link = next(s for s in health["sources"] if s["id"] == "toss-link")
    assert (link["state"], link["cadence"], link["extra"]) == (
        "fresh",
        "per-check",
        {"account": "8901"},
    )


def test_turning_on_needs_the_pin_and_the_same_preview(lw: Live, web: TestClient) -> None:
    ready(lw)
    first = web.get("/api/mode").json()["preview"]["hash"]
    wrong = turn_on(web, first, pin="000000")
    assert (wrong.status_code, wrong.json()) == (403, {"error": "pin", "remaining": 4})
    assert web.post(
        "/api/mode/live", json={"pin": "12", "confirm": True, "previewHash": first}
    ).json() == {"error": "invalid-pin"}
    # The account changed by more than 1% since the owner looked: a new preview, not live.
    lw.fake.deposit("KRW", D("500000"))
    lw.sync("2026-06-30 21:05")
    changed = turn_on(web, first)
    assert changed.status_code == 409
    body = changed.json()
    assert body["error"] == "preview-changed"
    assert body["preview"]["current"] == [{"label": "krw-cash", "krw": 10500000}]
    assert live.mode_of(lw.conn) == "paper"
    ok = turn_on(web, body["preview"]["hash"])
    assert (ok.status_code, ok.json()) == (200, {"mode": "live"})
    assert turn_on(web, "anything").json() == {"mode": "live"}  # idempotent
    start = repo.start_event(lw.conn, "live")
    assert start is not None and start.amount == D("10500000")  # noqa: PT018
    shell = web.get("/api/shell").json()
    assert (shell["mode"], shell["liveSince"]) == ("live", "2026-06-30T21:05:00+09:00")
    mode = web.get("/api/mode").json()
    assert mode["live"] == {"since": "2026-06-30", "days": 1}
    assert (mode["preflight"], mode["preview"]) == (None, None)
    assert mode["offPreview"] == {"cancel": [], "cash": [{"currency": "KRW", "krw": 10500000}]}


def test_a_small_change_keeps_the_approved_preview(lw: Live, web: TestClient) -> None:
    ready(lw)
    first = web.get("/api/mode").json()["preview"]["hash"]
    lw.fake.deposit("KRW", D("10000"))  # 0.1%: the same orders, almost the same amounts
    lw.sync("2026-06-30 21:05")
    assert turn_on(web, first).json() == {"mode": "live"}


def test_another_program_on_the_same_client_blocks_turning_on(lw: Live, web: TestClient) -> None:
    ready(lw)
    lw.fake.revoke_from_elsewhere()
    lw.sync("2026-06-30 21:05")
    mode = web.get("/api/mode").json()
    link = next(r for r in mode["preflight"] if r["id"] == "toss-link")
    assert link == {"id": "toss-link", "ok": False, "facts": {"cause": "conflict"}}
    assert mode["canTurnOn"] == {"ok": False, "cause": "checks"}
    blocked = turn_on(web, mode["preview"]["hash"])
    assert blocked.json() == {"error": "blocked", "detail": {"cause": "checks"}}


def test_an_old_toss_check_blocks_turning_on(lw: Live, web: TestClient) -> None:
    ready(lw)
    # Both markets are closed at 21:00-21:50 (KRX shut, NYSE opens 22:30): the tick looks every
    # 30 minutes then, so a look counts as old only past 15 + 30 minutes (sync_max_age).
    lw.at("2026-06-30 21:50")
    mode = web.get("/api/mode").json()
    rows = {r["id"]: r for r in mode["preflight"]}
    assert rows["toss-link"]["facts"] == {"cause": "old"}
    assert rows["freshness"]["facts"]["source"] == "toss-balance"
    # The old account picture is the link's doing: one cause, not two.
    assert rows["freshness"]["sameCauseAs"] == "toss-link"
    assert mode["preview"]["kind"] == "not-computable"


def test_at_night_the_mode_screen_gets_a_fresh_look_within_a_tick(
    lw: Live, web: TestClient
) -> None:
    """At night the tick looks every 30 minutes, but the preview needs an account picture
    within 15: opening the mode screen makes the next tick look, so turning on waits one tick,
    not up to 30 minutes."""
    lw.tick("2026-06-30 21:00")
    lw.market_data()
    lw.tick("2026-06-30 21:15")
    assert lw.status().checked_at == kst("2026-06-30 21:00")  # the night cadence
    lw.at("2026-06-30 21:16")
    mode = web.get("/api/mode").json()
    rows = {r["id"]: r for r in mode["preflight"]}
    assert rows["toss-link"]["ok"] is True  # 16 minutes is no old link at night ...
    assert rows["freshness"]["facts"]["source"] == "toss-balance"  # ... but an old picture
    assert "sameCauseAs" not in rows["freshness"]
    assert mode["preview"]["kind"] == "not-computable"
    lw.tick("2026-06-30 21:20")
    assert lw.status().checked_at == kst("2026-06-30 21:20")
    mode = web.get("/api/mode").json()
    assert mode["canTurnOn"] == {"ok": True}
    assert turn_on(web, mode["preview"]["hash"]).json() == {"mode": "live"}


def test_turning_off_cancels_at_the_broker_through_the_tick(lw: Live, web: TestClient) -> None:
    ready(lw)
    assert turn_on(web, web.get("/api/mode").json()["preview"]["hash"]).json() == {"mode": "live"}
    lw.sync("2026-07-01 08:29")
    assert lw.check("2026-07-01 08:30")["result"] == "rebalance"
    lw.fake.fill_mode = "open"
    lw.sync("2026-07-01 09:05")
    mode = web.get("/api/mode").json()
    cancel = mode["offPreview"]["cancel"]
    assert [(o["side"], o["market"]) for o in cancel] == [("buy", "KR")]
    lw.at("2026-07-01 09:06")
    off = web.post("/api/mode/paper").json()
    assert off["mode"] == "paper"
    assert [o["instrument"]["id"] for o in off["cancelPending"]] == ["KR:069500"]
    assert off["cancelFailed"] == []
    lw.fake.refuse["cancel"] = (422, "cancel-restricted", {})
    lw.sync("2026-07-01 09:07")
    shell = web.get("/api/shell").json()
    assert shell["status"] == {"kind": "cancel-failed", "count": 1}
    assert shell["banner"] == {
        "kind": "cancel-failed",
        "market": "KR",
        "side": "buy",
        "link": "mode",
    }
    health = web.get("/api/health").json()
    todo = next(t for t in health["todos"] if t["kind"] == "cancel-failed")
    assert todo["facts"] == {"at": "2026-07-01T09:05:00+09:00", "market": "KR", "side": "buy"}
    mode = web.get("/api/mode").json()
    assert [o["status"] for o in mode["cancelFailed"]] == ["pending"]
    assert mode["canTurnOn"] == {"ok": False, "cause": "cancel-pending"}
    assert mode["liveOff"] == {
        "from": "2026-06-30",
        "to": "2026-07-01",
        "offAt": "2026-07-01T09:06:00+09:00",
    }
    retry = web.post("/api/mode/cancel-retry").json()
    assert retry["cancelFailed"] == []
    assert len(retry["cancelPending"]) == 1
    del lw.fake.refuse["cancel"]
    lw.sync("2026-07-01 09:10")
    assert web.get("/api/shell").json()["status"]["kind"] != "cancel-failed"
    assert web.get("/api/mode").json()["cancelPending"] is None


def test_health_shows_the_live_todos(
    lw: Live, web: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready(lw)
    assert turn_on(web, web.get("/api/mode").json()["preview"]["hash"]).json() == {"mode": "live"}
    lw.sync("2026-07-01 08:29")
    lw.check("2026-07-01 08:30")
    lw.fake.refuse["069500"] = (422, "prerequisite-required", {})
    lw.sync("2026-07-01 09:10")
    lw.stages()
    health = web.get("/api/health").json()
    kinds = {t["kind"]: t for t in health["todos"]}
    assert kinds["order-rejected"]["facts"]["reason"] == "broker-rejected"
    # No conversion to make by hand (D47): the mix shows beside the to-dos, never among them.
    assert set(kinds) == {"order-rejected"}
    assert health["summary"]["todoCount"] == 1
    assert health["liveCash"] == {
        "newMoney": None,
        "fxSuggestion": {
            "direction": "krw-usd",
            "krw": 5000000,
            "usd": 3591.95,
            "rate": 1392.0,
            "now": {"kr": 100.0, "us": 0.0},
            "target": {"kr": 50.0, "us": 50.0},
        },
    }
    balance = next(s for s in health["sources"] if s["id"] == "toss-balance")
    assert balance["basis"] == "match"
    # The key goes away while live: the link is red and named.
    monkeypatch.delenv("AUTOTRADE_LIVE_ORDERS")
    lw.sync("2026-07-01 09:15")
    health = web.get("/api/health").json()
    link = next(t for t in health["todos"] if t["kind"] == "toss-link")
    assert (link["severity"], link["facts"], link["action"]) == (
        "red",
        {"cause": "env-off"},
        {"kind": "manual"},
    )
    source = next(s for s in health["sources"] if s["id"] == "toss-link")
    assert source["state"] == "stale"


def test_a_mismatch_is_a_red_manual_todo(lw: Live, web: TestClient) -> None:
    ready(lw)
    assert turn_on(web, web.get("/api/mode").json()["preview"]["hash"]).json() == {"mode": "live"}
    lw.fake.hold("069500", D("3"), D("32000"))
    lw.sync("2026-07-01 08:00")
    lw.reconcile()
    health = web.get("/api/health").json()
    todo = next(t for t in health["todos"] if t["kind"] == "broker-mismatch")
    assert todo["facts"] == {
        "reason": "positions",
        "instrument": "KOSPI200 ETF",
        "ledgerQty": "0",
        "brokerQty": "3",
        "count": 1,
    }
    assert todo["effect"] == "orders-zero-live-blocked"
    # One card for one cause: the link's own to-do does not repeat the mismatch.
    assert [t["kind"] for t in health["todos"]] == ["broker-mismatch"]
    source = next(s for s in health["sources"] if s["id"] == "toss-balance")
    assert (source["state"], source["basis"]) == ("stale", "mismatch")
    assert web.get("/api/shell").json()["status"]["kind"] == "todo"


def test_the_key_expiry_warns_when_the_owner_gave_it(lw: Live, web: TestClient) -> None:
    from dataclasses import replace
    from datetime import date

    lw.ctx = replace(lw.ctx, cfg=replace(lw.cfg, toss_key_expires=date(2026, 7, 10)))
    ready(lw)
    health = web.get("/api/health").json()
    todo = next(t for t in health["todos"] if t["kind"] == "toss-expiring")
    assert todo["facts"] == {"expiresAt": "2026-07-10", "daysLeft": 10}
    link = next(s for s in health["sources"] if s["id"] == "toss-link")
    assert (link["state"], link["basis"], link["extra"]["daysLeft"]) == ("late", "2026-07-10", 10)
