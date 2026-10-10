"""Job entry points of the AI rule '3년 발굴' (phase 2): the daily watch and the review queue.

Like the phase-1 jobs (autotrade/jobs/tasks.py) a job downloads first (network, outside any
transaction), then runs the engine in one write transaction; a dry run rolls it back.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from autotrade.ai.cli import ClaudeCli, find_claude
from autotrade.ai.runner import run_ai
from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Market
from autotrade.engine import discovery_plan, reviews, watch
from autotrade.jobs.tasks import JobContext
from autotrade.market.calendar import CalendarRangeError, calendar_for
from autotrade.market.filings import CompanyNotFoundError, FilingSource, FilingSourceError
from autotrade.market.freshness import expected_session
from autotrade.market.service import prefetch_bars, prefetch_fx
from autotrade.rules.discovery import SCORE_BENCHMARK
from autotrade.timeutil import is_weekday, kst_date, require_aware


def _closed_only(
    series: list[tuple[Any, Decimal]], market: Market, cfg: Config, at: datetime
) -> list[tuple[Any, Decimal]]:
    """Drop a bar of a session that has not closed (and been published) yet."""
    lag = cfg.kr_publication_lag if market is Market.KR else cfg.us_publication_lag
    try:
        last = expected_session(calendar_for(market), at, lag)
    except CalendarRangeError:
        return series
    return [x for x in series if x[0] <= last]


def fetch_watch_input(ctx: JobContext, ledger_id: str, at: datetime) -> watch.WatchInput:
    """Download what the watch reads. Every failure is recorded, never raised."""
    conn, sources, today = ctx.conn, ctx.sources, kst_date(at)
    data = watch.WatchInput()
    open_picks = watch.watched_picks(conn, ledger_id)
    every = {p.pick_id: p for p in [*watch.scored_picks(conn, ledger_id), *open_picks]}
    markets: dict[str, Market] = {}
    for pick in every.values():
        inst = repo.get_instrument(conn, pick.instrument_id)
        markets[inst.yahoo_symbol] = inst.market
        markets[pick.benchmark] = inst.market
    for market in Market:
        markets.setdefault(SCORE_BENCHMARK[market.value], market)
    if sources.adjusted is not None:
        start = watch.adjusted_start(conn, ledger_id, today)
        for symbol in sorted(markets):
            try:
                series = sources.adjusted.fetch_adjusted(symbol, start, today)
            except Exception as exc:  # recorded, never raised
                data.adjusted_errors[symbol] = f"{type(exc).__name__}: {exc}"
                continue
            data.adjusted[symbol] = _closed_only(series, markets[symbol], ctx.cfg, at)
    if sources.valuation is not None:
        for pick in open_picks:
            if not watch.needs_valuation(pick):
                continue
            inst = repo.get_instrument(conn, pick.instrument_id)
            try:
                data.valuations[inst.instrument_id] = sources.valuation.fetch_valuation(
                    inst.yahoo_symbol
                )
            except Exception as exc:  # recorded, never raised
                data.valuation_errors[inst.instrument_id] = f"{type(exc).__name__}: {exc}"
    by_source: dict[str, FilingSource | None] = {"dart": sources.dart, "edgar": sources.edgar}
    asked: dict[str, int] = {}
    for pick in open_picks:
        inst = repo.get_instrument(conn, pick.instrument_id)
        name = watch.SOURCE_OF_MARKET[inst.market]
        source = by_source[name]
        if source is None:
            continue
        if name in data.source_states:  # this source already failed in this run
            data.filing_errors[inst.instrument_id] = (
                f"{name} not asked: {data.source_states[name][1]}"
            )
            continue
        try:
            data.filings[inst.instrument_id] = source.fetch_filings(
                inst, watch.filing_window(conn, pick, today), today
            )
            asked[name] = asked.get(name, 0) + 1
        except CompanyNotFoundError as exc:  # the source works; it does not know this company
            data.filing_errors[inst.instrument_id] = str(exc)[:300]
            asked[name] = asked.get(name, 0) + 1
        except FilingSourceError as exc:
            data.source_states[name] = (exc.state, str(exc)[:300])
            data.filing_errors[inst.instrument_id] = str(exc)[:300]
        except Exception as exc:  # an answer we cannot read
            data.source_states[name] = ("failed", f"{type(exc).__name__}: {exc}"[:300])
            data.filing_errors[inst.instrument_id] = f"{type(exc).__name__}: {exc}"[:300]
    for name, n in asked.items():
        data.source_states.setdefault(name, ("ok", f"{n} companies"))
    return data


def watch_job(
    ctx: JobContext, ledger_id: str, at: datetime, *, dry_run: bool = False
) -> dict[str, Any]:
    """The AI rule's daily code checks (autotrade/engine/watch.py)."""
    require_aware(at)
    base: dict[str, Any] = {"job": "watch", "ledger": ledger_id, "at": at, "dry_run": dry_run}
    d = kst_date(at)
    if not is_weekday(d):
        return {**base, "result": "weekend"}
    if not reviews.rule_active(ctx.conn, ledger_id):
        return {**base, "result": "not-active"}
    data = fetch_watch_input(ctx, ledger_id, at)
    try:
        with transaction(ctx.conn, rollback=dry_run):
            outcome = watch.run_watch(ctx.conn, ctx.cfg, ledger_id, at, data)
    except Exception as exc:
        if dry_run:
            raise
        error = f"{type(exc).__name__}: {exc}"
        with transaction(ctx.conn):
            ai_repo.insert_job_run(
                ctx.conn,
                job=watch.JOB,
                ledger_id=ledger_id,
                run_date=d,
                started_at=at,
                ended_at=at,
                result="failed",
                error=error,
                details={"crash": True},
            )
        return {**base, "result": "failed", "error": error}
    return {**base, "result": outcome.result, "run_id": outcome.run_id, **outcome.details}


