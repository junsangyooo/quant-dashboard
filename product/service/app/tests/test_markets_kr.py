"""국내 시장 정보 한 곳(P1-05 · ARCHITECTURE 4절 '시장' · QUALITY E7 · T1 순수 함수 경계값).

한국 시간 · 장 시간 · 확정 시각 · 휴장 규칙 · 호가 단위 · 가격 제한폭은 `app/domain/markets/kr.py`에만 정의해요(5벌 → 1벌).
"""

from __future__ import annotations

import ast
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from app.domain.markets import kr

ROOT = Path(__file__).resolve().parent.parent
KR = ROOT / "app" / "domain" / "markets" / "kr.py"


def _timezone_defs(path: Path) -> list[int]:
    """`timezone(timedelta(hours=9))` 꼴(한국 시간 정의)이 있는 줄."""
    out = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and getattr(node.func, "id", getattr(node.func, "attr", "")) == "timezone" \
                and node.args and isinstance(node.args[0], ast.Call) \
                and getattr(node.args[0].func, "id", getattr(node.args[0].func, "attr", "")) == "timedelta":
            out.append(node.lineno)
    return out


def test_one_kst_definition_in_app() -> None:
    found = {p.relative_to(ROOT).as_posix(): _timezone_defs(p) for p in sorted((ROOT / "app").rglob("*.py"))}
    assert {k: v for k, v in found.items() if v} == {"app/domain/markets/kr.py": _timezone_defs(KR)}
    assert len(_timezone_defs(KR)) == 1
    assert kr.KST.utcoffset(None) == timedelta(hours=9)


def test_weekday_rule_and_hours() -> None:
    fri, sat = date(2026, 10, 30), date(2026, 10, 31)
    assert kr.weekday_open(fri) and not kr.weekday_open(sat)
    h = kr.weekday_hours(fri)
    assert (h.open, h.known, h.start) == (True, False, datetime(2026, 10, 30, 9, 0, tzinfo=kr.KST))
    assert h.shift == timedelta(0) and h.at(8, 30) == datetime(2026, 10, 30, 8, 30, tzinfo=kr.KST)
    assert kr.weekday_hours(sat) == kr.DayHours(sat, False, None, False)
    late = kr.DayHours(fri, True, datetime(2026, 10, 30, 10, 0, tzinfo=kr.KST), True)
    assert late.shift == timedelta(hours=1) and late.at(8, 35) == datetime(2026, 10, 30, 9, 35, tzinfo=kr.KST)


def test_complete_until_without_calendar_and_day_end() -> None:
    assert kr.complete_until(datetime(2026, 11, 2, 19, 59, tzinfo=kr.KST)) == date(2026, 10, 30)
    assert kr.complete_until(datetime(2026, 11, 2, 20, 0, tzinfo=kr.KST)) == date(2026, 11, 2)
    assert kr.day_end(date(2026, 11, 2)).isoformat() == "2026-11-02T23:59:59+09:00"


def test_tick_size_edges() -> None:
    edges = [(1_999, 1), (2_000, 5), (4_999, 5), (5_000, 10), (19_999, 10), (20_000, 50), (49_999, 50),
             (50_000, 100), (199_999, 100), (200_000, 500), (499_999, 500), (500_000, 1_000)]
    assert [kr.tick_size(p) for p, _ in edges] == [t for _, t in edges]
    assert kr.tick_round(10_004) == 10_000.0 and kr.tick_round(10_006) == 10_010.0
    assert kr.ticks_below(2_000, 1) == 1_999 and kr.ticks_below(1, 3) == 1


def test_price_limit_is_the_old_literals() -> None:
    """하한가 비율은 전에 쓰던 0.7 그대로 · 응답 이상 문턱은 전의 Decimal('0.30') 그대로(값이 같아 계산도 같음)."""
    assert float(1 - kr.PRICE_LIMIT) == 0.7 and kr.PRICE_LIMIT == Decimal("0.30")
    assert kr.lower_limit(10_000) == 7_000 and kr.lower_limit(10_001) == 7_010
