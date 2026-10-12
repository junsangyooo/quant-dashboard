"""What the screens show of the live link (autotrade/PHASE3.md 2.7): the health screen's Toss rows
and to-dos, the orders a 'live off' could not cancel, and the header's counts.

All of it comes from what the tick recorded (broker_status, broker_orders, the live ledger); the
web service never reaches Toss. Live to-dos show whatever the mode is: after 'live off' a cancel
that failed must stay on the header until it is dealt with.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.orders import order_json
from autotrade.config import Config
from autotrade.db import live_repo, repo
from autotrade.domain.instruments import Instrument
from autotrade.engine import live
from autotrade.engine.live import KEY_EXPIRY_WARN_DAYS, LinkCheck

TICK = timedelta(minutes=5)  # the next tick looks again (deploy/autotrade.cron)
# Causes a person must fix on the server or in WTS; the others pass on their own (next tick).
MANUAL_CAUSES = frozenset(
    {"env-off", "no-key", "auth", "ip", "account", "not-tradable", "conflict", "never", "expired"}
)


def _age(now: datetime, since: datetime | None, cfg: Config) -> float:
    if since is None:
        return 0.0
    span = cfg.broker_max_age.total_seconds()
    return round(max(0.0, (now - since).total_seconds()) / span, 2)


def link_source(conn: sqlite3.Connection, cfg: Config, now: datetime) -> dict[str, Any] | None:
    """The 'toss-link' row: is the tick's last look at Toss good enough for live orders.
    basis = the client key's expiry when the owner gave it (the API has none, PHASE3.md 1.6)."""
    if not live.relevant(conn):
        return None
    check = live.link_check(conn, cfg, now)
    status = live_repo.get_status(conn)
    on = live.mode_of(conn) == live.LIVE
    if check.ok:
        state = "fresh"
    elif check.cause == "old":
        state = "late"
    elif check.cause in ("env-off", "never") and not on:
        state = "unknown"
    else:
        state = "stale"
    extra: dict[str, Any] = {}
    if check.cause:
        extra["cause"] = check.cause
    if check.account_tail:
        extra["account"] = check.account_tail
    if check.days_left is not None:
        extra["daysLeft"] = check.days_left
    return {
        "id": "toss-link",
        "state": state,
        "basis": None if check.key_expires is None else fmt.day(check.key_expires),
        "receivedAt": None if status is None or status.ok_at is None else fmt.iso(status.ok_at),
        "cadence": "per-check",
        "age": _age(now, None if status is None else status.checked_at, cfg),
        "extra": extra,
    }


def balance_source(conn: sqlite3.Connection, cfg: Config, now: datetime) -> dict[str, Any] | None:
    """The 'toss-balance' row: did the live ledger match the account at the last look."""
    if repo.start_event(conn, live.LIVE) is None:
        return None
    status = live_repo.get_status(conn)
    at = None if status is None else status.reconciled_at
    result = None if status is None else status.reconcile_state
    if result == "mismatch":
        state = "stale"
    elif result == "match" and at is not None and now - at <= cfg.broker_max_age:
        state = "fresh"
    elif result in ("match", "busy"):
        state = "late"
    else:
        state = "unknown"
    return {
        "id": "toss-balance",
        "state": state,
        "basis": result if result in ("match", "mismatch") else None,
        "receivedAt": None if at is None else fmt.iso(at),
        "cadence": "per-check",
        "age": _age(now, at, cfg),
    }


def sources(conn: sqlite3.Connection, cfg: Config, now: datetime) -> list[dict[str, Any]]:
    return [s for s in (link_source(conn, cfg, now), balance_source(conn, cfg, now)) if s]


def _instruments(conn: sqlite3.Connection) -> dict[str, Instrument]:
    return dict(live.rule_instruments(conn))


def order_of(conn: sqlite3.Connection, order_id: int) -> dict[str, Any]:
    """One live order as CONTRACT Order (approximate until it fills)."""
    order = repo.get_order(conn, order_id)
    stage = repo.get_stage(conn, order.stage_id)
    fill = repo.fill_of_order(conn, order_id)
    instruments = _instruments(conn)
    if order.instrument_id is not None and order.instrument_id not in instruments:
        instruments[order.instrument_id] = repo.get_instrument(conn, order.instrument_id)
    fills = {} if fill is None else {order_id: fill}
    out = order_json([order], fills, {stage.stage_id: stage}, instruments, "live")
    if out.get("status") == "failed":
        # A cancel request is waiting at the broker, not a failure of the order itself.
        out["status"] = "pending"
        out.pop("failure", None)
    return out


