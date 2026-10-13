"""The ledger's two accounts, each in its own currency (CONTRACT.md HomeResponse.accounts).

The owner, 2026-10-12: '국장과 미장은 엄연히 다른 화폐단위니까' — the home screen shows 전체 in
won and each account in its own money.

What an account is
- A ledger splits by currency. 한국 계좌 (KRW): Korean holdings at won prices and won cash.
  미국 계좌 (USD): US holdings at dollar prices and dollar cash. A holding belongs to the account
  of its currency.

Money into an account ('net in', in its currency)
- The start amount and deposits come in, withdrawals go out, each in the account of its currency
  (all won today, so all 한국 계좌).
- A conversion moves money between the two accounts: won → dollars takes the won it cost out of
  한국 계좌 and puts the dollars it bought into 미국 계좌; dollars → won the other way. It is a
  transfer, never a gain or a loss of either account.
- The live ledger (engine/live.py) records the same way: what the reconciliation finds coming in
  or going out is a deposit or withdrawal event in its own currency, dated when it arrived; a
  conversion a plan asked for (made by the owner in the Toss app) is the fx fill of its fx order.
  Two cases have no paper twin: a start or adopt-broker that moved both currencies carries each
  one's amount ('by_currency'), and the owner's conversion is two events (out of one currency,
  into the other) marked 'conversion', read here as a transfer. Live plans never convert (D47):
  every live conversion is the owner's, made in the Toss app.
- Dividends (after tax), fees and taxes are not money in: they stay in the value of the account of
  their currency, so they are that account's P&L.
- A fill counts from the moment the ledger took it: its order's execution time, which a snapshot
  taken at or after it includes. (A stage that runs late is stamped with its due time, so the
  stamp alone could fall before a snapshot that did not include the fill.)

P&L of an account = value − net in, in its currency. An account no money ever reached has no P&L
(None: the screen shows it empty).

Its % is the P&L over the money the account held on average: each flow weighted by the share of
the time it was in the account (the modified Dietz return, `dietz`). P&L ÷ net in bent with every
conversion: in the paper world (10/7) 한국 계좌 showed +14.55% while its only holding was up 13.3%,
because the won it had sent to 미국 계좌 no longer counted, and monthly rebalancing would drive the
base to zero. A time-weighted return was set aside: its sign can differ from the amount's, and a
dividend paid into an account the rule has just emptied would make it explode. The same return,
from a period's start, is the period %; each point of the 수익률 line is the return up to it.

The ledger's won P&L splits exactly into three parts (all whole won):

    ledger P&L = 한국 P&L + 미국 P&L in won + 환율 효과
    미국 P&L in won = round_half_up(미국 P&L in dollars × rate)      rate = basis.fxRate
    환율 효과 = ledger P&L − 한국 P&L − 미국 P&L in won                (the remainder)

The remainder is what the rate did to the dollars the conversions bought — their value at today's
rate minus the won they cost (net in × rate − net won sent) — plus the rounding of the dollar rows
to the won (each row rounds once, CONTRACT.md 표시 반올림). Defining it as the remainder makes the
three parts add up to the won by construction (tests/autotrade/api/test_api_accounts.py).

'손대지 않았을 때' stays a whole-ledger comparison and has no per-account line: the rule works by
moving money between the two accounts, so on one account alone the gap to an untouched half would
mostly be the money the rule moved, not how well it did (the series carry baseline None).

The 30-trading-day rule is each account's own record: an account younger than 30 snapshots shows
its whole record with no period chips, as the ledger does.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from functools import cached_property
from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.context import CompRow, LedgerContext, event_kind
from autotrade.api.views.refs import instrument as instrument_json
from autotrade.api.views.series import MARKER_KINDS, MIN_RECORD_DAYS, period_start
from autotrade.db import repo
from autotrade.db.models import EventRow, FillRow, OrderRow, SnapshotRow
from autotrade.domain.instruments import Currency
from autotrade.domain.money import ZERO, round_won
from autotrade.domain.planner import FxDirection
from autotrade.engine.common import CONVERSION
from autotrade.rules.discovery import RULE_ID as AI_RULE

ACCOUNTS: tuple[tuple[str, Currency], ...] = (("kr", Currency.KRW), ("us", Currency.USD))
CURRENCY_OF: dict[str, Currency] = dict(ACCOUNTS)
COUNTRY = {Currency.KRW: "KR", Currency.USD: "US"}
HOME_PERIODS = ("1m", "3m", "1y", "all")
# Markers about the whole ledger go on both accounts' lines; a plan's markers (rebalance and its
# states) on the accounts its orders touched; money in or out and dividends only on the line of
# their currency.
LEDGER_MARKERS = ("start", "live-on", "live-off")
PLAN_MARKERS = ("rebalance", "partial-failed", "in-progress")
STALE_SERIES = {Currency.KRW: "kr-quotes", Currency.USD: "us-quotes"}


@dataclass(frozen=True)
class Flow:
    """Money that moved into (amount > 0) or out of the account of `currency`."""

    applied_at: datetime
    currency: Currency
    amount: Decimal
    kind: str  # 'start' | 'deposit' | 'withdrawal' | 'transfer'


@dataclass(frozen=True)
class Point:
    """One account in one snapshot: its value and the money that had come in by then."""

    snapshot: SnapshotRow
    value: Decimal
    net_in: Decimal


def start_split(ev: EventRow) -> dict[Currency, Decimal] | None:
    """The amount per currency of a live start or adopt-broker event that moved both (payload
    'by_currency', signed: what came in), else None."""
    split = ev.payload.get("by_currency")
    if not isinstance(split, dict):
        return None
    return {Currency(str(k)): Decimal(str(v)) for k, v in split.items()}


def _in_or_out(amount: Decimal) -> str:
    return "deposit" if amount >= 0 else "withdrawal"


def amount_of(currency: Currency, x: Decimal) -> int | float:
    """A figure in the account's unit: whole won, or dollars to the cent."""
    return fmt.krw(x) if currency is Currency.KRW else fmt.usd(x)


