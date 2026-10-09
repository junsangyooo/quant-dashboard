"""The daily watch of '3년 발굴' (PHASE2.md §4·§5): code only, AI 0.

Runs once a weekday after the 08:30 check (autotrade/jobs/schedule.py) for a ledger where the
rule has picks. With what the job downloaded first (adjusted closes, valuation ratios, filing
lists) it, in one transaction:

1. records new filings and routes them (T28): earnings -> '실적 지표 뽑기' (extract), the other
   filings of held picks -> '관련 있나 가리기' (screen), routine papers -> skipped. Filings from
   before the pick day were known when it was picked and are only recorded. A pick whose metric
   table is still empty gets its latest earnings filing read once (backfill), so its sell
   conditions are not 'unknown' until the next earnings season.
2. checks each held pick's sell conditions (level, streak) against the metric table. A hit asks
   for the two-step confirmation (sell-confirm), once per new data point.
3. looks for price shocks against the same market's index on adjusted closes: a day at -8% or
   20 trading days at -20% (T28); after one, the stock is not counted for 20 trading days.
   Sessions missed while the server was down are scanned too.
4. checks each candidate's buy conditions (price, valuation, metrics: all must hold). A hit asks
   for one buy confirmation, at most once a month for the same conditions.
5. redraws the rule's 'vs index' line (rule_daily): the picks' mean excess return over their
   market's index since each pick day (T24 score.py), a sold pick frozen at its sale.
6. scores the judgments whose 6/12/24/36-month day has come (autotrade/engine/scoring.py).

It queues work and keeps records; it never trades. The AI runner (python -m autotrade.jobs ai)
asks, and the discovery planner turns decisions into plans.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.domain.conditions import (
    ConditionError,
    buy_met,
    check,
    check_buy,
    condition_digest,
    parse_condition,
)
from autotrade.domain.instruments import Instrument, Market
from autotrade.domain.watch import Shock, classify_kr, classify_us, excess_path, find_shocks
from autotrade.engine import metric_table
from autotrade.market.calendar import CalendarRangeError, calendar_for
from autotrade.market.filings import FilingInfo
from autotrade.rules.discovery import RULE_ID, SCORE_BENCHMARK
from autotrade.timeutil import kst_date

JOB = "watch"
FILING_LOOKBACK = timedelta(days=120)  # first look: back to the latest earnings season
FILING_OVERLAP = timedelta(days=7)  # later looks: a week of overlap (dedup by receipt number)
SHOCK_LOOKBACK = timedelta(days=45)  # calendar days of closes before the scan for the 20-day line
FILINGS_SEEN = "watch.filings.{}"  # setting: the day the instrument's filings were last fetched
SOURCE_OF_MARKET = {Market.KR: "dart", Market.US: "edgar"}
HUNDRED = Decimal(100)
PP = Decimal("0.01")

Series = list[tuple[date, Decimal]]


@dataclass
class WatchInput:
    """What the job downloaded before its transaction (autotrade/jobs/tasks.py watch_job)."""

    adjusted: dict[str, Series] = field(default_factory=dict)  # Yahoo symbol -> closed sessions
    adjusted_errors: dict[str, str] = field(default_factory=dict)
    valuations: dict[str, dict[str, Decimal]] = field(default_factory=dict)  # instrument id
    valuation_errors: dict[str, str] = field(default_factory=dict)
    filings: dict[str, list[FilingInfo]] = field(default_factory=dict)  # instrument id
    filing_errors: dict[str, str] = field(default_factory=dict)
    source_states: dict[str, tuple[str, str | None]] = field(default_factory=dict)  # dart/edgar


@dataclass
class WatchOutcome:
    result: str  # 'ok' | 'partial' (a source failed) | 'nothing' (no picks)
    run_id: int | None
    tasks: list[dict[str, Any]]
    details: dict[str, Any]


# ── what to fetch ────────────────────────────────────────────────────────────────────────────


def watched_picks(conn: sqlite3.Connection, ledger_id: str) -> list[ai_repo.PickRow]:
    """Open picks (held, candidate) of the rule in this ledger."""
    return ai_repo.picks_of(conn, ledger_id, RULE_ID, ai_repo.OPEN_PICK)


def scored_picks(conn: sqlite3.Connection, ledger_id: str) -> list[ai_repo.PickRow]:
    """Picks that are judgments with a price path: held now or sold."""
    return ai_repo.picks_of(conn, ledger_id, RULE_ID, ("held", "sold"))


def filing_window(conn: sqlite3.Connection, pick: ai_repo.PickRow, today: date) -> date:
    """Start of the filing look for a pick (the end is today)."""
    seen = repo.get_setting(conn, FILINGS_SEEN.format(pick.instrument_id))
    first = pick.picked_on - FILING_LOOKBACK
    if seen is None:
        return first
    return max(first, date.fromisoformat(seen) - FILING_OVERLAP)


def last_checked(conn: sqlite3.Connection, ledger_id: str) -> dict[str, date]:
    """The latest session per market the previous watch looked at."""
    for run in reversed(ai_repo.job_runs_of(conn, JOB, ledger_id, limit=10)):
        through = run.details.get("checked_through")
        if run.result in ("ok", "partial") and isinstance(through, dict):
            return {str(k): date.fromisoformat(str(v)) for k, v in through.items()}
    return {}


def adjusted_start(conn: sqlite3.Connection, ledger_id: str, today: date) -> date:
    """Closes are needed from the earliest pick day (the 'vs index' line and the scores) and a
    shock window before the oldest unchecked session."""
    days = [p.picked_on for p in scored_picks(conn, ledger_id)]
    days += [p.picked_on for p in watched_picks(conn, ledger_id)]
    days += list(last_checked(conn, ledger_id).values())
    return min([*days, today]) - SHOCK_LOOKBACK


def needs_valuation(pick: ai_repo.PickRow) -> bool:
    return pick.status == "candidate" and any(c.get("type") == "valuation" for c in pick.buy)


# ── the watch ────────────────────────────────────────────────────────────────────────────────


def _session_after(market: Market, d: date, n: int) -> date:
    """The n-th trading day after d (weekdays past the end of the holiday calendar)."""
    cal = calendar_for(market)
    out = d
    for _ in range(n):
        try:
            out = cal.next_trading_day(out)
        except CalendarRangeError:
            out += timedelta(days=1)
            while out.weekday() >= 5:
                out += timedelta(days=1)
    return out


def _kind_of(info: FilingInfo) -> str:
    return classify_kr(info.title) if info.source == "dart" else classify_us(info.form, info.items)


def _record_filings(
    conn: sqlite3.Connection,
    pick: ai_repo.PickRow,
    infos: Sequence[FilingInfo],
    at: datetime,
    tasks: list[dict[str, Any]],
) -> dict[str, int]:
    counts = {"new": 0, "queued": 0}
    earnings: list[tuple[FilingInfo, int]] = []
    for info in sorted(infos, key=lambda f: (f.filed_on, f.source_ref)):
        kind = _kind_of(info)
        status = "skipped" if kind == "skipped" or info.filed_on < pick.picked_on else "queued"
        if status == "queued" and kind == "other" and pick.status != "held":
            status = "skipped"  # a candidate's news waits for the buy confirmation
        filing_id, inserted = ai_repo.insert_filing(
            conn,
            instrument_id=pick.instrument_id,
            source=info.source,
            source_ref=info.source_ref,
            form=info.form,
            items=info.items,
            title=info.title,
            filed_on=info.filed_on,
            url=info.url,
            kind=kind,
            status=status,
            at=at,
        )
        if kind == "earnings":
            earnings.append((info, filing_id))
        if not inserted:
            continue
        counts["new"] += 1
        if status != "queued":
            continue
        task_kind = "extract" if kind == "earnings" else "screen"
        key = (
            f"extract:{filing_id}"
            if task_kind == "extract"
            else f"screen:{pick.pick_id}:{filing_id}"
        )
        task_id, created = ai_repo.enqueue_task(
            conn,
            kind=task_kind,
            ledger_id=pick.ledger_id,
            rule_id=pick.rule_id,
            trigger="filing",
            dedup_key=key,
            at=at,
            pick_id=pick.pick_id,
            filing_id=filing_id,
            detail={"title": info.title, "filed_on": info.filed_on.isoformat()},
        )
        if created:
            counts["queued"] += 1
            tasks.append({"task_id": task_id, "kind": task_kind, "pick": pick.instrument_id})
    _backfill(conn, pick, earnings, at, tasks, counts)
    return counts


def _backfill(
    conn: sqlite3.Connection,
    pick: ai_repo.PickRow,
    earnings: list[tuple[FilingInfo, int]],
    at: datetime,
    tasks: list[dict[str, Any]],
    counts: dict[str, int],
) -> None:
    """Read the latest earnings filing once when the company has no metric yet."""
    if not earnings or ai_repo.metric_values(conn, pick.instrument_id):
        return
    if ai_repo.extract_tasks_of_instrument(conn, pick.instrument_id):
        return
    info, filing_id = earnings[-1]
    task_id, created = ai_repo.enqueue_task(
        conn,
        kind="extract",
        ledger_id=pick.ledger_id,
        rule_id=pick.rule_id,
        trigger="backfill",
        dedup_key=f"extract:{filing_id}",
        at=at,
        pick_id=pick.pick_id,
        filing_id=filing_id,
        detail={"title": info.title, "filed_on": info.filed_on.isoformat()},
    )
    if created:
        ai_repo.set_filing_status(conn, filing_id, "queued")
        counts["queued"] += 1
        tasks.append({"task_id": task_id, "kind": "extract", "pick": pick.instrument_id})


def _seen_triggers(conn: sqlite3.Connection, pick_id: int) -> set[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    for task in ai_repo.tasks_of(conn, kind="sell-confirm", pick_id=pick_id):
        for t in task.detail.get("triggers", []):
            if isinstance(t, dict) and t.get("kind") == "condition":
                seen.add((str(t.get("digest")), str(t.get("period"))))
    return seen


def condition_hits(conn: sqlite3.Connection, pick: ai_repo.PickRow) -> list[dict[str, Any]]:
    """The sell conditions of a pick that the metric table meets now."""
    hits: list[dict[str, Any]] = []
    for i, data in enumerate(pick.invalidate):
        try:
            cond = parse_condition(data)
        except ConditionError:
            continue  # a condition the dictionary no longer knows: the review rewrites it
        if not cond.is_sell_metric or cond.metric is None:
            continue
        chk = check(cond, metric_table.observations(conn, pick.instrument_id, cond.metric))
        if chk.verdict == "hit":
            hits.append(
                {
                    "kind": "condition",
                    "index": i,
                    "digest": condition_digest(data),
                    "period": chk.period,
                    "value": None if chk.value is None else str(chk.value),
                    "condition": data,
                }
            )
    return hits


def _shock_trigger(
    cfg: Config,
    pick: ai_repo.PickRow,
    inst: Instrument,
    data: WatchInput,
    checked: dict[str, date],
) -> tuple[dict[str, Any] | None, Shock | None]:
    stock = data.adjusted.get(inst.yahoo_symbol)
    index = data.adjusted.get(pick.benchmark)
    if not stock or not index:
        return None, None
    prev = checked.get(inst.market.value)
    after = pick.picked_on if prev is None else max(prev, pick.picked_on)
    shocks = find_shocks(
        stock,
        index,
        day_line=cfg.shock_day,
        line_20d=cfg.shock_20d,
        window=cfg.shock_window,
        after=after,
        blocked_until=pick.shock_until,
    )
    if not shocks:
        return None, None
    last = shocks[-1]
    trigger = {
        "kind": "shock",
        "on": last.on.isoformat(),
        "shock": last.kind,
        "day_rel": str(last.day_rel.quantize(Decimal("0.0001"))),
        "rel20": None if last.rel20 is None else str(last.rel20.quantize(Decimal("0.0001"))),
        "missed": [s.on.isoformat() for s in shocks[:-1]],
    }
    return trigger, last


def _sell_checks(
    conn: sqlite3.Connection,
    cfg: Config,
    pick: ai_repo.PickRow,
    inst: Instrument,
    data: WatchInput,
    checked: dict[str, date],
    at: datetime,
    tasks: list[dict[str, Any]],
) -> None:
    if pick.decision is not None:
        return  # a decision waits for its plan
    open_confirms = ai_repo.tasks_of(
        conn, kind="sell-confirm", statuses=("pending", "running", "failed"), pick_id=pick.pick_id
    )
    seen = _seen_triggers(conn, pick.pick_id)
    triggers = [t for t in condition_hits(conn, pick) if (t["digest"], t["period"]) not in seen]
    shock_trigger, shock = _shock_trigger(cfg, pick, inst, data, checked)
    if shock is not None and shock_trigger is not None:
        until = _session_after(inst.market, shock.on, cfg.shock_window - 1)
        ai_repo.update_pick(conn, pick.pick_id, at, shock_until=until)
        triggers.append(shock_trigger)
    if not triggers or open_confirms:
        return  # nothing new, or a confirmation is already on its way (it reads the latest data)
    today = kst_date(at)
    task_id, created = ai_repo.enqueue_task(
        conn,
        kind="sell-confirm",
        ledger_id=pick.ledger_id,
        rule_id=pick.rule_id,
        trigger="shock" if all(t["kind"] == "shock" for t in triggers) else "condition",
        dedup_key=f"sell-confirm:{pick.pick_id}:{today.isoformat()}",
        at=at,
        pick_id=pick.pick_id,
        detail={"triggers": triggers},
    )
    if created:
        tasks.append({"task_id": task_id, "kind": "sell-confirm", "pick": pick.instrument_id})


def latest_close(data: WatchInput, inst: Instrument) -> tuple[date, Decimal] | None:
    series = data.adjusted.get(inst.yahoo_symbol)
    return series[-1] if series else None


def buy_checks(
    conn: sqlite3.Connection,
    pick: ai_repo.PickRow,
    price: Decimal | None,
    ratios: dict[str, Decimal],
) -> list[Any]:
    out = []
    for data in pick.buy:
        try:
            cond = parse_condition(data)
        except ConditionError:
            continue
        obs = (
            metric_table.observations(conn, pick.instrument_id, cond.metric)
            if cond.type in ("level", "streak") and cond.metric
            else []
        )
        out.append(check_buy(cond, price, ratios, obs))
    return out


def buy_gap(pick: ai_repo.PickRow, price: Decimal) -> dict[str, str] | None:
    """How near a candidate is to its buy price (the 'until the buy price' bar): progress from
    the pick day's price (0) to the line (100), and the gap in % still to go."""
    for data in pick.buy:
        if data.get("type") != "price":
            continue
        try:
            cond = parse_condition(data)
        except ConditionError:
            continue
        if cond.value is None or cond.op is None or cond.value <= 0:
            continue
        line, start = cond.value, pick.picked_price
        span = start - line if cond.op in ("<", "<=") else line - start
        gone = start - price if cond.op in ("<", "<=") else price - start
        progress = HUNDRED if span <= 0 else max(Decimal(0), min(HUNDRED, gone * HUNDRED / span))
        return {
            "price": str(price),
            "line": str(line),
            "progress": str(progress.quantize(Decimal(1))),
            "gap_pct": str(((price / line - 1) * HUNDRED).quantize(Decimal("0.1"))),
        }
    return None


