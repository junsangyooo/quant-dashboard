"""The questions of '3년 발굴', one flow per task kind (PHASE2.md §6·§7, D27·D30·D31·D35~D37).

  kind            model (effort)   calls  what the answer does
  extract         haiku            1      metric values into the metric table (T27)
  screen          haiku            1      'relevant' -> a sell confirmation (filing)
  sell-confirm    sonnet (low)     2      both '반증' -> sell (D27); else hold, recorded. A shock
                                          is checked against the news with the web (D31)
  buy-confirm     sonnet (low)     2      both '근거 있음' -> buy, or a switch question when no
                                          slot; else no buy, recorded (audit 2026-10-10, E5)
  monthly-review  sonnet (low)     1      verdict, sell conditions rewritten; '반증' or two months
                                          of '약화' -> a sell confirmation
  discovery       opus + web       1      new picks (each asked as a buy confirmation before any
                                          money moves), candidates with buy conditions
  switch          sonnet (low)     2      both '바꾼다' and beating the code's costs -> switch (D37)

A buy rests on two independent answers, like a sale: the quarterly discovery reads the web (open
to what a fetched page says), so its new picks are candidates until two web-free calls on a
packet the code built (filings, metric table, prices, the pick's conditions; not the discovery's
own words) both say '근거 있음'. A new pick that is not confirmed stays a candidate with the
reason in its note; the next discovery asks again if it lists it again, or lets it expire.

A flow prepares (database reads and downloads: no transaction), the runner makes the calls, an
optional `after` step downloads what the answer needs (discovery prices and kinds), and `apply`
writes the effects in one transaction. Decisions only mark picks; the discovery planner
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
from autotrade.ai.cli import MAX_PROMPT_BYTES, CliCall, CliResult
from autotrade.ai.prompts import Prompt, load
from autotrade.ai.text import TEXT_LIMIT, focus, keywords
from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.domain import metrics
from autotrade.domain.conditions import ConditionError, condition_json, parse_condition
from autotrade.domain.instruments import MARKET_CURRENCY, Currency, Instrument, Kind, Market
from autotrade.domain.money import ZERO, round_half_up, round_won, trade_fee, usd_in_krw
from autotrade.domain.periods import PeriodError, is_period, parse_period
from autotrade.engine.common import load_rule
from autotrade.engine.tax import us_tax
from autotrade.engine.watch import FILINGS_SEEN
from autotrade.market.filings import (
    FilingInfo,
    FilingSourceError,
    SourceMaintenanceError,
    SourceNoKeyError,
    SourceUnreachableError,
)
from autotrade.market.service import MarketSources
from autotrade.rules.discovery import RULE_ID, SCORE_BENCHMARK
from autotrade.rules.index_half import RULE_ID as INDEX_RULE
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
    """A source is down, a key is missing, or the evidence is not in yet: wait, without counting
    an attempt."""


class SourceAnswerError(RetryLaterError):
    """A source answered with something that cannot be used (a corrupt download, a refusal, an
    empty text): wait without counting an attempt; the runner gives the task up after
    MAX_SOURCE_TRIES such answers (autotrade/ai/runner.py)."""


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
    except (SourceUnreachableError, SourceMaintenanceError, SourceNoKeyError) as exc:
        raise RetryLaterError(f"{filing.source}: {exc}") from exc  # down, or no key here
    except FilingSourceError as exc:  # a refusal or a download we cannot read
        raise SourceAnswerError(f"{filing.source}: {exc}") from exc
    if not text.strip():
        raise SourceAnswerError(f"filing {filing.source_ref} has no text")
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
    inputs: list[dict[str, Any]],
    outputs: list[dict[str, Any]],
    votes: list[str] | None = None,
) -> dict[str, Any]:
    """The event payload of a judgment. `input` and `output` are the card's two lines as data
    items (CONTRACT.md JudgmentItem: codes, numbers, dates and instrument ids, never words)."""
    out: dict[str, Any] = {
        "task_id": task.task_id,
        "kind": task.kind,
        "trigger": JUDGMENT_TRIGGER.get(task.trigger, "condition"),
        "instrument_id": instrument_id,
        "model": results[0].call.model if results else None,
        "tokens": sum(r.tokens for r in results),
        "verdict": verdict,
        "action": action,
        "input": inputs,
        "output": outputs,
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


def fit_text(
    text: str, words: Sequence[str], limit: int, steps: str, build: Callable[[str], str]
) -> str:
    """The packet with as much of the filing as fits one command-line argument: the text is
    focused at `limit` characters and cut further while the prompt is over MAX_PROMPT_BYTES (a
    Korean report is 3 bytes a character; a long dictionary or title list adds to it)."""
    while True:
        packet = build(focus(text, words, limit))
        if len(f"{steps}\n\n{packet}".encode()) <= MAX_PROMPT_BYTES or limit <= 1000:
            return packet
        limit = int(limit * 0.8)


# The longest quote stored with a value. The prompt asks for a locator of 80 characters or fewer
# (enough to find the sentence in the filing); the schema leaves a little room above that so a
# slightly long locator does not make the CLI ask the model again.
QUOTE_MAX = 100
# How many stored periods of one metric the extraction is told about, newest first. A filing
# compares with the prior quarter and the prior year (an annual report with three years), so
# older periods are not worth the prompt; one that does appear is simply extracted again.
KNOWN_PERIODS = 16


def _plain(value: Decimal) -> str:
    """A stored value as the model writes one: digits, no exponent, no trailing zeros."""
    return format(value.normalize(), "f")


def known_values(conn: sqlite3.Connection, instrument_id: str, wanted: Sequence[str]) -> list[str]:
    """The values the metric table already holds for the wanted metrics, one line per metric.

    The extraction leaves these (metric, period) pairs out unless the filing states them
    differently (a restatement), so each filing pays only for what is new: the comparison
    periods of an earnings report (the prior quarter, the prior year) are usually already in the
    table from the reports that came before. With nothing stored (a company's first extraction)
    the list is empty and everything is asked for."""
    rows: dict[str, list[ai_repo.MetricValueRow]] = {}
    for row in ai_repo.metric_values(conn, instrument_id):
        if row.metric in wanted and is_period(row.period):
            rows.setdefault(row.metric, []).append(row)
    lines = []
    for key in sorted(rows):
        newest = sorted(rows[key], key=lambda r: _period_order(r.period), reverse=True)
        known = " · ".join(f"{r.period} {_plain(r.value)} {r.unit}" for r in newest[:KNOWN_PERIODS])
        lines.append(f"- {key}: {known}")
    return lines


def _period_order(key: str) -> tuple[int, int]:
    period = parse_period(key)
    return period.year, period.sub


def prepare_extract(env: FlowEnv, task: ai_repo.TaskRow) -> Prepared:
    if task.filing_id is None:
        raise SkipTaskError("no filing")
    filing = ai_repo.get_filing(env.conn, task.filing_id)
    inst = repo.get_instrument(env.conn, filing.instrument_id)
    wanted = wanted_metrics(env.conn, inst.instrument_id)
    known = known_values(env.conn, inst.instrument_id, wanted)
    text = _filing_text(env, filing)

    def build(body: str) -> str:
        cut = " (길어서 뽑을 지표가 나오는 부분만 옮김)" if len(body) < len(text) else ""
        return pk.join(
            [
                "## 공시",
                f"- 회사: {inst.name} ({inst.instrument_id}) · 통화 {inst.currency.value}",
                f"- 공시: {filing.title} · {filing.filed_on} · {filing.source.upper()}",
            ],
            ["## 뽑을 지표"]
            + [f"- {k}: {metrics.label(k)} — {metrics.resolve(k)[0].description}" for k in wanted],
            ["## 표에 이미 있는 값 (지표: 기간 값 단위)", *known] if known else [],
            [f"## 원문{cut}", body],
        )

    prompt = load("extract")
    packet = fit_text(text, keywords(wanted), TEXT_LIMIT, prompt.steps, build)
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
    return str(key), period, value, unit, str(item.get("quote") or "")[:QUOTE_MAX]


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
    instrument_id = prepared.context["instrument_id"]
    table = {(v.metric, v.period): v for v in ai_repo.metric_values(env.conn, instrument_id)}
    stored: list[str] = []
    dropped: list[str] = []
    unchanged: list[str] = []
    for item in items:
        try:
            key, period, value, unit, quote = _metric_item(item, prepared.context["wanted"])
        except (FlowError, PeriodError) as exc:
            dropped.append(str(exc))
            continue
        held = table.get((key, period))
        if held is not None and held.value == value and held.unit == unit:
            # Already in the table as stated: the row keeps the filing it came from.
            unchanged.append(f"{key}.{period}")
            continue
        ai_repo.upsert_metric_value(
            env.conn,
            instrument_id=instrument_id,
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
    summary: dict[str, Any] = {"stored": stored, "dropped": dropped, "notes": output.get("notes")}
    if unchanged:
        summary["unchanged"] = unchanged
    return summary


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

    def build(body: str) -> str:
        return pk.join(
            pk.header(pick, inst),
            pk.conditions(env.conn, pick, "invalidate"),
            ["## 새 공시", f"- {filing.title} · {filing.filed_on} · {filing.source.upper()}"],
            ["## 원문" + (" (일부)" if len(body) < len(text) else ""), body],
        )

    prompt = load("screen")
    packet = fit_text(text, _sell_words(pick), TEXT_LIMIT // 2, prompt.steps, build)
    return Prepared([_call(prompt, "screen", packet, "haiku")], packet)


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
    task: ai_repo.TaskRow,
    pick: ai_repo.PickRow,
    inst: Instrument,
    quotes: pk.Quotes,
) -> str:
    """A held pick's packet for the sell confirmation (with the rationale it was bought on)."""
    today = kst_date(env.at)
    return pk.join(
        pk.today_rows(env.at),
        pk.header(pick, inst),
        pk.price_rows(pick, inst, quotes),
        pk.trigger_rows(env.conn, task),
        pk.conditions(env.conn, pick, "invalidate"),
        pk.conditions(env.conn, pick, "confirm"),
        pk.metric_rows(env.conn, pick.instrument_id),
        pk.filing_rows(env.conn, pick.instrument_id, today),
        pk.tax_rows(env.conn, env.cfg, pick, inst, quotes, env.at),
    )


def _pick_input(env: FlowEnv, inst: Instrument, task: ai_repo.TaskRow) -> list[dict[str, Any]]:
    """The input line of a pick's judgment: the company, what set it off, the filings read."""
    out: list[dict[str, Any]] = [{"key": "instrument", "instrument_id": inst.instrument_id}]
    for t in task.detail.get("triggers", []):
        if not isinstance(t, dict):
            continue
        if t.get("kind") == "shock":
            day_rel = (Decimal(str(t.get("day_rel"))) * 100).quantize(Decimal("0.1"))
            out.append({"key": "shock", "date": str(t.get("on")), "value": float(day_rel)})
        elif t.get("kind") == "condition":
            out.append({"key": "condition", "value": int(t.get("index", 0)) + 1})
        elif t.get("kind") == "filing":
            out.append({"key": "filing", "date": str(t.get("filed_on"))})
        elif t.get("kind") == "monthly":
            item: dict[str, Any] = {"key": "review", "value": str(t.get("verdict"))}
            if t.get("weak_months"):
                item["months"] = int(t["weak_months"])
            out.append(item)
    shown = pk.recent_filings(env.conn, inst.instrument_id, kst_date(env.at))
    out.append({"key": "filings", "value": len(shown)})
    return out


def is_shock(task: ai_repo.TaskRow) -> bool:
    """A price shock is among what set the confirmation off."""
    return any(
        isinstance(t, dict) and t.get("kind") == "shock" for t in task.detail.get("triggers", [])
    )


def prepare_sell_confirm(env: FlowEnv, task: ai_repo.TaskRow) -> Prepared:
    """Two independent calls. A shock is checked against the news with the web (D31: news
    usually explains a price shock before any filing does); every other question is web-free."""
    pick, inst = _held(env, task)
    quotes = pk.quotes_for_pick(env.sources, pick, inst, kst_date(env.at))
    packet = _pick_packet(env, task, pick, inst, quotes)
    prompt = load("sell_confirm")
    web = is_shock(task)
    calls = [_call(prompt, f"sell-confirm#{i}", packet, "sonnet", "low", web=web) for i in (1, 2)]
    return Prepared(calls, packet, {"instrument": inst.instrument_id, "web": web})


def new_facts(results: Sequence[CliResult]) -> list[dict[str, str]]:
    """The web facts both answers found (fact, source, date), malformed ones left out."""
    out: list[dict[str, str]] = []
    for r in results:
        for item in r.output.get("new_facts") or []:
            if not isinstance(item, Mapping):
                continue
            fact, source, day = item.get("fact"), item.get("source"), item.get("date")
            if all(isinstance(x, str) and x.strip() for x in (fact, source, day)):
                out.append(
                    {"fact": str(fact)[:240], "source": str(source)[:200], "date": str(day)[:10]}
                )
    return out


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
    facts = new_facts(results)
    payload = _judgment(
        task,
        results,
        call_ids,
        verdict=combined,
        action="sell" if sell else "none",
        instrument_id=inst.instrument_id,
        inputs=_pick_input(env, inst, task),
        # A shock is checked with the web: how many news items the two answers found.
        outputs=[{"key": "news", "value": len(facts)}] if prepared.context.get("web") else [],
        votes=votes,
    )
    # The model's own words stay in the record (and in ai_calls); the screens get data only.
    payload["reasons"] = [r[:120] for r in reasons if r]
    payload["new_facts"] = facts
    _event(env, task, "ai-sell" if sell else "ai-check", payload)
    return {"votes": votes, "sell": sell, "new_facts": facts}


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


BUY_DECISION = {"근거 있음": "buy", "근거 없음": "skip"}
# A buy confirmation waits for the company's filings to be read (the watch lists them, the
# runner extracts the latest earnings) so that its two answers stand on the metric table, not on
# prices alone; after EVIDENCE_WAIT it goes on with what there is.
EVIDENCE_WAIT = timedelta(days=5)


def evidence_pending(env: FlowEnv, pick: ai_repo.PickRow, task: ai_repo.TaskRow) -> str | None:
    """Why the buy confirmation should wait for the company's filings (None: ask now)."""
    if env.at - task.created_at > EVIDENCE_WAIT:
        return None
    if repo.get_setting(env.conn, FILINGS_SEEN.format(pick.instrument_id)) is None:
        return "waiting for the daily watch to list the company's filings"
    reading = [
        t
        for t in ai_repo.extract_tasks_of_instrument(env.conn, pick.instrument_id)
        if t.is_open(env.cfg.ai_max_attempts)
    ]
    if reading:
        return f"waiting for {len(reading)} earnings filing(s) of the company to be read"
    return None


def buy_packet(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    pick: ai_repo.PickRow,
    inst: Instrument,
    quotes: pk.Quotes,
) -> str:
    """What a buy is judged on, all of it built by code: the filings, the metric table, prices,
    the pick's conditions with the code's checks. The discovery's own words (its rationale,
    priced-in and risk notes, sources) stay out: they come from fetched web pages."""
    today = kst_date(env.at)
    last = quotes.last(inst.yahoo_symbol)
    ratios = quotes.ratios.get(inst.yahoo_symbol, {})
    return pk.join(
        pk.today_rows(env.at),
        [pk.DATA_NOT_ORDERS],
        pk.code_header(pick, inst),
        pk.buy_trigger_rows(task),
        pk.price_rows(pick, inst, quotes),
        pk.conditions(env.conn, pick, "buy", None if last is None else last[1], ratios, words=False)
        if pick.buy
        else [],
        pk.conditions(env.conn, pick, "invalidate", words=False),
        pk.conditions(env.conn, pick, "confirm", words=False),
        pk.metric_rows(env.conn, pick.instrument_id),
        pk.filing_rows(env.conn, pick.instrument_id, today),
        pk.tax_rows(env.conn, env.cfg, pick, inst, quotes, env.at),
    )


def prepare_buy_confirm(env: FlowEnv, task: ai_repo.TaskRow) -> Prepared:
    """Two independent web-free calls (E5): a buy needs two '근거 있음', like a sale needs two
    '반증'."""
    pick, inst = _pick(env, task)
    if pick.status != "candidate" or pick.decision is not None:
        raise SkipTaskError(f"the pick is {pick.status}")
    waiting = evidence_pending(env, pick, task)
    if waiting is not None:
        raise RetryLaterError(waiting)
    quotes = pk.quotes_for_pick(env.sources, pick, inst, kst_date(env.at))
    packet = buy_packet(env, task, pick, inst, quotes)
    prompt = load("buy_confirm")
    calls = [_call(prompt, f"buy-confirm#{i}", packet, "sonnet", "low") for i in (1, 2)]
    return Prepared(calls, packet, {"instrument": inst.instrument_id})


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


def _add_note(note: str | None, line: str) -> str:
    return line if not note else f"{note}\n{line}"


def apply_buy_confirm(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    prepared: Prepared,
    results: list[CliResult],
    call_ids: list[int],
) -> dict[str, Any]:
    votes = [_choice(r.output.get("decision"), BUY_DECISION, "decision") for r in results]
    reasons = [_text(r.output.get("reason"), "reason") for r in results]
    pick, inst = _pick(env, task)
    buy = len(votes) == 2 and all(v == "buy" for v in votes)
    out: dict[str, Any] = {"votes": votes, "buy": buy, "reasons": reasons}
    action = "none"
    outputs: list[dict[str, Any]] = []
    if buy:
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
            out["switch_task"] = _switch_task(env, task, pick.pick_id, task.trigger)
            outputs.append({"key": "slot-full"})  # no slot: asked as a switch instead
    elif task.trigger == "discovery":
        # A new pick the two answers did not confirm stays a candidate (no buy condition, so
        # the daily watch never asks for it); the next discovery asks again if it lists it again,
        # or lets it expire.
        said = (
            f"{kst_date(env.at)} 사기 확인: '근거 있음' {votes.count('buy')}/2 · 다음 발굴까지 후보"
        )
        ai_repo.update_pick(env.conn, pick.pick_id, env.at, note=_add_note(pick.note, said))
        out["kept_as_candidate"] = True
    inputs: list[dict[str, Any]] = [{"key": "instrument", "instrument_id": inst.instrument_id}]
    if task.trigger == "discovery":
        inputs.append({"key": "month", "value": str(task.detail.get("month", ""))})
    else:
        inputs.append({"key": "checks", "value": len(task.detail.get("checks", []))})
    inputs.append(
        {
            "key": "filings",
            "value": len(pk.recent_filings(env.conn, inst.instrument_id, kst_date(env.at))),
        }
    )
    payload = _judgment(
        task,
        results,
        call_ids,
        verdict="buy" if buy else "skip",
        action=action,
        instrument_id=inst.instrument_id,
        inputs=inputs,
        outputs=outputs,
        votes=votes,  # 'buy' | 'skip', twice
    )
    payload["reasons"] = [r[:120] for r in reasons if r]
    _event(env, task, "ai-buy" if action == "buy" else "ai-check", payload)
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
    rewritten: int,
    tokens: int,
    call_id: int,
) -> None:
    """One event for the month's reviews, rebuilt as each pick's review lands."""
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
    payload.setdefault("rewritten", {})[str(pick_id)] = rewritten
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
    payload["input"] = [
        {"key": "month", "value": month},
        {"key": "picks", "value": len(payload["verdicts"])},
    ]
    payload["output"] = [
        *({"key": v, "value": counts[v]} for v in ("hold", "weaken", "invalidated")),
        {"key": "rewritten", "value": sum(int(n) for n in payload["rewritten"].values())},
    ]
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
    # Sell conditions new or changed against the ones held before ('고쳐 쓴 팔 조건 n').
    rewritten = sum(1 for c in good if c not in pick.invalidate)
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
        trigger: dict[str, Any] = {"kind": "monthly", "verdict": verdict, "month": month}
        if verdict == "weaken":
            trigger["weak_months"] = weak
        task_id, _ = ai_repo.enqueue_task(
            env.conn,
            kind="sell-confirm",
            ledger_id=task.ledger_id,
            rule_id=task.rule_id,
            trigger="monthly",
            dedup_key=f"sell-confirm:{pick.pick_id}:monthly:{month}",
            at=env.at,
            pick_id=pick.pick_id,
            detail={"triggers": [trigger]},
        )
        out["sell_confirm_task"] = task_id
    _month_event(
        env,
        task,
        month,
        pick.pick_id,
        verdict,
        pick.last_verdict not in (None, verdict),
        rewritten,
        results[0].tokens,
        call_ids[0],
    )
    # The month's last review asks the switch question. A review that failed for good waits for
    # a person and does not hold the others up (it is a red 'to do' of its own).
    left = [
        t
        for t in ai_repo.open_tasks(
            env.conn, env.cfg.ai_max_attempts, kind="monthly-review", ledger_id=task.ledger_id
        )
        if t.detail.get("month") == month and t.task_id != task.task_id
    ]
    if not left:
        out["switch_task"] = _monthly_switch(env, task, month)
    return out