def cancel_failed_orders(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [order_of(conn, r.order_id) for r in live.cancel_failed(conn)]


def cancel_pending_orders(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    return [order_of(conn, r.order_id) for r in live.cancel_pending(conn)]


def _link_todo(
    check: LinkCheck, on: bool, started: bool, env: bool, now: datetime
) -> dict[str, Any] | None:
    if check.ok or check.cause is None:
        return None
    # Before anything was asked of the link, its absence is not a to-do.
    if not (on or started or env):
        return None
    if check.cause in ("env-off", "never") and not on:
        return None
    manual = check.cause in MANUAL_CAUSES
    return {
        "id": "toss-link",
        "severity": "red" if on else "yellow",
        "kind": "toss-link",
        "facts": {"cause": check.cause},
        "action": {"kind": "manual"}
        if manual
        else {"kind": "auto-retry", "at": fmt.iso(now + TICK)},
        "effect": "orders-and-reconcile-stop",
    }


def todos(conn: sqlite3.Connection, cfg: Config, now: datetime) -> list[dict[str, Any]]:
    """The live ledger's to-dos, newest worries first (CONTRACT HealthResponse.todos)."""
    out: list[dict[str, Any]] = []
    on = live.mode_of(conn) == live.LIVE
    started = repo.start_event(conn, live.LIVE) is not None
    status = live_repo.get_status(conn)
    env = status is not None and status.env_live
    for row in live.cancel_failed(conn):
        order = repo.get_order(conn, row.order_id)
        out.append(
            {
                "id": f"cancel-failed:{row.order_id}",
                "severity": "red",
                "kind": "cancel-failed",
                "facts": {
                    "at": fmt.iso(repo.get_stage(conn, order.stage_id).due_at),
                    "market": order.market,
                    "side": order.side,
                },
                "action": {"kind": "manual"},
                "effect": "other",
            }
        )
    if started and status is not None and status.reconcile_state == "mismatch":
        detail = status.reconcile_detail
        facts: dict[str, Any] = {"reason": str(detail.get("reason") or "other")}
        positions = detail.get("positions")
        if isinstance(positions, list) and positions:
            first = positions[0]
            facts.update(
                {
                    "instrument": str(first.get("instrument_id")),
                    "ledgerQty": str(first.get("ledger")),
                    "brokerQty": str(first.get("broker")),
                    "count": len(positions),
                }
            )
        if detail.get("currency"):
            facts["currency"] = str(detail["currency"])
        out.append(
            {
                "id": "broker-mismatch",
                "severity": "red",
                "kind": "broker-mismatch",
                "facts": facts,
                "action": {"kind": "manual"},
                "effect": "orders-zero-live-blocked",
            }
        )
    for row in live.unknown_orders(conn):
        order = repo.get_order(conn, row.order_id)
        out.append(
            {
                "id": f"broker-mismatch:order:{row.order_id}",
                "severity": "red",
                "kind": "broker-mismatch",
                "facts": {"reason": "order-unknown", "market": order.market, "side": order.side},
                "action": {"kind": "manual"},
                "effect": "orders-zero-live-blocked",
            }
        )
    check = live.link_check(conn, cfg, now)
    link = _link_todo(check, on, started, env, now)
    if link is not None:
        out.append(link)
    if check.days_left is not None and check.days_left <= KEY_EXPIRY_WARN_DAYS:
        out.append(
            {
                "id": "toss-expiring",
                "severity": "yellow",
                "kind": "toss-expiring",
                "facts": {
                    "expiresAt": fmt.day(check.key_expires) if check.key_expires else "",
                    "daysLeft": check.days_left,
                },
                "action": {"kind": "manual"},
                "effect": "orders-and-reconcile-stop",
            }
        )
    for fx in live.fx_todos(conn, now):
        order = fx.order
        to_usd = fx.direction.value == "krw_to_usd"
        received = order.est_received or Decimal(0)
        facts = {
            "direction": "krw-usd" if to_usd else "usd-krw",
            "krw": fmt.krw(order.est_amount if to_usd else received),
            "usd": fmt.usd(received if to_usd else order.est_amount),
            "rate": fmt.rate(order.est_rate or Decimal(0)),
            "orderId": order.order_id,
        }
        if fx.by is not None:
            facts["by"] = fmt.iso(fx.by)
        out.append(
            {
                "id": f"fx-manual:{order.order_id}",
                "severity": "yellow",
                "kind": "fx-manual",
                "facts": facts,
                "action": {"kind": "manual"},
                "effect": "other",
            }
        )
    return out


def header_counts(conn: sqlite3.Connection, cfg: Config, now: datetime) -> tuple[int, int]:
    """(manual live to-dos, cancels that failed) for the header (CONTRACT ShellResponse)."""
    items = todos(conn, cfg, now)
    manual = sum(
        1 for t in items if t["action"]["kind"] == "manual" and t["kind"] != "cancel-failed"
    )
    cancels = sum(1 for t in items if t["kind"] == "cancel-failed")
    return manual, cancels


def live_since(conn: sqlite3.Connection) -> datetime | None:
    periods = live.live_periods(conn)
    if live.mode_of(conn) == live.LIVE and periods and periods[-1][1] is None:
        return periods[-1][0]
    return None
