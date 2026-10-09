"""Create or upgrade the database and its fixed rows (idempotent).

Settings written here are defaults; once stored they are the truth (change them in the table).
"""

from __future__ import annotations

import sqlite3
from datetime import datetime

from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.db.connection import transaction
from autotrade.db.migrations import migrate
from autotrade.domain import metrics
from autotrade.domain.instruments import kr_etf, us_etf
from autotrade.engine.common import LIVE, PAPER
from autotrade.engine.seed import import_seed
from autotrade.rules.discovery import discovery_3y
from autotrade.rules.index_half import index_half

MODE = "mode"


def start_date_key(ledger_id: str) -> str:
    return f"ledger.{ledger_id}.start_date"


def start_amount_key(ledger_id: str) -> str:
    return f"ledger.{ledger_id}.start_amount"


KR_TICKER = "rule.index_half.kr_ticker"
US_TICKER = "rule.index_half.us_ticker"


def bootstrap(conn: sqlite3.Connection, cfg: Config, at: datetime) -> None:
    migrate(conn, at)
    with transaction(conn):
        repo.ensure_setting(conn, MODE, "paper", at)
        repo.ensure_setting(conn, start_amount_key(PAPER), str(cfg.paper_start_amount), at)
        repo.ensure_setting(
            conn,
            start_date_key(PAPER),
            cfg.paper_start_date.isoformat() if cfg.paper_start_date else "",
            at,
        )
        kr_ticker = repo.ensure_setting(conn, KR_TICKER, cfg.kr_etf_ticker, at)
        us_ticker = repo.ensure_setting(conn, US_TICKER, cfg.us_etf_ticker, at)
        repo.ensure_ledger(conn, PAPER, "모의투자", at)
        repo.ensure_ledger(conn, LIVE, "실전", at)
        kr = kr_etf(kr_ticker, cfg.kr_etf_name)
        us = us_etf(us_ticker, cfg.us_etf_name)
        repo.upsert_instrument(conn, kr, at)
        repo.upsert_instrument(conn, us, at)
        rule = index_half(kr, us, cfg.threshold)
        repo.upsert_rule(conn, rule.rule_id, rule.name, rule.kind, rule.to_json(), at)
        # Phase 2: the AI rule, its metric dictionary, the rule shares and its first judgments.
        ai_rule = discovery_3y()
        repo.upsert_rule(conn, ai_rule.rule_id, ai_rule.name, ai_rule.kind, ai_rule.to_json(), at)
        ai_repo.sync_dictionary(conn, metrics.DICTIONARY)
        for ledger_id, shares in cfg.rule_shares.items():
            for rule_id, pct in shares.items():
                ai_repo.ensure_share(conn, ledger_id, rule_id, pct, at)
        import_seed(conn, at)
