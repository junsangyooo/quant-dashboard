"""웹 쪽 검사 기록(P1-01c): 금지어(빌드 결과 · 찍은 화면 글)와 `npm test · lint · typecheck · build`의 지금 결과.

- 금지어: `web/tests/words.test.ts`가 하는 검사를 **빌드 결과 `web/dist`**(`.js` · `.html` · `forbiddenHits`와 같은 규칙 ·
  `web/tests/forbiddenWords.json`을 그대로 읽음)와 **찍은 화면 글**(`screen_texts.json`의 `text`)에 대해 지금 상태로 돌려요.
  규칙 적용은 서버 쪽 시험이 쓰는 `tests/words_rules.hits`(같은 꼴 · 예외를 지운 뒤 남은 것)예요. 0건이어야 하고 아니면
  그대로 적어요(고치지 않음). `forbiddenWords.json`이 문서와 다른 문제(Q-N18)는 여기서 보지 않아요.
- npm: `npm run typecheck` · `npm run lint` · `npm test` · `npm run build`를 `web/`에서 차례로 돌려 종료 코드와 요약 수
  (typecheck: `error TS` 줄 수 · lint: eslint 문제 수 · prettier 경고 파일 수 · test: 파일 · 시험 통과/실패 수 · build: dist
  파일 이름)만 남겨요(시간은 본체 밖 timing에). 실패해도 고치지 않고 기록해요. `build`가 `web/dist`를 다시 만들어요.
"""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[2]
WEB = APP / "web"
RULES_JSON = WEB / "tests" / "forbiddenWords.json"


def rules() -> dict[str, Any]:
    return json.loads(RULES_JSON.read_text(encoding="utf-8"))


def forbidden_words(texts_json: Path | None) -> dict[str, Any]:
    from tests.words_rules import hits

    r = rules()
    dist_hits: list[str] = []
    dist = WEB / "dist"
    dist_files = sorted(p for p in dist.rglob("*") if p.suffix in (".js", ".html")) if dist.exists() else []
    for f in dist_files:
        name = f.relative_to(WEB).as_posix()
        dist_hits += [f"{name}: {h}" for h in hits(f.read_text(encoding="utf-8"), r)]
    screen_hits: list[str] = []
    screens = 0
    if texts_json is not None and texts_json.exists():
        texts = json.loads(texts_json.read_text(encoding="utf-8"))
        screens = len(texts)
        for key in sorted(texts):
            screen_hits += [f"{key}: {h}" for h in hits(texts[key]["text"], r)]
    return {"rules": {"words": len(r["words"]), "chips": r["chips"], "headerChips": r["headerChips"], "source": "web/tests/forbiddenWords.json"},
            "dist_files": [p.relative_to(WEB).as_posix() for p in dist_files], "dist_hits": dist_hits, "dist_count": len(dist_hits),
            "screens": screens, "screen_hits": screen_hits, "screen_count": len(screen_hits)}


def _run(cmd: list[str]) -> tuple[int, str, float]:
    t0 = time.perf_counter()
    p = subprocess.run(cmd, cwd=WEB, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr, round(time.perf_counter() - t0, 2)


def npm_checks() -> tuple[dict[str, Any], dict[str, float], dict[str, str]]:
    """(기록 본체, 시간, 전체 출력). 본체에는 시간 · 경로가 들어가지 않아요."""
    record: dict[str, Any] = {}
    timing: dict[str, float] = {}
    outputs: dict[str, str] = {}

    code, out, took = _run(["npm", "run", "typecheck"])
    record["typecheck"] = {"exit": code, "ts_errors": len(re.findall(r"error TS\d+", out))}
    timing["typecheck"], outputs["typecheck"] = took, out

    code, out, took = _run(["npm", "run", "lint"])
    m = re.search(r"✖ (\d+) problems? \((\d+) errors?, (\d+) warnings?\)", out)
    record["lint"] = {"exit": code, "eslint_problems": int(m.group(1)) if m else 0,
                      "eslint_errors": int(m.group(2)) if m else 0, "eslint_warnings": int(m.group(3)) if m else 0,
                      "prettier_warn_files": len(re.findall(r"^\[warn\] (?!Code style)", out, flags=re.M))}
    timing["lint"], outputs["lint"] = took, out

    code, out, took = _run(["npm", "test"])
    files = re.search(r"Test Files\s+(?:(\d+) failed \| )?(\d+) passed(?: \| (\d+) skipped)? \((\d+)\)", out)
    tests = re.search(r"Tests\s+(?:(\d+) failed \| )?(\d+) passed(?: \| (\d+) skipped)? \((\d+)\)", out)
    record["test"] = {"exit": code,
                      "files_failed": int(files.group(1) or 0) if files else None, "files_passed": int(files.group(2)) if files else None,
                      "files_total": int(files.group(4)) if files else None,
                      "tests_failed": int(tests.group(1) or 0) if tests else None, "tests_passed": int(tests.group(2)) if tests else None,
                      "tests_total": int(tests.group(4)) if tests else None,
                      "failed_list": sorted(set(re.findall(r"^\s*(?:FAIL|×|✗)\s+(\S+\.test\.tsx?)(?:\s*>\s*(.+?))?\s*$", out, flags=re.M)))}
    timing["test"], outputs["test"] = took, out

    code, out, took = _run(["npm", "run", "build"])
    dist = WEB / "dist"
    assets = sorted(p.relative_to(dist).as_posix() for p in dist.rglob("*") if p.is_file() and p.suffix in (".js", ".css", ".html"))
    record["build"] = {"exit": code, "dist_files": assets}
    timing["build"], outputs["build"] = took, out
    return record, timing, outputs


if __name__ == "__main__":
    import sys

    if "--npm" in sys.argv:
        rec, tm, _ = npm_checks()
        print(json.dumps(rec, ensure_ascii=False, indent=1))
        print(json.dumps(tm))
    else:
        default = Path(__file__).resolve().parent / "web" / "screens" / "screen_texts.json"
        fw = forbidden_words(default)
        print(json.dumps({k: v for k, v in fw.items() if k != "dist_files"}, ensure_ascii=False, indent=1))