def _buy_check(
    conn: sqlite3.Connection,
    pick: ai_repo.PickRow,
    inst: Instrument,
    data: WatchInput,
    at: datetime,
    tasks: list[dict[str, Any]],
    gaps: dict[str, dict[str, str]],
) -> None:
    if pick.decision is not None or not pick.buy:
        return
    close = latest_close(data, inst)
    if close is not None:
        gap = buy_gap(pick, close[1])
        if gap is not None:
            gaps[str(pick.pick_id)] = gap
    checks = buy_checks(
        conn, pick, None if close is None else close[1], data.valuations.get(inst.instrument_id, {})
    )
    if not buy_met(checks):
        return
    today = kst_date(at)
    task_id, created = ai_repo.enqueue_task(
        conn,
        kind="buy-confirm",
        ledger_id=pick.ledger_id,
        rule_id=pick.rule_id,
        trigger="buy-price",
        dedup_key=f"buy-confirm:{pick.pick_id}:{today:%Y-%m}:{condition_digest(pick.buy)}",
        at=at,
        pick_id=pick.pick_id,
        detail={
            "close": None
            if close is None
            else {"date": close[0].isoformat(), "price": str(close[1])},
            "checks": [
                {"condition": c.condition.type, "verdict": c.verdict, "value": str(c.value)}
                for c in checks
            ],
        },
    )
    if created:
        tasks.append({"task_id": task_id, "kind": "buy-confirm", "pick": pick.instrument_id})


