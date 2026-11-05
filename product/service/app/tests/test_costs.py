"""거래 비용 한 표(TASKS P1-10 · ARCHITECTURE 4절 '시장' · ENGINE-RULES R-B1 · R-L7).

수수료 · 매도 세금 · 배당 원천징수 숫자는 `app/domain/costs.py`에만 정의해요. 서버(`app/`)의 다른 파일과 웹 `src/`에 그 숫자 ·
그 숫자의 퍼센트 글 · 비용 이름의 상수 정의가 있으면 실패해요(시험 · 독스트링 · 파이썬 주석 · 생성 타입은 뺌 · 웹은 줄 단위라 주석도 봄).
"""

from __future__ import annotations

import ast
import math
import re
from datetime import date
from pathlib import Path

from app.domain import costs

ROOT = Path(__file__).resolve().parent.parent
COSTS = Path("app/domain/costs.py")
WEB_SKIP = {"types.gen.ts"}
COST_NAME = re.compile(r"(^|_)(FEES?|TAX(ES)?|WITHHOLD\w*|COMMISSIONS?)(_|$)")


def _rates() -> list[float]:
    return sorted({r for row in costs.TABLE for r in (row.fee, row.sell_tax, row.dividend_withholding)})


def _numbers() -> list[float]:
    """비용 비율과 그것으로 바로 만든 꼴(1 − r · 1 + r · 퍼센트 r × 100)."""
    return [v for r in _rates() for v in (r, 1 - r, 1 + r, r * 100)]


def _percent_text() -> re.Pattern[str]:
    """비용 비율을 퍼센트 글로 쓴 꼴(예: '0.18%' · '0.015 %' · '15.4%')."""
    forms = sorted({repr(round(r * 100, 10)) for r in _rates()}, key=len, reverse=True)
    return re.compile(r"(?<![\d.])(" + "|".join(re.escape(f) for f in forms) + r")0*\s*%")


def _docstrings(tree: ast.AST) -> set[int]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                out.add(id(first.value))
    return out


def python_cost_literals(app_root: Path) -> dict[str, list[str]]:
    """`app_root`(앱 패키지 폴더의 부모) 아래 `app/**/*.py`에서 `app/domain/costs.py` 밖의 비용 숫자 · 퍼센트 글 · 비용 상수 이름."""
    numbers, text = _numbers(), _percent_text()
    found: dict[str, list[str]] = {}
    for path in sorted((app_root / "app").rglob("*.py")):
        rel = path.relative_to(app_root)
        if rel == COSTS:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        docs = _docstrings(tree)
        hits = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and type(node.value) in (int, float) and \
                    any(math.isclose(node.value, v, rel_tol=1e-12, abs_tol=0) for v in numbers):
                hits.append(f"{node.lineno}: 숫자 {node.value!r}")
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
                hits += [f"{node.lineno}: 글 {m.group(0)!r}" for m in text.finditer(node.value)]
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                for t in targets:
                    for name in ast.walk(t):
                        if isinstance(name, ast.Name) and name.id.isupper() and COST_NAME.search(name.id):
                            hits.append(f"{node.lineno}: 이름 {name.id}")
        if hits:
            found[rel.as_posix()] = sorted(hits)
    return found


def web_cost_literals(src: Path) -> dict[str, list[str]]:
    """웹 `src/` 글(ts · tsx · css · json)에서 비용 숫자 · 퍼센트 글(생성 타입 뺌)."""
    numbers = "|".join(re.escape(repr(r)) for r in _rates())
    pattern = re.compile(rf"(?<![\d.])({numbers})(?!\d)|{_percent_text().pattern}")
    found: dict[str, list[str]] = {}
    for path in sorted(src.rglob("*")):
        if path.suffix not in {".ts", ".tsx", ".css", ".json"} or path.name in WEB_SKIP or "node_modules" in path.parts:
            continue
        hits = [f"{i}: {m.group(0)!r}" for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                for m in pattern.finditer(line)]
        if hits:
            found[path.relative_to(src).as_posix()] = hits
    return found


def test_values_are_the_old_code_values() -> None:
    """옮기기 전 `engine.FEE` · `engine.SELL_TAX` · `live.py`의 `(1 - 0.154)` 그대로(값이 같아 계산도 같음)."""
    assert (costs.FEE, costs.SELL_TAX, costs.DIVIDEND_WITHHOLDING) == (0.00015, 0.0018, 0.154)
    assert 1 - costs.DIVIDEND_WITHHOLDING == 1 - 0.154 and costs.FEE + costs.SELL_TAX == 0.00015 + 0.0018


def test_table_is_date_keyed_and_covers_every_day() -> None:
    since = [row.since for row in costs.TABLE]
    assert since[0] == date.min and since == sorted(since) and len(set(since)) == len(since)
    assert costs.costs_on("2019-06-02") is costs.costs_on(date(2019, 6, 2))


def test_flat_names_hold_on_every_date() -> None:
    """1단계는 한 줄 표: 엔진 · 실행 흐름이 읽는 이름(`FEE` · `SELL_TAX` · `DIVIDEND_WITHHOLDING`)이 어느 날에나 맞아요.
    날짜별 줄을 더하면(R-B4 · Q-N26) 여기서 실패해요 · 그때는 부르는 쪽을 `costs_on(매도한 날)`로 바꿔요."""
    days = [date.min, date(2019, 6, 2), date(2019, 6, 3), date(2021, 1, 1), date(2024, 6, 3), date(2025, 6, 2),
            date(2026, 1, 2), date.max]
    assert all(costs.costs_on(d) == costs.FLAT for d in days)
    assert costs.FLAT == costs.TABLE[0]


def test_cost_numbers_are_defined_only_in_costs() -> None:
    assert python_cost_literals(ROOT) == {}


def test_web_src_has_no_cost_numbers() -> None:
    assert web_cost_literals(ROOT / "web" / "src") == {}


def test_guard_catches_planted_cost_literals(tmp_path: Path) -> None:
    pkg = tmp_path / "app" / "run"
    pkg.mkdir(parents=True)
    (pkg / "x.py").write_text(
        '"""수수료 0.015%는 독스트링이라 보지 않아요."""\n'
        "FEE_RATE = 1\n"
        "def f(q, p, dps):\n"
        "    chip = '매도 세금 0.18%'\n"
        "    return q * p * (1 + 0.00015) + dps * 0.846\n",
        encoding="utf-8")
    (tmp_path / "app" / "domain").mkdir()
    (tmp_path / "app" / "domain" / "costs.py").write_text("FEE = 0.00015\n", encoding="utf-8")
    got = python_cost_literals(tmp_path)
    assert list(got) == ["app/run/x.py"]
    assert got["app/run/x.py"] == sorted(["2: 이름 FEE_RATE", "4: 글 '0.18%'", "5: 숫자 0.00015", "5: 숫자 0.846"])
    web = tmp_path / "src"
    (web / "copy").mkdir(parents=True)
    (web / "copy" / "chips.ts").write_text("export const a = '원천징수 15.4%'\nexport const b = 0.0018\n", encoding="utf-8")
    (web / "api").mkdir()
    (web / "api" / "types.gen.ts").write_text("// 0.0018\n", encoding="utf-8")
    assert web_cost_literals(web) == {"copy/chips.ts": ["1: '15.4%'", "2: '0.0018'"]}
