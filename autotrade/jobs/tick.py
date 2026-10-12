"""python -m autotrade.jobs tick — cron calls it every 5 minutes (deploy/autotrade.cron).

Each tick asks autotrade/jobs/schedule.py what is due, in this order — dividends, check, retry,
watch, ai-plan, stages, snapshot, backup, ai-queue — and runs it through the same job functions
as the per-task commands. The AI calls themselves run in their own cron line
(python -m autotrade.jobs ai), because a model call has no time limit (ops notes §7).
Every task that ran prints one JSON line (stdout -> data/logs/autotrade-jobs.log); a tick with
nothing due prints nothing. A task that breaks is logged and the tick goes on with the next one.

One tick runs the paper ledger, then the live ledger (run_all, autotrade/PHASE3.md 2.8), then
the backup once. The live ledger's turn: the Toss sync (broker: the only code that calls Toss,
and only with AUTOTRADE_LIVE_ORDERS=1), the stages (the Toss executor reads what the sync
recorded), the reconciliation, the check and its retry (while the mode is live), the snapshot
(whenever the ledger has started: an account that is off still counts, 인계 15). Live dividends
come from the account (the reconciliation), not from the paper ledger's dividend job. A task
whose report says 'quiet' (nothing changed) prints nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from autotrade.db import repo
from autotrade.engine import live
from autotrade.engine.check import FAILED
from autotrade.jobs.ai_tasks import plan_job, queue_job, watch_job
from autotrade.jobs.live_tasks import broker_job, reconcile_job
from autotrade.jobs.schedule import (
    Due,
    ai_plan_due,
    backup_due,
    check_due,
    dividends_due,
    queue_due,
    retry_due,
    snapshot_due,
    stages_due,
    watch_due,
)
from autotrade.jobs.tasks import (
    JobContext,
    backup_job,
    check_job,
    dividend_job,
    snapshot_job,
    stage_job,
)

TASKS = (
    "dividends",
    "check",
    "retry",
    "watch",
    "ai-plan",
    "stages",
    "snapshot",
    "backup",
    "ai-queue",
)
# The live ledger's turn (PHASE3.md 2.8): the sync first, so the stages read fresh broker
# records and the check reconciles a fresh snapshot.
LIVE_TASKS = ("broker", "stages", "reconcile", "check", "retry", "snapshot")
# What a log line keeps from a job's report (the full report stays in the database records).
KEEP = (
    "result",
    "error",
    "run_id",
    "plan_id",
    "total_krw",
    "baseline_krw",
    "stale",
    "booked",
    "waiting",
    "fetch_errors",
    "path",
    "bytes",
    "removed",
    "tasks",
    "filings",
    "vs_index",
    "scored",
    "month",
    "sell",
    "buy",
    "waiting",
    "changes",
    "booked",
    "reason",
    "state",
    "token_revoked",
)


def tick_ledgers(ctx: JobContext) -> list[str]:
    """The ledgers a tick runs: paper always; live once it matters (the key is set, the ledger
    has started, or the mode is live)."""
    out = ["paper"]
    if ctx.cfg.live_orders or live.relevant(ctx.conn):
        out.append(live.LIVE)
    return out


def _live_due(task: str, ctx: JobContext, at: datetime) -> Due | None:
    started = repo.start_event(ctx.conn, live.LIVE) is not None
    on = live.mode_of(ctx.conn) == live.LIVE
    if task == "broker":
        return Due("broker", "every-tick")
    if task == "reconcile":
        return Due("reconcile", "every-tick") if started else None
    if task in ("check", "retry"):
        if not (started and on):
            return None
        if task == "check":
            return check_due(ctx.conn, ctx.cfg, live.LIVE, at)
        return retry_due(ctx.conn, ctx.cfg, live.LIVE, at)
    if task == "snapshot":
        return snapshot_due(ctx.conn, ctx.cfg, live.LIVE, at) if started else None
    if task == "stages":
        return stages_due(ctx.conn, live.LIVE, at)
    return None


def _due(task: str, ctx: JobContext, ledger_id: str, at: datetime, backup_dir: Path) -> Due | None:
    if ledger_id == live.LIVE and task != "backup":
        return _live_due(task, ctx, at)
    if task == "dividends":
        if ctx.sources.dividends is None:
            return None
        return dividends_due(ctx.conn, ledger_id, at)
    if task == "check":
        return check_due(ctx.conn, ctx.cfg, ledger_id, at)
    if task == "retry":
        return retry_due(ctx.conn, ctx.cfg, ledger_id, at)
    if task == "stages":
        return stages_due(ctx.conn, ledger_id, at)
    if task == "snapshot":
        return snapshot_due(ctx.conn, ctx.cfg, ledger_id, at)
    if task == "watch":
        return watch_due(ctx.conn, ctx.cfg, ledger_id, at)
    if task == "ai-queue":
        return queue_due(ctx.conn, ledger_id, at)
    if task == "ai-plan":
        return ai_plan_due(ctx.conn, ctx.cfg, ledger_id, at)
    started = [lid for lid in tick_ledgers(ctx) if repo.start_event(ctx.conn, lid) is not None]
    return backup_due(ctx.conn, ctx.cfg, sorted({ledger_id, *started}), backup_dir, at)


def _run(task: str, ctx: JobContext, ledger_id: str, at: datetime) -> dict[str, Any]:
    if task == "broker":
        return broker_job(
            ctx.conn, ctx.cfg, at, transport=ctx.toss_transport, now=ctx.wall, sleep=ctx.sleep
        )
    if task == "reconcile":
        return reconcile_job(ctx.conn, ctx.cfg, at)
    if task == "dividends":
        return dividend_job(ctx, ledger_id, at)
    if task == "check":
        return check_job(ctx, ledger_id, at)
    if task == "retry":
        return check_job(ctx, ledger_id, at, retry=True)
    if task == "stages":
        return stage_job(ctx, ledger_id, at)
    if task == "snapshot":
        return snapshot_job(ctx, ledger_id, at)
    if task == "watch":
        return watch_job(ctx, ledger_id, at)
    if task == "ai-queue":
        return queue_job(ctx, ledger_id, at)
    if task == "ai-plan":
        return plan_job(ctx, ledger_id, at)
    return backup_job(ctx, at)


def _summary(report: dict[str, Any]) -> dict[str, Any]:
    out = {k: report[k] for k in KEEP if k in report}
    stages = report.get("stages")
    if isinstance(stages, list):
        out["stages"] = [
            {k: s.get(k) for k in ("plan_id", "kind", "market", "status")}
            for s in stages
            if isinstance(s, dict)
        ]
    return out


def run_tick(
    ctx: JobContext,
    ledger_id: str,
    clock: Callable[[], datetime],
    backup_dir: Path,
    emit: Callable[[dict[str, Any]], None],
    tasks: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Run every due task of one ledger once, in order. Returns the lines it emitted. `tasks`
    narrows the list (dev-seed replays without the backup)."""
    lines: list[dict[str, Any]] = []
    order = LIVE_TASKS if ledger_id == live.LIVE else TASKS
    wanted = order if tasks is None else tasks
    for task in (t for t in order if t in wanted):
        at = clock()
        line: dict[str, Any] = {"at": at, "task": task, "ledger": ledger_id}
        try:
            due = _due(task, ctx, ledger_id, at, backup_dir)
            if due is None:
                continue
            line["why"] = due.why
            report = _run(task, ctx, ledger_id, at)
            if report.get("result") == "quiet":
                continue  # nothing changed: nothing to log
            line.update(_summary(report))
        except Exception as exc:  # one broken task must not stop the others
            line.update({"result": FAILED, "error": f"{type(exc).__name__}: {exc}"})
        emit(line)
        lines.append(line)
    return lines


def run_all(
    ctx: JobContext,
    clock: Callable[[], datetime],
    backup_dir: Path,
    emit: Callable[[dict[str, Any]], None],
) -> list[dict[str, Any]]:
    """What cron's tick runs: the paper ledger, the live ledger when it matters, then the backup
    once (after both snapshots)."""
    lines = run_tick(
        ctx, "paper", clock, backup_dir, emit, tasks=[t for t in TASKS if t != "backup"]
    )
    if live.LIVE in tick_ledgers(ctx):
        lines += run_tick(ctx, live.LIVE, clock, backup_dir, emit, tasks=LIVE_TASKS)
    lines += run_tick(ctx, "paper", clock, backup_dir, emit, tasks=["backup"])
    return lines
