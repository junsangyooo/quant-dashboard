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
from autotrade.db import ai_repo, repo
from autotrade.db.connection import transaction
from autotrade.engine import watch as watch_engine
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
    assert ai["basisLine"]["metricTableAt"] == "2026-10-12"  # '지표 표 10/12'
    # '다음 확인 10/15 08:30 · 점검 11/1'
    assert ai["next"] == {
        "kind": "next-check",
        "at": "2026-10-15T08:30:00+09:00",
        "reviewAt": "2026-11-01T08:30:00+09:00",
    }
    assert ai["vsIndex"]["points"][-1]["date"] == "2026-10-13"
    kinds = [i["kind"] for i in plan["schedule"]["items"]]
    assert {"monthly-review", "discovery"} <= set(kinds)
    review = next(i for i in plan["schedule"]["items"] if i["kind"] == "monthly-review")
    assert review == {
        "kind": "monthly-review",
        "at": "2026-11-01T08:30:00+09:00",
        "ruleId": "discovery_3y",
    }
    found = next(i for i in plan["schedule"]["items"] if i["kind"] == "discovery")
    assert found == {
        "kind": "discovery",
        "at": "2026-12-01T08:30:00+09:00",
        "ruleId": "discovery_3y",
    }
    # The index rule sells dollars back to won: the US sale at 22:30, then '달러 → 원'.
    assert plan["schedule"]["now"]["ruleId"] == "index_half"
    [fx] = next(s for s in plan["schedule"]["now"]["stages"] if s["kind"] == "fx")["orders"]
    assert (fx["direction"], fx["at"]) == ("usd-krw", "2026-10-15T09:10:00+09:00")


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
    # The start card's 'at' is the next run.
    assert nodes["start"]["now"] == {
        "headKey": "now",
        "rows": [],
        "at": "2026-10-15T08:30:00+09:00",
    }
    # kv rows hold codes and data only; the third column ('정상', '새 0', '1곳') is a note.
    assert nodes["data"]["now"]["rows"] == [
        {"kind": "kv", "key": "krClose", "value": "2026-10-13", "note": "fresh"},
        {"kind": "kv", "key": "usClose", "value": "2026-10-13", "note": "fresh"},
        {"kind": "kv", "key": "filings", "value": "-", "note": "0"},
        {"kind": "kv", "key": "metricTable", "value": "2026-10-12", "note": "1"},
    ]
    assert nodes["condition"]["now"]["rows"][-1] == {"kind": "kv", "key": "hits", "value": "1"}
    assert nodes["ai"]["now"]["rows"][-1] == {
        "kind": "kv",
        "key": "verdict",
        "value": "invalidated",
        "note": "shock",
    }
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
    ai_events = [
        e
        for m in history["months"]
        for e in m["events"]
        if e.get("rule", {}).get("id") == "discovery_3y" and "weightsMini" in e
    ]
    assert ai_events
    assert all(e["weightsMini"]["target"] == [] for e in ai_events)  # no target tick
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
    assert [n["now"]["headKey"] for n in earnings["nodes"]] == ["now", "now-last", "now", "now"]
    data = next(n for n in earnings["nodes"] if n["id"] == "data")
    assert data["now"]["rows"][-1] == {"kind": "kv", "key": "companies", "value": "1"}
    monthly = logged_in.get("/api/rules/discovery_3y?lane=monthly").json()["display"]
    start = next(n for n in monthly["nodes"] if n["id"] == "start")
    # The start card's 'at' is the next run: the review is done by the 1st's 08:30 check.
    assert start["now"] == {"headKey": "now", "rows": [], "at": "2026-11-01T08:30:00+09:00"}
    quarterly = logged_in.get("/api/rules/discovery_3y?lane=quarterly").json()["display"]
    nodes = {n["id"]: n for n in quarterly["nodes"]}
    assert nodes["start"]["now"] == {
        "headKey": "now",
        "rows": [{"kind": "kv", "key": "daysToNext", "value": "48"}],
        "at": "2026-12-01T08:30:00+09:00",
    }
    # The stock card lists three and says '외 11'; '후보 대기 · 0' is a kv row, not a status.
    stock = nodes["stock"]
    assert stock["more"] == 11
    # Equal weights: no per-instrument targets, the target each is a kv row.
    weight = nodes["weight"]
    assert (weight["more"], "targets" in weight) == (11, False)
    assert weight["now"]["rows"][-1] == {"kind": "kv", "key": "targetEach", "value": "7.1"}
    assert [r["kind"] for r in stock["now"]["rows"]] == ["instrument"] * 3 + ["kv"]
    assert stock["now"]["rows"][-1] == {"kind": "kv", "key": "candidates", "value": "0"}
    assert nodes["result"]["now"]["rows"] == [{"kind": "kv", "key": "candidates", "value": "0"}]
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


