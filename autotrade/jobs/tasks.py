"""Job entry points used by the CLI and by the 5-minute tick (autotrade/jobs/tick.py).

Each job first downloads what it needs (network, outside any transaction; each download is
committed to the market cache on its own), then runs the engine in one write transaction.
A dry run rolls that transaction back, so the ledger, plans, orders, events and runs are untouched
(downloaded market data stays cached). Every job is safe to run again.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from autotrade.broker.base import Executor, executor_for
from autotrade.broker.paper import DbMarketReader, PaperExecutor
from autotrade.config import Config
from autotrade.db import repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency, Instrument, Market
from autotrade.engine import discovery_plan
from autotrade.engine.check import (
    FAILED,
    TODO,
    needs_retry,
    record_check_failure,
    retry_time,
    run_check,
)
from autotrade.engine.common import load_rule
from autotrade.engine.dividends import book_dividends, watched_instruments
from autotrade.engine.runner import run_due_stages
from autotrade.engine.snapshot import SnapshotError, take_snapshot
from autotrade.engine.status import ledger_status, next_check_at
from autotrade.engine.todos import TodoError, open_todos, resolve, retry_ai
from autotrade.jobs.backup import BackupError, backup_dir_for, run_backup
from autotrade.market.service import (
    FetchErrors,
    MarketSources,
    prefetch_bars,
    prefetch_dividends,
    prefetch_fx,
)
from autotrade.rules.index_half import RULE_ID
from autotrade.timeutil import et_date, is_weekday, kst_date, require_aware


@dataclass
class JobContext:
    conn: sqlite3.Connection
    cfg: Config
    sources: MarketSources
    clock: Callable[[], float] = field(default=time.monotonic)

    def executor(self, ledger_id: str) -> Executor:
        paper = PaperExecutor(DbMarketReader(self.conn), self.cfg.fees, self.cfg.fx_fill_max_age)
        return executor_for(ledger_id, paper)


def _rule_instruments(conn: sqlite3.Connection) -> list[Instrument]:
    rule, instruments = load_rule(conn, RULE_ID)
    return [instruments[i] for i in rule.instrument_ids]


def _prefetch_window(
    ctx: JobContext, instruments: list[Instrument], d: date, at: datetime
) -> FetchErrors:
    errors = FetchErrors()
    start = d - timedelta(days=ctx.cfg.bar_lookback_days)
    errors.bars = prefetch_bars(ctx.conn, ctx.sources, instruments, start, d, at)
    errors.fx = prefetch_fx(ctx.conn, ctx.sources, at)
    return errors


def _record_crash(
    ctx: JobContext,
    ledger_id: str,
    job: str,
    d: date,
    at: datetime,
    exc: BaseException,
    attempt: int,
) -> str:
    """An unexpected error rolled the job back; keep a trace of it in runs."""
    error = f"{type(exc).__name__}: {exc}"
    with transaction(ctx.conn):
        run_id = repo.insert_run(ctx.conn, ledger_id, job, d, at, attempt)
        repo.finish_run(
            ctx.conn,
            run_id,
            ended_at=at,
            duration_ms=0,
            result=FAILED,
            error=error,
            details={"crash": True},
        )
    return error


def _record_check_crash(
    ctx: JobContext,
    ledger_id: str,
    d: date,
    at: datetime,
    exc: BaseException,
    attempt: int,
    final_attempt: bool,
) -> tuple[str, str]:
    """A check that crashed counts like one that failed (audit E10): the same run row with its
    retry time, the same 'check-failed' event, so the 09:30 retry runs and a final crash is the
    same '직접 할 일' as a final failure. Returns (result, error)."""
    error = f"{type(exc).__name__}: {exc}"
    retry_at = retry_time(ctx.cfg, d, at, final_attempt)
    result = FAILED if retry_at is not None else TODO
    with transaction(ctx.conn):
        run_id = repo.insert_run(ctx.conn, ledger_id, "check", d, at, attempt)
        repo.finish_run(
            ctx.conn,
            run_id,
            ended_at=at,
            duration_ms=0,
            result=result,
            error=error,
            details={"crash": True, "attempt": attempt, "retry_at": retry_at},
        )
        record_check_failure(ctx.conn, ledger_id, d, at, error, retry_at)
    return result, error


def check_job(
    ctx: JobContext, ledger_id: str, at: datetime, *, dry_run: bool = False, retry: bool = False
) -> dict[str, Any]:
    require_aware(at)
    job = "retry" if retry else "check"
    ctx.executor(ledger_id)  # refuses ledgers without an executor before touching anything
    d = kst_date(at)
    base: dict[str, Any] = {"job": job, "ledger": ledger_id, "at": at, "dry_run": dry_run}
    if not is_weekday(d):
        return {**base, "result": "weekend"}
    if retry:
        needed, attempt = needs_retry(ctx.conn, ledger_id, d)
        if not needed:
            return {**base, "result": "not-needed"}
    else:
        attempt = len(repo.runs_on(ctx.conn, ledger_id, "check", d)) + 1
    try:
        errors = _prefetch_window(ctx, _rule_instruments(ctx.conn), d, at)
        with transaction(ctx.conn, rollback=dry_run):
            outcome = run_check(
                ctx.conn,
                ctx.cfg,
                ledger_id,
                at,
                fetch=errors,
                attempt=attempt,
                final_attempt=retry,
                clock=ctx.clock,
            )
    except Exception as exc:
        if dry_run:
            raise
        result, error = _record_check_crash(ctx, ledger_id, d, at, exc, attempt, retry)
        return {**base, "result": result, "error": error}
    return {
        **base,
        "result": outcome.result,
        "run_id": outcome.run_id,
        "plan_id": outcome.plan_id,
        "error": outcome.error,
        "details": outcome.details,
    }


def stage_result(statuses: list[str]) -> str:
    """'failed' if any stage failed, 'done' if every executed stage finished, else 'waiting'."""
    if any(s in ("failed", "todo") for s in statuses):
        return "failed"
    if statuses and all(s == "done" for s in statuses):
        return "done"
    return "waiting"


def stage_job(
    ctx: JobContext, ledger_id: str, at: datetime, *, dry_run: bool = False
) -> dict[str, Any]:
    require_aware(at)
    executor = ctx.executor(ledger_id)
    base: dict[str, Any] = {"job": "stage", "ledger": ledger_id, "at": at, "dry_run": dry_run}
    due = [s for s in repo.pending_stages(ctx.conn, ledger_id) if s.due_at <= at]
    if not due:
        return {**base, "result": "nothing-due"}
    errors = FetchErrors()
    sessions: dict[str, set[date]] = {}
    fx_times: set[datetime] = set()
    for stage in due:
        for order in repo.orders_of_stage(ctx.conn, stage.stage_id, ["pending"]):
            if order.side == "fx":
                fx_times.add(stage.due_at)
            elif order.instrument_id is not None:
                us = order.market == Market.US.value
                session = et_date(stage.due_at) if us else kst_date(stage.due_at)
                sessions.setdefault(order.instrument_id, set()).add(session)
                if us:
                    # A dollar trade is booked in won at the rate of its plan's conversion, or
                    # else at the rate when it fills.
                    fx_times.add(stage.due_at)
    for iid, dates in sessions.items():
        inst = repo.get_instrument(ctx.conn, iid)
        errors.bars.update(
            prefetch_bars(
                ctx.conn, ctx.sources, [inst], min(dates) - timedelta(days=5), max(dates), at
            )
        )
    for when in sorted(fx_times):
        error = prefetch_fx(ctx.conn, ctx.sources, when)
        if error:
            errors.fx = error
    d = kst_date(at)
    started = ctx.clock()
    try:
        with transaction(ctx.conn, rollback=dry_run):
            run_id = repo.insert_run(ctx.conn, ledger_id, "stage", d, at)
            results = run_due_stages(ctx.conn, ctx.cfg, ledger_id, at, executor, errors)
            # The AI rule's picks follow their fills at once (a sold pick is closed).
            discovery_plan.reconcile(ctx.conn, ledger_id, at)
            result = stage_result([r.status for r in results])
            elapsed = int((ctx.clock() - started) * 1000)
            repo.finish_run(
                ctx.conn,
                run_id,
                ended_at=at + timedelta(milliseconds=elapsed),
                duration_ms=elapsed,
                result=result,
                error=None,
                details={"stages": [r.__dict__ for r in results]},
            )
    except Exception as exc:
        if dry_run:
            raise
        return {
            **base,
            "result": FAILED,
            "error": _record_crash(ctx, ledger_id, "stage", d, at, exc, 1),
        }
    return {**base, "result": result, "stages": [r.__dict__ for r in results]}


def snapshot_job(
    ctx: JobContext, ledger_id: str, at: datetime, *, dry_run: bool = False
) -> dict[str, Any]:
    require_aware(at)
    ctx.executor(ledger_id)
    d = kst_date(at)
    base: dict[str, Any] = {"job": "snapshot", "ledger": ledger_id, "at": at, "dry_run": dry_run}
    if not is_weekday(d):
        return {**base, "result": "weekend"}
    instruments = {i.instrument_id: i for i in _rule_instruments(ctx.conn)}
    for iid in repo.load_state(ctx.conn, ledger_id).positions:
        instruments.setdefault(iid, repo.get_instrument(ctx.conn, iid))
    _prefetch_window(ctx, list(instruments.values()), d, at)
    started = ctx.clock()
    error: str | None = None
    row = None
    try:
        with transaction(ctx.conn, rollback=dry_run):
            run_id = repo.insert_run(ctx.conn, ledger_id, "snapshot", d, at)
            try:
                outcome = take_snapshot(ctx.conn, ctx.cfg, ledger_id, at)
                result, row = outcome.result, outcome.row
            except SnapshotError as exc:
                result, error = FAILED, str(exc)
            elapsed = int((ctx.clock() - started) * 1000)
            repo.finish_run(
                ctx.conn,
                run_id,
                ended_at=at + timedelta(milliseconds=elapsed),
                duration_ms=elapsed,
                result=result,
                error=error,
                details={} if row is None else {"total_krw": row.total_krw, "stale": row.stale},
            )
    except Exception as exc:
        if dry_run:
            raise
        return {
            **base,
            "result": FAILED,
            "error": _record_crash(ctx, ledger_id, "snapshot", d, at, exc, 1),
        }
    out: dict[str, Any] = {**base, "result": result, "error": error}
    if row is not None:
        out.update(
            {
                "date": row.date,
                "total_krw": row.total_krw,
                "pnl_krw": row.pnl_krw,
                "baseline_krw": row.baseline_krw,
                "fx_rate": row.fx_rate,
                "kr_close_date": row.kr_close_date,
                "us_close_date": row.us_close_date,
                "stale": row.stale,
            }
        )
    return out


def status_job(ctx: JobContext, ledger_id: str, at: datetime) -> dict[str, Any]:
    return {"job": "status", **ledger_status(ctx.conn, ctx.cfg, ledger_id, at)}


def dividend_job(
    ctx: JobContext, ledger_id: str, at: datetime, *, dry_run: bool = False
) -> dict[str, Any]:
    """Download the recent dividends of what the ledger holds, then book those paid by today."""
    require_aware(at)
    ctx.executor(ledger_id)  # the paper ledger only: live dividends will come from the broker
    base: dict[str, Any] = {"job": "dividends", "ledger": ledger_id, "at": at, "dry_run": dry_run}
    d = kst_date(at)
    instruments = watched_instruments(ctx.conn, ledger_id)
    errors = prefetch_dividends(
        ctx.conn,
        ctx.cfg,
        ctx.sources,
        instruments,
        d - timedelta(days=ctx.cfg.dividend_lookback_days),
        d,
        at,
    )
    if any(i.currency is Currency.USD for i in instruments):
        prefetch_fx(ctx.conn, ctx.sources, at)  # a dollar dividend is valued at today's rate
    try:
        with transaction(ctx.conn, rollback=dry_run):
            booked = book_dividends(ctx.conn, ctx.cfg, ledger_id, at)
    except Exception as exc:
        if dry_run:
            raise
        return {**base, "result": FAILED, "error": f"{type(exc).__name__}: {exc}"}
    done = [b for b in booked if "event_id" in b]
    waiting = [b for b in booked if "event_id" not in b]
    if done:
        result = "booked"
    elif errors and len(errors) == len(instruments):
        result = FAILED
    else:
        result = "nothing-due"
    out: dict[str, Any] = {**base, "result": result, "booked": done, "waiting": waiting}
    if errors:
        out["fetch_errors"] = errors
    return out


def backup_job(ctx: JobContext, at: datetime) -> dict[str, Any]:
    """Today's copy of the whole database (every ledger) under data/backup/autotrade/."""
    require_aware(at)
    base: dict[str, Any] = {"job": "backup", "at": at}
    try:
        report = run_backup(ctx.conn, backup_dir_for(ctx.cfg.db_path), kst_date(at))
    except (BackupError, sqlite3.Error, OSError) as exc:
        return {**base, "result": FAILED, "error": f"{type(exc).__name__}: {exc}"}
    return {**base, **report}


