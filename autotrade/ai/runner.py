"""The AI runner: `python -m autotrade.jobs ai` (PHASE2.md §6).

Cron calls it every 5 minutes (deploy/autotrade.cron), apart from the tick: a model call has no
time limit (ops notes §7), so it must not hold the tick's lock. It takes due tasks one at a
time, cheap and urgent kinds first (autotrade/db/ai_repo.py TASK_ORDER):

  1. prepare  read the database, download what the packet needs (no transaction)
  2. start    mark the task running and count the attempt (a short transaction)
  3. calls    the subscription CLI, one or two calls (no transaction); a sell confirmation's
              second call is skipped once the first one failed
  4. after    downloads the answer needs (discovery prices), if any
  5. record   every call goes into ai_calls with its tokens; the flow applies the answer; the task
              is done or failed (one transaction). A failed task is taken again on a later run,
              up to Config.ai_max_attempts; a source that is down only postpones it (no attempt).

Without AUTOTRADE_AI_CALLS=1 nothing is called and nothing is recorded: the tasks wait.
The month's tokens are counted against the budget (default 600,000); going over shows a yellow
'to do' on the health screen and never stops the runner (a sale must not wait for a budget).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from autotrade.ai.cli import ClaudeCli, CliResult
from autotrade.ai.flows import (
    FLOWS,
    RETRY_SOURCE,
    FlowEnv,
    FlowError,
    Prepared,
    RetryLaterError,
    SkipTaskError,
)
from autotrade.ai.prompts import load
from autotrade.config import Config
from autotrade.db import ai_repo
from autotrade.db.connection import transaction
from autotrade.market.service import MarketSources
from autotrade.timeutil import KST, kst_date

MAX_TASKS_PER_RUN = 20


@dataclass(frozen=True)
class TaskOutcome:
    task_id: int
    kind: str
    status: str  # 'done' | 'failed' | 'cancelled' | 'later'
    calls: int
    tokens: int
    error: str | None = None


def month_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, 1, tzinfo=KST)
    end = datetime(d.year + (d.month == 12), d.month % 12 + 1, 1, tzinfo=KST)
    return start, end


def month_tokens(conn: sqlite3.Connection, at: datetime) -> int:
    start, end = month_bounds(kst_date(at))
    return ai_repo.tokens_between(conn, start, end)


def _record_calls(
    conn: sqlite3.Connection, task_id: int, prepared: Prepared, results: list[CliResult]
) -> list[int]:
    ids: list[int] = []
    for r in results:
        ids.append(
            ai_repo.insert_call(
                conn,
                task_id=task_id,
                purpose=r.call.purpose,
                caller="runner",
                model=r.call.model,
                effort=r.call.effort,
                web=r.call.web,
                prompt=f"{r.call.system}\n\n{load_steps(r.call.prompt, prepared.packet)}",
                input_text=prepared.packet,
                output=r.output,
                usage=r.usage,
                tokens=r.tokens,
                cost_usd=r.cost_usd,
                duration_ms=r.duration_ms,
                exit_code=r.exit_code,
                error=r.error,
                started_at=r.started_at,
                finished_at=r.finished_at,
            )
        )
    return ids


def load_steps(prompt: str, packet: str) -> str:
    """The instructions part of a prompt (the packet is stored on its own)."""
    return prompt[: len(prompt) - len(packet)].rstrip() if prompt.endswith(packet) else prompt


def run_task(
    conn: sqlite3.Connection,
    cfg: Config,
    sources: MarketSources,
    cli: ClaudeCli,
    task: ai_repo.TaskRow,
    now: Callable[[], datetime],
) -> TaskOutcome:
    flow = FLOWS[task.kind]
    try:
        prepared = flow.prepare(FlowEnv(conn, cfg, sources, now()), task)
    except SkipTaskError as exc:
        with transaction(conn):
            ai_repo.finish_task(
                conn, task.task_id, now(), status="cancelled", result={"skipped": str(exc)}
            )
        return TaskOutcome(task.task_id, task.kind, "cancelled", 0, 0, str(exc))
    except RetryLaterError as exc:
        with transaction(conn):
            ai_repo.defer_task(conn, task.task_id, now() + RETRY_SOURCE, str(exc))
        return TaskOutcome(task.task_id, task.kind, "later", 0, 0, str(exc))
    except FlowError as exc:
        with transaction(conn):
            ai_repo.start_task(conn, task.task_id, now())
            ai_repo.finish_task(conn, task.task_id, now(), status="failed", error=str(exc))
        return TaskOutcome(task.task_id, task.kind, "failed", 0, 0, str(exc))
    with transaction(conn):
        ai_repo.start_task(conn, task.task_id, now())
    results: list[CliResult] = []
    for call in prepared.calls:
        result = cli.run(call)
        results.append(result)
        if not result.ok:
            break
    error = next((r.error or "no answer" for r in results if not r.ok), None)
    if error is None and flow.after is not None:
        try:
            flow.after(FlowEnv(conn, cfg, sources, now()), task, prepared, results)
        except (FlowError, RetryLaterError) as exc:
            error = str(exc)
    tokens = sum(r.tokens for r in results)
    with transaction(conn):  # the calls are kept whatever happens next (they cost tokens)
        call_ids = _record_calls(conn, task.task_id, prepared, results)
    try:
        with transaction(conn):
            if error is None:
                try:
                    summary = flow.apply(
                        FlowEnv(conn, cfg, sources, now()), task, prepared, results, call_ids
                    )
                except FlowError as exc:
                    error = f"answer not usable: {exc}"
                    raise _UnusableError from exc
                ai_repo.finish_task(conn, task.task_id, now(), status="done", result=summary)
    except _UnusableError:
        pass  # the flow's writes were rolled back with the transaction
    except Exception as exc:  # a bug in a flow must not leave the task 'running'
        error = f"crash: {type(exc).__name__}: {exc}"
    if error is not None:
        with transaction(conn):
            ai_repo.finish_task(conn, task.task_id, now(), status="failed", error=error[:500])
    status = "done" if error is None else "failed"
    return TaskOutcome(task.task_id, task.kind, status, len(results), tokens, error)


class _UnusableError(Exception):
    """Rolls back a flow's writes when its answer cannot be used."""