def test_before_the_first_check_the_ai_rule_waits_too(logged_in: TestClient) -> None:
    home = logged_in.get("/api/home").json()  # 7/1 16:10, no check has run in this world
    card = home["planCard"]
    assert card["gauge"] == {"kind": "drift", "threshold": 2.0, "needle": None}
    assert card["share"] == {"pct": 0.0, "target": 80.0}
    assert card["others"] == {"count": 1, "status": "before-first"}  # '외 1개 규칙 · 첫 확인 전'
    ai = logged_in.get("/api/plan").json()["rules"][1]
    assert (ai["status"], ai["next"]) == (
        "scheduled",
        {"kind": "first-check", "at": "2026-07-02T08:30:00+09:00"},
    )


def test_a_yellow_card_alone_keeps_the_summary_ok(
    lived: None, logged_in: TestClient, app: Any, db: sqlite3.Connection
) -> None:
    state = app.state.autotrade
    app.state.autotrade = replace(state, cfg=replace(state.cfg, ai_monthly_budget=5000))
    health = logged_in.get("/api/health").json()
    budget = next(t for t in health["todos"] if t["kind"] == "ai-cli")
    assert (budget["severity"], budget["facts"]) == (
        "yellow",
        {"reason": "over-budget", "tokens": 8800, "budget": 5000},
    )
    assert health["summary"]["todoCount"] == 1  # the cards the owner has to act on himself
    assert health["summary"]["kind"] == "ok"  # a yellow card alone: '정상 · 할 일 1'
    with transaction(db):
        ai_repo.set_source_state(db, "dart", "maintenance", "DART 800", kst("2026-10-14 16:20"))
    health = logged_in.get("/api/health").json()
    outage = next(t for t in health["todos"] if t["kind"] == "filings")
    assert outage["severity"] == "red"
    assert {k: outage["facts"][k] for k in ("source", "market", "state")} == {
        "source": "dart",
        "market": "KR",  # '한국 공시 수집 점검 중'
        "state": "maintenance",
    }
    assert outage["facts"]["since"] < "2026-10-14T16:20:00+09:00"  # the last success
    assert health["summary"]["kind"] == "check"
    assert health["summary"]["todoCount"] == 1  # the engine retries the outage: not '할 일'
    # EDGAR never answered and two tasks failed three times: the owner is asked.
    with transaction(db):
        ai_repo.set_source_state(db, "edgar", "failed", "EDGAR 503", kst("2026-10-14 16:20"))
        db.execute("UPDATE source_states SET ok_at = NULL WHERE source_id = 'edgar'")
        for i, made in enumerate(("2026-10-13 06:00", "2026-10-14 06:00")):
            task_id, _ = ai_repo.enqueue_task(
                db,
                kind="extract",
                ledger_id="paper",
                rule_id="discovery_3y",
                trigger="filing",
                dedup_key=f"stuck:{i}",
                at=kst(made),
            )
            for _ in range(3):
                ai_repo.start_task(db, task_id, kst("2026-10-14 06:10"))
            ai_repo.finish_task(db, task_id, kst("2026-10-14 06:11"), status="failed", error="x")
    health = logged_in.get("/api/health").json()
    edgar = next(t for t in health["todos"] if t["id"] == "filings:edgar")
    assert edgar["facts"] == {"source": "edgar", "market": "US", "state": "failed"}  # no since
    assert health["summary"]["todoCount"] == 2  # the stuck tasks wait for the owner
    stuck = next(t for t in health["todos"] if t["id"].startswith("ai-cli:failed"))
    assert (stuck["severity"], stuck["facts"]) == (
        "red",
        {
            "reason": "task-failed",
            "count": 2,
            "taskKind": "extract",
            "since": "2026-10-13T06:00:00+09:00",  # 'AI 호출 실패 · 10/13 06:00부터'
        },
    )


