"""Conditions in the fixed JSON form (D26, PHASE2.md §3) and how the code checks them (AI 0).

  level      {"type":"level","metric":"op_margin","op":"<","value":20,"unit":"%"}
             optional "change": "yoy" | "qoq"  compare the % change instead of the value
                      "periods": N             the last N consecutive periods all meet it
                      "period": "2026Q3"       one exact period
  streak     {"type":"streak","metric":"operating_income","change":"yoy","direction":"down",
              "periods":2}                     N consecutive periods moved that way
  event      {"type":"event","kind":"customer_loss","text":"상위 XPU 고객 이탈 공시"}
             only the AI judges it (the code skips it)
  price      {"type":"price","op":"<=","value":74100}                buy: latest close
  valuation  {"type":"valuation","metric":"per_fwd","op":"<=","value":15}  buy: valuation

Any condition may carry "note" (why a transcription is uncertain); it is never evaluated.
A sell list is OR: one hit sets off the two-step confirmation (D27). A buy list is AND: every
condition the code can check must hold (an event in it is left to the buy confirmation). A
confirm list is read by the AI reviews only. For months, "qoq" means the previous month.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from autotrade.domain import metrics
from autotrade.domain.periods import Period, PeriodError, parse_period

TYPES = ("level", "streak", "event", "price", "valuation")
OPS = ("<", "<=", ">", ">=")
CHANGES = ("yoy", "qoq")
DIRECTIONS = ("down", "up")
VALUATION_METRICS = ("per_fwd", "per", "pbr")
HUNDRED = Decimal(100)

_FIELDS = {
    "level": {"type", "metric", "op", "value", "unit", "change", "periods", "period", "note"},
    "streak": {"type", "metric", "change", "direction", "periods", "note"},
    "event": {"type", "kind", "text", "note"},
    "price": {"type", "op", "value", "note"},
    "valuation": {"type", "metric", "op", "value", "note"},
}


class ConditionError(ValueError):
    pass


@dataclass(frozen=True)
class Condition:
    type: str
    metric: str | None = None
    op: str | None = None
    value: Decimal | None = None
    unit: str | None = None
    change: str | None = None
    direction: str | None = None
    periods: int = 1
    period: str | None = None
    kind: str | None = None
    text: str | None = None
    note: str | None = None

    @property
    def is_sell_metric(self) -> bool:
        """Checked by the code against the metric table."""
        return self.type in ("level", "streak")


def _number(value: Any, what: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ConditionError(f"{what} must be a number")
    try:
        out = Decimal(str(value))
    except InvalidOperation as exc:
        raise ConditionError(f"{what} must be a number") from exc
    if not out.is_finite():
        raise ConditionError(f"{what} must be finite")
    return out


def _choice(data: Mapping[str, Any], key: str, options: Sequence[str]) -> str:
    value = data.get(key)
    if value not in options:
        raise ConditionError(f"{key} must be one of {', '.join(options)}, got {value!r}")
    return str(value)


def parse_condition(data: Mapping[str, Any]) -> Condition:
    """One condition from its JSON form. Raises ConditionError (checked against the dictionary)."""
    if not isinstance(data, Mapping):
        raise ConditionError("a condition is an object")
    kind = _choice(data, "type", TYPES)
    extra = set(data) - _FIELDS[kind]
    if extra:
        raise ConditionError(f"{kind}: unknown fields {sorted(extra)}")
    note = data.get("note")
    if note is not None and not isinstance(note, str):
        raise ConditionError("note must be text")
    if kind == "event":
        ev_kind, text = data.get("kind"), data.get("text")
        if not isinstance(ev_kind, str) or not ev_kind.strip():
            raise ConditionError("event: kind is required")
        if not isinstance(text, str) or not text.strip():
            raise ConditionError("event: text is required")
        return Condition("event", kind=ev_kind.strip(), text=text.strip(), note=note)
    if kind == "price":
        value = _number(data.get("value"), "price: value")
        if value <= 0:
            raise ConditionError("price: value must be positive")
        return Condition("price", op=_choice(data, "op", OPS), value=value, note=note)
    if kind == "valuation":
        return Condition(
            "valuation",
            metric=_choice(data, "metric", VALUATION_METRICS),
            op=_choice(data, "op", OPS),
            value=_number(data.get("value"), "valuation: value"),
            note=note,
        )
    metric = data.get("metric")
    if not isinstance(metric, str):
        raise ConditionError(f"{kind}: metric is required")
    try:
        metrics.resolve(metric)
    except metrics.MetricError as exc:
        raise ConditionError(str(exc)) from exc
    periods = data.get("periods", 1)
    if isinstance(periods, bool) or not isinstance(periods, int) or periods < 1:
        raise ConditionError(f"{kind}: periods must be a whole number >= 1")
    if kind == "streak":
        return Condition(
            "streak",
            metric=metric,
            change=_choice(data, "change", CHANGES),
            direction=_choice(data, "direction", DIRECTIONS),
            periods=periods,
            note=note,
        )
    change = data.get("change")
    if change is not None and change not in CHANGES:
        raise ConditionError(f"level: change must be one of {', '.join(CHANGES)}")
    unit = data.get("unit")
    if unit not in metrics.UNITS:
        raise ConditionError(f"level: unit must be one of {', '.join(metrics.UNITS)}")
    if change is not None and unit != "%":
        raise ConditionError("level: a change is compared in %")
    if change is None and not metrics.unit_fits(metric, str(unit)):
        raise ConditionError(f"level: {metric} is not measured in {unit}")
    period = data.get("period")
    if period is not None:
        try:
            parse_period(str(period))
        except PeriodError as exc:
            raise ConditionError(str(exc)) from exc
        if periods != 1:
            raise ConditionError("level: one exact period cannot also need several periods")
    return Condition(
        "level",
        metric=metric,
        op=_choice(data, "op", OPS),
        value=_number(data.get("value"), "level: value"),
        unit=str(unit),
        change=change,
        periods=periods,
        period=None if period is None else str(period),
        note=note,
    )


def condition_digest(data: Any) -> str:
    """A short fingerprint of a condition (or a list of them) in its JSON form: a rewritten
    condition is a new one for the 'once per data point' rule."""
    text = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha1(text.encode()).hexdigest()[:10]


def parse_conditions(items: Any) -> list[Condition]:
    if not isinstance(items, list):
        raise ConditionError("conditions are a list")
    return [parse_condition(c) for c in items]


def condition_json(c: Condition) -> dict[str, Any]:
    """The JSON form back (numbers as plain JSON numbers)."""
    out: dict[str, Any] = {"type": c.type}
    for key in ("metric", "op"):
        value = getattr(c, key)
        if value is not None:
            out[key] = value
    if c.value is not None:
        out["value"] = int(c.value) if c.value == c.value.to_integral_value() else float(c.value)
    for key in ("unit", "change", "direction", "period", "kind", "text"):
        value = getattr(c, key)
        if value is not None:
            out[key] = value
    if c.type == "streak" or c.periods != 1:
        out["periods"] = c.periods
    if c.note is not None:
        out["note"] = c.note
    return out


# ── checking against the metric table ─────────────────────────────────────────────────────


@dataclass(frozen=True)
class Observation:
    period: str
    value: Decimal
    unit: str


@dataclass(frozen=True)
class Check:
    condition: Condition
    verdict: str  # 'hit' | 'clear' | 'unknown' | 'skip'
    period: str | None = None  # the latest period looked at
    value: Decimal | None = None  # what was compared (a value, or a change in %)
    run: int = 0  # periods in a row that meet it, up to the latest
    reason: str | None = None  # why 'unknown'


def meets(value: Decimal, op: str, threshold: Decimal) -> bool:
    if op == "<":
        return value < threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    return value >= threshold


def _points(observations: Sequence[Observation]) -> list[tuple[Period, Decimal, str]]:
    """One family of periods, in order; the latest observation sets the family and the unit."""
    parsed: list[tuple[Period, Decimal, str]] = []
    for o in observations:
        try:
            parsed.append((parse_period(o.period), o.value, o.unit))
        except PeriodError:
            continue
    if not parsed:
        return []
    parsed.sort(key=lambda x: x[0])
    family, unit = parsed[-1][0].family, parsed[-1][2]
    return [x for x in parsed if x[0].family == family and x[2] == unit]


def _changes(pts: list[tuple[Period, Decimal, str]], change: str) -> list[tuple[Period, Decimal]]:
    by = {p: v for p, v, _ in pts}
    out: list[tuple[Period, Decimal]] = []
    for p, v, _ in pts:
        ref = p.year_ago() if change == "yoy" else p.previous()
        base = by.get(ref)
        if base is None or base <= 0:
            continue  # no growth rate from a missing or negative base
        out.append((p, (v / base - 1) * HUNDRED))
    return out


def _trailing_run(seq: list[tuple[Period, bool]]) -> int:
    """How many consecutive periods up to the latest have the flag set."""
    run = 0
    for i in range(len(seq) - 1, -1, -1):
        p, flag = seq[i]
        if not flag:
            break
        if run and seq[i + 1][0].previous() != p:
            break  # a gap ends the run
        run += 1
    return run


def check(cond: Condition, observations: Sequence[Observation]) -> Check:
    """Check one sell (or confirm) condition against a metric's stored values."""
    if cond.type not in ("level", "streak"):
        return Check(cond, "skip", reason="not checked by the code")
    pts = _points(observations)
    if not pts:
        return Check(cond, "unknown", reason="no values")
    if cond.type == "streak":
        if cond.change is None or cond.direction is None:  # pragma: no cover — parse ensures
            raise ConditionError("streak without change or direction")
        by = {p: v for p, v, _ in pts}
        moves: list[tuple[Period, bool]] = []
        for p, v, _ in pts:
            ref = p.year_ago() if cond.change == "yoy" else p.previous()
            if ref not in by:
                continue
            moves.append((p, v < by[ref] if cond.direction == "down" else v > by[ref]))
        if not moves:
            return Check(cond, "unknown", reason="no period to compare with")
        run = _trailing_run(moves)
        last_p = moves[-1][0]
        return Check(cond, "hit" if run >= cond.periods else "clear", period=last_p.key, run=run)
    if cond.op is None or cond.value is None or cond.unit is None:  # pragma: no cover
        raise ConditionError("level without op, value or unit")
    if cond.change is None and pts[-1][2] != cond.unit:
        return Check(cond, "unknown", reason=f"values are in {pts[-1][2]}, not {cond.unit}")
    series: list[tuple[Period, Decimal]] = (
        _changes(pts, cond.change) if cond.change else [(p, v) for p, v, _ in pts]
    )
    if not series:
        return Check(cond, "unknown", reason="no period to compare with")
    if cond.period is not None:
        want = parse_period(cond.period)
        found = [v for p, v in series if p == want]
        if not found:
            return Check(cond, "unknown", period=cond.period, reason="not reported yet")
        hit = meets(found[0], cond.op, cond.value)
        return Check(cond, "hit" if hit else "clear", cond.period, found[0], 1 if hit else 0)
    flags = [(p, meets(v, cond.op, cond.value)) for p, v in series]
    run = _trailing_run(flags)
    last_p, last_v = series[-1]
    return Check(cond, "hit" if run >= cond.periods else "clear", last_p.key, last_v, run=run)


