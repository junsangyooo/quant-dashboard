"""python -m autotrade.jobs <command> [options]

Options: --ledger paper, --dry-run, --at ISO, --db PATH, --note TEXT (resolve, ai-retry),
--predeploy (backup).

  tick       what cron runs every 5 minutes: decides what is due now and runs it (see
             autotrade/jobs/schedule.py for the times and how late each may still run).
             One JSON line per task that ran; nothing when nothing is due.
  check      08:30 weekdays: data, weights, plan (sell -> FX -> buy)
  retry      09:30: runs the check again only if today's check failed or did not run
  stage      run the stages that are due (KR 09:05, FX 09:10, US open); safe to run often
  snapshot   16:00 valuation and the untouched baseline
  dividends  download recent dividends of what the ledger holds and book those paid by today
  backup     copy the database to data/backup/autotrade/autotrade-<date>.db (7 kept).
             --predeploy: autotrade-predeploy-<UTC YYYYmmdd-HHMMSS>.db instead (5 kept apart from
             the daily ones), one JSON line with its path; no lock and any schema (deploy.sh runs
             it before migrate). No database yet: {"job":"backup","result":"no-database"}, exit 0
  watch      the AI rule's daily code checks (filings, sell and buy conditions, price shocks,
             the 'vs index' line, scores); it queues AI tasks and never trades
  ai-plan    turn the AI rule's decisions into a plan (the tick runs it before 09:05)
  ai         run the due AI tasks through the subscription CLI (its own cron line, its own lock
             data/autotrade.db-ai.lock: a call has no time limit). Calls only when
             AUTOTRADE_AI_CALLS=1; without it the tasks wait and only the runner's heartbeat
             is written
  ai-retry   ai-retry <ai-cli:failed:<id> | id> [--note TEXT] [--ask-again]: ask a failed AI
             task again (attempts back to 0; an answer it already got is applied, not asked
             again, unless --ask-again). `resolve ai-cli:failed:<id>` gives it up instead
  todos      list the open '직접 할 일' (manual actions) with their ids
  resolve    resolve <todo-id> [--note TEXT]: close a manual action after handling it (e.g. in
             the Toss app); the rule plans again at the next check
  status     read-only summary
  migrate    create or upgrade data/autotrade.db and write its fixed rows (deploy.sh runs it);
             the only command that changes the schema. The file is made 0600 (and -wal/-shm)
  set-pin    set the owner PIN (first time or reset). Reads it twice from standard input,
             never from the command line, closes every open session and clears the lockout
             (as unlock does).
  unlock     clear every wrong PIN and PIN lock: reopens new logins after 'PIN 실패 급증' closed
             them and takes the alert off the screens. Open sessions are untouched.
  dev-seed   development only: build a new database at --db by replaying the engine on a scripted
             market (--world first-day | paper | discovery, autotrade/dev/worlds.py). No network,
             no AI CLI. --pin sets the owner PIN without asking (default 123456); no other command
             takes it. Refuses data/, the configured ledger and an existing file (exit 2).

--at sets the clock for testing (ISO 8601; without an offset it is KST). Output is JSON.
Jobs that write take a lock (data/autotrade.db-jobs.lock): tick skips its turn when another job
holds it; the other commands wait for it up to 2 minutes and exit with 3 if it stays busy.
Every command but migrate, backup and dev-seed first compares the stored schema with the code's:
behind or ahead (a missing database is 0), it writes one line
{"job": ..., "result": "schema-mismatch", "stored": N, "code": M} and exits 3, doing nothing.
Exit code 1 when a job failed or needs a manual action, 2 when the ledger cannot run.
"""

from __future__ import annotations

import argparse
import getpass
import json
import sqlite3
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Any, TextIO

from autotrade.broker.base import LiveOrdersBlockedError
from autotrade.config import Config, load_config
from autotrade.db.connection import connect, json_default, secure_files
from autotrade.db.migrations import LATEST_VERSION, current_version, stored_version
from autotrade.engine.bootstrap import bootstrap
from autotrade.jobs.ai_tasks import ai_job, plan_job, watch_job
from autotrade.jobs.backup import BackupError, backup_dir_for, run_predeploy_backup
from autotrade.jobs.lock import ai_lock_path, job_lock, lock_path
from autotrade.jobs.tasks import (
    FAILING_RESULTS,
    JobContext,
    ai_retry_job,
    backup_job,
    check_job,
    dividend_job,
    resolve_job,
    snapshot_job,
    stage_job,
    status_job,
    todos_job,
)
from autotrade.jobs.tick import run_tick
from autotrade.market.service import MarketSources, default_sources
from autotrade.timeutil import KST, UTC, parse_cli_time

