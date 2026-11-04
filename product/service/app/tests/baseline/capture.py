"""P1-01 기준선 만들기(명령 하나 · 두 번 돌려 본체가 바이트 단위로 같아요 · 서버 P1-01b + 화면 · 웹 숫자 P1-01c).

    cd product/service/app && .venv/bin/python -m tests.baseline.capture [--out DIR] [--web-out DIR] [--skip-pytest] [--skip-web]

`--out DIR`만 주면 웹 기록도 저장소 밖으로 가요(`DIR`이 `server`로 끝나면 그 옆 `web` · 아니면 `DIR/web`).

`tests/baseline/server/`에 적는 것(본체 · 대조 대상):
- `clock.json` · `mask.json`: 고정 시각 · 씨앗 · 패치 자리 · 가릴 필드.
- `api_shapes.json`: pytest 전체(`-p tests.baseline.plugin`)에서 오간 응답의 라우트 × 상태 코드 → 키 · 타입 구조 ·
  라우트마다 남는/지울 · 관측 없음 표시.
- `engine_cases.json`: 엔진 거래 사례(백테스트 · 규칙 층 · 모의투자 흐름 · 실전 아침 흐름).
- `dayflow.json`: 하루 흐름 6가지 날.
- `counts.json`: 숫자(ARCHITECTURE 7절 셈 규칙).
- `pytest.json`: pytest 통과 · 실패 수와 실패 목록(시간은 뺌).
- `versions.txt`: `pip freeze --all` · `node -v` · `npm ls --depth=0 --unicode`(경로는 지움). Node 24가 아니면 까닭을 적고 실패해요.
본체 밖(두 번 같을 수 없음 · 대조에서 뺌): `timing.json`(pytest · 백테스트 사례(326 재생 포함) · 화면 API p50 · p95 · 화면 찍기 ·
npm 검사 · 웹 숫자).

`tests/baseline/web/`에 적는 것(P1-01c · 본체 · Node 24 + Playwright + `PW_CHROMIUM` 브라우저가 필요 · 없으면 까닭을 적고 실패):
- `npm_checks.json`: `npm run typecheck · lint · test · build`의 종료 코드 · 요약 수(`build`가 `web/dist`를 다시 만듦).
- `screens/*.png` · `screens/screens.json` · `screens/screen_texts.json`: 화면 그림(상태 36 × 1440 · 390) · 목록 · 화면 글(`screens.py`).
- `web_counts.json`: 웹 숫자(화면 경계 · jscpd · 같은 CSS · 원시 토큰 · 토큰 대조 · 같은 글 · 줄 · 파일 · `webcounts.py`).
- `forbidden_words.json`: 금지어(빌드 결과 · 화면 글 · `webchecks.py`).
`versions.txt`에는 Playwright · 브라우저 판을 더해요.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[2]
DEFAULT_OUT = Path(__file__).resolve().parent / "server"
DEFAULT_WEB_OUT = Path(__file__).resolve().parent / "web"
BODY_FILES = ("clock.json", "mask.json", "api_shapes.json", "engine_cases.json", "dayflow.json", "counts.json",
              "pytest.json", "versions.txt")
WEB_BODY_FILES = ("npm_checks.json", "web_counts.json", "forbidden_words.json", "screens/screens.json",
                  "screens/screen_texts.json")  # + screens/*.png
TIMING_FILE = "timing.json"


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


@contextlib.contextmanager
def temp_home() -> Iterator[dict[str, str]]:
    """자식 프로세스(pytest · npm · node · 서버)용 환경: HOME은 운영체제 임시 폴더(끝나면 지움 · P1-02 ④).

    키 파일 · 실제 전송 설정 파일의 기본 자리가 `~/.config/quant-service/`라, 자식이 실제 홈을 만들거나 읽지 않게 해요.
    npm · npx 캐시(`~/.npm`)만은 진짜 것을 가리켜요(jscpd 같은 npx 도구를 다시 내려받지 않게 · 키와 무관).
    `run()`이 이 환경을 `os.environ`에 걸어 두어 그 안에서 띄우는 모든 자식이 물려받아요.
    """
    real_home = os.environ.get("HOME", "")
    with tempfile.TemporaryDirectory(prefix="quant-baseline-home-") as d:
        env = dict(os.environ, HOME=d)
        npm_cache = Path(real_home) / ".npm" if real_home else None
        if "npm_config_cache" not in env and npm_cache is not None and npm_cache.is_dir():
            env["npm_config_cache"] = str(npm_cache)
        yield env


@contextlib.contextmanager
def _children_use_temp_home() -> Iterator[None]:
    saved = dict(os.environ)
    with temp_home() as env:
        os.environ.clear()
        os.environ.update(env)
        try:
            yield
        finally:
            os.environ.clear()
            os.environ.update(saved)


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
    npm = sh(["npm", "ls", "--depth=0", "--unicode"], cwd=APP / "web")  # 트리 꼴을 명시(로케일에 흔들리지 않게)
    npm_lines = []
    for line in npm.splitlines():
        if " /" in line and not line.startswith(("├", "└", "│")):  # "web@0.0.0 /abs/path" → 경로 지움
            line = line.split(" /", 1)[0]
        npm_lines.append(line.rstrip())
    return "\n".join(["# pip freeze --all", pip, "", "# node -v", node, "", "# npm ls --depth=0 --unicode (web)", *npm_lines, ""])


def screen_versions_text() -> str:
    """화면 찍기 도구 판(P1-01c): `web/node_modules`의 playwright · @playwright/test 판과 `PW_CHROMIUM` 브라우저의 `--version`."""
    def pkg_version(name: str) -> str:
        p = APP / "web" / "node_modules" / name / "package.json"
        try:
            return str(json.loads(p.read_text(encoding="utf-8"))["version"])
        except (OSError, KeyError, ValueError):
            return "(not installed)"

    chromium = os.environ.get("PW_CHROMIUM") or "/opt/pw-browsers/chromium"
    try:
        p = subprocess.run([chromium, "--version"], capture_output=True, text=True)
        browser = (p.stdout or p.stderr).strip()
    except OSError as exc:
        browser = f"(not available: {type(exc).__name__})"
    return "\n".join(["# playwright (web/node_modules)", f"playwright {pkg_version('playwright')}",
                      f"@playwright/test {pkg_version('@playwright/test')}", "",
                      "# browser (PW_CHROMIUM --version · DEVELOPING 4절)", f"PW_CHROMIUM={chromium}", browser, ""])


def require_node_24() -> str:
    """DEVELOPING 4절: Node 24가 아니면 `versions.txt`가 달라져 두 번 같음 · 대조가 깨져요. 까닭을 적고 실패해요."""
    try:
        v = subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.strip()
    except OSError as exc:
        raise SystemExit(f"node가 없어요({type(exc).__name__}) · Node 24가 필요해요(`. /opt/session-env.sh` 뒤에 돌려요)")
    if not v.startswith("v24."):
        raise SystemExit(f"node 판이 {v or '(없음)'}이에요 · 기준선은 Node 24로 만들고 대조해요(`. /opt/session-env.sh` 뒤에)")
    return v


def web_out_for(out: Path) -> Path:
    """`--out`만 주면 웹 기록도 저장소 밖으로: `…/server` → `…/web`(compare · 기본 배치와 같음) · 그 밖은 `<out>/web`."""
    return out.parent / "web" if out.name == "server" else out / "web"


def run_web(web_out: Path, timing: dict[str, Any], *, quiet: bool = False) -> None:
    """화면 · 웹 숫자(P1-01c): npm 검사(build가 dist를 만듦) → 화면 찍기 → 웹 숫자 → 금지어."""
    from tests.baseline import screens, webchecks, webcounts

    web_out.mkdir(parents=True, exist_ok=True)
    t0 = time.perf_counter()
    npm, npm_timing, outputs = webchecks.npm_checks()
    _dump(web_out / "npm_checks.json", npm)
    timing["npm_seconds"] = npm_timing
    if os.environ.get("QUANT_BASELINE_KEEP_PYTEST_OUTPUT"):
        for k, v in outputs.items():
            (web_out / f"npm_{k}_output.txt").write_text(v, encoding="utf-8")
    if not quiet:
        print("npm:", {k: v["exit"] for k, v in npm.items()}, f"({time.perf_counter() - t0:.1f}s)")

    t0 = time.perf_counter()
    idx = screens.capture(web_out, quiet=True)
    timing["screens_seconds"] = round(time.perf_counter() - t0, 2)
    if not quiet:
        print("screens:", idx["summary"], f"({timing['screens_seconds']}s)")

    t0 = time.perf_counter()
    wc = webcounts.run_all()
    timing["webcounts_seconds"] = round(time.perf_counter() - t0, 2)
    _dump(web_out / "web_counts.json", wc)
    if not quiet:
        print("web counts:", wc["summary"])

    fw = webchecks.forbidden_words(web_out / "screens" / "screen_texts.json")
    _dump(web_out / "forbidden_words.json", fw)
    if not quiet:
        print(f"forbidden words: dist {fw['dist_count']} · screens {fw['screen_count']}")


def run(out: Path, *, skip_pytest: bool = False, quiet: bool = False, skip_web: bool = False,
        web_out: Path | None = None) -> dict[str, Any]:
    with _children_use_temp_home():  # 자식(pytest · npm · node · 서버)의 HOME은 임시 폴더(P1-02 ④)
        return _run(out, skip_pytest=skip_pytest, quiet=quiet, skip_web=skip_web, web_out=web_out)


def _run(out: Path, *, skip_pytest: bool, quiet: bool, skip_web: bool, web_out: Path | None) -> dict[str, Any]:
    from tests.baseline import clock, counts, dayflow, engine_cases, mask, replay, screen_api

    web_out = web_out or web_out_for(out)
    require_node_24()
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

    if not skip_web:
        run_web(web_out, timing, quiet=quiet)

    (out / "versions.txt").write_text(versions_text() + "\n" + screen_versions_text(), encoding="utf-8")
    _dump(out / TIMING_FILE, timing)
    return {"out": str(out), "web_out": str(web_out), "timing": timing}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--web-out", default=None, help="웹 기록 폴더(기본: --out이 `server`로 끝나면 그 옆 `web` · 아니면 --out 아래 `web`)")
    ap.add_argument("--skip-pytest", action="store_true", help="API 모양 · pytest 수를 다시 만들지 않음(빠른 확인용)")
    ap.add_argument("--skip-web", action="store_true", help="화면 · 웹 숫자(P1-01c)를 다시 만들지 않음(빠른 확인용)")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)
    run(Path(a.out), skip_pytest=a.skip_pytest, quiet=a.quiet, skip_web=a.skip_web,
        web_out=Path(a.web_out) if a.web_out else web_out_for(Path(a.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
