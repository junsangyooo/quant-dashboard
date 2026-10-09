"""'직접 할 일': listing open manual actions and closing them (jobs todos / resolve)."""

from __future__ import annotations

import sqlite3
from datetime import date

import pytest

from autotrade.db import repo
from autotrade.db.connection import transaction
from autotrade.domain.cash import Purpose
from autotrade.engine.todos import TodoError, open_todos, resolve
from autotrade.jobs.tasks import JobContext, check_job, resolve_job, stage_job, todos_job

from .fakes import KR, US, World
from .helpers import kst
from .test_engine_rebalance import seed_1007


def make_todo(ctx: JobContext, world: World, conn: sqlite3.Connection) -> int:
    """The 10/07 plan whose US buy fails at 22:30 and again on 10/08: '직접 할 일'."""
    seed_1007(conn, world)
    check_job(ctx, "paper", kst("2026-10-07 08:30"))
    stage_job(ctx, "paper", kst("2026-10-07 09:05"))
    stage_job(ctx, "paper", kst("2026-10-07 09:10"))
    world.fail_bars.add(US)
    stage_job(ctx, "paper", kst("2026-10-07 22:30"))
    stage_job(ctx, "paper", kst("2026-10-08 22:30"))
    [plan] = repo.plans_with_status(conn, "paper", "todo")
    return plan.plan_id


