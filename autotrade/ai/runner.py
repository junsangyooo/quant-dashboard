"""The AI runner: `python -m autotrade.jobs ai` (PHASE2.md §6).

Cron calls it every 5 minutes (deploy/autotrade.cron), apart from the tick: a model call has no
time limit (ops notes §7), so it must not hold the tick's lock. It takes due tasks one at a
time, cheap and urgent kinds first (autotrade/db/ai_repo.py TASK_ORDER):

  1. prepare  read the database, download what the packet needs (no transaction)
  2. calls    the subscription CLI, one or two calls (no transaction); a two-call question's
              second call is skipped once the first one failed. A complete answer kept from an
              earlier attempt (answer_calls) is applied again instead: nothing is asked twice
  3. record   every call goes into ai_calls with its tokens at once, before anything else can
              go wrong (they cost tokens), and a complete answer is kept on the task
  4. after    downloads the answer needs (discovery prices and kinds), if any
  5. apply    the flow writes the answer's effects and the task is done (one transaction)

Whatever goes wrong is recorded on the task and never stops the other tasks (audit E2):
  - a source down, a key missing, the evidence not in yet (RetryLaterError), a network or a
    database blink: the task waits an hour, no attempt counted
  - a download we cannot use (a corrupt file, a refusal, an empty text): it waits the same way,
    and after MAX_SOURCE_TRIES such answers the task gives up with a record (the filing too)
  - a failed call or an answer the flow cannot use: a failed attempt; Config.ai_max_attempts of
    them and the task waits for a person (a red 'to do': `ai-retry` or `resolve`)
  - anything else (a bug, a missing row, a prompt too long) would only fail the same way again:
    the task fails for good at once, its traceback goes to the log (stderr), its answer is kept
  - the CLI cannot even start: a source down. No attempt, nothing turns red, the run stops and
    the next one looks for the CLI again; the health screen's AI CLI row shows it

Every run writes a heartbeat (ai_runner): its gate, the CLI it found, whether it has a DART key,
the task it is asking and since when. The web service reads it (it never has the runner's
environment). Without AUTOTRADE_AI_CALLS=1 nothing is asked and only the heartbeat is written.
The month's tokens are counted against the budget (default 600,000); going over shows a yellow
'to do' on the health screen and never stops the runner (a sale must not wait for a budget).
"""

from __future__ import annotations

import contextlib
import http.client
import sqlite3
import sys
import traceback
import zipfile
import zlib
from collections.abc import Callable
from dataclasses import dataclass, replace
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
    SourceAnswerError,
)
from autotrade.ai.prompts import load
from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.db.connection import transaction
from autotrade.market.service import MarketSources
from autotrade.timeutil import KST, kst_date

MAX_TASKS_PER_RUN = 20
MAX_SOURCE_TRIES = 3  # unusable downloads before a task gives up (not attempts: no model asked)
ERROR_KEEP = 500

# How a task treats an error (classify).
OUTAGE = "outage"
UNUSABLE = "unusable"
FAULT = "fault"
# A download that arrived broken: zip and deflate errors, a cut-off stream.
CORRUPT: tuple[type[BaseException], ...] = (zlib.error, zipfile.BadZipFile, EOFError)


@dataclass(frozen=True)
class TaskOutcome:
    task_id: int
    kind: str
    # 'done' | 'failed' | 'cancelled' | 'later' | 'gave-up' | 'cli-missing' | 'crash'
    status: str
    calls: int
    tokens: int  # tokens of the calls made in this run (a kept answer costs none)
    error: str | None = None
    reused: bool = False  # a kept answer was applied again


def month_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime(d.year, d.month, 1, tzinfo=KST)
    end = datetime(d.year + (d.month == 12), d.month % 12 + 1, 1, tzinfo=KST)
    return start, end


def month_tokens(conn: sqlite3.Connection, at: datetime) -> int:
    start, end = month_bounds(kst_date(at))
    return ai_repo.tokens_between(conn, start, end)


