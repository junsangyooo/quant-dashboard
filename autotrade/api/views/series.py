"""Time series shared by home, history and plan: snapshots, periods, event markers, drift.

Money in or out against values (one rule everywhere): a period's change is the P&L at its closing
valuation less the P&L at its opening one, P&L being the value less the money in by that moment.
So money counts in a period when it arrived after the opening valuation and by the closing one:
a deposit at 20:00 belongs to the next day's 16:00 value, not to the day it came (its 16:00 value
was taken before it). A snapshot stores its value and the money in from the same ledger state at
the same moment (engine/snapshot.py take_snapshot), so its P&L is exact even when a deposit was
booked late; now, the closing pair is the ledger's (ctx.total, ctx.contributions, ctx.as_of).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.context import LedgerContext, event_kind
from autotrade.db.models import SnapshotRow
from autotrade.domain.cash import Purpose
from autotrade.domain.instruments import Currency
from autotrade.domain.money import ZERO, usd_in_krw
from autotrade.domain.weights import drift_report

MIN_RECORD_DAYS = 30  # '기록 30거래일 미만이면 기간 칩 숨김'
# The home trend's markers (SCR-HOME legend). A failed check has none there: the history band
# shows it ('✕ 확인 실패').
MARKER_KINDS = (
    "start",
    "rebalance",
    "partial-failed",
    "in-progress",
    "dividend",
    "deposit",
    "withdrawal",
    "live-on",
    "live-off",
)


def months_back(d: date, months: int) -> date:
    y, m = d.year, d.month - months
    while m <= 0:
        y, m = y - 1, m + 12
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise ValueError(d)  # pragma: no cover


def period_start(period: str, today: date, since: date) -> date:
    if period == "1m":
        return max(months_back(today, 1), since)
    if period == "3m":
        return max(months_back(today, 3), since)
    if period == "1y":
        return max(date(today.year - 1, today.month, min(today.day, 28)), since)
    return since


def long_record(ctx: LedgerContext) -> bool:
    return len(ctx.snapshots) >= MIN_RECORD_DAYS


def ret(value: Decimal, base: Decimal) -> float:
    return fmt.ret2((value - base) / base) if base > 0 else 0.0


def snapshot_pnl(snap: SnapshotRow) -> Decimal:
    """A snapshot's P&L: its value less the money that had come in when it was taken."""
    return snap.total_krw - snap.contributions


@dataclass(frozen=True)
class Opening:
    """The valuation a period opens with: its value, its P&L, and when it was taken (money that
    came in after `at` belongs to the period)."""

    value: Decimal
    pnl: Decimal
    at: datetime


def opening(ctx: LedgerContext, d: date) -> Opening | None:
    """The valuation of a period that starts on d: the snapshot on d or the last one before it,
    else the start when the ledger had started by d (worth what came in, so no P&L: a live
    ledger turned on after that day's snapshot ran has no snapshot on its first day). None
    before the start."""
    best: SnapshotRow | None = None
    for s in ctx.snapshots:
        if s.date <= d:
            best = s
    if best is not None:
        return Opening(best.total_krw, snapshot_pnl(best), best.valued_at)
    if ctx.start is not None and ctx.start_date <= d:
        return Opening(ctx.start_amount, ZERO, ctx.start.occurred_at)
    return None


def pnl_now(ctx: LedgerContext) -> Decimal:
    """The ledger's P&L at `ctx.as_of`: the total less the money in by then."""
    return ctx.total - ctx.contributions


def series_points(ctx: LedgerContext, since: date) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []
    for snap in ctx.snapshots:
        if snap.date < since:
            continue
        baseline = snap.baseline_krw
        points.append(
            {
                "date": fmt.day(snap.date),
                "value": fmt.krw(snap.total_krw),
                "ret": ret(snap.total_krw, snap.contributions),
                "baseline": None if baseline is None else fmt.krw(baseline),
                "baselineRet": None if baseline is None else ret(baseline, snap.contributions),
            }
        )
    return points