def dietz(
    start_value: Decimal,
    end_value: Decimal,
    flows: Iterable[Flow],
    start_at: datetime,
    end_at: datetime,
) -> Decimal | None:
    """The modified Dietz return of start_at → end_at: the gain (end − start − flows) over the
    money held on average, the start value plus each flow weighted by the share of the span left
    after it. None when that average is not positive (the account held nothing to earn on)."""
    span = Decimal(int((end_at - start_at).total_seconds()))
    moved = held = ZERO
    for f in flows:
        moved += f.amount
        left = Decimal(int((end_at - f.applied_at).total_seconds()))
        held += f.amount * (min(max(left / span, ZERO), Decimal(1)) if span > 0 else Decimal(1))
    held += start_value
    if held <= 0:
        return None
    return (end_value - start_value - moved) / held


def snapshot_value(snap: SnapshotRow, currency: Currency) -> Decimal:
    """One account's value in a stored snapshot, in its currency."""
    total = snap.cash_krw if currency is Currency.KRW else snap.cash_usd
    for pos in snap.positions:
        if pos.get("currency") != currency.value:
            continue
        if currency is Currency.KRW:
            total += Decimal(str(pos.get("value_krw")))
        else:
            total += Decimal(str(pos.get("price"))) * int(pos.get("qty") or 0)
    return total


