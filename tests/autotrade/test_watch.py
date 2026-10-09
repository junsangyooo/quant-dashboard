"""Phase 2, step 2: the daily code checks of '3년 발굴' (filings, sell and buy conditions,
price shocks with the T28 numbers, the 'vs index' line, scoring) and when they run."""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal

import pytest

from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.db.connection import transaction
from autotrade.domain.conditions import Observation, buy_met, check_buy, parse_condition
from autotrade.domain.instruments import Currency, Instrument, Kind, Market
from autotrade.domain.watch import (
    classify_kr,
    classify_us,
    excess_path,
    find_shocks,
    window_return,
)
from autotrade.engine import metric_table, reviews, scoring
from autotrade.engine import watch as watch_engine
from autotrade.jobs.ai_tasks import queue_job, watch_job
from autotrade.jobs.schedule import queue_due, watch_due
from autotrade.jobs.tasks import JobContext
from autotrade.jobs.tick import run_tick
from autotrade.market.calendar import NYSE
from autotrade.market.filings import SourceMaintenanceError, SourceUnreachableError
from autotrade.rules.discovery import RULE_ID

from .fakes import World
from .helpers import kst
from .phase2 import flat_world, pick_of, put_metric

D = Decimal
HANWHA_OCEAN = "KR:042660"


# ── filing kinds (T28) ───────────────────────────────────────────────────────────────────────


def test_korean_filings_are_sorted_by_name() -> None:
    assert classify_kr("임원ㆍ주요주주특정증권등소유상황보고서") == "skipped"
    assert classify_kr("주식등의대량보유상황보고서(일반)") == "skipped"
    assert classify_kr("[기재정정]투자설명서") == "skipped"
    assert classify_kr("기업설명회(IR)개최(안내공시)") == "skipped"
    assert classify_kr("반기보고서 (2026.06)") == "earnings"
    assert classify_kr("연결재무제표기준영업(잠정)실적(공정공시)") == "earnings"
    assert classify_kr("매출액또는손익구조30%(대규모법인은15%)이상변동") == "earnings"
    assert classify_kr("단일판매ㆍ공급계약체결") == "other"
    assert classify_kr("유상증자결정") == "other"


def test_us_filings_are_sorted_by_form_and_item() -> None:
    assert classify_us("8-K", "2.02,9.01") == "earnings"
    assert classify_us("8-K", "5.07") == "skipped"  # the vote of the annual meeting
    assert classify_us("8-K", "5.07,9.01") == "skipped"
    assert classify_us("8-K", "5.03,5.07,9.01") == "other"  # more than the vote
    assert classify_us("8-K", "5.02,9.01") == "other"
    assert classify_us("8-K/A", "1.01") == "other"
    assert classify_us("8-K", None) == "other"
    assert classify_us("6-K", None) == "earnings"  # TSMC: monthly revenue and results
    assert classify_us("10-Q", None) == "skipped"
    assert classify_us("4", None) == "skipped"


# ── shocks (T28 numbers) ─────────────────────────────────────────────────────────────────────


def days(n: int, start: date = date(2026, 1, 5)) -> list[date]:
    out: list[date] = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def path(values: list[str], when: list[date]) -> list[tuple[date, Decimal]]:
    return [(d, D(v)) for d, v in zip(when, values, strict=True)]


def shocks(
    stock: list[tuple[date, Decimal]], index: list[tuple[date, Decimal]], **kw: object
) -> list[str]:
    args: dict[str, object] = {
        "day_line": D("-0.08"),
        "line_20d": D("-0.20"),
        "window": 20,
        "after": None,
        "blocked_until": None,
    }
    args.update(kw)
    return [f"{s.on}:{s.kind}" for s in find_shocks(stock, index, **args)]  # type: ignore[arg-type]


def test_a_day_at_minus_8_percent_against_the_index_is_a_shock() -> None:
    when = days(5)
    index = path(["100", "100", "100", "100", "101"], when)
    assert shocks(path(["100", "100", "92", "92", "92"], when), index) == [f"{when[2]}:day"]
    assert shocks(path(["100", "100", "92.1", "92.1", "92.1"], when), index) == []  # -7.9%
    # The index fell too: 9% down against 1% down is 8% under the index.
    index2 = path(["100", "100", "99", "99", "99"], when)
    assert shocks(path(["100", "100", "91", "91", "91"], when), index2) == [f"{when[2]}:day"]
    # A stock that only follows the index down is no shock.
    assert (
        shocks(
            path(["100", "100", "90", "90", "90"], when),
            path(["100", "100", "90", "90", "90"], when),
        )
        == []
    )


