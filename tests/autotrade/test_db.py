"""Database: WAL, versioned migrations, transactions, repository round trips, config."""

from __future__ import annotations

import sqlite3
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path

import pytest

from autotrade.config import Config, load_config
from autotrade.db import repo
from autotrade.db.connection import connect, dumps, journal_mode, loads, transaction
from autotrade.db.migrations import MIGRATIONS, current_version, migrate
from autotrade.domain.instruments import Currency
from autotrade.engine.bootstrap import bootstrap
from autotrade.market.types import FxQuote
from autotrade.rules.model import RuleDef, RuleTarget

from .helpers import kst

D = Decimal


def test_wal_and_versions(tmp_path: Path) -> None:
    conn = connect(tmp_path / "nested" / "dir" / "autotrade.db")
    assert journal_mode(conn) == "wal"
    assert migrate(conn) == len(MIGRATIONS)
    assert migrate(conn) == len(MIGRATIONS)  # idempotent
    assert current_version(conn) == len(MIGRATIONS)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {
        "settings",
        "ledgers",
        "instruments",
        "positions",
        "cash",
        "pending_cash",
        "rules",
        "runs",
        "events",
        "plans",
        "stages",
        "orders",
        "fills",
        "snapshots",
        "market_prices",
        "fx_rates",
        "data_freshness",
    } <= tables
    conn.close()


def test_transactions_commit_roll_back_and_dry_run(conn: sqlite3.Connection) -> None:
    at = kst("2026-10-07 08:30")
    with transaction(conn):
        repo.set_setting(conn, "a", "1", at)

    def fail_inside() -> None:
        with transaction(conn):
            repo.set_setting(conn, "a", "2", at)
            raise RuntimeError

    with pytest.raises(RuntimeError):
        fail_inside()
    with transaction(conn, rollback=True):
        repo.set_setting(conn, "a", "3", at)
    assert repo.get_setting(conn, "a") == "1"
    with transaction(conn):
        assert repo.ensure_setting(conn, "a", "9", at) == "1"
        assert repo.ensure_setting(conn, "b", "9", at) == "9"


def test_bootstrap_rows(conn: sqlite3.Connection, cfg: Config) -> None:
    assert repo.get_setting(conn, "mode") == "paper"
    assert repo.get_setting(conn, "ledger.paper.start_amount") == "10000000"
    assert repo.get_setting(conn, "ledger.paper.start_date") == "2026-07-01"
    assert repo.get_setting(conn, "rule.index_half.us_ticker") == "SPYM"
    assert repo.get_ledger(conn, "paper").name == "모의투자"
    assert repo.get_ledger(conn, "live").start_date is None
    rule = RuleDef.from_json(repo.get_rule(conn, "index_half").definition)
    assert rule.instrument_ids == ("KR:069500", "US:SPYM")
    assert rule.threshold == D("0.02")
    assert rule.display["measured"]["median"] == "9.5"
    assert [r.rule_id for r in repo.enabled_rules(conn)] == ["index_half"]
    assert repo.get_instrument(conn, "US:SPYM").yahoo_symbol == "SPYM"
    bootstrap(conn, cfg, kst("2026-07-01 08:00"))  # idempotent
    with pytest.raises(repo.NotFoundError):
        repo.get_instrument(conn, "US:NOPE")
    with pytest.raises(repo.NotFoundError):
        repo.get_ledger(conn, "nope")
    with pytest.raises(repo.NotFoundError):
        repo.get_rule(conn, "nope")
    with pytest.raises(repo.NotFoundError):
        repo.get_plan(conn, 1)
    with pytest.raises(repo.NotFoundError):
        repo.get_stage(conn, 1)
    with pytest.raises(repo.NotFoundError):
        repo.get_order(conn, 1)
    with pytest.raises(repo.NotFoundError):
        repo.load_state(conn, "nope")