def classify(exc: BaseException) -> str:
    """outage: wait, no attempt · unusable: wait, a source try · fault: fail for good now."""
    if isinstance(exc, SourceAnswerError):
        return UNUSABLE
    if isinstance(exc, RetryLaterError):
        return OUTAGE
    if isinstance(exc, CORRUPT):
        return UNUSABLE
    if isinstance(exc, sqlite3.OperationalError):
        text = str(exc).lower()
        return OUTAGE if "locked" in text or "busy" in text else FAULT
    if isinstance(exc, (OSError, http.client.HTTPException)):
        return OUTAGE  # the network (sockets, TLS, a cut-off answer) or the disk blinked
    return FAULT


def _error(exc: BaseException) -> str:
    """'ZeroDivisionError: division by zero (flows.py:812 apply_switch)'."""
    text = f"{type(exc).__name__}: {exc}"
    frames = traceback.extract_tb(exc.__traceback__)
    if frames:
        last = frames[-1]
        text += f" ({last.filename.rsplit('/', 1)[-1]}:{last.lineno} {last.name})"
    return text[:ERROR_KEEP]


def _log_fault(task: ai_repo.TaskRow, stage: str, exc: BaseException) -> None:
    """The traceback of an unexpected error goes to the runner's log (cron sends stderr there)."""
    sys.stderr.write(f"autotrade ai: task {task.task_id} ({task.kind}) failed in {stage}:\n")
    sys.stderr.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    sys.stderr.flush()


def load_steps(prompt: str, packet: str) -> str:
    """The instructions part of a prompt (the packet is stored on its own)."""
    return prompt[: len(prompt) - len(packet)].rstrip() if prompt.endswith(packet) else prompt


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


def kept_answer(
    conn: sqlite3.Connection, task: ai_repo.TaskRow, prepared: Prepared
) -> tuple[list[CliResult], list[int]] | None:
    """The complete answer an earlier attempt got and could not apply, as the results of this
    attempt's calls (None: there is none, or it no longer fits the question)."""
    if not task.answer_calls:
        return None
    try:
        rows = [ai_repo.get_call(conn, call_id) for call_id in task.answer_calls]
    except repo.NotFoundError:
        return None
    if [r.purpose for r in rows] != [c.purpose for c in prepared.calls] or not all(
        r.ok for r in rows
    ):
        return None
    results = [
        CliResult(
            call=call,
            exit_code=row.exit_code,
            output=row.output,
            usage=row.usage,
            tokens=row.tokens,
            cost_usd=row.cost_usd,
            duration_ms=row.duration_ms or 0,
            error=row.error,
            started_at=row.started_at,
            finished_at=row.finished_at or row.started_at,
        )
        for call, row in zip(prepared.calls, rows, strict=True)
    ]
    return results, list(task.answer_calls)


def _wait(
    conn: sqlite3.Connection,
    cfg: Config,
    task: ai_repo.TaskRow,
    now: Callable[[], datetime],
    exc: BaseException,
    stage: str,
    started: bool,
) -> TaskOutcome:
    """What a task does when `exc` stopped it (classify): wait, or fail for good."""
    kind = classify(exc)
    status = task.status if started else None  # put back what start_task changed
    if kind == FAULT:
        _log_fault(task, stage, exc)
        error = f"{stage}: {_error(exc)}"
        with transaction(conn):
            ai_repo.give_up_task(conn, task.task_id, now(), cfg.ai_max_attempts, error)
        return TaskOutcome(task.task_id, task.kind, "gave-up", 0, 0, error)
    error = f"{stage}: {exc}"[:ERROR_KEEP]
    if kind == UNUSABLE and task.source_tries + 1 >= MAX_SOURCE_TRIES:
        error = f"gave up after {task.source_tries + 1} unusable downloads; {error}"[:ERROR_KEEP]
        with transaction(conn):
            ai_repo.defer_task(conn, task.task_id, now(), error, source_try=True)
            ai_repo.give_up_task(conn, task.task_id, now(), cfg.ai_max_attempts, error)
            if task.filing_id is not None:
                ai_repo.set_filing_status(conn, task.filing_id, "failed")
        return TaskOutcome(task.task_id, task.kind, "gave-up", 0, 0, error)
    with transaction(conn):
        ai_repo.defer_task(
            conn,
            task.task_id,
            now() + RETRY_SOURCE,
            error,
            status=status,
            source_try=kind == UNUSABLE,
        )
    return TaskOutcome(task.task_id, task.kind, "later", 0, 0, error)


