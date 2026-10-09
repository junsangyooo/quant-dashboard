"""Phase 2 through the API (PHASE2.md §9): the paper ledger shared 80/20 with '3년 발굴', after
a seed purchase, a shock confirmed twice and its sale (the daily lane end to end)."""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from autotrade.ai.cli import ClaudeCli
from autotrade.ai.runner import run_ai
from autotrade.config import Config
from autotrade.jobs.tasks import JobContext
from autotrade.jobs.tick import run_tick

from ..ai_fakes import ScriptedRunner, sell
from ..fakes import World
from ..helpers import kst
from ..phase2 import flat_world, put_metric, start_paper
from ..test_discovery_plan import seed_prices
from .support import Clock

OCEAN, HANWHA = "KR:042660", "KR:012450"


@pytest.fixture
def api_cfg(tmp_path: Any) -> Config:
    """Phase 2: the default shares (the paper ledger 80/20)."""
    return Config(db_path=tmp_path / "autotrade.db", paper_start_date=date(2026, 7, 1))


def tick(jobs: JobContext, when: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    return run_tick(jobs, "paper", lambda: kst(when), jobs.cfg.db_path.parent, lines.append)


@pytest.fixture
def lived(world: World, jobs: JobContext, db: sqlite3.Connection, clock: Clock) -> None:
    """Built before the owner logs in: the session is opened at the reading time."""
    start_paper(jobs, world)
    for t in ("2026-10-13 08:25", "2026-10-13 09:10", "2026-10-14 08:25", "2026-10-14 16:00"):
        world.rate(kst(t), "1400.0")
    seed_prices(db, world, ["2026-10-12", "2026-10-13"], "10000")
    tick(jobs, "2026-10-13 08:40")
    for t in ("09:05", "09:10", "22:30"):
        tick(jobs, f"2026-10-13 {t}")
    seed_prices(db, world, ["2026-10-14"], "10000")
    world.bar(OCEAN, "2026-10-14", close="9000", open_="9000")
    flat_world(
        db,
        world,
        "2026-10-14",
        start="2026-08-01",
        overrides={"042660.KS": lambda i, d: "90" if d >= date(2026, 10, 13) else "100"},
    )
    put_metric(db, HANWHA, "segment_backlog:지상방산", "2026Q1", "38300000000000", "KRW")
    put_metric(db, HANWHA, "segment_backlog:지상방산", "2026Q2", "33000000000000", "KRW")
    tick(jobs, "2026-10-14 08:30")
    runner = ScriptedRunner()
    runner.add("sell", sell("반증"), sell("반증"))
    at = kst("2026-10-14 08:35")
    cli = ClaudeCli("claude", jobs.cfg.db_path.parent / "ai-cwd", runner=runner, now=lambda: at)
    run_ai(db, replace(jobs.cfg, ai_calls_enabled=True), jobs.sources, cli, lambda: at)
    tick(jobs, "2026-10-14 08:45")
    tick(jobs, "2026-10-14 09:05")
    tick(jobs, "2026-10-14 16:05")  # the snapshot
    clock.now = kst("2026-10-14 16:30")


def test_the_plan_tab_shows_two_cards_and_the_sell_condition_gauge(
    lived: None, logged_in: TestClient
) -> None:
    response = logged_in.get("/api/plan")
    assert response.status_code == 200, response.text
    plan = response.json()
    assert [c["rule"]["id"] for c in plan["rules"]] == ["index_half", "discovery_3y"]
    ai = plan["rules"][1]
    assert ai["rule"] == {"id": "discovery_3y", "name": "3년 발굴", "ai": True, "colorIndex": 1}
    assert ai["share"]["target"] == 20.0
    assert plan["rules"][0]["share"]["target"] == 80.0
    assert [s["rule"]["id"] for s in plan["ruleShares"]] == ["index_half", "discovery_3y"]
    assert round(sum(s["pct"] for s in plan["ruleShares"]), 1) <= 100.0
    # 지상방산 backlog: 38.3조 on the oldest report, 33조 now, the line 30조:
    # (38.3 - 33) / (38.3 - 30) = 64% of the way, 3.0조 left.
    assert ai["gauge"] == {
        "kind": "sell-condition",
        "needle": {
            "instrument": {
                "id": HANWHA,
                "name": "한화에어로스페이스",
                "kind": "stock",
                "market": "KR",
                "currency": "KRW",
                "initials": "한",
            },
            "progress": 64.0,
            "metric": "지상방산 수주잔고",
            "marginText": "3.0조",
        },
    }
    rows = {r["instrument"]["id"]: r for r in ai["rows"]}
    assert OCEAN not in rows  # sold
    assert len(rows) == 14
    assert rows[HANWHA]["progress"] == 64.0
    assert rows[HANWHA]["target"] == 7.1  # 1/14
    assert ai["status"] == "hold"
    assert ai["basisLine"]["metricTableAt"] == "2026-10-12T08:00:00+09:00"
    assert ai["vsIndex"]["points"][-1]["date"] == "2026-10-13"
    kinds = [i["kind"] for i in plan["schedule"]["items"]]
    assert {"monthly-review", "discovery"} <= set(kinds)
    review = next(i for i in plan["schedule"]["items"] if i["kind"] == "monthly-review")
    assert review == {
        "kind": "monthly-review",
        "at": "2026-10-31T22:00:00+09:00",
        "ruleId": "discovery_3y",
    }


def test_home_groups_the_holdings_by_rule(lived: None, logged_in: TestClient) -> None:
    home = logged_in.get("/api/home").json()
    groups = {g["key"]: g for g in home["composition"]["groups"]}
    assert "discovery_3y" in groups
    ai_rows = groups["discovery_3y"]["rows"]
    ids = [r["instrument"]["id"] for r in ai_rows if r["kind"] == "holding"]
    assert HANWHA in ids
    assert "KR:069500" in ids  # the index ETF that holds the rule's idle money
    assert OCEAN not in ids
    total = sum(r["krw"] for g in groups.values() for r in g["rows"])
    assert abs(total - home["total"]) <= 2
    assert round(sum(g["pct"] for g in groups.values()), 1) == 100.0
    assert "rule" in home["composition"]["groupBy"]
    assert home["planCard"]["others"]["count"] == 1


def test_the_rules_tab_draws_four_lanes(lived: None, logged_in: TestClient) -> None:
    rules = logged_in.get("/api/rules").json()["rules"]
    assert [r["rule"]["id"] for r in rules] == ["index_half", "discovery_3y"]
    detail = logged_in.get("/api/rules/discovery_3y").json()
    flow = detail["display"]
    assert flow["kind"] == "flow"
    assert [lane["id"] for lane in flow["lanes"]] == ["daily", "earnings", "monthly", "quarterly"]
    assert flow["lane"] == "daily"
    edges = {(e["from"], e["to"]): e["style"] for e in flow["edges"]}
    assert edges[("start", "data")] == "taken"  # the watch ran on 10/14
    assert edges[("condition", "ai")] == "taken"
    assert edges[("confirm", "action")] == "taken"
    assert edges[("confirm", "result")] == "not-taken"
    assert edges[("action", "exception")] == "exception"
    nodes = {n["id"]: n for n in flow["nodes"]}
    assert nodes["ai"]["now"]["headKey"] == "now-last-judgment"
    assert {"kind": "kv", "key": "votes", "value": "invalidated,invalidated"} in nodes["confirm"][
        "now"
    ]["rows"]
    quarterly = logged_in.get("/api/rules/discovery_3y?lane=quarterly").json()["display"]
    assert quarterly["lane"] == "quarterly"
    assert {
        "from": "condition",
        "to": "result",
        "label": "no-wait",
        "style": "not-taken",
    } in quarterly["edges"]
    assert logged_in.get("/api/rules/nope").status_code == 404


def test_the_day_shows_the_ai_judgment(lived: None, logged_in: TestClient) -> None:
    day = logged_in.get("/api/day/2026-10-14").json()
    kinds = [e["kind"] for e in day["events"]]
    assert "ai-sell" in kinds
    sold = next(e for e in day["events"] if e["kind"] == "ai-sell")
    j = sold["judgment"]
    assert (j["trigger"], j["model"], j["tokens"], j["verdict"], j["votes"], j["action"]) == (
        "shock",
        "sonnet",
        8800,
        "invalidated",
        ["invalidated", "invalidated"],
        "sell",
    )
    assert j["instrument"]["id"] == OCEAN
    assert j["inputSummary"][0] == "한화오션"
    plans = [
        e for e in day["events"] if e["kind"] in ("rebalance", "in-progress", "partial-failed")
    ]
    ai_plan = next(e for e in plans if e["rule"]["id"] == "discovery_3y")
    assert OCEAN in [i["id"] for i in ai_plan["weights"]["instruments"]]
    history = logged_in.get("/api/history").json()
    assert [r["rule"]["id"] for r in history["filters"]["rules"]] == ["index_half", "discovery_3y"]
    assert {"kind": "ai", "count": 1} in history["filters"]["kinds"]


def test_health_lists_filings_ai_cli_and_the_metric_table(
    lived: None, logged_in: TestClient, db: sqlite3.Connection
) -> None:
    health = logged_in.get("/api/health").json()
    sources = {s["id"]: s for s in health["sources"]}
    assert {"filings", "ai-cli", "metric-table"} <= set(sources)
    assert sources["filings"]["state"] == "fresh"
    assert sources["filings"]["extra"] == {"dart": "ok", "edgar": "ok"}
    assert sources["ai-cli"]["state"] == "fresh"
    assert sources["ai-cli"]["basis"] == "sonnet"
    assert sources["ai-cli"]["extra"]["monthTokens"] == 8800
    assert sources["metric-table"]["basis"] == "2026-10-12"
    assert health["summary"]["sourcesTotal"] == 6


def test_the_other_lanes_show_their_last_run(lived: None, logged_in: TestClient) -> None:
    earnings = logged_in.get("/api/rules/discovery_3y?lane=earnings").json()["display"]
    assert [n["now"]["headKey"] for n in earnings["nodes"]] == [
        "now-last",
        "now-last-judgment",
        "now",
        "now",
    ]
    monthly = logged_in.get("/api/rules/discovery_3y?lane=monthly").json()["display"]
    start = next(n for n in monthly["nodes"] if n["id"] == "start")
    assert start["now"] == {
        "headKey": "now-month",
        "rows": [{"kind": "kv", "key": "nextReview", "value": "2026-10-31T22:00:00+09:00"}],
    }
    quarterly = logged_in.get("/api/rules/discovery_3y?lane=quarterly").json()["display"]
    nodes = {n["id"]: n for n in quarterly["nodes"]}
    assert {"kind": "kv", "key": "daysToNext", "value": "47"} in nodes["start"]["now"]["rows"]
    assert len(nodes["stock"]["now"]["rows"]) == 15  # 14 held and the candidates count
    assert logged_in.get("/api/rules/discovery_3y?lane=nope").json()["display"]["lane"] == "daily"


def test_margin_texts() -> None:
    from autotrade.api.views.discovery import margin_text
    from autotrade.domain.conditions import Distance

    def text(
        margin: str | None, unit: str | None, left: int | None = None, kind: str = "quarter"
    ) -> str:
        return margin_text(
            Distance(Decimal(50), None if margin is None else Decimal(margin), unit, left),
            None,
            kind,
        )

    assert text("2.34", "%") == "2.3%p"
    assert text("-3100000000000", "KRW") == "3.1조"
    assert text("45000000000", "KRW") == "450억"
    assert text("1240000000", "USD") == "$1.2B"
    assert text("350000000", "USD") == "$350M"
    assert text("0.123", "x") == "0.12x"
    assert text("3", "count") == "3"
    assert text(None, None, 2) == "2분기"
    assert text(None, None, 1, "month") == "1달"


def test_initials_follow_figma_for_every_name() -> None:
    from autotrade.api.views.refs import initials
    from autotrade.domain.instruments import Currency, Instrument, Kind, Market, kr_etf, us_etf

    def kr(ticker: str, name: str) -> Instrument:
        return Instrument(
            f"KR:{ticker}", Market.KR, Currency.KRW, Kind.STOCK, ticker, name, f"{ticker}.KS"
        )

    nvda = Instrument("US:NVDA", Market.US, Currency.USD, Kind.STOCK, "NVDA", "NVIDIA", "NVDA")
    assert initials(kr_etf("069500", "KOSPI200 ETF")) == "K2"
    assert initials(us_etf("SPYM", "S&P 500 ETF")) == "SP"
    assert initials(kr("005930", "삼성전자")) == "삼"
    assert initials(kr("267260", "HD현대일렉트릭")) == "HD"
    assert initials(kr("326030", "SK바이오팜")) == "SK"
    assert initials(kr("000000", "K리츠")) == "K"
    assert initials(nvda) == "NV"