def test_candidates_near_their_buy_price(
    lived: None, logged_in: TestClient, db: sqlite3.Connection
) -> None:
    from autotrade.domain.instruments import Currency, Instrument, Kind, Market

    nvda = Instrument("US:NVDA", Market.US, Currency.USD, Kind.STOCK, "NVDA", "NVIDIA", "NVDA")
    at = kst("2026-10-14 16:20")
    with transaction(db):
        repo.upsert_instrument(db, nvda, at)
        pick_id = ai_repo.insert_pick(
            db,
            ai_repo.NewPick(
                ledger_id="paper",
                rule_id="discovery_3y",
                instrument_id="US:NVDA",
                status="candidate",
                picked_on=date(2026, 10, 1),
                picked_price=Decimal(100),
                benchmark="SPY",
                benchmark_price=Decimal(100),
                theme="AI 연산",
                rationale="r",
                confirm=[],
                invalidate=[
                    {"type": "level", "metric": "op_margin", "op": "<", "value": 50, "unit": "%"}
                ],
                buy=[{"type": "price", "op": "<=", "value": 95}],
                confidence=None,
                source="test",
            ),
            at,
        )
        pick = ai_repo.get_pick(db, pick_id)
        gap = watch_engine.buy_gap(pick, Decimal(97))
        # 100 at the pick, 97 now, the line 95: 60% of the way, 2.1% still to fall.
        assert gap == {"price": "97", "line": "95", "progress": "60", "gap_pct": "2.1"}
        ai_repo.insert_job_run(
            db,
            job="watch",
            ledger_id="paper",
            run_date=date(2026, 10, 14),
            started_at=at,
            ended_at=at,
            result="ok",
            error=None,
            details={"buy_gaps": {str(pick_id): gap}},
        )
    flow = logged_in.get("/api/rules/discovery_3y?lane=quarterly").json()["display"]
    condition = next(n for n in flow["nodes"] if n["id"] == "condition")
    assert condition["now"]["rows"] == [
        {
            "kind": "instrument",
            "instrument": {
                "id": "US:NVDA",
                "name": "NVIDIA",
                "kind": "stock",
                "market": "US",
                "currency": "USD",
                "initials": "NV",
            },
            "progress": 60.0,
            "marginText": "2.1%",
        }
    ]
    result = next(n for n in flow["nodes"] if n["id"] == "result")
    assert result["now"]["rows"] == [{"kind": "kv", "key": "candidates", "value": "1"}]


def test_the_last_plan_spans_its_days(
    lived: None, logged_in: TestClient, db: sqlite3.Connection
) -> None:
    """'마지막 10/14~10/15': a plan whose last fill came a day later shows its span."""
    plan = [p for p in repo.plans_of_ledger(db, "paper") if p.rule_id == "discovery_3y"][-1]
    last_fill = repo.fills_of_plan(db, plan.plan_id)[-1]
    with transaction(db):
        db.execute(
            "UPDATE fills SET filled_at = ? WHERE fill_id = ?",
            ("2026-10-15T00:30:00+00:00", last_fill.fill_id),
        )
    flow = logged_in.get("/api/rules/discovery_3y").json()["display"]
    action = next(n for n in flow["nodes"] if n["id"] == "action")["now"]
    assert (action["headKey"], action["at"], action["until"]) == (
        "now-last",
        "2026-10-14",
        "2026-10-15",
    )
    sides = [r["side"] for r in action["rows"]]
    assert sides[0] == "sell"  # sells come first
    assert all(r["kind"] == "order" for r in action["rows"])
    assert action["rows"][0]["text"] == "한화오션"  # a trade's text is its instrument's name


