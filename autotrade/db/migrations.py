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

V2 = """
CREATE TABLE auth_pin (
    id          INTEGER PRIMARY KEY CHECK (id = 1),
    pin_hash    TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE sessions (
    session_id    TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    expires_at    TEXT NOT NULL,
    revoked_at    TEXT,
    revoked_why   TEXT,
    ip            TEXT,
    user_agent    TEXT,
    device_kind   TEXT NOT NULL DEFAULT 'other'
                  CHECK (device_kind IN ('iphone-app', 'iphone-safari', 'mac', 'other')),
    device_name   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX sessions_open ON sessions(revoked_at, expires_at);

CREATE TABLE pin_locks (
    ip            TEXT PRIMARY KEY,
    failures      INTEGER NOT NULL DEFAULT 0,
    locked_until  TEXT,
    updated_at    TEXT NOT NULL
);

CREATE TABLE pin_failures (
    failure_id  INTEGER PRIMARY KEY,
    ip          TEXT NOT NULL,
    at          TEXT NOT NULL
);
CREATE INDEX pin_failures_at ON pin_failures(at);

CREATE TABLE notification_prefs (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    events        TEXT NOT NULL,
    hide_amounts  INTEGER NOT NULL DEFAULT 0,
    saved_at      TEXT NOT NULL
)
"""

# V3: events get a natural key ('ref', unique per ledger: one booking per dividend, one
# resolution per manual action) and the kind 'todo-resolved'. SQLite cannot change a CHECK, so
# the table is rebuilt; nothing references events, so the drop is safe with foreign keys on.
# Dividends announced by the source are market data, like market_prices. The untouched baseline
# keeps the dividends its units earned as cash ('손대지 않았을 때' gets the same dividends).
V3 = """
CREATE TABLE events_v3 (
    event_id     INTEGER PRIMARY KEY,
    ledger_id    TEXT NOT NULL REFERENCES ledgers(ledger_id),
    kind         TEXT NOT NULL CHECK (kind IN ('start', 'rebalance', 'check-failed', 'dividend',
                                                'deposit', 'withdrawal', 'live-on', 'live-off',
                                                'todo-resolved')),
    event_date   TEXT NOT NULL,
    occurred_at  TEXT NOT NULL,
    rule_id      TEXT REFERENCES rules(rule_id),
    plan_id      INTEGER UNIQUE REFERENCES plans(plan_id),
    status       TEXT,
    amount       TEXT,
    currency     TEXT,
    ref          TEXT,
    payload      TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

INSERT INTO events_v3 (event_id, ledger_id, kind, event_date, occurred_at, rule_id, plan_id,
                       status, amount, currency, payload, created_at, updated_at)
    SELECT event_id, ledger_id, kind, event_date, occurred_at, rule_id, plan_id, status, amount,
           currency, payload, created_at, updated_at
    FROM events;

DROP TABLE events;

ALTER TABLE events_v3 RENAME TO events;

CREATE INDEX events_ledger ON events(ledger_id, event_date);
CREATE UNIQUE INDEX events_one_start ON events(ledger_id) WHERE kind = 'start';
CREATE UNIQUE INDEX events_one_check_failure ON events(ledger_id, event_date)
    WHERE kind = 'check-failed';
CREATE UNIQUE INDEX events_ref ON events(ledger_id, ref) WHERE ref IS NOT NULL;

CREATE TABLE dividends (
    instrument_id  TEXT NOT NULL REFERENCES instruments(instrument_id),
    ex_date        TEXT NOT NULL,
    pay_date       TEXT NOT NULL,
    pay_estimated  INTEGER NOT NULL DEFAULT 1,
    per_share      TEXT NOT NULL,
    currency       TEXT NOT NULL CHECK (currency IN ('KRW', 'USD')),
    source         TEXT NOT NULL,
    fetched_at     TEXT NOT NULL,
    PRIMARY KEY (instrument_id, ex_date)
);
CREATE INDEX dividends_paid ON dividends(pay_date);

ALTER TABLE snapshots ADD COLUMN baseline_cash_krw TEXT
"""

