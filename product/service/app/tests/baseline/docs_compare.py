"""덤(Q-N18 준비): `f33e2a9` 바로 전 판 문서 표(`frozen/docs-before-f33e2a9/`)가 지금 `app/catalog.py` ·
`web/tests/forbiddenWords.json`과 같은지를 **지금 시험 함수의 비교 논리 그대로** 돌려 봐요(시험은 바꾸지 않아요).

    cd product/service/app && .venv/bin/python -m tests.baseline.docs_compare

`tests/test_catalog.py` · `tests/test_copytext.py`를 가져와 문서 표만 얼린 판으로 바꿔 끼우고 시험 함수를 불러요.
결과는 보고(`tests/baseline/reports/P1-01a.md`)에만 적고, 쓸지는 제품 주인의 답에 달렸어요.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests import test_catalog as tc
from tests import words_rules as wr

DOCS = Path(__file__).resolve().parent / "frozen" / "docs-before-f33e2a9"


def _run(name: str, fn, *args) -> str:  # type: ignore[no-untyped-def]
    try:
        fn(*args)
        return f"- {name}: 통과"
    except AssertionError as exc:
        return f"- {name}: 실패 · {str(exc).splitlines()[0][:160]}"


def main() -> None:
    lines = ["## 카탈로그(DATA-CATALOG 1절 · ENGINE-RULES 11-3 · f33e2a9^ 판) ↔ app/catalog.py"]
    tc.CATALOG_ROWS = tc._table(DOCS / "DATA-CATALOG-1.md", "## 1. 조건 카탈로그", "- **주식 수 맞춤")
    tc.DICT_ROWS = tc._table(DOCS / "ENGINE-RULES-11-3.md", "### 11-3.", "- 값 범위")
    lines.append(f"- 표 행 수: DATA-CATALOG {len(tc.CATALOG_ROWS)} · ENGINE-RULES {len(tc.DICT_ROWS)} · "
                 f"코드 {len(tc.cat.ITEMS)}")
    bad = [str(n) for n in range(53) if _run("", tc.test_catalog_row_text, n).endswith("통과") is False]
    lines.append(f"- test_catalog_row_text[0..52](얼린 DATA-CATALOG 1절): 실패 {len(bad)}건"
                 + (f" · 행 {', '.join(bad)}" if bad else ""))
    bad = [str(n) for n in range(53) if _run("", tc.test_dictionary_row, n).endswith("통과") is False]
    lines.append(f"- test_dictionary_row[0..52](얼린 ENGINE-RULES 11-3): 실패 {len(bad)}건"
                 + (f" · 행 {', '.join(bad)}" if bad else ""))
    lines.append(_run("test_catalog_blocks_match_dictionary_blocks(얼린 두 표)", tc.test_catalog_blocks_match_dictionary_blocks))
    lines.append("- (참고) 지금 문서로는 P1-00과 같이 row_text 14건 · dictionary_row 1건 · blocks 1건이 실패해요")

    lines.append("")
    lines.append("## 금지어(GLOSSARY 5절 · SPEC 8-1 · f33e2a9^ 판) ↔ web/tests/forbiddenWords.json")
    wr.GLOSSARY = DOCS / "GLOSSARY-5.md"
    wr.SPEC = DOCS / "SPEC-8-1.md"
    rules = wr.load_rules()
    on_disk = json.loads(wr.JSON_PATH.read_text(encoding="utf-8"))
    lines.append(f"- 얼린 문서로 만든 규칙 == forbiddenWords.json: {rules == on_disk} "
                 f"(낱말 {len(rules['words'])} ↔ {len(on_disk['words'])})")
    from tests import test_copytext as tcp

    lines.append(_run("test_forbidden_list_is_the_glossary(얼린 GLOSSARY 5절 · SPEC 8-1)",
                      tcp.test_forbidden_list_is_the_glossary))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
