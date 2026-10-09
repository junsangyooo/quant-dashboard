"""Scoring the judgments of '3년 발굴' (PHASE2.md §8, T24 score.py).

Every judgment is compared with the same market's index (069500.KS, SPY) on adjusted closes
(dividends included), 6, 12, 24 and 36 months after it was made. The daily watch scores what has
come due, with the closes it already downloaded; a score is written once per judgment and
horizon (the store keeps the first, and a later run never rewrites it).

  pick    from the pick day to the checkpoint, or to the sale when it was sold earlier:
          value = the stock, index = its market's index, excess = value - index.
  sell    from the sale to the checkpoint: the sold stock against its index. A negative excess
          means the sale was right (the stock then lagged).
  switch  from the switch to the checkpoint: value = the bought stock, index = the sold stock
          (the alternative), excess = value - index - the switch's costs as a share of the money
          moved (D37: a switch has to beat its costs).

A checkpoint is scored only when the closes reach within a week of it, so a gap in the data
waits for the next run instead of scoring the wrong day.
"""

from __future__ import annotations

import calendar
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from autotrade.db import ai_repo, repo
from autotrade.domain.watch import WindowReturn, window_return
from autotrade.rules.discovery import RULE_ID
from autotrade.timeutil import kst_date

HORIZONS = (6, 12, 24, 36)
MAX_DATA_GAP = timedelta(days=7)
PLACES = Decimal("0.000001")

Series = list[tuple[date, Decimal]]


def add_months(d: date, months: int) -> date:
    month = d.month - 1 + months
    year, month = d.year + month // 12, month % 12 + 1
    return date(year, month, min(d.day, calendar.monthrange(year, month)[1]))


def _usable(w: WindowReturn | None, end: date) -> WindowReturn | None:
    return w if w is not None and end - w.last <= MAX_DATA_GAP else None


def _row(
    kind: str,
    ref_id: int,
    horizon: int,
    start: date,
    due: date,
    w: WindowReturn,
    excess: Decimal,
    at: datetime,
) -> ai_repo.ScoreRow:
    return ai_repo.ScoreRow(
        kind=kind,
        ref_id=ref_id,
        horizon_months=horizon,
        start_on=start,
        due_on=due,
        end_on=w.last,
        value_return=w.value.quantize(PLACES),
        index_return=w.index.quantize(PLACES),
        excess=excess.quantize(PLACES),
        scored_at=at,
    )


def _cost_share(costs: dict[str, Any]) -> Decimal:
    try:
        return Decimal(str(costs.get("total_pct", "0"))) / 100
    except ArithmeticError:
        return Decimal(0)


def score_due(
    conn: sqlite3.Connection, ledger_id: str, adjusted: dict[str, Series], at: datetime
) -> int:
    """Write the scores that have come due. Returns how many were written."""
    today = kst_date(at)
    have = {(s.kind, s.ref_id, s.horizon_months) for s in ai_repo.scores_of(conn)}
    rows: list[ai_repo.ScoreRow] = []
    picks = {p.pick_id: p for p in ai_repo.picks_of(conn, ledger_id, RULE_ID, ("held", "sold"))}
    symbols = {
        pid: repo.get_instrument(conn, p.instrument_id).yahoo_symbol for pid, p in picks.items()
    }
    for pick in picks.values():
        stock, index = adjusted.get(symbols[pick.pick_id]), adjusted.get(pick.benchmark)
        if not stock or not index:
            continue
        for h in HORIZONS:
            due = add_months(pick.picked_on, h)
            if due <= today and ("pick", pick.pick_id, h) not in have:
                end = due if pick.closed_on is None else min(due, pick.closed_on)
                w = _usable(window_return(stock, index, pick.picked_on, end), end)
                if w is not None:
                    rows.append(
                        _row("pick", pick.pick_id, h, pick.picked_on, due, w, w.value - w.index, at)
                    )
            if pick.status != "sold" or pick.closed_on is None:
                continue
            due = add_months(pick.closed_on, h)
            if due <= today and ("sell", pick.pick_id, h) not in have:
                w = _usable(window_return(stock, index, pick.closed_on, due), due)
                if w is not None:
                    rows.append(
                        _row("sell", pick.pick_id, h, pick.closed_on, due, w, w.value - w.index, at)
                    )
    for sw in ai_repo.switches_of(conn, ledger_id, RULE_ID):
        bought, sold = picks.get(sw.bought_pick_id), picks.get(sw.sold_pick_id)
        if bought is None or sold is None:
            continue
        b_series, s_series = (
            adjusted.get(symbols[bought.pick_id]),
            adjusted.get(symbols[sold.pick_id]),
        )
        if not b_series or not s_series:
            continue
        for h in HORIZONS:
            due = add_months(sw.decided_on, h)
            if due > today or ("switch", sw.switch_id, h) in have:
                continue
            w = _usable(window_return(b_series, s_series, sw.decided_on, due), due)
            if w is not None:
                excess = w.value - w.index - _cost_share(sw.costs)
                rows.append(_row("switch", sw.switch_id, h, sw.decided_on, due, w, excess, at))
    for row in rows:
        ai_repo.upsert_score(conn, row)
    return len(rows)
