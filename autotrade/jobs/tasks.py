"""Job entry points used by the CLI (and later by cron).

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
from autotrade.domain.instruments import Instrument, Market
from autotrade.engine.check import FAILED, TODO, needs_retry, run_check
from autotrade.engine.common import load_rule
from autotrade.engine.runner import run_due_stages
from autotrade.engine.snapshot import SnapshotError, take_snapshot
from autotrade.engine.status import ledger_status
from autotrade.market.service import FetchErrors, MarketSources, prefetch_bars, prefetch_fx
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
    errors = _prefetch_window(ctx, _rule_instruments(ctx.conn), d, at)
    try:
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
        return {
            **base,
            "result": FAILED,
            "error": _record_crash(ctx, ledger_id, "check", d, at, exc, attempt),
        }
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


FAILING_RESULTS = (FAILED, TODO)