def excess_paths(
    conn: sqlite3.Connection, ledger_id: str, adjusted: dict[str, Series]
) -> dict[int, list[tuple[date, Decimal]]]:
    """Each held or sold pick's excess over its index since the pick day (a fraction)."""
    out: dict[int, list[tuple[date, Decimal]]] = {}
    for pick in scored_picks(conn, ledger_id):
        inst = repo.get_instrument(conn, pick.instrument_id)
        stock, index = adjusted.get(inst.yahoo_symbol), adjusted.get(pick.benchmark)
        if not stock or not index:
            continue
        path = excess_path(stock, index, pick.picked_on, pick.closed_on)
        if path:
            out[pick.pick_id] = path
    return out


def vs_index_points(
    conn: sqlite3.Connection, ledger_id: str, adjusted: dict[str, Series]
) -> list[tuple[date, Decimal, int]]:
    """(date, mean excess in %p, picks counted) on every session date since the first pick."""
    paths = list(excess_paths(conn, ledger_id, adjusted).values())
    if not paths:
        return []
    dates = sorted({d for path in paths for d, _ in path})
    points: list[tuple[date, Decimal, int]] = []
    cursors = [0] * len(paths)
    current: list[Decimal | None] = [None] * len(paths)
    for d in dates:
        for i, path in enumerate(paths):
            while cursors[i] < len(path) and path[cursors[i]][0] <= d:
                current[i] = path[cursors[i]][1]
                cursors[i] += 1
        values = [v for v in current if v is not None]
        mean = sum(values, Decimal(0)) / len(values) * HUNDRED
        points.append((d, mean.quantize(PP), len(values)))
    return points


