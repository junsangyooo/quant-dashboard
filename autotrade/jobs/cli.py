"""python -m autotrade.jobs {check,stage,retry,snapshot,status} --ledger paper [options]

Options: --dry-run, --at ISO, --db PATH.

  check     08:30 weekdays: data, weights, plan (sell -> FX -> buy)
  retry     09:30: runs the check again only if today's check failed or did not run
  stage     run the stages that are due (KR 09:05, FX 09:10, US open); safe to run often
  snapshot  16:00 valuation and the untouched baseline
  status    read-only summary

--at sets the clock for testing (ISO 8601; without an offset it is KST). Output is JSON.
Exit code 1 when the job failed or needs a manual action, 2 when the ledger cannot run.
No cron or systemd is installed by this package.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from autotrade.broker.base import LiveOrdersBlockedError
from autotrade.config import load_config
from autotrade.db.connection import connect, json_default
from autotrade.engine.bootstrap import bootstrap
from autotrade.jobs.tasks import (
    FAILING_RESULTS,
    JobContext,
    check_job,
    snapshot_job,
    stage_job,
    status_job,
)
from autotrade.market.service import MarketSources, default_sources
from autotrade.timeutil import KST, UTC, parse_cli_time

COMMANDS = ("check", "stage", "retry", "snapshot", "status")


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
    parser.add_argument("--ledger", default="paper", choices=("paper", "live"))
    parser.add_argument("--dry-run", action="store_true", help="roll back every ledger change")
    parser.add_argument("--at", help="clock for testing, ISO 8601 (KST when no offset)")
    parser.add_argument("--db", help="database path (default: AUTOTRADE_DB or data/autotrade.db)")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    sources: MarketSources | None = None,
    env: Mapping[str, str] | None = None,
    now: Callable[[], datetime] | None = None,
    out: Callable[[str], Any] = print,
) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(env)
    db_path = Path(args.db) if args.db else cfg.db_path
    at = parse_cli_time(args.at) if args.at else (now or (lambda: datetime.now(UTC)))()
    conn = connect(db_path)
    try:
        bootstrap(conn, cfg, at)
        ctx = JobContext(conn, cfg, sources or default_sources())
        if args.command == "check":
            report = check_job(ctx, args.ledger, at, dry_run=args.dry_run)
        elif args.command == "retry":
            report = check_job(ctx, args.ledger, at, dry_run=args.dry_run, retry=True)
        elif args.command == "stage":
            report = stage_job(ctx, args.ledger, at, dry_run=args.dry_run)
        elif args.command == "snapshot":
            report = snapshot_job(ctx, args.ledger, at, dry_run=args.dry_run)
        else:
            report = status_job(ctx, args.ledger, at)
    except LiveOrdersBlockedError as exc:
        print(json.dumps({"error": "ledger-blocked", "detail": str(exc)}), file=sys.stderr)
        return 2
    finally:
        conn.close()
    out(json.dumps(report, default=_cli_default, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report.get("result") in FAILING_RESULTS else 0
