"""'직접 할 일' (manual actions): list them, and close one after the owner has handled it.

Two kinds, with the ids the web API shows (autotrade/api/views/health.py):

- 'order-failed:<order id>': an order of a plan in 'todo' status. It failed again on its retry,
  the broker rejected it (인계 11), or it waited on a stage that did (it was cancelled). The id is
  the order's first attempt. While such a plan is open the rule makes no new plan (engine/check).
- 'check-failed:<YYYY-MM-DD>': the day's check failed on its last attempt and no check has
  succeeded since.

resolve() closes one after the owner has dealt with it (in the Toss app, for a live order):

- an order todo closes its whole plan: what the plan still had to send is cancelled, its stages
  stop, the plan and its event become 'resolved', and the next check plans again from the ledger
  as it is (fills that happened stay; nothing is invented for the order that did not fill);
- a check todo marks that day's failure as handled.

Either way an event 'todo-resolved' records it (with the owner's note), under a natural key so
that resolving twice changes nothing.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from autotrade.db import repo
from autotrade.db.models import OrderRow, PlanRow
from autotrade.engine.common import refresh_cash_parts
from autotrade.timeutil import kst_date, require_aware

ORDER_TODO = "order-failed"
CHECK_TODO = "check-failed"
FAILED_RESULTS = ("failed", "todo")


class TodoError(ValueError):
    """The id is malformed, unknown, or not an open manual action."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True)
class Todo:
    todo_id: str
    kind: str  # ORDER_TODO | CHECK_TODO
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


def open_todos(conn: sqlite3.Connection, ledger_id: str) -> list[Todo]:
    out: list[Todo] = []
    for plan in repo.plans_with_status(conn, ledger_id, "todo"):
        out.extend(_order_todos(conn, plan))
    check = _check_todo(conn, ledger_id)
    if check is not None:
        out.append(check)
    return out


def _parse(todo_id: str) -> tuple[str, str]:
    kind, sep, value = todo_id.partition(":")
    if not sep or kind not in (ORDER_TODO, CHECK_TODO) or not value:
        raise TodoError(
            "bad-id", f"not a todo id: {todo_id!r} (order-failed:<id>, check-failed:<date>)"
        )
    return kind, value


def resolve(
    conn: sqlite3.Connection, ledger_id: str, todo_id: str, at: datetime, note: str | None = None
) -> dict[str, Any]:
    """Close one manual action. The caller owns the transaction. Raises TodoError."""
    require_aware(at)
    kind, value = _parse(todo_id)
    if kind == ORDER_TODO:
        return _resolve_plan(conn, ledger_id, todo_id, value, at, note)
    return _resolve_check(conn, ledger_id, todo_id, value, at, note)


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
    cancelled = repo.cancel_pending_orders_of_plan(conn, plan.plan_id)
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
