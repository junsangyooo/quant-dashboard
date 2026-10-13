"""The live executor and the rules for one live order (autotrade/PHASE3.md 2.3).

The stage runner calls `TossExecutor` inside its one write transaction, so the executor never
touches the network: it reads what the tick's Toss sync recorded in broker_orders (sent, open,
filled, rejected) and turns it into the runner's outcomes. Sending, polling and cancelling are
the sync's (autotrade/jobs/live_tasks.py), outside any transaction.

- Both keys are checked right before an order leaves (`permit_for`): AUTOTRADE_LIVE_ORDERS=1 in
  this process and the stored mode 'live', read in the same transaction that commits the order's
  intent. A cancellation needs only the first key (it lowers risk, and 'live off' must cancel).
- One engine order has one client order id, derived from its idempotency key, so a resend of the
  same order is the same order at Toss (10 minutes, PHASE3.md 1.7). A retry (attempt 2) has its
  own key and id.
- Limit prices: a buy at most `slippage` over the current price, rounded up to the tick; a sell
  at least that much under it, rounded down. Fills are at market; the limit is a cap.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Mapping
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from autotrade.broker.base import (
    LIVE_ENV,
    NOTHING_TO_BUY,
    Failed,
    FailureReason,
    FxRequest,
    NotTraded,
    Outcome,
    TradeFilled,
    TradeRequest,
    Waiting,
)
from autotrade.broker.toss_api import LivePermit
from autotrade.config import Config
from autotrade.db import live_repo, repo
from autotrade.domain.instruments import Currency, Instrument, Kind
from autotrade.domain.planner import Side
from autotrade.engine.bootstrap import MODE

LIVE = "live"
PRICE_PLACES = Decimal("0.000001")

# Broker answers that mean 'not now', not 'no': the attempt fails and is sent again the next
# trading day like any failure (인계 11's '다음 날 같은 시각'), never a manual action at once. A buy
# the cash cannot pay one share of when it is due is neither ('not-sent' NOTHING_TO_BUY): it ends
# with nothing traded (base.NotTraded) and its cash waits for the next check.
RETRYABLE_CODES = frozenset(
    {
        "order-hours-closed",
        "nothing-to-sell",
        "lost",
        "link",
        "unreachable",
        "no-quote",
    }
)


def client_order_id(idem_key: str) -> str:
    """'at-' + 32 hex digits of the order's idempotency key: 35 characters of [A-Za-z0-9-],
    within Toss's 36 (openapi.json clientOrderId)."""
    return "at-" + hashlib.sha256(idem_key.encode("utf-8")).hexdigest()[:32]


# ── the two keys ─────────────────────────────────────────────────────────────────────────


