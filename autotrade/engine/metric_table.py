"""The metric table as the checks, the gauge and the AI packets read it.

Stored values come from '실적 지표 뽑기' (autotrade/ai/flows.py). The derived metrics of the
dictionary (op_margin = operating_income / revenue × 100, book_to_bill = new_orders / revenue)
are computed for every period where both parts are stored in the same unit; a value the
extraction stored itself for that period wins (the company's own rounding). Parts in different
currencies (HD한국조선해양 reports orders in dollars and revenue in won) give nothing: the
condition stays 'unknown' rather than mixing units.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from autotrade.db import ai_repo
from autotrade.domain import metrics
from autotrade.domain.conditions import Observation
from autotrade.domain.periods import PeriodError, parse_period

CENT = Decimal("0.01")


def _order(o: Observation) -> tuple[int, str]:
    try:
        p = parse_period(o.period)
    except PeriodError:
        return (1, o.period)
    return (0, f"{p.kind}:{p.year:04d}:{p.sub:02d}")


def observations(conn: sqlite3.Connection, instrument_id: str, metric: str) -> list[Observation]:
    """Every stored (or derivable) value of one metric of one company, oldest first."""
    d, _ = metrics.resolve(metric)
    found = {
        r.period: Observation(r.period, r.value, r.unit)
        for r in ai_repo.metric_values(conn, instrument_id, metric)
    }
    if d.formula is not None:
        top_key, bottom_key = d.formula
        bottom = {r.period: r for r in ai_repo.metric_values(conn, instrument_id, bottom_key)}
        for top in ai_repo.metric_values(conn, instrument_id, top_key):
            base = bottom.get(top.period)
            if top.period in found or base is None or base.unit != top.unit or base.value <= 0:
                continue
            value = (top.value / base.value * d.scale).quantize(CENT)
            unit = "%" if d.unit_kind == "pct" else "x"
            found[top.period] = Observation(top.period, value, unit)
    return sorted(found.values(), key=_order)


def table(conn: sqlite3.Connection, instrument_id: str) -> dict[str, list[Observation]]:
    """All metrics of one company (stored ones and the derived metrics that can be computed)."""
    keys = {r.metric for r in ai_repo.metric_values(conn, instrument_id)}
    for d in metrics.DICTIONARY:
        if d.formula is not None and set(d.formula) <= keys:
            keys.add(d.key)
    out = {key: observations(conn, instrument_id, key) for key in sorted(keys)}
    return {k: v for k, v in out.items() if v}
