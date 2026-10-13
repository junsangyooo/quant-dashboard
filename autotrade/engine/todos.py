"""'직접 할 일' (manual actions): list them, and close one after the owner has handled it.

Three kinds, with the ids the web API shows (autotrade/api/views/health.py, discovery.py):

- 'order-failed:<order id>': an order of a plan in 'todo' status. It failed again on its retry,
  the broker rejected it (인계 11), or it waited on a stage that did (it was cancelled). The id is
  the order's first attempt. While such a plan is open the rule makes no new plan (engine/check).
- 'check-failed:<YYYY-MM-DD>': the day's check failed (or crashed) on its last attempt and no
  check has succeeded since.
- 'ai-cli:failed:<task id>': an AI task that failed Config.ai_max_attempts times (or gave up at
  once on a fault that would only repeat). It waits for a person and blocks nothing meanwhile:
  a new hit asks a new confirmation (engine/watch.py).

resolve() closes one after the owner has dealt with it (in the Toss app, for a live order):

- an order todo closes its whole plan: what the plan still had to send is cancelled, its stages
  stop, the plan and its event become 'resolved', and the next check plans again from the ledger
  as it is (fills that happened stay; nothing is invented for the order that did not fill);
- a check todo marks that day's failure as handled;
- an AI todo cancels the task (`python -m autotrade.jobs ai-retry <id>` asks it again instead:
  retry_ai, attempts back to 0; a complete answer it already got is applied, not asked again).

Either way an event 'todo-resolved' records it (with the owner's note), under a natural key so
that resolving twice changes nothing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.db.models import OrderRow, PlanRow
from autotrade.engine.common import refresh_cash_parts
from autotrade.timeutil import kst_date, require_aware

ORDER_TODO = "order-failed"
CHECK_TODO = "check-failed"
AI_TODO = "ai-cli:failed"
FAILED_RESULTS = ("failed", "todo")


def _max(max_attempts: int | None) -> int:
    return Config().ai_max_attempts if max_attempts is None else max_attempts


class TodoError(ValueError):
    """The id is malformed, unknown, or not an open manual action."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class Todo:
    todo_id: str
    kind: str  # ORDER_TODO | CHECK_TODO | AI_TODO
    day: date  # the plan's date, or the failed check's date
    plan_id: int | None = None
    facts: dict[str, Any] = field(default_factory=dict)


def _chains(orders: list[OrderRow]) -> dict[int, list[OrderRow]]:
    """Attempts of each order by its first attempt's id (retries point back via retry_of)."""
    by_id = {o.order_id: o for o in orders}
    chains: dict[int, list[OrderRow]] = {}
    for o in orders:
        root = o
        while root.retry_of is not None and root.retry_of in by_id:
            root = by_id[root.retry_of]
        chains.setdefault(root.order_id, []).append(o)
    for attempts in chains.values():
        attempts.sort(key=lambda a: a.attempt)
    return chains


def _order_todos(conn: sqlite3.Connection, plan: PlanRow) -> list[Todo]:
    out: list[Todo] = []
    for root_id, attempts in sorted(_chains(repo.orders_of_plan(conn, plan.plan_id)).items()):
        latest = attempts[-1]
        if not (latest.status == "cancelled" or (latest.status == "failed" and latest.manual)):
            continue
        out.append(
            Todo(
                todo_id=f"{ORDER_TODO}:{root_id}",
                kind=ORDER_TODO,
                day=plan.plan_date,
                plan_id=plan.plan_id,
                facts={
                    "stage": latest.stage,
                    "market": latest.market,
                    "side": latest.side,
                    "instrument_id": latest.instrument_id,
                    "qty": latest.qty,
                    "amount": latest.est_amount,
                    "currency": latest.currency.value,
                    "status": latest.status,
                    "reason": latest.failure_reason
                    or ("waits-on-failed-stage" if latest.status == "cancelled" else None),
                    "detail": latest.failure_detail,
                    "attempts": len(attempts),
                },
            )
        )
    return out


