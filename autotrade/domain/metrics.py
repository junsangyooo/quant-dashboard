"""The metric dictionary: the metrics a sell or buy condition may name (D26, PHASE2.md §3).

A key is either plain ('op_margin') or takes one parameter after a colon
('segment_revenue:AI', 'guidance:2027 매출 성장'). The parameter is the company's own word for a
segment or a guidance item. Labels are what the screens show beside a gauge ('이익률', 'AI 매출').

Where the numbers come from:
- financials: the quarterly income statement (revenue, operating income, net income); in phase 2
  they are read from the earnings filing by the extraction step like the rest.
- extraction: '실적 지표 뽑기' (Haiku) reads them from the filing text (T27).
- derived: the code computes them from two stored metrics of the same period.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str  # screen data; '{param}' is replaced by the parameter
    unit_kind: str  # 'pct' | 'money' | 'ratio' | 'count' | 'any'
    period_kind: str  # 'quarter' | 'month' | 'year' | 'any'
    source: str  # 'financials' | 'extraction' | 'derived'
    description: str
    param: str | None = None  # name of the ':<...>' part
    formula: tuple[str, str] | None = None  # derived: (numerator, denominator)
    scale: int = 1  # derived: multiply the ratio (100 for a percentage)


DICTIONARY: tuple[MetricDef, ...] = (
    MetricDef("revenue", "매출", "money", "quarter", "financials", "매출액(연결)"),
    MetricDef("operating_income", "영업이익", "money", "quarter", "financials", "영업이익(연결)"),
    MetricDef("net_income", "순이익", "money", "quarter", "financials", "당기순이익(연결, 지배)"),
    MetricDef(
        "op_margin",
        "이익률",
        "pct",
        "quarter",
        "derived",
        "영업이익률 = 영업이익 / 매출 × 100",
        formula=("operating_income", "revenue"),
        scale=100,
    ),
    MetricDef("eps", "EPS", "money", "any", "financials", "주당순이익(회사가 쓰는 기준)"),
    MetricDef("fcf", "FCF", "money", "any", "extraction", "잉여현금흐름"),
    MetricDef("ebitda_margin", "EBITDA 마진", "pct", "quarter", "extraction", "EBITDA / 매출"),
    MetricDef("net_debt_to_ebitda", "순부채/EBITDA", "ratio", "any", "extraction", "배수"),
    MetricDef("backlog", "수주잔고", "money", "quarter", "extraction", "기말 수주잔고"),
    MetricDef("new_orders", "신규 수주", "money", "any", "extraction", "기간 중 신규 수주"),
    MetricDef(
        "book_to_bill",
        "수주/매출",
        "ratio",
        "any",
        "derived",
        "신규 수주 / 매출(같은 기간, 같은 통화)",
        formula=("new_orders", "revenue"),
    ),
    MetricDef(
        "monthly_revenue_yoy", "월매출 전년비", "pct", "month", "extraction", "월매출 전년 대비 %"
    ),
    MetricDef(
        "segment_revenue",
        "{param} 매출",
        "money",
        "any",
        "extraction",
        "부문·제품 매출",
        param="부문",
    ),
    MetricDef(
        "segment_operating_income",
        "{param} 영업이익",
        "money",
        "quarter",
        "extraction",
        "부문 영업이익",
        param="부문",
    ),
    MetricDef(
        "segment_op_margin",
        "{param} 이익률",
        "pct",
        "quarter",
        "extraction",
        "부문 영업이익률",
        param="부문",
    ),
    MetricDef(
        "segment_backlog",
        "{param} 수주잔고",
        "money",
        "quarter",
        "extraction",
        "부문 기말 수주잔고",
        param="부문",
    ),
    MetricDef(
        "guidance",
        "{param}",
        "any",
        "any",
        "extraction",
        "회사가 낸 목표·전망(구간이면 하한)",
        param="항목",
    ),
)

BY_KEY: dict[str, MetricDef] = {m.key: m for m in DICTIONARY}

# Units a metric value or a condition may carry.
UNITS = ("%", "KRW", "USD", "x", "count")
UNIT_KIND = {"%": "pct", "KRW": "money", "USD": "money", "x": "ratio", "count": "count"}


class MetricError(ValueError):
    pass


def resolve(key: str) -> tuple[MetricDef, str | None]:
    """The dictionary entry of a full key and its parameter. Raises MetricError."""
    base, sep, param = key.partition(":")
    d = BY_KEY.get(base)
    if d is None:
        raise MetricError(f"{key!r} is not in the metric dictionary")
    if d.param is None and sep:
        raise MetricError(f"{base!r} takes no parameter")
    if d.param is not None and not param.strip():
        raise MetricError(f"{base!r} needs a {d.param} after ':'")
    return d, (param.strip() or None) if sep else None


def label(key: str) -> str:
    d, param = resolve(key)
    return d.label.replace("{param}", param or "")


def unit_fits(key: str, unit: str) -> bool:
    """Can a value of this metric be in this unit?"""
    d, _ = resolve(key)
    kind = UNIT_KIND.get(unit)
    if kind is None:
        return False
    return d.unit_kind in ("any", kind)
