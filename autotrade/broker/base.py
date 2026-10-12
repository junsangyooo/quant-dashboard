"""Executors: one engine, two executors (paper, and Toss for the live ledger).

An executor turns one order into an outcome: filled, still waiting for its price, or failed.
It never touches the ledger; the stage runner applies outcomes.

Live orders need both AUTOTRADE_LIVE_ORDERS=1 and the stored mode 'live' (ops notes 안전). The
Toss executor (autotrade/broker/toss.py) only reads what the tick's Toss sync recorded; sending
happens there, behind both keys (autotrade/PHASE3.md 2.3).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol

from autotrade.domain.instruments import Instrument
from autotrade.domain.planner import FxDirection, Side

LIVE_ENV = "AUTOTRADE_LIVE_ORDERS"


class FailureReason(str, Enum):
    NO_QUOTE = "no-quote"  # price or rate unavailable ('시세 응답 없음')
    BROKER_REJECTED = "broker-rejected"  # never retried (인계 11)
    OTHER = "other"


@dataclass(frozen=True)
class TradeRequest:
    order_id: int
    instrument: Instrument
    side: Side
    qty: int
    session_date: date  # exchange-local session date
    due_at: datetime
    available_cash: Decimal  # in the instrument's currency, for buys
    held_qty: int  # for sells
    fetch_error: str | None  # this job could not download the price
    deadline_passed: bool  # the session is over; waiting longer will not help


@dataclass(frozen=True)
class FxRequest:
    order_id: int
    direction: FxDirection
    amount: Decimal  # in the source currency
    due_at: datetime
    available: Decimal  # source currency
    fetch_error: str | None
    deadline_passed: bool


@dataclass(frozen=True)
class TradeFilled:
    qty: int
    price: Decimal
    gross: Decimal
    fee: Decimal
    price_source: str
    filled_at: datetime | None = None  # live: the broker's time (paper: the stage time)


@dataclass(frozen=True)
class FxFilled:
    from_amount: Decimal
    to_amount: Decimal
    rate: Decimal
    price_source: str
    filled_at: datetime | None = None


@dataclass(frozen=True)
class Waiting:
    detail: str


@dataclass(frozen=True)
class Failed:
    reason: FailureReason
    detail: str

    @property
    def retryable(self) -> bool:
        return self.reason is not FailureReason.BROKER_REJECTED


Outcome = TradeFilled | FxFilled | Waiting | Failed


class Executor(Protocol):
    name: str  # 'paper' | 'toss'

    def trade(self, req: TradeRequest) -> Outcome: ...

    def fx(self, req: FxRequest) -> Outcome: ...


class LiveOrdersBlockedError(PermissionError):
    pass


def live_orders_allowed(mode: str, env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return mode == "live" and source.get(LIVE_ENV) == "1"


def executor_for(ledger_id: str, paper: Executor, live: Executor | None = None) -> Executor:
    """The paper ledger's executor, or the live ledger's (Toss)."""
    if ledger_id == "paper":
        return paper
    if ledger_id == "live" and live is not None:
        return live
    raise LiveOrdersBlockedError(f"ledger {ledger_id!r} has no executor")


SIDE_FOR_STAGE: Mapping[str, Side] = {"sell": Side.SELL, "buy": Side.BUY, "fx": Side.FX}