def _check_todo(conn: sqlite3.Connection, ledger_id: str) -> Todo | None:
    """The newest final check failure, unless a check has succeeded on that day or later."""
    failures = [
        e for e in repo.events_of_ledger(conn, ledger_id, ["check-failed"]) if e.status == "todo"
    ]
    if not failures:
        return None
    ev = max(failures, key=lambda e: e.event_date)
    later = repo.runs_of_ledger(conn, ledger_id, "check", since=ev.event_date)
    if any(r.result is not None and r.result not in FAILED_RESULTS for r in later):
        return None
    return Todo(
        todo_id=f"{CHECK_TODO}:{ev.event_date.isoformat()}",
        kind=CHECK_TODO,
        day=ev.event_date,
        facts={
            "error": ev.payload.get("error"),
            "attempts": ev.payload.get("attempts"),
            "at": ev.occurred_at,
        },
    )


def _ai_todos(conn: sqlite3.Connection, ledger_id: str, max_attempts: int) -> list[Todo]:
    """One per AI task that waits for a person."""
    out: list[Todo] = []
    for t in ai_repo.stuck_tasks(conn, max_attempts, ledger_id):
        facts: dict[str, Any] = {
            "task_kind": t.kind,
            "trigger": t.trigger,
            "attempts": t.attempts,
            "error": t.last_error,
            "created_at": t.created_at,
            "kept_answer": bool(t.answer_calls),
        }
        if t.pick_id is not None:
            facts["instrument_id"] = ai_repo.get_pick(conn, t.pick_id).instrument_id
        out.append(
            Todo(
                todo_id=f"{AI_TODO}:{t.task_id}",
                kind=AI_TODO,
                day=kst_date(t.finished_at or t.created_at),
                facts=facts,
            )
        )
    return out


def open_todos(
    conn: sqlite3.Connection, ledger_id: str, max_attempts: int | None = None
) -> list[Todo]:
    out: list[Todo] = []
    for plan in repo.plans_with_status(conn, ledger_id, "todo"):
        out.extend(_order_todos(conn, plan))
    check = _check_todo(conn, ledger_id)
    if check is not None:
        out.append(check)
    out.extend(_ai_todos(conn, ledger_id, _max(max_attempts)))
    return out


def _parse(todo_id: str) -> tuple[str, str]:
    if todo_id.startswith(f"{AI_TODO}:"):
        value = todo_id[len(AI_TODO) + 1 :]
        if not value.isdigit():
            raise TodoError("bad-id", f"not a task id: {value!r}")
        return AI_TODO, value
    kind, sep, value = todo_id.partition(":")
    if not sep or kind not in (ORDER_TODO, CHECK_TODO) or not value:
        raise TodoError(
            "bad-id",
            f"not a todo id: {todo_id!r} (order-failed:<id>, check-failed:<date>,"
            " ai-cli:failed:<task id>)",
        )
    return kind, value


def resolve(
    conn: sqlite3.Connection,
    ledger_id: str,
    todo_id: str,
    at: datetime,
    note: str | None = None,
    max_attempts: int | None = None,
) -> dict[str, Any]:
    """Close one manual action. The caller owns the transaction. Raises TodoError."""
    require_aware(at)
    kind, value = _parse(todo_id)
    if kind == ORDER_TODO:
        return _resolve_plan(conn, ledger_id, todo_id, value, at, note)
    if kind == AI_TODO:
        return _cancel_ai(conn, ledger_id, todo_id, int(value), at, note, _max(max_attempts))
    return _resolve_check(conn, ledger_id, todo_id, value, at, note)


def _ai_task(conn: sqlite3.Connection, ledger_id: str, task_id: int) -> ai_repo.TaskRow:
    try:
        task = ai_repo.get_task(conn, task_id)
    except repo.NotFoundError as exc:
        raise TodoError("not-found", f"no AI task {task_id}") from exc
    if task.ledger_id != ledger_id:
        raise TodoError("not-found", f"AI task {task_id} is not in the {ledger_id} ledger")
    return task


