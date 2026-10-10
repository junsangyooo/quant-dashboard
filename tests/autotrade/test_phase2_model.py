"""Phase 2, step 1: schema V4, the seed, the metric dictionary, conditions and rule shares."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from autotrade.config import Config, load_config, parse_shares, read_env_key
from autotrade.db import ai_repo, repo
from autotrade.db.connection import connect, transaction
from autotrade.db.migrations import MIGRATIONS, V1, V2, V3, _statements, current_version, migrate
from autotrade.domain import metrics
from autotrade.domain.conditions import (
    Condition,
    ConditionError,
    Observation,
    check,
    condition_json,
    distance,
    parse_condition,
    parse_conditions,
)
from autotrade.domain.instruments import Currency
from autotrade.domain.ledger import CashFlowKind, LedgerError
from autotrade.domain.periods import Period, PeriodError, is_period, parse_period
from autotrade.engine import sleeves
from autotrade.engine.bootstrap import bootstrap
from autotrade.engine.rebuild import verify_ledger
from autotrade.engine.seed import SEED_PATH, import_seed, read_seed
from autotrade.jobs.tasks import JobContext, check_job, stage_job
from autotrade.rules.discovery import RULE_ID as DISCOVERY

from .fakes import KR, US, World
from .helpers import kst
from .test_engine_first_day import first_day_world

D = Decimal


# ── schema ───────────────────────────────────────────────────────────────────────────────


def test_v4_keeps_plans_stages_orders_and_events(tmp_path: Path) -> None:
    conn = connect(tmp_path / "v3.db")
    try:
        conn.execute(
            "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT NOT NULL,"
            " applied_at TEXT NOT NULL)"
        )
        for version, sql in ((1, V1), (2, V2), (3, V3)):
            with transaction(conn):
                for statement in _statements(sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations VALUES (?, 'old', '2026-10-09T00:00:00+00:00')",
                    (version,),
                )
        stamp = "2026-10-07T00:00:00+00:00"
        with transaction(conn):
            conn.execute(
                "INSERT INTO ledgers (ledger_id, name, created_at, updated_at)"
                " VALUES ('paper', 'p', ?, ?)",
                (stamp, stamp),
            )
            conn.execute(
                "INSERT INTO rules (rule_id, name, kind, definition, updated_at)"
                " VALUES ('index_half', '지수 반반', 'fixed', '{}', ?)",
                (stamp,),
            )
            conn.execute(
                "INSERT INTO instruments (instrument_id, market, currency, kind, ticker, name,"
                " yahoo_symbol, updated_at) VALUES ('KR:069500', 'KR', 'KRW', 'etf', '069500',"
                " 'K', '069500.KS', ?)",
                (stamp,),
            )
            conn.execute(
                "INSERT INTO plans (plan_id, ledger_id, rule_id, plan_date, reason, status, basis,"
                " weights_before, weights_after_est, created_at) VALUES (7, 'paper', 'index_half',"
                " '2026-10-07', 'drift', 'in-progress', '{}', '{}', '{}', ?)",
                (stamp,),
            )
            conn.execute(
                "INSERT INTO stages (stage_id, plan_id, seq, kind, market, scheduled_at, due_at,"
                " status) VALUES (3, 7, 1, 'sell', 'KR', ?, ?, 'pending')",
                (stamp, stamp),
            )
            conn.execute(
                "INSERT INTO orders (order_id, idem_key, ledger_id, plan_id, stage_id, stage,"
                " market, instrument_id, side, currency, est_amount, status, created_at) VALUES"
                " (5, 'k', 'paper', 7, 3, 'sell', 'KR', 'KR:069500', 'sell', 'KRW', '1',"
                " 'pending', ?)",
                (stamp,),
            )
            conn.execute(
                "INSERT INTO events (event_id, ledger_id, kind, event_date, occurred_at, plan_id,"
                " ref, payload, created_at, updated_at) VALUES (9, 'paper', 'rebalance',"
                " '2026-10-07', ?, 7, 'r', '{}', ?, ?)",
                (stamp, stamp, stamp),
            )
        assert migrate(conn) == len(MIGRATIONS) == 5
        assert repo.get_plan(conn, 7).reason == "drift"
        assert [s.stage_id for s in repo.stages_of(conn, 7)] == [3]
        assert repo.get_order(conn, 5).plan_id == 7
        event = repo.event_of_plan(conn, 7)
        assert event is not None
        assert (event.event_id, event.ref) == (9, "r")
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1  # back on
        with transaction(conn):  # the new kinds and reasons fit
            conn.execute(
                "INSERT INTO plans (ledger_id, rule_id, plan_date, reason, status, basis,"
                " weights_before, weights_after_est, created_at) VALUES ('paper', 'index_half',"
                " '2026-10-08', 'ai', 'in-progress', '{}', '{}', '{}', ?)",
                (stamp,),
            )
            repo.insert_event(
                conn,
                ledger_id="paper",
                kind="ai-sell",
                event_date=date(2026, 10, 8),
                occurred_at=kst("2026-10-08 09:00"),
            )
        with pytest.raises(sqlite3.IntegrityError), transaction(conn):
            conn.execute("DELETE FROM plans WHERE plan_id = 7")  # foreign keys are enforced
    finally:
        conn.close()


def test_a_migration_that_breaks_foreign_keys_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from autotrade.db import migrations

    conn = connect(tmp_path / "x.db")
    try:
        migrate(conn)
        bad = (
            6,
            "orphan",
            "INSERT INTO stages (plan_id, seq, kind, market, scheduled_at, due_at,"
            " status) VALUES (99, 1, 'sell', 'KR', 'x', 'x', 'pending')",
        )
        monkeypatch.setattr(migrations, "MIGRATIONS", (*migrations.MIGRATIONS, bad))
        monkeypatch.setattr(migrations, "FK_OFF", frozenset({6}))
        with pytest.raises(sqlite3.IntegrityError, match="breaks foreign keys"):
            migrate(conn)
        assert current_version(conn) == 5  # rolled back
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    finally:
        conn.close()


# ── the seed and the dictionary ──────────────────────────────────────────────────────────


def test_the_seed_is_t24_moved_by_hand(conn: sqlite3.Connection) -> None:
    seed = read_seed()
    assert (seed.source, seed.ledger_id, seed.rule_id) == ("T24", "paper", DISCOVERY)
    assert len(seed.picks) == 15
    markets = [p.instrument.market.value for p in seed.picks]
    assert (markets.count("KR"), markets.count("US")) == (8, 7)
    # Every condition passed the dictionary; text-only ones are events.
    events = [c for p in seed.picks for c in p.invalidate if c["type"] == "event"]
    assert {c["kind"] for c in events} == {"customer_loss", "capex_cut", "guidance_cut"}
    avgo = next(p for p in seed.picks if p.instrument.ticker == "AVGO")
    assert avgo.invalidate[1] == {
        "type": "event",
        "kind": "customer_loss",
        "text": "상위 XPU 고객 이탈 또는 자체설계 전환 공시",
    }
    hd = next(p for p in seed.picks if p.instrument.ticker == "267260")
    assert hd.invalidate == [
        {"type": "streak", "metric": "backlog", "change": "yoy", "direction": "down", "periods": 2},
        {"type": "level", "metric": "op_margin", "op": "<", "value": 20, "unit": "%"},
    ]
    assert hd.texts["invalidate_text"] == "수주잔고 2분기 연속 전년보다 감소, 또는 이익률 20% 미만"
    notes = [c for p in seed.picks for c in (*p.confirm, *p.invalidate) if "note" in c]
    assert len(notes) >= 10  # uncertain transcriptions are marked

    # bootstrap imported it once: 15 held picks at the T24 prices and dates.
    picks = ai_repo.picks_of(conn, "paper", DISCOVERY)
    assert [p.status for p in picks] == ["held"] * 15
    first = picks[0]
    assert (first.instrument_id, first.picked_on, first.picked_price) == (
        "KR:012450",
        date(2026, 10, 7),
        D("972000"),
    )
    assert (first.benchmark, first.benchmark_price) == ("069500.KS", D("108550"))
    assert repo.get_instrument(conn, "US:TSM").yahoo_symbol == "TSM"
    with transaction(conn):
        assert import_seed(conn, kst("2026-10-09 12:00")) == 0  # once only
    assert ai_repo.picks_of(conn, "live", DISCOVERY) == []
    assert SEED_PATH.name == "discovery_seed.json"


def test_the_dictionary_is_in_the_database(conn: sqlite3.Connection) -> None:
    assert ai_repo.dictionary_keys(conn) == sorted(m.key for m in metrics.DICTIONARY)
    assert metrics.label("segment_revenue:AI") == "AI 매출"
    assert metrics.label("op_margin") == "이익률"
    assert metrics.resolve("guidance:2027 매출 성장")[1] == "2027 매출 성장"
    for bad in ("nope", "op_margin:x", "segment_revenue", "segment_revenue: "):
        with pytest.raises(metrics.MetricError):
            metrics.resolve(bad)
    assert metrics.unit_fits("backlog", "USD")
    assert not metrics.unit_fits("op_margin", "KRW")
    assert not metrics.unit_fits("op_margin", "won")
    assert metrics.unit_fits("guidance:x", "%")


# ── conditions ───────────────────────────────────────────────────────────────────────────


def test_the_fixed_form_is_strict() -> None:
    level = parse_condition(
        {"type": "level", "metric": "op_margin", "op": "<", "value": 20, "unit": "%"}
    )
    assert level == Condition("level", metric="op_margin", op="<", value=D(20), unit="%")
    assert condition_json(level) == {
        "type": "level",
        "metric": "op_margin",
        "op": "<",
        "value": 20,
        "unit": "%",
    }
    assert condition_json(parse_condition({"type": "price", "op": "<=", "value": 74100.5})) == {
        "type": "price",
        "op": "<=",
        "value": 74100.5,
    }
    assert parse_condition({"type": "valuation", "metric": "per_fwd", "op": "<=", "value": 15})
    bad = [
        "x",
        {"type": "nope"},
        {"type": "level", "metric": "op_margin", "op": "<", "value": 20, "unit": "%", "x": 1},
        {"type": "level", "metric": "op_margin", "op": "=", "value": 20, "unit": "%"},
        {"type": "level", "metric": "op_margin", "op": "<", "value": "a", "unit": "%"},
        {"type": "level", "metric": "op_margin", "op": "<", "value": True, "unit": "%"},
        {"type": "level", "metric": "op_margin", "op": "<", "value": "Infinity", "unit": "%"},
        {"type": "level", "metric": "op_margin", "op": "<", "value": 20, "unit": "KRW"},
        {
            "type": "level",
            "metric": "revenue",
            "op": "<",
            "value": 20,
            "unit": "KRW",
            "change": "yoy",
        },
        {"type": "level", "metric": "revenue", "op": "<", "value": 2, "unit": "%", "change": "mom"},
        {"type": "level", "metric": "nope", "op": "<", "value": 20, "unit": "%"},
        {"type": "level", "metric": 3, "op": "<", "value": 20, "unit": "%"},
        {
            "type": "level",
            "metric": "revenue",
            "op": "<",
            "value": 20,
            "unit": "KRW",
            "period": "Q3",
        },
        {
            "type": "level",
            "metric": "revenue",
            "op": "<",
            "value": 20,
            "unit": "KRW",
            "period": "2026Q3",
            "periods": 2,
        },
        {"type": "streak", "metric": "revenue", "change": "yoy", "direction": "sideways"},
        {"type": "streak", "metric": "revenue", "change": "yoy", "direction": "down", "periods": 0},
        {"type": "event", "kind": "", "text": "x"},
        {"type": "event", "kind": "a", "text": " "},
        {"type": "price", "op": "<=", "value": 0},
        {"type": "valuation", "metric": "roe", "op": "<=", "value": 1},
        {"type": "event", "kind": "a", "text": "b", "note": 3},
    ]
    for item in bad:
        with pytest.raises(ConditionError):
            parse_condition(item)  # type: ignore[arg-type]
    with pytest.raises(ConditionError):
        parse_conditions({"type": "event"})


def obs(*rows: tuple[str, str]) -> list[Observation]:
    return [Observation(p, D(v), "%") for p, v in rows]


def money(*rows: tuple[str, str], unit: str = "KRW") -> list[Observation]:
    return [Observation(p, D(v), unit) for p, v in rows]


def test_level_conditions() -> None:
    margin = parse_condition(
        {"type": "level", "metric": "op_margin", "op": "<", "value": 20, "unit": "%"}
    )
    clear = check(margin, obs(("2026Q1", "24.9"), ("2026Q2", "25.1")))
    assert (clear.verdict, clear.period, clear.value) == ("clear", "2026Q2", D("25.1"))
    hit = check(margin, obs(("2026Q2", "25.1"), ("2026Q3", "19.4")))
    assert (hit.verdict, hit.run) == ("hit", 1)
    assert check(margin, []).verdict == "unknown"
    assert check(margin, money(("2026Q3", "19"))).reason == "values are in KRW, not %"
    # The gauge: 25 on the pick day, 22.3 now, sell below 20 -> 54% of the way, 2.3%p left.
    dist = distance(check(margin, obs(("2026Q3", "22.3"))), D(25))
    assert dist is not None
    assert (dist.progress, dist.margin) == (D(54), D("2.3"))
    hit_dist = distance(hit, D(25))
    assert hit_dist is not None
    assert (hit_dist.progress, hit_dist.margin) == (D(100), D(0))
    above = parse_condition(
        {"type": "level", "metric": "net_debt_to_ebitda", "op": ">", "value": 2.5, "unit": "x"}
    )
    up = distance(check(above, [Observation("FY2026", D("2.0"), "x")]), D("1.0"))
    assert up is not None
    assert (up.progress, up.margin) == (D("200") / 3, D("0.5"))
    no_base = distance(check(above, [Observation("FY2026", D("2.0"), "x")]), None)
    assert no_base is not None
    assert no_base.progress == 0  # the pick-day value is the current one

    # Several periods in a row (삼양식품 매출 증가율 2분기 연속 10% 미만).
    growth = parse_condition(
        {
            "type": "level",
            "metric": "revenue",
            "change": "yoy",
            "op": "<",
            "value": 10,
            "unit": "%",
            "periods": 2,
        }
    )
    revenue = money(
        ("2025Q1", "100"),
        ("2025Q2", "100"),
        ("2025Q3", "100"),
        ("2026Q1", "125"),
        ("2026Q2", "108"),
        ("2026Q3", "105"),
    )
    two = check(growth, revenue)
    assert (two.verdict, two.run, two.value) == ("hit", 2, D(5))
    one = check(growth, revenue[:5])
    assert (one.verdict, one.run) == ("clear", 1)
    one_dist = distance(one, None)
    assert one_dist is not None
    assert (one_dist.progress, one_dist.periods_left) == (D(50), 1)
    assert check(growth, money(("2026Q1", "100"))).verdict == "unknown"  # no year-ago value
    gap = money(("2025Q1", "100"), ("2025Q3", "100"), ("2026Q1", "105"), ("2026Q3", "105"))
    assert check(growth, gap).run == 1  # a missing quarter breaks the run

    # One exact period (셀트리온 3Q 4,500억 미만).
    q3 = parse_condition(
        {
            "type": "level",
            "metric": "operating_income",
            "op": "<",
            "value": 450000000000,
            "unit": "KRW",
            "period": "2026Q3",
        }
    )
    assert check(q3, money(("2026Q2", "451791591338"))).reason == "not reported yet"
    assert check(q3, money(("2026Q3", "460000000000"))).verdict == "clear"
    assert check(q3, money(("2026Q3", "440000000000"))).verdict == "hit"
    assert distance(check(q3, []), None) is None


def test_streak_conditions_and_skips() -> None:
    down2 = parse_condition(
        {"type": "streak", "metric": "backlog", "change": "yoy", "direction": "down", "periods": 2}
    )
    usd = [
        ("2025Q1", "70"),
        ("2025Q2", "80"),
        ("2025Q3", "85"),
        ("2026Q1", "75"),
        ("2026Q2", "79"),
        ("2026Q3", "84"),
    ]
    hit = check(down2, money(*usd, unit="USD"))
    assert (hit.verdict, hit.run, hit.period) == ("hit", 2, "2026Q3")
    assert check(down2, money(*usd[:5], unit="USD")).verdict == "clear"  # 2026Q1 went up
    assert check(down2, money(("2026Q1", "1"), unit="USD")).verdict == "unknown"
    qoq = parse_condition(
        {
            "type": "streak",
            "metric": "segment_revenue:AI",
            "change": "qoq",
            "direction": "down",
            "periods": 2,
        }
    )
    fiscal = money(("FY2026Q2", "12"), ("FY2026Q3", "11"), ("FY2026Q4", "10"), unit="USD")
    assert check(qoq, fiscal).verdict == "hit"
    months = [Observation("2026-07", D(5), "%"), Observation("2026-08", D(4), "%")]
    mom = parse_condition(
        {"type": "streak", "metric": "monthly_revenue_yoy", "change": "qoq", "direction": "down"}
    )
    assert check(mom, months).verdict == "hit"
    mixed = [Observation("2026Q1", D(1), "USD"), Observation("bad", D(2), "USD")]
    assert check(qoq, mixed).verdict == "unknown"
    event = parse_condition({"type": "event", "kind": "capex_cut", "text": "설비투자 축소"})
    assert check(event, []).verdict == "skip"
    assert distance(check(event, []), None) is None
    streak_dist = distance(hit, None)
    assert streak_dist is not None
    assert (streak_dist.progress, streak_dist.periods_left) == (D(100), 0)


def test_periods() -> None:
    assert parse_period("2026Q2") == Period("quarter", 2026, 2)
    assert parse_period("FY2026Q4").key == "FY2026Q4"
    assert parse_period("2026-08").previous().key == "2026-07"
    assert parse_period("2026-01").previous().key == "2025-12"
    assert parse_period("2026Q1").previous().key == "2025Q4"
    assert parse_period("FY2027").previous().key == "FY2026"
    assert parse_period("2026Q3").year_ago().key == "2025Q3"
    assert parse_period("FY2027").key == "FY2027"
    assert parse_period("2026Q1") < parse_period("2026Q2")
    assert is_period("2026-12")
    assert not is_period("2026-13")
    with pytest.raises(PeriodError):
        parse_period("Q3")


# ── shares and sleeves ───────────────────────────────────────────────────────────────────


def test_rule_shares(conn: sqlite3.Connection, tmp_path: Path) -> None:
    assert ai_repo.shares(conn, "paper") == {DISCOVERY: D(0), "index_half": D(100)}  # test cfg
    fresh = connect(tmp_path / "fresh.db")
    try:
        bootstrap(fresh, Config(db_path=tmp_path / "fresh.db"), kst("2026-10-09 12:00"))
        assert ai_repo.shares(fresh, "paper") == {DISCOVERY: D(20), "index_half": D(80)}
        assert ai_repo.shares(fresh, "live") == {DISCOVERY: D(0), "index_half": D(100)}
    finally:
        fresh.close()
    assert parse_shares("index_half=70, discovery_3y=30") == {
        "index_half": D(70),
        "discovery_3y": D(30),
    }
    for bad in ("index_half=70", "x", "index_half=120,discovery_3y=-20", "=100"):
        with pytest.raises(ValueError, match="rule share"):
            parse_shares(bad)
    cfg = load_config({"AUTOTRADE_PAPER_SHARES": "index_half=90,discovery_3y=10"})
    assert cfg.rule_shares["paper"]["discovery_3y"] == D(10)
    secrets = tmp_path / ".env"
    secrets.write_text("OTHER=1\nexport DART_API_KEY='abc'\n")
    cfg = load_config({"AUTOTRADE_SECRETS_ENV": str(secrets), "AUTOTRADE_AI_CALLS": "1"})
    assert (cfg.dart_api_key, cfg.ai_calls_enabled) == ("abc", True)
    assert read_env_key(tmp_path / "missing", "X") is None
    assert read_env_key(secrets, "NONE") is None


@pytest.fixture
def shared(tmp_path: Path) -> sqlite3.Connection:
    cfg = Config(db_path=tmp_path / "shared.db", paper_start_date=date(2026, 7, 1))
    c = connect(cfg.db_path)
    bootstrap(c, cfg, kst("2026-06-30 12:00"))
    return c


def test_the_start_is_shared_80_20(
    shared: sqlite3.Connection, world: World, tmp_path: Path
) -> None:
    cfg = Config(db_path=tmp_path / "shared.db", paper_start_date=date(2026, 7, 1))
    ctx = JobContext(shared, cfg, world.sources())
    first_day_world(world)
    report = check_job(ctx, "paper", kst("2026-07-01 08:30"))
    assert report["result"] == "rebalance"
    sleeve = ai_repo.load_sleeve(shared, "paper", DISCOVERY)
    assert sleeve.cash_of(Currency.KRW) == D("2000000")  # 20% of 10,000,000
    assert sleeve.contributions_krw == D("2000000")
    start = repo.start_event(shared, "paper")
    assert start is not None
    assert start.payload["sleeves"] == {DISCOVERY: "2000000"}
    # '지수 반반' plans on its 8,000,000: 4,000,000 / (32,000 x 1.00015) -> 124 shares.
    orders = {(o.side, o.market): o for o in repo.orders_of_ledger(shared, "paper")}
    assert orders[("buy", "KR")].qty == 124
    base = sleeves.base_view(shared, "paper")
    assert base.cash_of(Currency.KRW) == D("8000000")
    for t in ("09:05", "09:10", "22:30"):
        stage_job(ctx, "paper", kst(f"2026-07-01 {t}"))
    assert sleeves.base_view(shared, "paper").qty_of(KR) == 124
    assert ai_repo.load_sleeve(shared, "paper", DISCOVERY).cash_of(Currency.KRW) == D("2000000")
    assert sleeves.base_view(shared, "paper").qty_of(US) > 0
    assert verify_ledger(shared, "paper") == []
    assert sleeves.verify_sleeves(shared, "paper") == []
    shared.close()


def test_sleeve_arithmetic(shared: sqlite3.Connection) -> None:
    at = kst("2026-07-01 08:30")
    with transaction(shared):
        state = repo.load_state(shared, "paper")
        assert sleeves.subtract(state, state).positions == {}
        parts = sleeves.split_inflow(
            shared,
            "paper",
            CashFlowKind.DEPOSIT,
            D("1000001"),
            Currency.KRW,
            None,
            None,
            at,
        )
    assert parts == {DISCOVERY: D("200000")}  # rounded down; the base rule keeps the rest
    with pytest.raises(ValueError, match="dividends"):
        sleeves.split_inflow(
            shared, "paper", CashFlowKind.DIVIDEND, D(1), Currency.KRW, None, None, at
        )
    with pytest.raises(LedgerError):
        sleeves.base_view(shared, "paper")  # the sleeve has cash the ledger never received
    assert (
        sleeves.split_dividend(
            shared, "paper", KR, date(2026, 7, 2), 0, D(1), Currency.KRW, None, None, at
        )
        == {}
    )
    shared.close()
