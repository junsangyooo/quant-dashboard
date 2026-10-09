"""Data packets: what the code hands the AI, in Korean Markdown with field keys (D25, T26).

The AI quotes numbers by their key ('metric.op_margin.2026Q2', 'now.close'), so every number in
a packet has one, and nothing the AI needs is left for it to look up (the web is only for the
quarterly discovery). A packet is rebuilt from the database for each call and stored with the
call (ai_calls.input), so any judgment can be read again with exactly what it saw.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from autotrade.config import Config
from autotrade.db import ai_repo, repo
from autotrade.domain import metrics
from autotrade.domain.conditions import (
    Check,
    Condition,
    ConditionError,
    check,
    check_buy,
    parse_condition,
)
from autotrade.domain.instruments import Currency, Instrument
from autotrade.domain.money import ZERO, round_half_up, round_won, usd_in_krw
from autotrade.domain.watch import window_return
from autotrade.engine import metric_table, sleeves
from autotrade.engine.tax import us_tax
from autotrade.market.service import MarketSources
from autotrade.rules.discovery import RULE_ID
from autotrade.timeutil import kst_date

Series = list[tuple[date, Decimal]]
HUNDRED = Decimal(100)
ONE_DECIMAL = Decimal("0.1")
FILING_DAYS = 90
PRICE_LOOKBACK = timedelta(days=45)
METRIC_ROWS = 8  # latest periods per metric in a packet
VERDICT_KO = {"hold": "유지", "weaken": "약화", "invalidated": "반증"}
OPS_KO = {"<": "<", "<=": "≤", ">": ">", ">=": "≥"}


@dataclass
class Quotes:
    """Adjusted closes and ratios a flow fetched before its call (by Yahoo symbol)."""

    closes: dict[str, Series] = field(default_factory=dict)
    ratios: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)

    def last(self, symbol: str) -> tuple[date, Decimal] | None:
        series = self.closes.get(symbol)
        return series[-1] if series else None


def fetch_quotes(
    sources: MarketSources,
    symbols: Iterable[str],
    start: date,
    end: date,
    ratio_symbols: Iterable[str] = (),
) -> Quotes:
    """Network: adjusted closes (and ratios) for a packet. Failures are kept, never raised."""
    quotes = Quotes()
    for symbol in sorted(set(symbols)):
        if sources.adjusted is None:
            quotes.errors[symbol] = "no adjusted-close source"
            continue
        try:
            quotes.closes[symbol] = sources.adjusted.fetch_adjusted(symbol, start, end)
        except Exception as exc:  # the packet says the price is unknown
            quotes.errors[symbol] = f"{type(exc).__name__}: {exc}"
    for symbol in sorted(set(ratio_symbols)):
        if sources.valuation is None:
            continue
        try:
            quotes.ratios[symbol] = sources.valuation.fetch_valuation(symbol)
        except Exception as exc:  # the packet says the ratio is unknown
            quotes.errors[f"ratios:{symbol}"] = f"{type(exc).__name__}: {exc}"
    return quotes


def quotes_for_pick(
    sources: MarketSources, pick: ai_repo.PickRow, inst: Instrument, today: date
) -> Quotes:
    start = min(pick.picked_on, today - PRICE_LOOKBACK) - timedelta(days=7)
    return fetch_quotes(
        sources, [inst.yahoo_symbol, pick.benchmark], start, today, [inst.yahoo_symbol]
    )


# ── text pieces ──────────────────────────────────────────────────────────────────────────────


def num(value: Decimal | None, places: Decimal | None = None) -> str:
    if value is None:
        return "모름"
    if places is not None:
        value = round_half_up(value, places)
    return format(value.normalize(), "f") if value == value.to_integral_value() else str(value)


def pct(fraction: Decimal | None) -> str:
    return "모름" if fraction is None else num(fraction * HUNDRED, ONE_DECIMAL)


def describe(cond: Condition) -> str:
    """A condition in words, for people and the AI (the JSON form goes alongside)."""
    if cond.type == "event":
        return f"사건: {cond.text}"
    op = OPS_KO.get(cond.op or "", cond.op or "")
    if cond.type == "price":
        return f"종가 {op} {num(cond.value)}"
    if cond.type == "valuation":
        return f"{cond.metric} {op} {num(cond.value)}"
    label = metrics.label(cond.metric or "")
    if cond.type == "streak":
        change = "전년 같은 기간보다" if cond.change == "yoy" else "직전 기간보다"
        way = "줄어듦" if cond.direction == "down" else "늘어남"
        return f"{label}이 {change} {way}, {cond.periods}기 연속"
    what = label
    if cond.change == "yoy":
        what = f"{label} 전년 대비 증가율"
    elif cond.change == "qoq":
        what = f"{label} 직전 기간 대비 증가율"
    text = f"{what} {op} {num(cond.value)}{'' if cond.unit == 'count' else cond.unit}"
    if cond.period:
        text += f" ({cond.period})"
    if cond.periods > 1:
        text += f", {cond.periods}기 연속"
    return text


def check_text(chk: Check) -> str:
    words = {
        "hit": "걸림",
        "clear": "안 걸림",
        "unknown": "모름",
        "skip": "AI가 판단(사건형)",
    }
    out = words[chk.verdict]
    if chk.verdict in ("hit", "clear") and chk.period:
        value = "" if chk.value is None else f" {num(chk.value, Decimal('0.01'))}"
        out += f" ({chk.period}{value})"
    elif chk.verdict == "unknown" and chk.reason:
        out += f" ({chk.reason})"
    return out


def clean(data: Mapping[str, Any]) -> dict[str, Any]:
    """An AI-written condition without its null fields (the schema allows them)."""
    return {k: v for k, v in data.items() if v is not None}


def conditions(
    conn: sqlite3.Connection,
    pick: ai_repo.PickRow,
    which: str,
    price: Decimal | None = None,
    ratios: Mapping[str, Decimal] | None = None,
) -> list[str]:
    """Numbered conditions with what the code found (which: confirm | invalidate | buy)."""
    items: list[dict[str, Any]] = getattr(pick, which)
    titles = {
        "confirm": "## 확인 조건 (confirm: 이어지면 근거가 산다)",
        "invalidate": "## 반증 조건 (invalidate: 하나라도 걸리면 두 번 확인한다)",
        "buy": "## 살 조건 (buy: 코드가 대조할 수 있는 것은 모두 맞아야 한다)",
    }
    lines = [titles[which]]
    if not items:
        return [*lines, "- (없음)"]
    for i, data in enumerate(items, start=1):
        try:
            cond = parse_condition(data)
        except ConditionError as exc:
            lines.append(f"{i}. (읽을 수 없는 조건: {exc}) {data}")
            continue
        if which == "buy":
            obs = (
                metric_table.observations(conn, pick.instrument_id, cond.metric)
                if cond.type in ("level", "streak") and cond.metric
                else []
            )
            chk = check_buy(cond, price, ratios or {}, obs)
        elif cond.type in ("level", "streak") and cond.metric:
            chk = check(cond, metric_table.observations(conn, pick.instrument_id, cond.metric))
        else:
            chk = Check(cond, "skip")
        note = f" · 메모: {cond.note}" if cond.note else ""
        lines.append(f"{i}. {describe(cond)} · 코드 대조: {check_text(chk)}{note}")
    text = pick.texts.get(f"{which}_text")
    if text:
        lines.append(f"- 고를 때 쓴 글: {text}")
    return lines


def header(pick: ai_repo.PickRow, inst: Instrument) -> list[str]:
    verdict = VERDICT_KO.get(pick.last_verdict or "", "없음")
    at = "" if pick.last_verdict_at is None else f" ({kst_date(pick.last_verdict_at)})"
    status = {"held": "보유", "candidate": "후보", "sold": "판매", "expired": "만료"}[pick.status]
    return [
        "## 종목",
        f"- 종목: {inst.name} ({inst.instrument_id}, {inst.yahoo_symbol})"
        f" · 시장 {inst.market.value} · 상태 {status} · 흐름: {pick.theme}",
        f"- 고른 날 {pick.picked_on} · 고른 가격 {num(pick.picked_price)}"
        f" · 그날 지수({pick.benchmark}) {num(pick.benchmark_price)}",
        f"- 고를 때 근거: {pick.rationale or '(없음)'}",
        f"- 고를 때 확신: {pick.confidence or '없음'} (기록만 한다. 비중에 쓰지 않는다)",
        f"- 마지막 판정: {verdict}{at} · 약화가 이어진 달 {pick.weak_months}",
    ]


def price_rows(pick: ai_repo.PickRow, inst: Instrument, quotes: Quotes) -> list[str]:
    lines = ["## 지금 값 (Yahoo 수정 종가, 배당 포함)", "| 칸 키 | 값 |", "|---|---|"]
    stock, index = quotes.closes.get(inst.yahoo_symbol), quotes.closes.get(pick.benchmark)
    last = quotes.last(inst.yahoo_symbol)
    if last is None:
        return [*lines, "| now.close | 모름 (시세를 받지 못함) |"]
    lines.append(f"| now.close | {num(last[1])} ({last[0]}) |")
    if stock and index:
        since = window_return(stock, index, pick.picked_on)
        if since is not None:
            lines += [
                f"| now.return_since_pick_pct | {pct(since.value)} |",
                f"| now.index_return_since_pick_pct | {pct(since.index)} |",
                f"| now.excess_since_pick_pp | {pct(since.value - since.index)} |",
            ]
        if len(stock) > 20:
            twenty = window_return(stock, index, stock[-21][0])
            if twenty is not None:
                lines += [
                    f"| now.return_20d_pct | {pct(twenty.value)} |",
                    f"| now.index_return_20d_pct | {pct(twenty.index)} |",
                ]
        high = max(c for _, c in stock)
        lines.append(f"| now.from_high_pct | {pct(last[1] / high - 1)} (기간 고점 대비) |")
    for key, value in sorted(quotes.ratios.get(inst.yahoo_symbol, {}).items()):
        lines.append(f"| now.{key} | {num(value, Decimal('0.01'))} |")
    return lines


def metric_rows(conn: sqlite3.Connection, instrument_id: str) -> list[str]:
    lines = [
        "## 지표 표 (공시에서 뽑은 값, '계산'은 코드가 두 값으로 계산)",
        "| 칸 키 | 값 | 단위 | 출처 |",
        "|---|---|---|---|",
    ]
    stored = {(r.metric, r.period): r for r in ai_repo.metric_values(conn, instrument_id)}
    titles: dict[int, str] = {}
    rows = 0
    for key, observations in metric_table.table(conn, instrument_id).items():
        for o in observations[-METRIC_ROWS:]:
            row = stored.get((key, o.period))
            source = "계산"
            if row is not None and row.filing_id is not None:
                if row.filing_id not in titles:
                    filing = ai_repo.get_filing(conn, row.filing_id)
                    titles[row.filing_id] = f"{filing.title} {filing.filed_on}"
                source = titles[row.filing_id]
            elif row is not None:
                source = row.source
            lines.append(f"| metric.{key}.{o.period} | {num(o.value)} | {o.unit} | {source} |")
            rows += 1
    if not rows:
        lines.append("| (없음) | | | 아직 뽑은 실적 공시가 없다 |")
    return lines


def filing_rows(conn: sqlite3.Connection, instrument_id: str, today: date) -> list[str]:
    lines = [f"## 최근 공시 ({FILING_DAYS}일)"]
    status_ko = {
        "relevant": "가림: 관련 있음",
        "irrelevant": "가림: 관련 없음",
        "done": "지표 뽑음",
        "queued": "처리 대기",
        "skipped": "정기 공시·고르기 전",
        "failed": "읽기 실패",
        "new": "새 공시",
    }
    filings = ai_repo.filings_of(conn, instrument_id, today - timedelta(days=FILING_DAYS))
    shown = [f for f in filings if f.kind != "skipped"]
    if not shown:
        return [*lines, "- (없음)"]
    for f in shown[-15:]:
        lines.append(f"- {f.filed_on} · {f.source.upper()} · {f.title} · {status_ko[f.status]}")
    return lines


def trigger_rows(conn: sqlite3.Connection, task: ai_repo.TaskRow) -> list[str]:
    lines = ["## 걸린 것 (코드가 매일 대조해서 찾음)"]
    for t in task.detail.get("triggers", []):
        if not isinstance(t, dict):
            continue
        if t.get("kind") == "shock":
            rel20 = t.get("rel20")
            lines.append(
                f"- 급락 {t.get('on')}: 하루 지수 대비 {pct(Decimal(str(t.get('day_rel'))))}%"
                + ("" if rel20 is None else f", 20거래일 지수 대비 {pct(Decimal(str(rel20)))}%")
                + " (문턱: 하루 -8% 또는 20거래일 -20%)"
            )
        elif t.get("kind") == "condition":
            try:
                text = describe(parse_condition(t.get("condition") or {}))
            except ConditionError:
                text = str(t.get("condition"))
            lines.append(
                f"- 반증 조건 {int(t.get('index', 0)) + 1} 걸림: {text} — {t.get('period')}"
                f" {t.get('value') or ''}".rstrip()
            )
        elif t.get("kind") == "filing":
            lines.append(f"- 공시 {t.get('filed_on')}: {t.get('title')} — 가림: {t.get('reason')}")
        elif t.get("kind") == "monthly":
            lines.append(f"- 월 점검 판정: {t.get('verdict')} ({t.get('month')})")
    if len(lines) == 1:
        lines.append(f"- {task.trigger}")
    return lines


@dataclass(frozen=True)
class Holding:
    qty: int
    cost_krw: Decimal


def holding(conn: sqlite3.Connection, pick: ai_repo.PickRow) -> Holding | None:
    pos = ai_repo.load_sleeve(conn, pick.ledger_id, pick.rule_id).positions.get(pick.instrument_id)
    return None if pos is None else Holding(pos.qty, pos.cost_krw)


def tax_rows(
    conn: sqlite3.Connection,
    cfg: Config,
    pick: ai_repo.PickRow,
    inst: Instrument,
    quotes: Quotes,
    at: datetime,
) -> list[str]:
    """US stocks only (D36): this year's numbers for the whole ledger and this position."""
    if inst.currency is not Currency.USD:
        return []
    held = holding(conn, pick)
    last = quotes.last(inst.yahoo_symbol)
    fx = repo.fx_at(conn, at)
    unrealized = ZERO
    known = held is not None and last is not None and fx is not None
    if held is not None and last is not None and fx is not None:
        unrealized = usd_in_krw(last[1] * held.qty, fx.rate) - held.cost_krw
    numbers = us_tax(conn, cfg, pick.ledger_id, kst_date(at).year, unrealized)
    lines = [
        "## 세금 (미국 종목, 계좌 전체, 코드 계산 — 22%, 기본공제 250만 원)",
        "| 칸 키 | 값 |",
        "|---|---|",
        f"| tax.year | {numbers.year} |",
        f"| tax.realized_krw | {num(numbers.realized_krw)}"
        " (올해 해외 실현 손익, 장투 미국 ETF 포함) |",
        f"| tax.deduction_left_krw | {num(numbers.deduction_left_krw)} |",
    ]
    if known:
        lines += [
            f"| tax.unrealized_krw | {num(numbers.unrealized_krw)}"
            " (이 종목 평가 이익, 산 날 환율 기준) |",
            f"| tax.if_sold_krw | {num(numbers.tax_if_sold_krw)}"
            " (지금 다 팔면 늘어나는 올해 세금) |",
        ]
    else:
        lines.append("| tax.unrealized_krw | 모름 (보유 없음, 시세나 환율 없음) |")
    return lines