class Accounts:
    """한국 계좌 and 미국 계좌 of one ledger at one moment (built once per request)."""

    def __init__(self, ctx: LedgerContext) -> None:
        self.ctx = ctx

    # ── what came in, and when the ledger took it ──────────────────────────────────────────

    @cached_property
    def orders(self) -> list[OrderRow]:
        return repo.orders_of_ledger(self.ctx.conn, self.ctx.ledger_id)

    @cached_property
    def fills(self) -> list[tuple[datetime, FillRow]]:
        """(applied at, fill) of the ledger's fills taken by now."""
        ctx = self.ctx
        executed = {o.order_id: o.executed_at for o in self.orders}
        out: list[tuple[datetime, FillRow]] = []
        for f in repo.fills_of_ledger(ctx.conn, ctx.ledger_id):
            applied = executed.get(f.order_id) or f.filled_at
            if applied <= ctx.now:
                out.append((applied, f))
        return out

    @cached_property
    def flows(self) -> list[Flow]:
        out: list[Flow] = []
        for ev in self.ctx.events:
            if ev.amount is None or ev.kind not in ("start", "deposit", "withdrawal"):
                continue
            split = start_split(ev)
            if split is not None:
                # A live start or adopt-broker that moved both currencies carries each
                # currency's own amount, signed (engine/live.py).
                for currency, amount in split.items():
                    kind = ev.kind if ev.kind == "start" else _in_or_out(amount)
                    out.append(Flow(ev.occurred_at, currency, amount, kind))
                continue
            sign = -1 if ev.kind == "withdrawal" else 1
            # A conversion no plan asked for (the owner's, in the Toss app) is two events, one
            # per currency: a transfer between the accounts like an fx fill, not money in or out.
            kind = "transfer" if ev.payload.get("reason") == CONVERSION else ev.kind
            out.append(Flow(ev.occurred_at, ev.currency or Currency.KRW, sign * ev.amount, kind))
        for applied, f in self.fills:
            if f.kind != "fx" or f.fx_direction is None or f.received is None:
                continue
            direction = FxDirection(f.fx_direction)
            out.append(Flow(applied, direction.source, -f.gross, "transfer"))
            out.append(Flow(applied, direction.target, f.received, "transfer"))
        return sorted(out, key=lambda f: f.applied_at)

    def net_in(self, currency: Currency, at: datetime | None = None) -> Decimal:
        """Money into the account by `at` (everything so far when None)."""
        return sum(
            (
                f.amount
                for f in self.flows
                if f.currency is currency and (at is None or f.applied_at <= at)
            ),
            ZERO,
        )

    def flows_of(
        self, currency: Currency, until: datetime, after: datetime | None = None
    ) -> list[Flow]:
        """The account's flows in (after, until], oldest first."""
        return [
            f
            for f in self.flows
            if f.currency is currency
            and f.applied_at <= until
            and (after is None or f.applied_at > after)
        ]

    def funded(self, currency: Currency) -> bool:
        """Money has reached the account, or it holds something (else it is empty: no P&L)."""
        if any(f.currency is currency and f.amount > 0 for f in self.flows):
            return True
        values = self.values
        return values is not None and values[currency] != 0

    # ── value now ──────────────────────────────────────────────────────────────────────────

    @cached_property
    def values(self) -> dict[Currency, Decimal] | None:
        """Each account's value now, in its currency: the valuation the hero shows ('16:00 기준'),
        else the last snapshot when the stored prices cannot value the ledger now."""
        val = self.ctx.valuation
        if val is not None:
            kr, us = val.cash_krw, val.cash_usd
            for p in val.positions:
                if p.instrument.currency is Currency.KRW:
                    kr += p.value_krw
                else:
                    us += p.price * p.qty
            return {Currency.KRW: kr, Currency.USD: us}
        if self.ctx.snapshots:
            last = self.ctx.snapshots[-1]
            return {c: snapshot_value(last, c) for c in Currency}
        return None

    @cached_property
    def at(self) -> datetime:
        """The moment `values` are of: now, or the last snapshot's when they come from it. What
        came in after that snapshot is not in its values, so P&L and returns stop there too (else
        a conversion since would show as a gain in one account and a loss in the other)."""
        return self.ctx.as_of

    @property
    def rate(self) -> Decimal:
        """The rate that values dollars in won here (the hero's basis)."""
        if self.ctx.valuation is not None:
            return self.ctx.fx_rate
        return self.ctx.snapshots[-1].fx_rate if self.ctx.snapshots else ZERO

    def pnl(self, currency: Currency) -> Decimal | None:
        values = self.values
        if values is None or not self.funded(currency):
            return None
        return values[currency] - self.net_in(currency, self.at)

    def pct(self, currency: Currency) -> float | None:
        """The account's return since money first reached it (`dietz`); None while it is empty or
        held nothing on average."""
        values = self.values
        flows = self.flows_of(currency, self.at)
        if values is None or not flows or not self.funded(currency):
            return None
        r = dietz(ZERO, values[currency], flows, flows[0].applied_at, self.at)
        return None if r is None else fmt.ret2(r)

    def split(self, ledger_pnl: int) -> dict[str, int]:
        """The ledger's won P&L in three parts that add up to it: 한국, 미국 in won, 환율 효과."""
        kr = fmt.krw(self.pnl(Currency.KRW) or ZERO)
        us = fmt.krw(round_won((self.pnl(Currency.USD) or ZERO) * self.rate))
        return {"kr": kr, "us": us, "fx": ledger_pnl - kr - us}

    # ── one account for the screen ─────────────────────────────────────────────────────────

    def account(self, account_id: str, period: str | None) -> dict[str, Any]:
        currency = CURRENCY_OF[account_id]
        values = self.values or dict.fromkeys(Currency, ZERO)
        pnl = self.pnl(currency)
        return {
            "id": account_id,
            "currency": currency.value,
            "total": amount_of(currency, values[currency]),
            "pnl": None
            if pnl is None
            else {"amount": amount_of(currency, pnl), "pct": self.pct(currency)},
            # An account's money moves with its own market only: dollars stay dollars whatever
            # the rate (the rate shows in 전체). Values from the last snapshot are stale too.
            "stale": STALE_SERIES[currency] in self.ctx.stale_series or self.ctx.from_snapshot,
            "trend": self.trend(currency, period),
            "composition": self.composition(currency),
        }

    def points(self, currency: Currency) -> list[Point]:
        """The account in each snapshot, from the first one it had money."""
        out: list[Point] = []
        for snap in self.ctx.snapshots:
            value = snapshot_value(snap, currency)
            net_in = self.net_in(currency, snap.valued_at)
            if not out and value == 0 and net_in == 0:
                continue
            out.append(Point(snap, value, net_in))
        return out

    def returns(self, currency: Currency, points: list[Point]) -> list[float]:
        """The account's return from when money first reached it up to each point (`dietz`). A
        point where it held nothing on average keeps the return before it (0.0 at first)."""
        out: list[float] = []
        last = 0.0
        for p in points:
            at = p.snapshot.valued_at
            flows = self.flows_of(currency, at)
            r = dietz(ZERO, p.value, flows, flows[0].applied_at, at) if flows else None
            if r is not None:
                last = fmt.ret2(r)
            out.append(last)
        return out

    def _period(self, points: list[Point], period: str | None, default: str) -> tuple[bool, str]:
        long = len(points) >= MIN_RECORD_DAYS
        return long, (period if (long and period in HOME_PERIODS) else (default if long else "all"))

    def trend(self, currency: Currency, period: str | None) -> dict[str, Any]:
        ctx = self.ctx
        points = self.points(currency)
        long, chosen = self._period(points, period, "3m")
        first = points[0].snapshot.date if points else ctx.start_date
        since = period_start(chosen, ctx.today, first)
        shown = [p for p in points if p.snapshot.date >= since]
        empty = "first-day" if len(points) <= 1 and self.funded(currency) else None
        period_pnl = None
        values = self.values
        if long and chosen != "all" and values is not None:
            before = [p for p in points if p.snapshot.date <= since]
            if before and before[-1].value > 0:
                start = before[-1]
                came = self.flows_of(currency, self.at, after=start.snapshot.valued_at)
                amount = values[currency] - start.value - sum((f.amount for f in came), ZERO)
                r = dietz(start.value, values[currency], came, start.snapshot.valued_at, self.at)
                if r is not None:
                    period_pnl = {"amount": amount_of(currency, amount), "pct": fmt.ret2(r)}
        return {
            "periods": list(HOME_PERIODS) if long else None,
            "period": chosen,
            "periodPnl": period_pnl,
            "series": [
                {
                    "date": fmt.day(p.snapshot.date),
                    "value": amount_of(currency, p.value),
                    "ret": ret,
                    "baseline": None,
                    "baselineRet": None,
                    # 들어온 돈 by that day. A conversion moves the value and this line together,
                    # so the gap between them is the account's P&L.
                    "netIn": amount_of(currency, p.net_in),
                }
                for p, ret in zip(shown, self.returns(currency, shown), strict=True)
            ],
            "events": self.markers(currency, shown[0].snapshot.date if shown else since),
            "empty": empty,
        }

    @cached_property
    def plan_currencies(self) -> dict[int, set[Currency]]:
        """The accounts each plan's orders touched: a trade's currency, both for a conversion."""
        out: dict[int, set[Currency]] = {}
        for order in self.orders:
            touched = set(Currency) if order.side == "fx" else {order.currency}
            out.setdefault(order.plan_id, set()).update(touched)
        return out

    def markers(self, currency: Currency, since: date) -> list[dict[str, Any]]:
        """One marker per day, like the ledger's (CONTRACT Trend.events), for this account."""
        by_date: dict[str, list[str]] = {}
        for ev in self.ctx.events:
            kind = event_kind(ev)
            if ev.event_date < since or kind not in MARKER_KINDS:
                continue
            if kind in PLAN_MARKERS:
                touched = None if ev.plan_id is None else self.plan_currencies.get(ev.plan_id)
                if touched and currency not in touched:
                    continue
            elif kind not in LEDGER_MARKERS and (ev.currency or Currency.KRW) is not currency:
                continue
            by_date.setdefault(fmt.day(ev.event_date), []).append(kind)
        out: list[dict[str, Any]] = []
        for d in sorted(by_date):
            kinds = by_date[d]
            marker: dict[str, Any] = {"date": d, "kind": kinds[0], "kinds": kinds}
            if len(kinds) > 1:
                marker["count"] = len(kinds)
            out.append(marker)
        return out

    # ── 구성 of one account ─────────────────────────────────────────────────────────────────

    def composition(self, currency: Currency) -> dict[str, Any]:
        """The account's rows, valued in its currency; % of the account (adds up to 100.0).
        Targets are the ledger's, so the account's groups carry none."""
        ctx = self.ctx
        rows = [r for r in ctx.composition.rows if (r.currency or Currency.KRW) is currency]
        amounts = [self._row_amount(r, currency) for r in rows]
        pcts = fmt.allocate_pct1(amounts)
        shown = [
            (row, self._row_json(row, currency, amount, pct))
            for row, amount, pct in zip(rows, amounts, pcts, strict=True)
        ]
        groups: list[dict[str, Any]] = []
        for key, rule, label in (
            (ctx.rule.rule_id, ctx.rule_json(), None),
            (AI_RULE, ctx.ai_rule.rule_json(), None),
            ("outside", None, None),
            ("cash", None, "cash"),
        ):
            members = [j for r, j in shown if r.group == key]
            if not members:
                continue
            group: dict[str, Any] = {
                "key": key,
                "pct": float(sum((Decimal(str(j["pct"])) for j in members), ZERO)),
                "target": None,
                "rows": members,
            }
            if rule is not None:
                group["rule"] = rule
            if label is not None:
                group["label"] = label
            groups.append(group)

        holdings = [r.instrument for r in rows if r.kind == "holding" and r.instrument is not None]
        countries = {i.market.value for i in holdings}
        countries |= {COUNTRY[currency] for r in rows if r.kind == "cash"}
        group_by = [
            name
            for name, count in (
                ("instrument", len({i.instrument_id for i in holdings})),
                ("kind", len({i.kind for i in holdings})),
                ("country", len(countries)),
                ("rule", len({r.group for r in rows if r.group not in ("cash", "outside")})),
            )
            if count >= 2
        ]
        withdraw = [r for r in rows if r.chip and r.chip.get("kind") == "withdraw-wait"]
        pending_bar = None
        if withdraw:
            until = max(r.until for r in withdraw if r.until is not None)
            pending_bar = {
                "withdraw": {
                    "krw": fmt.krw(sum((r.krw for r in withdraw), ZERO)),
                    "until": fmt.day(until),
                }
            }
        outside = [r for r in rows if r.group == "outside"]
        return {
            "groupBy": group_by,
            "groups": groups,
            "pendingBar": pending_bar,
            "outsideRules": (
                {"count": len(outside), "krw": fmt.krw(sum((r.krw for r in outside), ZERO))}
                if outside
                else None
            ),
        }

    def _row_amount(self, row: CompRow, currency: Currency) -> Decimal:
        if currency is Currency.KRW:
            return row.krw
        if row.kind == "holding" and row.instrument is not None and row.qty:
            val = self.ctx.valuation
            close = None if val is None else val.closes.get(row.instrument.instrument_id)
            return ZERO if close is None else close.price * row.qty
        return row.usd if row.usd is not None else ZERO

    @staticmethod
    def _row_json(
        row: CompRow, currency: Currency, amount: Decimal, pct: Decimal
    ) -> dict[str, Any]:
        out: dict[str, Any] = {"kind": row.kind, "pct": float(pct), "krw": fmt.krw(row.krw)}
        if currency is Currency.USD:
            out["usd"] = fmt.usd(amount)
        if row.kind == "holding" and row.instrument is not None:
            out["instrument"] = instrument_json(row.instrument)
            out["qty"] = row.qty
            if currency is Currency.KRW:
                cost = row.cost_krw
                value = row.krw
            else:  # in dollars: the rate is not in it
                cost = None if row.avg_price is None or not row.qty else row.avg_price * row.qty
                value = amount
            if cost is not None and cost > 0:
                out["pnlPct"] = fmt.ret1((value - cost) / cost)
            if row.avg_price is not None:
                avg = fmt.krw(row.avg_price) if currency is Currency.KRW else fmt.usd(row.avg_price)
                out["avgCost"] = {"amount": avg, "currency": currency.value}
        else:
            out["cash"] = {"currency": currency.value, "country": COUNTRY[currency]}
            if row.chip is not None:
                out["chip"] = row.chip
        return out

    # ── 변동 분해 of one account ────────────────────────────────────────────────────────────

    def breakdown(self, account_id: str, period: str | None) -> dict[str, Any]:
        """Start → deposits → withdrawals → conversions → market → dividends → fees → now, in the
        account's currency. Signed parts; the market part is what is left, so they add up to
        end − start exactly."""
        ctx = self.ctx
        currency = CURRENCY_OF[account_id]
        points = self.points(currency)
        _, chosen = self._period(points, period, "all")
        first = points[0].snapshot.date if points else ctx.start_date
        since = period_start(chosen, ctx.today, first)
        after: datetime | None = None
        if chosen == "all":
            # From the start: 한국 계좌 began with the start amount (not a deposit), 미국 계좌 with
            # nothing (its dollars came by conversions).
            start_value = ZERO
            split = None if ctx.start is None else start_split(ctx.start)
            if split is not None:  # a live start with dollars: each account its own part
                start_value = split.get(currency, ZERO)
            elif ctx.start is not None and (ctx.start.currency or Currency.KRW) is currency:
                start_value = ctx.start_amount
            from_day = ctx.start_date
        else:
            start = [p for p in points if p.snapshot.date <= since][-1]
            start_value, after, from_day = start.value, start.snapshot.valued_at, since

        def in_period(at: datetime) -> bool:
            return at <= self.at and (after is None or at > after)

        parts = {"deposit": ZERO, "withdrawal": ZERO, "transfer": ZERO}
        for f in self.flows:
            if f.currency is currency and f.kind != "start" and in_period(f.applied_at):
                parts[f.kind] += f.amount
        dividend = sum(
            (
                ev.amount
                for ev in ctx.events
                if ev.kind == "dividend"
                and ev.amount is not None
                and (ev.currency or Currency.KRW) is currency
                and in_period(ev.occurred_at)
            ),
            ZERO,
        )
        fees = -sum(
            (
                f.fee
                for applied, f in self.fills
                if f.kind == "trade" and f.currency is currency and in_period(applied)
            ),
            ZERO,
        )
        values = self.values or dict.fromkeys(Currency, ZERO)
        shown = {
            "start": amount_of(currency, start_value),
            "deposit": amount_of(currency, parts["deposit"]),
            "withdrawal": amount_of(currency, parts["withdrawal"]),
            "transfer": amount_of(currency, parts["transfer"]),
            "dividend": amount_of(currency, dividend),
            "fees": amount_of(currency, fees),
            "end": amount_of(currency, values[currency]),
        }
        market = _remainder(
            currency,
            shown["end"],
            [v for k, v in shown.items() if k != "end"],
        )
        return {
            "from": fmt.day(from_day),
            "to": fmt.day(ctx.today),
            "currency": currency.value,
            "start": shown["start"],
            "deposit": shown["deposit"],
            "withdrawal": shown["withdrawal"],
            "transfer": shown["transfer"],
            "market": market,
            "dividend": shown["dividend"],
            "fees": shown["fees"],
            "end": shown["end"],
        }


def _remainder(currency: Currency, end: int | float, parts: Iterable[int | float]) -> int | float:
    """end − the other parts, counted in won or in cents (no float dust in dollars)."""
    if currency is Currency.KRW:
        return int(end) - sum(int(p) for p in parts)
    cents = round(end * 100) - sum(round(p * 100) for p in parts)
    return fmt.usd(Decimal(cents) / 100)


def home_accounts(
    ctx: LedgerContext, period: str | None, ledger_pnl: int | None
) -> dict[str, Any] | None:
    """HomeResponse.accounts: None until the first fill (the ledger has no P&L before it), and
    while nothing can value the accounts: no valuation now and no snapshot yet (the first day
    before 16:00 with the rate missing). The hero still shows the ledger then."""
    if ledger_pnl is None:
        return None
    accounts = Accounts(ctx)
    if accounts.values is None:
        return None
    return {
        "list": [accounts.account(account_id, period) for account_id, _ in ACCOUNTS],
        "split": accounts.split(ledger_pnl),
    }