def test_twenty_sessions_at_minus_20_percent_against_the_index_is_a_shock() -> None:
    when = days(22)
    # The index loses 10% and the stock 28% over 20 sessions, never 8% in a day:
    # 0.72 / 0.90 - 1 = -20%.
    index = path([str(100 - Decimal(i) * D("0.5")) for i in range(21)] + ["90"], when)
    stock = path([str(100 - Decimal(i) * D("1.4")) for i in range(21)] + ["72"], when)
    assert shocks(stock, index) == [f"{when[20]}:20d"]
    softer = path([str(100 - Decimal(i) * D("1.3")) for i in range(21)] + ["74"], when)
    assert shocks(softer, index) == []


def test_a_shock_is_not_counted_again_for_20_sessions() -> None:
    when = days(45)
    index = path(["100"] * 45, when)
    # Drops of 10% on sessions 5, 15 and 25: the second falls in the first one's 20 sessions.
    values, price = [], D(100)
    for i in range(45):
        if i in (5, 15, 25):
            price = price * D("0.9")
        values.append(str(price))
    stock = path(values, when)
    assert shocks(stock, index) == [f"{when[5]}:day", f"{when[25]}:day"]
    assert shocks(stock, index, after=when[5]) == [f"{when[15]}:day"]  # the next scan
    assert shocks(stock, index, blocked_until=when[24]) == [f"{when[25]}:day"]


def test_window_returns_and_excess_paths() -> None:
    when = days(4)
    stock = path(["100", "110", "120", "90"], when)
    index = path(["200", "200", "220", "200"], when)
    w = window_return(stock, index, when[0], when[2])
    assert w is not None
    assert (w.value, w.index, w.last) == (D("0.2"), D("0.1"), when[2])
    assert window_return(stock, index, when[3]) is None  # one session only
    assert excess_path(stock, index, when[1]) == [
        (when[1], D(0)),
        (when[2], D("120") / D("110") - 1 - (D("220") / D("200") - 1)),
        (when[3], D("90") / D("110") - 1),
    ]
    assert excess_path(stock, index, when[3] + timedelta(days=1)) == []


def test_buy_conditions_must_all_hold() -> None:
    price = parse_condition({"type": "price", "op": "<=", "value": 95})
    per = parse_condition({"type": "valuation", "metric": "per_fwd", "op": "<=", "value": 20})
    event = parse_condition({"type": "event", "kind": "guidance_raise", "text": "가이던스 상향"})
    margin = parse_condition(
        {"type": "level", "metric": "op_margin", "op": ">=", "value": 20, "unit": "%"}
    )
    ratios = {"per_fwd": D(18)}
    checks = [check_buy(c, D(94), ratios) for c in (price, per, event)]
    assert [c.verdict for c in checks] == ["hit", "hit", "skip"]
    assert buy_met(checks)
    assert not buy_met([check_buy(price, D(96), ratios), checks[1]])
    assert check_buy(price, None, ratios).verdict == "unknown"
    assert check_buy(per, D(94), {}).verdict == "unknown"
    assert not buy_met([check_buy(event, D(94), ratios)])  # nothing the code can check
    obs = [Observation("2026Q2", D(25), "%")]
    assert check_buy(margin, None, {}, obs).verdict == "hit"


# ── the daily watch ──────────────────────────────────────────────────────────────────────────


def ocean_falls(i: int, d: date) -> str:
    return "90" if d >= date(2026, 10, 12) else "100"


def first_watch_world(conn: sqlite3.Connection, world: World) -> None:
    flat_world(conn, world, "2026-10-13", overrides={"042660.KS": ocean_falls})
    world.filing("KR:012450", "dart", "20260814000001", "반기보고서 (2026.06)", "2026-08-14")
    world.filing(
        "KR:012450",
        "dart",
        "20261008000002",
        "임원ㆍ주요주주특정증권등소유상황보고서",
        "2026-10-08",
    )
    world.filing("KR:012450", "dart", "20261012000003", "단일판매ㆍ공급계약체결", "2026-10-12")
    world.filing(
        "US:AVGO", "edgar", "0001730168-26-000100", "8-K", "2026-09-04", "8-K", "2.02,9.01"
    )
    world.filing("US:AVGO", "edgar", "0001730168-26-000101", "8-K", "2026-10-08", "8-K", "5.07")
    world.filing(
        "US:AVGO", "edgar", "0001730168-26-000102", "8-K", "2026-10-09", "8-K", "8.01,9.01"
    )
    world.filing("US:TSM", "edgar", "0001046179-26-000200", "6-K", "2026-10-10", "6-K")


