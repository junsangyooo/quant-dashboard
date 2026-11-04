"""기준선 대조(P1-14 · 뒤 일감의 검토자용): 지금 트리에서 관측을 다시 만들어 저장된 기준선의 **'남는 것'**과 비교해요.

    cd product/service/app && .venv/bin/python -m tests.baseline.compare [--baseline DIR] [--web-baseline DIR] [--skip-pytest]
                                                                       [--skip-web] [--timing]

판정(종료 코드 0 = '남는 것' 차이 0):
- 시계 · 가릴 필드: `clock.json` · `mask.json`이 같아야 해요(다르면 다른 기록도 뜻이 달라져요).
- API 모양: 남는 라우트가 모두 있고, 남는 시험이 관측한 (라우트 × 상태)의 모양이 같아야 해요. 남는 라우트의 새 관측
  (기준선에 없던 상태 코드)은 알림으로만 적어요. 지울 라우트 · 지울 시험만 관측한 것은 보지 않아요.
- 엔진 거래: 사례마다 거래 · 건너뜀 · 경고 글 · 상태가 같아야 해요(사례 전부가 '남는 것').
- 하루 흐름: 6가지 날의 사건 목록이 같아야 해요.
- 숫자 · pytest 수: 전후 표로만 보여요(줄어드는 것이 목표라 차이가 실패가 아니에요).
- 시간: `--timing`을 주면 20% 넘게 느려진 항목이 있을 때 실패(기본은 표만).
- 화면(P1-01c · `--skip-web`이 아니면): 기준선 화면마다 PNG 픽셀 차 %(sha256이 같으면 0% · 아니면 브라우저 canvas로 셈)가
  **0.5% 이하**이고 화면 글 · 역할 트리가 같아야 해요. 기준선에서 건너뛴 화면이 새로 찍히면 알림.
- 웹 숫자 · 금지어 · npm 검사: 표로만 보여요. 다만 금지어가 0에서 늘거나 npm 검사가 통과에서 실패로 바뀌면 차이예요.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from tests.baseline.capture import DEFAULT_OUT, DEFAULT_WEB_OUT, TIMING_FILE, run as capture_run


def _load(d: Path, name: str) -> Any:
    p = d / name
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8")) if name.endswith(".json") else p.read_text(encoding="utf-8")


def _paths(a: Any, b: Any, prefix: str = "", out: list[str] | None = None, limit: int = 20) -> list[str]:
    """두 JSON의 다른 자리(앞 limit개)."""
    out = [] if out is None else out
    if len(out) >= limit:
        return out
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                out.append(f"{prefix}/{k}: 새로 생김")
            elif k not in b:
                out.append(f"{prefix}/{k}: 사라짐")
            else:
                _paths(a[k], b[k], f"{prefix}/{k}", out, limit)
            if len(out) >= limit:
                break
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(f"{prefix}: 길이 {len(a)} → {len(b)}")
        for i, (x, y) in enumerate(zip(a, b, strict=False)):
            _paths(x, y, f"{prefix}[{i}]", out, limit)
            if len(out) >= limit:
                break
    elif a != b:
        out.append(f"{prefix}: {json.dumps(a, ensure_ascii=False)[:80]} → {json.dumps(b, ensure_ascii=False)[:80]}")
    return out


def compare_api(base: dict[str, Any], new: dict[str, Any]) -> tuple[list[str], list[str]]:
    problems, notes = [], []
    new_routes = {r["route"] for r in new["routes"]}
    for r in base["routes"]:
        if r["kept"] and r["route"] not in new_routes:
            problems.append(f"남는 라우트가 사라짐: {r['route']}")
    base_kept = {r["route"] for r in base["routes"] if r["kept"]}
    for route in sorted(new_routes - {r["route"] for r in base["routes"]}):
        notes.append(f"새 라우트(기준선에 없음): {route}")
    for key, rec in base["observations"].items():
        if not rec["kept_route"] or rec["shape"] is None:
            continue
        got = new["observations"].get(key)
        if got is None:
            problems.append(f"관측이 사라짐(남는 시험이 보던 것): {key}")
            continue
        if got["shape"] != rec["shape"]:
            diff = _paths(rec["shape"], got["shape"], "", limit=5)
            problems.append(f"모양 다름: {key} · " + " · ".join(diff))
    for key, rec in new["observations"].items():
        route = key.rsplit(" ", 1)[0]
        if route in base_kept and key not in base["observations"] and rec["shape"] is not None:
            notes.append(f"새 관측(남는 라우트 · 기준선에 없던 상태): {key}")
    return problems, notes


def compare_cases(base: dict[str, Any], new: dict[str, Any]) -> list[str]:
    problems = []
    b = {c["id"]: c for c in base["cases"]}
    n = {c["id"]: c for c in new["cases"]}
    for id_, c in b.items():
        if id_ not in n:
            problems.append(f"엔진 사례 사라짐: {id_}")
            continue
        if n[id_] != c:
            problems.append(f"엔진 사례 다름: {id_} · " + " · ".join(_paths(c, n[id_], "", limit=5)))
    for id_ in n:
        if id_ not in b:
            problems.append(f"엔진 사례 새로 생김(기준선에 없음): {id_}")
    return problems


def compare_dayflow(base: dict[str, Any], new: dict[str, Any]) -> list[str]:
    problems = []
    for name, day in base.items():
        if name not in new:
            problems.append(f"하루 흐름 날 사라짐: {name}")
            continue
        if new[name] != day:
            problems.append(f"하루 흐름 다름: {name} · " + " · ".join(_paths(day, new[name], "", limit=6)))
    return problems


def table(base: dict[str, Any], new: dict[str, Any], title: str) -> list[str]:
    lines = [f"[{title}]"]
    for k in sorted(set(base) | set(new)):
        a, b = base.get(k), new.get(k)
        mark = "" if a == b else "  ←"
        lines.append(f"  {k}: {a} → {b}{mark}")
    return lines


def timing_table(base: dict[str, Any], new: dict[str, Any]) -> tuple[list[str], list[str]]:
    lines, slow = ["[시간 · 기준 → 지금 · 20% 규칙]"], []

    def row(name: str, a: Any, b: Any) -> None:
        if not isinstance(a, int | float) or not isinstance(b, int | float) or a <= 0:
            lines.append(f"  {name}: {a} → {b}")
            return
        pct = (b / a - 1) * 100
        flag = " ← 20% 넘게 느림" if pct > 20 else ""
        lines.append(f"  {name}: {a} → {b} ({pct:+.0f}%){flag}")
        if pct > 20:
            slow.append(name)

    for k in ("pytest_seconds", "engine_cases_seconds", "replay_326_seconds", "dayflow_seconds", "screens_seconds",
              "webcounts_seconds"):
        row(k, base.get(k), new.get(k))
    for k, v in (base.get("npm_seconds") or {}).items():
        row(f"npm {k}", v, (new.get("npm_seconds") or {}).get(k))
    for route, v in (base.get("screen_api") or {}).items():
        nv = (new.get("screen_api") or {}).get(route, {})
        row(f"screen {route} p95_ms", v.get("p95_ms"), nv.get("p95_ms"))
    return lines, slow


def compare_web(base: Path, new: Path) -> tuple[list[str], list[str], list[str]]:
    """화면 · 웹 숫자 · 금지어 · npm 검사(P1-01c) → (차이, 알림, 찍을 줄)."""
    from tests.baseline import screens

    problems, notes, lines = [], [], []
    p, n, rows = screens.compare(base / "screens", new / "screens")
    problems += p
    notes += n
    worst = max((r["pixel_pct"] for r in rows), default=0.0)
    lines.append(f"[화면 · 기준선 {len(rows)}장 · 픽셀 차 최대 {worst}% · 문턱 {screens.PIXEL_THRESHOLD_PCT}% · "
                 f"다른 그림 {sum(1 for r in rows if r['pixel_pct'] > 0)}장 · 글 다름 {sum(1 for r in rows if not r['text_same'])}장]")
    for r in rows:
        if r["pixel_pct"] > 0 or not r["text_same"] or not r["aria_same"]:
            lines.append(f"  {r['screen']}: 픽셀 차 {r['pixel_pct']}% ({r['size']}) · 글 같음 {r['text_same']} · 역할 트리 같음 {r['aria_same']}")
    b_wc, n_wc = _load(base, "web_counts.json"), _load(new, "web_counts.json")
    if b_wc and n_wc:
        lines += table(b_wc["summary"], n_wc["summary"], "웹 숫자")
    b_fw, n_fw = _load(base, "forbidden_words.json") or {}, _load(new, "forbidden_words.json") or {}
    lines += table({k: b_fw.get(k) for k in ("dist_count", "screen_count")},
                   {k: n_fw.get(k) for k in ("dist_count", "screen_count")}, "금지어(빌드 결과 · 화면 글)")
    for k in ("dist_count", "screen_count"):
        if (n_fw.get(k) or 0) > (b_fw.get(k) or 0):
            problems.append(f"금지어가 늘어남({k}): {b_fw.get(k)} → {n_fw.get(k)} · " + " · ".join(n_fw.get(k.replace('count', 'hits'), [])[:3]))
    b_npm, n_npm = _load(base, "npm_checks.json") or {}, _load(new, "npm_checks.json") or {}
    lines += table({k: v.get("exit") for k, v in b_npm.items()}, {k: v.get("exit") for k, v in n_npm.items()}, "npm 검사 종료 코드")
    for k, v in n_npm.items():
        if v.get("exit") != 0 and (b_npm.get(k) or {}).get("exit") == 0:
            problems.append(f"npm {k}가 통과에서 실패로 바뀜(exit {v.get('exit')})")
    return problems, notes, lines


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--baseline", default=str(DEFAULT_OUT))
    ap.add_argument("--web-baseline", default=str(DEFAULT_WEB_OUT))
    ap.add_argument("--skip-pytest", action="store_true", help="API 모양 · pytest 수는 대조하지 않음(빠른 확인용)")
    ap.add_argument("--skip-web", action="store_true", help="화면 · 웹 숫자(P1-01c)는 대조하지 않음(빠른 확인용)")
    ap.add_argument("--timing", action="store_true", help="20% 넘게 느려진 항목이 있으면 실패")
    ap.add_argument("--keep", default=None, help="다시 만든 관측을 이 폴더에 남김(server · web 하위 폴더 · 기본은 임시 폴더)")
    a = ap.parse_args(argv)
    base = Path(a.baseline)
    problems: list[str] = []
    notes: list[str] = []
    with tempfile.TemporaryDirectory(prefix="quant-baseline-compare-") as d:
        root = Path(a.keep) if a.keep else Path(d)
        out, web_out = root / "server", root / "web"
        capture_run(out, skip_pytest=a.skip_pytest, quiet=True, skip_web=a.skip_web, web_out=web_out)
        for name in ("clock.json", "mask.json"):
            if _load(base, name) != _load(out, name):
                problems.append(f"{name} 다름: " + " · ".join(_paths(_load(base, name), _load(out, name), "", limit=5)))
        if not a.skip_pytest:
            b_api, n_api = _load(base, "api_shapes.json"), _load(out, "api_shapes.json")
            if b_api is None:
                problems.append("기준선에 api_shapes.json이 없음")
            else:
                p, n = compare_api(b_api, n_api)
                problems += p
                notes += n
                print(*table(b_api["summary"], n_api["summary"], "API 모양 요약"), sep="\n")
                print(*table(_load(base, "pytest.json") or {}, _load(out, "pytest.json") or {}, "pytest"), sep="\n")
        problems += compare_cases(_load(base, "engine_cases.json"), _load(out, "engine_cases.json"))
        problems += compare_dayflow(_load(base, "dayflow.json"), _load(out, "dayflow.json"))
        print(*table(_load(base, "counts.json")["summary"], _load(out, "counts.json")["summary"], "숫자"), sep="\n")
        if (_load(base, "versions.txt") or "") != (_load(out, "versions.txt") or ""):
            notes.append("versions.txt 다름(설치된 판이 바뀜)")
        if not a.skip_web:
            p, n, w_lines = compare_web(Path(a.web_baseline), web_out)
            problems += p
            notes += n
            print(*w_lines, sep="\n")
        t_lines, slow = timing_table(_load(base, TIMING_FILE) or {}, _load(out, TIMING_FILE) or {})
        print(*t_lines, sep="\n")
        if a.timing and slow:
            problems.append("20% 넘게 느려짐: " + ", ".join(slow))
    for n in notes:
        print("알림:", n)
    for p in problems:
        print("차이:", p)
    print(f"'남는 것' 차이 {len(problems)}건 · 알림 {len(notes)}건")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
