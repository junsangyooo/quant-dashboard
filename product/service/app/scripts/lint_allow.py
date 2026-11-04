"""ruff · mypy를 돌리고 결과를 허용 목록(`tests/allow/ruff.txt` · `tests/allow/mypy.txt`)과 대조해요(P1-02 ③).

    cd product/service/app && .venv/bin/python scripts/lint_allow.py ruff
    cd product/service/app && .venv/bin/python scripts/lint_allow.py mypy

- 허용 목록 한 줄 = `파일 규칙 수  # 까닭`. (파일 × 규칙)마다 지금 위반 수가 목록의 수와 **정확히 같아야** 통과예요:
  늘면 실패(새 위반) · 줄면 실패(목록을 줄여 '줄어들기만' 하게 · P1-04와 같은 방식) · 목록에 없는 (파일 × 규칙)은 실패.
- 어느 폴더에서 불러도 같아요(이 파일 위치 기준 `product/service/app`에서 돌려요). 도구는 같은 venv(`sys.executable`)의 것.
- 종료 코드: 0 통과 · 1 어긋남 · 2 도구 실행 실패.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
ALLOW = APP / "tests" / "allow"
RUFF_TARGETS = ["app", "tests", "scripts"]
MYPY_TARGETS = ["app"]
LINE = re.compile(r"^(\S+)\s+(\S+)\s+(\d+)\s*(?:#.*)?$")


def load_allow(name: str) -> Counter[tuple[str, str]]:
    allowed: Counter[tuple[str, str]] = Counter()
    for raw in (ALLOW / name).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = LINE.match(line)
        if not m:
            raise SystemExit(f"허용 목록 줄을 읽을 수 없어요({name}): {raw}")
        allowed[(m.group(1), m.group(2))] += int(m.group(3))
    return allowed


def run_ruff() -> Counter[tuple[str, str]]:
    cmd = [sys.executable, "-m", "ruff", "check", *RUFF_TARGETS, "--output-format", "json", "--config", "ruff.toml"]
    p = subprocess.run(cmd, cwd=APP, capture_output=True, text=True)
    if p.returncode not in (0, 1) or not p.stdout.strip().startswith("["):
        raise SystemExit(f"ruff 실행 실패(exit {p.returncode}):\n{(p.stdout + p.stderr)[-2000:]}")
    found: Counter[tuple[str, str]] = Counter()
    for v in json.loads(p.stdout):
        rel = Path(v["filename"]).resolve().relative_to(APP).as_posix()
        found[(rel, str(v["code"]))] += 1
    return found


def run_mypy() -> Counter[tuple[str, str]]:
    cmd = [sys.executable, "-m", "mypy", *MYPY_TARGETS, "--config-file", "mypy.ini", "--no-error-summary",
           "--no-color-output"]
    p = subprocess.run(cmd, cwd=APP, capture_output=True, text=True)
    if p.returncode not in (0, 1):
        raise SystemExit(f"mypy 실행 실패(exit {p.returncode}):\n{(p.stdout + p.stderr)[-2000:]}")
    found: Counter[tuple[str, str]] = Counter()
    for line in p.stdout.splitlines():
        m = re.match(r"^([^:]+):\d+(?::\d+)?: error: .*\[([a-z-]+)\]$", line)
        if m:
            found[(m.group(1), m.group(2))] += 1
        elif ": error: " in line:
            found[(line.split(":", 1)[0], "unknown")] += 1
    return found


def compare(tool: str, found: Counter[tuple[str, str]], allowed: Counter[tuple[str, str]]) -> int:
    problems = []
    for key in sorted(set(found) | set(allowed)):
        f, a = found.get(key, 0), allowed.get(key, 0)
        if f > a:
            problems.append(f"늘었어요 {key[0]} {key[1]}: {a} → {f}" if a else f"새 위반 {key[0]} {key[1]}: {f}")
        elif f < a:
            problems.append(f"줄었어요 {key[0]} {key[1]}: {a} → {f} · 허용 목록(tests/allow/{tool}.txt)을 그만큼 줄여요")
    total_f, total_a = sum(found.values()), sum(allowed.values())
    print(f"{tool}: 위반 {total_f} · 허용 목록 {total_a}({len(allowed)}줄) · 어긋남 {len(problems)}")
    for line in problems:
        print("  " + line)
    return 1 if problems else 0


def main(argv: list[str]) -> int:
    if len(argv) != 1 or argv[0] not in ("ruff", "mypy"):
        print(__doc__)
        return 2
    tool = argv[0]
    found = run_ruff() if tool == "ruff" else run_mypy()
    return compare(tool, found, load_allow(f"{tool}.txt"))


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