def release_orphans(conn: sqlite3.Connection, at: datetime) -> int:
    """Tasks left 'running' by a runner that died (the caller holds the runner's lock, so no
    other runner has them): they count as a failed attempt and are taken again."""
    stuck = ai_repo.tasks_of(conn, statuses=("running",))
    with transaction(conn):
        for t in stuck:
            ai_repo.finish_task(conn, t.task_id, at, status="failed", error="the runner stopped")
    return len(stuck)


def run_ai(
    conn: sqlite3.Connection,
    cfg: Config,
    sources: MarketSources,
    cli: ClaudeCli,
    now: Callable[[], datetime],
    max_tasks: int = MAX_TASKS_PER_RUN,
) -> dict[str, Any]:
    at = now()
    if not cfg.ai_calls_enabled:
        due = ai_repo.due_tasks(conn, at, cfg.ai_max_attempts)
        return {"job": "ai", "at": at, "result": "disabled", "due": len(due)}
    for flow in FLOWS.values():
        load(flow.prompt)  # a broken prompt file fails here, before any call
    orphans = release_orphans(conn, at)
    tried: set[int] = set()
    outcomes: list[TaskOutcome] = []
    while len(outcomes) < max_tasks:
        due = [
            t for t in ai_repo.due_tasks(conn, now(), cfg.ai_max_attempts) if t.task_id not in tried
        ]
        if not due:
            break
        task = due[0]
        tried.add(task.task_id)
        outcomes.append(run_task(conn, cfg, sources, cli, task, now))
    used = month_tokens(conn, now())
    failed = [o for o in outcomes if o.status == "failed"]
    result = "nothing-due" if not outcomes else ("failed" if failed else "ok")
    return {
        "job": "ai",
        "at": at,
        "result": result,
        "tasks": [o.__dict__ for o in outcomes],
        "tokens": sum(o.tokens for o in outcomes),
        "month_tokens": used,
        "budget": cfg.ai_monthly_budget,
        "over_budget": used > cfg.ai_monthly_budget,
        "orphans": orphans,
    }