def event_markers(ctx: LedgerContext, since: date | None = None) -> list[dict[str, Any]]:
    """One marker per day (CONTRACT.md Trend.events): the day's first event kind, every kind of
    the day in `kinds`, and `count` when there are two or more (a bundle marker). A marker stays
    on its event's own day even when the money came after that day's value (it opens that day's
    panel, which lists the event); it nets nothing, so it needs no valuation time."""
    by_date: dict[str, list[str]] = {}
    for ev in ctx.listed_events:
        if since is not None and ev.event_date < since:
            continue
        kind = event_kind(ev)
        if kind in MARKER_KINDS:
            by_date.setdefault(fmt.day(ev.event_date), []).append(kind)
    out: list[dict[str, Any]] = []
    for d in sorted(by_date):
        kinds = by_date[d]
        marker: dict[str, Any] = {"date": d, "kind": kinds[0], "kinds": kinds}
        if len(kinds) > 1:
            marker["count"] = len(kinds)
        out.append(marker)
    return out


def snapshot_drift(ctx: LedgerContext, snap: SnapshotRow) -> Decimal | None:
    """Largest |drift| of the rule at a snapshot (weights incl. cash waiting to buy)."""
    if snap.stale:
        return None
    values: dict[str, Decimal] = dict.fromkeys(ctx.rule.instrument_ids, ZERO)
    for pos in snap.positions:
        iid = str(pos.get("instrument_id"))
        if iid in values:
            value = Decimal(str(pos.get("value_krw")))
            values[iid] = ctx.base_value(iid, int(pos.get("qty") or 0), value, snap.valued_at)
    waiting: dict[str, Decimal] = {}
    for part in snap.cash_parts:
        part_iid = str(part.get("instrument_id"))
        if part.get("purpose") != "buy_wait" or part_iid not in values:
            continue
        amount = Decimal(str(part.get("amount")))
        krw = (
            amount
            if part.get("currency") == Currency.KRW.value
            else usd_in_krw(amount, snap.fx_rate)
        )
        waiting[part_iid] = waiting.get(part_iid, ZERO) + krw
    targets = {t.instrument_id: t.weight for t in ctx.rule.targets}
    report = drift_report(values, waiting, targets, ctx.rule.threshold)
    if not report.weights:
        return None
    return abs(report.max_drift)


def snapshot_mix(ctx: LedgerContext, snap: SnapshotRow) -> Decimal | None:
    """|한국's share - its target| of the live rule's money at a snapshot (D47), as
    LedgerContext.mix_deviation reads it now: the rule's holdings and the cash of each currency,
    cash leaving for a withdrawal left out (the live ledger has no AI share). None when the
    snapshot's prices were stale or the rule held nothing."""
    if snap.stale:
        return None
    kr = us = ZERO
    for pos in snap.positions:
        if str(pos.get("instrument_id")) not in ctx.rule.instrument_ids:
            continue
        value = Decimal(str(pos.get("value_krw")))
        if pos.get("currency") == Currency.KRW.value:
            kr += value
        else:
            us += value
    for part in snap.cash_parts:
        if part.get("purpose") == Purpose.WITHDRAW_WAIT.value:
            continue
        amount = Decimal(str(part.get("amount")))
        if part.get("currency") == Currency.KRW.value:
            kr += amount
        else:
            us += usd_in_krw(amount, snap.fx_rate)
    if kr + us <= 0:
        return None
    return abs(kr / (kr + us) - ctx.target_kr)


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_changes(ctx: LedgerContext) -> dict[str, int]:
    """Change per month in whole won, net of money in and out; the changes add up to the P&L.

    month change = P&L at the month's last valuation - P&L at the previous month's (the module
    docstring), with the P&L before the start 0 and the current month ending at the ledger's P&L
    now. Money that came after a month's last 16:00 value is the next month's: a deposit on the
    evening of 6/30 is in neither June's value nor June's money in. Each month is the change of
    the rounded running sum, so rounding never piles up: the months add up to the rounded P&L
    exactly ('월 변동의 합 = 손익').
    """
    month_pnl: dict[str, Decimal] = {}
    for snap in ctx.snapshots:
        month_pnl[month_key(snap.date)] = snapshot_pnl(snap)
    month_pnl[month_key(ctx.today)] = pnl_now(ctx)
    # Every month with a value or an event gets a row (a month with events but no value keeps
    # the previous P&L: its change is 0 and the sum still equals the P&L).
    months = sorted(set(month_pnl) | {month_key(e.event_date) for e in ctx.events})
    out: dict[str, int] = {}
    running = ZERO
    shown = 0
    for m in months:
        running = month_pnl.get(m, running)
        out[m] = fmt.krw(running) - shown
        shown += out[m]
    return out


def trading_days_back(days: Sequence[date], today: date, n: int) -> list[date]:
    return [d for d in days if d <= today][-n:]


def weekdays(start: date, end: date) -> list[date]:
    out: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out
