"""Storage of the live ledger's broker side (schema 6, autotrade/PHASE3.md 2.9).

- broker_status: one row, what the tick last saw of the Toss link (the web reads it; it cannot
  reach Toss itself).
- broker_snapshots: what the account held when the tick looked.
- broker_orders: the broker side of each live order (client order id, broker order id, status,
  the fill as the broker reported it, cancel requests).
- external_fills: fills and conversions in the account that the engine did not send.
- live_previews: the first-order previews shown on the mode screen, by hash.

The caller owns the transaction, as everywhere in autotrade/db.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from autotrade.broker.toss_api import BrokerHolding, BrokerOrder, OrderRequest
from autotrade.db.connection import dumps, loads
from autotrade.domain.instruments import Currency
from autotrade.timeutil import from_iso, to_iso


def _dt(value: Any) -> datetime | None:
    return None if value is None else from_iso(str(value))


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _iso(value: datetime | None) -> str | None:
    return None if value is None else to_iso(value)


# ── broker_status ────────────────────────────────────────────────────────────────────────

STATUS_STATES = (
    "ok",
    "off",
    "no-key",
    "auth",
    "ip",
    "account",
    "unreachable",
    "maintenance",
    "error",
)


@dataclass(frozen=True)
class BrokerStatus:
    state: str
    env_live: bool
    checked_at: datetime
    ok_at: datetime | None = None
    account_seq: int | None = None
    account_tail: str | None = None
    tradable: dict[str, str] = field(default_factory=dict)  # instrument -> 'ok' | cause
    tradable_at: datetime | None = None
    commissions: dict[str, Decimal] = field(default_factory=dict)  # 'KR' | 'US' -> rate
    revoked: int = 0  # token-revoked answers seen in the last check
    revoked_at: datetime | None = None
    key_expires: date | None = None
    detail: str | None = None
    reconcile_state: str | None = None  # 'match' | 'mismatch' | 'busy'
    reconciled_at: datetime | None = None  # the last reconciliation, whatever it found
    reconcile_detail: dict[str, Any] = field(default_factory=dict)
    matched_at: datetime | None = None  # the last reconciliation that matched
    # The account's open 조건주문 when the tick last looked (ConditionalOrder.to_json); None
    # when they were never read.
    conditional: list[dict[str, Any]] | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> BrokerStatus:
        tradable = loads(str(row["tradable"])) or {}
        commissions = loads(str(row["commissions"])) or {}
        detail = loads(str(row["reconcile_detail"])) or {}
        conditional = (
            None if row["conditional_orders"] is None else loads(str(row["conditional_orders"]))
        )
        return cls(
            state=str(row["state"]),
            env_live=bool(row["env_live"]),
            checked_at=from_iso(str(row["checked_at"])),
            ok_at=_dt(row["ok_at"]),
            account_seq=None if row["account_seq"] is None else int(row["account_seq"]),
            account_tail=None if row["account_tail"] is None else str(row["account_tail"]),
            tradable={str(k): str(v) for k, v in tradable.items()},
            tradable_at=_dt(row["tradable_at"]),
            commissions={str(k): Decimal(str(v)) for k, v in commissions.items()},
            revoked=int(row["revoked"]),
            revoked_at=_dt(row["revoked_at"]),
            key_expires=None
            if row["key_expires"] is None
            else date.fromisoformat(str(row["key_expires"])),
            detail=None if row["detail"] is None else str(row["detail"]),
            reconcile_state=None if row["reconcile_state"] is None else str(row["reconcile_state"]),
            reconciled_at=_dt(row["reconciled_at"]),
            reconcile_detail=detail if isinstance(detail, dict) else {},
            matched_at=_dt(row["matched_at"]),
            conditional=[dict(c) for c in conditional if isinstance(c, dict)]
            if isinstance(conditional, list)
            else None,
        )


def get_status(conn: sqlite3.Connection) -> BrokerStatus | None:
    row = conn.execute("SELECT * FROM broker_status WHERE id = 1").fetchone()
    return None if row is None else BrokerStatus.from_row(row)


def save_status(conn: sqlite3.Connection, status: BrokerStatus, at: datetime) -> None:
    if status.state not in STATUS_STATES:
        raise ValueError(f"not a broker state: {status.state}")
    conn.execute(
        "INSERT INTO broker_status (id, state, env_live, checked_at, ok_at, account_seq,"
        " account_tail, tradable, tradable_at, commissions, revoked, revoked_at, key_expires,"
        " detail, reconcile_state, reconciled_at, reconcile_detail, matched_at,"
        " conditional_orders, updated_at)"
        " VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET state = excluded.state, env_live = excluded.env_live,"
        " checked_at = excluded.checked_at, ok_at = excluded.ok_at,"
        " account_seq = excluded.account_seq, account_tail = excluded.account_tail,"
        " tradable = excluded.tradable, tradable_at = excluded.tradable_at,"
        " commissions = excluded.commissions, revoked = excluded.revoked,"
        " revoked_at = excluded.revoked_at, key_expires = excluded.key_expires,"
        " detail = excluded.detail, reconcile_state = excluded.reconcile_state,"
        " reconciled_at = excluded.reconciled_at, reconcile_detail = excluded.reconcile_detail,"
        " matched_at = excluded.matched_at, conditional_orders = excluded.conditional_orders,"
        " updated_at = excluded.updated_at",
        (
            status.state,
            1 if status.env_live else 0,
            to_iso(status.checked_at),
            _iso(status.ok_at),
            status.account_seq,
            status.account_tail,
            dumps(status.tradable),
            _iso(status.tradable_at),
            dumps({k: str(v) for k, v in status.commissions.items()}),
            status.revoked,
            _iso(status.revoked_at),
            None if status.key_expires is None else status.key_expires.isoformat(),
            status.detail,
            status.reconcile_state,
            _iso(status.reconciled_at),
            dumps(status.reconcile_detail),
            _iso(status.matched_at),
            None if status.conditional is None else dumps(status.conditional),
            to_iso(at),
        ),
    )


# ── broker_snapshots ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AccountSnapshot:
    snapshot_id: int
    taken_at: datetime  # when the balances were read
    confirmed_at: datetime  # the latest tick that found the same account
    cash: dict[Currency, Decimal]  # buying power per currency
    holdings: list[BrokerHolding]
    closed_orders: list[BrokerOrder]  # filled orders read with it (the reconciliation's input)
    quiet: bool  # no open order anywhere when it was read

    def cash_of(self, currency: Currency) -> Decimal:
        return self.cash.get(currency, Decimal(0))

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> AccountSnapshot:
        holdings = loads(str(row["holdings"])) or []
        closed = loads(str(row["closed_orders"])) or []
        return cls(
            snapshot_id=int(row["snapshot_id"]),
            taken_at=from_iso(str(row["taken_at"])),
            confirmed_at=from_iso(str(row["confirmed_at"])),
            cash={
                Currency.KRW: Decimal(str(row["cash_krw"])),
                Currency.USD: Decimal(str(row["cash_usd"])),
            },
            holdings=[BrokerHolding.from_json(h) for h in holdings],
            closed_orders=[BrokerOrder.from_json(o) for o in closed],
            quiet=bool(row["quiet"]),
        )


def _snapshot_content(
    cash: Mapping[Currency, Decimal],
    holdings: Sequence[BrokerHolding],
    closed: Sequence[BrokerOrder],
    quiet: bool,
) -> tuple[str, str, str, str, int]:
    return (
        str(cash.get(Currency.KRW, Decimal(0))),
        str(cash.get(Currency.USD, Decimal(0))),
        dumps([h.to_json() for h in holdings]),
        dumps([o.to_json() for o in closed]),
        1 if quiet else 0,
    )


def record_snapshot(
    conn: sqlite3.Connection,
    taken_at: datetime,
    cash: Mapping[Currency, Decimal],
    holdings: Sequence[BrokerHolding],
    closed: Sequence[BrokerOrder],
    quiet: bool,
) -> int:
    """Store what the account held, or confirm the latest row when nothing changed."""
    content = _snapshot_content(cash, holdings, closed, quiet)
    last = conn.execute(
        "SELECT snapshot_id, cash_krw, cash_usd, holdings, closed_orders, quiet"
        " FROM broker_snapshots ORDER BY snapshot_id DESC LIMIT 1"
    ).fetchone()
    if last is not None and tuple(last)[1:] == content:
        conn.execute(
            "UPDATE broker_snapshots SET confirmed_at = ? WHERE snapshot_id = ?",
            (to_iso(taken_at), int(last["snapshot_id"])),
        )
        return int(last["snapshot_id"])
    cur = conn.execute(
        "INSERT INTO broker_snapshots (taken_at, confirmed_at, cash_krw, cash_usd, holdings,"
        " closed_orders, quiet) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (to_iso(taken_at), to_iso(taken_at), *content),
    )
    if cur.lastrowid is None:  # pragma: no cover — sqlite always sets it after an INSERT
        raise RuntimeError("no row id")
    return int(cur.lastrowid)


def latest_snapshot(conn: sqlite3.Connection) -> AccountSnapshot | None:
    row = conn.execute(
        "SELECT * FROM broker_snapshots ORDER BY snapshot_id DESC LIMIT 1"
    ).fetchone()
    return None if row is None else AccountSnapshot.from_row(row)


def get_snapshot(conn: sqlite3.Connection, snapshot_id: int) -> AccountSnapshot | None:
    row = conn.execute(
        "SELECT * FROM broker_snapshots WHERE snapshot_id = ?", (snapshot_id,)
    ).fetchone()
    return None if row is None else AccountSnapshot.from_row(row)


def prune_snapshots(conn: sqlite3.Connection, before: datetime) -> int:
    """Drop old snapshots, never the latest one."""
    cur = conn.execute(
        "DELETE FROM broker_snapshots WHERE confirmed_at < ? AND snapshot_id <"
        " (SELECT MAX(snapshot_id) FROM broker_snapshots)",
        (to_iso(before),),
    )
    return int(cur.rowcount)


# ── broker_orders ────────────────────────────────────────────────────────────────────────

OPEN_STATES = ("sending", "sent", "unknown")


@dataclass(frozen=True)
class BrokerOrderRow:
    order_id: int
    ledger_id: str
    client_order_id: str
    broker_order_id: str | None
    state: str  # sending | sent | unknown | done | rejected | not-sent
    request: OrderRequest | None
    sent_at: datetime | None
    status: str | None  # the broker's order status
    filled_qty: Decimal | None
    filled_amount: Decimal | None
    avg_price: Decimal | None
    commission: Decimal | None
    tax: Decimal | None
    filled_at: datetime | None
    settlement_date: date | None
    error_code: str | None
    error_detail: str | None
    retry_after: datetime | None
    cancel_state: str | None
    cancel_requested_at: datetime | None
    cancel_error: str | None
    cancel_attempts: int
    updated_at: datetime
    # 'unknown'/'ambiguous': the account's orders that matched it, as the search saw them:
    # {"order": BrokerOrder.to_json(), "closed": bool (from the CLOSED list)}.
    candidates: list[dict[str, Any]] = field(default_factory=list)

    @property
    def open(self) -> bool:
        return self.state in OPEN_STATES

    @property
    def fee(self) -> Decimal:
        return (self.commission or Decimal(0)) + (self.tax or Decimal(0))

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> BrokerOrderRow:
        request = loads(str(row["request"])) or {}
        settlement = row["settlement_date"]
        candidates = loads(str(row["candidates"])) or []
        return cls(
            order_id=int(row["order_id"]),
            ledger_id=str(row["ledger_id"]),
            client_order_id=str(row["client_order_id"]),
            broker_order_id=None if row["broker_order_id"] is None else str(row["broker_order_id"]),
            state=str(row["state"]),
            request=OrderRequest.from_json(request) if request else None,
            sent_at=_dt(row["sent_at"]),
            status=None if row["status"] is None else str(row["status"]),
            filled_qty=_dec(row["filled_qty"]),
            filled_amount=_dec(row["filled_amount"]),
            avg_price=_dec(row["avg_price"]),
            commission=_dec(row["commission"]),
            tax=_dec(row["tax"]),
            filled_at=_dt(row["filled_at"]),
            settlement_date=None if settlement is None else date.fromisoformat(str(settlement)),
            error_code=None if row["error_code"] is None else str(row["error_code"]),
            error_detail=None if row["error_detail"] is None else str(row["error_detail"]),
            retry_after=_dt(row["retry_after"]),
            cancel_state=None if row["cancel_state"] is None else str(row["cancel_state"]),
            cancel_requested_at=_dt(row["cancel_requested_at"]),
            cancel_error=None if row["cancel_error"] is None else str(row["cancel_error"]),
            cancel_attempts=int(row["cancel_attempts"]),
            updated_at=from_iso(str(row["updated_at"])),
            candidates=[dict(c) for c in candidates if isinstance(c, dict)]
            if isinstance(candidates, list)
            else [],
        )


def get_broker_order(conn: sqlite3.Connection, order_id: int) -> BrokerOrderRow | None:
    row = conn.execute("SELECT * FROM broker_orders WHERE order_id = ?", (order_id,)).fetchone()
    return None if row is None else BrokerOrderRow.from_row(row)


def broker_orders_of(
    conn: sqlite3.Connection, ledger_id: str, states: Sequence[str] | None = None
) -> list[BrokerOrderRow]:
    sql = "SELECT * FROM broker_orders WHERE ledger_id = ?"
    params: list[Any] = [ledger_id]
    if states:
        sql += f" AND state IN ({','.join('?' * len(states))})"
        params.extend(states)
    rows = conn.execute(sql + " ORDER BY order_id", params).fetchall()
    return [BrokerOrderRow.from_row(r) for r in rows]


def our_broker_ids(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT broker_order_id FROM broker_orders WHERE broker_order_id IS NOT NULL"
    ).fetchall()
    return {str(r[0]) for r in rows}


def insert_intent(
    conn: sqlite3.Connection,
    *,
    order_id: int,
    ledger_id: str,
    request: OrderRequest,
    at: datetime,
) -> None:
    """The order is about to be sent: committed before the request leaves (PHASE3.md 2.3)."""
    conn.execute(
        "INSERT INTO broker_orders (order_id, ledger_id, client_order_id, state, request,"
        " sent_at, updated_at) VALUES (?, ?, ?, 'sending', ?, ?, ?)"
        " ON CONFLICT(order_id) DO UPDATE SET state = 'sending', request = excluded.request,"
        " sent_at = excluded.sent_at, error_code = NULL, error_detail = NULL,"
        " retry_after = NULL, candidates = '[]', updated_at = excluded.updated_at",
        (
            order_id,
            ledger_id,
            request.client_order_id,
            dumps(request.to_json()),
            to_iso(at),
            to_iso(at),
        ),
    )


def record_not_sent(
    conn: sqlite3.Connection,
    *,
    order_id: int,
    ledger_id: str,
    client_order_id: str,
    code: str,
    detail: str,
    at: datetime,
    request: OrderRequest | None = None,
    retry_after: datetime | None = None,
) -> None:
    """The engine decided not to send this attempt (no cash, nothing to sell, over the limit,
    order hours), or the broker never got it."""
    conn.execute(
        "INSERT INTO broker_orders (order_id, ledger_id, client_order_id, state, request,"
        " error_code, error_detail, retry_after, updated_at)"
        " VALUES (?, ?, ?, 'not-sent', ?, ?, ?, ?, ?)"
        " ON CONFLICT(order_id) DO UPDATE SET state = 'not-sent', error_code = excluded.error_code,"
        " error_detail = excluded.error_detail, retry_after = excluded.retry_after,"
        " updated_at = excluded.updated_at",
        (
            order_id,
            ledger_id,
            client_order_id,
            dumps({} if request is None else request.to_json()),
            code,
            detail[:400],
            _iso(retry_after),
            to_iso(at),
        ),
    )


def mark_sent(conn: sqlite3.Connection, order_id: int, broker_order_id: str, at: datetime) -> None:
    conn.execute(
        "UPDATE broker_orders SET state = 'sent', broker_order_id = ?, error_code = NULL,"
        " error_detail = NULL, updated_at = ? WHERE order_id = ?",
        (broker_order_id, to_iso(at), order_id),
    )


def mark_unknown(
    conn: sqlite3.Connection,
    order_id: int,
    code: str,
    detail: str,
    at: datetime,
    candidates: Sequence[Mapping[str, Any]] = (),
) -> None:
    conn.execute(
        "UPDATE broker_orders SET state = 'unknown', error_code = ?, error_detail = ?,"
        " candidates = ?, updated_at = ? WHERE order_id = ?",
        (code, detail[:400], dumps([dict(c) for c in candidates]), to_iso(at), order_id),
    )


def mark_rejected(
    conn: sqlite3.Connection, order_id: int, code: str, detail: str, at: datetime
) -> None:
    conn.execute(
        "UPDATE broker_orders SET state = 'rejected', error_code = ?, error_detail = ?,"
        " updated_at = ? WHERE order_id = ?",
        (code, detail[:400], to_iso(at), order_id),
    )


def record_broker_view(
    conn: sqlite3.Connection,
    order_id: int,
    view: BrokerOrder,
    at: datetime,
    *,
    finished: bool | None = None,
) -> None:
    """What the broker says of our order now: its status and the fill so far. An order that is
    over makes the row 'done' (the fill is final): `finished`, or by default its own record
    (BrokerOrder.terminal; a PARTIAL_FILLED order needs the CLOSED list, jobs/live_tasks.py)."""
    over = view.terminal if finished is None else finished
    state = "done" if over else "sent"
    conn.execute(
        "UPDATE broker_orders SET state = ?, broker_order_id = ?, status = ?, filled_qty = ?,"
        " filled_amount = ?, avg_price = ?, commission = ?, tax = ?, filled_at = ?,"
        " settlement_date = ?, updated_at = ? WHERE order_id = ?",
        (
            state,
            view.order_id,
            view.status,
            str(view.filled_qty),
            None if view.filled_amount is None else str(view.filled_amount),
            None if view.avg_price is None else str(view.avg_price),
            None if view.commission is None else str(view.commission),
            None if view.tax is None else str(view.tax),
            _iso(view.filled_at),
            None if view.settlement_date is None else view.settlement_date.isoformat(),
            to_iso(at),
            order_id,
        ),
    )


def request_cancel(conn: sqlite3.Connection, order_id: int, at: datetime) -> None:
    conn.execute(
        "UPDATE broker_orders SET cancel_state = 'requested', cancel_requested_at ="
        " COALESCE(cancel_requested_at, ?), cancel_error = NULL, updated_at = ?"
        " WHERE order_id = ? AND (cancel_state IS NULL OR cancel_state != 'done')",
        (to_iso(at), to_iso(at), order_id),
    )


def record_cancel(
    conn: sqlite3.Connection, order_id: int, state: str, error: str | None, at: datetime
) -> None:
    conn.execute(
        "UPDATE broker_orders SET cancel_state = ?, cancel_error = ?,"
        " cancel_attempts = cancel_attempts + 1, updated_at = ? WHERE order_id = ?",
        (state, None if error is None else error[:400], to_iso(at), order_id),
    )


def cancel_rows(
    conn: sqlite3.Connection, ledger_id: str, states: Iterable[str]
) -> list[BrokerOrderRow]:
    wanted = list(states)
    rows = conn.execute(
        "SELECT * FROM broker_orders WHERE ledger_id = ?"
        f" AND cancel_state IN ({','.join('?' * len(wanted))}) ORDER BY order_id",
        (ledger_id, *wanted),
    ).fetchall()
    return [BrokerOrderRow.from_row(r) for r in rows]


# ── external_fills ───────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ExternalFill:
    ext_id: int
    ledger_id: str
    broker_order_id: str | None
    kind: str  # 'trade' | 'fx'
    treatment: str  # 'ledger' | 'outside'
    instrument_id: str | None
    symbol: str | None
    name: str | None
    side: str  # buy | sell; for fx the direction (krw_to_usd | usd_to_krw)
    currency: Currency  # trade: the instrument's; fx: the source currency
    qty: int | None
    gross: Decimal  # trade: filled amount; fx: what left the source currency
    fee: Decimal
    fee_krw: Decimal
    krw_rate: Decimal | None
    received: Decimal | None  # fx: what the target currency got
    filled_at: datetime
    settlement_date: date | None
    event_id: int | None
    rule_id: str | None = None  # a rule's part the owner traded (schema 7); None: '지수 반반'

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> ExternalFill:
        settlement = row["settlement_date"]
        return cls(
            ext_id=int(row["ext_id"]),
            ledger_id=str(row["ledger_id"]),
            broker_order_id=None if row["broker_order_id"] is None else str(row["broker_order_id"]),
            kind=str(row["kind"]),
            treatment=str(row["treatment"]),
            instrument_id=None if row["instrument_id"] is None else str(row["instrument_id"]),
            symbol=None if row["symbol"] is None else str(row["symbol"]),
            name=None if row["name"] is None else str(row["name"]),
            side=str(row["side"]),
            currency=Currency(str(row["currency"])),
            qty=None if row["qty"] is None else int(row["qty"]),
            gross=Decimal(str(row["gross"])),
            fee=Decimal(str(row["fee"])),
            fee_krw=Decimal(str(row["fee_krw"])),
            krw_rate=_dec(row["krw_rate"]),
            received=_dec(row["received"]),
            filled_at=from_iso(str(row["filled_at"])),
            settlement_date=None if settlement is None else date.fromisoformat(str(settlement)),
            event_id=None if row["event_id"] is None else int(row["event_id"]),
            rule_id=None if row["rule_id"] is None else str(row["rule_id"]),
        )


@dataclass(frozen=True)
class NewExternalFill:
    ledger_id: str
    broker_order_id: str | None
    kind: str
    treatment: str
    instrument_id: str | None
    symbol: str | None
    name: str | None
    side: str
    currency: Currency
    qty: int | None
    gross: Decimal
    fee: Decimal
    fee_krw: Decimal
    krw_rate: Decimal | None
    received: Decimal | None
    filled_at: datetime
    settlement_date: date | None
    event_id: int | None = None
    rule_id: str | None = None


def insert_external(conn: sqlite3.Connection, fill: NewExternalFill, at: datetime) -> int:
    cur = conn.execute(
        "INSERT INTO external_fills (ledger_id, broker_order_id, kind, treatment, instrument_id,"
        " symbol, name, side, currency, qty, gross, fee, fee_krw, krw_rate, received, filled_at,"
        " settlement_date, event_id, rule_id, recorded_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            fill.ledger_id,
            fill.broker_order_id,
            fill.kind,
            fill.treatment,
            fill.instrument_id,
            fill.symbol,
            fill.name,
            fill.side,
            fill.currency.value,
            fill.qty,
            str(fill.gross),
            str(fill.fee),
            str(fill.fee_krw),
            None if fill.krw_rate is None else str(fill.krw_rate),
            None if fill.received is None else str(fill.received),
            to_iso(fill.filled_at),
            None if fill.settlement_date is None else fill.settlement_date.isoformat(),
            fill.event_id,
            fill.rule_id,
            to_iso(at),
        ),
    )
    if cur.lastrowid is None:  # pragma: no cover
        raise RuntimeError("no row id")
    return int(cur.lastrowid)


def externals_of(
    conn: sqlite3.Connection, ledger_id: str, treatment: str | None = None
) -> list[ExternalFill]:
    sql = "SELECT * FROM external_fills WHERE ledger_id = ?"
    params: list[Any] = [ledger_id]
    if treatment is not None:
        sql += " AND treatment = ?"
        params.append(treatment)
    rows = conn.execute(sql + " ORDER BY filled_at, ext_id", params).fetchall()
    return [ExternalFill.from_row(r) for r in rows]


def external_broker_ids(conn: sqlite3.Connection, ledger_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT broker_order_id FROM external_fills WHERE ledger_id = ?"
        " AND broker_order_id IS NOT NULL",
        (ledger_id,),
    ).fetchall()
    return {str(r[0]) for r in rows}


# ── live_previews ────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class StoredPreview:
    hash: str
    computed_at: datetime
    snapshot_id: int | None
    total_krw: Decimal
    signature: str
    payload: dict[str, Any]


def save_preview(conn: sqlite3.Connection, preview: StoredPreview) -> None:
    conn.execute(
        "INSERT INTO live_previews (hash, computed_at, snapshot_id, total_krw, signature, payload)"
        " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(hash) DO UPDATE SET computed_at ="
        " excluded.computed_at",
        (
            preview.hash,
            to_iso(preview.computed_at),
            preview.snapshot_id,
            str(preview.total_krw),
            preview.signature,
            dumps(preview.payload),
        ),
    )


def get_preview(conn: sqlite3.Connection, preview_hash: str) -> StoredPreview | None:
    row = conn.execute("SELECT * FROM live_previews WHERE hash = ?", (preview_hash,)).fetchone()
    if row is None:
        return None
    payload = loads(str(row["payload"])) or {}
    return StoredPreview(
        hash=str(row["hash"]),
        computed_at=from_iso(str(row["computed_at"])),
        snapshot_id=None if row["snapshot_id"] is None else int(row["snapshot_id"]),
        total_krw=Decimal(str(row["total_krw"])),
        signature=str(row["signature"]),
        payload=payload if isinstance(payload, dict) else {},
    )


def prune_previews(conn: sqlite3.Connection, before: datetime) -> None:
    conn.execute("DELETE FROM live_previews WHERE computed_at < ?", (to_iso(before),))
