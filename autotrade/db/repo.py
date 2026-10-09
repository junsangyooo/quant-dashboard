"""Repository functions: every read and write of data/autotrade.db goes through here.

None of these commit; the caller owns the transaction (autotrade/db/connection.py).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from autotrade.db.connection import dumps
from autotrade.db.models import (
    EventRow,
    FillRow,
    FreshnessRow,
    LedgerRow,
    OrderRow,
    PlanRow,
    RuleRow,
    RunRow,
    SnapshotRow,
    StageRow,
    bar_from_row,
    fx_from_row,
    instrument_from_row,
)
from autotrade.domain.cash import CashPart, Purpose, WithdrawWait
from autotrade.domain.instruments import Currency, Instrument
from autotrade.domain.ledger import LedgerState, Position
from autotrade.domain.money import ZERO
from autotrade.market.types import PAIR_USDKRW, Bar, FxQuote
from autotrade.timeutil import to_iso


class NotFoundError(LookupError):
    pass


def _one(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(sql, params).fetchone()
    return row


def _all(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, params).fetchall())


def _lastrowid(cur: sqlite3.Cursor) -> int:
    if cur.lastrowid is None:
        raise RuntimeError("insert returned no row id")
    return int(cur.lastrowid)


# ── settings ─────────────────────────────────────────────────────────────────────────────


def get_setting(conn: sqlite3.Connection, key: str) -> str | None:
    row = _one(conn, "SELECT value FROM settings WHERE key = ?", (key,))
    return None if row is None else str(row["value"])


def set_setting(conn: sqlite3.Connection, key: str, value: str, at: datetime) -> None:
    conn.execute(
        "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value, to_iso(at)),
    )


def ensure_setting(conn: sqlite3.Connection, key: str, value: str, at: datetime) -> str:
    """Write the default only when the key is missing; return the stored value."""
    current = get_setting(conn, key)
    if current is None:
        set_setting(conn, key, value, at)
        return value
    return current


# ── ledgers ──────────────────────────────────────────────────────────────────────────────


def ensure_ledger(conn: sqlite3.Connection, ledger_id: str, name: str, at: datetime) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO ledgers (ledger_id, name, created_at, updated_at)"
        " VALUES (?, ?, ?, ?)",
        (ledger_id, name, to_iso(at), to_iso(at)),
    )
    for currency in Currency:
        conn.execute(
            "INSERT OR IGNORE INTO cash (ledger_id, currency, amount, updated_at)"
            " VALUES (?, ?, '0', ?)",
            (ledger_id, currency.value, to_iso(at)),
        )


def get_ledger(conn: sqlite3.Connection, ledger_id: str) -> LedgerRow:
    row = _one(conn, "SELECT * FROM ledgers WHERE ledger_id = ?", (ledger_id,))
    if row is None:
        raise NotFoundError(f"ledger {ledger_id}")
    return LedgerRow.from_row(row)


def mark_ledger_started(
    conn: sqlite3.Connection, ledger_id: str, start_date: date, amount: Decimal, at: datetime
) -> None:
    conn.execute(
        "UPDATE ledgers SET started_at = ?, start_date = ?, start_amount = ?, updated_at = ?"
        " WHERE ledger_id = ?",
        (to_iso(at), start_date.isoformat(), str(amount), to_iso(at), ledger_id),
    )


def load_state(conn: sqlite3.Connection, ledger_id: str) -> LedgerState:
    cash = {
        Currency(str(r["currency"])): Decimal(str(r["amount"]))
        for r in _all(conn, "SELECT currency, amount FROM cash WHERE ledger_id = ?", (ledger_id,))
    }
    positions = {
        str(r["instrument_id"]): Position(
            instrument_id=str(r["instrument_id"]),
            currency=Currency(str(r["currency"])),
            qty=int(r["qty"]),
            cost_native=Decimal(str(r["cost_native"])),
            cost_krw=Decimal(str(r["cost_krw"])),
        )
        for r in _all(conn, "SELECT * FROM positions WHERE ledger_id = ?", (ledger_id,))
    }
    led = _one(conn, "SELECT * FROM ledgers WHERE ledger_id = ?", (ledger_id,))
    if led is None:
        raise NotFoundError(f"ledger {ledger_id}")
    for currency in Currency:
        cash.setdefault(currency, ZERO)
    return LedgerState(
        cash=cash,
        positions=positions,
        realized_krw=Decimal(str(led["realized_krw"])),
        fees_krw=Decimal(str(led["fees_krw"])),
        contributions_krw=Decimal(str(led["contributions_krw"])),
        income_krw=Decimal(str(led["income_krw"])),
    )


def save_state(conn: sqlite3.Connection, ledger_id: str, state: LedgerState, at: datetime) -> None:
    stamp = to_iso(at)
    for currency in Currency:
        conn.execute(
            "INSERT INTO cash (ledger_id, currency, amount, updated_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(ledger_id, currency) DO UPDATE SET amount = excluded.amount,"
            " updated_at = excluded.updated_at",
            (ledger_id, currency.value, str(state.cash_of(currency)), stamp),
        )
    conn.execute("DELETE FROM positions WHERE ledger_id = ?", (ledger_id,))
    for pos in state.positions.values():
        conn.execute(
            "INSERT INTO positions (ledger_id, instrument_id, currency, qty, cost_native,"
            " cost_krw, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                ledger_id,
                pos.instrument_id,
                pos.currency.value,
                pos.qty,
                str(pos.cost_native),
                str(pos.cost_krw),
                stamp,
            ),
        )
    conn.execute(
        "UPDATE ledgers SET realized_krw = ?, fees_krw = ?, contributions_krw = ?,"
        " income_krw = ?, updated_at = ? WHERE ledger_id = ?",
        (
            str(state.realized_krw),
            str(state.fees_krw),
            str(state.contributions_krw),
            str(state.income_krw),
            stamp,
            ledger_id,
        ),
    )


# ── instruments and rules ────────────────────────────────────────────────────────────────


def upsert_instrument(conn: sqlite3.Connection, inst: Instrument, at: datetime) -> None:
    conn.execute(
        "INSERT INTO instruments (instrument_id, market, currency, kind, ticker, name,"
        " yahoo_symbol, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(instrument_id) DO UPDATE SET name = excluded.name,"
        " yahoo_symbol = excluded.yahoo_symbol, updated_at = excluded.updated_at",
        (
            inst.instrument_id,
            inst.market.value,
            inst.currency.value,
            inst.kind.value,
            inst.ticker,
            inst.name,
            inst.yahoo_symbol,
            to_iso(at),
        ),
    )


def get_instrument(conn: sqlite3.Connection, instrument_id: str) -> Instrument:
    row = _one(conn, "SELECT * FROM instruments WHERE instrument_id = ?", (instrument_id,))
    if row is None:
        raise NotFoundError(f"instrument {instrument_id}")
    return instrument_from_row(row)


def upsert_rule(
    conn: sqlite3.Connection,
    rule_id: str,
    name: str,
    kind: str,
    definition: Mapping[str, Any],
    at: datetime,
) -> None:
    conn.execute(
        "INSERT INTO rules (rule_id, name, kind, definition, updated_at) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(rule_id) DO UPDATE SET name = excluded.name, kind = excluded.kind,"
        " definition = excluded.definition, updated_at = excluded.updated_at",
        (rule_id, name, kind, dumps(dict(definition)), to_iso(at)),
    )


def get_rule(conn: sqlite3.Connection, rule_id: str) -> RuleRow:
    row = _one(conn, "SELECT * FROM rules WHERE rule_id = ?", (rule_id,))
    if row is None:
        raise NotFoundError(f"rule {rule_id}")
    return RuleRow.from_row(row)


def enabled_rules(conn: sqlite3.Connection) -> list[RuleRow]:
    return [
        RuleRow.from_row(r)
        for r in _all(conn, "SELECT * FROM rules WHERE enabled = 1 ORDER BY rule_id")
    ]


# ── pending cash ─────────────────────────────────────────────────────────────────────────

DERIVED_PURPOSES = (Purpose.BUY_WAIT.value, Purpose.SUB_SHARE.value, Purpose.NEW.value)


def add_withdraw_wait(
    conn: sqlite3.Connection,
    ledger_id: str,
    currency: Currency,
    amount: Decimal,
    until: date,
    at: datetime,
) -> int:
    cur = conn.execute(
        "INSERT INTO pending_cash (ledger_id, currency, purpose, amount, until_date, updated_at)"
        " VALUES (?, ?, 'withdraw_wait', ?, ?, ?)",
        (ledger_id, currency.value, str(amount), until.isoformat(), to_iso(at)),
    )
    return _lastrowid(cur)


def withdraw_waits(conn: sqlite3.Connection, ledger_id: str) -> list[WithdrawWait]:
    return [
        WithdrawWait(
            currency=Currency(str(r["currency"])),
            amount=Decimal(str(r["amount"])),
            until=date.fromisoformat(str(r["until_date"])),
        )
        for r in _all(
            conn,
            "SELECT * FROM pending_cash WHERE ledger_id = ? AND purpose = 'withdraw_wait'"
            " ORDER BY pending_id",
            (ledger_id,),
        )
    ]


def expire_withdraw_waits(conn: sqlite3.Connection, ledger_id: str, today: date) -> int:
    """Release withdraw waits whose last day has passed (인계 14). Returns how many."""
    cur = conn.execute(
        "DELETE FROM pending_cash WHERE ledger_id = ? AND purpose = 'withdraw_wait'"
        " AND until_date < ?",
        (ledger_id, today.isoformat()),
    )
    return int(cur.rowcount)


def replace_cash_parts(
    conn: sqlite3.Connection, ledger_id: str, parts: Iterable[CashPart], at: datetime
) -> None:
    """Rewrite the derived parts (buy_wait, sub_share, new); withdraw waits are inputs."""
    conn.execute(
        f"DELETE FROM pending_cash WHERE ledger_id = ? AND purpose IN ({','.join('?' * 3)})",
        (ledger_id, *DERIVED_PURPOSES),
    )
    for p in parts:
        if p.purpose is Purpose.WITHDRAW_WAIT:
            continue
        conn.execute(
            "INSERT INTO pending_cash (ledger_id, currency, purpose, instrument_id, amount,"
            " updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (
                ledger_id,
                p.currency.value,
                p.purpose.value,
                p.instrument_id,
                str(p.amount),
                to_iso(at),
            ),
        )


def cash_parts(conn: sqlite3.Connection, ledger_id: str) -> list[CashPart]:
    return [
        CashPart(
            currency=Currency(str(r["currency"])),
            purpose=Purpose(str(r["purpose"])),
            amount=Decimal(str(r["amount"])),
            instrument_id=None if r["instrument_id"] is None else str(r["instrument_id"]),
            until=None if r["until_date"] is None else date.fromisoformat(str(r["until_date"])),
        )
        for r in _all(
            conn, "SELECT * FROM pending_cash WHERE ledger_id = ? ORDER BY pending_id", (ledger_id,)
        )
    ]


# ── runs ─────────────────────────────────────────────────────────────────────────────────


def insert_run(
    conn: sqlite3.Connection,
    ledger_id: str,
    job: str,
    run_date: date,
    started_at: datetime,
    attempt: int = 1,
) -> int:
    cur = conn.execute(
        "INSERT INTO runs (ledger_id, job, run_date, attempt, started_at) VALUES (?, ?, ?, ?, ?)",
        (ledger_id, job, run_date.isoformat(), attempt, to_iso(started_at)),
    )
    return _lastrowid(cur)


def finish_run(
    conn: sqlite3.Connection,
    run_id: int,
    *,
    ended_at: datetime,
    duration_ms: int,
    result: str,
    error: str | None,
    details: Mapping[str, Any],
) -> None:
    conn.execute(
        "UPDATE runs SET ended_at = ?, duration_ms = ?, result = ?, error = ?, details = ?"
        " WHERE run_id = ?",
        (to_iso(ended_at), duration_ms, result, error, dumps(dict(details)), run_id),
    )


def runs_on(conn: sqlite3.Connection, ledger_id: str, job: str, run_date: date) -> list[RunRow]:
    return [
        RunRow.from_row(r)
        for r in _all(
            conn,
            "SELECT * FROM runs WHERE ledger_id = ? AND job = ? AND run_date = ? ORDER BY run_id",
            (ledger_id, job, run_date.isoformat()),
        )
    ]


def last_run(conn: sqlite3.Connection, ledger_id: str, job: str) -> RunRow | None:
    row = _one(
        conn,
        "SELECT * FROM runs WHERE ledger_id = ? AND job = ? ORDER BY run_id DESC LIMIT 1",
        (ledger_id, job),
    )
    return None if row is None else RunRow.from_row(row)


# Check results that looked at the free cash: it was invested or found below one share.
CASH_JUDGED_RESULTS = ("rebalance", "in-range", "already-planned")


def last_cash_check(conn: sqlite3.Connection, ledger_id: str) -> RunRow | None:
    """The latest check that judged the free cash (cash after it is a leftover, not new).

    A check that stopped earlier (stale data, a holiday, a pending withdrawal, a running plan,
    a failure) leaves new cash new: it is still to be invested at the next check.
    """
    row = _one(
        conn,
        "SELECT * FROM runs WHERE ledger_id = ? AND job = 'check'"
        f" AND result IN ({','.join('?' * len(CASH_JUDGED_RESULTS))})"
        " ORDER BY run_id DESC LIMIT 1",
        (ledger_id, *CASH_JUDGED_RESULTS),
    )
    return None if row is None else RunRow.from_row(row)


# ── plans, stages, orders ────────────────────────────────────────────────────────────────

OPEN_PLAN_STATUSES = ("in-progress", "partial-failed", "todo")


def insert_plan(
    conn: sqlite3.Connection,
    *,
    ledger_id: str,
    rule_id: str,
    plan_date: date,
    run_id: int | None,
    reason: str,
    basis: Mapping[str, Any],
    weights_before: Mapping[str, Any],
    weights_after_est: Mapping[str, Any],
    created_at: datetime,
) -> int:
    cur = conn.execute(
        "INSERT INTO plans (ledger_id, rule_id, plan_date, run_id, reason, status, basis,"
        " weights_before, weights_after_est, created_at)"
        " VALUES (?, ?, ?, ?, ?, 'in-progress', ?, ?, ?, ?)",
        (
            ledger_id,
            rule_id,
            plan_date.isoformat(),
            run_id,
            reason,
            dumps(dict(basis)),
            dumps(dict(weights_before)),
            dumps(dict(weights_after_est)),
            to_iso(created_at),
        ),
    )
    return _lastrowid(cur)


def get_plan(conn: sqlite3.Connection, plan_id: int) -> PlanRow:
    row = _one(conn, "SELECT * FROM plans WHERE plan_id = ?", (plan_id,))
    if row is None:
        raise NotFoundError(f"plan {plan_id}")
    return PlanRow.from_row(row)


def plan_on(conn: sqlite3.Connection, ledger_id: str, rule_id: str, d: date) -> PlanRow | None:
    row = _one(
        conn,
        "SELECT * FROM plans WHERE ledger_id = ? AND rule_id = ? AND plan_date = ?",
        (ledger_id, rule_id, d.isoformat()),
    )
    return None if row is None else PlanRow.from_row(row)


def open_plans(
    conn: sqlite3.Connection, ledger_id: str, rule_id: str | None = None
) -> list[PlanRow]:
    sql = (
        "SELECT * FROM plans WHERE ledger_id = ? AND status IN ('in-progress', 'partial-failed',"
        " 'todo')"
    )
    params: list[Any] = [ledger_id]
    if rule_id is not None:
        sql += " AND rule_id = ?"
        params.append(rule_id)
    return [PlanRow.from_row(r) for r in _all(conn, sql + " ORDER BY plan_id", params)]


def set_plan_status(
    conn: sqlite3.Connection, plan_id: int, status: str, completed_at: datetime | None = None
) -> None:
    conn.execute(
        "UPDATE plans SET status = ?, completed_at = ? WHERE plan_id = ?",
        (status, None if completed_at is None else to_iso(completed_at), plan_id),
    )


def insert_stage(
    conn: sqlite3.Connection,
    *,
    plan_id: int,
    seq: int,
    kind: str,
    market: str,
    due_at: datetime,
    depends_on: Sequence[int],
) -> int:
    cur = conn.execute(
        "INSERT INTO stages (plan_id, seq, kind, market, scheduled_at, due_at, status,"
        " depends_on) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)",
        (plan_id, seq, kind, market, to_iso(due_at), to_iso(due_at), dumps(list(depends_on))),
    )
    return _lastrowid(cur)


def stages_of(conn: sqlite3.Connection, plan_id: int) -> list[StageRow]:
    return [
        StageRow.from_row(r)
        for r in _all(conn, "SELECT * FROM stages WHERE plan_id = ? ORDER BY seq", (plan_id,))
    ]


def get_stage(conn: sqlite3.Connection, stage_id: int) -> StageRow:
    row = _one(conn, "SELECT * FROM stages WHERE stage_id = ?", (stage_id,))
    if row is None:
        raise NotFoundError(f"stage {stage_id}")
    return StageRow.from_row(row)


def update_stage(
    conn: sqlite3.Connection,
    stage_id: int,
    *,
    status: str | None = None,
    due_at: datetime | None = None,
    attempts: int | None = None,
    last_error: str | None = None,
    completed_at: datetime | None = None,
) -> None:
    sets: list[str] = []
    params: list[Any] = []
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if due_at is not None:
        sets.append("due_at = ?")
        params.append(to_iso(due_at))
    if attempts is not None:
        sets.append("attempts = ?")
        params.append(attempts)
    if last_error is not None:
        sets.append("last_error = ?")
        params.append(last_error)
    if completed_at is not None:
        sets.append("completed_at = ?")
        params.append(to_iso(completed_at))
    if not sets:
        return
    conn.execute(f"UPDATE stages SET {', '.join(sets)} WHERE stage_id = ?", (*params, stage_id))


def pending_stages(conn: sqlite3.Connection, ledger_id: str) -> list[StageRow]:
    return [
        StageRow.from_row(r)
        for r in _all(
            conn,
            "SELECT s.* FROM stages s JOIN plans p ON p.plan_id = s.plan_id"
            " WHERE p.ledger_id = ? AND s.status IN ('pending', 'failed')"
            " ORDER BY s.due_at, s.plan_id, s.seq",
            (ledger_id,),
        )
    ]


@dataclass(frozen=True)
class NewOrder:
    idem_key: str
    ledger_id: str
    plan_id: int
    stage_id: int
    stage: str
    market: str
    instrument_id: str | None
    side: str
    fx_direction: str | None
    currency: Currency
    qty: int | None
    est_price: Decimal | None
    est_amount: Decimal
    est_fee: Decimal
    est_rate: Decimal | None
    est_received: Decimal | None
    attempt: int = 1
    retry_of: int | None = None


def insert_order(conn: sqlite3.Connection, order: NewOrder, at: datetime) -> tuple[int, bool]:
    """Insert unless the idempotency key exists. Returns (order_id, inserted)."""
    existing = _one(conn, "SELECT order_id FROM orders WHERE idem_key = ?", (order.idem_key,))
    if existing is not None:
        return int(existing["order_id"]), False
    cur = conn.execute(
        "INSERT INTO orders (idem_key, ledger_id, plan_id, stage_id, stage, market,"
        " instrument_id, side, fx_direction, currency, qty, est_price, est_amount, est_fee,"
        " est_rate, est_received, status, attempt, retry_of, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)",
        (
            order.idem_key,
            order.ledger_id,
            order.plan_id,
            order.stage_id,
            order.stage,
            order.market,
            order.instrument_id,
            order.side,
            order.fx_direction,
            order.currency.value,
            order.qty,
            None if order.est_price is None else str(order.est_price),
            str(order.est_amount),
            str(order.est_fee),
            None if order.est_rate is None else str(order.est_rate),
            None if order.est_received is None else str(order.est_received),
            order.attempt,
            order.retry_of,
            to_iso(at),
        ),
    )
    return _lastrowid(cur), True


def get_order(conn: sqlite3.Connection, order_id: int) -> OrderRow:
    row = _one(conn, "SELECT * FROM orders WHERE order_id = ?", (order_id,))
    if row is None:
        raise NotFoundError(f"order {order_id}")
    return OrderRow.from_row(row)


def orders_of_stage(
    conn: sqlite3.Connection, stage_id: int, statuses: Sequence[str] | None = None
) -> list[OrderRow]:
    sql = "SELECT * FROM orders WHERE stage_id = ?"
    params: list[Any] = [stage_id]
    if statuses:
        sql += f" AND status IN ({','.join('?' * len(statuses))})"
        params.extend(statuses)
    return [OrderRow.from_row(r) for r in _all(conn, sql + " ORDER BY order_id", params)]


def orders_of_ledger(conn: sqlite3.Connection, ledger_id: str) -> list[OrderRow]:
    return [
        OrderRow.from_row(r)
        for r in _all(
            conn, "SELECT * FROM orders WHERE ledger_id = ? ORDER BY order_id", (ledger_id,)
        )
    ]


def pending_orders(conn: sqlite3.Connection, ledger_id: str) -> list[OrderRow]:
    return [
        OrderRow.from_row(r)
        for r in _all(
            conn,
            "SELECT * FROM orders WHERE ledger_id = ? AND status = 'pending' ORDER BY order_id",
            (ledger_id,),
        )
    ]


def mark_order_filled(
    conn: sqlite3.Connection, order_id: int, executor: str, executed_at: datetime
) -> None:
    conn.execute(
        "UPDATE orders SET status = 'filled', executor = ?, executed_at = ? WHERE order_id = ?",
        (executor, to_iso(executed_at), order_id),
    )


def mark_order_failed(
    conn: sqlite3.Connection,
    order_id: int,
    *,
    reason: str,
    detail: str,
    executor: str,
    executed_at: datetime,
    retry_at: datetime | None,
    manual: bool,
) -> None:
    conn.execute(
        "UPDATE orders SET status = 'failed', failure_reason = ?, failure_detail = ?,"
        " executor = ?, executed_at = ?, retry_at = ?, manual = ? WHERE order_id = ?",
        (
            reason,
            detail,
            executor,
            to_iso(executed_at),
            None if retry_at is None else to_iso(retry_at),
            1 if manual else 0,
            order_id,
        ),
    )


def cancel_orders_of_stage(conn: sqlite3.Connection, stage_id: int) -> None:
    conn.execute(
        "UPDATE orders SET status = 'cancelled' WHERE stage_id = ? AND status = 'pending'",
        (stage_id,),
    )


# ── fills ────────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NewFill:
    order_id: int
    ledger_id: str
    kind: str  # 'trade' | 'fx'
    instrument_id: str | None
    side: str
    fx_direction: str | None
    currency: Currency
    qty: int | None
    price: Decimal | None
    gross: Decimal
    fee: Decimal
    fee_krw: Decimal
    krw_rate: Decimal | None
    received: Decimal | None
    filled_at: datetime
    price_source: str
    executor: str


def insert_fill(conn: sqlite3.Connection, fill: NewFill) -> int:
    cur = conn.execute(
        "INSERT INTO fills (order_id, ledger_id, kind, instrument_id, side, fx_direction,"
        " currency, qty, price, gross, fee, fee_krw, krw_rate, received, filled_at,"
        " price_source, executor) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            fill.order_id,
            fill.ledger_id,
            fill.kind,
            fill.instrument_id,
            fill.side,
            fill.fx_direction,
            fill.currency.value,
            fill.qty,
            None if fill.price is None else str(fill.price),
            str(fill.gross),
            str(fill.fee),
            str(fill.fee_krw),
            None if fill.krw_rate is None else str(fill.krw_rate),
            None if fill.received is None else str(fill.received),
            to_iso(fill.filled_at),
            fill.price_source,
            fill.executor,
        ),
    )
    return _lastrowid(cur)


def fills_of_ledger(conn: sqlite3.Connection, ledger_id: str) -> list[FillRow]:
    return [
        FillRow.from_row(r)
        for r in _all(
            conn,
            "SELECT * FROM fills WHERE ledger_id = ? ORDER BY filled_at, fill_id",
            (ledger_id,),
        )
    ]


def fills_of_plan(conn: sqlite3.Connection, plan_id: int) -> list[FillRow]:
    return [
        FillRow.from_row(r)
        for r in _all(
            conn,
            "SELECT f.* FROM fills f JOIN orders o ON o.order_id = f.order_id"
            " WHERE o.plan_id = ? ORDER BY f.filled_at, f.fill_id",
            (plan_id,),
        )
    ]


# ── events ───────────────────────────────────────────────────────────────────────────────


def insert_event(
    conn: sqlite3.Connection,
    *,
    ledger_id: str,
    kind: str,
    event_date: date,
    occurred_at: datetime,
    rule_id: str | None = None,
    plan_id: int | None = None,
    status: str | None = None,
    amount: Decimal | None = None,
    currency: Currency | None = None,
    payload: Mapping[str, Any] | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO events (ledger_id, kind, event_date, occurred_at, rule_id, plan_id, status,"
        " amount, currency, payload, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ledger_id,
            kind,
            event_date.isoformat(),
            to_iso(occurred_at),
            rule_id,
            plan_id,
            status,
            None if amount is None else str(amount),
            None if currency is None else currency.value,
            dumps(dict(payload or {})),
            to_iso(occurred_at),
            to_iso(occurred_at),
        ),
    )
    return _lastrowid(cur)


def update_event(
    conn: sqlite3.Connection,
    event_id: int,
    at: datetime,
    *,
    status: str | None = None,
    payload: Mapping[str, Any] | None = None,
    plan_id: int | None = None,
) -> None:
    sets = ["updated_at = ?"]
    params: list[Any] = [to_iso(at)]
    if status is not None:
        sets.append("status = ?")
        params.append(status)
    if payload is not None:
        sets.append("payload = ?")
        params.append(dumps(dict(payload)))
    if plan_id is not None:
        sets.append("plan_id = ?")
        params.append(plan_id)
    conn.execute(f"UPDATE events SET {', '.join(sets)} WHERE event_id = ?", (*params, event_id))


def event_of_plan(conn: sqlite3.Connection, plan_id: int) -> EventRow | None:
    row = _one(conn, "SELECT * FROM events WHERE plan_id = ?", (plan_id,))
    return None if row is None else EventRow.from_row(row)


def start_event(conn: sqlite3.Connection, ledger_id: str) -> EventRow | None:
    row = _one(conn, "SELECT * FROM events WHERE ledger_id = ? AND kind = 'start'", (ledger_id,))
    return None if row is None else EventRow.from_row(row)


def check_failure_event(conn: sqlite3.Connection, ledger_id: str, d: date) -> EventRow | None:
    row = _one(
        conn,
        "SELECT * FROM events WHERE ledger_id = ? AND kind = 'check-failed' AND event_date = ?",
        (ledger_id, d.isoformat()),
    )
    return None if row is None else EventRow.from_row(row)


def events_of_ledger(
    conn: sqlite3.Connection, ledger_id: str, kinds: Sequence[str] | None = None
) -> list[EventRow]:
    sql = "SELECT * FROM events WHERE ledger_id = ?"
    params: list[Any] = [ledger_id]
    if kinds:
        sql += f" AND kind IN ({','.join('?' * len(kinds))})"
        params.extend(kinds)
    return [
        EventRow.from_row(r) for r in _all(conn, sql + " ORDER BY occurred_at, event_id", params)
    ]


CASH_FLOW_KINDS = ("start", "deposit", "withdrawal", "dividend")


def inflows_since(
    conn: sqlite3.Connection, ledger_id: str, since: datetime | None
) -> dict[Currency, Decimal]:
    """Start amount, deposits and dividends recorded after `since` (all of them when None)."""
    sql = (
        "SELECT currency, amount FROM events WHERE ledger_id = ?"
        " AND kind IN ('start', 'deposit', 'dividend') AND amount IS NOT NULL"
    )
    params: list[Any] = [ledger_id]
    if since is not None:
        sql += " AND occurred_at > ?"
        params.append(to_iso(since))
    out: dict[Currency, Decimal] = {}
    for r in _all(conn, sql, params):
        ccy = Currency(str(r["currency"] or "KRW"))
        out[ccy] = out.get(ccy, ZERO) + Decimal(str(r["amount"]))
    return out


# ── snapshots ────────────────────────────────────────────────────────────────────────────


def upsert_snapshot(conn: sqlite3.Connection, snap: SnapshotRow, at: datetime) -> None:
    conn.execute(
        "INSERT INTO snapshots (ledger_id, date, valued_at, total_krw, positions, cash_krw,"
        " cash_usd, cash_parts, fx_rate, fx_at, kr_close_date, us_close_date, contributions,"
        " pnl_krw, baseline_krw, baseline_units, stale, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(ledger_id, date) DO UPDATE SET valued_at = excluded.valued_at,"
        " total_krw = excluded.total_krw, positions = excluded.positions,"
        " cash_krw = excluded.cash_krw, cash_usd = excluded.cash_usd,"
        " cash_parts = excluded.cash_parts, fx_rate = excluded.fx_rate, fx_at = excluded.fx_at,"
        " kr_close_date = excluded.kr_close_date, us_close_date = excluded.us_close_date,"
        " contributions = excluded.contributions, pnl_krw = excluded.pnl_krw,"
        " baseline_krw = excluded.baseline_krw, baseline_units = excluded.baseline_units,"
        " stale = excluded.stale, created_at = excluded.created_at",
        (
            snap.ledger_id,
            snap.date.isoformat(),
            to_iso(snap.valued_at),
            str(snap.total_krw),
            dumps(snap.positions),
            str(snap.cash_krw),
            str(snap.cash_usd),
            dumps(snap.cash_parts),
            str(snap.fx_rate),
            to_iso(snap.fx_at),
            None if snap.kr_close_date is None else snap.kr_close_date.isoformat(),
            None if snap.us_close_date is None else snap.us_close_date.isoformat(),
            str(snap.contributions),
            str(snap.pnl_krw),
            None if snap.baseline_krw is None else str(snap.baseline_krw),
            None if snap.baseline_units is None else dumps(snap.baseline_units),
            dumps(snap.stale),
            to_iso(at),
        ),
    )


def get_snapshot(conn: sqlite3.Connection, ledger_id: str, d: date) -> SnapshotRow | None:
    row = _one(
        conn, "SELECT * FROM snapshots WHERE ledger_id = ? AND date = ?", (ledger_id, d.isoformat())
    )
    return None if row is None else SnapshotRow.from_row(row)


def latest_snapshot_before(conn: sqlite3.Connection, ledger_id: str, d: date) -> SnapshotRow | None:
    row = _one(
        conn,
        "SELECT * FROM snapshots WHERE ledger_id = ? AND date < ? ORDER BY date DESC LIMIT 1",
        (ledger_id, d.isoformat()),
    )
    return None if row is None else SnapshotRow.from_row(row)


# ── market data ──────────────────────────────────────────────────────────────────────────


def upsert_bars(conn: sqlite3.Connection, bars: Iterable[Bar], fetched_at: datetime) -> int:
    count = 0
    for b in bars:
        conn.execute(
            "INSERT INTO market_prices (instrument_id, session_date, open, high, low, close,"
            " source, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(instrument_id, session_date) DO UPDATE SET open = excluded.open,"
            " high = excluded.high, low = excluded.low, close = excluded.close,"
            " source = excluded.source, fetched_at = excluded.fetched_at",
            (
                b.instrument_id,
                b.session_date.isoformat(),
                None if b.open is None else str(b.open),
                None if b.high is None else str(b.high),
                None if b.low is None else str(b.low),
                str(b.close),
                b.source,
                to_iso(fetched_at),
            ),
        )
        count += 1
    return count


def get_bar(conn: sqlite3.Connection, instrument_id: str, session_date: date) -> Bar | None:
    row = _one(
        conn,
        "SELECT * FROM market_prices WHERE instrument_id = ? AND session_date = ?",
        (instrument_id, session_date.isoformat()),
    )
    return None if row is None else bar_from_row(row)


def latest_bar(conn: sqlite3.Connection, instrument_id: str, on_or_before: date) -> Bar | None:
    row = _one(
        conn,
        "SELECT * FROM market_prices WHERE instrument_id = ? AND session_date <= ?"
        " ORDER BY session_date DESC LIMIT 1",
        (instrument_id, on_or_before.isoformat()),
    )
    return None if row is None else bar_from_row(row)


def insert_fx(conn: sqlite3.Connection, quote: FxQuote, fetched_at: datetime) -> None:
    conn.execute(
        "INSERT INTO fx_rates (pair, as_of, rate, source, fetched_at) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(pair, as_of) DO UPDATE SET rate = excluded.rate, source = excluded.source,"
        " fetched_at = excluded.fetched_at",
        (PAIR_USDKRW, to_iso(quote.as_of), str(quote.rate), quote.source, to_iso(fetched_at)),
    )


def fx_at(conn: sqlite3.Connection, at: datetime) -> FxQuote | None:
    """The latest stored quote at or before `at`."""
    row = _one(
        conn,
        "SELECT * FROM fx_rates WHERE pair = ? AND as_of <= ? ORDER BY as_of DESC LIMIT 1",
        (PAIR_USDKRW, to_iso(at)),
    )
    return None if row is None else fx_from_row(row)


def _ensure_freshness_row(conn: sqlite3.Connection, series: str, at: datetime) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO data_freshness (series, state, updated_at) VALUES (?, 'unknown', ?)",
        (series, to_iso(at)),
    )


def record_fetch(
    conn: sqlite3.Connection,
    series: str,
    *,
    attempted_at: datetime,
    source: str | None,
    error: str | None,
) -> None:
    """One fetch attempt. A success (error None) also moves 'fetched_at' ('받은 시각')."""
    _ensure_freshness_row(conn, series, attempted_at)
    conn.execute(
        "UPDATE data_freshness SET attempted_at = ?, error = ?, updated_at = ?,"
        " fetched_at = CASE WHEN ? IS NULL THEN ? ELSE fetched_at END,"
        " source = COALESCE(?, source) WHERE series = ?",
        (
            to_iso(attempted_at),
            error,
            to_iso(attempted_at),
            error,
            to_iso(attempted_at),
            source,
            series,
        ),
    )


def record_state(
    conn: sqlite3.Connection,
    series: str,
    *,
    state: str,
    basis: str | None,
    expected: str | None,
    missing_sessions: int,
    at: datetime,
) -> None:
    """The verdict of the latest evaluation ('기준', '상태')."""
    _ensure_freshness_row(conn, series, at)
    conn.execute(
        "UPDATE data_freshness SET state = ?, basis = ?, expected = ?, missing_sessions = ?,"
        " updated_at = ? WHERE series = ?",
        (state, basis, expected, missing_sessions, to_iso(at), series),
    )


def get_freshness(conn: sqlite3.Connection, series: str) -> FreshnessRow | None:
    row = _one(conn, "SELECT * FROM data_freshness WHERE series = ?", (series,))
    return None if row is None else FreshnessRow.from_row(row)


def all_freshness(conn: sqlite3.Connection) -> list[FreshnessRow]:
    return [
        FreshnessRow.from_row(r) for r in _all(conn, "SELECT * FROM data_freshness ORDER BY series")
    ]
