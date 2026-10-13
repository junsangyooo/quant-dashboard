"""A read-only summary of one ledger, for the jobs CLI and for debugging."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, time, timedelta
from typing import Any

from autotrade.config import Config
from autotrade.db import repo
from autotrade.domain.status import StatusFlags, rule_status
from autotrade.engine.bootstrap import MODE
from autotrade.engine.rebuild import verify_ledger
from autotrade.timeutil import KST, at_kst, is_weekday, kst_date, require_aware


def next_check_at(cfg: Config, at: datetime) -> datetime:
    """The next weekday check time strictly after `at`."""
    d = kst_date(at)
    for i in range(8):
        candidate = at_kst(d + timedelta(days=i), cfg.check_time)
        if candidate > at and is_weekday(candidate.date()):
            return candidate
    raise RuntimeError("no weekday within a week")  # pragma: no cover


def first_check_after(cfg: Config, d: date) -> datetime:
    """The first weekday check on a later day than `d` (KST): when the owner's money of day d
    is used (D48)."""
    return next_check_at(cfg, at_kst(d + timedelta(days=1), time(0, 0)))


def ledger_status(
    conn: sqlite3.Connection, cfg: Config, ledger_id: str, at: datetime
) -> dict[str, Any]:
    require_aware(at)
    ledger = repo.get_ledger(conn, ledger_id)
    state = repo.load_state(conn, ledger_id)
    parts = repo.cash_parts(conn, ledger_id)
    last = repo.last_run(conn, ledger_id, "check")
    open_plans = repo.open_plans(conn, ledger_id)
    today = kst_date(at)
    today_runs = repo.runs_on(conn, ledger_id, "check", today)
    last_today = today_runs[-1].result if today_runs else None
    freshness = repo.all_freshness(conn)

    plans_json: list[dict[str, Any]] = []
    todo: list[dict[str, Any]] = []
    for plan in open_plans:
        stages_json = []
        for stage in repo.stages_of(conn, plan.plan_id):
            orders = [
                {
                    "order_id": o.order_id,
                    "side": o.side,
                    "instrument_id": o.instrument_id,
                    "qty": o.qty,
                    "est_amount": o.est_amount,
                    "currency": o.currency.value,
                    "status": o.status,
                    "attempt": o.attempt,
                    "failure": o.failure_reason,
                    "retry_at": o.retry_at,
                    "manual": o.manual,
                }
                for o in repo.orders_of_stage(conn, stage.stage_id)
            ]
            stages_json.append(
                {
                    "kind": stage.kind,
                    "market": stage.market,
                    "status": stage.status,
                    "due_at": stage.due_at.astimezone(KST),
                    "orders": orders,
                }
            )
            if stage.status == "todo":
                todo.append(
                    {
                        "plan_id": plan.plan_id,
                        "stage": stage.kind,
                        "market": stage.market,
                        "error": stage.last_error,
                    }
                )
        plans_json.append(
            {
                "plan_id": plan.plan_id,
                "rule_id": plan.rule_id,
                "date": plan.plan_date,
                "status": plan.status,
                "stages": stages_json,
            }
        )
    failure = repo.check_failure_event(conn, ledger_id, today)
    if failure is not None and failure.status == "todo":
        todo.append({"check_failed": today, "error": failure.payload.get("error")})

    flags = StatusFlags(
        quote_wait=last_today == "quote-wait" or any(f.state == "stale" for f in freshness),
        partial_failed=any(p.status in ("partial-failed", "todo") for p in open_plans),
        in_progress=any(p.status == "in-progress" for p in open_plans),
        withdraw_wait=any(p.purpose.value == "withdraw_wait" for p in parts),
        holiday=last_today == "holiday",
        scheduled=last is None,
    )
    snap = repo.latest_snapshot_before(conn, ledger_id, today + timedelta(days=1))
    return {
        "ledger": ledger_id,
        "mode": repo.get_setting(conn, MODE),
        "start": {"date": ledger.start_date, "amount": ledger.start_amount},
        "rule_status": rule_status(flags).value,
        "last_check": None
        if last is None
        else {
            "at": last.started_at.astimezone(KST),
            "result": last.result,
            "seconds": None if last.duration_ms is None else round(last.duration_ms / 1000, 1),
            "error": last.error,
        },
        "next_check_at": next_check_at(cfg, at),
        "cash": {c.value: state.cash_of(c) for c in state.cash},
        "cash_parts": [
            {
                "currency": p.currency.value,
                "purpose": p.purpose.value,
                "amount": p.amount,
                "instrument_id": p.instrument_id,
                "until": p.until,
            }
            for p in parts
        ],
        "positions": [
            {
                "instrument_id": p.instrument_id,
                "qty": p.qty,
                "avg_price": p.avg_price,
                "cost_krw": p.cost_krw,
            }
            for p in state.positions.values()
        ],
        "open_plans": plans_json,
        "todo": todo,
        "snapshot": None
        if snap is None
        else {
            "date": snap.date,
            "total_krw": snap.total_krw,
            "pnl_krw": snap.pnl_krw,
            "baseline_krw": snap.baseline_krw,
            "stale": snap.stale,
        },
        "freshness": [
            {
                "series": f.series,
                "state": f.state,
                "basis": f.basis,
                "missing_sessions": f.missing_sessions,
                "fetched_at": f.fetched_at,
                "error": f.error,
            }
            for f in freshness
        ],
        "ledger_check": verify_ledger(conn, ledger_id),
    }