def dictionary_rows() -> list[str]:
    lines = [
        "## 지표 사전 (조건에 쓸 수 있는 지표)",
        "| 키 | 이름 | 단위 | 기간 | 뜻 |",
        "|---|---|---|---|---|",
    ]
    units = {"pct": "%", "money": "KRW/USD", "ratio": "x", "count": "count", "any": "%·KRW·USD·x"}
    periods = {"quarter": "분기", "month": "월", "year": "연", "any": "아무 기간"}
    for d in metrics.DICTIONARY:
        key = d.key if d.param is None else f"{d.key}:<{d.param}>"
        lines.append(
            f"| {key} | {d.label.replace('{param}', '<' + (d.param or '') + '>')} |"
            f" {units[d.unit_kind]} | {periods[d.period_kind]} | {d.description} |"
        )
    return lines


CONDITION_FORM = """## 조건 형식 (JSON, 이 모양만 코드가 읽는다)
- 수준: {"type":"level","metric":"op_margin","op":"<","value":20,"unit":"%"}
  - 증가율로 비교: "change":"yoy"(전년 같은 기간) 또는 "qoq"(직전 기간), 단위는 %
  - N기 연속: "periods":2 · 한 기간만: "period":"2026Q4"
    (기간 키: 2026Q3, FY2026Q4, 2026-08, FY2027)
- 연속 변화:
  {"type":"streak","metric":"operating_income","change":"yoy","direction":"down","periods":2}
- 사건(AI만 판단): {"type":"event","kind":"customer_loss","text":"상위 고객 이탈 공시"}
- 살 조건: {"type":"price","op":"<=","value":74100} 또는
  {"type":"valuation","metric":"per_fwd","op":"<=","value":15} (per_fwd·per·pbr)
- 단위: % · KRW · USD · x · count. 금액은 원·달러 단위 숫자(억·조를 풀어 쓴다).
- 확실하지 않은 옮김은 "note"에 적는다."""


