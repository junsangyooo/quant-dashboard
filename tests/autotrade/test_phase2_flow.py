"""Phase 2 end to end on the paper ledger: the daily lane of '3년 발굴' (Figma 17:5855).

08:30 tick: check, then the watch sees a shock -> the AI runner asks twice, both '반증' ->
08:45 tick: the planner sells the pick and parks the money in the index ETF -> 09:05 stage ->
the next morning the pick is closed as sold. (The seed was picked on 10/7: shocks count after.)
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

from autotrade.ai.cli import ClaudeCli
from autotrade.ai.runner import run_ai
from autotrade.db import ai_repo, repo
from autotrade.engine import sleeves
from autotrade.engine.rebuild import verify_ledger
from autotrade.jobs.tasks import JobContext
from autotrade.jobs.tick import run_tick
from autotrade.rules.discovery import RULE_ID

from .ai_fakes import ScriptedRunner, sell
from .fakes import World
from .helpers import kst
from .phase2 import flat_world, pick_of
from .test_discovery_plan import seed_prices

D = Decimal
OCEAN = "KR:042660"


def tick(ctx: JobContext, when: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    return run_tick(ctx, "paper", lambda: kst(when), ctx.cfg.db_path.parent, lines.append)


def test_a_shock_confirmed_twice_sells_at_the_next_stage(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    # 10/13: the first plan buys the seed (13 shares of each 10,000-won Korean pick).
    for t in ("2026-10-13 08:25", "2026-10-13 09:10", "2026-10-14 08:25", "2026-10-15 08:25"):
        world.rate(kst(t), "1400.0")
    seed_prices(p2conn, world, ["2026-10-12", "2026-10-13"], "10000")
    names = [line["task"] for line in tick(p2ctx, "2026-10-13 08:40")]
    assert "ai-plan" in names
    for t in ("09:05", "09:10", "22:30"):
        tick(p2ctx, f"2026-10-13 {t}")
    assert ai_repo.load_sleeve(p2conn, "paper", RULE_ID).qty_of(OCEAN) == 13

    # 10/14 08:30: the watch finds 한화오션 10% under its index on 10/13.
    seed_prices(p2conn, world, ["2026-10-14"], "10000")
    world.bar(OCEAN, "2026-10-14", close="9000", open_="9000")
    flat_world(
        p2conn,
        world,
        "2026-10-14",
        start="2026-08-01",
        overrides={"042660.KS": lambda i, d: "90" if d >= date(2026, 10, 13) else "100"},
    )
    lines = tick(p2ctx, "2026-10-14 08:30")
    watch = next(line for line in lines if line["task"] == "watch")
    assert ("sell-confirm", OCEAN) in [(t["kind"], t["pick"]) for t in watch["tasks"]]

    # 08:35: the AI runner (its own cron line) asks twice; both say '반증'.
    runner = ScriptedRunner()
    runner.add("sell", sell("반증"), sell("반증"))
    cfg = replace(p2ctx.cfg, ai_calls_enabled=True)
    at = kst("2026-10-14 08:35")
    cli = ClaudeCli("claude", p2ctx.cfg.db_path.parent / "ai-cwd", runner=runner, now=lambda: at)
    report = run_ai(p2conn, cfg, p2ctx.sources, cli, lambda: at)
    assert [t["kind"] for t in report["tasks"]] == ["sell-confirm"]
    assert pick_of(p2conn, OCEAN).decision == "sell"

    # 08:45: the planner sells all 13 shares and parks the money; 09:05 the stage fills.
    lines = tick(p2ctx, "2026-10-14 08:45")
    plan_line = next(line for line in lines if line["task"] == "ai-plan")
    assert plan_line["result"] == "planned"
    assert [OCEAN, 13] in [list(x) for x in plan_line["sell"]]
    assert any(x[0] == "KR:069500" for x in plan_line["buy"])
    tick(p2ctx, "2026-10-14 09:05")
    assert ai_repo.load_sleeve(p2conn, "paper", RULE_ID).qty_of(OCEAN) == 0

    # The next weekday's planner run closes the pick as sold on the day it filled.
    seed_prices(p2conn, world, ["2026-10-15"], "10000")
    flat_world(p2conn, world, "2026-10-15", start="2026-08-01")
    tick(p2ctx, "2026-10-15 08:45")
    sold = ai_repo.picks_of(p2conn, "paper", RULE_ID, ("sold",))
    assert [(p.instrument_id, p.closed_on) for p in sold] == [(OCEAN, date(2026, 10, 14))]
    events = {e.kind for e in repo.events_of_ledger(p2conn, "paper")}
    assert {"ai-sell", "rebalance", "start"} <= events
    assert sleeves.verify_sleeves(p2conn, "paper") == []
    assert verify_ledger(p2conn, "paper") == []
