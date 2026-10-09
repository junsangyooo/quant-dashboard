"""Reads and writes of the phase-2 tables (the AI rule '3년 발굴', schema V4).

Rule shares and sleeves, the judgment ledger (picks), the metric dictionary and table, filings,
the AI task queue and call log, switches, scores, the daily 'vs index' line, the runs of the new
jobs and the state of the outside sources. None of these commit (the caller owns the
transaction, autotrade/db/connection.py).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from autotrade.db.connection import dumps, loads
from autotrade.db.repo import NotFoundError
from autotrade.domain.instruments import Currency
from autotrade.domain.ledger import LedgerState, Position
from autotrade.domain.metrics import MetricDef
from autotrade.domain.money import ZERO
from autotrade.timeutil import from_iso, to_iso


def _one(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> sqlite3.Row | None:
    row: sqlite3.Row | None = conn.execute(sql, params).fetchone()
    return row


def _all(conn: sqlite3.Connection, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
    return list(conn.execute(sql, params).fetchall())


def _id(cur: sqlite3.Cursor) -> int:
    if cur.lastrowid is None:  # pragma: no cover — sqlite always sets it for INSERT
        raise RuntimeError("insert returned no row id")
    return int(cur.lastrowid)


def _dt(value: Any) -> datetime | None:
    return None if value is None else from_iso(str(value))


def _d(value: Any) -> date | None:
    return None if value is None else date.fromisoformat(str(value))


def _s(value: Any) -> str | None:
    return None if value is None else str(value)


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


# ── rule shares ──────────────────────────────────────────────────────────────────────────


def shares(conn: sqlite3.Connection, ledger_id: str) -> dict[str, Decimal]:
    """Target share of each rule in the ledger, in percent."""
    return {
        str(r["rule_id"]): Decimal(str(r["target_pct"]))
        for r in _all(
            conn,
            "SELECT rule_id, target_pct FROM rule_shares WHERE ledger_id = ? ORDER BY rule_id",
            (ledger_id,),
        )
    }


def set_share(
    conn: sqlite3.Connection, ledger_id: str, rule_id: str, pct: Decimal, at: datetime
) -> None:
    conn.execute(
        "INSERT INTO rule_shares (ledger_id, rule_id, target_pct, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(ledger_id, rule_id) DO UPDATE SET target_pct = excluded.target_pct,"
        " updated_at = excluded.updated_at",
        (ledger_id, rule_id, str(pct), to_iso(at)),
    )


def ensure_share(
    conn: sqlite3.Connection, ledger_id: str, rule_id: str, pct: Decimal, at: datetime
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO rule_shares (ledger_id, rule_id, target_pct, updated_at)"
        " VALUES (?, ?, ?, ?)",
        (ledger_id, rule_id, str(pct), to_iso(at)),
    )


# ── sleeves ──────────────────────────────────────────────────────────────────────────────


def load_sleeve(conn: sqlite3.Connection, ledger_id: str, rule_id: str) -> LedgerState:
    cash = dict.fromkeys(Currency, ZERO)
    for r in _all(
        conn,
        "SELECT currency, amount FROM sleeve_cash WHERE ledger_id = ? AND rule_id = ?",
        (ledger_id, rule_id),
    ):
        cash[Currency(str(r["currency"]))] = Decimal(str(r["amount"]))
    positions = {
        str(r["instrument_id"]): Position(
            instrument_id=str(r["instrument_id"]),
            currency=Currency(str(r["currency"])),
            qty=int(r["qty"]),
            cost_native=Decimal(str(r["cost_native"])),
            cost_krw=Decimal(str(r["cost_krw"])),
        )
        for r in _all(
            conn,
            "SELECT * FROM sleeve_positions WHERE ledger_id = ? AND rule_id = ?"
            " ORDER BY instrument_id",
            (ledger_id, rule_id),
        )
    }
    tot = _one(
        conn,
        "SELECT * FROM sleeve_totals WHERE ledger_id = ? AND rule_id = ?",
        (ledger_id, rule_id),
    )
    if tot is None:
        return LedgerState(cash=cash, positions=positions)
    return LedgerState(
        cash=cash,
        positions=positions,
        realized_krw=Decimal(str(tot["realized_krw"])),
        fees_krw=Decimal(str(tot["fees_krw"])),
        contributions_krw=Decimal(str(tot["contributions_krw"])),
        income_krw=Decimal(str(tot["income_krw"])),
    )


def save_sleeve(
    conn: sqlite3.Connection, ledger_id: str, rule_id: str, state: LedgerState, at: datetime
) -> None:
    stamp = to_iso(at)
    for currency in Currency:
        conn.execute(
            "INSERT INTO sleeve_cash (ledger_id, rule_id, currency, amount, updated_at)"
            " VALUES (?, ?, ?, ?, ?) ON CONFLICT(ledger_id, rule_id, currency)"
            " DO UPDATE SET amount = excluded.amount, updated_at = excluded.updated_at",
            (ledger_id, rule_id, currency.value, str(state.cash_of(currency)), stamp),
        )
    conn.execute(
        "DELETE FROM sleeve_positions WHERE ledger_id = ? AND rule_id = ?", (ledger_id, rule_id)
    )
    for pos in state.positions.values():
        conn.execute(
            "INSERT INTO sleeve_positions (ledger_id, rule_id, instrument_id, currency, qty,"
            " cost_native, cost_krw, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                ledger_id,
                rule_id,
                pos.instrument_id,
                pos.currency.value,
                pos.qty,
                str(pos.cost_native),
                str(pos.cost_krw),
                stamp,
            ),
        )
    conn.execute(
        "INSERT INTO sleeve_totals (ledger_id, rule_id, realized_krw, fees_krw,"
        " contributions_krw, income_krw, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(ledger_id, rule_id) DO UPDATE SET realized_krw = excluded.realized_krw,"
        " fees_krw = excluded.fees_krw, contributions_krw = excluded.contributions_krw,"
        " income_krw = excluded.income_krw, updated_at = excluded.updated_at",
        (
            ledger_id,
            rule_id,
            str(state.realized_krw),
            str(state.fees_krw),
            str(state.contributions_krw),
            str(state.income_krw),
            stamp,
        ),
    )


def sleeve_rules(conn: sqlite3.Connection, ledger_id: str) -> list[str]:
    """Rules with a sleeve of their own in this ledger."""
    return [
        str(r["rule_id"])
        for r in _all(
            conn,
            "SELECT rule_id FROM sleeve_totals WHERE ledger_id = ? ORDER BY rule_id",
            (ledger_id,),
        )
    ]


@dataclass(frozen=True)
class SleeveFlowRow:
    flow_id: int
    ledger_id: str
    rule_id: str
    event_id: int | None
    kind: str
    amount: Decimal
    currency: Currency
    krw_rate: Decimal | None
    occurred_at: datetime

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> SleeveFlowRow:
        return cls(
            flow_id=int(r["flow_id"]),
            ledger_id=str(r["ledger_id"]),
            rule_id=str(r["rule_id"]),
            event_id=None if r["event_id"] is None else int(r["event_id"]),
            kind=str(r["kind"]),
            amount=Decimal(str(r["amount"])),
            currency=Currency(str(r["currency"])),
            krw_rate=_dec(r["krw_rate"]),
            occurred_at=from_iso(str(r["occurred_at"])),
        )


def insert_sleeve_flow(
    conn: sqlite3.Connection,
    *,
    ledger_id: str,
    rule_id: str,
    event_id: int | None,
    kind: str,
    amount: Decimal,
    currency: Currency,
    krw_rate: Decimal | None,
    occurred_at: datetime,
) -> int:
    cur = conn.execute(
        "INSERT INTO sleeve_flows (ledger_id, rule_id, event_id, kind, amount, currency,"
        " krw_rate, occurred_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ledger_id,
            rule_id,
            event_id,
            kind,
            str(amount),
            currency.value,
            None if krw_rate is None else str(krw_rate),
            to_iso(occurred_at),
        ),
    )
    return _id(cur)


def sleeve_flows(conn: sqlite3.Connection, ledger_id: str, rule_id: str) -> list[SleeveFlowRow]:
    return [
        SleeveFlowRow.from_row(r)
        for r in _all(
            conn,
            "SELECT * FROM sleeve_flows WHERE ledger_id = ? AND rule_id = ?"
            " ORDER BY occurred_at, flow_id",
            (ledger_id, rule_id),
        )
    ]


def sleeve_flows_since(
    conn: sqlite3.Connection, ledger_id: str, since: datetime | None, kinds: Sequence[str]
) -> list[SleeveFlowRow]:
    sql = (
        f"SELECT * FROM sleeve_flows WHERE ledger_id = ? AND kind IN ({','.join('?' * len(kinds))})"
    )
    params: list[Any] = [ledger_id, *kinds]
    if since is not None:
        sql += " AND occurred_at > ?"
        params.append(to_iso(since))
    return [SleeveFlowRow.from_row(r) for r in _all(conn, sql + " ORDER BY flow_id", params)]


# ── picks (판단 장부) ───────────────────────────────────────────────────────────────────


OPEN_PICK = ("candidate", "held")


@dataclass(frozen=True)
class PickRow:
    pick_id: int
    ledger_id: str
    rule_id: str
    instrument_id: str
    status: str
    picked_on: date
    picked_price: Decimal
    benchmark: str
    benchmark_price: Decimal
    theme: str
    rationale: str
    confirm: list[dict[str, Any]]
    invalidate: list[dict[str, Any]]
    buy: list[dict[str, Any]]
    texts: dict[str, Any]  # the conditions in the words they were picked with
    confidence: str | None
    source: str
    last_verdict: str | None
    last_verdict_at: datetime | None
    weak_months: int
    decision: str | None
    decided_at: datetime | None
    decision_task_id: int | None
    shock_until: date | None
    closed_on: date | None
    closed_reason: str | None
    note: str | None
    created_at: datetime

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> PickRow:
        return cls(
            pick_id=int(r["pick_id"]),
            ledger_id=str(r["ledger_id"]),
            rule_id=str(r["rule_id"]),
            instrument_id=str(r["instrument_id"]),
            status=str(r["status"]),
            picked_on=date.fromisoformat(str(r["picked_on"])),
            picked_price=Decimal(str(r["picked_price"])),
            benchmark=str(r["benchmark"]),
            benchmark_price=Decimal(str(r["benchmark_price"])),
            theme=str(r["theme"]),
            rationale=str(r["rationale"]),
            confirm=loads(str(r["confirm"])) or [],
            invalidate=loads(str(r["invalidate"])) or [],
            buy=loads(str(r["buy"])) or [],
            texts=loads(str(r["texts"])) or {},
            confidence=_s(r["confidence"]),
            source=str(r["source"]),
            last_verdict=_s(r["last_verdict"]),
            last_verdict_at=_dt(r["last_verdict_at"]),
            weak_months=int(r["weak_months"]),
            decision=_s(r["decision"]),
            decided_at=_dt(r["decided_at"]),
            decision_task_id=None if r["decision_task_id"] is None else int(r["decision_task_id"]),
            shock_until=_d(r["shock_until"]),
            closed_on=_d(r["closed_on"]),
            closed_reason=_s(r["closed_reason"]),
            note=_s(r["note"]),
            created_at=from_iso(str(r["created_at"])),
        )


@dataclass(frozen=True)
class NewPick:
    ledger_id: str
    rule_id: str
    instrument_id: str
    status: str
    picked_on: date
    picked_price: Decimal
    benchmark: str
    benchmark_price: Decimal
    theme: str
    rationale: str
    confirm: list[dict[str, Any]]
    invalidate: list[dict[str, Any]]
    buy: list[dict[str, Any]]
    confidence: str | None
    source: str
    note: str | None = None
    texts: dict[str, Any] | None = None


def insert_pick(conn: sqlite3.Connection, pick: NewPick, at: datetime) -> int:
    cur = conn.execute(
        "INSERT INTO picks (ledger_id, rule_id, instrument_id, status, picked_on, picked_price,"
        " benchmark, benchmark_price, theme, rationale, confirm, invalidate, buy, texts,"
        " confidence, source, note, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            pick.ledger_id,
            pick.rule_id,
            pick.instrument_id,
            pick.status,
            pick.picked_on.isoformat(),
            str(pick.picked_price),
            pick.benchmark,
            str(pick.benchmark_price),
            pick.theme,
            pick.rationale,
            dumps(pick.confirm),
            dumps(pick.invalidate),
            dumps(pick.buy),
            dumps(pick.texts or {}),
            pick.confidence,
            pick.source,
            pick.note,
            to_iso(at),
            to_iso(at),
        ),
    )
    return _id(cur)


def get_pick(conn: sqlite3.Connection, pick_id: int) -> PickRow:
    row = _one(conn, "SELECT * FROM picks WHERE pick_id = ?", (pick_id,))
    if row is None:
        raise NotFoundError(f"pick {pick_id}")
    return PickRow.from_row(row)


def picks_of(
    conn: sqlite3.Connection,
    ledger_id: str,
    rule_id: str,
    statuses: Sequence[str] | None = None,
) -> list[PickRow]:
    sql = "SELECT * FROM picks WHERE ledger_id = ? AND rule_id = ?"
    params: list[Any] = [ledger_id, rule_id]
    if statuses:
        sql += f" AND status IN ({','.join('?' * len(statuses))})"
        params.extend(statuses)
    return [PickRow.from_row(r) for r in _all(conn, sql + " ORDER BY pick_id", params)]


def open_pick(
    conn: sqlite3.Connection, ledger_id: str, rule_id: str, instrument_id: str
) -> PickRow | None:
    row = _one(
        conn,
        "SELECT * FROM picks WHERE ledger_id = ? AND rule_id = ? AND instrument_id = ?"
        " AND status IN ('candidate', 'held')",
        (ledger_id, rule_id, instrument_id),
    )
    return None if row is None else PickRow.from_row(row)


def picks_by_instrument(
    conn: sqlite3.Connection, instrument_id: str, statuses: Sequence[str] = OPEN_PICK
) -> list[PickRow]:
    """Picks of one company in any ledger or rule."""
    return [
        PickRow.from_row(r)
        for r in _all(
            conn,
            f"SELECT * FROM picks WHERE instrument_id = ? AND status IN"
            f" ({','.join('?' * len(statuses))}) ORDER BY pick_id",
            (instrument_id, *statuses),
        )
    ]


_PICK_FIELDS = {
    "status",
    "confirm",
    "invalidate",
    "buy",
    "last_verdict",
    "last_verdict_at",
    "weak_months",
    "decision",
    "decided_at",
    "decision_task_id",
    "shock_until",
    "closed_on",
    "closed_reason",
    "note",
}


def _cell(value: Any) -> Any:
    if isinstance(value, datetime):
        return to_iso(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, (list, dict)):
        return dumps(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def update_pick(conn: sqlite3.Connection, pick_id: int, at: datetime, **fields: Any) -> None:
    """Set the given columns (None clears them)."""
    unknown = set(fields) - _PICK_FIELDS
    if unknown:
        raise ValueError(f"not pick fields: {sorted(unknown)}")
    if not fields:
        return
    sets = [f"{k} = ?" for k in fields] + ["updated_at = ?"]
    params = [_cell(v) for v in fields.values()] + [to_iso(at), pick_id]
    conn.execute(f"UPDATE picks SET {', '.join(sets)} WHERE pick_id = ?", params)


# ── metric dictionary and metric table ───────────────────────────────────────────────────


def sync_dictionary(conn: sqlite3.Connection, defs: Iterable[MetricDef]) -> None:
    for d in defs:
        conn.execute(
            "INSERT INTO metric_dictionary (key, label, unit_kind, period_kind, source, param,"
            " description) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(key) DO UPDATE SET"
            " label = excluded.label, unit_kind = excluded.unit_kind,"
            " period_kind = excluded.period_kind, source = excluded.source,"
            " param = excluded.param, description = excluded.description",
            (d.key, d.label, d.unit_kind, d.period_kind, d.source, d.param, d.description),
        )


def dictionary_keys(conn: sqlite3.Connection) -> list[str]:
    return [str(r["key"]) for r in _all(conn, "SELECT key FROM metric_dictionary ORDER BY key")]


@dataclass(frozen=True)
class MetricValueRow:
    instrument_id: str
    metric: str
    period: str
    value: Decimal
    unit: str
    filing_id: int | None
    quote: str | None
    source: str
    call_id: int | None
    extracted_at: datetime

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> MetricValueRow:
        return cls(
            instrument_id=str(r["instrument_id"]),
            metric=str(r["metric"]),
            period=str(r["period"]),
            value=Decimal(str(r["value"])),
            unit=str(r["unit"]),
            filing_id=None if r["filing_id"] is None else int(r["filing_id"]),
            quote=_s(r["quote"]),
            source=str(r["source"]),
            call_id=None if r["call_id"] is None else int(r["call_id"]),
            extracted_at=from_iso(str(r["extracted_at"])),
        )


def upsert_metric_value(
    conn: sqlite3.Connection,
    *,
    instrument_id: str,
    metric: str,
    period: str,
    value: Decimal,
    unit: str,
    filing_id: int | None,
    quote: str | None,
    source: str,
    call_id: int | None,
    at: datetime,
) -> None:
    conn.execute(
        "INSERT INTO metric_values (instrument_id, metric, period, value, unit, filing_id, quote,"
        " source, call_id, extracted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(instrument_id, metric, period) DO UPDATE SET value = excluded.value,"
        " unit = excluded.unit, filing_id = excluded.filing_id, quote = excluded.quote,"
        " source = excluded.source, call_id = excluded.call_id,"
        " extracted_at = excluded.extracted_at",
        (
            instrument_id,
            metric,
            period,
            str(value),
            unit,
            filing_id,
            quote,
            source,
            call_id,
            to_iso(at),
        ),
    )


def metric_values(
    conn: sqlite3.Connection, instrument_id: str, metric: str | None = None
) -> list[MetricValueRow]:
    sql = "SELECT * FROM metric_values WHERE instrument_id = ?"
    params: list[Any] = [instrument_id]
    if metric is not None:
        sql += " AND metric = ?"
        params.append(metric)
    return [
        MetricValueRow.from_row(r) for r in _all(conn, sql + " ORDER BY metric, period", params)
    ]


def latest_metric_at(conn: sqlite3.Connection) -> datetime | None:
    row = _one(conn, "SELECT MAX(extracted_at) AS at FROM metric_values WHERE source != 'seed'")
    return None if row is None or row["at"] is None else from_iso(str(row["at"]))


# ── filings ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FilingRow:
    filing_id: int
    instrument_id: str
    source: str
    source_ref: str
    form: str
    items: str | None
    title: str
    filed_on: date
    url: str | None
    kind: str
    status: str
    fetched_at: datetime

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> FilingRow:
        return cls(
            filing_id=int(r["filing_id"]),
            instrument_id=str(r["instrument_id"]),
            source=str(r["source"]),
            source_ref=str(r["source_ref"]),
            form=str(r["form"]),
            items=_s(r["items"]),
            title=str(r["title"]),
            filed_on=date.fromisoformat(str(r["filed_on"])),
            url=_s(r["url"]),
            kind=str(r["kind"]),
            status=str(r["status"]),
            fetched_at=from_iso(str(r["fetched_at"])),
        )


def insert_filing(
    conn: sqlite3.Connection,
    *,
    instrument_id: str,
    source: str,
    source_ref: str,
    form: str,
    items: str | None,
    title: str,
    filed_on: date,
    url: str | None,
    kind: str,
    status: str,
    at: datetime,
) -> tuple[int, bool]:
    """Insert unless the filing is known. Returns (filing_id, inserted)."""
    row = _one(
        conn,
        "SELECT filing_id FROM filings WHERE source = ? AND source_ref = ? AND instrument_id = ?",
        (source, source_ref, instrument_id),
    )
    if row is not None:
        return int(row["filing_id"]), False
    cur = conn.execute(
        "INSERT INTO filings (instrument_id, source, source_ref, form, items, title, filed_on,"
        " url, kind, status, fetched_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            instrument_id,
            source,
            source_ref,
            form,
            items,
            title,
            filed_on.isoformat(),
            url,
            kind,
            status,
            to_iso(at),
        ),
    )
    return _id(cur), True


def get_filing(conn: sqlite3.Connection, filing_id: int) -> FilingRow:
    row = _one(conn, "SELECT * FROM filings WHERE filing_id = ?", (filing_id,))
    if row is None:
        raise NotFoundError(f"filing {filing_id}")
    return FilingRow.from_row(row)


def set_filing_status(conn: sqlite3.Connection, filing_id: int, status: str) -> None:
    conn.execute("UPDATE filings SET status = ? WHERE filing_id = ?", (status, filing_id))


def filings_of(
    conn: sqlite3.Connection, instrument_id: str, since: date | None = None
) -> list[FilingRow]:
    sql = "SELECT * FROM filings WHERE instrument_id = ?"
    params: list[Any] = [instrument_id]
    if since is not None:
        sql += " AND filed_on >= ?"
        params.append(since.isoformat())
    return [
        FilingRow.from_row(r) for r in _all(conn, sql + " ORDER BY filed_on, filing_id", params)
    ]


def latest_filings(conn: sqlite3.Connection, limit: int = 20) -> list[FilingRow]:
    return [
        FilingRow.from_row(r)
        for r in _all(
            conn,
            "SELECT * FROM filings ORDER BY filed_on DESC, filing_id DESC LIMIT ?",
            (limit,),
        )
    ]


# ── AI tasks and calls ───────────────────────────────────────────────────────────────────

TASK_KINDS = (
    "extract",
    "screen",
    "sell-confirm",
    "buy-confirm",
    "monthly-review",
    "discovery",
    "switch",
)


@dataclass(frozen=True)
class TaskRow:
    task_id: int
    kind: str
    status: str
    ledger_id: str
    rule_id: str
    pick_id: int | None
    filing_id: int | None
    trigger: str
    detail: dict[str, Any]
    dedup_key: str
    not_before: datetime
    attempts: int
    last_error: str | None
    result: dict[str, Any] | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> TaskRow:
        detail = loads(str(r["detail"])) or {}
        result = loads(_s(r["result"]))
        return cls(
            task_id=int(r["task_id"]),
            kind=str(r["kind"]),
            status=str(r["status"]),
            ledger_id=str(r["ledger_id"]),
            rule_id=str(r["rule_id"]),
            pick_id=None if r["pick_id"] is None else int(r["pick_id"]),
            filing_id=None if r["filing_id"] is None else int(r["filing_id"]),
            trigger=str(r["trigger"]),
            detail=detail if isinstance(detail, dict) else {},
            dedup_key=str(r["dedup_key"]),
            not_before=from_iso(str(r["not_before"])),
            attempts=int(r["attempts"]),
            last_error=_s(r["last_error"]),
            result=result if isinstance(result, dict) else None,
            created_at=from_iso(str(r["created_at"])),
            started_at=_dt(r["started_at"]),
            finished_at=_dt(r["finished_at"]),
        )


def enqueue_task(
    conn: sqlite3.Connection,
    *,
    kind: str,
    ledger_id: str,
    rule_id: str,
    trigger: str,
    dedup_key: str,
    at: datetime,
    not_before: datetime | None = None,
    pick_id: int | None = None,
    filing_id: int | None = None,
    detail: Mapping[str, Any] | None = None,
) -> tuple[int, bool]:
    """Queue an AI task unless one with the same key exists. Returns (task_id, inserted)."""
    if kind not in TASK_KINDS:
        raise ValueError(f"not a task kind: {kind}")
    row = _one(conn, "SELECT task_id FROM ai_tasks WHERE dedup_key = ?", (dedup_key,))
    if row is not None:
        return int(row["task_id"]), False
    cur = conn.execute(
        "INSERT INTO ai_tasks (kind, status, ledger_id, rule_id, pick_id, filing_id, trigger,"
        " detail, dedup_key, not_before, created_at) VALUES (?, 'pending', ?, ?, ?, ?, ?, ?, ?,"
        " ?, ?)",
        (
            kind,
            ledger_id,
            rule_id,
            pick_id,
            filing_id,
            trigger,
            dumps(dict(detail or {})),
            dedup_key,
            to_iso(not_before or at),
            to_iso(at),
        ),
    )
    return _id(cur), True


def get_task(conn: sqlite3.Connection, task_id: int) -> TaskRow:
    row = _one(conn, "SELECT * FROM ai_tasks WHERE task_id = ?", (task_id,))
    if row is None:
        raise NotFoundError(f"task {task_id}")
    return TaskRow.from_row(row)


# The runner takes cheap and urgent work first: reading a filing feeds the daily checks, selling
# decisions come before buying ones, the quarterly discovery last.
TASK_ORDER = {
    "extract": 0,
    "screen": 1,
    "sell-confirm": 2,
    "monthly-review": 3,
    "buy-confirm": 4,
    "switch": 5,
    "discovery": 6,
}


def due_tasks(conn: sqlite3.Connection, at: datetime, max_attempts: int) -> list[TaskRow]:
    rows = [
        TaskRow.from_row(r)
        for r in _all(
            conn,
            "SELECT * FROM ai_tasks WHERE status IN ('pending', 'failed') AND not_before <= ?"
            " AND attempts < ? ORDER BY task_id",
            (to_iso(at), max_attempts),
        )
    ]
    rows.sort(key=lambda t: (TASK_ORDER[t.kind], t.task_id))
    return rows


def tasks_of(
    conn: sqlite3.Connection,
    *,
    kind: str | None = None,
    statuses: Sequence[str] | None = None,
    pick_id: int | None = None,
) -> list[TaskRow]:
    sql = "SELECT * FROM ai_tasks WHERE 1 = 1"
    params: list[Any] = []
    if kind is not None:
        sql += " AND kind = ?"
        params.append(kind)
    if statuses:
        sql += f" AND status IN ({','.join('?' * len(statuses))})"
        params.extend(statuses)
    if pick_id is not None:
        sql += " AND pick_id = ?"
        params.append(pick_id)
    return [TaskRow.from_row(r) for r in _all(conn, sql + " ORDER BY task_id", params)]


def extract_tasks_of_instrument(conn: sqlite3.Connection, instrument_id: str) -> list[TaskRow]:
    return [
        TaskRow.from_row(r)
        for r in _all(
            conn,
            "SELECT t.* FROM ai_tasks t JOIN filings f ON f.filing_id = t.filing_id"
            " WHERE t.kind = 'extract' AND f.instrument_id = ? ORDER BY t.task_id",
            (instrument_id,),
        )
    ]


def defer_task(
    conn: sqlite3.Connection, task_id: int, not_before: datetime, error: str | None
) -> None:
    """Try again later without counting an attempt (a source was down, not the AI)."""
    conn.execute(
        "UPDATE ai_tasks SET not_before = ?, last_error = ? WHERE task_id = ?",
        (to_iso(not_before), error, task_id),
    )


def last_done(conn: sqlite3.Connection, kind: str, ledger_id: str) -> TaskRow | None:
    row = _one(
        conn,
        "SELECT * FROM ai_tasks WHERE kind = ? AND ledger_id = ? AND status = 'done'"
        " ORDER BY finished_at DESC, task_id DESC LIMIT 1",
        (kind, ledger_id),
    )
    return None if row is None else TaskRow.from_row(row)


def start_task(conn: sqlite3.Connection, task_id: int, at: datetime) -> None:
    conn.execute(
        "UPDATE ai_tasks SET status = 'running', attempts = attempts + 1, started_at = ?"
        " WHERE task_id = ?",
        (to_iso(at), task_id),
    )


def finish_task(
    conn: sqlite3.Connection,
    task_id: int,
    at: datetime,
    *,
    status: str,
    result: Mapping[str, Any] | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE ai_tasks SET status = ?, result = ?, last_error = ?, finished_at = ?"
        " WHERE task_id = ?",
        (status, None if result is None else dumps(dict(result)), error, to_iso(at), task_id),
    )


@dataclass(frozen=True)
class CallRow:
    call_id: int
    task_id: int | None
    purpose: str
    caller: str
    model: str
    effort: str | None
    web: bool
    prompt: str
    input: str
    output: Any
    usage: dict[str, Any] | None
    tokens: int
    cost_usd: Decimal | None
    duration_ms: int | None
    exit_code: int | None
    error: str | None
    started_at: datetime
    finished_at: datetime | None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> CallRow:
        usage = loads(_s(r["usage"]))
        return cls(
            call_id=int(r["call_id"]),
            task_id=None if r["task_id"] is None else int(r["task_id"]),
            purpose=str(r["purpose"]),
            caller=str(r["caller"]),
            model=str(r["model"]),
            effort=_s(r["effort"]),
            web=bool(r["web"]),
            prompt=str(r["prompt"]),
            input=str(r["input"]),
            output=loads(_s(r["output"])),
            usage=usage if isinstance(usage, dict) else None,
            tokens=int(r["tokens"]),
            cost_usd=_dec(r["cost_usd"]),
            duration_ms=None if r["duration_ms"] is None else int(r["duration_ms"]),
            exit_code=None if r["exit_code"] is None else int(r["exit_code"]),
            error=_s(r["error"]),
            started_at=from_iso(str(r["started_at"])),
            finished_at=_dt(r["finished_at"]),
        )

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.error is None and self.output is not None


def insert_call(
    conn: sqlite3.Connection,
    *,
    task_id: int | None,
    purpose: str,
    caller: str,
    model: str,
    effort: str | None,
    web: bool,
    prompt: str,
    input_text: str,
    output: Any,
    usage: Mapping[str, Any] | None,
    tokens: int,
    cost_usd: Decimal | None,
    duration_ms: int | None,
    exit_code: int | None,
    error: str | None,
    started_at: datetime,
    finished_at: datetime | None,
) -> int:
    cur = conn.execute(
        "INSERT INTO ai_calls (task_id, purpose, caller, model, effort, web, prompt, input,"
        " output, usage, tokens, cost_usd, duration_ms, exit_code, error, started_at,"
        " finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            task_id,
            purpose,
            caller,
            model,
            effort,
            1 if web else 0,
            prompt,
            input_text,
            None if output is None else dumps(output),
            None if usage is None else dumps(dict(usage)),
            tokens,
            None if cost_usd is None else str(cost_usd),
            duration_ms,
            exit_code,
            error,
            to_iso(started_at),
            None if finished_at is None else to_iso(finished_at),
        ),
    )
    return _id(cur)


def calls_of_task(conn: sqlite3.Connection, task_id: int) -> list[CallRow]:
    return [
        CallRow.from_row(r)
        for r in _all(conn, "SELECT * FROM ai_calls WHERE task_id = ? ORDER BY call_id", (task_id,))
    ]


def get_call(conn: sqlite3.Connection, call_id: int) -> CallRow:
    row = _one(conn, "SELECT * FROM ai_calls WHERE call_id = ?", (call_id,))
    if row is None:
        raise NotFoundError(f"call {call_id}")
    return CallRow.from_row(row)


def tokens_between(conn: sqlite3.Connection, start: datetime, end: datetime) -> int:
    row = _one(
        conn,
        "SELECT COALESCE(SUM(tokens), 0) AS n FROM ai_calls"
        " WHERE started_at >= ? AND started_at < ?",
        (to_iso(start), to_iso(end)),
    )
    return 0 if row is None else int(row["n"])


def last_calls(conn: sqlite3.Connection, limit: int = 1) -> list[CallRow]:
    return [
        CallRow.from_row(r)
        for r in _all(conn, "SELECT * FROM ai_calls ORDER BY call_id DESC LIMIT ?", (limit,))
    ]


def last_ok_call(conn: sqlite3.Connection) -> CallRow | None:
    row = _one(
        conn,
        "SELECT * FROM ai_calls WHERE exit_code = 0 AND error IS NULL AND output IS NOT NULL"
        " ORDER BY call_id DESC LIMIT 1",
    )
    return None if row is None else CallRow.from_row(row)


# ── switches and scores ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class SwitchRow:
    switch_id: int
    ledger_id: str
    rule_id: str
    sold_pick_id: int
    bought_pick_id: int
    decided_on: date
    task_id: int | None
    costs: dict[str, Any]

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> SwitchRow:
        costs = loads(str(r["costs"])) or {}
        return cls(
            switch_id=int(r["switch_id"]),
            ledger_id=str(r["ledger_id"]),
            rule_id=str(r["rule_id"]),
            sold_pick_id=int(r["sold_pick_id"]),
            bought_pick_id=int(r["bought_pick_id"]),
            decided_on=date.fromisoformat(str(r["decided_on"])),
            task_id=None if r["task_id"] is None else int(r["task_id"]),
            costs=costs if isinstance(costs, dict) else {},
        )


def insert_switch(
    conn: sqlite3.Connection,
    *,
    ledger_id: str,
    rule_id: str,
    sold_pick_id: int,
    bought_pick_id: int,
    decided_on: date,
    task_id: int | None,
    costs: Mapping[str, Any],
    at: datetime,
) -> int:
    cur = conn.execute(
        "INSERT INTO switches (ledger_id, rule_id, sold_pick_id, bought_pick_id, decided_on,"
        " task_id, costs, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            ledger_id,
            rule_id,
            sold_pick_id,
            bought_pick_id,
            decided_on.isoformat(),
            task_id,
            dumps(dict(costs)),
            to_iso(at),
        ),
    )
    return _id(cur)


def switches_of(conn: sqlite3.Connection, ledger_id: str, rule_id: str) -> list[SwitchRow]:
    return [
        SwitchRow.from_row(r)
        for r in _all(
            conn,
            "SELECT * FROM switches WHERE ledger_id = ? AND rule_id = ? ORDER BY switch_id",
            (ledger_id, rule_id),
        )
    ]


@dataclass(frozen=True)
class ScoreRow:
    kind: str
    ref_id: int
    horizon_months: int
    start_on: date
    due_on: date
    end_on: date
    value_return: Decimal
    index_return: Decimal
    excess: Decimal
    scored_at: datetime

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> ScoreRow:
        return cls(
            kind=str(r["kind"]),
            ref_id=int(r["ref_id"]),
            horizon_months=int(r["horizon_months"]),
            start_on=date.fromisoformat(str(r["start_on"])),
            due_on=date.fromisoformat(str(r["due_on"])),
            end_on=date.fromisoformat(str(r["end_on"])),
            value_return=Decimal(str(r["value_return"])),
            index_return=Decimal(str(r["index_return"])),
            excess=Decimal(str(r["excess"])),
            scored_at=from_iso(str(r["scored_at"])),
        )


def upsert_score(conn: sqlite3.Connection, score: ScoreRow) -> None:
    conn.execute(
        "INSERT INTO scores (kind, ref_id, horizon_months, start_on, due_on, end_on,"
        " value_return, index_return, excess, scored_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(kind, ref_id, horizon_months) DO UPDATE SET start_on = excluded.start_on,"
        " due_on = excluded.due_on, end_on = excluded.end_on,"
        " value_return = excluded.value_return, index_return = excluded.index_return,"
        " excess = excluded.excess, scored_at = excluded.scored_at",
        (
            score.kind,
            score.ref_id,
            score.horizon_months,
            score.start_on.isoformat(),
            score.due_on.isoformat(),
            score.end_on.isoformat(),
            str(score.value_return),
            str(score.index_return),
            str(score.excess),
            to_iso(score.scored_at),
        ),
    )


def scores_of(conn: sqlite3.Connection, kind: str | None = None) -> list[ScoreRow]:
    sql = "SELECT * FROM scores"
    params: list[Any] = []
    if kind is not None:
        sql += " WHERE kind = ?"
        params.append(kind)
    return [
        ScoreRow.from_row(r)
        for r in _all(conn, sql + " ORDER BY kind, ref_id, horizon_months", params)
    ]


# ── the 'vs index' line, job runs, source states ─────────────────────────────────────────


def upsert_rule_daily(
    conn: sqlite3.Connection,
    ledger_id: str,
    rule_id: str,
    d: date,
    excess_pp: Decimal | None,
    details: Mapping[str, Any],
    at: datetime,
) -> None:
    conn.execute(
        "INSERT INTO rule_daily (ledger_id, rule_id, date, excess_pp, details, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(ledger_id, rule_id, date) DO UPDATE SET"
        " excess_pp = excluded.excess_pp, details = excluded.details,"
        " updated_at = excluded.updated_at",
        (
            ledger_id,
            rule_id,
            d.isoformat(),
            None if excess_pp is None else str(excess_pp),
            dumps(dict(details)),
            to_iso(at),
        ),
    )


def rule_daily(
    conn: sqlite3.Connection, ledger_id: str, rule_id: str
) -> list[tuple[date, Decimal | None]]:
    return [
        (date.fromisoformat(str(r["date"])), _dec(r["excess_pp"]))
        for r in _all(
            conn,
            "SELECT date, excess_pp FROM rule_daily WHERE ledger_id = ? AND rule_id = ?"
            " ORDER BY date",
            (ledger_id, rule_id),
        )
    ]


def latest_pick_excess(
    conn: sqlite3.Connection, ledger_id: str, rule_id: str
) -> dict[int, Decimal]:
    """Each pick's excess over its index in %p, as the last watch stored it."""
    row = _one(
        conn,
        "SELECT details FROM rule_daily WHERE ledger_id = ? AND rule_id = ?"
        " ORDER BY date DESC LIMIT 1",
        (ledger_id, rule_id),
    )
    details = loads(str(row["details"])) if row is not None else None
    picks = details.get("picks") if isinstance(details, dict) else None
    if not isinstance(picks, dict):
        return {}
    return {int(k): Decimal(str(v)) for k, v in picks.items()}


