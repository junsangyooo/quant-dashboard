"""What the 5-minute tick runs now, and how late it may still run it (all times KST).

Cron wakes `python -m autotrade.jobs tick` every 5 minutes (deploy/autotrade.cron). Each tick asks
these functions, in this order, what is due; the records (runs, snapshots, the dividend fetch, the
backup files) say what already ran today, so every task runs once however often the tick comes.

  task       due (weekdays unless noted)          a late tick still runs it ...
  ---------  -----------------------------------  ---------------------------------------------
  dividends  08:00, before the check               any time that day; after a failed download it
                                                   waits 60 min (DIVIDEND_RETRY_EVERY)
  check      08:30                                 until 09:30. Down at 08:30, back at 08:47 ->
                                                   the check runs at 08:47 and plans as usual.
  retry      09:30, if today's check failed or     until 15:30 (RETRY_CUTOFF), once: it is the
             never ran                             final attempt (a failure is '직접 할 일')
  stages     each stage's own time: KR 09:05,      whenever. The paper fill is that session's
             FX 09:10, US at the NYSE open         open, so a late run records the same fill; a
             (22:30 KST in US daylight time,       price that never comes fails the stage after
             23:30 otherwise; any day)             its session closes and it is retried the next
                                                   trading day (engine/runner.py)
  snapshot   16:00, or the KRX close + 20 min      until the NYSE opens that evening (22:30 or
             when KRX closes late (수능 16:30)     23:30), midnight on US holidays; a failed
                                                   valuation is retried after 30 min
  backup     after the snapshot (every day;        until midnight (copies are named by KST date)
             from 16:00 on weekends)
  ai-plan    after the watch, while decisions come   until the Korean order time (09:05): a later
             (the AI rule's plan)                    decision waits for the next morning
  watch      08:30, after the check (the AI rule's   any time that day; a crashed run is tried
             daily code checks, phase 2)             again after 30 min. Sessions missed while
                                                     down are scanned by the next run
  ai-queue   22:00 the evening before the 1st        until the 3rd of the month (the monthly
             (monthly reviews; discovery on the      review must not be skipped)
             1st of 4·6·9·12월)

Why the windows end where they do:
- check -> 09:30: from then on the 09:30 retry is the same check as the final attempt.
- retry -> 15:30: a check that could not run before the KRX close waits for the next morning; it
  would plan on the data the next check reads anyway, and the record shows the missed day.
- snapshot -> NYSE open: until the US session opens, the ledger and the prices are what they were
  at 16:00 (only the rate's time differs); after it, that evening's US fills would be valued at
  the previous US close.

Holidays: the check and the snapshot still run on a weekday when a market (or both) is closed;
the check holds the closed market's orders itself (ops notes 매일 확인 2).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path

from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.engine import discovery_plan, reviews
from autotrade.engine import watch as watch_engine
from autotrade.engine.bootstrap import start_date_key
from autotrade.engine.check import FAILED, TODO
from autotrade.engine.runner import eligible_stages
from autotrade.jobs.backup import backup_path
from autotrade.market.calendar import KRX, NYSE
from autotrade.market.service import DIVIDENDS_SERIES
from autotrade.rules.discovery import RULE_ID as DISCOVERY
from autotrade.timeutil import at_kst, is_weekday, kst_date

TICK_EVERY = timedelta(minutes=5)  # deploy/autotrade.cron
DIVIDEND_TIME = time(8, 0)
DIVIDEND_RETRY_EVERY = timedelta(minutes=60)
RETRY_CUTOFF = time(15, 30)
SNAPSHOT_RETRY_EVERY = timedelta(minutes=30)
SNAPSHOT_DONE = ("ok", "not-started", "weekend")
WATCH_RETRY_EVERY = timedelta(minutes=30)
WATCH_DONE = ("ok", "partial", "nothing")


@dataclass(frozen=True)
class Due:
    task: str
    why: str  # 'on-time' | 'late' | 'retry' | 'missed-check' | 'n due'


def _timing(now: datetime, scheduled: datetime) -> str:
    return "on-time" if now - scheduled < TICK_EVERY else "late"


def _waiting_for_start(conn: sqlite3.Connection, ledger_id: str, d: date) -> bool:
    """The ledger has a start date in the future: nothing runs before it."""
    if repo.start_event(conn, ledger_id) is not None:
        return False
    text = repo.get_setting(conn, start_date_key(ledger_id)) or ""
    return bool(text) and d < date.fromisoformat(text)


def dividends_due(conn: sqlite3.Connection, ledger_id: str, now: datetime) -> Due | None:
    d = kst_date(now)
    scheduled = at_kst(d, DIVIDEND_TIME)
    if not is_weekday(d) or now < scheduled or repo.start_event(conn, ledger_id) is None:
        return None
    row = repo.get_freshness(conn, DIVIDENDS_SERIES)
    if row is not None:
        if row.fetched_at is not None and kst_date(row.fetched_at) == d:
            return None  # downloaded today
        if row.attempted_at is not None and now - row.attempted_at < DIVIDEND_RETRY_EVERY:
            return None
        if row.attempted_at is not None and kst_date(row.attempted_at) == d:
            return Due("dividends", "retry")
    return Due("dividends", _timing(now, scheduled))


def check_due(conn: sqlite3.Connection, cfg: Config, ledger_id: str, now: datetime) -> Due | None:
    d = kst_date(now)
    scheduled = at_kst(d, cfg.check_time)
    if not is_weekday(d) or not scheduled <= now < at_kst(d, cfg.retry_time):
        return None
    if _waiting_for_start(conn, ledger_id, d) or repo.runs_on(conn, ledger_id, "check", d):
        return None
    return Due("check", _timing(now, scheduled))


def retry_due(conn: sqlite3.Connection, cfg: Config, ledger_id: str, now: datetime) -> Due | None:
    d = kst_date(now)
    scheduled = at_kst(d, cfg.retry_time)
    if not is_weekday(d) or not scheduled <= now < at_kst(d, RETRY_CUTOFF):
        return None
    if _waiting_for_start(conn, ledger_id, d):
        return None
    runs = repo.runs_on(conn, ledger_id, "check", d)
    if any(r.result not in (FAILED, TODO, None) for r in runs):
        return None  # a check went through today (same test as engine/check.needs_retry)
    if any(r.started_at >= scheduled for r in runs):
        return None  # the retry already ran: it was the final attempt
    return Due("retry", "retry" if runs else "missed-check")


def stages_due(conn: sqlite3.Connection, ledger_id: str, now: datetime) -> Due | None:
    """Stages whose time has come and whose earlier stages are done. A stage that waits on one
    rescheduled to another day is not due, so a failed sell does not make every tick run."""
    eligible = eligible_stages(conn, ledger_id, now)
    if not eligible:
        return None
    return Due("stages", f"{len(eligible)} due")


def snapshot_window(cfg: Config, d: date) -> tuple[datetime, datetime]:
    """[start, end) of the day's snapshot: 16:00 (or the KRX close + publication lag when KRX
    closes later) until the NYSE opens that evening, or midnight when NYSE is closed."""
    start = at_kst(d, cfg.snapshot_time)
    if KRX.is_trading_day(d):
        start = max(start, KRX.session_close(d) + cfg.kr_publication_lag)
    # The NYSE session that opens on the evening of KST day d is the one of ET date d.
    end = NYSE.session_open(d) if NYSE.is_trading_day(d) else at_kst(d + timedelta(days=1), time())
    return start, end


def snapshot_done(conn: sqlite3.Connection, ledger_id: str, d: date) -> bool:
    return any(r.result in SNAPSHOT_DONE for r in repo.runs_on(conn, ledger_id, "snapshot", d))


def snapshot_due(
    conn: sqlite3.Connection, cfg: Config, ledger_id: str, now: datetime
) -> Due | None:
    d = kst_date(now)
    if not is_weekday(d) or _waiting_for_start(conn, ledger_id, d):
        return None
    start, end = snapshot_window(cfg, d)
    if not start <= now < end or snapshot_done(conn, ledger_id, d):
        return None
    runs = repo.runs_on(conn, ledger_id, "snapshot", d)
    if runs:
        if now - runs[-1].started_at < SNAPSHOT_RETRY_EVERY:
            return None
        return Due("snapshot", "retry")
    return Due("snapshot", _timing(now, start))


def backup_due(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_ids: list[str],
    backup_dir: Path,
    now: datetime,
) -> Due | None:
    """Once a day after the day's snapshots (done, or their window closed); weekends from 16:00."""
    d = kst_date(now)
    if backup_path(backup_dir, d).exists():
        return None
    if now < at_kst(d, cfg.snapshot_time):
        return None
    if is_weekday(d):
        _, end = snapshot_window(cfg, d)
        for ledger_id in ledger_ids:
            waiting = not snapshot_done(conn, ledger_id, d) and now < end
            if waiting and not _waiting_for_start(conn, ledger_id, d):
                return None  # the snapshot may still come: back up after it
    return Due("backup", "after-snapshot" if is_weekday(d) else "daily")