def env_live(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return source.get(LIVE_ENV) == "1"


def permit_for(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    at: datetime,
    *,
    purpose: str = "order",
    env: Mapping[str, str] | None = None,
) -> LivePermit | None:
    """A permit when both keys are there (an order), or the first (a cancellation). Read inside
    the caller's write transaction, so the mode cannot change between the check and the
    intent's commit."""
    if ledger_id != LIVE or not cfg.live_orders or not env_live(env):
        return None
    if purpose == "order" and (repo.get_setting(conn, MODE) or "paper") != LIVE:
        return None
    if purpose not in ("order", "cancel"):
        raise ValueError(f"not a permit purpose: {purpose}")
    return LivePermit(ledger_id, at, _granted=True)


# ── prices on the tick ───────────────────────────────────────────────────────────────────

# KRX tick sizes (2023 table, KOSPI and KOSDAQ alike): (below this price, tick).
KR_STOCK_TICKS: tuple[tuple[Decimal, Decimal], ...] = (
    (Decimal(2000), Decimal(1)),
    (Decimal(5000), Decimal(5)),
    (Decimal(20000), Decimal(10)),
    (Decimal(50000), Decimal(50)),
    (Decimal(200000), Decimal(100)),
    (Decimal(500000), Decimal(500)),
)
KR_STOCK_TOP_TICK = Decimal(1000)
# ETFs and ETNs: 1 won below 2,000, else 5.
KR_ETF_TICKS: tuple[tuple[Decimal, Decimal], ...] = ((Decimal(2000), Decimal(1)),)
KR_ETF_TOP_TICK = Decimal(5)


def tick_size(inst: Instrument, price: Decimal) -> Decimal:
    if inst.currency is Currency.USD:
        return Decimal("0.01") if price >= 1 else Decimal("0.0001")
    table, top = (
        (KR_ETF_TICKS, KR_ETF_TOP_TICK)
        if inst.kind is Kind.ETF
        else (KR_STOCK_TICKS, KR_STOCK_TOP_TICK)
    )
    for below, tick in table:
        if price < below:
            return tick
    return top


def on_tick(inst: Instrument, price: Decimal, *, up: bool) -> Decimal:
    """The nearest valid price at or above (up) or at or below `price`. A price that crosses a
    tier boundary is checked against the tick of where it lands."""
    tick = tick_size(inst, price)
    rounding = ROUND_CEILING if up else ROUND_FLOOR
    out = (price / tick).to_integral_value(rounding=rounding) * tick
    landed = tick_size(inst, out)
    if landed != tick:
        out = (out / landed).to_integral_value(rounding=rounding) * landed
    return out


def limit_price(inst: Instrument, side: Side, reference: Decimal, slippage: Decimal) -> Decimal:
    """A buy pays at most `reference x (1 + slippage)`, a sell takes at least
    `reference x (1 - slippage)`, each on the tick (never past the cap)."""
    if reference <= 0:
        raise ValueError("reference price must be positive")
    if side is Side.BUY:
        return on_tick(inst, reference * (1 + slippage), up=False)
    return on_tick(inst, reference * (1 - slippage), up=True)


def fee_rate(cfg: Config, commissions: Mapping[str, Decimal], inst: Instrument) -> Decimal:
    """The commission a live order is sized with: Toss's rate for the market (read once a day,
    broker_status) or the configured one, whichever is higher (a share too many is refused)."""
    return max(commissions.get(inst.market.value, Decimal(0)), cfg.fees.rate_for(inst.currency))


def buy_unit(inst: Instrument, reference: Decimal, slippage: Decimal, rate: Decimal) -> Decimal:
    """The most one share of a live buy takes: its limit price over `reference` plus the fee at
    that price. The send divides the cash by it (jobs/live_tasks.py), and the live plan sizes
    its buys with it at the plan price (domain/planner.py PlanItem.buy_unit)."""
    return limit_price(inst, Side.BUY, reference, slippage) * (1 + rate)


# ── the executor ─────────────────────────────────────────────────────────────────────────


class TossExecutor:
    """Reads broker_orders; never sends. See the module docstring."""

    name = "toss"

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def trade(self, req: TradeRequest) -> Outcome:
        row = live_repo.get_broker_order(self.conn, req.order_id)
        if row is None:
            if req.deadline_passed:
                return Failed(FailureReason.OTHER, "not sent before the session closed")
            return Waiting("not sent yet")
        if row.state in live_repo.OPEN_STATES:
            # Never fail an order whose end at the broker is unknown: a retry would send the
            # same shares again.
            return Waiting(f"{row.state} at the broker")
        if row.state == "not-sent":
            code = row.error_code or "other"
            if code == NOTHING_TO_BUY:
                return NotTraded(NOTHING_TO_BUY, row.error_detail or "")
            if code == "order-hours-closed" and not req.deadline_passed:
                return Waiting("order hours closed; sent again when they open")
            if code in ("no-quote",):
                return Failed(FailureReason.NO_QUOTE, f"not sent: {code}")
            if code in RETRYABLE_CODES:
                return Failed(FailureReason.OTHER, f"not sent: {code} {row.error_detail or ''}")
            return Failed(FailureReason.BROKER_REJECTED, f"not sent: {code}")
        if row.state == "rejected":
            code = row.error_code or "rejected"
            if code in RETRYABLE_CODES:
                return Failed(FailureReason.OTHER, f"{code}: {row.error_detail or ''}")
            return Failed(FailureReason.BROKER_REJECTED, f"{code}: {row.error_detail or ''}")
        return _done(row)

    def fx(self, req: FxRequest) -> Outcome:
        # Toss converts no currency through the API (PHASE3.md 1.1), so a live plan never has a
        # conversion (D47, engine/check.py refuses one). One here would wait forever: it fails,
        # and after its retry it is a person's.
        return Failed(FailureReason.OTHER, "live plans never convert (D47)")


def _done(row: live_repo.BrokerOrderRow) -> Outcome:
    filled = row.filled_qty or Decimal(0)
    if filled > 0:
        if filled != filled.to_integral_value():
            return Failed(FailureReason.BROKER_REJECTED, f"fractional fill {filled}")
        qty = int(filled)
        gross = row.filled_amount
        if gross is None and row.avg_price is not None:
            gross = row.avg_price * qty
        if gross is None or gross <= 0:
            return Failed(FailureReason.OTHER, "filled without an amount")
        price = (gross / qty).quantize(PRICE_PLACES, rounding=ROUND_HALF_UP)
        return TradeFilled(
            qty,
            price,
            gross,
            row.fee,
            f"toss:{row.broker_order_id}",
            filled_at=row.filled_at,
        )
    if row.status == "REJECTED":
        return Failed(FailureReason.BROKER_REJECTED, "rejected by the broker")
    return Failed(FailureReason.OTHER, f"{(row.status or 'closed').lower()} without a fill")


def fill_of(row: live_repo.BrokerOrderRow) -> TradeFilled | None:
    """The fill a finished broker order carries, if any (for fills booked outside the runner)."""
    outcome = _done(row) if row.state == "done" else None
    return outcome if isinstance(outcome, TradeFilled) else None
