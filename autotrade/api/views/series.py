"""Time series shared by home, history and plan: snapshots, periods, event markers, drift."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views.context import LedgerContext, event_kind
from autotrade.db.models import SnapshotRow
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


def contributions_by_date(ctx: LedgerContext) -> dict[date, Decimal]:
    """Net money in per day: start and deposits in, withdrawals out (dividends are income)."""
    out: dict[date, Decimal] = {}
    for ev in ctx.events:
        if ev.amount is None:
            continue
        if ev.kind in ("start", "deposit"):
            out[ev.event_date] = out.get(ev.event_date, ZERO) + ev.amount
        elif ev.kind == "withdrawal":
            out[ev.event_date] = out.get(ev.event_date, ZERO) - ev.amount
    return out


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
    the day in `kinds`, and `count` when there are two or more (a bundle marker)."""
    by_date: dict[str, list[str]] = {}
    for ev in ctx.events:
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


def value_on(ctx: LedgerContext, d: date) -> Decimal | None:
    """The snapshot value on d, or on the last snapshot before it."""
    best: SnapshotRow | None = None
    for s in ctx.snapshots:
        if s.date <= d:
            best = s
    return None if best is None else best.total_krw


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


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_changes(ctx: LedgerContext, total: Decimal) -> dict[str, int]:
    """Change per month in whole won, net of money in and out; the changes add up to the P&L.

    month change = (value at month end - value at the previous month end) - net money in during
    the month, with the value before the start = 0 and the current month ending at `total`.
    Each month is the change of the rounded running sum, so rounding never piles up: the months
    add up to the rounded P&L exactly ('월 변동의 합 = 손익').
    """
    flows = contributions_by_date(ctx)
    month_end: dict[str, Decimal] = {}
    for snap in ctx.snapshots:
        month_end[month_key(snap.date)] = snap.total_krw
    current = month_key(ctx.today)
    month_end[current] = total
    # Every month with a value, money in or out, or an event gets a row (a month with events but
    # no snapshot keeps the previous value: its change is 0 and the sum still equals the P&L).
    months = sorted(
        set(month_end)
        | {month_key(d) for d in flows}
        | {month_key(e.event_date) for e in ctx.events}
    )
    out: dict[str, int] = {}
    previous = running = ZERO
    shown = 0
    for m in months:
        end = month_end.get(m, previous)
        net_in = sum((v for d, v in flows.items() if month_key(d) == m), ZERO)
        running += end - previous - net_in
        out[m] = fmt.krw(running) - shown
        shown += out[m]
        previous = end
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
