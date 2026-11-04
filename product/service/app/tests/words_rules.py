"""금지어 규칙(GLOSSARY 5절 + SPEC 8-1 왼쪽 열)을 문서에서 읽어요(TASKS T-01 · T-71).

- 목록의 정답은 문서예요. 이 파일은 문서 표를 읽어 규칙으로 바꾸기만 해요.
- 화면 시험(web/tests/words.test.ts)은 같은 규칙을 `web/tests/forbiddenWords.json`으로 읽어요.
  그 파일이 문서와 같은지는 `tests/test_words.py`(P1-03 전에는 `tests/test_copytext.py`)가 봐요. 다시 만들기:
  `.venv/bin/python -m tests.words_rules --write`
- 검사 꼴: 예외 꼴을 지운 뒤 남은 것만 세요(GLOSSARY 5절 '검사 꼴').
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parent.parent
SERVICE = APP.parent
GLOSSARY = SERVICE / "GLOSSARY.md"
SPEC = SERVICE / "SPEC.md"
JSON_PATH = APP / "web" / "tests" / "forbiddenWords.json"

QUOTED = re.compile(r"'([^']+)'")
_DAY = "[월화수목금토일]"


def _section(text: str, start: str, stop: str) -> list[str]:
    lines = text.splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith(start))
    out = []
    for line in lines[i + 1 :]:
        if line.startswith(stop):
            break
        out.append(line)
    return out


def _rows(lines: list[str]) -> list[list[str]]:
    rows = []
    for line in lines:
        if not line.startswith("|") or line.startswith("|---"):
            continue
        rows.append([c.strip() for c in line.strip().strip("|").split("|")])
    return rows[1:]  # 머리 행 빼기


def phrase_pattern(phrase: str) -> str:
    """문서의 예시 문구를 찾는 정규식. 예시 날짜 · 요일 · 버전 자리는 아무 값이나 맞게 해요."""
    out = re.escape(phrase)
    out = re.sub(r"\d{1,2}/\d{1,2}", r"\\d{1,2}/\\d{1,2}", out.replace("\\/", "/"))
    out = re.sub(r"\\\(" + _DAY + r"\\\)", r"\\(" + _DAY + r"\\)", out)
    out = out.replace("MVP\\-xx", r"MVP\-\d+").replace("CV\\-x", r"CV\-\d+")
    return out


def _spec_8_1_phrases() -> list[tuple[str, list[str]]]:
    """(없앨 문구, 예외) 목록. '대신' 열의 새 문구가 없앨 문구를 품고 있으면 그 새 문구는 예외예요
    (예: '모의투자 기록이 있는 …' → '실전 운용이나 모의투자 기록이 있는 …')."""
    rows = _rows(_section(SPEC.read_text(encoding="utf-8"), "### 8-1.", "### 8-2."))
    out: list[tuple[str, list[str]]] = []
    for row in rows:
        instead = QUOTED.findall(row[2])
        for quoted in QUOTED.findall(row[0]):
            for part in quoted.split("…"):
                part = part.strip().strip("·").strip()
                if part:
                    out.append((part, [new for new in instead if part in new]))
    return out


def load_rules() -> dict[str, Any]:
    """{"words": [{"word", "pattern", "except", "source"}], "chips": [...], "headerChips": [...]}."""
    rows = _rows(_section(GLOSSARY.read_text(encoding="utf-8"), "## 5.", "검사 꼴"))
    words: list[dict[str, Any]] = []
    chips: list[str] = []
    header_chips: list[str] = []

    def add(word: str, exceptions: list[str], source: str, pattern: str | None = None) -> None:
        if any(w["word"] == word for w in words):
            return
        words.append(
            {"word": word, "pattern": pattern or re.escape(word), "except": exceptions, "source": source}
        )

    for left, right in rows:
        exceptions = QUOTED.findall(right) if right != "—" else []
        if left.startswith("SPEC 8-1"):
            for phrase, allowed in _spec_8_1_phrases():
                if phrase in ("예시", "모의투자"):  # 칩 규칙으로 봐요(아래)
                    continue
                add(phrase, allowed, "SPEC 8-1", phrase_pattern(phrase))
            continue
        if left.startswith("칩 글자가 정확히"):
            quoted = QUOTED.findall(left)
            chips.append(quoted[0])
            header_chips.append(quoted[1])
            continue
        if left.startswith("내부 낱말:"):
            left = left.removeprefix("내부 낱말:").strip()
            exceptions = []  # '코드 · 로그 안은 괜찮아요'는 검사 범위(화면 글만) 얘기예요
        left = left.removesuffix("(lab)").strip()
        parts = QUOTED.findall(left) if left.startswith("'") else [p.strip() for p in left.split(" · ")]
        for part in parts:
            add(part, exceptions, "GLOSSARY 5")
    return {"words": words, "chips": chips, "headerChips": header_chips}


def hits(text: str, rules: dict[str, Any] | None = None) -> list[str]:
    """금지어마다 예외 꼴을 지운 뒤 남은 것을 '낱말: …앞뒤…'로 돌려줘요."""
    rules = rules or load_rules()
    out = []
    for rule in rules["words"]:
        cleaned = text
        for ok in rule["except"]:
            cleaned = cleaned.replace(ok, "\x00" * len(ok))
        for m in re.finditer(rule["pattern"], cleaned):
            ctx = cleaned[max(0, m.start() - 10) : m.end() + 10].replace("\x00", "·").replace("\n", " ")
            out.append(f"{rule['word']}: …{ctx}…")
    return out


def write_json() -> None:
    JSON_PATH.write_text(json.dumps(load_rules(), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if "--write" in sys.argv:
        write_json()
    print(json.dumps(load_rules(), ensure_ascii=False, indent=1))


# ── 서버 글 뽑기 ────────────────────────────────────────────────────────────

HANGUL = re.compile(r"[가-힣]")


def server_strings(path: Path) -> list[tuple[int, str]]:
    """파이썬 파일에서 한글이 든 문자열(문서 글 · 주석 빼고)을 (줄, 글)로 뽑아요."""
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docstrings.add(id(body[0].value))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            if HANGUL.search(node.value):
                out.append((node.lineno, node.value))
    return sorted(out)