def test_the_first_watch(p2ctx: JobContext, p2conn: sqlite3.Connection, world: World) -> None:
    first_watch_world(p2conn, world)
    report = watch_job(p2ctx, "paper", kst("2026-10-13 08:40"))
    assert report["result"] == "ok"
    made = {(t["kind"], t["pick"]) for t in report["tasks"]}
    assert made == {
        ("extract", "KR:012450"),  # backfill: the half-year report read before the pick
        ("screen", "KR:012450"),  # the supply contract
        ("extract", "US:AVGO"),  # backfill: the 2.02 press release
        ("screen", "US:AVGO"),  # 8.01
        ("extract", "US:TSM"),  # the 6-K after the pick
        ("sell-confirm", HANWHA_OCEAN),  # 10% under the index on 10/12
    }
    backfill = [t for t in ai_repo.tasks_of(p2conn, kind="extract") if t.trigger == "backfill"]
    assert len(backfill) == 2
    statuses = {f.source_ref: (f.kind, f.status) for f in ai_repo.latest_filings(p2conn, 50)}
    assert statuses == {
        "20260814000001": ("earnings", "queued"),
        "20261008000002": ("skipped", "skipped"),
        "20261012000003": ("other", "queued"),
        "0001730168-26-000100": ("earnings", "queued"),
        "0001730168-26-000101": ("skipped", "skipped"),
        "0001730168-26-000102": ("other", "queued"),
        "0001046179-26-000200": ("earnings", "queued"),
    }
    confirm = ai_repo.tasks_of(p2conn, kind="sell-confirm")[0]
    assert confirm.trigger == "shock"
    shock = confirm.detail["triggers"][0]
    assert (shock["kind"], shock["on"], shock["shock"], shock["day_rel"]) == (
        "shock",
        "2026-10-12",
        "day",
        "-0.1000",
    )
    ocean = pick_of(p2conn, HANWHA_OCEAN)
    assert ocean.shock_until is not None
    assert ocean.shock_until > date(2026, 11, 3)
    dart, edgar = ai_repo.source_state(p2conn, "dart"), ai_repo.source_state(p2conn, "edgar")
    assert dart is not None
    assert edgar is not None
    assert (dart.state, dart.detail, edgar.state) == ("ok", "8 companies", "ok")
    # 10/13 has not closed at 08:40 KST: the last sessions looked at are 10/12 in both markets.
    assert report["checked_through"] == {"KR": "2026-10-12", "US": "2026-10-12"}
    # The mean excess of the 15 picks: one of them is 10% under its index.
    line = ai_repo.rule_daily(p2conn, "paper", RULE_ID)
    assert line[0] == (date(2026, 10, 6), D("0.00"))
    assert line[-1] == (date(2026, 10, 12), D("-0.67"))
    assert report["vs_index"] == "-0.67"

    # The next day: nothing new is asked (dedup, and the shock is in its 20 sessions).
    flat_world(p2conn, world, "2026-10-14", overrides={"042660.KS": ocean_falls})
    again = watch_job(p2ctx, "paper", kst("2026-10-14 08:40"))
    assert (again["result"], again["tasks"], again["filings"]) == (
        "ok",
        [],
        {"new": 0, "queued": 0},
    )
    assert again["checked_through"] == {"KR": "2026-10-13", "US": "2026-10-13"}
    seen = repo.get_setting(p2conn, watch_engine.FILINGS_SEEN.format("KR:012450"))
    assert seen == "2026-10-14"
    assert "filings:dart:KR:012450:2026-10-06:2026-10-14" in world.calls  # a week of overlap


