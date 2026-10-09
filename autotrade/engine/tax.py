"""The US tax numbers of a ledger (D36), from its fills: the AI packets read them.

The whole ledger counts (the long-term rule's US ETF too): its trade fills are replayed in time
order with the ledger's own arithmetic (autotrade/domain/ledger.py), and every dollar sale
becomes a SoldLot in won.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from autotrade.config import Config
from autotrade.db import repo
from autotrade.domain.instruments import Currency
from autotrade.domain.ledger import LedgerState, TradeFill, apply_trade
from autotrade.domain.planner import Side
from autotrade.domain.tax import SoldLot, TaxNumbers, numbers, realized_in
from autotrade.timeutil import kst_date


def sold_lots(conn: sqlite3.Connection, ledger_id: str) -> list[SoldLot]:
    state = LedgerState(cash=dict.fromkeys(Currency, Decimal("1e18")))  # cash is not the point
    lots: list[SoldLot] = []
    for fill in repo.fills_of_ledger(conn, ledger_id):
        if fill.kind != "trade" or fill.instrument_id is None or fill.qty is None:
            continue
        if fill.price is None:
            continue
        trade = TradeFill(
            fill.instrument_id,
            fill.currency,
            Side(fill.side),
            fill.qty,
            fill.price,
            fill.fee,
            fill.krw_rate,
        )
        if trade.side is Side.SELL and fill.currency is Currency.USD:
            before = state.positions[fill.instrument_id]
            after = apply_trade(state, trade)
            left = after.positions.get(fill.instrument_id)
            removed = before.cost_krw - (left.cost_krw if left is not None else Decimal(0))
            lots.append(
                SoldLot(
                    kst_date(fill.filled_at).year,
                    trade.to_krw(trade.gross - trade.fee),
                    removed,
                )
            )
            state = after
        else:
            state = apply_trade(state, trade)
    return lots


def us_tax(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    year: int,
    unrealized_krw: Decimal,
) -> TaxNumbers:
    realized = realized_in(sold_lots(conn, ledger_id), year)
    return numbers(year, realized, unrealized_krw, cfg.us_gains_tax, cfg.us_gains_deduction)