def test_list_and_resolve_a_failed_order(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    plan_id = make_todo(ctx, world, conn)
    first = min(o.order_id for o in repo.orders_of_plan(conn, plan_id) if o.side == "buy")
    listed = todos_job(ctx, "paper", kst("2026-10-09 09:00"))
    [todo] = listed["todos"]
    assert todo["id"] == f"order-failed:{first}"  # the same id the web API shows
    assert (todo["kind"], todo["plan_id"], todo["date"]) == (
        "order-failed",
        plan_id,
        date(2026, 10, 7),
    )
    assert (todo["side"], todo["market"], todo["instrument_id"]) == ("buy", "US", US)
    assert (todo["reason"], todo["attempts"], todo["status"]) == ("no-quote", 2, "failed")

    # While it is open the rule makes no new plan.
    world.fail_bars.clear()
    world.bar(KR, "2026-10-08", close="38000", open_="37000")
    world.bar(US, "2026-10-08", close="60.00", open_="61.00")
    world.rate(kst("2026-10-09 08:25"), "1382.4")
    assert check_job(ctx, "paper", kst("2026-10-09 08:30"))["result"] == "partial-failed"

    retry_id = max(o.order_id for o in repo.orders_of_plan(conn, plan_id) if o.side == "buy")
    assert retry_id != first  # the second attempt's id names the same manual action
    out = resolve_job(
        ctx, "paper", f"order-failed:{retry_id}", kst("2026-10-09 10:00"), note="bought in Toss"
    )
    assert out["result"] == "resolved"
    assert (out["plan_id"], out["closed"], out["cancelled_orders"]) == (plan_id, [todo["id"]], [])
    assert out["next_check_at"] == kst("2026-10-12 08:30")
    assert repo.get_plan(conn, plan_id).status == "resolved"
    event = repo.event_of_plan(conn, plan_id)
    assert event is not None
    assert event.status == "resolved"
    assert (event.payload["resolved_todo"], event.payload["resolved_note"]) == (
        todo["id"],
        "bought in Toss",
    )
    [note] = repo.events_of_ledger(conn, "paper", ["todo-resolved"])
    assert (note.ref, note.event_date, note.payload["closed"]) == (
        f"todo-resolved:plan:{plan_id}",
        date(2026, 10, 9),
        [todo["id"]],
    )
    assert todos_job(ctx, "paper", kst("2026-10-09 10:01"))["todos"] == []
    assert [p for p in repo.cash_parts(conn, "paper") if p.purpose is Purpose.BUY_WAIT] == []
    # Twice is a no-op.
    again = resolve_job(ctx, "paper", todo["id"], kst("2026-10-09 10:05"))
    assert (again["result"], again["event_id"]) == ("already-resolved", out["event_id"])

    # The next check plans again from the ledger as it is.
    world.bar(KR, "2026-10-09", close="38000", open_="38000")
    world.bar(US, "2026-10-09", close="60.00", open_="60.00")
    world.rate(kst("2026-10-12 08:25"), "1382.4")
    monday = check_job(ctx, "paper", kst("2026-10-12 08:30"))
    assert monday["result"] == "rebalance"
    assert repo.open_plans(conn, "paper")[-1].plan_id != plan_id


def test_resolving_cancels_what_the_plan_still_had_to_send(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_1007(conn, world)
    plan_id = check_job(ctx, "paper", kst("2026-10-07 08:30"))["plan_id"]
    # A manual action on the sell while the conversion and the US buy are still to come
    # (a broker rejection, say).
    with transaction(conn):
        sell = next(o for o in repo.orders_of_plan(conn, plan_id) if o.side == "sell")
        conn.execute(
            "UPDATE orders SET status = 'failed', manual = 1, failure_reason = 'broker-rejected'"
            " WHERE order_id = ?",
            (sell.order_id,),
        )
        repo.set_plan_status(conn, plan_id, "todo")
    pending = [o.order_id for o in repo.orders_of_plan(conn, plan_id) if o.status == "pending"]
    assert pending
    out = resolve_job(ctx, "paper", f"order-failed:{sell.order_id}", kst("2026-10-07 12:00"))
    assert out["cancelled_orders"] == pending
    assert repo.pending_orders(conn, "paper") == []
    assert all(s.status in ("done", "todo") for s in repo.stages_of(conn, plan_id))
    assert repo.pending_stages(conn, "paper") == []
    # The stage runner never touches a resolved plan again.
    assert stage_job(ctx, "paper", kst("2026-10-07 22:30"))["result"] == "nothing-due"
    assert repo.get_plan(conn, plan_id).status == "resolved"


def test_a_failed_check_is_a_todo_until_resolved_or_a_later_check_succeeds(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    world.fail_bars.update({KR, US})
    world.fail_fx = True
    check_job(ctx, "paper", kst("2026-07-01 08:30"))
    assert open_todos(conn, "paper") == []  # still has its 09:30 retry
    check_job(ctx, "paper", kst("2026-07-01 09:30"), retry=True)
    [todo] = todos_job(ctx, "paper", kst("2026-07-01 10:00"))["todos"]
    assert (todo["id"], todo["kind"], todo["attempts"]) == (
        "check-failed:2026-07-01",
        "check-failed",
        2,
    )
    assert str(todo["error"]).startswith("no-quote")
    out = resolve_job(ctx, "paper", todo["id"], kst("2026-07-01 10:05"), note="checked by hand")
    assert (out["result"], out["closed"]) == ("resolved", [todo["id"]])
    failure = repo.check_failure_event(conn, "paper", date(2026, 7, 1))
    assert failure is not None
    assert (failure.status, failure.payload["resolved_note"]) == ("resolved", "checked by hand")
    assert open_todos(conn, "paper") == []
    again = resolve_job(ctx, "paper", todo["id"], kst("2026-07-01 10:06"))
    assert again["result"] == "already-resolved"

    # Another day fails for good, then a later check works: nothing left to do.
    check_job(ctx, "paper", kst("2026-07-02 08:30"))
    check_job(ctx, "paper", kst("2026-07-02 09:30"), retry=True)
    assert [t.todo_id for t in open_todos(conn, "paper")] == ["check-failed:2026-07-02"]
    world.fail_bars.clear()
    world.fail_fx = False
    world.bar(KR, "2026-07-02", close="32000")
    world.bar(US, "2026-07-02", close="66.00")
    world.rate(kst("2026-07-03 08:25"), "1390.0")
    assert check_job(ctx, "paper", kst("2026-07-03 08:30"))["result"] != "failed"
    assert open_todos(conn, "paper") == []


@pytest.mark.parametrize(
    ("todo_id", "code"),
    [
        ("nonsense", "bad-id"),
        ("order-failed:", "bad-id"),
        ("order-failed:abc", "bad-id"),
        ("order-failed:999999", "not-found"),
        ("check-failed:2026-13-01", "bad-id"),
        ("check-failed:2026-07-01", "not-a-todo"),
    ],
)
def test_bad_todo_ids(ctx: JobContext, conn: sqlite3.Connection, todo_id: str, code: str) -> None:
    out = resolve_job(ctx, "paper", todo_id, kst("2026-07-01 10:00"))
    assert out["result"] == code
    assert out["error"]


def test_only_open_manual_actions_can_be_resolved(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    seed_1007(conn, world)
    plan_id = check_job(ctx, "paper", kst("2026-10-07 08:30"))["plan_id"]
    order = repo.orders_of_plan(conn, plan_id)[0]
    with transaction(conn), pytest.raises(TodoError, match="not an open manual action") as err:
        resolve(conn, "paper", f"order-failed:{order.order_id}", kst("2026-10-07 09:00"))
    assert err.value.code == "not-a-todo"
    with transaction(conn), pytest.raises(TodoError) as other:
        resolve(conn, "live", f"order-failed:{order.order_id}", kst("2026-10-07 09:00"))
    assert other.value.code == "not-found"  # another ledger's order
    assert repo.get_plan(conn, plan_id).status == "in-progress"
