"""What the screens show of the live link (autotrade/PHASE3.md 2.7): the health screen's Toss rows
and to-dos, the orders a 'live off' could not cancel, and the header's counts. And what they show
of the live ledger's money (D47·D48): the conversion that would bring the mix to the targets and
the owner's money that waits for the next weekday's check (information, never a to-do).

All of it comes from what the tick recorded (broker_status, broker_orders, the live ledger); the
web service never reaches Toss. Live to-dos show whatever the mode is: after 'live off' a cancel
that failed must stay on the header until it is dealt with.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from autotrade.api.views import fmt
from autotrade.api.views.orders import order_json
from autotrade.config import Config
from autotrade.db import live_repo, repo
from autotrade.domain.currency_mix import FxSuggestion
from autotrade.domain.instruments import Currency, Instrument
from autotrade.domain.planner import FxDirection
from autotrade.engine import live
from autotrade.engine.live import KEY_EXPIRY_WARN_DAYS, LinkCheck

if TYPE_CHECKING:
    from autotrade.api.views.context import LedgerContext

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
        # A key the owner said expires within two weeks reads 'late' ('만료 12일 전').
        soon = check.days_left is not None and check.days_left <= KEY_EXPIRY_WARN_DAYS
        state = "late" if soon else "fresh"
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


def _name(conn: sqlite3.Connection, instrument_id: str) -> str:
    """The display name of an instrument the to-do names (its id when the rules never had it)."""
    try:
        return repo.get_instrument(conn, instrument_id).name
    except repo.NotFoundError:
        return instrument_id


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
    if check.cause == "mismatch":
        return None  # the broker-mismatch card says it, with what differs
    manual = check.cause in MANUAL_CAUSES
    return {
        "id": "toss-link",
        "severity": "red" if on else "yellow",
        "kind": "toss-link",
        "facts": {"cause": check.cause},
        "action": {"kind": "manual"}
        if manual
        else {"kind": "auto-retry", "at": fmt.iso(now + TICK)},
        "effect": "orders-zero-live-blocked",  # no live order goes while it lasts
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
                    "instrument": _name(conn, str(first.get("instrument_id"))),
                    "ledgerQty": str(first.get("ledger")),
                    "brokerQty": str(first.get("broker")),
                    "count": len(positions),
                }
            )
        elif detail.get("instrument_id"):
            facts["instrument"] = _name(conn, str(detail["instrument_id"]))
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
    return out


def fx_suggestion_json(found: FxSuggestion | None) -> dict[str, Any] | None:
    """CONTRACT FxSuggestion (D47): the conversion that would bring the mix to the targets."""
    if found is None:
        return None
    kr, us = fmt.allocate_pct1([found.mix.kr_krw, found.mix.us_krw])
    target_kr = found.mix.target_kr
    return {
        "direction": "krw-usd" if found.direction is FxDirection.KRW_TO_USD else "usd-krw",
        "krw": fmt.krw(found.krw),
        "usd": fmt.usd(found.usd),
        "rate": fmt.rate(found.rate),
        "now": {"kr": float(kr), "us": float(us)},
        "target": {"kr": fmt.pct1(target_kr), "us": fmt.pct1(1 - target_kr)},
    }


def new_money_json(amounts: Mapping[Currency, Decimal], usable_from: datetime) -> dict[str, Any]:
    """CONTRACT NewMoneyWait (D48): the owner's money of today, and when it is used."""
    return {
        "krw": fmt.krw(amounts.get(Currency.KRW, Decimal(0))),
        "usd": fmt.usd(amounts.get(Currency.USD, Decimal(0))),
        "from": fmt.iso(usable_from),
    }


def live_cash(ctx: LedgerContext) -> dict[str, Any] | None:
    """CONTRACT LiveCash: what the mode and health screens show of the live ledger's money while
    live is on (the waiting new money, the conversion to the targets). None otherwise."""
    if not ctx.live or not ctx.started or live.mode_of(ctx.conn) != live.LIVE:
        return None
    return {
        "newMoney": new_money_json(ctx.new_money, ctx.new_money_from) if ctx.new_money else None,
        "fxSuggestion": fx_suggestion_json(ctx.fx_suggestion),
    }


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