COMMANDS = (
    "tick",
    "check",
    "retry",
    "stage",
    "snapshot",
    "dividends",
    "backup",
    "watch",
    "ai-plan",
    "ai",
    "ai-retry",
    "todos",
    "resolve",
    "status",
    "migrate",
    "set-pin",
    "unlock",
    "dev-seed",
)
LOCKED = (
    "tick",
    "check",
    "retry",
    "stage",
    "snapshot",
    "dividends",
    "backup",
    "watch",
    "ai-plan",
    "resolve",
    "ai-retry",
)
LOCK_WAIT_S = 120.0
EXIT_BUSY = 3
EXIT_SCHEMA = 3  # the stored schema is not the code's: `migrate` first (deploy.sh)
TAKES_ID = ("resolve", "ai-retry")


def _cli_default(value: object) -> Any:
    """Times in the output are shown in KST (+09:00); the database keeps UTC."""
    if isinstance(value, datetime):
        return value.astimezone(KST).isoformat(timespec="seconds")
    return json_default(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m autotrade.jobs", description=__doc__.split("\n")[0]
    )
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("todo_id", nargs="?", help="resolve, ai-retry: the id that 'todos' lists")
    parser.add_argument("--ledger", default="paper", choices=("paper", "live"))
    parser.add_argument("--dry-run", action="store_true", help="roll back every ledger change")
    parser.add_argument("--at", help="clock for testing, ISO 8601 (KST when no offset)")
    parser.add_argument("--db", help="database path (default: AUTOTRADE_DB or data/autotrade.db)")
    parser.add_argument("--note", help="resolve, ai-retry: what the owner did (kept in the event)")
    parser.add_argument(
        "--predeploy", action="store_true", help="backup: the copy deploy.sh makes before migrate"
    )
    parser.add_argument(
        "--ask-again", action="store_true", help="ai-retry: drop a kept answer, ask the model"
    )
    parser.add_argument(
        "--world", choices=("first-day", "paper", "discovery"), help="dev-seed: the world"
    )
    parser.add_argument("--pin", help="dev-seed only: the owner PIN of the new database")
    return parser


def _dev_seed(
    args: argparse.Namespace, env: Mapping[str, str] | None, out: Callable[[str], Any]
) -> int:
    # Imported here: the dev worlds are never needed by the server's jobs.
    from autotrade.dev.worlds import DevSeedRefusedError, dev_seed

    try:
        report = dev_seed(Path(args.db) if args.db else None, args.world, args.pin, env=env)
    except DevSeedRefusedError as exc:
        print(
            json.dumps({"job": "dev-seed", "result": "refused", "error": str(exc)}), file=sys.stderr
        )
        return 2
    out(_dump(report))
    return 0


def _read_pin_twice(stdin: TextIO) -> tuple[str, str]:
    if stdin.isatty():
        return getpass.getpass("New PIN (6 digits): "), getpass.getpass("Again: ")
    return stdin.readline().strip(), stdin.readline().strip()


def _set_pin(conn: sqlite3.Connection, cfg: Config, at: datetime, stdin: TextIO) -> dict[str, Any]:
    # Imported here: the web API stack is only needed for this command.
    from autotrade.api.auth import set_pin
    from autotrade.api.security import is_valid_pin, load_or_create_secret
    from autotrade.api.settings import default_settings

    first, second = _read_pin_twice(stdin)
    if not is_valid_pin(first):
        return {"job": "set-pin", "result": "failed", "error": "invalid-pin"}
    if first != second:
        return {"job": "set-pin", "result": "failed", "error": "pin-mismatch"}
    settings = default_settings(cfg)
    reset = set_pin(conn, load_or_create_secret(settings.secret_path), first, settings.scrypt_n, at)
    return {
        "job": "set-pin",
        "result": "ok",
        "revokedSessions": reset.revoked,
        **_lockout_report(reset.unlocked),
    }


