"""The questions of '3년 발굴', one flow per task kind (PHASE2.md §6·§7, D27·D30·D31·D35~D37).

  kind            model (effort)   calls  what the answer does
  extract         haiku            1      metric values into the metric table (T27)
  screen          haiku            1      'relevant' -> a sell confirmation (filing)
  sell-confirm    sonnet (low)     2      both '반증' -> sell (D27); else hold, recorded
  buy-confirm     sonnet (low)     1      '근거 있음' -> buy, or a switch question when no slot
  monthly-review  sonnet (low)     1      verdict, sell conditions rewritten; '반증' or two months
                                          of '약화' -> a sell confirmation
  discovery       opus + web       1      new picks (same amount), candidates with buy conditions
  switch          sonnet (low)     2      both '바꾼다' and beating the code's costs -> switch (D37)

A flow prepares (database reads and downloads: no transaction), the runner makes the calls, an
optional `after` step downloads what the answer needs (discovery prices), and `apply` writes the
effects in one transaction. Decisions only mark picks; the discovery planner
(autotrade/engine/discovery_plan.py) turns them into orders at the next stage time.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from autotrade.ai import packets as pk
from autotrade.ai.cli import CliCall, CliResult
from autotrade.ai.prompts import Prompt, load
from autotrade.ai.text import TEXT_LIMIT, focus, keywords
from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.domain import metrics
from autotrade.domain.conditions import ConditionError, condition_json, parse_condition
from autotrade.domain.instruments import MARKET_CURRENCY, Currency, Instrument, Kind, Market
from autotrade.domain.money import ZERO, round_half_up, round_won, trade_fee, usd_in_krw
from autotrade.domain.periods import PeriodError, parse_period
from autotrade.engine.tax import us_tax
from autotrade.market.filings import FilingInfo, FilingSourceError
from autotrade.market.service import MarketSources
from autotrade.rules.discovery import RULE_ID, SCORE_BENCHMARK
from autotrade.timeutil import kst_date

VERDICT = {"유지": "hold", "약화": "weaken", "반증": "invalidated"}
SEVERITY = {"invalidated": 3, "weaken": 2, "hold": 1}
RETRY_SOURCE = timedelta(hours=1)
# AiJudgment.trigger (autotrade/CONTRACT.md) of each task trigger
JUDGMENT_TRIGGER = {
    "shock": "shock",
    "condition": "condition",
    "filing": "filing",
    "backfill": "filing",
    "monthly": "monthly",
    "discovery": "discovery",
    "buy-price": "buy-price",
}


class FlowError(Exception):
    """The answer (or the data) cannot be used: the task fails and is tried again."""


class RetryLaterError(Exception):
    """A source is down: wait, without counting an attempt."""


class SkipTaskError(Exception):
    """The task no longer applies (the pick was sold, decided ...): cancelled, no call."""


@dataclass
class FlowEnv:
    conn: sqlite3.Connection
    cfg: Config
    sources: MarketSources
    at: datetime


@dataclass
class Prepared:
    calls: list[CliCall]
    packet: str
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Flow:
    kind: str
    prompt: str
    prepare: Callable[[FlowEnv, ai_repo.TaskRow], Prepared]
    apply: Callable[
        [FlowEnv, ai_repo.TaskRow, Prepared, list[CliResult], list[int]], dict[str, Any]
    ]
    after: Callable[[FlowEnv, ai_repo.TaskRow, Prepared, list[CliResult]], None] | None = None


def _call(
    prompt: Prompt,
    purpose: str,
    packet: str,
    model: str,
    effort: str | None = None,
    *,
    web: bool = False,
    schema: Mapping[str, Any] | None = None,
) -> CliCall:
    return CliCall(
        purpose=purpose,
        prompt=f"{prompt.steps}\n\n{packet}",
        system=prompt.system,
        schema=schema if schema is not None else prompt.schema,
        model=model,
        effort=effort,
        web=web,
    )


def _pick(env: FlowEnv, task: ai_repo.TaskRow) -> tuple[ai_repo.PickRow, Instrument]:
    if task.pick_id is None:
        raise SkipTaskError("the task has no pick")
    pick = ai_repo.get_pick(env.conn, task.pick_id)
    return pick, repo.get_instrument(env.conn, pick.instrument_id)


def _held(env: FlowEnv, task: ai_repo.TaskRow) -> tuple[ai_repo.PickRow, Instrument]:
    pick, inst = _pick(env, task)
    if pick.status != "held":
        raise SkipTaskError(f"the pick is {pick.status}")
    if pick.decision is not None:
        raise SkipTaskError(f"the pick already has a decision: {pick.decision}")
    return pick, inst


def _source(env: FlowEnv, name: str) -> Any:
    source = env.sources.dart if name == "dart" else env.sources.edgar
    if source is None:
        raise RetryLaterError(f"no {name} source configured")
    return source


def _filing_text(env: FlowEnv, filing: ai_repo.FilingRow) -> str:
    info = FilingInfo(
        filing.source,
        filing.source_ref,
        filing.form,
        filing.items,
        filing.title,
        filing.filed_on,
        filing.url,
    )
    try:
        text: str = _source(env, filing.source).fetch_text(info)
    except FilingSourceError as exc:
        raise RetryLaterError(f"{filing.source}: {exc}") from exc
    if not text.strip():
        raise FlowError(f"filing {filing.source_ref} has no text")
    return text


def _event(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    kind: str,
    payload: dict[str, Any],
    ref: str | None = None,
) -> int:
    ref = ref or f"ai:{task.task_id}"
    existing = repo.event_by_ref(env.conn, task.ledger_id, ref)
    if existing is not None:
        repo.update_event(env.conn, existing.event_id, env.at, payload=payload)
        return existing.event_id
    return repo.insert_event(
        env.conn,
        ledger_id=task.ledger_id,
        kind=kind,
        event_date=kst_date(env.at),
        occurred_at=env.at,
        rule_id=RULE_ID,
        status="done",
        payload=payload,
        ref=ref,
    )


def _judgment(
    task: ai_repo.TaskRow,
    results: Sequence[CliResult],
    call_ids: Sequence[int],
    *,
    verdict: str,
    action: str,
    instrument_id: str | None,
    inputs: list[str],
    outputs: list[str],
    votes: list[str] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "task_id": task.task_id,
        "kind": task.kind,
        "trigger": JUDGMENT_TRIGGER.get(task.trigger, "condition"),
        "instrument_id": instrument_id,
        "model": results[0].call.model if results else None,
        "tokens": sum(r.tokens for r in results),
        "verdict": verdict,
        "action": action,
        "input_summary": inputs,
        "output_summary": outputs,
        "call_ids": list(call_ids),
    }
    if votes is not None:
        out["votes"] = votes
    return out


def _text(value: Any, what: str) -> str:
    if not isinstance(value, str):
        raise FlowError(f"{what} is not text")
    return value


def _choice(value: Any, options: Mapping[str, str], what: str) -> str:
    if value not in options:
        raise FlowError(f"{what}: unexpected {value!r}")
    return options[value]


# ── extract ──────────────────────────────────────────────────────────────────────────────────

BASE_METRICS = ("revenue", "operating_income", "net_income")


def wanted_metrics(conn: sqlite3.Connection, instrument_id: str) -> list[str]:
    """The base income lines, every metric an open pick's conditions name, and the parts of the
    derived ones (op_margin needs operating_income and revenue)."""
    keys = set(BASE_METRICS)
    for pick in ai_repo.picks_by_instrument(conn, instrument_id):
        for data in (*pick.confirm, *pick.invalidate, *pick.buy):
            key = data.get("metric")
            if data.get("type") not in ("level", "streak") or not isinstance(key, str):
                continue
            try:
                d, _ = metrics.resolve(key)
            except metrics.MetricError:
                continue
            if d.formula is not None:
                keys.update(d.formula)
            else:
                keys.add(key)
    return sorted(keys)


def prepare_extract(env: FlowEnv, task: ai_repo.TaskRow) -> Prepared:
    if task.filing_id is None:
        raise SkipTaskError("no filing")
    filing = ai_repo.get_filing(env.conn, task.filing_id)
    inst = repo.get_instrument(env.conn, filing.instrument_id)
    wanted = wanted_metrics(env.conn, inst.instrument_id)
    text = _filing_text(env, filing)
    body = focus(text, keywords(wanted))
    cut = " (길어서 뽑을 지표가 나오는 부분만 옮김)" if len(body) < len(text) else ""
    packet = pk.join(
        [
            "## 공시",
            f"- 회사: {inst.name} ({inst.instrument_id}) · 통화 {inst.currency.value}",
            f"- 공시: {filing.title} · {filing.filed_on} · {filing.source.upper()}",
        ],
        ["## 뽑을 지표"]
        + [f"- {k}: {metrics.label(k)} — {metrics.resolve(k)[0].description}" for k in wanted],
        [f"## 원문{cut}", body],
    )
    prompt = load("extract")
    call = _call(prompt, "extract", packet, "haiku", schema=prompt.with_metrics(wanted))
    return Prepared([call], packet, {"wanted": wanted, "instrument_id": inst.instrument_id})


def _metric_item(
    item: Mapping[str, Any], wanted: Sequence[str]
) -> tuple[str, str, Decimal, str, str]:
    key = item.get("metric")
    if key not in wanted:
        raise FlowError(f"metric {key!r} was not asked for")
    period = str(item.get("period"))
    parse_period(period)
    try:
        value = Decimal(str(item.get("value")))
    except InvalidOperation as exc:
        raise FlowError(f"{key}: value is not a number") from exc
    if not value.is_finite():
        raise FlowError(f"{key}: value is not finite")
    unit = str(item.get("unit"))
    if not metrics.unit_fits(str(key), unit):
        raise FlowError(f"{key} is not measured in {unit}")
    return str(key), period, value, unit, str(item.get("quote") or "")[:300]


def apply_extract(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    prepared: Prepared,
    results: list[CliResult],
    call_ids: list[int],
) -> dict[str, Any]:
    output = results[0].output
    items = output.get("metrics")
    if not isinstance(items, list):
        raise FlowError("no metrics list")
    stored: list[str] = []
    dropped: list[str] = []
    for item in items:
        try:
            key, period, value, unit, quote = _metric_item(item, prepared.context["wanted"])
        except (FlowError, PeriodError) as exc:
            dropped.append(str(exc))
            continue
        ai_repo.upsert_metric_value(
            env.conn,
            instrument_id=prepared.context["instrument_id"],
            metric=key,
            period=period,
            value=value,
            unit=unit,
            filing_id=task.filing_id,
            quote=quote,
            source="extract",
            call_id=call_ids[0],
            at=env.at,
        )
        stored.append(f"{key}.{period}")
    if task.filing_id is not None:
        ai_repo.set_filing_status(env.conn, task.filing_id, "done")
    return {"stored": stored, "dropped": dropped, "notes": output.get("notes")}


# ── screen ───────────────────────────────────────────────────────────────────────────────────


def _sell_words(pick: ai_repo.PickRow) -> list[str]:
    keys = [str(c["metric"]) for c in pick.invalidate if isinstance(c.get("metric"), str)]
    words: list[str] = []
    for key in keys:
        try:
            words += keywords([key])
        except metrics.MetricError:
            continue
    words += [str(c["text"]) for c in pick.invalidate if isinstance(c.get("text"), str)]
    return words


def prepare_screen(env: FlowEnv, task: ai_repo.TaskRow) -> Prepared:
    pick, inst = _held(env, task)
    if task.filing_id is None:
        raise SkipTaskError("no filing")
    filing = ai_repo.get_filing(env.conn, task.filing_id)
    text = _filing_text(env, filing)
    body = focus(text, _sell_words(pick), TEXT_LIMIT // 2)
    packet = pk.join(
        pk.header(pick, inst),
        pk.conditions(env.conn, pick, "invalidate"),
        ["## 새 공시", f"- {filing.title} · {filing.filed_on} · {filing.source.upper()}"],
        ["## 원문" + (" (일부)" if len(body) < len(text) else ""), body],
    )
    return Prepared([_call(load("screen"), "screen", packet, "haiku")], packet)


def apply_screen(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    prepared: Prepared,
    results: list[CliResult],
    call_ids: list[int],
) -> dict[str, Any]:
    output = results[0].output
    relevant = output.get("relevant")
    if not isinstance(relevant, bool):
        raise FlowError("relevant is not true or false")
    reason = _text(output.get("reason"), "reason")
    if task.filing_id is None or task.pick_id is None:  # pragma: no cover — prepare checked
        raise FlowError("screen without filing or pick")
    ai_repo.set_filing_status(env.conn, task.filing_id, "relevant" if relevant else "irrelevant")
    out: dict[str, Any] = {"relevant": relevant, "touches": output.get("touches"), "reason": reason}
    if relevant:
        filing = ai_repo.get_filing(env.conn, task.filing_id)
        task_id, _ = ai_repo.enqueue_task(
            env.conn,
            kind="sell-confirm",
            ledger_id=task.ledger_id,
            rule_id=task.rule_id,
            trigger="filing",
            dedup_key=f"sell-confirm:{task.pick_id}:filing:{task.filing_id}",
            at=env.at,
            pick_id=task.pick_id,
            filing_id=task.filing_id,
            detail={
                "triggers": [
                    {
                        "kind": "filing",
                        "filing_id": task.filing_id,
                        "title": filing.title,
                        "filed_on": filing.filed_on.isoformat(),
                        "reason": reason,
                    }
                ]
            },
        )
        out["sell_confirm_task"] = task_id
    return out


# ── sell confirmation (two calls) ────────────────────────────────────────────────────────────


def _pick_packet(
    env: FlowEnv,
    task: ai_repo.TaskRow | None,
    pick: ai_repo.PickRow,
    inst: Instrument,
    quotes: pk.Quotes,
    *,
    buy: bool = False,
) -> str:
    today = kst_date(env.at)
    last = quotes.last(inst.yahoo_symbol)
    ratios = quotes.ratios.get(inst.yahoo_symbol, {})
    return pk.join(
        pk.today_rows(env.at),
        pk.header(pick, inst),
        pk.price_rows(pick, inst, quotes),
        pk.trigger_rows(env.conn, task) if task is not None and not buy else [],
        pk.conditions(env.conn, pick, "buy", None if last is None else last[1], ratios)
        if buy
        else [],
        pk.conditions(env.conn, pick, "invalidate"),
        pk.conditions(env.conn, pick, "confirm"),
        pk.metric_rows(env.conn, pick.instrument_id),
        pk.filing_rows(env.conn, pick.instrument_id, today),
        pk.tax_rows(env.conn, env.cfg, pick, inst, quotes, env.at),
    )


def _summary_of_pick(inst: Instrument, task: ai_repo.TaskRow) -> list[str]:
    out = [inst.name]
    for t in task.detail.get("triggers", []):
        if not isinstance(t, dict):
            continue
        if t.get("kind") == "shock":
            out.append(
                f"급락 {t.get('on')} 하루 지수 대비 {pk.pct(Decimal(str(t.get('day_rel'))))}%"
            )
        elif t.get("kind") == "condition":
            out.append(
                f"반증 조건 {int(t.get('index', 0)) + 1} · {t.get('period')} {t.get('value')}"
            )
        elif t.get("kind") == "filing":
            out.append(f"공시 {t.get('filed_on')} {t.get('title')}")
        elif t.get("kind") == "monthly":
            out.append(f"월 점검 {t.get('verdict')}")
    return out


def prepare_sell_confirm(env: FlowEnv, task: ai_repo.TaskRow) -> Prepared:
    pick, inst = _held(env, task)
    quotes = pk.quotes_for_pick(env.sources, pick, inst, kst_date(env.at))
    packet = _pick_packet(env, task, pick, inst, quotes)
    prompt = load("sell_confirm")
    calls = [_call(prompt, f"sell-confirm#{i}", packet, "sonnet", "low") for i in (1, 2)]
    return Prepared(calls, packet, {"instrument": inst.instrument_id})


def apply_sell_confirm(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    prepared: Prepared,
    results: list[CliResult],
    call_ids: list[int],
) -> dict[str, Any]:
    votes = [_choice(r.output.get("verdict"), VERDICT, "verdict") for r in results]
    pick, inst = _pick(env, task)
    sell = len(votes) == 2 and all(v == "invalidated" for v in votes)
    combined = max(votes, key=lambda v: SEVERITY[v]) if not sell else "invalidated"
    if combined == "invalidated" and not sell:
        combined = "weaken"  # one '반증' alone is a weakening, not a sale (D27)
    fields: dict[str, Any] = {"last_verdict": combined, "last_verdict_at": env.at}
    if sell:
        fields.update(
            decision="sell",
            decided_at=env.at,
            decision_task_id=task.task_id,
            closed_reason="반증 확인(두 번)",
        )
    ai_repo.update_pick(env.conn, pick.pick_id, env.at, **fields)
    reasons = [
        str(r.output.get("bear_case" if v == "invalidated" else "bull_case") or "")
        for r, v in zip(results, votes, strict=True)
    ]
    _event(
        env,
        task,
        "ai-sell" if sell else "ai-check",
        _judgment(
            task,
            results,
            call_ids,
            verdict=combined,
            action="sell" if sell else "none",
            instrument_id=inst.instrument_id,
            inputs=_summary_of_pick(inst, task),
            outputs=[" · ".join(pk.VERDICT_KO[v] for v in votes), *[r[:120] for r in reasons if r]],
            votes=votes,
        ),
    )
    return {"votes": votes, "sell": sell}


# ── buy confirmation ─────────────────────────────────────────────────────────────────────────


def weakest_held(conn: sqlite3.Connection, ledger_id: str) -> ai_repo.PickRow | None:
    """The held pick to give up first: the worst last verdict, then the most months of
    weakening, then the lowest excess over its index (the last watch's numbers)."""
    held = [p for p in ai_repo.picks_of(conn, ledger_id, RULE_ID, ("held",)) if p.decision is None]
    if not held:
        return None
    excess = ai_repo.latest_pick_excess(conn, ledger_id, RULE_ID)
    return max(
        held,
        key=lambda p: (
            SEVERITY.get(p.last_verdict or "hold", 1),
            p.weak_months,
            -excess.get(p.pick_id, ZERO),
            -p.pick_id,
        ),
    )


def held_count(conn: sqlite3.Connection, ledger_id: str) -> int:
    return len(ai_repo.picks_of(conn, ledger_id, RULE_ID, ("held",)))


def prepare_buy_confirm(env: FlowEnv, task: ai_repo.TaskRow) -> Prepared:
    pick, inst = _pick(env, task)
    if pick.status != "candidate" or pick.decision is not None:
        raise SkipTaskError(f"the pick is {pick.status}")
    quotes = pk.quotes_for_pick(env.sources, pick, inst, kst_date(env.at))
    packet = _pick_packet(env, task, pick, inst, quotes, buy=True)
    return Prepared([_call(load("buy_confirm"), "buy-confirm", packet, "sonnet", "low")], packet)


def _switch_task(env: FlowEnv, task: ai_repo.TaskRow, candidate: int, origin: str) -> int | None:
    weakest = weakest_held(env.conn, task.ledger_id)
    if weakest is None:
        return None
    task_id, _ = ai_repo.enqueue_task(
        env.conn,
        kind="switch",
        ledger_id=task.ledger_id,
        rule_id=task.rule_id,
        trigger=origin,
        dedup_key=f"switch:{candidate}:{weakest.pick_id}:{kst_date(env.at):%Y-%m}",
        at=env.at,
        pick_id=candidate,
        detail={"candidate": candidate, "weakest": weakest.pick_id},
    )
    return task_id


def apply_buy_confirm(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    prepared: Prepared,
    results: list[CliResult],
    call_ids: list[int],
) -> dict[str, Any]:
    output = results[0].output
    decision = _choice(
        output.get("decision"), {"근거 있음": "buy", "근거 없음": "skip"}, "decision"
    )
    reason = _text(output.get("reason"), "reason")
    pick, inst = _pick(env, task)
    out: dict[str, Any] = {"decision": decision, "reason": reason}
    action, notes = "none", [reason[:120]]
    if decision == "buy":
        if held_count(env.conn, task.ledger_id) < env.cfg.discovery_max_picks:
            ai_repo.update_pick(
                env.conn,
                pick.pick_id,
                env.at,
                status="held",
                decision="buy",
                decided_at=env.at,
                decision_task_id=task.task_id,
            )
            action = "buy"
        else:
            out["switch_task"] = _switch_task(env, task, pick.pick_id, "buy-price")
            notes.insert(0, "자리 없음: 바꾸기 확인으로")
    _event(
        env,
        task,
        "ai-buy" if action == "buy" else "ai-check",
        _judgment(
            task,
            results,
            call_ids,
            verdict="buy" if decision == "buy" else "skip",
            action=action,
            instrument_id=inst.instrument_id,
            inputs=[
                inst.name,
                *[f"{c['condition']} {c['verdict']}" for c in task.detail.get("checks", [])],
            ],
            outputs=[str(output.get("decision")), *notes],
        ),
    )
    return out


# ── monthly review ───────────────────────────────────────────────────────────────────────────


def rewrite(conditions: Any) -> tuple[list[dict[str, Any]], list[str]]:
    """The review's sell conditions in the fixed form; the ones the code cannot read are left
    out (and reported)."""
    good: list[dict[str, Any]] = []
    bad: list[str] = []
    for data in conditions if isinstance(conditions, list) else []:
        if not isinstance(data, Mapping):
            bad.append("not an object")
            continue
        try:
            good.append(condition_json(parse_condition(pk.clean(data))))
        except ConditionError as exc:
            bad.append(str(exc))
    return good, bad


def prepare_monthly_review(env: FlowEnv, task: ai_repo.TaskRow) -> Prepared:
    pick, inst = _held(env, task)
    quotes = pk.quotes_for_pick(env.sources, pick, inst, kst_date(env.at))
    packet = pk.join(
        pk.today_rows(env.at),
        pk.header(pick, inst),
        pk.price_rows(pick, inst, quotes),
        pk.conditions(env.conn, pick, "confirm"),
        pk.conditions(env.conn, pick, "invalidate"),
        pk.metric_rows(env.conn, pick.instrument_id),
        pk.filing_rows(env.conn, pick.instrument_id, kst_date(env.at)),
        pk.tax_rows(env.conn, env.cfg, pick, inst, quotes, env.at),
        pk.dictionary_rows(),
        [pk.CONDITION_FORM],
    )
    call = _call(load("monthly_review"), "monthly-review", packet, "sonnet", "low")
    return Prepared([call], packet, {"instrument": inst.instrument_id})


def _month_event(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    month: str,
    pick_id: int,
    verdict: str,
    changed: bool,
    tokens: int,
    call_id: int,
) -> None:
    ref = f"monthly-review:{month}"
    existing = repo.event_by_ref(env.conn, task.ledger_id, ref)
    payload: dict[str, Any] = (
        dict(existing.payload)
        if existing is not None
        else {
            "month": month,
            "verdicts": {},
            "changed": [],
            "tokens": 0,
            "call_ids": [],
            "trigger": "monthly",
            "model": "sonnet",
        }
    )
    payload["verdicts"][str(pick_id)] = verdict
    if changed and pick_id not in payload["changed"]:
        payload["changed"].append(pick_id)
    payload["tokens"] = int(payload.get("tokens", 0)) + tokens
    payload["call_ids"] = [*payload.get("call_ids", []), call_id]
    counts = {
        v: list(payload["verdicts"].values()).count(v) for v in ("hold", "weaken", "invalidated")
    }
    payload["counts"] = counts
    worst = max(payload["verdicts"].values(), key=lambda v: SEVERITY[v])
    payload["verdict"] = worst
    payload["action"] = "none"
    payload["output_summary"] = [
        f"유지 {counts['hold']}",
        f"약화 {counts['weaken']}",
        f"반증 {counts['invalidated']}",
    ]
    payload["input_summary"] = [f"{len(payload['verdicts'])}종목", month]
    _event(env, task, "monthly-review", payload, ref)


def apply_monthly_review(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    prepared: Prepared,
    results: list[CliResult],
    call_ids: list[int],
) -> dict[str, Any]:
    output = results[0].output
    verdict = _choice(output.get("verdict"), VERDICT, "verdict")
    pick, _ = _pick(env, task)
    good, bad = rewrite(output.get("sell_conditions"))
    weak = pick.weak_months + 1 if verdict == "weaken" else 0
    fields: dict[str, Any] = {
        "last_verdict": verdict,
        "last_verdict_at": env.at,
        "weak_months": weak,
    }
    if good:
        fields["invalidate"] = good
    ai_repo.update_pick(env.conn, pick.pick_id, env.at, **fields)
    month = str(task.detail.get("month") or f"{kst_date(env.at):%Y-%m}")
    out: dict[str, Any] = {
        "verdict": verdict,
        "weak_months": weak,
        "rewritten": len(good),
        "refused": bad,
    }
    if verdict == "invalidated" or weak >= 2:
        reason = "반증" if verdict == "invalidated" else f"약화 {weak}달"
        task_id, _ = ai_repo.enqueue_task(
            env.conn,
            kind="sell-confirm",
            ledger_id=task.ledger_id,
            rule_id=task.rule_id,
            trigger="monthly",
            dedup_key=f"sell-confirm:{pick.pick_id}:monthly:{month}",
            at=env.at,
            pick_id=pick.pick_id,
            detail={"triggers": [{"kind": "monthly", "verdict": reason, "month": month}]},
        )
        out["sell_confirm_task"] = task_id
    _month_event(
        env,
        task,
        month,
        pick.pick_id,
        verdict,
        pick.last_verdict not in (None, verdict),
        results[0].tokens,
        call_ids[0],
    )
    left = [
        t
        for t in ai_repo.tasks_of(
            env.conn, kind="monthly-review", statuses=("pending", "running", "failed")
        )
        if t.detail.get("month") == month
        and t.task_id != task.task_id
        and t.ledger_id == task.ledger_id
    ]
    if not left:
        out["switch_task"] = _monthly_switch(env, task, month)
    return out


def _monthly_switch(env: FlowEnv, task: ai_repo.TaskRow, month: str) -> int | None:
    """D37: with every slot taken, the month's last review asks whether the weakest holding
    should give way to the oldest candidate."""
    if held_count(env.conn, task.ledger_id) < env.cfg.discovery_max_picks:
        return None
    candidates = [
        p
        for p in ai_repo.picks_of(env.conn, task.ledger_id, RULE_ID, ("candidate",))
        if p.decision is None
    ]
    if not candidates:
        return None
    return _switch_task(env, task, candidates[0].pick_id, "monthly")


# ── quarterly discovery ──────────────────────────────────────────────────────────────────────


def prepare_discovery(env: FlowEnv, task: ai_repo.TaskRow) -> Prepared:
    conn = env.conn
    slots = max(0, env.cfg.discovery_max_picks - held_count(conn, task.ledger_id))
    candidates = ai_repo.picks_of(conn, task.ledger_id, RULE_ID, ("candidate",))
    previous = ai_repo.last_done(conn, "discovery", task.ledger_id)
    prev_lines = ["## 지난 발굴"]
    if previous is not None and previous.result:
        prev_lines.append(f"- 날짜: {previous.detail.get('month')}")
        prev_lines.append(f"- 거시: {str(previous.result.get('macro', ''))[:800]}")
        for flow in (
            previous.result.get("flows", [])
            if isinstance(previous.result.get("flows"), list)
            else []
        ):
            if isinstance(flow, dict):
                prev_lines.append(f"- 흐름 {flow.get('name')}: {str(flow.get('why', ''))[:200]}")
    else:
        prev_lines.append("- T24(2026-10-07) 첫 발굴: 보유 종목의 흐름 칸을 본다.")
    cand_lines = ["## 지금 후보 (살 조건을 기다림)"]
    for p in candidates:
        inst = repo.get_instrument(conn, p.instrument_id)
        cand_lines.append(f"- {inst.name} ({inst.instrument_id}) · {p.theme} · 살 조건 {p.buy}")
    if len(cand_lines) == 1:
        cand_lines.append("- (없음)")
    packet = pk.join(
        pk.today_rows(env.at),
        [
            "## 규칙",
            f"- 최대 종목 수 {env.cfg.discovery_max_picks} · slots_left {slots}",
            "- 새 종목은 같은 금액으로 산다. 판 돈은 다음에 살 때까지 같은 나라 지수 ETF에 둔다.",
            "- 한국 종목은 매달 1일 한국 종목끼리 같은 금액으로 다시 맞춘다.",
            "- 미국 종목은 세금 때문에 다시 맞추지 않는다(새 돈·판 돈으로만 맞춘다).",
        ],
        pk.sleeve_rows(conn, task.ledger_id),
        pk.sleeve_value_note(conn, task.ledger_id, env.at),
        cand_lines,
        prev_lines,
        pk.dictionary_rows(),
        [pk.CONDITION_FORM],
    )
    call = _call(load("discovery"), "discovery", packet, "opus", web=True)
    return Prepared([call], packet, {"slots": slots, "month": task.detail.get("month")})


def _symbol_options(entry: Mapping[str, Any]) -> list[str]:
    market, ticker, yahoo = (
        entry.get("market"),
        str(entry.get("ticker", "")),
        str(entry.get("yahoo", "")),
    )
    if market == "US":
        return [yahoo or ticker]
    options = [yahoo] if yahoo else []
    for suffix in (".KS", ".KQ"):
        if f"{ticker}{suffix}" not in options:
            options.append(f"{ticker}{suffix}")
    return options


def after_discovery(
    env: FlowEnv, task: ai_repo.TaskRow, prepared: Prepared, results: list[CliResult]
) -> None:
    """Network: the latest close of each new company and of the indexes (the pick price)."""
    output = results[0].output
    entries = [*output.get("picks", []), *output.get("candidates", [])]
    today = kst_date(env.at)
    start = today - timedelta(days=14)
    prices: dict[str, tuple[str, str, str]] = {}  # ticker key -> (symbol, date, close)
    bench = pk.fetch_quotes(env.sources, SCORE_BENCHMARK.values(), start, today)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = f"{entry.get('market')}:{entry.get('ticker')}"
        for symbol in _symbol_options(entry):
            last = pk.fetch_quotes(env.sources, [symbol], start, today).last(symbol)
            if last is not None:
                prices[key] = (symbol, last[0].isoformat(), str(last[1]))
                break
    prepared.context["prices"] = prices
    marks: dict[str, tuple[str, str]] = {}
    for symbol in SCORE_BENCHMARK.values():
        last = bench.last(symbol)
        if last is not None:
            marks[symbol] = (last[0].isoformat(), str(last[1]))
    prepared.context["bench"] = marks


def _new_pick(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    entry: Mapping[str, Any],
    status: str,
    prepared: Prepared,
) -> tuple[str | None, str | None]:
    """Insert one company of the answer. Returns (instrument id, refusal)."""
    market = entry.get("market")
    if market not in ("KR", "US"):
        return None, f"market {market!r}"
    ticker = str(entry.get("ticker", "")).strip().upper()
    key = f"{market}:{ticker}"
    if ai_repo.open_pick(env.conn, task.ledger_id, RULE_ID, key) is not None:
        return None, f"{key} is already open"
    price = prepared.context.get("prices", {}).get(key)
    benchmark = SCORE_BENCHMARK[str(market)]
    bench = prepared.context.get("bench", {}).get(benchmark)
    if price is None or bench is None:
        return None, f"{key}: no close"
    invalidate, bad_inv = rewrite(entry.get("invalidate"))
    confirm, _ = rewrite(entry.get("confirm"))
    buy, bad_buy = rewrite(entry.get("buy"))
    if not invalidate:
        return None, f"{key}: no sell condition the code can read ({'; '.join(bad_inv)})"
    if status == "candidate" and not buy:
        return None, f"{key}: a candidate needs a buy condition ({'; '.join(bad_buy)})"
    m = Market(str(market))
    inst = Instrument(
        instrument_id=key,
        market=m,
        currency=MARKET_CURRENCY[m],
        kind=Kind.STOCK,
        ticker=ticker,
        name=str(entry.get("name", ticker))[:60],
        yahoo_symbol=price[0],
    )
    repo.upsert_instrument(env.conn, inst, env.at)
    month = str(prepared.context.get("month") or f"{kst_date(env.at):%Y-%m}")
    pick_id = ai_repo.insert_pick(
        env.conn,
        ai_repo.NewPick(
            ledger_id=task.ledger_id,
            rule_id=RULE_ID,
            instrument_id=key,
            status=status,
            picked_on=date.fromisoformat(price[1]),
            picked_price=Decimal(price[2]),
            benchmark=benchmark,
            benchmark_price=Decimal(bench[1]),
            theme=str(entry.get("theme", ""))[:60],
            rationale=str(entry.get("rationale", ""))[:600],
            confirm=confirm,
            invalidate=invalidate,
            buy=buy if status == "candidate" else [],
            confidence=str(entry.get("confidence")) if entry.get("confidence") else None,
            source=f"discovery:{month}",
            texts={
                "priced_in": entry.get("priced_in"),
                "risks": entry.get("risks"),
                "sources": entry.get("sources"),
            },
        ),
        env.at,
    )
    if status == "held":
        ai_repo.update_pick(
            env.conn,
            pick_id,
            env.at,
            decision="buy",
            decided_at=env.at,
            decision_task_id=task.task_id,
        )
    return key, None


def apply_discovery(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    prepared: Prepared,
    results: list[CliResult],
    call_ids: list[int],
) -> dict[str, Any]:
    output = results[0].output
    picks, candidates = output.get("picks"), output.get("candidates")
    if not isinstance(picks, list) or not isinstance(candidates, list):
        raise FlowError("picks and candidates must be lists")
    slots = int(prepared.context.get("slots", 0))
    added: list[str] = []
    waiting: list[str] = []
    refused: list[str] = []
    for entry in picks:
        if len(added) >= slots:
            refused.append(f"{entry.get('ticker')}: no slot left")
            continue
        key, why = _new_pick(env, task, entry, "held", prepared)
        if key:
            added.append(key)
        else:
            refused.append(why or "?")
    new_candidates: set[str] = set()
    for entry in candidates:
        key, why = _new_pick(env, task, entry, "candidate", prepared)
        if key:
            waiting.append(key)
            new_candidates.add(key)
        else:
            refused.append(why or "?")
            if why and "already open" in why:
                new_candidates.add(f"{entry.get('market')}:{str(entry.get('ticker', '')).upper()}")
    month = str(prepared.context.get("month") or f"{kst_date(env.at):%Y-%m}")
    expired: list[str] = []
    for old in ai_repo.picks_of(env.conn, task.ledger_id, RULE_ID, ("candidate",)):
        if old.instrument_id in new_candidates or old.source == f"discovery:{month}":
            continue
        ai_repo.update_pick(
            env.conn,
            old.pick_id,
            env.at,
            status="expired",
            closed_on=kst_date(env.at),
            closed_reason=f"발굴 {month}에서 빠짐",
        )
        expired.append(old.instrument_id)
    _event(
        env,
        task,
        "discovery",
        _judgment(
            task,
            results,
            call_ids,
            verdict="buy" if added else "skip",
            action="buy" if added else "none",
            instrument_id=None,
            inputs=[
                month,
                f"보유 {held_count(env.conn, task.ledger_id) - len(added)}",
                f"후보 {len(candidates)}",
            ],
            outputs=[f"새 종목 {len(added)}", f"후보 {len(waiting)}", f"만료 {len(expired)}"],
        ),
        f"discovery:{month}",
    )
    return {
        "macro": output.get("macro"),
        "flows": output.get("flows"),
        "added": added,
        "candidates": waiting,
        "expired": expired,
        "refused": refused,
    }


# ── switch (two calls, costs from the code) ──────────────────────────────────────────────────


@dataclass(frozen=True)
class SwitchCosts:
    amount_krw: Decimal
    sell_fee_krw: Decimal
    sell_tax_krw: Decimal
    buy_fee_krw: Decimal
    parking_krw: Decimal

    @property
    def total_krw(self) -> Decimal:
        return self.sell_fee_krw + self.sell_tax_krw + self.buy_fee_krw + self.parking_krw

    @property
    def total_pct(self) -> Decimal:
        if self.amount_krw <= 0:
            return ZERO
        return round_half_up(self.total_krw / self.amount_krw * 100, Decimal("0.01"))

    def as_json(self) -> dict[str, str]:
        return {
            "amount_krw": str(self.amount_krw),
            "sell_fee_krw": str(self.sell_fee_krw),
            "sell_tax_krw": str(self.sell_tax_krw),
            "buy_fee_krw": str(self.buy_fee_krw),
            "parking_krw": str(self.parking_krw),
            "total_krw": str(self.total_krw),
            "total_pct": str(self.total_pct),
        }


def switch_costs(
    env: FlowEnv,
    sold: ai_repo.PickRow,
    sold_inst: Instrument,
    bought_inst: Instrument,
    sold_price: Decimal | None,
    rate: Decimal | None,
) -> SwitchCosts:
    """D37: fees and taxes of selling the weakest holding and buying the candidate with the
    money, and the round trip through the index ETF that holds sold money until the buy."""
    fees = env.cfg.fees
    held = pk.holding(env.conn, sold)
    if held is None or sold_price is None or (sold_inst.currency is Currency.USD and rate is None):
        return SwitchCosts(ZERO, ZERO, ZERO, ZERO, ZERO)
    gross = sold_price * held.qty
    to_krw: Callable[[Decimal], Decimal] = (
        (lambda v: v)
        if sold_inst.currency is Currency.KRW
        else (lambda v: usd_in_krw(v, rate or ZERO))
    )
    amount = to_krw(gross)
    sell_fee = to_krw(trade_fee(sold_inst.currency, gross, fees))
    if sold_inst.currency is Currency.KRW:
        sell_tax = round_won(gross * fees.kr_stock_sell_tax)
    else:
        sell_tax = us_tax(
            env.conn, env.cfg, sold.ledger_id, kst_date(env.at).year, amount - held.cost_krw
        ).tax_if_sold_krw
    buy_rate = fees.rate_for(bought_inst.currency)
    parking_rate = fees.rate_for(sold_inst.currency) * 2
    return SwitchCosts(
        amount_krw=round_won(amount),
        sell_fee_krw=round_won(sell_fee),
        sell_tax_krw=round_won(sell_tax),
        buy_fee_krw=round_won(amount * buy_rate),
        parking_krw=round_won(amount * parking_rate),
    )


def prepare_switch(env: FlowEnv, task: ai_repo.TaskRow) -> Prepared:
    conn = env.conn
    candidate = ai_repo.get_pick(conn, int(task.detail["candidate"]))
    sold = ai_repo.get_pick(conn, int(task.detail["weakest"]))
    if candidate.status != "candidate" or candidate.decision is not None:
        raise SkipTaskError(f"the candidate is {candidate.status}")
    if sold.status != "held" or sold.decision is not None:
        raise SkipTaskError(f"the holding is {sold.status}")
    c_inst = repo.get_instrument(conn, candidate.instrument_id)
    s_inst = repo.get_instrument(conn, sold.instrument_id)
    today = kst_date(env.at)
    c_quotes = pk.quotes_for_pick(env.sources, candidate, c_inst, today)
    s_quotes = pk.quotes_for_pick(env.sources, sold, s_inst, today)
    fx = repo.fx_at(conn, env.at)
    last = s_quotes.last(s_inst.yahoo_symbol)
    costs = switch_costs(
        env,
        sold,
        s_inst,
        c_inst,
        None if last is None else last[1],
        None if fx is None else fx.rate,
    )
    cost_rows = ["## 바꾸는 비용 (코드 계산, 원)", "| 칸 키 | 값 |", "|---|---|"] + [
        f"| cost.{k} | {v} |" for k, v in costs.as_json().items()
    ]
    packet = pk.join(
        pk.today_rows(env.at),
        ["# 판 종목 (가장 약한 보유)"],
        pk.header(sold, s_inst),
        pk.price_rows(sold, s_inst, s_quotes),
        pk.conditions(conn, sold, "invalidate"),
        pk.metric_rows(conn, sold.instrument_id),
        pk.tax_rows(conn, env.cfg, sold, s_inst, s_quotes, env.at),
        ["# 살 종목 (후보)"],
        pk.header(candidate, c_inst),
        pk.price_rows(candidate, c_inst, c_quotes),
        pk.conditions(conn, candidate, "buy"),
        pk.conditions(conn, candidate, "invalidate"),
        cost_rows,
    )
    prompt = load("switch")
    calls = [_call(prompt, f"switch#{i}", packet, "sonnet", "low") for i in (1, 2)]
    return Prepared(calls, packet, {"costs": costs.as_json()})


def apply_switch(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    prepared: Prepared,
    results: list[CliResult],
    call_ids: list[int],
) -> dict[str, Any]:
    votes = [
        _choice(r.output.get("decision"), {"바꾼다": "switch", "바꾸지 않는다": "keep"}, "decision")
        for r in results
    ]
    beats = [r.output.get("beats_cost") is True for r in results]
    switch = len(votes) == 2 and all(v == "switch" for v in votes) and all(beats)
    candidate = ai_repo.get_pick(env.conn, int(task.detail["candidate"]))
    sold = ai_repo.get_pick(env.conn, int(task.detail["weakest"]))
    out: dict[str, Any] = {"votes": votes, "beats_cost": beats, "switch": switch}
    if switch:
        ai_repo.update_pick(
            env.conn,
            sold.pick_id,
            env.at,
            decision="sell",
            decided_at=env.at,
            decision_task_id=task.task_id,
            closed_reason="바꾸기",
        )
        ai_repo.update_pick(
            env.conn,
            candidate.pick_id,
            env.at,
            status="held",
            decision="buy",
            decided_at=env.at,
            decision_task_id=task.task_id,
        )
        out["switch_id"] = ai_repo.insert_switch(
            env.conn,
            ledger_id=task.ledger_id,
            rule_id=RULE_ID,
            sold_pick_id=sold.pick_id,
            bought_pick_id=candidate.pick_id,
            decided_on=kst_date(env.at),
            task_id=task.task_id,
            costs=prepared.context["costs"],
            at=env.at,
        )
    sold_name = repo.get_instrument(env.conn, sold.instrument_id).name
    bought_name = repo.get_instrument(env.conn, candidate.instrument_id).name
    _event(
        env,
        task,
        "ai-buy" if switch else "ai-check",
        _judgment(
            task,
            results,
            call_ids,
            verdict="buy" if switch else "skip",
            action="switch" if switch else "none",
            instrument_id=candidate.instrument_id,
            inputs=[
                f"판 종목 {sold_name}",
                f"살 종목 {bought_name}",
                f"비용 {prepared.context['costs']['total_pct']}%",
            ],
            outputs=[" · ".join("바꾼다" if v == "switch" else "안 바꾼다" for v in votes)],
        ),
    )
    return out


FLOWS: dict[str, Flow] = {
    "extract": Flow("extract", "extract", prepare_extract, apply_extract),
    "screen": Flow("screen", "screen", prepare_screen, apply_screen),
    "sell-confirm": Flow("sell-confirm", "sell_confirm", prepare_sell_confirm, apply_sell_confirm),
    "buy-confirm": Flow("buy-confirm", "buy_confirm", prepare_buy_confirm, apply_buy_confirm),
    "monthly-review": Flow(
        "monthly-review", "monthly_review", prepare_monthly_review, apply_monthly_review
    ),
    "discovery": Flow(
        "discovery", "discovery", prepare_discovery, apply_discovery, after_discovery
    ),
    "switch": Flow("switch", "switch", prepare_switch, apply_switch),
}