# V4: phase 2, the AI rule '3년 발굴' (autotrade/PHASE2.md).
# - plans: the AI rule's plans have reason 'ai' (what they carry is in basis). The CHECK cannot be
#   altered, so the table is rebuilt; stages, orders and events reference it, which is why this
#   migration runs with foreign keys off and checks them before committing (FK_OFF).
# - events: the AI rule's kinds (CONTRACT.md EventKind) join the CHECK.
# - rule_shares: each rule's target share of a ledger (PHASE2.md §1).
# - sleeve_*: what a rule other than the base rule (index_half) owns inside the shared ledger.
#   The base rule's part is the ledger minus the other rules' sleeves.
# - picks (판단 장부), metric_dictionary / metric_values (지표 사전·지표 표), filings (공시),
#   ai_tasks (일감) and ai_calls (호출 기록), scores (채점), switches (바꾸기), rule_daily ('지수
#   대비' line), job_runs (the new jobs' runs), source_states (DART·EDGAR·AI CLI).
V4 = """
CREATE TABLE plans_v4 (
    plan_id            INTEGER PRIMARY KEY,
    ledger_id          TEXT NOT NULL REFERENCES ledgers(ledger_id),
    rule_id            TEXT NOT NULL REFERENCES rules(rule_id),
    plan_date          TEXT NOT NULL,
    run_id             INTEGER REFERENCES runs(run_id),
    reason             TEXT NOT NULL CHECK (reason IN ('start', 'drift', 'new_cash', 'ai')),
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

INSERT INTO plans_v4 SELECT plan_id, ledger_id, rule_id, plan_date, run_id, reason, status, basis,
                            weights_before, weights_after_est, created_at, completed_at
    FROM plans;

DROP TABLE plans;

ALTER TABLE plans_v4 RENAME TO plans;

CREATE TABLE events_v4 (
    event_id     INTEGER PRIMARY KEY,
    ledger_id    TEXT NOT NULL REFERENCES ledgers(ledger_id),
    kind         TEXT NOT NULL CHECK (kind IN ('start', 'rebalance', 'check-failed', 'dividend',
                                                'deposit', 'withdrawal', 'live-on', 'live-off',
                                                'todo-resolved', 'discovery', 'ai-buy',
                                                'ai-sell', 'ai-check', 'monthly-review')),
    event_date   TEXT NOT NULL,
    occurred_at  TEXT NOT NULL,
    rule_id      TEXT REFERENCES rules(rule_id),
    plan_id      INTEGER UNIQUE REFERENCES plans(plan_id),
    status       TEXT,
    amount       TEXT,
    currency     TEXT,
    ref          TEXT,
    payload      TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

INSERT INTO events_v4 SELECT event_id, ledger_id, kind, event_date, occurred_at, rule_id, plan_id,
                             status, amount, currency, ref, payload, created_at, updated_at
    FROM events;

DROP TABLE events;

ALTER TABLE events_v4 RENAME TO events;

CREATE INDEX events_ledger ON events(ledger_id, event_date);
CREATE UNIQUE INDEX events_one_start ON events(ledger_id) WHERE kind = 'start';
CREATE UNIQUE INDEX events_one_check_failure ON events(ledger_id, event_date)
    WHERE kind = 'check-failed';
CREATE UNIQUE INDEX events_ref ON events(ledger_id, ref) WHERE ref IS NOT NULL;

CREATE TABLE rule_shares (
    ledger_id   TEXT NOT NULL REFERENCES ledgers(ledger_id),
    rule_id     TEXT NOT NULL REFERENCES rules(rule_id),
    target_pct  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (ledger_id, rule_id)
);

CREATE TABLE sleeve_positions (
    ledger_id      TEXT NOT NULL REFERENCES ledgers(ledger_id),
    rule_id        TEXT NOT NULL REFERENCES rules(rule_id),
    instrument_id  TEXT NOT NULL REFERENCES instruments(instrument_id),
    currency       TEXT NOT NULL,
    qty            INTEGER NOT NULL CHECK (qty > 0),
    cost_native    TEXT NOT NULL,
    cost_krw       TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (ledger_id, rule_id, instrument_id)
);

CREATE TABLE sleeve_cash (
    ledger_id   TEXT NOT NULL REFERENCES ledgers(ledger_id),
    rule_id     TEXT NOT NULL REFERENCES rules(rule_id),
    currency    TEXT NOT NULL CHECK (currency IN ('KRW', 'USD')),
    amount      TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (ledger_id, rule_id, currency)
);

CREATE TABLE sleeve_totals (
    ledger_id          TEXT NOT NULL REFERENCES ledgers(ledger_id),
    rule_id            TEXT NOT NULL REFERENCES rules(rule_id),
    realized_krw       TEXT NOT NULL DEFAULT '0',
    fees_krw           TEXT NOT NULL DEFAULT '0',
    contributions_krw  TEXT NOT NULL DEFAULT '0',
    income_krw         TEXT NOT NULL DEFAULT '0',
    updated_at         TEXT NOT NULL,
    PRIMARY KEY (ledger_id, rule_id)
);

CREATE TABLE sleeve_flows (
    flow_id      INTEGER PRIMARY KEY,
    ledger_id    TEXT NOT NULL REFERENCES ledgers(ledger_id),
    rule_id      TEXT NOT NULL REFERENCES rules(rule_id),
    event_id     INTEGER,
    kind         TEXT NOT NULL CHECK (kind IN ('start', 'deposit', 'withdrawal', 'dividend')),
    amount       TEXT NOT NULL,
    currency     TEXT NOT NULL CHECK (currency IN ('KRW', 'USD')),
    krw_rate     TEXT,
    occurred_at  TEXT NOT NULL
);
CREATE INDEX sleeve_flows_rule ON sleeve_flows(ledger_id, rule_id, occurred_at);

CREATE TABLE picks (
    pick_id           INTEGER PRIMARY KEY,
    ledger_id         TEXT NOT NULL REFERENCES ledgers(ledger_id),
    rule_id           TEXT NOT NULL REFERENCES rules(rule_id),
    instrument_id     TEXT NOT NULL REFERENCES instruments(instrument_id),
    status            TEXT NOT NULL CHECK (status IN ('candidate', 'held', 'sold', 'expired')),
    picked_on         TEXT NOT NULL,
    picked_price      TEXT NOT NULL,
    benchmark         TEXT NOT NULL,
    benchmark_price   TEXT NOT NULL,
    theme             TEXT NOT NULL,
    rationale         TEXT NOT NULL DEFAULT '',
    confirm           TEXT NOT NULL DEFAULT '[]',
    invalidate        TEXT NOT NULL DEFAULT '[]',
    buy               TEXT NOT NULL DEFAULT '[]',
    texts             TEXT NOT NULL DEFAULT '{}',
    confidence        TEXT,
    source            TEXT NOT NULL,
    last_verdict      TEXT CHECK (last_verdict IN ('hold', 'weaken', 'invalidated')),
    last_verdict_at   TEXT,
    weak_months       INTEGER NOT NULL DEFAULT 0,
    decision          TEXT CHECK (decision IN ('buy', 'sell')),
    decided_at        TEXT,
    decision_task_id  INTEGER,
    shock_until       TEXT,
    closed_on         TEXT,
    closed_reason     TEXT,
    note              TEXT,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);
CREATE UNIQUE INDEX picks_open ON picks(ledger_id, rule_id, instrument_id)
    WHERE status IN ('candidate', 'held');

CREATE TABLE metric_dictionary (
    key          TEXT PRIMARY KEY,
    label        TEXT NOT NULL,
    unit_kind    TEXT NOT NULL CHECK (unit_kind IN ('pct', 'money', 'ratio', 'count', 'any')),
    period_kind  TEXT NOT NULL CHECK (period_kind IN ('quarter', 'month', 'year', 'any')),
    source       TEXT NOT NULL CHECK (source IN ('financials', 'extraction', 'derived')),
    param        TEXT,
    description  TEXT NOT NULL
);

CREATE TABLE filings (
    filing_id      INTEGER PRIMARY KEY,
    instrument_id  TEXT NOT NULL REFERENCES instruments(instrument_id),
    source         TEXT NOT NULL CHECK (source IN ('dart', 'edgar')),
    source_ref     TEXT NOT NULL,
    form           TEXT NOT NULL,
    items          TEXT,
    title          TEXT NOT NULL,
    filed_on       TEXT NOT NULL,
    url            TEXT,
    kind           TEXT NOT NULL CHECK (kind IN ('earnings', 'other', 'skipped')),
    status         TEXT NOT NULL CHECK (status IN ('new', 'queued', 'done', 'relevant',
                                                   'irrelevant', 'skipped', 'failed')),
    fetched_at     TEXT NOT NULL,
    UNIQUE (source, source_ref, instrument_id)
);
CREATE INDEX filings_by_instrument ON filings(instrument_id, filed_on);

CREATE TABLE metric_values (
    instrument_id  TEXT NOT NULL REFERENCES instruments(instrument_id),
    metric         TEXT NOT NULL,
    period         TEXT NOT NULL,
    value          TEXT NOT NULL,
    unit           TEXT NOT NULL,
    filing_id      INTEGER REFERENCES filings(filing_id),
    quote          TEXT,
    source         TEXT NOT NULL,
    call_id        INTEGER,
    extracted_at   TEXT NOT NULL,
    PRIMARY KEY (instrument_id, metric, period)
);

CREATE TABLE ai_tasks (
    task_id      INTEGER PRIMARY KEY,
    kind         TEXT NOT NULL CHECK (kind IN ('extract', 'screen', 'sell-confirm',
                                               'buy-confirm', 'monthly-review', 'discovery',
                                               'switch')),
    status       TEXT NOT NULL CHECK (status IN ('pending', 'running', 'done', 'failed',
                                                 'cancelled')),
    ledger_id    TEXT NOT NULL REFERENCES ledgers(ledger_id),
    rule_id      TEXT NOT NULL REFERENCES rules(rule_id),
    pick_id      INTEGER REFERENCES picks(pick_id),
    filing_id    INTEGER REFERENCES filings(filing_id),
    trigger      TEXT NOT NULL,
    detail       TEXT NOT NULL DEFAULT '{}',
    dedup_key    TEXT NOT NULL UNIQUE,
    not_before   TEXT NOT NULL,
    attempts     INTEGER NOT NULL DEFAULT 0,
    last_error   TEXT,
    result       TEXT,
    created_at   TEXT NOT NULL,
    started_at   TEXT,
    finished_at  TEXT
);
CREATE INDEX ai_tasks_queue ON ai_tasks(status, not_before);

CREATE TABLE ai_calls (
    call_id      INTEGER PRIMARY KEY,
    task_id      INTEGER REFERENCES ai_tasks(task_id),
    purpose      TEXT NOT NULL,
    caller       TEXT NOT NULL,
    model        TEXT NOT NULL,
    effort       TEXT,
    web          INTEGER NOT NULL DEFAULT 0,
    prompt       TEXT NOT NULL,
    input        TEXT NOT NULL,
    output       TEXT,
    usage        TEXT,
    tokens       INTEGER NOT NULL DEFAULT 0,
    cost_usd     TEXT,
    duration_ms  INTEGER,
    exit_code    INTEGER,
    error        TEXT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT
);
CREATE INDEX ai_calls_by_time ON ai_calls(started_at);
CREATE INDEX ai_calls_by_task ON ai_calls(task_id);

CREATE TABLE switches (
    switch_id       INTEGER PRIMARY KEY,
    ledger_id       TEXT NOT NULL REFERENCES ledgers(ledger_id),
    rule_id         TEXT NOT NULL REFERENCES rules(rule_id),
    sold_pick_id    INTEGER NOT NULL REFERENCES picks(pick_id),
    bought_pick_id  INTEGER NOT NULL REFERENCES picks(pick_id),
    decided_on      TEXT NOT NULL,
    task_id         INTEGER REFERENCES ai_tasks(task_id),
    costs           TEXT NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL
);

CREATE TABLE scores (
    kind            TEXT NOT NULL CHECK (kind IN ('pick', 'sell', 'switch')),
    ref_id          INTEGER NOT NULL,
    horizon_months  INTEGER NOT NULL CHECK (horizon_months IN (6, 12, 24, 36)),
    start_on        TEXT NOT NULL,
    due_on          TEXT NOT NULL,
    end_on          TEXT NOT NULL,
    value_return    TEXT NOT NULL,
    index_return    TEXT NOT NULL,
    excess          TEXT NOT NULL,
    scored_at       TEXT NOT NULL,
    PRIMARY KEY (kind, ref_id, horizon_months)
);

CREATE TABLE rule_daily (
    ledger_id   TEXT NOT NULL REFERENCES ledgers(ledger_id),
    rule_id     TEXT NOT NULL REFERENCES rules(rule_id),
    date        TEXT NOT NULL,
    excess_pp   TEXT,
    details     TEXT NOT NULL DEFAULT '{}',
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (ledger_id, rule_id, date)
);

CREATE TABLE job_runs (
    run_id      INTEGER PRIMARY KEY,
    job         TEXT NOT NULL,
    ledger_id   TEXT,
    run_date    TEXT NOT NULL,
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    result      TEXT,
    error       TEXT,
    details     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX job_runs_by_date ON job_runs(job, run_date);

CREATE TABLE source_states (
    source_id     TEXT PRIMARY KEY,
    state         TEXT NOT NULL CHECK (state IN ('ok', 'maintenance', 'stale', 'failed',
                                                 'no-key', 'unknown')),
    detail        TEXT,
    attempted_at  TEXT,
    ok_at         TEXT,
    updated_at    TEXT NOT NULL
)
"""

MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (1, "initial schema", V1),
    (2, "pin, sessions, lockout, notification preferences", V2),
    (3, "event refs, todo resolutions, dividends, baseline dividend cash", V3),
    (4, "the AI rule: shares, sleeves, picks, metrics, filings, AI tasks and calls", V4),
)

# Migrations that rebuild a table other tables reference. SQLite's documented procedure: foreign
# keys off around the transaction, PRAGMA foreign_key_check before the commit.
FK_OFF = frozenset({4})


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
        fk_off = version in FK_OFF
        if fk_off:
            conn.execute("PRAGMA foreign_keys=OFF")  # no effect inside a transaction
        try:
            with transaction(conn):
                for statement in _statements(sql):
                    conn.execute(statement)
                if fk_off:
                    broken = conn.execute("PRAGMA foreign_key_check").fetchall()
                    if broken:
                        raise sqlite3.IntegrityError(
                            f"migration {version} breaks foreign keys: {broken[:5]}"
                        )
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, stamp),
                )
        finally:
            if fk_off:
                conn.execute("PRAGMA foreign_keys=ON")
    return current_version(conn)