def queue_job(
    ctx: JobContext, ledger_id: str, at: datetime, *, dry_run: bool = False
) -> dict[str, Any]:
    """Queue the monthly reviews and the quarterly discovery (autotrade/engine/reviews.py)."""
    require_aware(at)
    base: dict[str, Any] = {"job": "ai-queue", "ledger": ledger_id, "at": at, "dry_run": dry_run}
    if not reviews.rule_active(ctx.conn, ledger_id):
        return {**base, "result": "not-active"}
    with transaction(ctx.conn, rollback=dry_run):
        report = reviews.queue_reviews(ctx.conn, ledger_id, at)
    return {**base, **report}


def ai_workdir(db_path: Path) -> Path:
    """The empty folder the CLI runs in (no project files for it to read)."""
    return db_path.parent / "ai-cwd"


def ai_job(
    ctx: JobContext, now: Callable[[], datetime], *, cli: ClaudeCli | None = None
) -> dict[str, Any]:
    """Run the due AI tasks (autotrade/ai/runner.py). Calls only with AUTOTRADE_AI_CALLS=1.
    The CLI is looked for on every run (cron's PATH has none; autotrade/ai/cli.py find_claude):
    a missing one is a source down, recorded in the runner's heartbeat."""
    if cli is None:
        binary = find_claude(ctx.cfg.claude_bin, os.environ)
        cli = ClaudeCli.found(binary, ai_workdir(ctx.cfg.db_path), now=now)
    return run_ai(ctx.conn, ctx.cfg, ctx.sources, cli, now)


def plan_job(
    ctx: JobContext, ledger_id: str, at: datetime, *, dry_run: bool = False
) -> dict[str, Any]:
    """Turn the AI rule's decisions into a plan (autotrade/engine/discovery_plan.py)."""
    require_aware(at)
    ctx.executor(ledger_id)
    base: dict[str, Any] = {"job": "ai-plan", "ledger": ledger_id, "at": at, "dry_run": dry_run}
    d = kst_date(at)
    instruments = discovery_plan.needed_instruments(ctx.conn, ledger_id)
    errors = prefetch_bars(
        ctx.conn,
        ctx.sources,
        instruments,
        d - timedelta(days=ctx.cfg.bar_lookback_days),
        d,
        at,
    )
    fx_error = prefetch_fx(ctx.conn, ctx.sources, at)
    try:
        with transaction(ctx.conn, rollback=dry_run):
            outcome = discovery_plan.plan_ai(ctx.conn, ctx.cfg, ledger_id, at)
            ai_repo.insert_job_run(
                ctx.conn,
                job=discovery_plan.JOB,
                ledger_id=ledger_id,
                run_date=d,
                started_at=at,
                ended_at=at,
                result=outcome.result,
                error=None,
                details=outcome.details,
            )
    except Exception as exc:
        if dry_run:
            raise
        error = f"{type(exc).__name__}: {exc}"
        with transaction(ctx.conn):
            ai_repo.insert_job_run(
                ctx.conn,
                job=discovery_plan.JOB,
                ledger_id=ledger_id,
                run_date=d,
                started_at=at,
                ended_at=at,
                result="failed",
                error=error,
                details={"crash": True},
            )
        return {**base, "result": "failed", "error": error}
    out: dict[str, Any] = {**base, "result": outcome.result, "plan_id": outcome.plan_id}
    out.update({k: v for k, v in outcome.details.items() if k in ("sell", "buy", "waiting")})
    if errors or fx_error:
        out["fetch_errors"] = {**errors, **({"fx": fx_error} if fx_error else {})}
    return out