@dataclass(frozen=True)
class Distance:
    """How far a pick has come toward a sell condition, for the gauge (화면-맞춤.md ②).

    progress: 0 at the value on the pick day, 100 at the sell line. margin: what is left, in the
    condition's unit (level), or periods_left for conditions counted in periods.
    """

    progress: Decimal
    margin: Decimal | None
    unit: str | None
    periods_left: int | None


def distance(chk: Check, baseline: Decimal | None) -> Distance | None:
    cond = chk.condition
    if chk.verdict not in ("hit", "clear"):
        return None
    if chk.verdict == "hit":
        left = 0 if cond.type == "streak" or cond.periods > 1 else None
        return Distance(HUNDRED, Decimal(0) if left is None else None, cond.unit, left)
    if cond.type == "streak" or cond.periods > 1:
        need = cond.periods
        progress = Decimal(chk.run) * HUNDRED / Decimal(need)
        return Distance(progress, None, None, need - chk.run)
    if cond.op is None or cond.value is None or chk.value is None:
        return None
    current, line = chk.value, cond.value
    start = current if baseline is None else baseline
    if cond.op in ("<", "<="):
        span, gone = start - line, start - current
        margin = current - line
    else:
        span, gone = line - start, current - start
        margin = line - current
    if span <= 0:
        progress = HUNDRED if margin <= 0 else Decimal(0)
    else:
        progress = max(Decimal(0), min(HUNDRED, gone * HUNDRED / span))
    return Distance(progress, margin, cond.unit, None)


def check_buy(
    cond: Condition,
    price: Decimal | None,
    ratios: Mapping[str, Decimal],
    observations: Sequence[Observation] = (),
) -> Check:
    """One buy condition: the latest close, a valuation ratio, or a metric (level, streak)."""
    if cond.type == "event":
        return Check(cond, "skip", reason="only the AI judges it")
    if cond.type in ("level", "streak"):
        return check(cond, observations)
    if cond.op is None or cond.value is None:  # pragma: no cover — parse ensures
        raise ConditionError(f"{cond.type} without op or value")
    if cond.type == "price":
        if price is None:
            return Check(cond, "unknown", reason="no close")
        return Check(cond, "hit" if meets(price, cond.op, cond.value) else "clear", value=price)
    ratio = ratios.get(cond.metric or "")
    if ratio is None:
        return Check(cond, "unknown", reason=f"no {cond.metric}")
    return Check(cond, "hit" if meets(ratio, cond.op, cond.value) else "clear", value=ratio)


def buy_met(checks: Sequence[Check]) -> bool:
    """Every checkable buy condition holds (and there is at least one)."""
    counted = [c for c in checks if c.verdict != "skip"]
    return bool(counted) and all(c.verdict == "hit" for c in counted)
