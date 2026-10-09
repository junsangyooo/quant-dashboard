"""Stage and Order objects (CONTRACT.md 공통 타입) built from plans, orders and fills.

- One Order per instrument (or conversion) of a stage: retries of the same order are folded
  into it. A pending retry shows as 'failed' with failure.retryAt ('다시 10/08 22:30'); a
  second failure or a cancelled order shows failure.manual ('직접 할 일').
- Stages are grouped by kind in the order sell -> fx -> buy, across markets ('매수(⏳ 22:30)'
  holds the Korean buy at 09:05 and the US buy at 22:30). Stages without orders are left out.
- A conversion order has market 'KR' (it is a won-side operation at the broker) and a
  `direction` ('krw-usd' | 'usd-krw').
- An order that failed and was sent again keeps its failure on the day it failed ('failed',
  `failure.reason`, `failure.retryAt`) and carries the outcome of the retry once it is known:
  `retried: {at, status: 'filled' | 'failed'}` ('9/15 다시 · 체결'). Such an order is settled
  when the retry filled (`settled`), and waits for nothing.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.refs import instrument as instrument_json
from autotrade.db import repo
from autotrade.db.models import FillRow, OrderRow, StageRow
from autotrade.domain.instruments import Currency, Instrument

STAGE_ORDER = ("sell", "fx", "buy")


def _money(currency: Currency, amount: Any) -> dict[str, Any]:
    if currency is Currency.KRW:
        return {"amountKrw": fmt.krw(amount)}
    return {"amountUsd": fmt.usd(amount)}


def _price(currency: Currency, price: Any) -> float | int:
    return fmt.krw(price) if currency is Currency.KRW else fmt.usd(price)


def order_json(
    attempts: list[OrderRow],
    fills: Mapping[int, FillRow],
    stages: Mapping[int, StageRow],
    instruments: Mapping[str, Instrument],
    executor: str,
) -> dict[str, Any]:
    latest = attempts[-1]
    first = attempts[0]
    stage = stages[latest.stage_id]
    fill = fills.get(latest.order_id)
    market = "KR" if latest.side == "fx" else latest.market
    out: dict[str, Any] = {"id": str(first.order_id), "market": market, "side": latest.side}

    if latest.side == "fx":
        krw_to_usd = latest.fx_direction == "krw_to_usd"
        out["direction"] = "krw-usd" if krw_to_usd else "usd-krw"
        if fill is not None and fill.received is not None and fill.krw_rate is not None:
            krw_amount = fill.gross if krw_to_usd else fill.received
            usd_amount = fill.received if krw_to_usd else fill.gross
            fx_rate = fill.krw_rate
        else:
            received = latest.est_received or latest.est_amount
            krw_amount = latest.est_amount if krw_to_usd else received
            usd_amount = received if krw_to_usd else latest.est_amount
            fx_rate = latest.est_rate or Decimal(0)
            out["approx"] = True
        out["fx"] = {
            "krw": fmt.krw(krw_amount),
            "usd": fmt.usd(usd_amount),
            "rate": fmt.rate(fx_rate),
        }
        out["amountKrw"] = fmt.krw(krw_amount)
        out["amountUsd"] = fmt.usd(usd_amount)
    else:
        inst = instruments[latest.instrument_id or ""]
        out["instrument"] = instrument_json(inst)
        if fill is not None and fill.price is not None:
            out["qty"] = fill.qty
            out["price"] = _price(inst.currency, fill.price)
            out.update(_money(inst.currency, fill.gross))
            fee: dict[str, Any] = {"krw": fmt.krw(fill.fee_krw)}
            if inst.currency is Currency.USD:
                fee["usd"] = fmt.usd(fill.fee)
            out["fee"] = fee
        else:
            out["qty"] = latest.qty
            out["price"] = _price(inst.currency, latest.est_price or 0)
            out["approx"] = True
            out.update(_money(inst.currency, latest.est_amount))
            out["fee"] = (
                {"krw": fmt.krw(latest.est_fee)}
                if inst.currency is Currency.KRW
                else {"usd": fmt.usd(latest.est_fee)}
            )

    failed = [a for a in attempts if a.status in ("failed", "cancelled")]
    if fill is not None and not failed:
        out["status"] = "filled"
        out["at"] = fmt.iso(fill.filled_at)
        out["fill"] = executor
        return out
    if latest.status == "pending" and not failed:
        out["at"] = fmt.iso(stage.due_at)
        out["status"] = "pending"
        return out
    out["status"] = "failed"
    first_failure = failed[0] if failed else latest
    out["at"] = fmt.iso(first_failure.executed_at or stage.due_at)
    reason = first_failure.failure_reason or "other"
    failure: dict[str, Any] = {"reason": reason if reason != "cancel-failed" else "other"}
    if len(attempts) > 1 or latest.status == "pending":
        failure["retryAt"] = fmt.iso(first_failure.retry_at or stage.due_at)
    if fill is not None:  # the retry filled: '9/15 다시 · 체결'
        out["fill"] = executor
        out["retried"] = {"at": fmt.iso(fill.filled_at), "status": "filled"}
    elif latest is not first_failure and latest.status in ("failed", "cancelled"):
        out["retried"] = {"at": fmt.iso(latest.executed_at or stage.due_at), "status": "failed"}
    if fill is None and latest.status != "pending":
        failure["manual"] = True
    out["failure"] = failure
    return out


def settled(order: Mapping[str, Any]) -> bool:
    """Filled, or failed and filled on a retry: nothing left to do for it."""
    retried = order.get("retried")
    return order.get("status") == "filled" or (
        isinstance(retried, Mapping) and retried.get("status") == "filled"
    )


def waiting_retry(order: Mapping[str, Any]) -> bool:
    """Failed, and sent again later ('다시 10/08 22:30'); the retry has no outcome yet."""
    failure = order.get("failure")
    return (
        isinstance(failure, Mapping)
        and bool(failure.get("retryAt"))
        and "retried" not in order
        and not failure.get("manual")
    )


def plan_stages(
    conn: sqlite3.Connection, plan_id: int, instruments: Mapping[str, Instrument], executor: str
) -> list[dict[str, Any]]:
    orders = repo.orders_of_plan(conn, plan_id)
    fills = {f.order_id: f for f in repo.fills_of_plan(conn, plan_id)}
    stages = {s.stage_id: s for s in repo.stages_of(conn, plan_id)}
    known = dict(instruments)  # the AI rule trades companies the caller may not list
    for o in orders:
        if o.instrument_id is not None and o.instrument_id not in known:
            known[o.instrument_id] = repo.get_instrument(conn, o.instrument_id)
    instruments = known
    groups: dict[tuple[str, str, str], list[OrderRow]] = {}
    for o in orders:
        key = (o.stage, o.market, o.instrument_id or o.fx_direction or "fx")
        groups.setdefault(key, []).append(o)
    by_kind: dict[str, list[dict[str, Any]]] = {}
    times: dict[str, list[tuple[str, datetime]]] = {}
    for (kind, _, _), attempts in groups.items():
        attempts.sort(key=lambda a: a.attempt)
        order = order_json(attempts, fills, stages, instruments, executor)
        by_kind.setdefault(kind, []).append(order)
        latest = attempts[-1]
        fill = fills.get(latest.order_id)
        when = fill.filled_at if fill is not None else stages[latest.stage_id].due_at
        times.setdefault(kind, []).append((order["status"], when))
    out: list[dict[str, Any]] = []
    for kind in STAGE_ORDER:
        if kind not in by_kind:
            continue
        orders_json = sorted(by_kind[kind], key=lambda o: str(o["at"]))
        statuses = [o["status"] for o in orders_json]
        if "failed" in statuses:
            status = "failed"
        elif "pending" in statuses:
            status = "pending"
        else:
            status = "done"
        open_times = [t for s, t in times[kind] if s != "filled"]
        at = min(open_times) if open_times else max(t for _, t in times[kind])
        out.append({"kind": kind, "status": status, "at": fmt.iso(at), "orders": orders_json})
    return out


def stages_mini(stages: list[dict[str, Any]]) -> list[str]:
    return [str(s["status"]) for s in stages]