def test_a_retried_order_row_shows_the_retry(
    lived: None, logged_in: TestClient, db: sqlite3.Connection
) -> None:
    """'10/14 다시 · 체결': the sale failed at 09:05 and filled on the retry."""
    from autotrade.domain.instruments import Currency

    plan = [p for p in repo.plans_of_ledger(db, "paper") if p.rule_id == "discovery_3y"][-1]
    sold = next(o for o in repo.orders_of_plan(db, plan.plan_id) if o.side == "sell")
    with transaction(db):
        db.execute("UPDATE orders SET attempt = 2 WHERE order_id = ?", (sold.order_id,))
        first, _ = repo.insert_order(
            db,
            repo.NewOrder(
                idem_key="paper:retried-sale",
                ledger_id="paper",
                plan_id=plan.plan_id,
                stage_id=sold.stage_id,
                stage="sell",
                market="KR",
                instrument_id=OCEAN,
                side="sell",
                fx_direction=None,
                currency=Currency.KRW,
                qty=sold.qty,
                est_price=sold.est_price,
                est_amount=sold.est_amount,
                est_fee=sold.est_fee,
                est_rate=None,
                est_received=None,
            ),
            kst("2026-10-14 08:45"),
        )
        repo.mark_order_failed(
            db,
            first,
            reason="no-quote",
            detail="no KR quote",
            executor="paper",
            executed_at=kst("2026-10-14 09:05"),
            retry_at=kst("2026-10-14 09:35"),
            manual=False,
        )
    flow = logged_in.get("/api/rules/discovery_3y").json()["display"]
    action = next(n for n in flow["nodes"] if n["id"] == "action")["now"]
    sale = action["rows"][0]
    assert (sale["text"], sale["status"], sale["retried"]) == ("한화오션", "filled", True)
    assert sale["at"] == "2026-10-14T09:05:00+09:00"  # when the retry filled
    # The day screen keeps the failed day and adds the retry's outcome.
    day = logged_in.get("/api/day/2026-10-14").json()
    ai_plan = next(
        e
        for e in day["events"]
        if e.get("rule", {}).get("id") == "discovery_3y" and e.get("stages")
    )
    order = next(o for st in ai_plan["stages"] for o in st["orders"] if o["side"] == "sell")
    assert (order["status"], order["failure"]["reason"]) == ("failed", "no-quote")
    assert order["retried"] == {"at": "2026-10-14T09:05:00+09:00", "status": "filled"}


def test_the_monthly_and_quarterly_lanes_after_their_runs(
    lived: None, logged_in: TestClient, db: sqlite3.Connection
) -> None:
    """A review and a discovery ran on 10/14 06:00: their cards show what they found."""
    held = ai_repo.picks_of(db, "paper", "discovery_3y", ("held",))
    at = kst("2026-10-14 06:00")
    judgment: dict[str, Any] = {
        "task_id": None,
        "kind": "discovery",
        "trigger": "discovery",
        "instrument_id": None,
        "model": "opus",
        "verdict": "buy",
        "action": "buy",
        "input_summary": [],
        "output_summary": [],
        "call_ids": [],
    }
    with transaction(db):
        for pick in held[:4]:  # the discovery's four new companies
            db.execute(
                "UPDATE picks SET source = 'discovery:2026-10' WHERE pick_id = ?", (pick.pick_id,)
            )
        repo.insert_event(
            db,
            ledger_id="paper",
            kind="discovery",
            event_date=at.date(),
            occurred_at=at,
            rule_id="discovery_3y",
            status="done",
            payload={**judgment, "tokens": 12000},
            ref="discovery:2026-10",
        )
        repo.insert_event(
            db,
            ledger_id="paper",
            kind="monthly-review",
            event_date=at.date(),
            occurred_at=at,
            rule_id="discovery_3y",
            status="done",
            payload={
                **judgment,
                "kind": "monthly-review",
                "trigger": "monthly",
                "verdict": "invalidated",
                "action": "none",
                "tokens": 9000,
                "counts": {"hold": 12, "weaken": 1, "invalidated": 1},
            },
            ref="monthly-review:2026-10",
        )
    quarterly = logged_in.get("/api/rules/discovery_3y?lane=quarterly").json()["display"]
    ai = next(n for n in quarterly["nodes"] if n["type"] == "ai")
    assert ai["more"] == 1  # four new companies, three listed: '외 1'
    assert ai["now"]["headKey"] == "now-last-judgment"
    assert ai["now"]["at"] == "2026-10-14"
    assert [r["kind"] for r in ai["now"]["rows"]] == ["instrument"] * 3 + ["kv", "kv"]
    assert ai["now"]["rows"][-2:] == [
        {"kind": "kv", "key": "candidates", "value": "0"},
        {"kind": "kv", "key": "tokens", "value": "12000"},
    ]
    taken = {(e["from"], e["to"]) for e in quarterly["edges"] if e["style"] == "taken"}
    assert {("start", "data"), ("data", "ai"), ("ai", "stock")} <= taken
    data = next(n for n in quarterly["nodes"] if n["id"] == "data")
    assert data["now"]["rows"] == [{"kind": "kv", "key": "lastDiscovery", "value": "2026-10-14"}]
    monthly = logged_in.get("/api/rules/discovery_3y?lane=monthly").json()["display"]
    nodes = {n["id"]: n for n in monthly["nodes"]}
    review = next(n for n in monthly["nodes"] if n["type"] == "ai")["now"]
    assert (review["headKey"], review["at"]) == ("now-last-judgment", "2026-10-14")
    assert review["rows"] == [
        {"kind": "kv", "key": "hold", "value": "12"},
        {"kind": "kv", "key": "weaken", "value": "1"},
        {"kind": "kv", "key": "invalidated", "value": "1"},
        {"kind": "kv", "key": "tokens", "value": "9000"},
    ]
    assert nodes["data"]["now"]["rows"][0] == {"kind": "kv", "key": "picks", "value": "14"}
    result = next(n for n in monthly["nodes"] if n["type"] == "result")["now"]
    assert result == {
        "headKey": "now",
        "rows": [{"kind": "status", "status": "hold"}],
        "at": "2026-10-14",
    }


