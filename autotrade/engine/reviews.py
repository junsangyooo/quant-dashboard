"""When the AI rule's monthly review and quarterly discovery are queued (PHASE2.md §7, D30).

The review of a month runs before the 08:30 check of its first day: from 22:00 KST the evening
before, one 'monthly-review' task per held pick (the AI runner takes them in turn). On the first
of April, June, September and December a 'discovery' task follows; the runner takes reviews
first, so the discovery sees this month's verdicts. A server that was down that evening still
queues them on the first three days of the month.

The rule takes part only in a ledger where it has a share and the ledger has started; in phase 2
that is the paper ledger (the live share is 0).
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta
from typing import Any

from autotrade.db import ai_repo, repo
from autotrade.rules.discovery import RULE_ID
from autotrade.timeutil import at_kst, kst_date

JOB = "ai-queue"
REVIEW_TIME = time(22, 0)
LATE_DAYS = 3
DISCOVERY_MONTHS = (4, 6, 9, 12)


def rule_active(conn: sqlite3.Connection, ledger_id: str) -> bool:
    """The AI rule has money in this ledger: a share above 0, a started ledger, and money it
    received (a ledger started before phase 2 gives the rule nothing until a deposit: the code
    never moves money between rules, PHASE2.md §1). Without money nothing is watched or asked."""
    share = ai_repo.shares(conn, ledger_id).get(RULE_ID)
    if not share or share <= 0 or repo.start_event(conn, ledger_id) is None:
        return False
    return ai_repo.load_sleeve(conn, ledger_id, RULE_ID).contributions_krw > 0


def review_month(at: datetime) -> date | None:
    """The first day of the month whose review is due at `at`, if any."""
    d = kst_date(at)
    tomorrow = d + timedelta(days=1)
    if tomorrow.day == 1 and at >= at_kst(d, REVIEW_TIME):
        return tomorrow
    if d.day <= LATE_DAYS:
        return d.replace(day=1)
    return None


def queued_for(conn: sqlite3.Connection, ledger_id: str, month: date) -> bool:
    return any(
        r.result == "ok" for r in ai_repo.job_runs_on(conn, JOB, month) if r.ledger_id == ledger_id
    )


def queue_reviews(conn: sqlite3.Connection, ledger_id: str, at: datetime) -> dict[str, Any]:
    """Queue the month's reviews (and the quarter's discovery). Idempotent."""
    month = review_month(at)
    if month is None:
        return {"result": "not-due"}
    key = month.strftime("%Y-%m")
    not_before = at_kst(month - timedelta(days=1), REVIEW_TIME)
    created: list[dict[str, Any]] = []
    for pick in ai_repo.picks_of(conn, ledger_id, RULE_ID, ("held",)):
        task_id, new = ai_repo.enqueue_task(
            conn,
            kind="monthly-review",
            ledger_id=ledger_id,
            rule_id=RULE_ID,
            trigger="monthly",
            dedup_key=f"monthly-review:{pick.pick_id}:{key}",
            at=at,
            not_before=not_before,
            pick_id=pick.pick_id,
            detail={"month": key},
        )
        if new:
            created.append(
                {"task_id": task_id, "kind": "monthly-review", "pick": pick.instrument_id}
            )
    if month.month in DISCOVERY_MONTHS:
        task_id, new = ai_repo.enqueue_task(
            conn,
            kind="discovery",
            ledger_id=ledger_id,
            rule_id=RULE_ID,
            trigger="discovery",
            dedup_key=f"discovery:{ledger_id}:{key}",
            at=at,
            not_before=not_before,
            detail={"month": key},
        )
        if new:
            created.append({"task_id": task_id, "kind": "discovery"})
    ai_repo.insert_job_run(
        conn,
        job=JOB,
        ledger_id=ledger_id,
        run_date=month,
        started_at=at,
        ended_at=at,
        result="ok",
        error=None,
        details={"month": key, "tasks": created},
    )
    return {"result": "ok", "month": key, "tasks": created}