def _monthly_switch(env: FlowEnv, task: ai_repo.TaskRow, month: str) -> int | None:
    """D37: with every slot taken, the month's last review asks whether the weakest holding
    should give way to the oldest candidate. A new pick of the discovery that its two buy answers
    did not confirm (it has no buy condition) is not offered: it waits for the next discovery."""
    if held_count(env.conn, task.ledger_id) < env.cfg.discovery_max_picks:
        return None
    candidates = [
        p
        for p in ai_repo.picks_of(env.conn, task.ledger_id, RULE_ID, ("candidate",))
        if p.decision is None and p.buy
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
    cand_lines = ["## 지금 후보 (살 조건이나 사기 확인을 기다림)"]
    for p in candidates:
        inst = repo.get_instrument(conn, p.instrument_id)
        waits = (
            f"살 조건 {p.buy}"
            if p.buy
            else "살 조건 없음 (지난 발굴의 새 종목, 사기 확인 전·안 됨)"
        )
        cand_lines.append(f"- {inst.name} ({inst.instrument_id}) · {p.theme} · {waits}")
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
    """Network: the latest close of each new company and of the indexes (the pick price), and
    what each one is (Yahoo's quote type: the rule buys companies, not funds)."""
    output = results[0].output
    entries = [*output.get("picks", []), *output.get("candidates", [])]
    today = kst_date(env.at)
    start = today - timedelta(days=14)
    prices: dict[str, tuple[str, str, str]] = {}  # ticker key -> (symbol, date, close)
    kinds: dict[str, str] = {}  # ticker key -> Yahoo quote type ('EQUITY', 'ETF' ...)
    bench = pk.fetch_quotes(env.sources, SCORE_BENCHMARK.values(), start, today)
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = f"{entry.get('market')}:{str(entry.get('ticker', '')).strip().upper()}"
        for symbol in _symbol_options(entry):
            last = pk.fetch_quotes(env.sources, [symbol], start, today).last(symbol)
            if last is not None:
                prices[key] = (symbol, last[0].isoformat(), str(last[1]))
                kind = pk.fetch_quote_type(env.sources, symbol)
                if kind is not None:
                    kinds[key] = kind
                break
    prepared.context["prices"] = prices
    prepared.context["kinds"] = kinds
    marks: dict[str, tuple[str, str]] = {}
    for symbol in SCORE_BENCHMARK.values():
        last = bench.last(symbol)
        if last is not None:
            marks[symbol] = (last[0].isoformat(), str(last[1]))
    prepared.context["bench"] = marks


def protected_instruments(conn: sqlite3.Connection) -> set[str]:
    """What the rule may never pick: the long-term rule's instruments, which are also the index
    ETFs that hold this rule's idle money (a 'pick' of one would sell the parked shares)."""
    rule, _ = load_rule(conn, INDEX_RULE)
    return set(rule.instrument_ids)


def _one_line(value: Any, limit: int) -> str:
    """A model-written label as one plain line (no line breaks, no runs of spaces)."""
    return " ".join(str(value or "").split())[:limit]


def _ask_to_buy(
    env: FlowEnv, task: ai_repo.TaskRow, pick_id: int, instrument_id: str, month: str
) -> int:
    """A new pick is bought only after two '근거 있음' (E5): queue its buy confirmation."""
    task_id, _ = ai_repo.enqueue_task(
        env.conn,
        kind="buy-confirm",
        ledger_id=task.ledger_id,
        rule_id=task.rule_id,
        trigger="discovery",
        dedup_key=f"buy-confirm:{pick_id}:discovery:{month}",
        at=env.at,
        pick_id=pick_id,
        detail={"month": month, "instrument_id": instrument_id},
    )
    return task_id


def _new_pick(
    env: FlowEnv,
    task: ai_repo.TaskRow,
    entry: Mapping[str, Any],
    new: bool,
    prepared: Prepared,
) -> tuple[str | None, str | None]:
    """Record one company of the answer as a candidate: a new pick (`new`) gets its buy
    confirmation queued, a candidate waits for its buy condition. Returns (instrument id,
    refusal)."""
    market = entry.get("market")
    if market not in ("KR", "US"):
        return None, f"market {market!r}"
    ticker = str(entry.get("ticker", "")).strip().upper()
    key = f"{market}:{ticker}"
    month = str(prepared.context.get("month") or f"{kst_date(env.at):%Y-%m}")
    if key in protected_instruments(env.conn):
        return None, f"{key}: an index ETF of the long-term rule (it holds the idle money)"
    known = ai_repo.open_pick(env.conn, task.ledger_id, RULE_ID, key)
    if known is not None:
        if new and known.status == "candidate":  # picked again: ask again whether to buy now
            _ask_to_buy(env, task, known.pick_id, key, month)
            return key, None
        return None, f"{key} is already open"
    try:
        stored: Instrument | None = repo.get_instrument(env.conn, key)
    except repo.NotFoundError:
        stored = None
    if stored is not None and stored.kind is not Kind.STOCK:
        return None, f"{key}: not a company ({stored.kind.value})"
    price = prepared.context.get("prices", {}).get(key)
    benchmark = SCORE_BENCHMARK[str(market)]
    bench = prepared.context.get("bench", {}).get(benchmark)
    if price is None or bench is None:
        return None, f"{key}: no close"
    if stored is None:
        kind = prepared.context.get("kinds", {}).get(key)
        if kind is None:
            return None, f"{key}: what it is is unknown (no quote type)"
        if kind != "EQUITY":
            return None, f"{key}: not a company ({kind})"
    invalidate, bad_inv = rewrite(entry.get("invalidate"))
    confirm, _ = rewrite(entry.get("confirm"))
    buy, bad_buy = rewrite(entry.get("buy"))
    if not invalidate:
        return None, f"{key}: no sell condition the code can read ({'; '.join(bad_inv)})"
    if not new and not buy:
        return None, f"{key}: a candidate needs a buy condition ({'; '.join(bad_buy)})"
    if stored is None:
        m = Market(str(market))
        repo.insert_instrument(
            env.conn,
            Instrument(
                instrument_id=key,
                market=m,
                currency=MARKET_CURRENCY[m],
                kind=Kind.STOCK,
                ticker=ticker,
                name=_one_line(entry.get("name") or ticker, 60),
                yahoo_symbol=price[0],
            ),
            env.at,
        )
    pick_id = ai_repo.insert_pick(
        env.conn,
        ai_repo.NewPick(
            ledger_id=task.ledger_id,
            rule_id=RULE_ID,
            instrument_id=key,
            status="candidate",
            picked_on=date.fromisoformat(price[1]),
            picked_price=Decimal(price[2]),
            benchmark=benchmark,
            benchmark_price=Decimal(bench[1]),
            theme=_one_line(entry.get("theme"), 60),
            rationale=str(entry.get("rationale", ""))[:600],
            confirm=confirm,
            invalidate=invalidate,
            buy=[] if new else buy,
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
    if new:
        _ask_to_buy(env, task, pick_id, key, month)
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
    # Slots as they are now (a kept answer may be applied later than it was asked).
    slots = max(0, env.cfg.discovery_max_picks - held_count(env.conn, task.ledger_id))
    held_before = held_count(env.conn, task.ledger_id)
    waiting_before = len(ai_repo.picks_of(env.conn, task.ledger_id, RULE_ID, ("candidate",)))
    added: list[str] = []
    waiting: list[str] = []
    refused: list[str] = []
    for entry in picks:
        if not isinstance(entry, dict):
            refused.append("not an object")
            continue
        if len(added) >= slots:
            refused.append(f"{entry.get('ticker')}: no slot left")
            continue
        key, why = _new_pick(env, task, entry, True, prepared)
        if key:
            added.append(key)
        else:
            refused.append(why or "?")
    new_candidates: set[str] = set(added)
    for entry in candidates:
        if not isinstance(entry, dict):
            refused.append("not an object")
            continue
        key, why = _new_pick(env, task, entry, False, prepared)
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
            # Nothing is bought on this answer: each new pick waits for two '근거 있음' (E5).
            action="none",
            instrument_id=None,
            inputs=[
                {"key": "month", "value": month},
                {"key": "held", "value": held_before},
                {"key": "candidates", "value": waiting_before},
            ],
            outputs=[
                {"key": "new-picks", "value": len(added)},
                {"key": "candidates", "value": len(waiting)},
                {"key": "expired", "value": len(expired)},
            ],
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
    money, and the round trip through the index ETF that holds sold money until the buy.

    A holding without shares costs nothing to give up (all zero, a fact). Shares without a
    price, or dollars without a rate, cannot be costed: the question waits (RetryLaterError)
    rather than show the AI zeros as the code's numbers."""
    fees = env.cfg.fees
    held = pk.holding(env.conn, sold)
    if held is None:
        return SwitchCosts(ZERO, ZERO, ZERO, ZERO, ZERO)
    if sold_price is None:
        raise RetryLaterError(f"switch costs: no price of {sold_inst.instrument_id}")
    if sold_inst.currency is Currency.USD and rate is None:
        raise RetryLaterError("switch costs: no KRW/USD rate")
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
    # A switch buys: like a buy confirmation it reads what the code built, not the discovery's
    # own words (E5).
    packet = pk.join(
        pk.today_rows(env.at),
        [pk.DATA_NOT_ORDERS],
        ["# 판 종목 (가장 약한 보유)"],
        pk.code_header(sold, s_inst),
        pk.price_rows(sold, s_inst, s_quotes),
        pk.conditions(conn, sold, "invalidate", words=False),
        pk.metric_rows(conn, sold.instrument_id),
        pk.tax_rows(conn, env.cfg, sold, s_inst, s_quotes, env.at),
        ["# 살 종목 (후보)"],
        pk.code_header(candidate, c_inst),
        pk.price_rows(candidate, c_inst, c_quotes),
        pk.conditions(conn, candidate, "buy", words=False),
        pk.conditions(conn, candidate, "invalidate", words=False),
        pk.metric_rows(conn, candidate.instrument_id),
        pk.filing_rows(conn, candidate.instrument_id, today),
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
    cost = Decimal(str(prepared.context["costs"]["total_pct"])).quantize(Decimal("0.01"))
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
                {"key": "sold", "instrument_id": sold.instrument_id},
                {"key": "bought", "instrument_id": candidate.instrument_id},
                {"key": "cost", "value": float(cost)},
            ],
            outputs=[],
            votes=votes,  # 'switch' | 'keep', twice
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