def _cancel_ai(
    conn: sqlite3.Connection,
    ledger_id: str,
    todo_id: str,
    task_id: int,
    at: datetime,
    note: str | None,
    max_attempts: int,
) -> dict[str, Any]:
    """The owner gives an AI task up: cancelled, its kept answer dropped, an event records it."""
    ref = f"todo-resolved:ai-task:{task_id}"
    done = repo.event_by_ref(conn, ledger_id, ref)
    if done is not None:
        return {"result": "already-resolved", "task_id": task_id, "event_id": done.event_id}
    task = _ai_task(conn, ledger_id, task_id)
    if not task.is_stuck(max_attempts):
        raise TodoError(
            "not-a-todo", f"{todo_id} is not an open manual action (task {task.status})"
        )
    ai_repo.keep_answer(conn, task_id, None)
    ai_repo.finish_task(
        conn,
        task_id,
        at,
        status="cancelled",
        result={"cancelled_by": "owner", "note": note},
        error=task.last_error,
    )
    event_id = repo.insert_event(
        conn,
        ledger_id=ledger_id,
        kind="todo-resolved",
        event_date=kst_date(at),
        occurred_at=at,
        rule_id=task.rule_id,
        ref=ref,
        payload={
            "todo_id": todo_id,
            "task_id": task_id,
            "task_kind": task.kind,
            "pick_id": task.pick_id,
            "error": task.last_error,
            "closed": [todo_id],
            "note": note,
        },
    )
    return {"result": "resolved", "task_id": task_id, "closed": [todo_id], "event_id": event_id}


def retry_ai(
    conn: sqlite3.Connection,
    ledger_id: str,
    todo_id: str,
    at: datetime,
    note: str | None = None,
    max_attempts: int | None = None,
    ask_again: bool = False,
) -> dict[str, Any]:
    """Ask a failed AI task again: attempts and source tries back to 0, due now. An answer it
    already got (kept_answer) is applied, not asked again, unless `ask_again` (an answer that
    can never be applied: the model is asked afresh, at the cost of a new call). `todo_id` is
    'ai-cli:failed:<id>' or the task id. The caller owns the transaction. Raises TodoError."""
    require_aware(at)
    value = todo_id[len(AI_TODO) + 1 :] if todo_id.startswith(f"{AI_TODO}:") else todo_id
    if not value.isdigit():
        raise TodoError("bad-id", f"not an AI task: {todo_id!r} (ai-cli:failed:<id> or <id>)")
    task = _ai_task(conn, ledger_id, int(value))
    if task.status != "failed":
        raise TodoError("not-a-todo", f"AI task {value} is {task.status}, not failed")
    stuck = task.is_stuck(_max(max_attempts))
    ai_repo.reset_task(conn, task.task_id, at)
    kept = bool(task.answer_calls) and not ask_again
    if ask_again:
        ai_repo.keep_answer(conn, task.task_id, None)
    event_id = repo.insert_event(
        conn,
        ledger_id=ledger_id,
        kind="todo-resolved",
        event_date=kst_date(at),
        occurred_at=at,
        rule_id=task.rule_id,
        payload={
            "todo_id": f"{AI_TODO}:{task.task_id}",
            "task_id": task.task_id,
            "task_kind": task.kind,
            "action": "retry",
            "ask_again": ask_again,
            "attempts_before": task.attempts,
            "error": task.last_error,
            "closed": [f"{AI_TODO}:{task.task_id}"] if stuck else [],
            "note": note,
        },
    )
    return {
        "result": "retried",
        "task_id": task.task_id,
        "kept_answer": kept,
        "event_id": event_id,
    }