def _ask(cli: ClaudeCli, prepared: Prepared) -> list[CliResult]:
    results: list[CliResult] = []
    for call in prepared.calls:
        result = cli.run(call)
        results.append(result)
        if not result.ok:
            break
    return results


def run_task(
    conn: sqlite3.Connection,
    cfg: Config,
    sources: MarketSources,
    cli: ClaudeCli,
    task: ai_repo.TaskRow,
    now: Callable[[], datetime],
) -> TaskOutcome:
    flow = FLOWS[task.kind]

    def env() -> FlowEnv:
        return FlowEnv(conn, cfg, sources, now())

    try:
        prepared = flow.prepare(env(), task)
    except SkipTaskError as exc:
        with transaction(conn):
            ai_repo.keep_answer(conn, task.task_id, None)
            ai_repo.finish_task(
                conn, task.task_id, now(), status="cancelled", result={"skipped": str(exc)}
            )
        return TaskOutcome(task.task_id, task.kind, "cancelled", 0, 0, str(exc))
    except Exception as exc:
        return _wait(conn, cfg, task, now, exc, "prepare", started=False)

    kept = kept_answer(conn, task, prepared)
    with transaction(conn):
        ai_repo.start_task(conn, task.task_id, now())
    if kept is not None:
        results, call_ids = kept
        tokens = 0
    else:
        results = _ask(cli, prepared)
        lost = next((r for r in results if not r.launched), None)
        if lost is not None:  # the CLI is down: no attempt, no record, the run stops
            error = lost.error or "the CLI could not start"
            with transaction(conn):
                ai_repo.unstart_task(conn, task, now(), error[:ERROR_KEEP])
                ai_repo.runner_cli_lost(conn, now(), error[:ERROR_KEEP])
            return TaskOutcome(task.task_id, task.kind, "cli-missing", 0, 0, error)
        tokens = sum(r.tokens for r in results)
        complete = len(results) == len(prepared.calls) and all(r.ok for r in results)
        with transaction(conn):  # the calls are kept whatever happens next (they cost tokens)
            call_ids = _record_calls(conn, task.task_id, prepared, results)
            if complete:
                ai_repo.keep_answer(conn, task.task_id, call_ids)
        failure = next((r.error or "no answer" for r in results if not r.ok), None)
        if failure is not None:
            with transaction(conn):
                ai_repo.finish_task(
                    conn, task.task_id, now(), status="failed", error=failure[:ERROR_KEEP]
                )
            return TaskOutcome(task.task_id, task.kind, "failed", len(results), tokens, failure)
    reused = kept is not None
    calls = 0 if reused else len(results)

    if flow.after is not None:
        try:
            flow.after(env(), task, prepared, results)
        except Exception as exc:
            out = _wait(conn, cfg, task, now, exc, "after", started=True)
            return replace(out, calls=calls, tokens=tokens, reused=reused)
    try:
        with transaction(conn):
            summary = flow.apply(env(), task, prepared, results, call_ids)
            if reused:
                summary = {**summary, "applied_again": call_ids}
            ai_repo.keep_answer(conn, task.task_id, None)
            ai_repo.finish_task(conn, task.task_id, now(), status="done", result=summary)
    except FlowError as exc:  # the flow's writes were rolled back with the transaction
        error = f"answer not usable: {exc}"[:ERROR_KEEP]
        with transaction(conn):
            ai_repo.keep_answer(conn, task.task_id, None)  # ask again next time
            ai_repo.finish_task(conn, task.task_id, now(), status="failed", error=error)
        return TaskOutcome(task.task_id, task.kind, "failed", calls, tokens, error, reused)
    except Exception as exc:
        out = _wait(conn, cfg, task, now, exc, "apply", started=True)
        return replace(out, calls=calls, tokens=tokens, reused=reused)
    return TaskOutcome(task.task_id, task.kind, "done", calls, tokens, None, reused)