@dataclass(frozen=True)
class JobRunRow:
    run_id: int
    job: str
    ledger_id: str | None
    run_date: date
    started_at: datetime
    ended_at: datetime | None
    result: str | None
    error: str | None
    details: dict[str, Any]

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> JobRunRow:
        details = loads(str(r["details"])) or {}
        return cls(
            run_id=int(r["run_id"]),
            job=str(r["job"]),
            ledger_id=_s(r["ledger_id"]),
            run_date=date.fromisoformat(str(r["run_date"])),
            started_at=from_iso(str(r["started_at"])),
            ended_at=_dt(r["ended_at"]),
            result=_s(r["result"]),
            error=_s(r["error"]),
            details=details if isinstance(details, dict) else {},
        )


def insert_job_run(
    conn: sqlite3.Connection,
    *,
    job: str,
    ledger_id: str | None,
    run_date: date,
    started_at: datetime,
    ended_at: datetime,
    result: str,
    error: str | None,
    details: Mapping[str, Any],
) -> int:
    cur = conn.execute(
        "INSERT INTO job_runs (job, ledger_id, run_date, started_at, ended_at, result, error,"
        " details) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            job,
            ledger_id,
            run_date.isoformat(),
            to_iso(started_at),
            to_iso(ended_at),
            result,
            error,
            dumps(dict(details)),
        ),
    )
    return _id(cur)