def _resolve_plan(
    conn: sqlite3.Connection,
    ledger_id: str,
    todo_id: str,
    value: str,
    at: datetime,
    note: str | None,
) -> dict[str, Any]:
    if not value.isdigit():
        raise TodoError("bad-id", f"not an order id: {value!r}")
    try:
        order = repo.get_order(conn, int(value))
    except repo.NotFoundError as exc:
        raise TodoError("not-found", f"no order {value}") from exc
    if order.ledger_id != ledger_id:
        raise TodoError("not-found", f"order {value} is not in the {ledger_id} ledger")
    while order.retry_of is not None:  # any attempt's id names the same manual action
        order = repo.get_order(conn, order.retry_of)
    todo_id = f"{ORDER_TODO}:{order.order_id}"
    plan = repo.get_plan(conn, order.plan_id)
    ref = f"todo-resolved:plan:{plan.plan_id}"
    done = repo.event_by_ref(conn, ledger_id, ref)
    if done is not None:
        return {"result": "already-resolved", "plan_id": plan.plan_id, "event_id": done.event_id}
    todos = _order_todos(conn, plan) if plan.status == "todo" else []
    if todo_id not in [t.todo_id for t in todos]:
        raise TodoError(
            "not-a-todo", f"{todo_id} is not an open manual action (plan {plan.status})"
        )
    cancelled = _close_orders(conn, plan.plan_id, at)
    for stage in repo.stages_of(conn, plan.plan_id):
        if stage.status in ("pending", "failed"):
            repo.update_stage(conn, stage.stage_id, status="todo", last_error=f"closed: {todo_id}")
    repo.set_plan_status(conn, plan.plan_id, "resolved", at)
    plan_event = repo.event_of_plan(conn, plan.plan_id)
    if plan_event is not None:
        payload = dict(plan_event.payload)
        payload.update({"resolved_at": at, "resolved_todo": todo_id, "resolved_note": note})
        repo.update_event(conn, plan_event.event_id, at, status="resolved", payload=payload)
    closed = [t.todo_id for t in todos]
    event_id = repo.insert_event(
        conn,
        ledger_id=ledger_id,
        kind="todo-resolved",
        event_date=kst_date(at),
        occurred_at=at,
        rule_id=plan.rule_id,
        ref=ref,
        payload={
            "todo_id": todo_id,
            "plan_id": plan.plan_id,
            "plan_date": plan.plan_date,
            "closed": closed,
            "cancelled_orders": cancelled,
            "note": note,
        },
    )
    refresh_cash_parts(conn, ledger_id, at)
    return {
        "result": "resolved",
        "plan_id": plan.plan_id,
        "closed": closed,
        "cancelled_orders": cancelled,
        "event_id": event_id,
    }


def _close_orders(conn: sqlite3.Connection, plan_id: int, at: datetime) -> list[int]:
    """Cancel what the plan still had to send. A live order already at the broker gets a cancel
    request the tick carries out; it stays pending until the broker ends it, so a fill that
    comes meanwhile is still booked (engine/live.py book_late_fills)."""
    from autotrade.db import live_repo

    out: list[int] = []
    for order in repo.orders_of_plan(conn, plan_id):
        if order.status != "pending":
            continue
        row = live_repo.get_broker_order(conn, order.order_id)
        if row is not None and row.open:
            live_repo.request_cancel(conn, order.order_id, at)
        else:
            repo.cancel_order(conn, order.order_id)
        out.append(order.order_id)
    return out


def _resolve_check(
    conn: sqlite3.Connection,
    ledger_id: str,
    todo_id: str,
    value: str,
    at: datetime,
    note: str | None,
) -> dict[str, Any]:
    try:
        day = date.fromisoformat(value)
    except ValueError as exc:
        raise TodoError("bad-id", f"not a date: {value!r}") from exc
    ref = f"todo-resolved:check:{day.isoformat()}"
    done = repo.event_by_ref(conn, ledger_id, ref)
    if done is not None:
        return {"result": "already-resolved", "date": day, "event_id": done.event_id}
    open_check = _check_todo(conn, ledger_id)
    if open_check is None or open_check.todo_id != todo_id:
        raise TodoError("not-a-todo", f"{todo_id} is not an open manual action")
    failure = repo.check_failure_event(conn, ledger_id, day)
    if failure is None:  # pragma: no cover — _check_todo found it
        raise TodoError("not-found", f"no check failure on {day}")
    payload = dict(failure.payload)
    payload.update({"resolved_at": at, "resolved_note": note})
    repo.update_event(conn, failure.event_id, at, status="resolved", payload=payload)
    event_id = repo.insert_event(
        conn,
        ledger_id=ledger_id,
        kind="todo-resolved",
        event_date=kst_date(at),
        occurred_at=at,
        ref=ref,
        payload={"todo_id": todo_id, "date": day, "closed": [todo_id], "note": note},
    )
    return {"result": "resolved", "date": day, "closed": [todo_id], "event_id": event_id}
