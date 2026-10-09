"""Typed rows. Each from_row() turns a sqlite3.Row into exact Python values."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from autotrade.db.connection import loads
from autotrade.domain.instruments import Currency, Instrument, Kind, Market
from autotrade.market.types import Bar, FxQuote
from autotrade.timeutil import from_iso

_Date = date  # SnapshotRow has a field named 'date'


def _dec(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _req_dec(value: Any) -> Decimal:
    if value is None:
        raise ValueError("missing decimal")
    return Decimal(str(value))


def _date(value: Any) -> date | None:
    return None if value is None else date.fromisoformat(str(value))


def _dt(value: Any) -> datetime | None:
    return None if value is None else from_iso(str(value))


def _str(value: Any) -> str | None:
    return None if value is None else str(value)


def instrument_from_row(row: sqlite3.Row) -> Instrument:
    return Instrument(
        instrument_id=str(row["instrument_id"]),
        market=Market(str(row["market"])),
        currency=Currency(str(row["currency"])),
        kind=Kind(str(row["kind"])),
        ticker=str(row["ticker"]),
        name=str(row["name"]),
        yahoo_symbol=str(row["yahoo_symbol"]),
    )


@dataclass(frozen=True)
class LedgerRow:
    ledger_id: str
    name: str
    started_at: datetime | None
    start_date: date | None
    start_amount: Decimal | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> LedgerRow:
        return cls(
            ledger_id=str(row["ledger_id"]),
            name=str(row["name"]),
            started_at=_dt(row["started_at"]),
            start_date=_date(row["start_date"]),
            start_amount=_dec(row["start_amount"]),
        )


@dataclass(frozen=True)
class RuleRow:
    rule_id: str
    name: str
    kind: str
    definition: dict[str, Any]
    enabled: bool

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> RuleRow:
        definition = loads(str(row["definition"]))
        if not isinstance(definition, dict):
            raise ValueError(f"rule {row['rule_id']}: definition is not an object")
        return cls(
            rule_id=str(row["rule_id"]),
            name=str(row["name"]),
            kind=str(row["kind"]),
            definition=definition,
            enabled=bool(row["enabled"]),
        )


@dataclass(frozen=True)
class RunRow:
    run_id: int
    ledger_id: str
    job: str
    run_date: date
    attempt: int
    started_at: datetime
    ended_at: datetime | None
    duration_ms: int | None
    result: str | None
    error: str | None
    details: dict[str, Any]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> RunRow:
        details = loads(str(row["details"])) or {}
        return cls(
            run_id=int(row["run_id"]),
            ledger_id=str(row["ledger_id"]),
            job=str(row["job"]),
            run_date=date.fromisoformat(str(row["run_date"])),
            attempt=int(row["attempt"]),
            started_at=from_iso(str(row["started_at"])),
            ended_at=_dt(row["ended_at"]),
            duration_ms=None if row["duration_ms"] is None else int(row["duration_ms"]),
            result=_str(row["result"]),
            error=_str(row["error"]),
            details=details if isinstance(details, dict) else {},
        )


@dataclass(frozen=True)
class PlanRow:
    plan_id: int
    ledger_id: str
    rule_id: str
    plan_date: date
    reason: str
    status: str
    basis: dict[str, Any]
    weights_before: dict[str, Any]
    weights_after_est: dict[str, Any]
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> PlanRow:
        return cls(
            plan_id=int(row["plan_id"]),
            ledger_id=str(row["ledger_id"]),
            rule_id=str(row["rule_id"]),
            plan_date=date.fromisoformat(str(row["plan_date"])),
            reason=str(row["reason"]),
            status=str(row["status"]),
            basis=loads(str(row["basis"])) or {},
            weights_before=loads(str(row["weights_before"])) or {},
            weights_after_est=loads(str(row["weights_after_est"])) or {},
            created_at=from_iso(str(row["created_at"])),
            completed_at=_dt(row["completed_at"]),
        )


@dataclass(frozen=True)
class StageRow:
    stage_id: int
    plan_id: int
    seq: int
    kind: str
    market: str
    scheduled_at: datetime
    due_at: datetime
    status: str
    attempts: int
    depends_on: tuple[int, ...]
    last_error: str | None
    completed_at: datetime | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> StageRow:
        deps = loads(str(row["depends_on"])) or []
        return cls(
            stage_id=int(row["stage_id"]),
            plan_id=int(row["plan_id"]),
            seq=int(row["seq"]),
            kind=str(row["kind"]),
            market=str(row["market"]),
            scheduled_at=from_iso(str(row["scheduled_at"])),
            due_at=from_iso(str(row["due_at"])),
            status=str(row["status"]),
            attempts=int(row["attempts"]),
            depends_on=tuple(int(d) for d in deps),
            last_error=_str(row["last_error"]),
            completed_at=_dt(row["completed_at"]),
        )


@dataclass(frozen=True)
class OrderRow:
    order_id: int
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
    status: str
    attempt: int
    retry_of: int | None
    failure_reason: str | None
    failure_detail: str | None
    retry_at: datetime | None
    manual: bool
    executed_at: datetime | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> OrderRow:
        return cls(
            order_id=int(row["order_id"]),
            idem_key=str(row["idem_key"]),
            ledger_id=str(row["ledger_id"]),
            plan_id=int(row["plan_id"]),
            stage_id=int(row["stage_id"]),
            stage=str(row["stage"]),
            market=str(row["market"]),
            instrument_id=_str(row["instrument_id"]),
            side=str(row["side"]),
            fx_direction=_str(row["fx_direction"]),
            currency=Currency(str(row["currency"])),
            qty=None if row["qty"] is None else int(row["qty"]),
            est_price=_dec(row["est_price"]),
            est_amount=_req_dec(row["est_amount"]),
            est_fee=_req_dec(row["est_fee"]),
            est_rate=_dec(row["est_rate"]),
            est_received=_dec(row["est_received"]),
            status=str(row["status"]),
            attempt=int(row["attempt"]),
            retry_of=None if row["retry_of"] is None else int(row["retry_of"]),
            failure_reason=_str(row["failure_reason"]),
            failure_detail=_str(row["failure_detail"]),
            retry_at=_dt(row["retry_at"]),
            manual=bool(row["manual"]),
            executed_at=_dt(row["executed_at"]),
        )


@dataclass(frozen=True)
class FillRow:
    fill_id: int
    order_id: int
    ledger_id: str
    kind: str
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

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> FillRow:
        return cls(
            fill_id=int(row["fill_id"]),
            order_id=int(row["order_id"]),
            ledger_id=str(row["ledger_id"]),
            kind=str(row["kind"]),
            instrument_id=_str(row["instrument_id"]),
            side=str(row["side"]),
            fx_direction=_str(row["fx_direction"]),
            currency=Currency(str(row["currency"])),
            qty=None if row["qty"] is None else int(row["qty"]),
            price=_dec(row["price"]),
            gross=_req_dec(row["gross"]),
            fee=_req_dec(row["fee"]),
            fee_krw=_req_dec(row["fee_krw"]),
            krw_rate=_dec(row["krw_rate"]),
            received=_dec(row["received"]),
            filled_at=from_iso(str(row["filled_at"])),
            price_source=str(row["price_source"]),
            executor=str(row["executor"]),
        )


@dataclass(frozen=True)
class EventRow:
    event_id: int
    ledger_id: str
    kind: str
    event_date: date
    occurred_at: datetime
    rule_id: str | None
    plan_id: int | None
    status: str | None
    amount: Decimal | None
    currency: Currency | None
    payload: dict[str, Any]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> EventRow:
        payload = loads(str(row["payload"])) or {}
        return cls(
            event_id=int(row["event_id"]),
            ledger_id=str(row["ledger_id"]),
            kind=str(row["kind"]),
            event_date=date.fromisoformat(str(row["event_date"])),
            occurred_at=from_iso(str(row["occurred_at"])),
            rule_id=_str(row["rule_id"]),
            plan_id=None if row["plan_id"] is None else int(row["plan_id"]),
            status=_str(row["status"]),
            amount=_dec(row["amount"]),
            currency=None if row["currency"] is None else Currency(str(row["currency"])),
            payload=payload if isinstance(payload, dict) else {},
        )


def bar_from_row(row: sqlite3.Row) -> Bar:
    return Bar(
        instrument_id=str(row["instrument_id"]),
        session_date=date.fromisoformat(str(row["session_date"])),
        open=_dec(row["open"]),
        high=_dec(row["high"]),
        low=_dec(row["low"]),
        close=_req_dec(row["close"]),
        source=str(row["source"]),
    )


def fx_from_row(row: sqlite3.Row) -> FxQuote:
    return FxQuote(
        rate=_req_dec(row["rate"]),
        as_of=from_iso(str(row["as_of"])),
        source=str(row["source"]),
    )


@dataclass(frozen=True)
class SnapshotRow:
    ledger_id: str
    date: date
    valued_at: datetime
    total_krw: Decimal
    positions: list[dict[str, Any]]
    cash_krw: Decimal
    cash_usd: Decimal
    cash_parts: list[dict[str, Any]]
    fx_rate: Decimal
    fx_at: datetime
    kr_close_date: _Date | None
    us_close_date: _Date | None
    contributions: Decimal
    pnl_krw: Decimal
    baseline_krw: Decimal | None
    baseline_units: dict[str, str] | None
    stale: list[str]

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> SnapshotRow:
        return cls(
            ledger_id=str(row["ledger_id"]),
            date=date.fromisoformat(str(row["date"])),
            valued_at=from_iso(str(row["valued_at"])),
            total_krw=_req_dec(row["total_krw"]),
            positions=loads(str(row["positions"])) or [],
            cash_krw=_req_dec(row["cash_krw"]),
            cash_usd=_req_dec(row["cash_usd"]),
            cash_parts=loads(str(row["cash_parts"])) or [],
            fx_rate=_req_dec(row["fx_rate"]),
            fx_at=from_iso(str(row["fx_at"])),
            kr_close_date=_date(row["kr_close_date"]),
            us_close_date=_date(row["us_close_date"]),
            contributions=_req_dec(row["contributions"]),
            pnl_krw=_req_dec(row["pnl_krw"]),
            baseline_krw=_dec(row["baseline_krw"]),
            baseline_units=loads(_str(row["baseline_units"])),
            stale=loads(str(row["stale"])) or [],
        )


@dataclass(frozen=True)
class FreshnessRow:
    series: str
    state: str
    basis: str | None
    expected: str | None
    missing_sessions: int
    source: str | None
    fetched_at: datetime | None
    attempted_at: datetime | None
    error: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> FreshnessRow:
        return cls(
            series=str(row["series"]),
            state=str(row["state"]),
            basis=_str(row["basis"]),
            expected=_str(row["expected"]),
            missing_sessions=int(row["missing_sessions"]),
            source=_str(row["source"]),
            fetched_at=_dt(row["fetched_at"]),
            attempted_at=_dt(row["attempted_at"]),
            error=_str(row["error"]),
        )