def run_watch(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    at: datetime,
    data: WatchInput,
    started_at: datetime | None = None,
) -> WatchOutcome:
    """The whole watch in the caller's transaction."""
    # Imported here: scoring reads the same closes and is a sibling engine module.
    from autotrade.engine.scoring import score_due

    today = kst_date(at)
    picks = watched_picks(conn, ledger_id)
    for source, (state, detail) in sorted(data.source_states.items()):
        ai_repo.set_source_state(conn, source, state, detail, at)
    tasks: list[dict[str, Any]] = []
    filings = {"new": 0, "queued": 0}
    checked = last_checked(conn, ledger_id)
    for pick in picks:
        infos = data.filings.get(pick.instrument_id)
        if infos is None:
            continue  # the source did not answer: look again next time from the same day
        counts = _record_filings(conn, pick, infos, at, tasks)
        filings = {k: filings[k] + counts[k] for k in filings}
        repo.set_setting(conn, FILINGS_SEEN.format(pick.instrument_id), today.isoformat(), at)
    gaps: dict[str, dict[str, str]] = {}
    for pick in watched_picks(conn, ledger_id):
        inst = repo.get_instrument(conn, pick.instrument_id)
        if pick.status == "held":
            _sell_checks(conn, cfg, pick, inst, data, checked, at, tasks)
        else:
            _buy_check(conn, pick, inst, data, at, tasks, gaps)
    through = dict(checked)
    for market in (Market.KR, Market.US):
        bench = data.adjusted.get(SCORE_BENCHMARK[market.value])
        if bench:
            through[market.value] = bench[-1][0]
    points = vs_index_points(conn, ledger_id, data.adjusted)
    latest = {
        str(pid): str((path[-1][1] * HUNDRED).quantize(PP))
        for pid, path in excess_paths(conn, ledger_id, data.adjusted).items()
    }
    for i, (d, value, n) in enumerate(points):
        extra: dict[str, Any] = {"n": n}
        if i == len(points) - 1:
            extra["picks"] = latest  # each pick's excess in %p (the weakest-pick choice reads it)
        ai_repo.upsert_rule_daily(conn, ledger_id, RULE_ID, d, value, extra, at)
    scored = score_due(conn, ledger_id, data.adjusted, at)
    failed = {k: v for k, v in data.source_states.items() if v[0] != "ok"}
    result = "partial" if failed or data.adjusted_errors else ("ok" if picks else "nothing")
    details: dict[str, Any] = {
        "picks": len(picks),
        "checked_through": {k: v.isoformat() for k, v in sorted(through.items())},
        "filings": filings,
        "tasks": tasks,
        "vs_index": None if not points else str(points[-1][1]),
        "scored": scored,
        "buy_gaps": gaps,
    }
    errors = {
        **{f"adjusted:{k}": v for k, v in data.adjusted_errors.items()},
        **{f"valuation:{k}": v for k, v in data.valuation_errors.items()},
        **{f"filings:{k}": v for k, v in data.filing_errors.items()},
    }
    if errors:
        details["errors"] = errors
    run_id = ai_repo.insert_job_run(
        conn,
        job=JOB,
        ledger_id=ledger_id,
        run_date=today,
        started_at=started_at or at,
        ended_at=at,
        result=result,
        error=None if not errors else "; ".join(sorted(errors))[:500],
        details=details,
    )
    return WatchOutcome(result, run_id, tasks, details)