def job_runs_on(conn: sqlite3.Connection, job: str, d: date) -> list[JobRunRow]:
    return [
        JobRunRow.from_row(r)
        for r in _all(
            conn,
            "SELECT * FROM job_runs WHERE job = ? AND run_date = ? ORDER BY run_id",
            (job, d.isoformat()),
        )
    ]


def job_runs_of(
    conn: sqlite3.Connection, job: str, ledger_id: str | None, limit: int = 50
) -> list[JobRunRow]:
    """The latest runs of a job (oldest first)."""
    rows = _all(
        conn,
        "SELECT * FROM job_runs WHERE job = ? AND ledger_id IS ? ORDER BY run_id DESC LIMIT ?",
        (job, ledger_id, limit),
    )
    return [JobRunRow.from_row(r) for r in reversed(rows)]


def last_job_run(conn: sqlite3.Connection, job: str) -> JobRunRow | None:
    row = _one(conn, "SELECT * FROM job_runs WHERE job = ? ORDER BY run_id DESC LIMIT 1", (job,))
    return None if row is None else JobRunRow.from_row(row)


@dataclass(frozen=True)
class SourceStateRow:
    source_id: str
    state: str
    detail: str | None
    attempted_at: datetime | None
    ok_at: datetime | None

    @classmethod
    def from_row(cls, r: sqlite3.Row) -> SourceStateRow:
        return cls(
            source_id=str(r["source_id"]),
            state=str(r["state"]),
            detail=_s(r["detail"]),
            attempted_at=_dt(r["attempted_at"]),
            ok_at=_dt(r["ok_at"]),
        )


def set_source_state(
    conn: sqlite3.Connection, source_id: str, state: str, detail: str | None, at: datetime
) -> None:
    """Record an attempt. 'ok' also moves the last-success time."""
    conn.execute(
        "INSERT INTO source_states (source_id, state, detail, attempted_at, ok_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(source_id) DO UPDATE SET state = excluded.state,"
        " detail = excluded.detail, attempted_at = excluded.attempted_at,"
        " ok_at = COALESCE(excluded.ok_at, source_states.ok_at),"
        " updated_at = excluded.updated_at",
        (
            source_id,
            state,
            detail,
            to_iso(at),
            to_iso(at) if state == "ok" else None,
            to_iso(at),
        ),
    )


def source_state(conn: sqlite3.Connection, source_id: str) -> SourceStateRow | None:
    row = _one(conn, "SELECT * FROM source_states WHERE source_id = ?", (source_id,))
    return None if row is None else SourceStateRow.from_row(row)
