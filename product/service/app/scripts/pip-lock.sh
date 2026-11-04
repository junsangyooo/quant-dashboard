#!/usr/bin/env bash
# 해시 lock 파일 만들기(P1-02 ⑦ · QUALITY S7): requirements.txt → requirements.lock · requirements-dev.txt → requirements-dev.lock.
#
#   cd product/service/app && scripts/pip-lock.sh        # 어느 폴더에서 불러도 같아요(이 파일 위치 기준)
#
# - 도구: pip-tools 7.6.2(requirements-dev.txt · 같은 venv의 `python -m piptools`).
# - 판: 기준선 `tests/baseline/server/versions.txt`의 `pip freeze --all` 목록을 제약(constraint)으로 주어 **지금 설치된 판
#   그대로** 고정해요(새 도구와 그 의존성만 더해져요). 판을 올리려면 먼저 기준선을 다시 만들어요(1단계는 판을 올리지 않아요).
# - `--allow-unsafe`: pip-tools가 pip · setuptools에 기대므로 dev lock에 그 판도 적어요.
# - 설치: `pip install --require-hashes -r requirements.lock`(앱) · `-r requirements-dev.lock`(개발 · 시험 · check.sh).
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${QUANT_PYTHON:-.venv/bin/python}
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT
awk '/^# pip freeze --all/{f=1;next} /^$/{f=0} f' tests/baseline/server/versions.txt > "$tmp"
for pair in "requirements.txt requirements.lock" "requirements-dev.txt requirements-dev.lock"; do
  set -- $pair
  CUSTOM_COMPILE_COMMAND="scripts/pip-lock.sh" "$PY" -m piptools compile --quiet --generate-hashes --allow-unsafe \
    --constraint "$tmp" --output-file "$2" "$1"
  echo "$2: $(grep -cE '^[A-Za-z0-9_.-]+==' "$2") packages pinned with hashes"
done
