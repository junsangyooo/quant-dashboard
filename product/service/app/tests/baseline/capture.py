"""P1-01b 서버 관측 기준선 만들기(명령 하나 · 두 번 돌려 본체가 바이트 단위로 같아요).

    cd product/service/app && .venv/bin/python -m tests.baseline.capture [--out DIR] [--skip-pytest]

`tests/baseline/server/`에 적는 것(본체 · 대조 대상):
- `clock.json` · `mask.json`: 고정 시각 · 씨앗 · 패치 자리 · 가릴 필드.
- `api_shapes.json`: pytest 전체(`-p tests.baseline.plugin`)에서 오간 응답의 라우트 × 상태 코드 → 키 · 타입 구조 ·
  라우트마다 남는/지울 · 관측 없음 표시.
- `engine_cases.json`: 엔진 거래 사례(백테스트 · 규칙 층 · 모의투자 흐름 · 실전 아침 흐름).
- `dayflow.json`: 하루 흐름 5가지 날.
- `counts.json`: 숫자(ARCHITECTURE 7절 셈 규칙).
- `pytest.json`: pytest 통과 · 실패 수와 실패 목록(시간은 뺌).
- `versions.txt`: `pip freeze --all` · `node -v` · `npm ls --depth=0`(경로는 지움).
본체 밖(두 번 같을 수 없음 · 대조에서 뺌): `timing.json`(pytest · 백테스트 사례(326 재생 포함) · 화면 API p50 · p95).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[2]
DEFAULT_OUT = Path(__file__).resolve().parent / "server"
BODY_FILES = ("clock.json", "mask.json", "api_shapes.json", "engine_cases.json", "dayflow.json", "counts.json",
              "pytest.json", "versions.txt")
TIMING_FILE = "timing.json"


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def run_pytest(api_out: Path, quiet: bool = False) -> dict[str, Any]:
    """pytest 전체를 플러그인과 함께 새 프로세스로 돌려요(결과 요약 · 실패 목록 · 걸린 시간)."""
    env = dict(os.environ, QUANT_BASELINE_API_OUT=str(api_out))
    t0 = time.perf_counter()
    proc = subprocess.run([sys.executable, "-m", "pytest", "-p", "tests.baseline.plugin"], cwd=APP, env=env,
                          capture_output=True, text=True)
    took = time.perf_counter() - t0
    text = proc.stdout + proc.stderr
    m = re.search(r"(?:(\d+) failed, )?(\d+) passed(?:, (\d+) skipped)?.*? in ([\d.]+)s", text)
    failed = sorted(re.findall(r"^FAILED (\S+)", text, flags=re.M))
    summary = {"passed": int(m.group(2)) if m else None, "failed": int(m.group(1) or 0) if m else None,
               "skipped": int(m.group(3) or 0) if m else None, "failed_list": failed, "exit_code": proc.returncode}
    if not quiet:
        print(f"pytest: {summary['passed']} passed · {summary['failed']} failed · {took:.1f}s (exit {proc.returncode})")
    return {"summary": summary, "seconds": round(took, 2), "reported_seconds": float(m.group(4)) if m else None,
            "output": text}


def api_record(raw: dict[str, Any]) -> dict[str, Any]:
    from tests.baseline.scope import DELETED_ROUTES

    observed: dict[str, list[int]] = {}
    for key in raw["observations"]:
        route, status = key.rsplit(" ", 1)
        observed.setdefault(route, []).append(int(status))
    routes = []
    for route in raw["routes"]:
        routes.append({"route": route, "kept": route not in DELETED_ROUTES, "observed": sorted(observed.get(route, [])),
                       "unobserved": route not in observed})
    obs = {}
    for key, rec in raw["observations"].items():
        route = key.rsplit(" ", 1)[0]
        obs[key] = {"kept_route": route not in DELETED_ROUTES, **rec}
    n_kept = sum(1 for r in routes if r["kept"])
    return {
        "summary": {
            "routes": len(routes), "routes_kept": n_kept, "routes_deleted": len(routes) - n_kept,
            "routes_unobserved": sum(1 for r in routes if r["unobserved"]),
            "routes_unobserved_kept": sum(1 for r in routes if r["unobserved"] and r["kept"]),
            "observations": len(obs),
            "observations_kept_route_with_kept_tests": sum(1 for v in obs.values() if v["kept_route"] and v["shape"]),
            "observations_only_by_deleted_tests": sum(1 for v in obs.values() if not v["shape"]),
        },
        "routes": routes, "observations": obs,
    }


def versions_text() -> str:
    def sh(cmd: list[str], cwd: Path | None = None) -> str:
        try:
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
            return (p.stdout or p.stderr).strip()
        except OSError as exc:
            return f"(not available: {type(exc).__name__})"

    pip = sh([sys.executable, "-m", "pip", "freeze", "--all"])
    node = sh(["node", "-v"])
    npm = sh(["npm", "ls", "--depth=0"], cwd=APP / "web")
    npm_lines = []
    for line in npm.splitlines():
        if " /" in line and not line.startswith(("├", "└", "│")):  # "web@0.0.0 /abs/path" → 경로 지움
            line = line.split(" /", 1)[0]
        npm_lines.append(line.rstrip())
    return "\n".join(["# pip freeze --all", pip, "", "# node -v", node, "", "# npm ls --depth=0 (web)", *npm_lines, ""])


def run(out: Path, *, skip_pytest: bool = False, quiet: bool = False) -> dict[str, Any]:
    from tests.baseline import clock, counts, dayflow, engine_cases, mask, replay, screen_api

    clock.freeze_plain()
    out.mkdir(parents=True, exist_ok=True)
    timing: dict[str, Any] = {"captured_on": date.today().isoformat(), "note": "두 번 같을 수 없음 · 본체 대조에서 뺌 · "
                                                                           "규칙: 20% 넘게 느려지지 않음(QUALITY T7)"}
    _dump(out / "clock.json", clock.as_record())
    _dump(out / "mask.json", mask.as_record())

    if not skip_pytest:
        with tempfile.TemporaryDirectory(prefix="quant-baseline-api-") as d:
            api_raw_path = Path(d) / "api_raw.json"
            pt = run_pytest(api_raw_path, quiet=quiet)
            raw = json.loads(api_raw_path.read_text(encoding="utf-8"))
        _dump(out / "api_shapes.json", api_record(raw))
        _dump(out / "pytest.json", pt["summary"])
        timing["pytest_seconds"] = pt["seconds"]
        timing["pytest_reported_seconds"] = pt["reported_seconds"]
        (out / "pytest_output.txt").write_text(pt["output"], encoding="utf-8") if os.environ.get(
            "QUANT_BASELINE_KEEP_PYTEST_OUTPUT") else None

    t0 = time.perf_counter()
    eng = engine_cases.run_all()
    timing["engine_cases_seconds"] = round(time.perf_counter() - t0, 2)
    _dump(out / "engine_cases.json", eng)
    if not quiet:
        print(f"engine cases: {eng['count']} ({timing['engine_cases_seconds']}s)")

    t0 = time.perf_counter()
    frozen_cases = replay.load_cases()
    diffs = replay.replay_all(frozen_cases)  # 차이 난 사례만 돌아와요
    timing["replay_326_seconds"] = round(time.perf_counter() - t0, 2)
    timing["replay_326_cases"] = len(frozen_cases)
    timing["replay_326_diff_cases"] = len(diffs)
    if not quiet:
        print(f"replay 326: {len(frozen_cases)} cases · diff {len(diffs)} ({timing['replay_326_seconds']}s)")

    t0 = time.perf_counter()
    days = dayflow.run_all()
    timing["dayflow_seconds"] = round(time.perf_counter() - t0, 2)
    _dump(out / "dayflow.json", days)
    if not quiet:
        print("dayflow:", {k: v["summary"]["events"] for k, v in days.items()}, f"({timing['dayflow_seconds']}s)")

    cnt = counts.run_all()
    _dump(out / "counts.json", cnt)
    if not quiet:
        print("counts:", cnt["summary"])

    with tempfile.TemporaryDirectory(prefix="quant-baseline-screen-") as d:
        sc = screen_api.run_all(Path(d))
    timing["screen_api"] = sc["timing"]
    timing["screen_api_setup"] = sc["setup"]
    timing["screen_api_summary"] = sc["screen_summary"]
    if not quiet:
        print("screen api p95 ms:", {k: v["p95_ms"] for k, v in sc["timing"].items()})

    (out / "versions.txt").write_text(versions_text(), encoding="utf-8")
    _dump(out / TIMING_FILE, timing)
    return {"out": str(out), "timing": timing}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--skip-pytest", action="store_true", help="API 모양 · pytest 수를 다시 만들지 않음(빠른 확인용)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    run(Path(a.out), skip_pytest=a.skip_pytest, quiet=a.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