def watch_due(conn: sqlite3.Connection, cfg: Config, ledger_id: str, now: datetime) -> Due | None:
    """The AI rule's daily checks: weekdays from the check time, once (a crash retries)."""
    d = kst_date(now)
    scheduled = at_kst(d, cfg.check_time)
    if not is_weekday(d) or now < scheduled or not reviews.rule_active(conn, ledger_id):
        return None
    runs = [r for r in ai_repo.job_runs_on(conn, watch_engine.JOB, d) if r.ledger_id == ledger_id]
    if any(r.result in WATCH_DONE for r in runs):
        return None
    if runs:
        if now - runs[-1].started_at < WATCH_RETRY_EVERY:
            return None
        return Due("watch", "retry")
    return Due("watch", _timing(now, scheduled))


def queue_due(conn: sqlite3.Connection, ledger_id: str, now: datetime) -> Due | None:
    """The month's reviews (and the quarter's discovery), from 22:00 the evening before."""
    month = reviews.review_month(now)
    if month is None or not reviews.rule_active(conn, ledger_id):
        return None
    if reviews.queued_for(conn, ledger_id, month):
        return None
    return Due("ai-queue", "on-time" if kst_date(now) < month else "late")


def ai_plan_due(conn: sqlite3.Connection, cfg: Config, ledger_id: str, now: datetime) -> Due | None:
    """The AI rule's plan: weekdays in [check time, Korean order time), after the ledger's
    first plan, with no discovery plan today or still running, and something to plan."""
    d = kst_date(now)
    start, end = discovery_plan.window(cfg, d)
    if not is_weekday(d) or not start <= now < end or not reviews.rule_active(conn, ledger_id):
        return None
    first = repo.start_event(conn, ledger_id)
    if first is None or first.plan_id is None:
        return None  # the start event's plan (the long-term rule's first buy) comes first
    if repo.plan_on(conn, ledger_id, DISCOVERY, d) is not None:
        return None
    if repo.open_plans(conn, ledger_id, DISCOVERY):
        return None
    if not discovery_plan.has_work(conn, ledger_id, now):
        return None
    prior = discovery_plan.last_run(conn, ledger_id, d)
    return Due("ai-plan", "new-decision" if prior is not None else _timing(now, start))
