#!/usr/bin/env bash
# 한 번에 모든 장치(ARCHITECTURE 7절 · TASKS P1-02 ⑥). 일감이 끝날 때마다 돌려요.
#
#   product/service/app/scripts/check.sh            # 어느 폴더에서 불러도 같아요(이 파일 위치 기준 product/service/app에서 돌아요)
#
# 단계(첫 실패에서 멈추지 않고 끝까지 돌아 모아 보고 · 모두 통과일 때만 종료 0):
#   secrets(비밀 검사 S11) → commit(커밋 위생) → ruff → mypy → pytest(전체 · 소스 검사 포함) → web-typecheck · web-lint · web-test ·
#   web-build → e2e-vault(금고 흐름 화면 시험) → pip-audit · npm-audit(허용 목록) → compare(기준선 대조 · 화면 포함 · 포트 8797).
# 조건: Node 24(아니면 까닭을 적고 종료 2) · `PW_CHROMIUM`(비어 있으면 /opt/pw-browsers/chromium · 브라우저는 내려받지 않음) ·
#   `.venv`(requirements-dev.lock으로 설치 · `QUANT_PYTHON`으로 바꿀 수 있음) · `web/node_modules`(npm ci) · 포트 8797 · 8798 비어 있음.
# 출력: 단계 전체 출력은 저장소 밖 `/tmp/check/<날짜시각>/NN-단계.log`(`CHECK_OUT`으로 바꿀 수 있음) · 화면에는 단계마다 한 줄과 끝에 요약 표.
set -u
APP="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP" || exit 2
PY=${QUANT_PYTHON:-"$APP/.venv/bin/python"}
export PW_CHROMIUM=${PW_CHROMIUM:-/opt/pw-browsers/chromium}
OUT=${CHECK_OUT:-/tmp/check/$(date +%Y%m%d-%H%M%S)}
mkdir -p "$OUT" || exit 2

node_v=$(node -v 2>/dev/null || echo '(없음)')
case "$node_v" in
  v24.*) ;;
  *) echo "node 판이 ${node_v}이에요 · Node 24가 필요해요(기준선 · package-lock · Playwright가 Node 24 기준 · \`. /opt/session-env.sh\` 뒤에 돌려요)" >&2
     exit 2 ;;
esac
[ -x "$PY" ] || { echo "파이썬이 없어요: $PY (python3.12 -m venv .venv && .venv/bin/pip install --require-hashes -r requirements-dev.lock)" >&2; exit 2; }
# 아무 실행 파일(`/bin/true` 같은 것)을 QUANT_PYTHON에 주면 파이썬 단계가 소리 없이 통과하므로, 판과 도구 import 결과를 **출력으로** 확인해요.
py_v=$("$PY" -c 'import sys; print(sys.version.split()[0])' 2>/dev/null)
case "$py_v" in
  3.*) ;;
  *) echo "파이썬이 아니거나 돌지 않아요: $PY (판 출력: '${py_v}') · QUANT_PYTHON은 requirements-dev.lock을 설치한 venv의 python이어야 해요" >&2; exit 2 ;;
esac
tools=$("$PY" -c 'import pytest, ruff, mypy, pip_audit; print("tools-ok")' 2>/dev/null)
[ "$tools" = "tools-ok" ] || {
  echo "파이썬 $PY($py_v)에 pytest · ruff · mypy · pip-audit이 없어요 · 파이썬 단계가 소리 없이 통과하지 않게 멈춰요(.venv/bin/pip install --require-hashes -r requirements-dev.lock)" >&2
  exit 2
}
[ -x "$PW_CHROMIUM" ] || echo "주의: 화면 찍기 브라우저가 없어요: PW_CHROMIUM=$PW_CHROMIUM (e2e-vault · compare 단계가 실패해요)" >&2

names=(); codes=(); secs=()
n=0
run_step() {  # run_step 이름 명령...
  local name=$1; shift
  n=$((n + 1))
  local log; log=$(printf '%s/%02d-%s.log' "$OUT" "$n" "$name")
  local t0; t0=$(date +%s)
  printf '%-14s ' "$name"
  "$@" > "$log" 2>&1
  local code=$?
  local took=$(( $(date +%s) - t0 ))
  names+=("$name"); codes+=("$code"); secs+=("$took")
  if [ "$code" = 0 ]; then echo "통과  ${took}s"; else echo "실패  ${took}s  (exit $code · $log)"; tail -n 3 "$log" | sed 's/^/    /'; fi
}
in_web() { (cd "$APP/web" && "$@"); }
port_free() { ! (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
compare_step() {
  if ! port_free 8797; then echo "포트 8797이 비어 있지 않아요(기준선 화면 서버 자리) · 다른 capture · compare가 돌고 있는지 봐요"; return 1; fi
  "$PY" -m tests.baseline.compare --keep "$OUT/compare"
}

echo "check.sh · $(date '+%Y-%m-%d %H:%M:%S') · node $node_v · python $PY ($py_v) · 출력 $OUT"
run_step secrets        "$PY" scripts/secrets_scan.py
run_step commit         scripts/commit_hygiene.sh
run_step ruff           "$PY" scripts/lint_allow.py ruff
run_step mypy           "$PY" scripts/lint_allow.py mypy
run_step pytest         "$PY" -m pytest
run_step web-typecheck  in_web npm run typecheck
run_step web-lint       in_web npm run lint
run_step web-test       in_web npm run test
run_step web-build      in_web npm run build
run_step e2e-vault      npx --prefix web playwright test -c web/e2e/playwright.config.ts
run_step pip-audit      "$PY" scripts/audit_allow.py pip
run_step npm-audit      "$PY" scripts/audit_allow.py npm
run_step compare        compare_step

echo
echo "단계           결과   시간    종료"
fails=0; total=0
for i in "${!names[@]}"; do
  c=${codes[$i]}; total=$((total + secs[$i]))
  [ "$c" = 0 ] && r=통과 || { r=실패; fails=$((fails + 1)); }
  printf '%-14s %s   %4ss   %s\n' "${names[$i]}" "$r" "${secs[$i]}" "$c"
done
printf '%-14s %s   %4ss   %s\n' "모두" "$([ "$fails" = 0 ] && echo 통과 || echo "실패 $fails")" "$total" "$([ "$fails" = 0 ] && echo 0 || echo 1)"
echo "출력: $OUT"
[ "$fails" = 0 ]