def test_sell_conditions_ask_once_per_data_point(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    flat_world(p2conn, world, "2026-10-14")
    # 한화오션 sells below a 7% operating margin: 150 / 3,000 = 5% in 2Q.
    put_metric(p2conn, HANWHA_OCEAN, "revenue", "2026Q2", "3000000000000", "KRW")
    put_metric(p2conn, HANWHA_OCEAN, "operating_income", "2026Q2", "150000000000", "KRW")
    assert metric_table.observations(p2conn, HANWHA_OCEAN, "op_margin") == [
        Observation("2026Q2", D("5.00"), "%")
    ]
    first = watch_job(p2ctx, "paper", kst("2026-10-13 08:40"))
    assert [(t["kind"], t["pick"]) for t in first["tasks"]] == [("sell-confirm", HANWHA_OCEAN)]
    task = ai_repo.tasks_of(p2conn, kind="sell-confirm")[0]
    trigger = task.detail["triggers"][0]
    assert (task.trigger, trigger["kind"], trigger["period"], trigger["value"]) == (
        "condition",
        "condition",
        "2026Q2",
        "5.00",
    )
    # Still pending the next day: no second task.
    assert watch_job(p2ctx, "paper", kst("2026-10-14 08:40"))["tasks"] == []
    with transaction(p2conn):
        ai_repo.finish_task(p2conn, task.task_id, kst("2026-10-14 09:00"), status="done")
    flat_world(p2conn, world, "2026-10-15")
    assert watch_job(p2ctx, "paper", kst("2026-10-15 08:40"))["tasks"] == []  # same 2Q value
    put_metric(p2conn, HANWHA_OCEAN, "revenue", "2026Q3", "3000000000000", "KRW")
    put_metric(p2conn, HANWHA_OCEAN, "operating_income", "2026Q3", "180000000000", "KRW")
    flat_world(p2conn, world, "2026-10-16")
    third = watch_job(p2ctx, "paper", kst("2026-10-16 08:40"))
    assert [(t["kind"], t["pick"]) for t in third["tasks"]] == [("sell-confirm", HANWHA_OCEAN)]
    # A decided pick waits for its plan and is not checked.
    with transaction(p2conn):
        ai_repo.update_pick(
            p2conn, pick_of(p2conn, HANWHA_OCEAN).pick_id, kst("2026-10-16 09:00"), decision="sell"
        )
        for t in ai_repo.tasks_of(p2conn, kind="sell-confirm"):
            ai_repo.finish_task(p2conn, t.task_id, kst("2026-10-16 09:00"), status="done")
    put_metric(p2conn, HANWHA_OCEAN, "revenue", "2026Q4", "3000000000000", "KRW")
    put_metric(p2conn, HANWHA_OCEAN, "operating_income", "2026Q4", "90000000000", "KRW")
    flat_world(p2conn, world, "2026-10-19")
    assert watch_job(p2ctx, "paper", kst("2026-10-19 08:40"))["tasks"] == []


def nvda() -> Instrument:
    return Instrument("US:NVDA", Market.US, Currency.USD, Kind.STOCK, "NVDA", "NVIDIA", "NVDA")


def add_candidate(conn: sqlite3.Connection, buy: list[dict[str, object]]) -> int:
    at = kst("2026-10-01 09:00")
    with transaction(conn):
        repo.upsert_instrument(conn, nvda(), at)
        return ai_repo.insert_pick(
            conn,
            ai_repo.NewPick(
                ledger_id="paper",
                rule_id=RULE_ID,
                instrument_id="US:NVDA",
                status="candidate",
                picked_on=date(2026, 10, 1),
                picked_price=D("100"),
                benchmark="SPY",
                benchmark_price=D("100"),
                theme="AI 연산",
                rationale="흐름은 맞지만 비싸다",
                confirm=[],
                invalidate=[],
                buy=buy,
                confidence="중",
                source="test",
            ),
            at,
        )


def test_a_candidate_at_its_buy_price_asks_once_a_month(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    buy: list[dict[str, object]] = [
        {"type": "price", "op": "<=", "value": 95},
        {"type": "valuation", "metric": "per_fwd", "op": "<=", "value": 20},
    ]
    pick_id = add_candidate(p2conn, buy)
    flat_world(p2conn, world, "2026-10-14", overrides={"NVDA": lambda i, d: "94"})
    world.valuations["NVDA"] = {"per_fwd": D(25)}
    assert watch_job(p2ctx, "paper", kst("2026-10-13 08:40"))["tasks"] == []  # PER 25 > 20
    world.valuations["NVDA"] = {"per_fwd": D(18)}
    second = watch_job(p2ctx, "paper", kst("2026-10-14 08:40"))
    assert [(t["kind"], t["pick"]) for t in second["tasks"]] == [("buy-confirm", "US:NVDA")]
    task = ai_repo.tasks_of(p2conn, kind="buy-confirm")[0]
    assert (task.trigger, task.pick_id, task.detail["close"]) == (
        "buy-price",
        pick_id,
        {"date": "2026-10-13", "price": "94"},
    )
    flat_world(p2conn, world, "2026-10-15", overrides={"NVDA": lambda i, d: "94"})
    assert watch_job(p2ctx, "paper", kst("2026-10-15 08:40"))["tasks"] == []  # once this month
    with transaction(p2conn):  # the review rewrote the conditions: a new question
        ai_repo.update_pick(
            p2conn,
            pick_id,
            kst("2026-10-15 09:00"),
            buy=[{"type": "price", "op": "<=", "value": 96}],
        )
    flat_world(p2conn, world, "2026-10-16", overrides={"NVDA": lambda i, d: "94"})
    assert len(watch_job(p2ctx, "paper", kst("2026-10-16 08:40"))["tasks"]) == 1
    assert "valuation:NVDA" in world.calls


def test_a_source_down_is_recorded_and_looked_at_again(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    first_watch_world(p2conn, world)
    world.filing_errors["dart"] = SourceMaintenanceError(
        "DART 800: 시스템 점검으로 인한 서비스 중지"
    )
    world.fail_adjusted.add("TSM")
    report = watch_job(p2ctx, "paper", kst("2026-10-13 08:40"))
    assert report["result"] == "partial"
    dart = ai_repo.source_state(p2conn, "dart")
    assert dart is not None
    assert (dart.state, dart.ok_at) == ("maintenance", None)
    assert "filings:KR:012450" in report["errors"]
    assert "adjusted:TSM" in report["errors"]
    asked = [c for c in world.calls if c.startswith("filings:dart")]
    assert len(asked) == 1  # one refusal stops DART for this run
    assert not [f for f in ai_repo.latest_filings(p2conn, 50) if f.source == "dart"]
    assert repo.get_setting(p2conn, watch_engine.FILINGS_SEEN.format("KR:012450")) is None
    # The schedule does not run it again that day; the next day DART answers.
    assert watch_due(p2conn, p2ctx.cfg, "paper", kst("2026-10-13 10:00")) is None
    del world.filing_errors["dart"]
    world.filing_errors["edgar"] = SourceUnreachableError("TimeoutError: timed out")
    flat_world(p2conn, world, "2026-10-14", overrides={"042660.KS": ocean_falls})
    nxt = watch_job(p2ctx, "paper", kst("2026-10-14 08:40"))
    assert "filings:dart:KR:012450:2026-06-09:2026-10-14" in world.calls  # from the pick again
    states = {s: ai_repo.source_state(p2conn, s) for s in ("dart", "edgar")}
    assert {s: (r.state if r else None) for s, r in states.items()} == {
        "dart": "ok",
        "edgar": "stale",
    }
    assert nxt["filings"]["new"] == 3


def test_scores_come_due_at_6_months(p2conn: sqlite3.Connection) -> None:
    at = kst("2026-10-13 08:40")
    msft = Instrument("US:MSFT", Market.US, Currency.USD, Kind.STOCK, "MSFT", "Microsoft", "MSFT")
    ibm = Instrument("US:IBM", Market.US, Currency.USD, Kind.STOCK, "IBM", "IBM", "IBM")
    with transaction(p2conn):
        for inst in (msft, ibm):
            repo.upsert_instrument(p2conn, inst, at)
        ids = {}
        for inst, status in ((msft, "held"), (ibm, "sold")):
            ids[inst.ticker] = ai_repo.insert_pick(
                p2conn,
                ai_repo.NewPick(
                    ledger_id="paper",
                    rule_id=RULE_ID,
                    instrument_id=inst.instrument_id,
                    status=status,
                    picked_on=date(2026, 1, 5),
                    picked_price=D(100),
                    benchmark="SPY",
                    benchmark_price=D(100),
                    theme="t",
                    rationale="r",
                    confirm=[],
                    invalidate=[],
                    buy=[],
                    confidence=None,
                    source="test",
                ),
                at,
            )
        ai_repo.update_pick(p2conn, ids["IBM"], at, closed_on=date(2026, 3, 2))
        ai_repo.insert_switch(
            p2conn,
            ledger_id="paper",
            rule_id=RULE_ID,
            sold_pick_id=ids["IBM"],
            bought_pick_id=ids["MSFT"],
            decided_on=date(2026, 3, 2),
            task_id=None,
            costs={"total_pct": "0.5"},
            at=at,
        )
    world = World()
    sessions = world.series(
        "MSFT", Market.US, "2025-12-01", "2026-10-12", lambda i, d: 100 + D(i) / 10
    )
    world.series("IBM", Market.US, "2025-12-01", "2026-10-12", lambda i, d: 100 - D(i) / 20)
    world.series("SPY", Market.US, "2025-12-01", "2026-10-12", lambda i, d: 100 + D(i) / 20)
    with transaction(p2conn):
        n = scoring.score_due(p2conn, "paper", world.adjusted, at)
    assert n == 4  # the MSFT pick, the IBM pick, the IBM sale, the switch: 6 months each
    scores = {(s.kind, s.ref_id, s.horizon_months): s for s in ai_repo.scores_of(p2conn)}
    price = {sym: dict(world.adjusted[sym]) for sym in ("MSFT", "IBM", "SPY")}

    def ret(sym: str, a: date, b: date) -> Decimal:
        return price[sym][b] / price[sym][a] - 1

    start, due = date(2026, 1, 5), date(2026, 7, 5)
    last = NYSE.latest_trading_day(due)  # 7/3 is a holiday: 7/2
    assert last in sessions
    msft_score = scores[("pick", ids["MSFT"], 6)]
    assert (msft_score.due_on, msft_score.end_on) == (due, last)
    assert msft_score.excess == (ret("MSFT", start, last) - ret("SPY", start, last)).quantize(
        scoring.PLACES
    )
    ibm_pick = scores[("pick", ids["IBM"], 6)]
    assert ibm_pick.end_on == date(2026, 3, 2)  # sold: scored up to the sale
    sell = scores[("sell", ids["IBM"], 6)]
    assert (sell.start_on, sell.due_on) == (date(2026, 3, 2), date(2026, 9, 2))
    assert sell.excess < 0  # IBM kept falling against the index: the sale was right
    switch = scores[("switch", 1, 6)]
    expected = ret("MSFT", date(2026, 3, 2), date(2026, 9, 2)) - ret(
        "IBM", date(2026, 3, 2), date(2026, 9, 2)
    )
    assert switch.excess == (expected - D("0.005")).quantize(scoring.PLACES)
    with transaction(p2conn):
        assert scoring.score_due(p2conn, "paper", world.adjusted, at) == 0  # written once
    # A gap in the closes waits instead of scoring the wrong day.
    short = {k: [x for x in v if x[0] < date(2026, 6, 1)] for k, v in world.adjusted.items()}
    assert scoring.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    with transaction(p2conn):
        p2conn.execute("DELETE FROM scores")
        assert scoring.score_due(p2conn, "paper", short, at) == 1  # only the IBM pick (to 3/2)


# ── when it runs ─────────────────────────────────────────────────────────────────────────────


def test_the_watch_runs_on_weekdays_after_the_check(
    p2ctx: JobContext,
    p2conn: sqlite3.Connection,
    world: World,
    conn: sqlite3.Connection,
    cfg: Config,
) -> None:
    c = p2ctx.cfg
    assert watch_due(p2conn, c, "paper", kst("2026-10-13 08:29")) is None
    due = watch_due(p2conn, c, "paper", kst("2026-10-13 08:30"))
    assert due is not None
    assert (due.task, due.why) == ("watch", "on-time")
    late = watch_due(p2conn, c, "paper", kst("2026-10-13 14:00"))
    assert late is not None
    assert late.why == "late"
    assert watch_due(p2conn, c, "paper", kst("2026-10-17 09:00")) is None  # Saturday
    assert watch_due(p2conn, c, "live", kst("2026-10-13 09:00")) is None  # share 0
    assert watch_due(conn, cfg, "paper", kst("2026-10-13 09:00")) is None  # phase-1 shares
    assert watch_job(p2ctx, "paper", kst("2026-10-17 09:00"))["result"] == "weekend"
    assert watch_job(p2ctx, "live", kst("2026-10-13 09:00"))["result"] == "not-active"
    with transaction(p2conn):  # a crashed run is tried again after 30 minutes
        ai_repo.insert_job_run(
            p2conn,
            job="watch",
            ledger_id="paper",
            run_date=date(2026, 10, 13),
            started_at=kst("2026-10-13 08:30"),
            ended_at=kst("2026-10-13 08:30"),
            result="failed",
            error="boom",
            details={},
        )
    assert watch_due(p2conn, c, "paper", kst("2026-10-13 08:45")) is None
    retry = watch_due(p2conn, c, "paper", kst("2026-10-13 09:00"))
    assert retry is not None
    assert retry.why == "retry"


def test_the_tick_runs_the_watch_after_the_check(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World, tmp_path: object
) -> None:
    first_watch_world(p2conn, world)
    lines: list[dict[str, object]] = []
    out = run_tick(
        p2ctx, "paper", lambda: kst("2026-10-13 08:40"), p2ctx.cfg.db_path.parent, lines.append
    )
    tasks = [line["task"] for line in out]
    assert tasks.index("check") < tasks.index("watch")
    watch_line = next(line for line in out if line["task"] == "watch")
    assert watch_line["result"] == "ok"
    assert len(watch_line["tasks"]) == 6


def test_a_crash_inside_the_watch_is_recorded(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*args: object, **kwargs: object) -> object:
        raise RuntimeError("broken")

    monkeypatch.setattr(watch_engine, "vs_index_points", boom)
    report = watch_job(p2ctx, "paper", kst("2026-10-13 08:40"))
    assert (report["result"], report["error"]) == ("failed", "RuntimeError: broken")
    runs = ai_repo.job_runs_on(p2conn, "watch", date(2026, 10, 13))
    assert [r.result for r in runs] == ["failed"]
    with pytest.raises(RuntimeError):
        watch_job(p2ctx, "paper", kst("2026-10-13 08:40"), dry_run=True)


def test_reviews_are_queued_the_evening_before_the_first(
    p2ctx: JobContext, p2conn: sqlite3.Connection
) -> None:
    assert reviews.review_month(kst("2026-10-31 21:59")) is None
    assert reviews.review_month(kst("2026-10-31 22:00")) == date(2026, 11, 1)
    assert reviews.review_month(kst("2026-11-03 12:00")) == date(2026, 11, 1)
    assert reviews.review_month(kst("2026-11-04 12:00")) is None
    assert queue_due(p2conn, "paper", kst("2026-10-31 21:59")) is None
    due = queue_due(p2conn, "paper", kst("2026-10-31 22:00"))
    assert due is not None
    assert (due.task, due.why) == ("ai-queue", "on-time")
    report = queue_job(p2ctx, "paper", kst("2026-10-31 22:00"))
    assert (report["result"], report["month"], len(report["tasks"])) == ("ok", "2026-11", 15)
    task = ai_repo.tasks_of(p2conn, kind="monthly-review")[0]
    assert task.not_before == kst("2026-10-31 22:00")
    assert queue_due(p2conn, "paper", kst("2026-10-31 22:05")) is None  # queued
    assert queue_job(p2ctx, "paper", kst("2026-11-04 08:00"))["result"] == "not-due"
    assert queue_job(p2ctx, "live", kst("2026-10-31 22:00"))["result"] == "not-active"
    # The first of December also starts a discovery; a late server still queues it on the 2nd.
    late = queue_due(p2conn, "paper", kst("2026-12-02 10:00"))
    assert late is not None
    assert late.why == "late"
    december = queue_job(p2ctx, "paper", kst("2026-12-02 10:00"))
    assert [t["kind"] for t in december["tasks"]].count("discovery") == 1
    assert len(ai_repo.tasks_of(p2conn, kind="discovery")) == 1
    again = reviews.queue_reviews(p2conn, "paper", kst("2026-12-02 10:05"))
    assert again["tasks"] == []  # every task is keyed by month


def test_a_ledger_started_before_phase_2_gives_the_rule_nothing(
    ctx: JobContext, conn: sqlite3.Connection, world: World
) -> None:
    from .phase2 import start_paper

    start_paper(ctx, world)  # phase-1 shares: '지수 반반' took all of it
    with transaction(conn):
        ai_repo.set_share(conn, "paper", RULE_ID, D(20), kst("2026-10-12 12:00"))
    assert not reviews.rule_active(conn, "paper")  # no money moves between rules by itself
    assert watch_due(conn, ctx.cfg, "paper", kst("2026-10-13 09:00")) is None
