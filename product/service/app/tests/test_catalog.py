"""조건 카탈로그(TASKS T-20): 문서 표(DATA-CATALOG 1절 · ENGINE-RULES 11-3)와 `app/catalog.py`가 같아요.

항목 수 · 순서 · id · op · params 키 · 블록 열 · 강도 열 · 별칭, 그리고 DATA-CATALOG의 글자 열(항목 · 비교 ·
값 범위 · 단위 · 출처 · 백테스트 · 블록)을 문서에서 읽어 비교해요.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from app import catalog as cat

SERVICE = Path(__file__).resolve().parents[2]


def _table(path: Path, start: str, stop: str) -> list[list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith(start))
    rows = []
    for line in lines[i + 1 :]:
        if line.startswith(stop):
            break
        if line.startswith("|") and not line.startswith("|---"):
            rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows[1:]


# 1단계 동안은 `f33e2a9` 전 판에서 얼린 표(지금 코드와 같은 옛 표 · `tests/baseline/frozen/docs-before-f33e2a9/`)와 견줘요.
# 지금 문서(SERVICE / "DATA-CATALOG.md" · "ENGINE-RULES.md" · "SPEC.md")와의 대조는 3단계(글 고치기)에서 다시 켜요(Q-N18 답 (가)).
DOCS = Path(__file__).resolve().parent / "baseline" / "frozen" / "docs-before-f33e2a9"
CATALOG_ROWS = _table(DOCS / "DATA-CATALOG-1.md", "## 1. 조건 카탈로그", "- **주식 수 맞춤")
DICT_ROWS = _table(DOCS / "ENGINE-RULES-11-3.md", "### 11-3.", "- 값 범위")
SPEC_ROWS = _table(DOCS / "SPEC-4-9.md", "### 4-9.", "---")


def _code_list(cell: str) -> list[str]:
    """'gte · lte · consec(증가)' → ['gte', 'lte', 'consec']"""
    return [re.sub(r"\(.*\)$", "", p.strip()).strip("`") for p in cell.split(" · ") if p.strip() != "—"]


def _stage_cell(cell: str) -> tuple[set[str], bool]:
    main, _, rest = cell.partition(" · ")
    stages = {cat.CIRCLE[c] for c in main.split() if c in cat.CIRCLE}
    sortable = "④" in rest
    if cell == "④":
        return {"select"}, False
    return stages, sortable


def test_same_count_and_order() -> None:
    assert len(DICT_ROWS) == len(CATALOG_ROWS) == len(cat.ITEMS) == 53
    assert [r[0].strip("`") for r in DICT_ROWS] == [i.id for i in cat.ITEMS]
    # SPEC 4-9(정답)와 DATA-CATALOG 1절이 같은 표
    assert SPEC_ROWS == CATALOG_ROWS


@pytest.mark.parametrize("n", range(53))
def test_dictionary_row(n: int) -> None:
    """ENGINE-RULES 11-3: id · 이름 · op · params 키 · 블록 · 강도 · 별칭."""
    row = DICT_ROWS[n]
    item = cat.ITEMS[n]
    rid, name, ops, params, _value, blocks, strength, alias = row
    assert rid.strip("`") == item.id
    assert list(item.ops) == _code_list(ops), item.id
    keys = re.findall(r"`([a-z_0-9]+)`", re.sub(r"\([^()]*\)", "", params))  # 괄호 안(고르기 값 · 범위)은 빼요
    assert keys == [p.key for p in item.params], item.id
    stages, sortable = _stage_cell(blocks)
    assert set(item.stages) == stages, item.id
    assert item.sortable == sortable, item.id
    # 강도 열: 있음 · 없음 · gte만 있음 · gte 빼고 있음 · —
    if strength in ("—", "없음"):
        assert item.strength == {}, item.id
    elif strength == "있음":
        assert set(item.strength) == set(item.ops), item.id
    elif strength == "gte만 있음":
        assert set(item.strength) == {"gte"}
    elif strength == "gte 빼고 있음":
        assert set(item.strength) == set(item.ops) - {"gte"}
    else:
        pytest.fail(f"모르는 강도 열 {strength}")
    names = [a.strip() for a in re.sub(r"\([^()]*\)", "", alias).split(" · ") if a.strip()]
    assert sorted(item.alias) == sorted(set(names)), item.id
    assert name.startswith(item.name.split("(")[0].split(" · ")[0]) or item.name.startswith(name.split("(")[0])


@pytest.mark.parametrize("n", range(53))
def test_catalog_row_text(n: int) -> None:
    """DATA-CATALOG 1절의 글자 열 그대로."""
    category, name, ops, rng, unit, source, backtest, blocks = CATALOG_ROWS[n]
    item = cat.ITEMS[n]
    got = (item.category, item.name if item.id not in ("disclosure",) else name, item.text_ops, item.text_range,
           item.text_unit, item.text_source, item.text_backtest, item.text_blocks)
    if item.id == "disclosure":  # 문서 '항목'은 공시 종류 목록 전체, 코드 이름은 '공시'
        assert name.startswith("공시: ")
    assert got == (category, name, ops, rng, unit, source, backtest, blocks)


def test_catalog_blocks_match_dictionary_blocks() -> None:
    """두 문서의 블록 열이 같은 단계를 말해요(DATA-CATALOG는 '정렬' · '실행 방식'을 더 적어요)."""
    for crow, drow in zip(CATALOG_ROWS, DICT_ROWS, strict=True):
        c = {cat.CIRCLE[x] for x in crow[7].replace("정렬", "").split() if x in cat.CIRCLE}
        d = {cat.CIRCLE[x] for x in drow[5].split() if x in cat.CIRCLE}
        assert c == d, (crow[1], drow[0])


def test_locks_starts_and_chips() -> None:
    dart = [i.id for i in cat.ITEMS if i.lock == cat.LOCK_DART]
    assert set(dart) == {"market_cap", "per", "pbr", "psr", "dividend_yield", "roe", "op_margin", "profit_state",
                         "sales_growth", "profit_growth", "sales_growth_3y", "debt_ratio", "disclosure"}
    assert cat.locked("per", dart=False) and not cat.locked("per", dart=True) and not cat.locked("ma", dart=False)
    assert cat.start_date(["ma", "per"]) == (date(2016, 4, 1), "DART 재무가 2015년 보고서부터예요")
    assert cat.start_date(["ma"]) is None
    assert cat.item("exclude_warning").backtest == "no" and cat.CHIP_LIVE_ONLY in cat.item("exclude_warning").chips
    assert cat.item("sector").chips == (cat.CHIP_SECTOR_NOW,) and cat.item("sector").backtest == "partial"
    assert all(cat.CHIP_SHARES in cat.item(i).chips for i in ("market_cap", "per", "pbr", "psr", "dividend_yield"))


def test_exec_modes_and_aliases() -> None:
    assert cat.item("stop_loss").execs == ("intraday", "broker", "close")
    assert cat.item("trailing_stop").execs == ("intraday", "close")  # 조건주문 불가(R-X3)
    assert cat.item("max_hold").execs == ("close",)
    assert cat.V1_ALIASES == {
        "manual_list": "manual_list", "min_price": "price", "high_breakout": "high_n", "min_turnover": "turnover",
        "ma_cross_up": "ma", "ma_break_down": "ma", "rsi_below": "rsi", "stop_loss": "stop_loss",
        "take_profit": "take_profit", "max_hold": "max_hold", "next_open": "next_open", "top_n": "top_n",
        "equal": "equal", "max_per_stock": "max_per_stock", "rebalance_every": "rebalance_every",
    }  # v1 조건 15개 모두(R-C8)
    assert cat.SORTABLE == ("strength", "return_n", "turnover", "volatility", "market_cap", "per", "pbr", "psr",
                            "dividend_yield", "roe", "op_margin", "sales_growth")
    assert set(cat.SORTABLE) == set(next(p for p in cat.item("top_n").params if p.key == "by").choices)


def test_stage_lists() -> None:
    sig = {i.id for i in cat.items_for("signal")}
    assert "per" not in sig and "profit_state" in sig and "disclosure" in sig  # R-G4
    sell = {i.id for i in cat.items_for("sell")}
    assert {"stop_loss", "profit_state", "per", "debt_ratio", "index_ma"} <= sell and "roe" not in sell
    assert {i.id for i in cat.items_for("universe")} == {"manual_list", "market", "security_type", "exclude_preferred",
                                                         "exclude_leveraged", "listed_days", "sector",
                                                         "exclude_warning", "market_cap"}
    assert len(cat.describe()) == 53