def test_rule_definition_validation() -> None:
    with pytest.raises(ValueError, match="sum"):
        RuleDef("r", "n", "fixed", D(1), (RuleTarget("a", D("0.4")),), D("0.02"))
    with pytest.raises(ValueError, match="threshold"):
        RuleDef("r", "n", "fixed", D(1), (RuleTarget("a", D(1)),), D("0"))
    rule = RuleDef("r", "n", "fixed", D(1), (RuleTarget("a", D(1)),), D("0.02"))
    assert RuleDef.from_json(rule.to_json()) == rule
    with pytest.raises(KeyError):
        rule.target_of("b")


def test_market_rows_and_freshness(conn: sqlite3.Connection) -> None:
    at = kst("2026-10-07 08:30")
    with transaction(conn):
        repo.insert_fx(conn, FxQuote(D("1380.6"), kst("2026-10-07 08:29"), "yfinance"), at)
        repo.insert_fx(conn, FxQuote(D("1381.0"), kst("2026-10-07 09:00"), "yfinance"), at)
        repo.record_fetch(conn, "fx", attempted_at=at, source="yfinance", error=None)
        repo.record_fetch(
            conn, "fx", attempted_at=kst("2026-10-07 09:00"), source=None, error="down"
        )
        repo.record_state(
            conn, "fx", state="fresh", basis="x", expected=None, missing_sessions=0, at=at
        )
    quote = repo.fx_at(conn, kst("2026-10-07 08:45"))
    assert quote is not None
    assert quote.rate == D("1380.6")
    assert repo.fx_at(conn, kst("2026-10-07 08:00")) is None
    fresh = repo.get_freshness(conn, "fx")
    assert fresh is not None
    assert (fresh.state, fresh.error, fresh.source) == ("fresh", "down", "yfinance")
    assert fresh.fetched_at == at  # the failed attempt did not move '받은 시각'
    assert [f.series for f in repo.all_freshness(conn)] == ["fx"]


def test_json_helpers() -> None:
    class Color(Enum):
        RED = "red"

    text = dumps(
        {
            "d": D("1.10"),
            "day": date(2026, 10, 7),
            "at": kst("2026-10-07 09:00"),
            "c": Color.RED,
            "t": (1, 2),
            "s": {3},
        }
    )
    assert loads(text) == {
        "at": "2026-10-07T00:00:00+00:00",
        "c": "red",
        "d": "1.10",
        "day": "2026-10-07",
        "s": [3],
        "t": [1, 2],
    }
    assert loads(None) is None
    with pytest.raises(TypeError):
        dumps({"x": object()})


def test_withdraw_wait_rows(conn: sqlite3.Connection) -> None:
    at = kst("2026-10-02 10:00")
    with transaction(conn):
        repo.add_withdraw_wait(conn, "paper", Currency.KRW, D("500425"), date(2026, 10, 12), at)
    assert [w.amount for w in repo.withdraw_waits(conn, "paper")] == [D("500425")]
    with transaction(conn):
        assert repo.expire_withdraw_waits(conn, "paper", date(2026, 10, 12)) == 0
        assert repo.expire_withdraw_waits(conn, "paper", date(2026, 10, 13)) == 1
    assert repo.withdraw_waits(conn, "paper") == []


def test_load_config_from_environment(tmp_path: Path) -> None:
    cfg = load_config(
        {
            "AUTOTRADE_DB": str(tmp_path / "x.db"),
            "AUTOTRADE_PAPER_START_DATE": "2026-07-01",
            "AUTOTRADE_PAPER_START_AMOUNT": "5000000",
            "AUTOTRADE_US_ETF": "VOO",
        }
    )
    assert cfg.db_path == tmp_path / "x.db"
    assert cfg.paper_start_date == date(2026, 7, 1)
    assert cfg.paper_start_amount == D("5000000")
    assert cfg.us_etf_ticker == "VOO"
    default = load_config({})
    assert default.us_etf_ticker == "SPYM"
    assert default.paper_start_date is None
    assert default.db_path.name == "autotrade.db"
    assert load_config().db_path.name == "autotrade.db"
