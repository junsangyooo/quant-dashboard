"""What the screens derive from one ledger at one moment.

Every read endpoint builds one LedgerContext, so a number shown on two screens comes from one
computation (e.g. the rule share '자산의 99.6%' on the home plan card, the plan tab and the rules
tab, and the composition group % that adds up its rows).

The hero, the composition and the weights are valued at the latest valuation point — the 16:00
snapshot or the 08:30 check, whichever is newer ('16:00 기준' / '08:30 기준') — over the ledger as
it is now (fills after that point included).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import cached_property
from typing import TYPE_CHECKING, Any

from autotrade.api.views import fmt
from autotrade.api.views.orders import plan_stages, settled
from autotrade.api.views.refs import instrument as instrument_json
from autotrade.api.views.refs import rule_ref
from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.db.models import EventRow, FillRow, LedgerRow, PlanRow, RunRow, SnapshotRow
from autotrade.domain.cash import CashPart, Purpose
from autotrade.domain.instruments import Currency, Instrument
from autotrade.domain.ledger import LedgerState
from autotrade.domain.money import ZERO, round_won, usd_in_krw
from autotrade.domain.status import RuleStatus, StatusFlags, rule_status
from autotrade.domain.weights import DriftReport, drift_report
from autotrade.engine.bootstrap import MODE, start_amount_key, start_date_key
from autotrade.engine.common import buy_wait_krw, load_rule
from autotrade.engine.status import next_check_at
from autotrade.engine.valuation import Valuation, ValuationError, value_ledger
from autotrade.market.calendar import KRX, NYSE, CalendarRangeError
from autotrade.rules.discovery import RULE_ID as AI_RULE
from autotrade.rules.index_half import RULE_ID
from autotrade.rules.model import RuleDef
from autotrade.timeutil import at_kst, is_weekday, kst_date

if TYPE_CHECKING:
    from autotrade.api.views.discovery import AiRule

SERIES_MARKET = {"kr-quotes": "KR", "us-quotes": "US", "fx": "FX"}
EXECUTOR = {"paper": "paper", "live": "live"}


@dataclass
class CompRow:
    kind: str  # 'holding' | 'cash'
    group: str  # rule id | 'cash' | 'outside'
    krw: Decimal
    instrument: Instrument | None = None
    currency: Currency | None = None
    usd: Decimal | None = None
    qty: int | None = None
    avg_price: Decimal | None = None
    cost_krw: Decimal | None = None
    chip: dict[str, Any] | None = None
    pct: Decimal = ZERO
    purpose: Purpose | None = None
    until: date | None = None


@dataclass
class Composition:
    rows: list[CompRow] = field(default_factory=list)

    def group_pct(self, group: str) -> Decimal:
        return sum((r.pct for r in self.rows if r.group == group), ZERO)

    def group_krw(self, group: str) -> Decimal:
        return sum((r.krw for r in self.rows if r.group == group), ZERO)


# Event kinds the engine records for itself and the screens do not list (CONTRACT.md EventKind):
# 'todo-resolved' notes that the owner closed a manual action (engine/todos.py); the screens
# show it on the rebalance row instead ('resolvedOn').
INTERNAL_EVENT_KINDS = ("todo-resolved",)


def event_kind(ev: EventRow) -> str:
    """CONTRACT.md EventKind of an event row (a rebalance shows its state)."""
    if ev.kind != "rebalance":
        return ev.kind
    if ev.status == "in-progress":
        return "in-progress"
    if ev.status in ("partial-failed", "todo", "resolved") or ev.payload.get("retried"):
        return "partial-failed"
    return "rebalance"


def event_krw(ev: EventRow) -> Decimal:
    """Won amount of a cash event. A dollar dividend carries the won value of its booking."""
    amount = ev.amount or ZERO
    if ev.currency is not Currency.USD:
        return amount
    krw = ev.payload.get("amount_krw")
    if krw is not None:
        return Decimal(str(krw))
    rate = ev.payload.get("krw_rate")
    return ZERO if rate is None else usd_in_krw(amount, Decimal(str(rate)))


class LedgerContext:
    def __init__(
        self, conn: sqlite3.Connection, cfg: Config, ledger_id: str, now: datetime
    ) -> None:
        self.conn = conn
        self.cfg = cfg
        self.ledger_id = ledger_id
        self.now = now
        self.today = kst_date(now)
        rule, instruments = load_rule(conn, RULE_ID)
        self.rule: RuleDef = rule
        self.rule_instruments: dict[str, Instrument] = instruments
        self.ledger: LedgerRow = repo.get_ledger(conn, ledger_id)
        self.start: EventRow | None = repo.start_event(conn, ledger_id)
        self.executor = EXECUTOR.get(ledger_id, "paper")

    # ── basic facts ──────────────────────────────────────────────────────────────────────

    @property
    def started(self) -> bool:
        return self.start is not None

    @cached_property
    def start_amount(self) -> Decimal:
        if self.start is not None and self.start.amount is not None:
            return self.start.amount
        text = repo.get_setting(self.conn, start_amount_key(self.ledger_id))
        return Decimal(text) if text else ZERO

    @cached_property
    def start_date(self) -> date:
        if self.start is not None:
            return self.start.event_date
        return kst_date(self.first_check_at)

    @cached_property
    def first_check_at(self) -> datetime:
        """When the ledger's first check runs (meaningful before the start)."""
        text = repo.get_setting(self.conn, start_date_key(self.ledger_id)) or ""
        start = date.fromisoformat(text) if text else self.today
        d = max(start, self.today)
        candidate = at_kst(d, self.cfg.check_time)
        if candidate <= self.now or not is_weekday(d):
            return next_check_at(self.cfg, max(candidate, self.now))
        return candidate

    @cached_property
    def mode(self) -> str:
        return repo.get_setting(self.conn, MODE) or "paper"

    @cached_property
    def instruments(self) -> dict[str, Instrument]:
        out = dict(self.rule_instruments)
        for iid in repo.load_state(self.conn, self.ledger_id).positions:
            if iid not in out:
                out[iid] = repo.get_instrument(self.conn, iid)
        return out

    @cached_property
    def last_check(self) -> RunRow | None:
        return repo.last_run(self.conn, self.ledger_id, "check")

    @cached_property
    def open_plan(self) -> PlanRow | None:
        plans = repo.open_plans(self.conn, self.ledger_id, self.rule.rule_id)
        return plans[-1] if plans else None

    @cached_property
    def parts(self) -> list[CashPart]:
        return repo.cash_parts(self.conn, self.ledger_id)

    @cached_property
    def snapshots(self) -> list[SnapshotRow]:
        return [
            s for s in repo.snapshots_of_ledger(self.conn, self.ledger_id) if s.date <= self.today
        ]

    @cached_property
    def events(self) -> list[EventRow]:
        return [
            e
            for e in repo.events_of_ledger(self.conn, self.ledger_id)
            if e.occurred_at <= self.now and e.kind not in INTERNAL_EVENT_KINDS
        ]

    @cached_property
    def next_check(self) -> datetime:
        if not self.started:
            return self.first_check_at
        return next_check_at(self.cfg, self.now)

    # ── valuation ────────────────────────────────────────────────────────────────────────

    @cached_property
    def valued_at(self) -> datetime | None:
        candidates: list[datetime] = []
        if self.snapshots:
            candidates.append(self.snapshots[-1].valued_at)
        if self.last_check is not None:
            candidates.append(self.last_check.started_at)
        candidates = [c for c in candidates if c <= self.now]
        return max(candidates) if candidates else None

    @cached_property
    def valuation(self) -> Valuation | None:
        if not self.started or self.valued_at is None:
            return None
        try:
            return value_ledger(
                self.conn, self.cfg, self.ledger_id, self.valued_at, self.rule_instruments.values()
            )
        except ValuationError:
            return None

    @property
    def fx_rate(self) -> Decimal:
        val = self.valuation
        return val.fx.rate if val is not None and val.fx is not None else ZERO

    @cached_property
    def total(self) -> Decimal:
        if self.valuation is not None:
            return self.valuation.total_krw
        if self.snapshots:
            return self.snapshots[-1].total_krw
        return self.start_amount

    @cached_property
    def contributions(self) -> Decimal:
        state = repo.load_state(self.conn, self.ledger_id)
        return state.contributions_krw if self.started else self.start_amount

    @cached_property
    def has_fills(self) -> bool:
        return bool(repo.fills_of_ledger(self.conn, self.ledger_id))

    @cached_property
    def stale_series(self) -> list[str]:
        return [] if self.valuation is None else self.valuation.stale

    def basis(self) -> dict[str, Any]:
        val = self.valuation
        if val is None:
            return {
                "valuedAt": fmt.iso(self.valued_at or self.now),
                "krClose": None,
                "usClose": None,
                "fxRate": None,
                "fxAt": None,
            }
        return {
            "valuedAt": fmt.iso(val.at),
            "krClose": None if val.kr_close is None else fmt.day(val.kr_close),
            "usClose": None if val.us_close is None else fmt.day(val.us_close),
            "fxRate": None if val.fx is None else fmt.rate(val.fx.rate),
            "fxAt": None if val.fx is None else fmt.iso(val.fx.as_of),
        }

    # ── composition (rows that add up to the total) ──────────────────────────────────────

    def _pending_buy_qty(self, instrument_id: str) -> int:
        if self.open_plan is None:
            return 0
        latest: dict[tuple[str, str], tuple[int, int]] = {}
        for o in repo.orders_of_plan(self.conn, self.open_plan.plan_id):
            if o.side == "buy" and o.instrument_id == instrument_id and o.qty is not None:
                key = (o.stage, o.instrument_id)
                if key not in latest or o.attempt > latest[key][0]:
                    latest[key] = (o.attempt, o.qty if o.status == "pending" else 0)
        return sum(q for _, q in latest.values())

    @cached_property
    def composition(self) -> Composition:
        comp = Composition()
        rule_ids = set(self.rule.instrument_ids)
        if not self.started:
            comp.rows.append(
                CompRow(
                    "cash",
                    "cash",
                    self.start_amount,
                    currency=Currency.KRW,
                    chip={"kind": "first-buy"},
                    purpose=Purpose.NEW,
                )
            )
        else:
            val = self.valuation
            sleeve = self.ai_sleeve
            ledger = repo.load_state(self.conn, self.ledger_id)
            if val is not None:
                for p in sorted(val.positions, key=lambda p: p.value_krw, reverse=True):
                    iid = p.instrument.instrument_id
                    mine = sleeve.positions.get(iid)
                    ai_qty = 0 if mine is None else mine.qty
                    ai_krw = round_won(p.value_krw * ai_qty / p.qty) if ai_qty else ZERO
                    base_qty = p.qty - ai_qty
                    if base_qty > 0:
                        total_native = ledger.positions[iid].cost_native
                        native = total_native - (ZERO if mine is None else mine.cost_native)
                        group = self.rule.rule_id if iid in rule_ids else "outside"
                        comp.rows.append(
                            CompRow(
                                "holding",
                                group,
                                p.value_krw - ai_krw,
                                instrument=p.instrument,
                                currency=p.instrument.currency,
                                qty=base_qty,
                                avg_price=native / base_qty,
                                cost_krw=p.cost_krw - (ZERO if mine is None else mine.cost_krw),
                            )
                        )
                    if mine is not None and ai_qty > 0:
                        comp.rows.append(
                            CompRow(
                                "holding",
                                AI_RULE,
                                ai_krw,
                                instrument=p.instrument,
                                currency=p.instrument.currency,
                                qty=ai_qty,
                                avg_price=mine.cost_native / ai_qty,
                                cost_krw=mine.cost_krw,
                            )
                        )
            comp.rows.extend(self._cash_rows())
            for currency in Currency:
                amount = sleeve.cash_of(currency)
                if amount <= 0:
                    continue
                usd = currency is Currency.USD
                comp.rows.append(
                    CompRow(
                        "cash",
                        AI_RULE,
                        usd_in_krw(amount, self.fx_rate) if usd else amount,
                        currency=currency,
                        usd=amount if usd else None,
                    )
                )
        for row, pct in zip(comp.rows, fmt.allocate_pct1([r.krw for r in comp.rows]), strict=True):
            row.pct = pct
        return comp

    def _cash_rows(self) -> list[CompRow]:
        rows: list[CompRow] = []
        rate = self.fx_rate
        usd_parts = [p for p in self.parts if p.currency is Currency.USD and p.amount > 0]
        cum_usd, cum_krw = ZERO, ZERO
        usd_krw: dict[int, Decimal] = {}
        for p in usd_parts:  # cumulative rounding: dollar rows add up to the dollar total
            cum_usd += p.amount
            krw_now = usd_in_krw(cum_usd, rate)
            usd_krw[id(p)] = krw_now - cum_krw
            cum_krw = krw_now
        checked = self.last_check is not None
        for p in self.parts:
            if p.amount <= 0:
                continue
            krw_value = p.amount if p.currency is Currency.KRW else usd_krw[id(p)]
            usd_amount = p.amount if p.currency is Currency.USD else None
            if p.purpose is Purpose.BUY_WAIT and p.instrument_id in self.rule.instrument_ids:
                inst = self.instruments[p.instrument_id]
                chip: dict[str, Any] | None = {
                    "kind": "buy-wait",
                    "instrumentName": inst.name,
                    "qty": self._pending_buy_qty(inst.instrument_id),
                }
                group = self.rule.rule_id
            elif p.purpose is Purpose.WITHDRAW_WAIT:
                chip = {
                    "kind": "withdraw-wait",
                    "until": None if p.until is None else fmt.day(p.until),
                }
                group = "cash"
            elif p.purpose is Purpose.NEW:
                chip = None if checked else {"kind": "first-buy"}
                group = "cash"
            else:
                chip = {"kind": "sub-share"}
                group = "cash"
            rows.append(
                CompRow(
                    "cash",
                    group,
                    krw_value,
                    currency=p.currency,
                    usd=usd_amount,
                    chip=chip,
                    purpose=p.purpose,
                    until=p.until,
                )
            )
        return rows

    @property
    def rule_share(self) -> Decimal:
        return self.composition.group_pct(self.rule.rule_id)

    # ── the AI rule (phase 2) ────────────────────────────────────────────────────────────

    @cached_property
    def ai_rule(self) -> AiRule:
        from autotrade.api.views.discovery import AiRule

        return AiRule(self)

    @cached_property
    def ai_sleeve(self) -> LedgerState:
        """The AI rule's part of the ledger (empty where it has no share)."""
        return ai_repo.load_sleeve(self.conn, self.ledger_id, AI_RULE)

    # ── weights, status, next action ─────────────────────────────────────────────────────

    @cached_property
    def ai_fills(self) -> list[FillRow]:
        return repo.fills_of_rule(self.conn, self.ledger_id, AI_RULE)

    def base_value(self, instrument_id: str, qty: int, value_krw: Decimal, at: datetime) -> Decimal:
        """'지수 반반''s part of a position's value at `at`: the shares the AI rule bought to park
        its money in the same index ETF are its own (engine/sleeves.py base_view)."""
        ai_qty = 0
        for fill in self.ai_fills:
            if fill.filled_at > at:
                break
            if fill.instrument_id == instrument_id and fill.qty:
                ai_qty += fill.qty if fill.side == "buy" else -fill.qty
        if qty <= 0 or ai_qty <= 0:
            return value_krw
        return value_krw * (qty - ai_qty) / qty

    @cached_property
    def drift(self) -> DriftReport | None:
        val = self.valuation
        if val is None:
            return None
        values = dict.fromkeys(self.rule.instrument_ids, ZERO)
        for p in val.positions:
            iid = p.instrument.instrument_id
            if iid in values:
                values[iid] = self.base_value(iid, p.qty, p.value_krw, val.at)
        waiting = buy_wait_krw(self.parts, self.fx_rate)
        targets = {t.instrument_id: t.weight for t in self.rule.targets}
        report = drift_report(values, waiting, targets, self.rule.threshold)
        return report if report.weights else None

    @cached_property
    def check_freshness(self) -> dict[str, Any]:
        if self.last_check is None:
            return {}
        fresh = self.last_check.details.get("freshness", {})
        return fresh if isinstance(fresh, dict) else {}

    def stale_at_check(self) -> list[str]:
        """The data sources the last check found not fresh ('kr-quotes', 'us-quotes', 'fx')."""
        out: list[str] = []
        for series in ("kr-quotes", "us-quotes", "fx"):
            info = self.check_freshness.get(series)
            if isinstance(info, dict) and info.get("state") not in (None, "fresh"):
                out.append(series)
        return out

    def stale_source(self) -> tuple[str, str, int] | None:
        """(market, basis date, sessions missing) of the series that made the last check wait."""
        for series in ("us-quotes", "kr-quotes", "fx"):
            info = self.check_freshness.get(series)
            if isinstance(info, dict) and info.get("state") != "fresh":
                basis = str(info.get("basis") or "")[:10]
                return SERIES_MARKET[series], basis, int(info.get("missing_sessions") or 0)
        return None

    @cached_property
    def withdraw_until(self) -> date | None:
        dates = [p.until for p in self.parts if p.purpose is Purpose.WITHDRAW_WAIT and p.until]
        return max(dates) if dates else None

    @cached_property
    def status(self) -> RuleStatus:
        last = self.last_check
        flags = StatusFlags(
            quote_wait=last is not None and last.result == "quote-wait",
            partial_failed=self.open_plan is not None
            and self.open_plan.status in ("partial-failed", "todo"),
            in_progress=self.open_plan is not None and self.open_plan.status == "in-progress",
            withdraw_wait=self.withdraw_until is not None,
            holiday=last is not None and last.run_date == self.today and last.result == "holiday",
            scheduled=last is None
            or (self.drift is not None and self.drift.exceeded and self.open_plan is None),
        )
        return rule_status(flags)

    @cached_property
    def stages(self) -> list[dict[str, Any]] | None:
        if self.open_plan is None:
            return None
        return plan_stages(self.conn, self.open_plan.plan_id, self.instruments, self.executor)

    def _first_open_order(self) -> dict[str, Any] | None:
        for stage in self.stages or []:
            for order in stage["orders"]:
                if not settled(order) and order["side"] != "fx":
                    return dict(order)
        for stage in self.stages or []:
            for order in stage["orders"]:
                if not settled(order):
                    return dict(order)
        return None

    @cached_property
    def next_action(self) -> dict[str, Any]:
        status = self.status
        if status is RuleStatus.QUOTE_WAIT:
            stale = self.stale_source()
            market, basis = (stale[0], stale[1]) if stale else ("US", "")
            return {"kind": "quote-wait", "market": market, "basisDate": basis}
        if status in (RuleStatus.PARTIAL_FAILED, RuleStatus.IN_PROGRESS):
            order = self._first_open_order()
            if order is not None:
                failure = order.get("failure")
                if isinstance(failure, dict) and failure.get("manual"):
                    return {"kind": "todo", "market": order["market"], "side": order["side"]}
                if isinstance(failure, dict) and failure.get("retryAt"):
                    return {
                        "kind": "retry",
                        "at": failure["retryAt"],
                        "market": order["market"],
                        "side": order["side"],
                    }
                name = order["instrument"]["name"] if "instrument" in order else ""
                return {
                    "kind": "order",
                    "at": order["at"],
                    "market": order["market"],
                    "side": order["side"],
                    "instrumentName": name,
                    "qty": order.get("qty", 0),
                }
        if status is RuleStatus.WITHDRAW_WAIT and self.withdraw_until is not None:
            return {"kind": "withdraw-wait", "until": fmt.day(self.withdraw_until)}
        if status is RuleStatus.HOLIDAY and self.last_check is not None:
            closed = self.last_check.details.get("closed_markets", [])
            return {
                "kind": "holiday",
                "markets": list(closed),
                "nextCheckAt": fmt.iso(self.next_check),
            }
        if self.last_check is None:
            return {"kind": "first-check", "at": fmt.iso(self.first_check_at)}
        return {"kind": "next-check", "at": fmt.iso(self.next_check)}

    def gauge(self) -> dict[str, Any]:
        needle = None
        report = self.drift
        if (
            report is not None
            and report.max_instrument is not None
            and self.status is not RuleStatus.QUOTE_WAIT
            and self.last_check is not None
        ):
            needle = {
                "instrument": instrument_json(self.instruments[report.max_instrument]),
                "deviation": fmt.pp1(report.max_drift),
                "toThreshold": fmt.pp1(report.to_threshold),
            }
        return {"kind": "drift", "threshold": fmt.pp1(self.rule.threshold), "needle": needle}

    @cached_property
    def target_pct(self) -> float:
        """The rule's target share of the ledger (PHASE2.md §1; 100% while it is alone)."""
        stored = ai_repo.shares(self.conn, self.ledger_id).get(self.rule.rule_id)
        return float(stored) if stored is not None else fmt.pct1(self.rule.asset_share)

    def share(self) -> dict[str, Any]:
        return {"pct": float(self.rule_share), "target": self.target_pct}

    def rule_json(self) -> dict[str, Any]:
        return rule_ref(self.rule, 0)

    # ── calendar helpers ─────────────────────────────────────────────────────────────────

    @staticmethod
    def closed_markets(d: date) -> list[str]:
        out: list[str] = []
        try:
            if not KRX.is_trading_day(d):
                out.append("KR")
            if not NYSE.is_trading_day(d):
                out.append("US")
        except CalendarRangeError:
            return []
        return out

    def upcoming_holidays(self, days: int = 7) -> list[dict[str, Any]]:
        """Weekdays in the next `days` days with one or both markets closed ('7/3 미국 휴장')."""
        out: list[dict[str, Any]] = []
        for i in range(1, days + 1):
            d = self.today + timedelta(days=i)
            if not is_weekday(d):
                continue
            closed = self.closed_markets(d)
            if closed:
                out.append({"kind": "holiday", "date": fmt.day(d), "markets": closed})
        return out
