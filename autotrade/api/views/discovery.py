"""The AI rule '3년 발굴' on the screens (CONTRACT.md, Vault 5-설계/화면-맞춤.md ②③).

- RuleCard: the same frame as the fixed rule with other contents. The gauge is the sell-condition
  gauge (D34): its needle is the held pick nearest to one of its sell conditions, 0 on the pick
  day's value and 100 on the line; each pick's row shows how far it has come and what is left.
  The 'vs index' line is the picks' mean excess over their market's index (rule_daily, the
  scoring's arithmetic).
- FlowDisplay: the four lanes of the rule definition (autotrade/rules/discovery.py) with the
  engine's '지금' values; edges taken today are solid.
- AiJudgment: built from the event the AI runner recorded (autotrade/ai/flows.py).
- Health: the rows filings, ai-cli and metric-table, and their 'to do' items.

Numbers, dates and enums only; the screen writes the words (CONTRACT.md 원칙). marginText is the
one compact number the gauge row prints ('2.3%p', '3.1조', '$350M', '2분기').
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import cached_property
from typing import TYPE_CHECKING, Any

from autotrade.ai.runner import month_tokens
from autotrade.api.views import fmt
from autotrade.api.views.orders import plan_stages, settled
from autotrade.api.views.refs import instrument as instrument_json
from autotrade.api.views.refs import rule_ref
from autotrade.db import ai_repo, repo
from autotrade.db.models import EventRow, PlanRow
from autotrade.domain import metrics
from autotrade.domain.conditions import (
    Check,
    ConditionError,
    Distance,
    Observation,
    check,
    distance,
    parse_condition,
)
from autotrade.domain.instruments import Instrument
from autotrade.domain.money import ZERO
from autotrade.domain.periods import PeriodError, parse_period
from autotrade.engine import metric_table
from autotrade.engine.reviews import DISCOVERY_MONTHS, rule_active
from autotrade.rules.discovery import RULE_ID
from autotrade.rules.model import RuleDef
from autotrade.timeutil import at_kst, kst_date

if TYPE_CHECKING:
    from autotrade.api.views.context import LedgerContext

COLOR = 1  # the second rule's colour
AI_EVENT_KINDS = ("discovery", "ai-buy", "ai-sell", "ai-check", "monthly-review")
PERIOD_WORD = {"quarter": "분기", "fquarter": "분기", "month": "달", "year": "년"}
HUNDRED = Decimal(100)


def margin_text(d: Distance, cond_metric: str | None, periods_kind: str | None) -> str:
    """What is left before the line, compactly: '2.3%p', '3.1조', '$350M', '0.12x', '2분기'."""
    if d.periods_left is not None:
        return f"{d.periods_left}{PERIOD_WORD.get(periods_kind or 'quarter', '분기')}"
    m = abs(d.margin or ZERO)
    if d.unit == "%":
        return f"{fmt.pp1(m / HUNDRED):.1f}%p"
    if d.unit == "KRW":
        if m >= Decimal("1e12"):
            return f"{(m / Decimal('1e12')).quantize(Decimal('0.1'))}조"
        return f"{(m / Decimal('1e8')).quantize(Decimal('1'))}억"
    if d.unit == "USD":
        if m >= Decimal("1e9"):
            return f"${(m / Decimal('1e9')).quantize(Decimal('0.1'))}B"
        return f"${(m / Decimal('1e6')).quantize(Decimal('1'))}M"
    if d.unit == "x":
        return f"{m.quantize(Decimal('0.01'))}x"
    return str(m.normalize())


def _baseline(chk: Check, observations: list[Observation]) -> Decimal | None:
    """The value the gauge starts from: the oldest stored one of the same series (the value
    known when the company was picked), when there are two or more."""
    cond = chk.condition
    if cond.type != "level" or cond.change is not None or cond.period is not None:
        return None
    usable = [o for o in observations if o.unit == cond.unit]
    return usable[0].value if len(usable) >= 2 else None


class AiRule:
    def __init__(self, ctx: LedgerContext) -> None:
        self.ctx = ctx
        self.conn: sqlite3.Connection = ctx.conn
        self.rule = RuleDef.from_json(repo.get_rule(ctx.conn, RULE_ID).definition)

    # ── who and how much ─────────────────────────────────────────────────────────────────

    @cached_property
    def target(self) -> Decimal | None:
        return ai_repo.shares(self.conn, self.ctx.ledger_id).get(RULE_ID)

    @property
    def shown(self) -> bool:
        """The rule is on the screens of this ledger: it has a share above 0."""
        return bool(self.target and self.target > 0)

    @property
    def active(self) -> bool:
        return rule_active(self.conn, self.ctx.ledger_id)

    @cached_property
    def held(self) -> list[ai_repo.PickRow]:
        return ai_repo.picks_of(self.conn, self.ctx.ledger_id, RULE_ID, ("held",))

    @cached_property
    def candidates(self) -> list[ai_repo.PickRow]:
        return ai_repo.picks_of(self.conn, self.ctx.ledger_id, RULE_ID, ("candidate",))

    def rule_json(self) -> dict[str, Any]:
        return rule_ref(self.rule, COLOR)

    def share(self) -> dict[str, Any]:
        return {
            "pct": float(self.ctx.composition.group_pct(RULE_ID)),
            "target": None if self.target is None else float(self.target),
        }

    def instrument(self, iid: str) -> Instrument:
        return repo.get_instrument(self.conn, iid)

    # ── plan, status, next action ────────────────────────────────────────────────────────

    @cached_property
    def open_plan(self) -> PlanRow | None:
        plans = repo.open_plans(self.conn, self.ctx.ledger_id, RULE_ID)
        return plans[-1] if plans else None

    @cached_property
    def stages(self) -> list[dict[str, Any]] | None:
        if self.open_plan is None:
            return None
        instruments = {
            o.instrument_id: self.instrument(o.instrument_id)
            for o in repo.orders_of_plan(self.conn, self.open_plan.plan_id)
            if o.instrument_id is not None
        }
        return plan_stages(self.conn, self.open_plan.plan_id, instruments, self.ctx.executor)

    @cached_property
    def status(self) -> str:
        """Same chips as the fixed rule; '유지' when nothing is to be done (CONTRACT RuleStatus)."""
        if not self.ctx.started:
            return "scheduled"
        if self.open_plan is not None:
            if self.open_plan.status in ("partial-failed", "todo"):
                return "partial-failed"
            return "in-progress"
        if any(p.decision == "sell" for p in self.held):
            return "sell-scheduled"
        if any(p.decision == "buy" for p in self.held):
            return "buy-scheduled"
        return "hold"

    def next_action(self) -> dict[str, Any]:
        for stage in self.stages or []:
            for order in stage["orders"]:
                if settled(order):
                    continue
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
                return {
                    "kind": "order",
                    "at": order["at"],
                    "market": order["market"],
                    "side": order["side"],
                    "instrumentName": order.get("instrument", {}).get("name", ""),
                    "qty": order.get("qty", 0),
                }
        if not self.ctx.started:
            return {"kind": "first-check", "at": fmt.iso(self.ctx.first_check_at)}
        # '다음 확인 10/8 08:30 · 점검 11/1': the next monthly review rides on the next check.
        return {
            "kind": "next-check",
            "at": fmt.iso(self.ctx.next_check),
            "reviewAt": fmt.iso(self.next_review()),
        }

    # ── the sell-condition gauge ─────────────────────────────────────────────────────────

    def nearest(self, pick: ai_repo.PickRow) -> tuple[Distance, str, str] | None:
        """(distance, metric label, margin text) of the pick's sell condition nearest its line."""
        best: tuple[Distance, str, str] | None = None
        for data in pick.invalidate:
            try:
                cond = parse_condition(data)
            except ConditionError:
                continue
            if cond.metric is None or not cond.is_sell_metric:
                continue
            obs = metric_table.observations(self.conn, pick.instrument_id, cond.metric)
            chk = check(cond, obs)
            d = distance(chk, _baseline(chk, obs))
            if d is None:
                continue
            kind = None
            if chk.period:
                try:
                    kind = parse_period(chk.period).kind
                except PeriodError:
                    kind = None
            text = margin_text(d, cond.metric, kind)
            if best is None or d.progress > best[0].progress:
                best = (d, metrics.label(cond.metric), text)
        return best

    @cached_property
    def distances(self) -> dict[int, tuple[Distance, str, str]]:
        out: dict[int, tuple[Distance, str, str]] = {}
        for pick in self.held:
            found = self.nearest(pick)
            if found is not None:
                out[pick.pick_id] = found
        return out

    def gauge(self) -> dict[str, Any]:
        needle = None
        if self.distances:
            pick_id, (d, label, text) = max(
                self.distances.items(), key=lambda kv: kv[1][0].progress
            )
            pick = next(p for p in self.held if p.pick_id == pick_id)
            needle = {
                "instrument": instrument_json(self.instrument(pick.instrument_id)),
                "progress": float(d.progress.quantize(Decimal(1))),
                "metric": label,
                "marginText": text,
            }
        return {"kind": "sell-condition", "needle": needle}

    def rows(self) -> list[dict[str, Any]]:
        comp = self.ctx.composition
        values = {
            r.instrument.instrument_id: r.krw
            for r in comp.rows
            if r.group == RULE_ID and r.kind == "holding" and r.instrument is not None
        }
        total = comp.group_krw(RULE_ID)
        target = fmt.pct1(Decimal(1) / len(self.held)) if self.held else 0.0
        out: list[dict[str, Any]] = []
        for pick in self.held:
            value = values.get(pick.instrument_id)
            row: dict[str, Any] = {
                "instrument": instrument_json(self.instrument(pick.instrument_id)),
                "weight": None if value is None or total <= 0 else fmt.pct1(value / total),
                "target": target,
                "toThreshold": None,
            }
            found = self.distances.get(pick.pick_id)
            if found is not None:
                d, label, text = found
                row.update(
                    {
                        "progress": float(d.progress.quantize(Decimal(1))),
                        "metric": label,
                        "marginText": text,
                    }
                )
            out.append(row)
        return out

    def vs_index(self) -> dict[str, Any] | None:
        points = ai_repo.rule_daily(self.conn, self.ctx.ledger_id, RULE_ID)
        points = [(d, v) for d, v in points if d <= self.ctx.today]
        if not points:
            return None
        return {
            "since": fmt.day(points[0][0]),
            "points": [
                {"date": fmt.day(d), "value": None if v is None else fmt.pp1(v / HUNDRED)}
                for d, v in points
            ],
        }

    def metric_table_at(self) -> str | None:
        """The day the metric table last changed ('지표 표 10/8')."""
        at = ai_repo.latest_metric_at(self.conn)
        return None if at is None else fmt.day(kst_date(at))

    def card(self) -> dict[str, Any]:
        val = self.ctx.valuation
        return {
            "rule": self.rule_json(),
            "share": self.share(),
            "status": self.status,
            "next": self.next_action(),
            "gauge": self.gauge(),
            "rows": self.rows(),
            "basisLine": {
                "pendingBuyIncluded": False,
                "fxRate": None if val is None or val.fx is None else fmt.rate(val.fx.rate),
                "fxAt": None if val is None or val.fx is None else fmt.iso(val.fx.as_of),
                "withdrawExcluded": False,
                "staleMarket": None,
                "staleBasisDate": None,
                "metricTableAt": self.metric_table_at(),
            },
            "vsIndex": self.vs_index(),
        }

    # ── schedule ─────────────────────────────────────────────────────────────────────────

    def _firsts(self) -> list[datetime]:
        """The next first-of-the-month mornings: a review is done by the 08:30 check of the
        1st (it runs from 22:00 the evening before), so the screens show the 1st."""
        first = self.ctx.today.replace(day=1)
        out: list[datetime] = []
        for _ in range(14):
            at = at_kst(first, self.ctx.cfg.check_time)
            if at > self.ctx.now:
                out.append(at)
            first = (first + timedelta(days=32)).replace(day=1)
        return out

    def next_review(self) -> datetime:
        return self._firsts()[0]

    def next_discovery(self) -> datetime:
        return next(at for at in self._firsts() if kst_date(at).month in DISCOVERY_MONTHS)

    def schedule_items(self) -> list[dict[str, Any]]:
        if not self.held and not self.candidates:
            return []
        return [
            {"kind": "monthly-review", "at": fmt.iso(self.next_review()), "ruleId": RULE_ID},
            {"kind": "discovery", "at": fmt.iso(self.next_discovery()), "ruleId": RULE_ID},
        ]

    # ── the flow display (four lanes) ────────────────────────────────────────────────────

    def _events_since(self, kinds: tuple[str, ...], since: date) -> list[EventRow]:
        return [e for e in self.ctx.events if e.kind in kinds and e.event_date >= since]

    def _tasks_today(self, kind: str) -> list[ai_repo.TaskRow]:
        return [
            t
            for t in ai_repo.tasks_of(self.conn, kind=kind)
            if t.ledger_id == self.ctx.ledger_id and kst_date(t.created_at) == self.ctx.today
        ]

    def _watch_today(self) -> ai_repo.JobRunRow | None:
        runs = [
            r
            for r in ai_repo.job_runs_on(self.conn, "watch", self.ctx.today)
            if r.ledger_id == self.ctx.ledger_id
        ]
        return runs[-1] if runs else None

    # Rows of the '지금' blocks hold data only (CONTRACT.md 원칙): kv keys and notes are codes,
    # values are dates, numbers or names; the screen writes the words.
    SHOW = 3  # instruments a card lists before '외 N'

    def _instrument_row(self, iid: str, **extra: Any) -> dict[str, Any]:
        row: dict[str, Any] = {
            "kind": "instrument",
            "instrument": instrument_json(self.instrument(iid)),
        }
        row.update({k: v for k, v in extra.items() if v is not None})
        return row

    @staticmethod
    def _kv(key: str, value: object, note: object = None) -> dict[str, Any]:
        row: dict[str, Any] = {"kind": "kv", "key": key, "value": str(value)}
        if note is not None:
            row["note"] = str(note)
        return row

    @staticmethod
    def _block(
        head: str,
        rows: list[dict[str, Any]],
        at: datetime | date | None = None,
        until: date | None = None,
    ) -> dict[str, Any]:
        out: dict[str, Any] = {"headKey": head, "rows": rows}
        if isinstance(at, datetime):
            out["at"] = fmt.iso(at)
        elif isinstance(at, date):
            out["at"] = fmt.day(at)
        if until is not None:
            out["until"] = fmt.day(until)
        return out

    def _last_event(self, kinds: tuple[str, ...]) -> EventRow | None:
        found = self._events_since(kinds, date.min)
        return found[-1] if found else None

    def _added_by(self, ev: EventRow) -> list[ai_repo.PickRow]:
        """Held picks a discovery added: their source is the event's key ('discovery:2026-12')."""
        return [p for p in self.held if ev.ref is not None and p.source == ev.ref]

    def _last_watch(self) -> ai_repo.JobRunRow | None:
        runs = ai_repo.job_runs_of(self.conn, "watch", self.ctx.ledger_id, limit=5)
        done = [r for r in runs if r.result in ("ok", "partial") and r.started_at <= self.ctx.now]
        return done[-1] if done else None

    def _weights(self) -> dict[str, float]:
        comp = self.ctx.composition
        total = comp.group_krw(RULE_ID)
        if total <= 0:
            return {}
        return {
            r.instrument.instrument_id: fmt.pct1(r.krw / total)
            for r in comp.rows
            if r.group == RULE_ID and r.kind == "holding" and r.instrument is not None
        }

    def _close_row(self, series: str, key: str) -> dict[str, Any] | None:
        info = self.ctx.check_freshness.get(series)
        if not isinstance(info, dict) or not info.get("basis"):
            return None
        return self._kv(key, str(info["basis"])[:10], info.get("state"))

    def _plan_rows(self, plan: PlanRow) -> list[dict[str, Any]]:
        instruments = {
            o.instrument_id: self.instrument(o.instrument_id)
            for o in repo.orders_of_plan(self.conn, plan.plan_id)
            if o.instrument_id is not None
        }
        rows: list[dict[str, Any]] = []
        for stage in plan_stages(self.conn, plan.plan_id, instruments, self.ctx.executor):
            for o in stage["orders"]:
                # A row sums the order up: a retried one shows the retry's outcome and says it
                # took a retry ('9/15 다시 · 체결'); the Order itself keeps its failed day.
                outcome = o.get("retried") or o
                row: dict[str, Any] = {
                    "kind": "order",
                    "side": o["side"],
                    # A trade's text is its instrument's name; a conversion's its direction code.
                    "text": o["instrument"]["name"]
                    if "instrument" in o
                    else o.get("direction", ""),
                    "status": outcome["status"],
                    "at": outcome["at"],
                }
                if "retried" in o:
                    row["retried"] = True
                rows.append(row)
        return rows

    def _action_block(self) -> dict[str, Any]:
        """The open plan's orders ('지금'), else the last plan's ('마지막', over its days)."""
        if self.open_plan is not None:
            return self._block("now", self._plan_rows(self.open_plan))
        plans = [
            p for p in repo.plans_of_ledger(self.conn, self.ctx.ledger_id) if p.rule_id == RULE_ID
        ]
        if not plans:
            return self._block("now-last", [])
        last = plans[-1]
        fills = repo.fills_of_plan(self.conn, last.plan_id)
        end = max((kst_date(f.filled_at) for f in fills), default=last.plan_date)
        return self._block(
            "now-last",
            self._plan_rows(last),
            last.plan_date,
            end if end != last.plan_date else None,
        )

    def _exceptions(self) -> dict[str, Any]:
        status = self.ctx.status.value
        active = status in ("holiday", "quote-wait", "withdraw-wait")
        return {
            "kind": "exceptions",
            "items": ["holiday", "quote-wait", "withdraw-wait"],
            "active": active,
        }

    def _now_daily(self, node: dict[str, Any]) -> dict[str, Any]:
        nid, watch = node["id"], self._last_watch()
        watched = None if watch is None else watch.started_at
        if nid == "start":
            return self._block("now", [], self.ctx.next_check)
        if nid == "data":
            rows = [
                r
                for r in (
                    self._close_row("kr-quotes", "krClose"),
                    self._close_row("us-quotes", "usClose"),
                )
                if r is not None
            ]
            if watch is not None:
                new = int(watch.details.get("filings", {}).get("new", 0))
                latest = ai_repo.latest_filings(self.conn, 1)
                name = self.instrument(latest[0].instrument_id).name if latest else "-"
                rows.append(self._kv("filings", name, new))
            with_metrics = {r.instrument_id for r in self._metric_rows()}
            rows.append(self._kv("metricTable", self.metric_table_at() or "-", len(with_metrics)))
            return self._block("now-check", rows, watched)
        if nid == "condition":
            tasks = [] if watch is None else watch.details.get("tasks", [])
            hits = [t for t in tasks if t.get("kind") in ("sell-confirm", "buy-confirm")]
            rows = [self._instrument_row(str(t["pick"])) for t in hits[: self.SHOW]]
            if not rows and self.distances:
                pick_id, (d, _label, text) = max(
                    self.distances.items(), key=lambda kv: kv[1][0].progress
                )
                pick = next(p for p in self.held if p.pick_id == pick_id)
                rows = [
                    self._instrument_row(
                        pick.instrument_id,
                        progress=float(d.progress.quantize(Decimal(1))),
                        marginText=text,
                    )
                ]
            return self._block("now-check", [*rows, self._kv("hits", len(hits))], watched)
        if node["type"] == "ai":
            ev = self._last_event(("ai-check", "ai-sell", "ai-buy"))
            if ev is None:
                return self._block("now-last-judgment", [])
            rows = [self._kv("verdict", ev.payload.get("verdict"), ev.payload.get("trigger"))]
            if ev.payload.get("instrument_id"):
                rows.insert(0, self._instrument_row(str(ev.payload["instrument_id"])))
            return self._block("now-last-judgment", rows, ev.occurred_at)
        if nid == "confirm":
            month = self._events_since(
                ("ai-check", "ai-sell", "ai-buy"), self.ctx.today.replace(day=1)
            )
            rows = [
                self._kv("judgments", len(month)),
                self._kv("sells", sum(1 for e in month if e.kind == "ai-sell")),
                self._kv("buys", sum(1 for e in month if e.kind == "ai-buy")),
            ]
            last = month[-1] if month else None
            if last is not None and last.payload.get("votes"):
                rows.append(self._kv("votes", ",".join(last.payload["votes"])))
            return self._block("now-month", rows)
        if nid == "result":
            return self._block(
                "now",
                [
                    {
                        "kind": "status",
                        "status": self.status,
                        **({"at": fmt.iso(watched)} if watched else {}),
                    }
                ],
            )
        if nid == "action":
            return self._action_block()
        return self._block("now", [self._exceptions()])

    def _metric_rows(self) -> list[ai_repo.MetricValueRow]:
        rows: list[ai_repo.MetricValueRow] = []
        for pick in self.held:
            rows.extend(ai_repo.metric_values(self.conn, pick.instrument_id))
        return rows

    def _now_earnings(self, node: dict[str, Any]) -> dict[str, Any]:
        nid = node["id"]
        filings = [f for f in ai_repo.latest_filings(self.conn, 50) if f.kind == "earnings"]
        if nid == "start":
            if not filings:
                return self._block("now", [])
            return self._block(
                "now", [self._instrument_row(filings[0].instrument_id)], filings[0].filed_on
            )
        if node["type"] == "ai":
            calls = [
                c for c in ai_repo.last_calls(self.conn, 50) if c.purpose == "extract" and c.ok
            ]
            if not calls:
                return self._block("now-last", [])
            call = calls[0]
            stored = [r for r in self._metric_rows() if r.call_id == call.call_id]
            rows: list[dict[str, Any]] = []
            if stored:
                periods = sorted({r.period for r in stored})
                rows.append(self._instrument_row(stored[0].instrument_id, marginText=periods[-1]))
            rows += [self._kv("metrics", len(stored)), self._kv("tokens", call.tokens)]
            return self._block("now-last", rows, kst_date(call.started_at))
        if nid == "data":
            latest: dict[str, ai_repo.MetricValueRow] = {}
            for r in sorted(self._metric_rows(), key=lambda r: r.extracted_at):
                latest[r.instrument_id] = r
            recent = sorted(latest.values(), key=lambda r: r.extracted_at, reverse=True)
            rows = [
                self._instrument_row(r.instrument_id, marginText=r.period)
                for r in recent[: self.SHOW]
            ]
            return self._block("now", [*rows, self._kv("companies", len(latest))])
        at = filings[0].filed_on if filings else None
        return self._block("now", [{"kind": "status", "status": self.status}], at)

    def _now_monthly(self, node: dict[str, Any]) -> dict[str, Any]:
        ev = self._last_event(("monthly-review",))
        nid = node["id"]
        if nid == "start":
            return self._block("now", [], self.next_review())
        if nid == "data":
            since = self.ctx.today - timedelta(days=30)
            new = sum(len(ai_repo.filings_of(self.conn, p.instrument_id, since)) for p in self.held)
            return self._block(
                "now", [self._kv("picks", len(self.held)), self._kv("newFilings", new)]
            )
        if node["type"] == "ai":
            if ev is None:
                return self._block("now-last-judgment", [])
            counts = ev.payload.get("counts", {})
            rows = [
                self._kv(k, counts[k]) for k in ("hold", "weaken", "invalidated") if k in counts
            ]
            rows.append(self._kv("tokens", ev.payload.get("tokens", 0)))
            return self._block("now-last-judgment", rows, kst_date(ev.occurred_at))
        at = None if ev is None else kst_date(ev.occurred_at)
        return self._block("now", [{"kind": "status", "status": self.status}], at)

    def _now_quarterly(self, node: dict[str, Any]) -> dict[str, Any]:
        nid = node["id"]
        ev = self._last_event(("discovery",))
        weights = self._weights()
        if nid == "start":
            days = (kst_date(self.next_discovery()) - self.ctx.today).days
            return self._block("now", [self._kv("daysToNext", days)], self.next_discovery())
        if nid == "data":
            last = "-" if ev is None else fmt.day(ev.event_date)
            return self._block("now", [self._kv("lastDiscovery", last)])
        if node["type"] == "ai":
            if ev is None:
                return self._block("now-last-judgment", [])
            added = self._added_by(ev)
            rows = [self._instrument_row(p.instrument_id) for p in added[: self.SHOW]]
            rows += [
                self._kv("candidates", len(self.candidates)),
                self._kv("tokens", ev.payload.get("tokens", 0)),
            ]
            return self._block("now-last-judgment", rows, ev.event_date)
        if nid in ("stock", "weight"):
            rows = [
                self._instrument_row(p.instrument_id, weight=weights.get(p.instrument_id))
                for p in self.held[: self.SHOW]
            ]
            if nid == "stock":
                rows.append(self._kv("candidates", len(self.candidates)))
            elif self.held:
                rows.append(self._kv("targetEach", fmt.pct1(Decimal(1) / len(self.held))))
            return self._block("now", rows)
        if nid == "condition":
            watch = self._last_watch()
            gaps = {} if watch is None else watch.details.get("buy_gaps", {})
            near = sorted(
                ((p, gaps[str(p.pick_id)]) for p in self.candidates if str(p.pick_id) in gaps),
                key=lambda pg: float(pg[1]["gap_pct"]),
            )
            rows = [
                self._instrument_row(
                    p.instrument_id,
                    progress=float(Decimal(g["progress"])),
                    marginText=f"{g['gap_pct']}%",
                )
                for p, g in near[: self.SHOW]
            ]
            return self._block("now-check", rows, None if watch is None else watch.started_at)
        if nid == "action":
            return self._action_block()
        if nid == "result":
            return self._block("now", [self._kv("candidates", len(self.candidates))])
        return self._block("now", [self._exceptions()])

    def _now(self, lane: str, node: dict[str, Any]) -> dict[str, Any]:
        """The node's '지금' block from the engine's records."""
        if lane == "daily":
            return self._now_daily(node)
        if lane == "earnings":
            return self._now_earnings(node)
        if lane == "monthly":
            return self._now_monthly(node)
        return self._now_quarterly(node)

    def _more(self, lane: str, node: dict[str, Any]) -> int | None:
        """'외 N': instruments a card has beyond the ones it lists."""
        if lane == "quarterly" and node["id"] in ("stock", "weight"):
            extra = len(self.held) - self.SHOW
            return extra if extra > 0 else None
        if lane == "quarterly" and node["type"] == "ai":
            ev = self._last_event(("discovery",))
            if ev is None:
                return None
            extra = len(self._added_by(ev)) - self.SHOW
            return extra if extra > 0 else None
        return None

    def _taken(self, lane: str) -> set[tuple[str, str]]:
        """Edges walked today (or in the lane's current period)."""
        watch = self._watch_today()
        taken: set[tuple[str, str]] = set()
        if lane == "daily" and watch is not None:
            taken |= {("start", "data"), ("data", "condition")}
            tasks = [
                t
                for t in watch.details.get("tasks", [])
                if t.get("kind") in ("sell-confirm", "buy-confirm")
            ]
            if tasks:
                taken.add(("condition", "ai"))
            else:
                taken.add(("condition", "result"))
            today = self._events_since(("ai-check", "ai-sell", "ai-buy"), self.ctx.today)
            if today:
                taken.add(("ai", "confirm"))
                if any(e.kind in ("ai-sell", "ai-buy") for e in today):
                    taken.add(("confirm", "action"))
                else:
                    taken.add(("confirm", "result"))
        if lane == "earnings" and self._tasks_today("extract"):
            taken |= {("start", "ai"), ("ai", "data"), ("data", "result")}
        if lane == "monthly" and self._events_since(
            ("monthly-review",), self.ctx.today.replace(day=1)
        ):
            taken |= {("start", "data"), ("data", "ai"), ("ai", "result")}
        if lane == "quarterly" and self._events_since(
            ("discovery",), self.ctx.today - timedelta(days=92)
        ):
            taken |= {
                ("start", "data"),
                ("data", "ai"),
                ("ai", "stock"),
                ("stock", "weight"),
                ("weight", "condition"),
            }
        return taken

    def flow(self, lane: str | None) -> dict[str, Any]:
        lanes = self.rule.display.get("lanes", [])
        ids = [str(item["id"]) for item in lanes]
        chosen = lane if lane in ids else ids[0]
        spec = next(item for item in lanes if item["id"] == chosen)
        taken = self._taken(chosen)
        nodes = []
        for node in spec["nodes"]:
            keep = ("id", "type", "col", "row", "title", "subtitle", "fields")
            out = {k: v for k, v in node.items() if k in keep}
            more = self._more(chosen, node)
            if more is not None:
                out["more"] = more
            out["now"] = self._now(chosen, node)
            nodes.append(out)
        edges = []
        for e in spec["edges"]:
            style = (
                "exception"
                if e.get("exception")
                else ("taken" if (e["from"], e["to"]) in taken else "not-taken")
            )
            edge: dict[str, Any] = {"from": e["from"], "to": e["to"], "style": style}
            if e.get("label"):
                edge["label"] = e["label"]
            edges.append(edge)
        return {
            "kind": "flow",
            "lanes": [{"id": item["id"], "label": item["label"]} for item in lanes],
            "lane": chosen,
            "nodes": nodes,
            "edges": edges,
        }

    def detail(self, lane: str | None) -> dict[str, Any]:
        return {
            "rule": self.rule_json(),
            "share": self.share(),
            "status": self.status,
            "example": False,
            "stale": self.ctx.stale_at_check(),
            "display": self.flow(lane),
        }

    # ── health ───────────────────────────────────────────────────────────────────────────

    def sources(self) -> list[dict[str, Any]]:
        if not self.shown:
            return []
        now = self.ctx.now
        rows: list[dict[str, Any]] = []
        states = {s: ai_repo.source_state(self.conn, s) for s in ("dart", "edgar")}
        known = {s: r for s, r in states.items() if r is not None}
        oks = [r.ok_at for r in known.values() if r.ok_at is not None]
        if not known:
            state = "unknown"
        elif any(r.state == "maintenance" for r in known.values()):
            state = "maintenance"
        elif any(r.state != "ok" for r in known.values()):
            state = "stale"
        else:
            state = "fresh"
        last_ok = max(oks) if oks else None
        rows.append(
            {
                "id": "filings",
                "state": state,
                "basis": None if last_ok is None else fmt.day(kst_date(last_ok)),
                "receivedAt": None if last_ok is None else fmt.iso(last_ok),
                "cadence": "daily",
                "age": 0.0
                if last_ok is None
                else round((now - last_ok).total_seconds() / 86400, 2),
                "extra": {s: (r.state if r else "unknown") for s, r in states.items()},
            }
        )
        good = ai_repo.last_ok_call(self.conn)
        last = ai_repo.last_calls(self.conn, 1)
        cli_state = "unknown" if not last else ("fresh" if last[0].ok else "stale")
        rows.append(
            {
                "id": "ai-cli",
                "state": cli_state,
                "basis": None if good is None else good.model,
                "receivedAt": None
                if good is None or good.finished_at is None
                else fmt.iso(good.finished_at),
                "cadence": "event",
                "age": 0.0,
                "extra": {
                    "monthTokens": month_tokens(self.conn, now),
                    "budget": self.ctx.cfg.ai_monthly_budget,
                    "enabled": int(self.ctx.cfg.ai_calls_enabled),
                    "due": len(ai_repo.due_tasks(self.conn, now, self.ctx.cfg.ai_max_attempts)),
                },
            }
        )
        table_at = ai_repo.latest_metric_at(self.conn)
        rows.append(
            {
                "id": "metric-table",
                "state": "unknown" if table_at is None else "fresh",
                "basis": None if table_at is None else fmt.day(kst_date(table_at)),
                "receivedAt": None if table_at is None else fmt.iso(table_at),
                "cadence": "event",
                "age": 0.0,
            }
        )
        return rows

    def todos(self) -> list[dict[str, Any]]:
        if not self.shown:
            return []
        out: list[dict[str, Any]] = []
        now, cfg = self.ctx.now, self.ctx.cfg
        used = month_tokens(self.conn, now)
        if used > cfg.ai_monthly_budget:
            out.append(
                {
                    "id": f"ai-cli:budget:{now:%Y-%m}",
                    "severity": "yellow",
                    "kind": "ai-cli",
                    "facts": {
                        "reason": "over-budget",
                        "tokens": used,
                        "budget": cfg.ai_monthly_budget,
                    },
                    "action": {"kind": "manual"},
                    "effect": "other",
                }
            )
        stuck = [
            t
            for t in ai_repo.tasks_of(self.conn, statuses=("failed",))
            if t.attempts >= cfg.ai_max_attempts
        ]
        if stuck:
            out.append(
                {
                    "id": f"ai-cli:failed:{stuck[-1].task_id}",
                    "severity": "red",
                    "kind": "ai-cli",
                    "facts": {
                        "reason": "task-failed",
                        "count": len(stuck),
                        "taskKind": stuck[-1].kind,
                        # 'AI 호출 실패 · 10/7 06:00부터': when the oldest stuck task was made.
                        "since": fmt.iso(min(t.created_at for t in stuck)),
                    },
                    "action": {"kind": "manual"},
                    "effect": "other",
                }
            )
        for source, market in (("dart", "KR"), ("edgar", "US")):
            row = ai_repo.source_state(self.conn, source)
            if row is not None and row.state != "ok":
                facts: dict[str, Any] = {"source": source, "market": market, "state": row.state}
                if row.ok_at is not None:  # facts hold values only: no key when never received
                    facts["since"] = fmt.iso(row.ok_at)
                out.append(
                    {
                        "id": f"filings:{source}",
                        "severity": "red",  # a fault the watch retries, like stale quotes
                        "kind": "filings",
                        "facts": facts,
                        "action": {"kind": "auto-retry", "at": fmt.iso(self.ctx.next_check)},
                        "effect": "other",
                    }
                )
        return out


def judgment(conn: sqlite3.Connection, ev: EventRow) -> dict[str, Any]:
    """CONTRACT.md AiJudgment from the event the AI runner recorded."""
    p = ev.payload
    out: dict[str, Any] = {
        "at": fmt.iso(ev.occurred_at),
        "trigger": p.get("trigger") or ("monthly" if ev.kind == "monthly-review" else "discovery"),
        "model": p.get("model") or ("opus" if ev.kind == "discovery" else "sonnet"),
        "tokens": int(p.get("tokens") or 0),
        "verdict": p.get("verdict") or "hold",
        "inputSummary": [str(x) for x in p.get("input_summary", [])],
        "outputSummary": [str(x) for x in p.get("output_summary", [])],
        "action": p.get("action") or "none",
    }
    if p.get("instrument_id"):
        out["instrument"] = instrument_json(repo.get_instrument(conn, str(p["instrument_id"])))
    if p.get("votes"):
        out["votes"] = list(p["votes"])
    return out
