"""Versioned schema migrations for data/autotrade.db.

Add a new (version, name, sql) entry to change the schema; never edit an applied one.
Money is stored as TEXT holding an exact Decimal, dates as 'YYYY-MM-DD' (KST for Korean and run
dates, ET for US session dates), times as UTC ISO 8601. Enum values follow autotrade/CONTRACT.md.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from autotrade.db.connection import transaction
from autotrade.timeutil import UTC, to_iso

V1 = """
CREATE TABLE settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE ledgers (
    ledger_id          TEXT PRIMARY KEY CHECK (ledger_id IN ('paper', 'live')),
    name               TEXT NOT NULL,
    base_currency      TEXT NOT NULL DEFAULT 'KRW',
    started_at         TEXT,
    start_date         TEXT,
    start_amount       TEXT,
    realized_krw       TEXT NOT NULL DEFAULT '0',
    fees_krw           TEXT NOT NULL DEFAULT '0',
    contributions_krw  TEXT NOT NULL DEFAULT '0',
    income_krw         TEXT NOT NULL DEFAULT '0',
    created_at         TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE instruments (
    instrument_id  TEXT PRIMARY KEY,
    market         TEXT NOT NULL CHECK (market IN ('KR', 'US')),
    currency       TEXT NOT NULL CHECK (currency IN ('KRW', 'USD')),
    kind           TEXT NOT NULL CHECK (kind IN ('etf', 'stock', 'coin')),
    ticker         TEXT NOT NULL,
    name           TEXT NOT NULL,
    yahoo_symbol   TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

CREATE TABLE rules (
    rule_id     TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL CHECK (kind IN ('fixed', 'ai')),
    definition  TEXT NOT NULL,
    enabled     INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL
);

CREATE TABLE positions (
    ledger_id      TEXT NOT NULL REFERENCES ledgers(ledger_id),
    instrument_id  TEXT NOT NULL REFERENCES instruments(instrument_id),
    currency       TEXT NOT NULL,
    qty            INTEGER NOT NULL CHECK (qty > 0),
    cost_native    TEXT NOT NULL,
    cost_krw       TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (ledger_id, instrument_id)
);

CREATE TABLE cash (
    ledger_id   TEXT NOT NULL REFERENCES ledgers(ledger_id),
    currency    TEXT NOT NULL CHECK (currency IN ('KRW', 'USD')),
    amount      TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (ledger_id, currency)
);

CREATE TABLE pending_cash (
    pending_id     INTEGER PRIMARY KEY,
    ledger_id      TEXT NOT NULL REFERENCES ledgers(ledger_id),
    currency       TEXT NOT NULL CHECK (currency IN ('KRW', 'USD')),
    purpose        TEXT NOT NULL
                   CHECK (purpose IN ('buy_wait', 'sub_share', 'withdraw_wait', 'new')),
    instrument_id  TEXT REFERENCES instruments(instrument_id),
    amount         TEXT NOT NULL,
    until_date     TEXT,
    updated_at     TEXT NOT NULL,
    CHECK ((purpose = 'buy_wait') = (instrument_id IS NOT NULL)),
    CHECK ((purpose = 'withdraw_wait') = (until_date IS NOT NULL))
);
CREATE INDEX pending_cash_ledger ON pending_cash(ledger_id, purpose);

CREATE TABLE runs (
    run_id       INTEGER PRIMARY KEY,
    ledger_id    TEXT NOT NULL REFERENCES ledgers(ledger_id),
    job          TEXT NOT NULL CHECK (job IN ('check', 'stage', 'snapshot')),
    run_date     TEXT NOT NULL,
    attempt      INTEGER NOT NULL DEFAULT 1,
    scheduled_at TEXT,
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    duration_ms  INTEGER,
    result       TEXT,
    error        TEXT,
    details      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX runs_by_date ON runs(ledger_id, job, run_date);

CREATE TABLE plans (
    plan_id            INTEGER PRIMARY KEY,
    ledger_id          TEXT NOT NULL REFERENCES ledgers(ledger_id),
    rule_id            TEXT NOT NULL REFERENCES rules(rule_id),
    plan_date          TEXT NOT NULL,
    run_id             INTEGER REFERENCES runs(run_id),
    reason             TEXT NOT NULL CHECK (reason IN ('start', 'drift', 'new_cash')),
    status             TEXT NOT NULL
                       CHECK (status IN ('in-progress', 'partial-failed', 'done', 'todo',
                                         'resolved')),
    basis              TEXT NOT NULL,
    weights_before     TEXT NOT NULL,
    weights_after_est  TEXT NOT NULL,
    created_at         TEXT NOT NULL,
    completed_at       TEXT,
    UNIQUE (ledger_id, rule_id, plan_date)
);

CREATE TABLE stages (
    stage_id      INTEGER PRIMARY KEY,
    plan_id       INTEGER NOT NULL REFERENCES plans(plan_id),
    seq           INTEGER NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN ('sell', 'fx', 'buy')),
    market        TEXT NOT NULL CHECK (market IN ('KR', 'US', 'FX')),
    scheduled_at  TEXT NOT NULL,
    due_at        TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('pending', 'done', 'failed', 'todo')),
    attempts      INTEGER NOT NULL DEFAULT 0,
    depends_on    TEXT NOT NULL DEFAULT '[]',
    last_error    TEXT,
    completed_at  TEXT,
    UNIQUE (plan_id, seq)
);
CREATE INDEX stages_due ON stages(status, due_at);

CREATE TABLE orders (
    order_id        INTEGER PRIMARY KEY,
    idem_key        TEXT NOT NULL UNIQUE,
    ledger_id       TEXT NOT NULL REFERENCES ledgers(ledger_id),
    plan_id         INTEGER NOT NULL REFERENCES plans(plan_id),
    stage_id        INTEGER NOT NULL REFERENCES stages(stage_id),
    stage           TEXT NOT NULL CHECK (stage IN ('sell', 'fx', 'buy')),
    market          TEXT NOT NULL CHECK (market IN ('KR', 'US', 'FX')),
    instrument_id   TEXT REFERENCES instruments(instrument_id),
    side            TEXT NOT NULL CHECK (side IN ('buy', 'sell', 'fx')),
    fx_direction    TEXT CHECK (fx_direction IN ('krw_to_usd', 'usd_to_krw')),
    currency        TEXT NOT NULL,
    qty             INTEGER,
    est_price       TEXT,
    est_amount      TEXT NOT NULL,
    est_fee         TEXT NOT NULL DEFAULT '0',
    est_rate        TEXT,
    est_received    TEXT,
    status          TEXT NOT NULL CHECK (status IN ('pending', 'filled', 'failed', 'cancelled')),
    attempt         INTEGER NOT NULL DEFAULT 1,
    retry_of        INTEGER REFERENCES orders(order_id),
    failure_reason  TEXT CHECK (failure_reason IN ('no-quote', 'broker-rejected', 'cancel-failed',
                                                   'other')),
    failure_detail  TEXT,
    retry_at        TEXT,
    manual          INTEGER NOT NULL DEFAULT 0,
    executor        TEXT,
    created_at      TEXT NOT NULL,
    executed_at     TEXT,
    CHECK ((side = 'fx') = (fx_direction IS NOT NULL)),
    CHECK ((side = 'fx') = (instrument_id IS NULL))
);
CREATE INDEX orders_stage ON orders(stage_id, status);

CREATE TABLE fills (
    fill_id        INTEGER PRIMARY KEY,
    order_id       INTEGER NOT NULL UNIQUE REFERENCES orders(order_id),
    ledger_id      TEXT NOT NULL REFERENCES ledgers(ledger_id),
    kind           TEXT NOT NULL CHECK (kind IN ('trade', 'fx')),
    instrument_id  TEXT REFERENCES instruments(instrument_id),
    side           TEXT NOT NULL CHECK (side IN ('buy', 'sell', 'fx')),
    fx_direction   TEXT,
    currency       TEXT NOT NULL,
    qty            INTEGER,
    price          TEXT,
    gross          TEXT NOT NULL,
    fee            TEXT NOT NULL,
    fee_krw        TEXT NOT NULL,
    krw_rate       TEXT,
    received       TEXT,
    filled_at      TEXT NOT NULL,
    price_source   TEXT NOT NULL,
    executor       TEXT NOT NULL CHECK (executor IN ('paper', 'toss'))
);
CREATE INDEX fills_ledger ON fills(ledger_id, filled_at);

CREATE TABLE events (
    event_id     INTEGER PRIMARY KEY,
    ledger_id    TEXT NOT NULL REFERENCES ledgers(ledger_id),
    kind         TEXT NOT NULL CHECK (kind IN ('start', 'rebalance', 'check-failed', 'dividend',
                                                'deposit', 'withdrawal', 'live-on', 'live-off')),
    event_date   TEXT NOT NULL,
    occurred_at  TEXT NOT NULL,
    rule_id      TEXT REFERENCES rules(rule_id),
    plan_id      INTEGER UNIQUE REFERENCES plans(plan_id),
    status       TEXT,
    amount       TEXT,
    currency     TEXT,
    payload      TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE INDEX events_ledger ON events(ledger_id, event_date);
CREATE UNIQUE INDEX events_one_start ON events(ledger_id) WHERE kind = 'start';
CREATE UNIQUE INDEX events_one_check_failure ON events(ledger_id, event_date)
    WHERE kind = 'check-failed';

CREATE TABLE snapshots (
    ledger_id       TEXT NOT NULL REFERENCES ledgers(ledger_id),
    date            TEXT NOT NULL,
    valued_at       TEXT NOT NULL,
    total_krw       TEXT NOT NULL,
    positions       TEXT NOT NULL,
    cash_krw        TEXT NOT NULL,
    cash_usd        TEXT NOT NULL,
    cash_parts      TEXT NOT NULL,
    fx_rate         TEXT NOT NULL,
    fx_at           TEXT NOT NULL,
    kr_close_date   TEXT,
    us_close_date   TEXT,
    contributions   TEXT NOT NULL,
    pnl_krw         TEXT NOT NULL,
    baseline_krw    TEXT,
    baseline_units  TEXT,
    stale           TEXT NOT NULL DEFAULT '[]',
    created_at      TEXT NOT NULL,
    PRIMARY KEY (ledger_id, date)
);

CREATE TABLE market_prices (
    instrument_id  TEXT NOT NULL REFERENCES instruments(instrument_id),
    session_date   TEXT NOT NULL,
    open           TEXT,
    high           TEXT,
    low            TEXT,
    close          TEXT NOT NULL,
    source         TEXT NOT NULL,
    fetched_at     TEXT NOT NULL,
    PRIMARY KEY (instrument_id, session_date)
);

CREATE TABLE fx_rates (
    pair        TEXT NOT NULL,
    as_of       TEXT NOT NULL,
    rate        TEXT NOT NULL,
    source      TEXT NOT NULL,
    fetched_at  TEXT NOT NULL,
    PRIMARY KEY (pair, as_of)
);

CREATE TABLE data_freshness (
    series            TEXT PRIMARY KEY,
    state             TEXT NOT NULL CHECK (state IN ('fresh', 'stale', 'unknown')),
    basis             TEXT,
    expected          TEXT,
    missing_sessions  INTEGER NOT NULL DEFAULT 0,
    cadence           TEXT NOT NULL DEFAULT 'daily',
    source            TEXT,
    fetched_at        TEXT,
    attempted_at      TEXT,
    error             TEXT,
    updated_at        TEXT NOT NULL
)
"""

MIGRATIONS: tuple[tuple[int, str, str], ...] = ((1, "initial schema", V1),)


def _statements(sql: str) -> list[str]:
    return [s.strip() for s in sql.split(";") if s.strip()]


def current_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def migrate(conn: sqlite3.Connection, now: datetime | None = None) -> int:
    """Apply pending migrations, each in its own transaction. Returns the schema version."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
    )
    applied = {int(r[0]) for r in conn.execute("SELECT version FROM schema_migrations")}
    stamp = to_iso(now or datetime.now(UTC))
    for version, name, sql in MIGRATIONS:
        if version in applied:
            continue
        with transaction(conn):
            for statement in _statements(sql):
                conn.execute(statement)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                (version, name, stamp),
            )
    return current_version(conn)