def test_the_earnings_lane_after_a_report_was_read(
    lived: None, logged_in: TestClient, db: sqlite3.Connection
) -> None:
    """한화에어로스페이스's Q3 report (10/14) was read: two metric values from one call."""
    at = kst("2026-10-14 18:00")
    with transaction(db):
        filing_id, _ = ai_repo.insert_filing(
            db,
            instrument_id=HANWHA,
            source="dart",
            source_ref="20261014000123",
            form="분기보고서",
            items=None,
            title="분기보고서 (2026.09)",
            filed_on=date(2026, 10, 14),
            url=None,
            kind="earnings",
            status="new",
            at=at,
        )
        call_id = ai_repo.insert_call(
            db,
            task_id=None,
            purpose="extract",
            caller="test",
            model="haiku",
            effort=None,
            web=False,
            prompt="extract",
            input_text="",
            output={"metrics": []},
            usage=None,
            tokens=3100,
            cost_usd=None,
            duration_ms=900,
            exit_code=0,
            error=None,
            started_at=at,
            finished_at=at,
        )
        for metric, value in (("segment_backlog:지상방산", "31000000000000"), ("op_margin", "9.1")):
            ai_repo.upsert_metric_value(
                db,
                instrument_id=HANWHA,
                metric=metric,
                period="2026Q3",
                value=Decimal(value),
                unit="KRW" if metric.startswith("segment") else "%",
                filing_id=filing_id,
                quote=None,
                source="extract",
                call_id=call_id,
                at=at,
            )
    flow = logged_in.get("/api/rules/discovery_3y?lane=earnings").json()["display"]
    nodes = {n["id"]: n for n in flow["nodes"]}
    hanwha = {
        "id": HANWHA,
        "name": "한화에어로스페이스",
        "kind": "stock",
        "market": "KR",
        "currency": "KRW",
        "initials": "한",
    }
    # The start card is the last report: its company and filing day.
    assert nodes["start"]["now"] == {
        "headKey": "now",
        "rows": [{"kind": "instrument", "instrument": hanwha}],
        "at": "2026-10-14",
    }
    ai = next(n for n in flow["nodes"] if n["type"] == "ai")["now"]
    assert ai == {
        "headKey": "now-last",
        "rows": [
            {"kind": "instrument", "instrument": hanwha, "marginText": "2026Q3"},
            {"kind": "kv", "key": "metrics", "value": "2"},
            {"kind": "kv", "key": "tokens", "value": "3100"},
        ],
        "at": "2026-10-14",
    }
    data = nodes["data"]["now"]
    assert data["rows"][0] == {"kind": "instrument", "instrument": hanwha, "marginText": "2026Q3"}
    assert data["rows"][-1] == {"kind": "kv", "key": "companies", "value": "1"}
