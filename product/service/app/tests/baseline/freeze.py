"""P1-01a 기준선: `tests/baseline/frozen/`의 얼린 파일(어떻게 만들었는지 · 무엇이 들었는지).

    cd product/service/app && .venv/bin/python -m tests.baseline.freeze      # 지금은 문서 표(아래 4)만 다시 떼어 둬요

얼린 파일 1 ~ 3은 **`f232bdf`(P1-01a · 앱 코드는 `origin/quant-service` 125685d 그대로)에서 만든 것이 기준**이에요. 그때 이 스크립트가
지울 코드(옛 v1 전략 · v1 엔진 · 일곱 칸 MVP 모듈 · 회귀 도구 `tests/regression/`)를 가져와 입력과 정답을 만들었고, P1-03이 그 코드를
지우면서 만드는 부분도 함께 뗐어요(이 파일에는 문서 표를 떼는 부분만 남음 · 두 번 돌려도 바이트가 같았던 기록은 P1-01a 보고 6절).
그 뒤로는 얼린 파일이 기준이고, 재생은 `tests/baseline/replay.py`(v3 엔진만)가 해요. 다시 만들 일은 없어요(만들려면 `f232bdf`를 받아요).

1. `frozen/bars.json`: 일봉 묶음 4개(회귀 씨앗 11 · 23 · 47 · 옛 예시용 대형주 10종목). 씨앗이 아니라 일봉 자체예요.
2. `frozen/v3_cases.json`: v1 → v3 문턱의 사례 326개. 사례마다 v1 본문 · v3 본문(`app.copytext.convert_v1` · v3 안의 변환) ·
   쓰는 일봉 묶음 이름 · 기간 · 현금 · v3 엔진(`app.engine.run_backtest`)의 거래(사유 · 판단일 · 종류) · 건너뜀(까닭) · 값 없음 기록 ·
   끝 자산 · 남은 보유, 그리고 v1 엔진 거래와 문턱 판정.
3. `frozen/v1_fixtures.json`: 지운 코드가 만들던 시험 입력 · 정답(회귀 본문 84개와 `normalize` · `mode_of` · v3 변환, 옛 예시 4개와
   v2 복사 글, 옛 빈 본문(`legacy`) 16개, `run_v1` 거래 한 건). 남는 시험(`test_copytext_v3.py` · `test_engine_v2.py` ·
   `test_api_v2.py` · `tests/helpers.py` · `test_baseline_frozen.py`)이 이 값을 읽어요.
4. `frozen/docs-before-f33e2a9/`: `f33e2a9` 바로 전 판 문서의 표(DATA-CATALOG 1절 · GLOSSARY 5절, 그리고 그 비교 논리가 함께 읽는
   SPEC 8-1 · ENGINE-RULES 11-3 · Q-N18). 이 부분은 지금도 다시 만들 수 있어요(`git show`로 같은 판을 읽음).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

FROZEN = Path(__file__).resolve().parent / "frozen"
DOCS = FROZEN / "docs-before-f33e2a9"
DOC_COMMIT = "f33e2a9^"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ── f33e2a9 바로 전 문서 표 ───────────────────────────────────────────────

DOC_PARTS = [
    # (파일, 시작 줄 머리, 끝 줄 머리(여기 전까지), 얼릴 파일 이름)
    ("DATA-CATALOG.md", "## 1. 조건 카탈로그", "## 2.", "DATA-CATALOG-1.md"),
    ("GLOSSARY.md", "## 5.", None, "GLOSSARY-5.md"),
    ("SPEC.md", "### 8-1.", "### 8-2.", "SPEC-8-1.md"),
    ("ENGINE-RULES.md", "### 11-3.", "### 11-4.", "ENGINE-RULES-11-3.md"),
]


def _section(text: str, start: str, stop: str | None) -> str:
    lines = text.splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith(start))
    out = []
    for line in lines[i:]:
        if stop is not None and line.startswith(stop) and out:
            break
        out.append(line)
    return "\n".join(out).rstrip("\n") + "\n"


def write_docs() -> None:
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True,
                          cwd=Path(__file__).resolve().parent).stdout.strip()
    for name, start, stop, out in DOC_PARTS:
        text = subprocess.run(["git", "-C", root, "show", f"{DOC_COMMIT}:product/service/{name}"],
                              capture_output=True, text=True, check=True).stdout
        head = f"<!-- product/service/{name} · {DOC_COMMIT} 판 · 이 부분만 · P1-01a가 떼어 둠(Q-N18) -->\n\n"
        _write(DOCS / out, head + _section(text, start, stop))


def main() -> None:
    write_docs()
    for p in sorted(FROZEN.rglob("*")):
        if p.is_file():
            print(f"{p.stat().st_size:>10}  {p.relative_to(FROZEN.parent.parent.parent)}")


if __name__ == "__main__":
    main()
