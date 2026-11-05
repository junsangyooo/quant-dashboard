"""얼린 v3 사례(`frozen/v3_cases.json` · `frozen/bars.json`)를 v3 엔진만으로 다시 돌려요(P1-01a).

이 모듈은 `app.domain.engine`과 표준 라이브러리만 가져와요. P1-03이 지운 모듈(옛 v1 · MVP 엔진 · 회귀 도구)에 기대지 않아서
P1-03 뒤에도 그대로 돌아요. 시험은 `tests/test_baseline_frozen.py`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.domain.engine import run_backtest

FROZEN = Path(__file__).resolve().parent / "frozen"
CASES_FILE = FROZEN / "v3_cases.json"
BARS_FILE = FROZEN / "bars.json"
V1_FIXTURES_FILE = FROZEN / "v1_fixtures.json"

# 재생이 비교하는 결과 항목(거래는 사유 · 판단일 · 종류까지 · 건너뜀은 까닭까지 · 값 없음 기록 · 끝 자산 · 남은 보유)
COMPARED = ("trades", "skipped", "notes", "final", "open")


def load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))["cases"]


def load_bars() -> dict[str, dict[str, list[dict[str, Any]]]]:
    return json.loads(BARS_FILE.read_text(encoding="utf-8"))["sets"]


def load_v1_fixtures() -> dict[str, Any]:
    return json.loads(V1_FIXTURES_FILE.read_text(encoding="utf-8"))


def run_case(case: dict[str, Any], bars: dict[str, dict[str, list[dict[str, Any]]]]) -> dict[str, Any]:
    """얼린 v3 본문 · 일봉으로 v3 엔진을 돌린 결과 중 비교 항목만."""
    res = run_backtest(case["v3_body"], bars[case["bars"]], None, case["start"], case["end"], float(case["cash"]),
                       check=False)
    return {k: res[k] for k in COMPARED}


def diff_case(case: dict[str, Any], got: dict[str, Any]) -> list[str]:
    """얼린 값과 다른 곳을 글로. 비어 있으면 같아요."""
    out: list[str] = []
    for k in COMPARED:
        want = case[k]
        if got[k] == want:
            continue
        if isinstance(want, list) and isinstance(got[k], list):
            n = min(len(want), len(got[k]))
            first = next((i for i in range(n) if want[i] != got[k][i]), n)
            out.append(f"{k}: 수 {len(want)} → {len(got[k])} · 첫 차이 #{first}: {want[first:first + 1]} → "
                       f"{got[k][first:first + 1]}")
        else:
            out.append(f"{k}: {want!r} → {got[k]!r}")
    return out


def replay_all(cases: list[dict[str, Any]] | None = None) -> dict[str, list[str]]:
    """사례 id → 차이 목록(차이가 있는 사례만)."""
    bars = load_bars()
    bad: dict[str, list[str]] = {}
    for case in cases if cases is not None else load_cases():
        d = diff_case(case, run_case(case, bars))
        if d:
            bad[case["id"]] = d
    return bad