def _lockout_report(cleared: Any) -> dict[str, Any]:
    """What unlock / set-pin cleared (autotrade.api.auth.Unlocked)."""
    return {
        "clearedFailures": cleared.failures,
        "clearedLocks": cleared.locks,
        "wasClosed": cleared.held,
        "wasAlerted": cleared.alerted,
    }


def _unlock(conn: sqlite3.Connection) -> dict[str, Any]:
    from autotrade.api.auth import unlock  # the web API stack is only needed for this command

    return {"job": "unlock", "result": "ok", **_lockout_report(unlock(conn))}


def _dump(report: dict[str, Any], *, line: bool = False) -> str:
    if line:
        return json.dumps(report, default=_cli_default, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(report, default=_cli_default, ensure_ascii=False, indent=2, sort_keys=True)


def _quiet(report: dict[str, Any]) -> bool:
    """An AI run with nothing to do writes nothing (cron calls it every 5 minutes)."""
    return report.get("result") == "nothing-due" or (
        report.get("result") in ("disabled", "cli-missing") and not report.get("due")
    )


def _dispatch(
    args: argparse.Namespace,
    ctx: JobContext,
    clock: Callable[[], datetime],
    stdin: TextIO,
) -> dict[str, Any]:
    at = clock()
    ledger, dry = args.ledger, args.dry_run
    if args.command == "migrate":
        report: dict[str, Any] = {
            "job": "migrate",
            "result": "ok",
            "schema": current_version(ctx.conn),
        }
        secured = secure_files(ctx.cfg.db_path)  # a database made before files were 0600
        if secured:
            report["secured"] = secured
        return report
    if args.command == "set-pin":
        return _set_pin(ctx.conn, ctx.cfg, at, stdin)
    if args.command == "unlock":
        return _unlock(ctx.conn)
    if args.command == "check":
        return check_job(ctx, ledger, at, dry_run=dry)
    if args.command == "retry":
        return check_job(ctx, ledger, at, dry_run=dry, retry=True)
    if args.command == "stage":
        return stage_job(ctx, ledger, at, dry_run=dry)
    if args.command == "snapshot":
        return snapshot_job(ctx, ledger, at, dry_run=dry)
    if args.command == "dividends":
        return dividend_job(ctx, ledger, at, dry_run=dry)
    if args.command == "backup":
        return backup_job(ctx, at)
    if args.command == "watch":
        return watch_job(ctx, ledger, at, dry_run=dry)
    if args.command == "ai":
        return ai_job(ctx, clock)
    if args.command == "ai-plan":
        return plan_job(ctx, ledger, at, dry_run=dry)
    if args.command == "todos":
        return todos_job(ctx, ledger, at)
    if args.command in TAKES_ID and not args.todo_id:
        error = f"give the todo id: {args.command} <id>"
        return {"job": args.command, "result": "bad-id", "error": error}
    if args.command == "resolve":
        return resolve_job(ctx, ledger, args.todo_id, at, note=args.note, dry_run=dry)
    if args.command == "ai-retry":
        return ai_retry_job(
            ctx, ledger, args.todo_id, at, note=args.note, ask_again=args.ask_again, dry_run=dry
        )
    return status_job(ctx, ledger, at)


def _tick(
    args: argparse.Namespace,
    ctx: JobContext,
    clock: Callable[[], datetime],
    out: Callable[[str], Any],
) -> int:
    ctx.executor(args.ledger)  # a ledger without an executor cannot tick (exit 2)

    def emit(line: dict[str, Any]) -> None:
        out(_dump(line, line=True))
        sys.stdout.flush()  # each line reaches the log even if the tick is killed later

    lines = run_tick(ctx, args.ledger, clock, backup_dir_for(ctx.cfg.db_path), emit)
    return 1 if any(line.get("result") in FAILING_RESULTS for line in lines) else 0


def _run(
    args: argparse.Namespace,
    cfg: Config,
    sources: MarketSources | None,
    clock: Callable[[], datetime],
    out: Callable[[str], Any],
    stdin: TextIO,
) -> int:
    if args.command != "migrate" and not cfg.db_path.exists():
        if args.command == "backup":
            out(_dump({"job": "backup", "result": "no-database"}, line=True))
            return 0
        out(_dump(_mismatch(args.command, 0), line=True))  # never creates the file
        return EXIT_SCHEMA
    conn = connect(cfg.db_path)
    try:
        if args.command == "migrate":
            bootstrap(conn, cfg, clock())  # the only place a job changes the schema
        elif args.command != "backup":  # a copy reads any schema
            stored = stored_version(conn)
            if stored != LATEST_VERSION:
                out(_dump(_mismatch(args.command, stored), line=True))
                return EXIT_SCHEMA
        ctx = JobContext(conn, cfg, sources or default_sources(cfg))
        if args.command == "tick":
            return _tick(args, ctx, clock, out)
        report = _dispatch(args, ctx, clock, stdin)
    except LiveOrdersBlockedError as exc:
        print(json.dumps({"error": "ledger-blocked", "detail": str(exc)}), file=sys.stderr)
        return 2
    finally:
        conn.close()
    if args.command == "ai" and _quiet(report):
        return 0
    out(_dump(report, line=args.command == "ai"))  # the AI log gets one line per run
    return 1 if report.get("result") in FAILING_RESULTS else 0


def _mismatch(command: str, stored: int) -> dict[str, Any]:
    return {"job": command, "result": "schema-mismatch", "stored": stored, "code": LATEST_VERSION}


def _predeploy(cfg: Config, clock: Callable[[], datetime], out: Callable[[str], Any]) -> int:
    """The copy deploy.sh makes before `migrate`: no lock (a copy only reads), any schema."""
    if not cfg.db_path.exists():
        out(_dump({"job": "backup", "result": "no-database"}, line=True))
        return 0
    conn = connect(cfg.db_path)
    try:
        report = run_predeploy_backup(conn, backup_dir_for(cfg.db_path), clock())
    except (BackupError, sqlite3.Error, OSError) as exc:
        error = f"{type(exc).__name__}: {exc}"
        out(_dump({"job": "backup", "result": "failed", "error": error}, line=True))
        return 1
    finally:
        conn.close()
    out(_dump({"job": "backup", "predeploy": True, **report}, line=True))
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    sources: MarketSources | None = None,
    env: Mapping[str, str] | None = None,
    now: Callable[[], datetime] | None = None,
    out: Callable[[str], Any] = print,
    stdin: TextIO | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.todo_id is not None and args.command not in TAKES_ID:
        # Only 'resolve' and 'ai-retry' take a value; above all, a PIN is never an argument.
        parser.error(f"{args.command} takes no argument")
    if args.predeploy and args.command != "backup":
        parser.error("--predeploy is only for backup")
    if args.ask_again and args.command != "ai-retry":
        parser.error("--ask-again is only for ai-retry")
    if args.command != "dev-seed" and (args.pin is not None or args.world is not None):
        # The owner PIN of a real ledger comes from standard input only (set-pin).
        parser.error("--pin and --world are only for dev-seed")
    if args.command == "dev-seed":
        if args.world is None:
            parser.error("dev-seed needs --world (first-day, paper or discovery)")
        return _dev_seed(args, env, out)
    cfg = load_config(env)
    if args.db:
        cfg = replace(cfg, db_path=Path(args.db))
    fixed = parse_cli_time(args.at) if args.at else None

    def clock() -> datetime:
        if fixed is not None:
            return fixed
        return (now or (lambda: datetime.now(UTC)))()

    if args.command == "backup" and args.predeploy:
        return _predeploy(cfg, clock, out)
    if args.command == "ai":
        with job_lock(ai_lock_path(cfg.db_path), 0.0) as locked:
            if not locked:  # the previous run is still asking
                out(_dump({"job": "ai", "result": "busy", "at": clock()}, line=True))
                return 0
            return _run(args, cfg, sources, clock, out, stdin or sys.stdin)
    if args.command not in LOCKED:
        return _run(args, cfg, sources, clock, out, stdin or sys.stdin)
    tick = args.command == "tick"
    with job_lock(lock_path(cfg.db_path), 0.0 if tick else LOCK_WAIT_S) as locked:
        if not locked:
            out(_dump({"job": args.command, "result": "busy", "at": clock()}, line=tick))
            return 0 if tick else EXIT_BUSY
        return _run(args, cfg, sources, clock, out, stdin or sys.stdin)