def todos_job(ctx: JobContext, ledger_id: str, at: datetime) -> dict[str, Any]:
    require_aware(at)
    todos = [
        {"id": t.todo_id, "kind": t.kind, "date": t.day, "plan_id": t.plan_id, **t.facts}
        for t in open_todos(ctx.conn, ledger_id, ctx.cfg.ai_max_attempts)
    ]
    return {"job": "todos", "ledger": ledger_id, "at": at, "result": "ok", "todos": todos}


def resolve_job(
    ctx: JobContext,
    ledger_id: str,
    todo_id: str,
    at: datetime,
    *,
    note: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Close a '직접 할 일' after the owner handled it; the rule plans again at the next check."""
    require_aware(at)
    base: dict[str, Any] = {
        "job": "resolve",
        "ledger": ledger_id,
        "todo_id": todo_id,
        "at": at,
        "dry_run": dry_run,
    }
    try:
        with transaction(ctx.conn, rollback=dry_run):
            outcome = resolve(ctx.conn, ledger_id, todo_id, at, note, ctx.cfg.ai_max_attempts)
    except TodoError as exc:
        return {**base, "result": exc.code, "error": str(exc)}
    return {**base, **outcome, "next_check_at": next_check_at(ctx.cfg, at)}


def ai_retry_job(
    ctx: JobContext,
    ledger_id: str,
    todo_id: str,
    at: datetime,
    *,
    note: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Ask a failed AI task again (attempts back to 0); the AI runner takes it on its next run."""
    require_aware(at)
    base: dict[str, Any] = {
        "job": "ai-retry",
        "ledger": ledger_id,
        "todo_id": todo_id,
        "at": at,
        "dry_run": dry_run,
    }
    try:
        with transaction(ctx.conn, rollback=dry_run):
            outcome = retry_ai(ctx.conn, ledger_id, todo_id, at, note, ctx.cfg.ai_max_attempts)
    except TodoError as exc:
        return {**base, "result": exc.code, "error": str(exc)}
    return {**base, **outcome}


# Results that make the CLI exit with 1 ('failed', a manual action, a todo that cannot be closed).
FAILING_RESULTS = (FAILED, TODO, "bad-id", "not-found", "not-a-todo")
