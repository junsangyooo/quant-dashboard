"""python -m autotrade.jobs tick — cron calls it every 5 minutes (deploy/autotrade.cron).

Each tick asks autotrade/jobs/schedule.py what is due, in this order — dividends, check, retry,
watch, ai-plan, stages, snapshot, backup, ai-queue — and runs it through the same job functions
as the per-task commands. The AI calls themselves run in their own cron line
(python -m autotrade.jobs ai), because a model call has no time limit (ops notes §7).
Every task that ran prints one JSON line (stdout -> data/logs/autotrade-jobs.log); a tick with
nothing due prints nothing. A task that breaks is logged and the tick goes on with the next one.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from autotrade.engine.check import FAILED
from autotrade.jobs.ai_tasks import plan_job, queue_job, watch_job
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
)


def _due(task: str, ctx: JobContext, ledger_id: str, at: datetime, backup_dir: Path) -> Due | None:
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
    return backup_due(ctx.conn, ctx.cfg, [ledger_id], backup_dir, at)


def _run(task: str, ctx: JobContext, ledger_id: str, at: datetime) -> dict[str, Any]:
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
    tasks: Sequence[str] = TASKS,
) -> list[dict[str, Any]]:
    """Run every due task once, in order. Returns the lines it emitted. `tasks` narrows the list
    (dev-seed replays without the backup)."""
    lines: list[dict[str, Any]] = []
    for task in (t for t in TASKS if t in tasks):
        at = clock()
        line: dict[str, Any] = {"at": at, "task": task, "ledger": ledger_id}
        try:
            due = _due(task, ctx, ledger_id, at, backup_dir)
            if due is None:
                continue
            line["why"] = due.why
            line.update(_summary(_run(task, ctx, ledger_id, at)))
        except Exception as exc:  # one broken task must not stop the others
            line.update({"result": FAILED, "error": f"{type(exc).__name__}: {exc}"})
        emit(line)
        lines.append(line)
    return lines
