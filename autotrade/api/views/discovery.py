"""The AI rule '3년 발굴' on the screens (CONTRACT.md, Vault 5-설계/화면-맞춤.md ②③).

- RuleCard: the same frame as the fixed rule with other contents. The gauge is the sell-condition
  gauge (D34): its needle is the held pick nearest to one of its sell conditions, 0 on the pick
  day's value and 100 on the line; each pick's row shows how far it has come and what is left.
  The 'vs index' line is the picks' mean excess over their market's index (rule_daily, the
  scoring's arithmetic).
- FlowDisplay: the four lanes of the rule definition (autotrade/rules/discovery.py) with the
  engine's '지금' values; edges taken today are solid.
- AiJudgment: built from the event the AI runner recorded (autotrade/ai/flows.py).
- Health: the rows filings, ai-cli and metric-table, and their 'to do' items. The AI runner
  runs in its own cron line with its own environment, so what it is (its gate, the CLI it found,
  its DART key, the task it is asking) comes from its heartbeat (ai_runner), never from this
  process's environment.

Numbers, dates and enums only; the screen writes the words (CONTRACT.md 원칙). What is left
before a line is a number and its unit (`margin`); a metric is its dictionary key and the company's
own parameter word (`metric`). The screen phrases both ('2.3%p', '3.1조', '$350M', '2분기',
'AI 매출').
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
from autotrade.domain.conditions import (
    Check,
    ConditionError,
    Distance,
    Observation,
    check,
    distance,
    parse_condition,
)
from autotrade.domain.instruments import Instrument, Market
from autotrade.domain.money import ZERO
from autotrade.domain.periods import PeriodError, parse_period
from autotrade.engine import metric_table
from autotrade.engine.reviews import DISCOVERY_MONTHS, rule_active
from autotrade.market.calendar import CalendarRangeError, ExchangeCalendar, calendar_for
from autotrade.rules.discovery import RULE_ID
from autotrade.rules.model import RuleDef
from autotrade.timeutil import at_kst, kst_date

if TYPE_CHECKING:
    from autotrade.api.views.context import LedgerContext

COLOR = 1  # the second rule's colour
AI_EVENT_KINDS = ("discovery", "ai-buy", "ai-sell", "ai-check", "monthly-review")
PERIOD_UNIT = {"quarter": "quarter", "fquarter": "quarter", "month": "month", "year": "year"}
HUNDRED = Decimal(100)
# Trading days an AI-rule source may stay dead before the header counts it: the 작동 screen shows
# it from the first miss, but the nightly DART maintenance must not flip the header.
HEADER_GRACE = 1
FILING_SOURCES = (("dart", Market.KR), ("edgar", Market.US))
# The AI queue on the health screen (audit E10). A call has no time limit (ops notes §7):
# past CALL_SLOW it shows as a yellow card, nothing stops it. A task due for QUEUE_DUE_LATE and
# not taken, or open for QUEUE_OPEN_LONG, shows the queue waiting, with why (QueueCause).
CALL_SLOW = timedelta(hours=1)
QUEUE_DUE_LATE = timedelta(hours=2)
QUEUE_OPEN_LONG = timedelta(days=3)
RUNNER_SILENT = timedelta(minutes=30)  # cron calls the runner every 5 minutes


def trading_days_since(cal: ExchangeCalendar, since: datetime, now: datetime) -> int:
    """Trading days of the market after the day of `since` up to the day of `now`, in its own
    dates (a Friday success is one trading day old on Monday; 한글날 does not count)."""
    start = since.astimezone(cal.tz).date()
    end = now.astimezone(cal.tz).date()
    try:
        return len(cal.trading_days(start, end))
    except CalendarRangeError:  # outside the holiday table: weekdays
        return sum(
            1 for i in range(1, (end - start).days + 1) if (start + timedelta(i)).weekday() < 5
        )


def margin(d: Distance, periods_kind: str | None) -> dict[str, Any]:
    """What is left before the line, as a number and its unit (CONTRACT.md Margin): pp1 for a
    percentage, won or dollars for money, the ratio, or the periods left."""
    if d.periods_left is not None:
        return {
            "unit": PERIOD_UNIT.get(periods_kind or "quarter", "quarter"),
            "value": d.periods_left,
        }
    m = abs(d.margin or ZERO)
    if d.unit == "%":
        return {"unit": "pp", "value": fmt.pp1(m / HUNDRED)}
    if d.unit == "KRW":
        return {"unit": "KRW", "value": fmt.krw(m)}
    if d.unit == "USD":
        return {"unit": "USD", "value": fmt.usd(m)}
    if d.unit == "x":
        return {"unit": "x", "value": float(m.quantize(Decimal("0.01")))}
    return {"unit": "count", "value": float(m.normalize())}


def metric_ref(key: str) -> dict[str, Any]:
    """A metric as its dictionary key and the company's own word ('segment_backlog', '지상방산')."""
    base, _, param = key.partition(":")
    return {"key": base, "param": param} if param else {"key": base}


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

    def nearest(
        self, pick: ai_repo.PickRow
    ) -> tuple[Distance, dict[str, Any], dict[str, Any]] | None:
        """(distance, metric, margin) of the pick's sell condition nearest its line."""
        best: tuple[Distance, dict[str, Any], dict[str, Any]] | None = None
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
            if best is None or d.progress > best[0].progress:
                best = (d, metric_ref(cond.metric), margin(d, kind))
        return best

    @cached_property
    def distances(self) -> dict[int, tuple[Distance, dict[str, Any], dict[str, Any]]]:
        out: dict[int, tuple[Distance, dict[str, Any], dict[str, Any]]] = {}
        for pick in self.held:
            found = self.nearest(pick)
            if found is not None:
                out[pick.pick_id] = found
        return out

    def gauge(self) -> dict[str, Any]:
        needle = None
        if self.distances:
            pick_id, (d, metric, left) = max(
                self.distances.items(), key=lambda kv: kv[1][0].progress
            )
            pick = next(p for p in self.held if p.pick_id == pick_id)
            needle = {
                "instrument": instrument_json(self.instrument(pick.instrument_id)),
                "progress": float(d.progress.quantize(Decimal(1))),
                "metric": metric,
                "margin": left,
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
                d, metric, left = found
                row.update(
                    {
                        "progress": float(d.progress.quantize(Decimal(1))),
                        "metric": metric,
                        "margin": left,
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
        active = status in ("holiday", "quote-wait")
        return {
            "kind": "exceptions",
            "items": ["holiday", "quote-wait"],
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
                pick_id, (d, _metric, left) = max(
                    self.distances.items(), key=lambda kv: kv[1][0].progress
                )
                pick = next(p for p in self.held if p.pick_id == pick_id)
                rows = [
                    self._instrument_row(
                        pick.instrument_id,
                        progress=float(d.progress.quantize(Decimal(1))),
                        margin=left,
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
                rows.append(self._instrument_row(stored[0].instrument_id, period=periods[-1]))
            rows += [self._kv("metrics", len(stored)), self._kv("tokens", call.tokens)]
            return self._block("now-last", rows, kst_date(call.started_at))
        if nid == "data":
            latest: dict[str, ai_repo.MetricValueRow] = {}
            for r in sorted(self._metric_rows(), key=lambda r: r.extracted_at):
                latest[r.instrument_id] = r
            recent = sorted(latest.values(), key=lambda r: r.extracted_at, reverse=True)
            rows = [
                self._instrument_row(r.instrument_id, period=r.period) for r in recent[: self.SHOW]
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
                    margin={"unit": "pct", "value": float(Decimal(g["gap_pct"]))},
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

    def _dead(self, since: datetime | None, market: Market) -> bool:
        """No success for more than HEADER_GRACE trading days of the market."""
        if since is None:
            return False
        return trading_days_since(calendar_for(market), since, self.ctx.now) > HEADER_GRACE

    def header_causes(self) -> int:
        """The AI-rule sources dead for more than a trading day, as causes of the header's
        '점검 n' (CONTRACT.md ShellResponse): each filings source (DART, EDGAR) and the AI CLI.
        A source that never answered is dead since its first attempt."""
        if not self.shown:
            return 0
        count = 0
        first_watch = ai_repo.first_job_run_at(self.conn, "watch", self.ctx.ledger_id)
        for source, market in FILING_SOURCES:
            row = ai_repo.source_state(self.conn, source)
            if (
                row is not None
                and row.state != "ok"
                and self._dead(row.ok_at or first_watch, market)
            ):
                count += 1
        last = ai_repo.last_calls(self.conn, 1)
        runner = self.runner
        if runner is not None and runner.enabled and runner.cli is None:
            if self._dead(runner.cli_missing_since, Market.KR):  # no CLI to call at all
                count += 1
        elif last and not last[0].ok:
            good = ai_repo.last_ok_call(self.conn)
            since = (
                (good.finished_at or good.started_at) if good else ai_repo.first_call_at(self.conn)
            )
            if self._dead(since, Market.KR):
                count += 1
        return count

    @cached_property
    def runner(self) -> ai_repo.RunnerRow | None:
        """The AI runner's heartbeat (None: it never ran)."""
        return ai_repo.runner_state(self.conn)

    def _filing_states(self) -> dict[str, str]:
        """DART and EDGAR as the watch last found them; DART is 'no-key' when the AI runner has
        no key to read Korean filing texts with (its cron line, not the tick's)."""
        states: dict[str, str] = {}
        for source, _ in FILING_SOURCES:
            row = ai_repo.source_state(self.conn, source)
            states[source] = "unknown" if row is None else row.state
        runner = self.runner
        if runner is not None and not runner.dart_key:
            states["dart"] = "no-key"
        return states

    def sources(self) -> list[dict[str, Any]]:
        if not self.shown:
            return []
        now = self.ctx.now
        rows: list[dict[str, Any]] = []
        states = {s: ai_repo.source_state(self.conn, s) for s in ("dart", "edgar")}
        known = {s: r for s, r in states.items() if r is not None}
        oks = [r.ok_at for r in known.values() if r.ok_at is not None]
        shown = self._filing_states()
        if not known and shown["dart"] != "no-key":
            state = "unknown"
        elif "maintenance" in shown.values():
            state = "maintenance"
        elif any(v not in ("ok", "unknown") for v in shown.values()):
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
                "extra": shown,
            }
        )
        good = ai_repo.last_ok_call(self.conn)
        last = ai_repo.last_calls(self.conn, 1)
        runner = self.runner
        if runner is not None and runner.cli is None:
            cli_state = "stale"  # no CLI to call: a source down (audit E1)
        else:
            cli_state = "unknown" if not last else ("fresh" if last[0].ok else "stale")
        extra: dict[str, Any] = {
            "monthTokens": month_tokens(self.conn, now),
            "budget": self.ctx.cfg.ai_monthly_budget,
            # The runner's own gate (AUTOTRADE_AI_CALLS on its cron line); 0 before it ran.
            "enabled": int(runner is not None and runner.enabled),
            "due": len(ai_repo.due_tasks(self.conn, now, self.ctx.cfg.ai_max_attempts)),
            "cli": "unknown" if runner is None else ("missing" if runner.cli is None else "ok"),
        }
        if runner is not None:
            extra["lastRunAt"] = fmt.iso(runner.started_at)
            if runner.task_kind is not None and runner.task_started_at is not None:
                extra["running"] = runner.task_kind
                extra["runningSince"] = fmt.iso(runner.task_started_at)
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
                "extra": extra,
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
        stuck = ai_repo.stuck_tasks(self.conn, cfg.ai_max_attempts, self.ctx.ledger_id)
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
        out += self._runner_todos()
        shown = self._filing_states()
        for source, market in FILING_SOURCES:
            row = ai_repo.source_state(self.conn, source)
            state = shown[source]
            if state in ("ok", "unknown"):
                continue
            facts: dict[str, Any] = {"source": source, "market": market.value, "state": state}
            if row is not None and row.ok_at is not None:  # values only: no key when never
                facts["since"] = fmt.iso(row.ok_at)
            # A missing key needs a person (the cron line); anything else the watch retries.
            action: dict[str, Any] = (
                {"kind": "manual"}
                if state == "no-key"
                else {"kind": "auto-retry", "at": fmt.iso(self.ctx.next_check)}
            )
            out.append(
                {
                    "id": f"filings:{source}",
                    "severity": "red",  # a fault, like stale quotes
                    "kind": "filings",
                    "facts": facts,
                    "action": action,
                    "effect": "other",
                }
            )
        return out

    def _runner_todos(self) -> list[dict[str, Any]]:
        """What the AI runner's heartbeat shows: no CLI (red), a call running long, the queue
        waiting (yellow). A call is never stopped (no time limit): the card only shows it."""
        out: list[dict[str, Any]] = []
        now, runner = self.ctx.now, self.runner
        if runner is not None and runner.enabled and runner.cli is None:
            facts: dict[str, Any] = {"reason": "cli-missing"}
            if runner.cli_missing_since is not None:
                facts["since"] = fmt.iso(runner.cli_missing_since)
            out.append(self._ai_todo("ai-cli:missing", "red", facts))
        slow = (
            runner is not None
            and runner.ended_at is None
            and runner.task_started_at is not None
            and now - runner.task_started_at > CALL_SLOW
        )
        if runner is not None and slow and runner.task_started_at is not None:
            out.append(
                self._ai_todo(
                    f"ai-cli:running:{runner.task_id}",
                    "yellow",
                    {
                        "reason": "call-running",
                        "taskKind": runner.task_kind or "",
                        "since": fmt.iso(runner.task_started_at),
                    },
                )
            )
        waiting = [
            t
            for t in ai_repo.open_tasks(
                self.conn, self.ctx.cfg.ai_max_attempts, ledger_id=self.ctx.ledger_id
            )
            if t.status != "running"
            and (now - t.not_before > QUEUE_DUE_LATE or now - t.created_at > QUEUE_OPEN_LONG)
        ]
        if waiting:
            quiet = runner is None or now - runner.started_at > RUNNER_SILENT
            if runner is not None and runner.ended_at is None and quiet:
                cause = "busy"  # one run holds the runner's lock (a long or hung call)
            elif quiet:
                cause = "stopped"  # the runner does not run (cron, or it fails to start)
            elif runner is not None and not runner.enabled:
                cause = "off"  # AUTOTRADE_AI_CALLS is not on
            elif runner is not None and runner.cli is None:
                cause = "cli-missing"
            else:
                cause = "deferred"  # sources down, a key missing, the evidence not in yet
            out.append(
                self._ai_todo(
                    "ai-cli:queue",
                    "yellow",
                    {
                        "reason": "queue-waiting",
                        "count": len(waiting),
                        "since": fmt.iso(min(t.created_at for t in waiting)),
                        "cause": cause,
                    },
                )
            )
        return out

    @staticmethod
    def _ai_todo(todo_id: str, severity: str, facts: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": todo_id,
            "severity": severity,
            "kind": "ai-cli",
            "facts": facts,
            "action": {"kind": "manual"},
            "effect": "other",
        }


# JudgmentItem keys whose value is a count (CONTRACT.md); the others carry a date, a code or an
# instrument. Anything else in a payload is not served.
COUNT_KEYS = frozenset(
    {
        "filings",
        "news",
        "picks",
        "held",
        "candidates",
        "checks",
        "hold",
        "weaken",
        "invalidated",
        "rewritten",
        "new-picks",
        "expired",
    }
)


def judgment_item(conn: sqlite3.Connection, item: Any) -> dict[str, Any] | None:
    """One item of a judgment's input or output line, as data (CONTRACT.md JudgmentItem)."""
    if not isinstance(item, dict) or not isinstance(item.get("key"), str):
        return None
    key = item["key"]
    if key in ("instrument", "sold", "bought") and item.get("instrument_id"):
        inst = repo.get_instrument(conn, str(item["instrument_id"]))
        return {"key": key, "instrument": instrument_json(inst)}
    if key in COUNT_KEYS:
        return {"key": key, "value": int(item.get("value") or 0)}
    if key == "shock":
        return {"key": key, "date": str(item.get("date")), "value": float(item.get("value") or 0)}
    if key == "filing":
        return {"key": key, "date": str(item.get("date"))}
    if key == "condition":
        return {"key": key, "value": int(item.get("value") or 0)}
    if key == "month":
        return {"key": key, "value": str(item.get("value"))}
    if key == "review":
        out: dict[str, Any] = {"key": key, "value": str(item.get("value"))}
        if item.get("months"):
            out["months"] = int(item["months"])
        return out
    if key == "cost":
        return {"key": key, "value": float(item.get("value") or 0)}
    if key == "slot-full":
        return {"key": key}
    return None


def judgment(conn: sqlite3.Connection, ev: EventRow) -> dict[str, Any]:
    """CONTRACT.md AiJudgment from the event the AI runner recorded: codes, numbers, dates and
    instruments only. The model's own words stay in the record (and in ai_calls)."""
    p = ev.payload
    lines = {
        side: [x for x in (judgment_item(conn, i) for i in p.get(side) or []) if x is not None]
        for side in ("input", "output")
    }
    out: dict[str, Any] = {
        "at": fmt.iso(ev.occurred_at),
        "trigger": p.get("trigger") or ("monthly" if ev.kind == "monthly-review" else "discovery"),
        "model": p.get("model") or ("opus" if ev.kind == "discovery" else "sonnet"),
        "tokens": int(p.get("tokens") or 0),
        "verdict": p.get("verdict") or "hold",
        "action": p.get("action") or "none",
        "input": lines["input"],
        "output": lines["output"],
    }
    if p.get("instrument_id"):
        out["instrument"] = instrument_json(repo.get_instrument(conn, str(p["instrument_id"])))
    if p.get("votes"):
        out["votes"] = list(p["votes"])
    return out
