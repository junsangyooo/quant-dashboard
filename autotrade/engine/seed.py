"""The first judgments of '3년 발굴': T24's 15 picks (autotrade/rules/discovery_seed.json).

The file holds the picks.csv conditions moved by hand into the fixed form (PHASE2.md §2 첫 판단);
no AI call is involved. bootstrap imports it once, when the rule has no picks in its ledger yet.
Each pick keeps the day and price it was picked at (scoring starts there), not the day it is
imported.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from autotrade.db import ai_repo, repo
from autotrade.domain.conditions import condition_json, parse_conditions
from autotrade.domain.instruments import MARKET_CURRENCY, Instrument, Kind, Market

SEED_PATH = Path(__file__).resolve().parents[1] / "rules" / "discovery_seed.json"


@dataclass(frozen=True)
class SeedPick:
    instrument: Instrument
    picked_on: date
    close: Decimal
    benchmark: str
    benchmark_close: Decimal
    theme: str
    confidence: str | None
    rationale: str
    confirm: list[dict[str, Any]]
    invalidate: list[dict[str, Any]]
    buy: list[dict[str, Any]]
    texts: dict[str, Any]
    note: str | None


@dataclass(frozen=True)
class Seed:
    source: str
    ledger_id: str
    rule_id: str
    picks: list[SeedPick]


def stock(market: str, ticker: str, name: str, yahoo: str) -> Instrument:
    m = Market(market)
    return Instrument(
        instrument_id=f"{m.value}:{ticker}",
        market=m,
        currency=MARKET_CURRENCY[m],
        kind=Kind.STOCK,
        ticker=ticker,
        name=name,
        yahoo_symbol=yahoo,
    )


def _pick(data: dict[str, Any]) -> SeedPick:
    # Parsing checks every condition against the metric dictionary; the stored form is the
    # normalised JSON (notes kept).
    lists = {
        key: [condition_json(c) for c in parse_conditions(data.get(key, []))]
        for key in ("confirm", "invalidate", "buy")
    }
    return SeedPick(
        instrument=stock(data["market"], data["ticker"], data["name"], data["yahoo"]),
        picked_on=date.fromisoformat(data["picked_on"]),
        close=Decimal(data["close"]),
        benchmark=data["benchmark"],
        benchmark_close=Decimal(data["benchmark_close"]),
        theme=data["theme"],
        confidence=data.get("confidence"),
        rationale=data["rationale"],
        confirm=lists["confirm"],
        invalidate=lists["invalidate"],
        buy=lists["buy"],
        texts={k: data[k] for k in ("confirm_text", "invalidate_text", "buy_text") if k in data},
        note=data.get("note"),
    )


def read_seed(path: Path = SEED_PATH) -> Seed:
    data = json.loads(path.read_text())
    return Seed(
        source=str(data["source"]),
        ledger_id=str(data["ledger_id"]),
        rule_id=str(data["rule_id"]),
        picks=[_pick(p) for p in data["picks"]],
    )


def import_seed(conn: sqlite3.Connection, at: datetime, path: Path = SEED_PATH) -> int:
    """Add the seed's picks unless the rule already has picks in that ledger. Returns how many.
    The caller owns the transaction."""
    seed = read_seed(path)
    if ai_repo.picks_of(conn, seed.ledger_id, seed.rule_id):
        return 0
    for p in seed.picks:
        repo.upsert_instrument(conn, p.instrument, at)
        ai_repo.insert_pick(
            conn,
            ai_repo.NewPick(
                ledger_id=seed.ledger_id,
                rule_id=seed.rule_id,
                instrument_id=p.instrument.instrument_id,
                status="held",
                picked_on=p.picked_on,
                picked_price=p.close,
                benchmark=p.benchmark,
                benchmark_price=p.benchmark_close,
                theme=p.theme,
                rationale=p.rationale,
                confirm=p.confirm,
                invalidate=p.invalidate,
                buy=p.buy,
                confidence=p.confidence,
                source=seed.source,
                note=p.note,
                texts=p.texts,
            ),
            at,
        )
    return len(seed.picks)