def join(*blocks: Sequence[str]) -> str:
    return "\n\n".join("\n".join(b) for b in blocks if b)


def today_rows(at: datetime) -> list[str]:
    return [f"기준: {kst_date(at)} (한국 시간)"]


def sleeve_rows(conn: sqlite3.Connection, ledger_id: str) -> list[str]:
    """The rule's holdings with the last watch's excess per pick (discovery, switch)."""
    excess = ai_repo.latest_pick_excess(conn, ledger_id, RULE_ID)
    lines = [
        "## 지금 보유 (3년 발굴)",
        "| 종목 | 흐름 | 고른 날 | 마지막 판정 | 지수 대비(%p) |",
        "|---|---|---|---|---|",
    ]
    held = ai_repo.picks_of(conn, ledger_id, RULE_ID, ("held",))
    for p in held:
        inst = repo.get_instrument(conn, p.instrument_id)
        lines.append(
            f"| {inst.name} ({inst.instrument_id}) | {p.theme} | {p.picked_on} |"
            f" {VERDICT_KO.get(p.last_verdict or '', '없음')} | {num(excess.get(p.pick_id))} |"
        )
    if not held:
        lines.append("| (없음) | | | | |")
    return lines


def sleeve_value_note(conn: sqlite3.Connection, ledger_id: str, at: datetime) -> list[str]:
    state = sleeves.view(conn, ledger_id, RULE_ID)
    fx = repo.fx_at(conn, at)
    cash = state.cash_of(Currency.KRW) + (
        usd_in_krw(state.cash_of(Currency.USD), fx.rate) if fx is not None else ZERO
    )
    return [
        f"- 규칙 현금(원화 환산): {num(round_won(cash))}원 · 보유 종목 수 {len(state.positions)}"
    ]