def release_orphans(conn: sqlite3.Connection, at: datetime) -> int:
    """Tasks left 'running' by a runner that died (the caller holds the runner's lock, so no
    other runner has them): they count as a failed attempt and are taken again (a kept answer
    is applied, not asked again)."""
    stuck = ai_repo.tasks_of(conn, statuses=("running",))
    with transaction(conn):
        for t in stuck:
            ai_repo.finish_task(conn, t.task_id, at, status="failed", error="the runner stopped")
    return len(stuck)


def _heartbeat(conn: sqlite3.Connection, fn: Callable[[], None]) -> None:
    """A heartbeat write never breaks a run (the database may be busy for a moment)."""
    with contextlib.suppress(sqlite3.Error), transaction(conn):
        fn()


def _heartbeat_task(
    conn: sqlite3.Connection, now: Callable[[], datetime], task: ai_repo.TaskRow | None
) -> None:
    """The task being asked now, and since when (None between tasks)."""
    with contextlib.suppress(sqlite3.Error), transaction(conn):
        if task is None:
            ai_repo.runner_task(conn, now(), None, None)
        else:
            ai_repo.runner_task(conn, now(), task.task_id, task.kind)


def run_ai(
    conn: sqlite3.Connection,
    cfg: Config,
    sources: MarketSources,
    cli: ClaudeCli,
    now: Callable[[], datetime],
    max_tasks: int = MAX_TASKS_PER_RUN,
) -> dict[str, Any]:
    at = now()
    _heartbeat(
        conn,
        lambda: ai_repo.runner_begin(
            conn,
            at,
            enabled=cfg.ai_calls_enabled,
            cli=cli.binary,
            cli_error=cli.missing,
            dart_key=bool(cfg.dart_api_key),
        ),
    )
    result = "crash"
    try:
        report = _run(conn, cfg, sources, cli, now, at, max_tasks)
        result = str(report["result"])
        return report
    finally:
        _heartbeat(conn, lambda: ai_repo.runner_end(conn, now(), result))


def _run(
    conn: sqlite3.Connection,
    cfg: Config,
    sources: MarketSources,
    cli: ClaudeCli,
    now: Callable[[], datetime],
    at: datetime,
    max_tasks: int,
) -> dict[str, Any]:
    if not cfg.ai_calls_enabled:
        due = ai_repo.due_tasks(conn, at, cfg.ai_max_attempts)
        return {"job": "ai", "at": at, "result": "disabled", "due": len(due)}
    if cli.binary is None:  # a source down: the tasks wait, nothing turns red
        due = ai_repo.due_tasks(conn, at, cfg.ai_max_attempts)
        return {
            "job": "ai",
            "at": at,
            "result": "cli-missing",
            "due": len(due),
            "error": cli.missing,
        }
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
        _heartbeat_task(conn, now, task)
        try:
            outcome = run_task(conn, cfg, sources, cli, task, now)
        except Exception as exc:  # the bookkeeping itself broke: the next run releases the task
            _log_fault(task, "runner", exc)
            outcome = TaskOutcome(task.task_id, task.kind, "crash", 0, 0, _error(exc))
        outcomes.append(outcome)
        _heartbeat_task(conn, now, None)
        if outcome.status == "cli-missing":
            break  # every task needs the CLI: the next run looks for it again
    used = month_tokens(conn, now())
    if any(o.status == "cli-missing" for o in outcomes):
        result = "cli-missing"
    elif any(o.status in ("failed", "gave-up", "crash") for o in outcomes):
        result = "failed"
    else:
        result = "nothing-due" if not outcomes else "ok"
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
