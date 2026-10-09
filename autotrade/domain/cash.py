"""What each won and dollar of cash is for (pending_cash purposes).

Every unit of cash is in exactly one part:

- withdraw_wait: proceeds the owner sold by hand and will withdraw (live only, 인계 5). Recorded
  as such; never invested, but counted in the total.
- buy_wait: cash that pending orders will spend. While a currency has pending buys (or a pending
  conversion out of it), all of that currency's free cash is attributed to them pro rata, so the
  dollars after the 09:10 conversion show as '달러 현금 · 매수 대기' in full (§1.1: $126.96,
  §4: $3,568.24) and count toward the instrument they will buy (인계 3).
- new: cash that arrived since the last check (start amount, deposits, dividends); the next
  check invests it per target ('첫 확인 때 매수').
- sub_share: the rest — leftovers below one share ('1주 미만 대기'). It belongs to no rule.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_FLOOR, Decimal
from enum import Enum

from autotrade.domain.instruments import Currency
from autotrade.domain.money import CENT, WON, ZERO


class Purpose(str, Enum):
    BUY_WAIT = "buy_wait"
    SUB_SHARE = "sub_share"
    WITHDRAW_WAIT = "withdraw_wait"
    NEW = "new"


@dataclass(frozen=True)
class CashPart:
    currency: Currency
    purpose: Purpose
    amount: Decimal
    instrument_id: str | None = None  # buy_wait only
    until: date | None = None  # withdraw_wait only


@dataclass(frozen=True)
class WithdrawWait:
    currency: Currency
    amount: Decimal
    until: date


@dataclass(frozen=True)
class Claim:
    """A pending order that will spend cash of one currency for some instruments."""

    currency: Currency
    amount: Decimal
    split: Mapping[str, Decimal]  # instrument -> share of this claim (weights, any scale)


def _unit(currency: Currency) -> Decimal:
    return WON if currency is Currency.KRW else CENT


def split_pro_rata(
    total: Decimal, weights: Sequence[tuple[str, Decimal]], unit: Decimal
) -> dict[str, Decimal]:
    """Split total by weights on the unit grid; the last key takes the remainder (exact sum)."""
    keys = [k for k, _ in weights]
    weight_sum = sum((w for _, w in weights), ZERO)
    out: dict[str, Decimal] = {}
    if not keys:
        return out
    if weight_sum <= 0:
        out[keys[-1]] = total
        return out
    used = ZERO
    for key, w in weights[:-1]:
        share = (total * w / weight_sum).quantize(unit, rounding=ROUND_FLOOR)
        out[key] = out.get(key, ZERO) + share
        used += share
    out[keys[-1]] = out.get(keys[-1], ZERO) + (total - used)
    return out


def partition(
    cash: Mapping[Currency, Decimal],
    withdraw_waits: Iterable[WithdrawWait],
    claims: Iterable[Claim],
    new_cash: Mapping[Currency, Decimal],
) -> list[CashPart]:
    waits = list(withdraw_waits)
    claim_list = list(claims)
    parts: list[CashPart] = []
    for currency in Currency:
        balance = cash.get(currency, ZERO)
        reserved = ZERO
        for w in waits:
            if w.currency is currency and w.amount > 0:
                take = min(w.amount, balance - reserved)
                if take > 0:
                    parts.append(CashPart(currency, Purpose.WITHDRAW_WAIT, take, until=w.until))
                    reserved += take
        free = balance - reserved
        if free <= 0:
            continue
        mine = [c for c in claim_list if c.currency is currency and c.amount > 0]
        if mine:
            per_instrument: dict[str, Decimal] = {}
            for c in mine:
                weight_sum = sum(c.split.values(), ZERO)
                for iid, weight in c.split.items():
                    share = c.amount * weight / weight_sum if weight_sum > 0 else ZERO
                    per_instrument[iid] = per_instrument.get(iid, ZERO) + share
            shares = split_pro_rata(free, sorted(per_instrument.items()), _unit(currency))
            for iid, amount in shares.items():
                if amount > 0:
                    parts.append(CashPart(currency, Purpose.BUY_WAIT, amount, instrument_id=iid))
            continue
        new = min(free, max(ZERO, new_cash.get(currency, ZERO)))
        if new > 0:
            parts.append(CashPart(currency, Purpose.NEW, new))
        if free - new > 0:
            parts.append(CashPart(currency, Purpose.SUB_SHARE, free - new))
    return parts


def buy_wait_by_instrument(parts: Iterable[CashPart]) -> dict[str, dict[Currency, Decimal]]:
    out: dict[str, dict[Currency, Decimal]] = {}
    for p in parts:
        if p.purpose is Purpose.BUY_WAIT and p.instrument_id is not None:
            slot = out.setdefault(p.instrument_id, {})
            slot[p.currency] = slot.get(p.currency, ZERO) + p.amount
    return out


def amount_by_purpose(parts: Iterable[CashPart], purpose: Purpose) -> dict[Currency, Decimal]:
    out: dict[Currency, Decimal] = {}
    for p in parts:
        if p.purpose is purpose:
            out[p.currency] = out.get(p.currency, ZERO) + p.amount
    return out
