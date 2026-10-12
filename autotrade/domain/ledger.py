"""Ledger state and how fills and cash flows change it (pure functions).

The same functions run in two places: the engine applies each fill as it happens, and the rebuild
folds every recorded event and fill from scratch. Both must agree to the won (tests).

Positions keep their cost in the instrument's currency (fees included, so the average price is
'평균 단가' of 예시-값표 §1.1: (2,906.90 + 126.13) / 46 = $65.94) and in won
('원화 취득원가'), converted at the rate of the conversion that paid for the buy.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import Enum

from autotrade.domain.instruments import Currency
from autotrade.domain.money import ZERO, round_won, usd_in_krw
from autotrade.domain.planner import FxDirection, Side


class LedgerError(ValueError):
    """A change that would make the ledger impossible (negative cash, overselling)."""


class CashFlowKind(str, Enum):
    START = "start"
    DEPOSIT = "deposit"
    WITHDRAWAL = "withdrawal"
    DIVIDEND = "dividend"


@dataclass(frozen=True)
class Position:
    instrument_id: str
    currency: Currency
    qty: int
    cost_native: Decimal  # total cost incl. fees, instrument currency (exact)
    cost_krw: Decimal  # won acquisition cost (whole won)

    @property
    def avg_price(self) -> Decimal:
        return self.cost_native / self.qty if self.qty else ZERO


@dataclass(frozen=True)
class LedgerState:
    cash: Mapping[Currency, Decimal] = field(
        default_factory=lambda: {Currency.KRW: ZERO, Currency.USD: ZERO}
    )
    positions: Mapping[str, Position] = field(default_factory=dict)
    realized_krw: Decimal = ZERO
    fees_krw: Decimal = ZERO
    contributions_krw: Decimal = ZERO  # start + deposits - withdrawals
    income_krw: Decimal = ZERO  # dividends (after tax)

    def cash_of(self, currency: Currency) -> Decimal:
        return self.cash.get(currency, ZERO)

    def qty_of(self, instrument_id: str) -> int:
        pos = self.positions.get(instrument_id)
        return pos.qty if pos else 0


@dataclass(frozen=True)
class TradeFill:
    instrument_id: str
    currency: Currency
    side: Side  # BUY or SELL
    qty: int
    price: Decimal
    fee: Decimal  # instrument currency
    krw_rate: Decimal | None = None  # US trades: rate used for the won cost basis
    # The broker's total for the fill (live). Its average price times the quantity need not be
    # exact (several partial fills), and the account's cash moves by this total.
    gross_amount: Decimal | None = None

    @property
    def gross(self) -> Decimal:
        return self.price * self.qty if self.gross_amount is None else self.gross_amount

    def to_krw(self, amount: Decimal) -> Decimal:
        if self.currency is Currency.KRW:
            return amount
        if self.krw_rate is None:
            raise LedgerError(f"{self.instrument_id}: dollar trade needs krw_rate")
        return usd_in_krw(amount, self.krw_rate)


@dataclass(frozen=True)
class FxFill:
    direction: FxDirection
    from_amount: Decimal
    to_amount: Decimal
    rate: Decimal


def _with_cash(state: LedgerState, currency: Currency, delta: Decimal) -> dict[Currency, Decimal]:
    cash = dict(state.cash)
    cash[currency] = cash.get(currency, ZERO) + delta
    if cash[currency] < 0:
        raise LedgerError(f"{currency.value} cash would go negative: {cash[currency]}")
    return cash


def opening_state(
    cash: Mapping[Currency, Decimal],
    positions: Mapping[str, Position],
    contributions_krw: Decimal,
) -> LedgerState:
    """A ledger that starts from an account as it is (the live ledger, PHASE3.md 2.6): its cash
    and the positions it adopts. What it holds is its contribution, so it starts at no gain."""
    if any(v < 0 for v in cash.values()):
        raise LedgerError("opening cash must not be negative")
    if any(p.qty <= 0 for p in positions.values()):
        raise LedgerError("opening positions must hold shares")
    if contributions_krw <= 0:
        raise LedgerError("an opening must bring something in")
    full = {c: cash.get(c, ZERO) for c in Currency}
    return LedgerState(cash=full, positions=dict(positions), contributions_krw=contributions_krw)


def apply_cash_flow(
    state: LedgerState,
    kind: CashFlowKind,
    amount: Decimal,
    currency: Currency = Currency.KRW,
    krw_rate: Decimal | None = None,
) -> LedgerState:
    if amount <= 0:
        raise LedgerError(f"{kind.value}: amount must be positive")
    in_krw = amount
    if currency is Currency.USD:
        if krw_rate is None:
            raise LedgerError("dollar cash flow needs krw_rate")
        in_krw = usd_in_krw(amount, krw_rate)
    if kind is CashFlowKind.WITHDRAWAL:
        return replace(
            state,
            cash=_with_cash(state, currency, -amount),
            contributions_krw=state.contributions_krw - in_krw,
        )
    if kind is CashFlowKind.DIVIDEND:
        return replace(
            state,
            cash=_with_cash(state, currency, amount),
            income_krw=state.income_krw + in_krw,
        )
    return replace(
        state,
        cash=_with_cash(state, currency, amount),
        contributions_krw=state.contributions_krw + in_krw,
    )


def apply_trade(state: LedgerState, fill: TradeFill) -> LedgerState:
    if fill.qty <= 0:
        raise LedgerError("trade quantity must be positive")
    gross = fill.gross
    fee_krw = fill.to_krw(fill.fee)
    positions = dict(state.positions)
    current = positions.get(fill.instrument_id)
    if fill.side is Side.BUY:
        cost = gross + fill.fee
        cash = _with_cash(state, fill.currency, -cost)
        base = current or Position(fill.instrument_id, fill.currency, 0, ZERO, ZERO)
        positions[fill.instrument_id] = Position(
            fill.instrument_id,
            fill.currency,
            base.qty + fill.qty,
            base.cost_native + cost,
            base.cost_krw + fill.to_krw(cost),
        )
        return replace(state, cash=cash, positions=positions, fees_krw=state.fees_krw + fee_krw)
    if fill.side is not Side.SELL:
        raise LedgerError(f"not a trade side: {fill.side}")
    if current is None or current.qty < fill.qty:
        raise LedgerError(f"{fill.instrument_id}: selling {fill.qty} of {current and current.qty}")
    proceeds = gross - fill.fee
    removed_native = current.cost_native * fill.qty / current.qty
    removed_krw = round_won(current.cost_krw * fill.qty / current.qty)
    remaining = current.qty - fill.qty
    if remaining == 0:
        del positions[fill.instrument_id]
    else:
        positions[fill.instrument_id] = Position(
            fill.instrument_id,
            fill.currency,
            remaining,
            current.cost_native - removed_native,
            current.cost_krw - removed_krw,
        )
    return replace(
        state,
        cash=_with_cash(state, fill.currency, proceeds),
        positions=positions,
        realized_krw=state.realized_krw + fill.to_krw(proceeds) - removed_krw,
        fees_krw=state.fees_krw + fee_krw,
    )


def apply_fx(state: LedgerState, fill: FxFill) -> LedgerState:
    if fill.from_amount <= 0 or fill.to_amount <= 0:
        raise LedgerError("conversion amounts must be positive")
    source, target = fill.direction.source, fill.direction.target
    after_debit = replace(state, cash=_with_cash(state, source, -fill.from_amount))
    return replace(after_debit, cash=_with_cash(after_debit, target, fill.to_amount))


def same_to_the_won(a: LedgerState, b: LedgerState) -> list[str]:
    """Differences between two states at the precision that matters (empty = same)."""
    problems: list[str] = []
    for currency in Currency:
        if a.cash_of(currency) != b.cash_of(currency):
            problems.append(
                f"cash {currency.value}: {a.cash_of(currency)} != {b.cash_of(currency)}"
            )
    ids = set(a.positions) | set(b.positions)
    for iid in sorted(ids):
        pa, pb = a.positions.get(iid), b.positions.get(iid)
        if pa is None or pb is None:
            problems.append(f"{iid}: present in only one state")
            continue
        if pa.qty != pb.qty:
            problems.append(f"{iid} qty: {pa.qty} != {pb.qty}")
        if round_won(pa.cost_krw) != round_won(pb.cost_krw):
            problems.append(f"{iid} cost_krw: {pa.cost_krw} != {pb.cost_krw}")
        if pa.cost_native != pb.cost_native:
            problems.append(f"{iid} cost_native: {pa.cost_native} != {pb.cost_native}")
    return problems
