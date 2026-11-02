#!/bin/bash
# 앱 켜기: 처음이면 준비(파이썬 venv · 화면 빌드)하고, 127.0.0.1:8765로 켠 뒤 브라우저를 연다.
# 이미 빌드돼 있으면 빌드를 건너뛴다. 이미 켜져 있으면 열기만 한다.
set -euo pipefail
umask 077
cd "$(dirname "$0")"
DATA="${MVP_DATA_DIR:-data}"
PORT="${MVP_PORT:-8765}"
URL="http://127.0.0.1:${PORT}"
PY=/opt/homebrew/bin/python3.12

if curl -fs --max-time 2 "${URL}/api/health" 2>/dev/null | grep -q '"quant-mvp"'; then
  echo "이미 켜져 있어요 · ${URL}"
  open "${URL}"
  exit 0
fi

if [ ! -x .venv/bin/python ]; then
  if [ ! -x "$PY" ]; then
    echo "Python 3.12가 없어요 · brew install python@3.12 로 설치해 주세요" >&2
    exit 1
  fi
  echo "처음이라 준비하고 있어요(1~2분)…"
  "$PY" -m venv .venv
  PIP_NO_CACHE_DIR=1 .venv/bin/pip install -q --upgrade pip
  PIP_NO_CACHE_DIR=1 .venv/bin/pip install -q -r requirements.txt
fi

if [ ! -f web/dist/index.html ]; then
  if ! command -v npm >/dev/null 2>&1; then
    echo "Node.js 24가 없어요 · brew install node@24 로 설치해 주세요" >&2
    exit 1
  fi
  echo "처음이라 화면을 만들고 있어요(1~2분)…"
  (cd web && npm ci --no-audit --no-fund --loglevel=error && npm run build >/dev/null)
fi

mkdir -p "$DATA"
chmod 700 "$DATA"
export MVP_DATA_DIR="$DATA"
touch "$DATA/server.log" && chmod 600 "$DATA/server.log"
# app.serve: 127.0.0.1에만 묶고 데이터 폴더의 app.lock으로 두 번째 실행을 막아요(T-51 · R-L5)
nohup .venv/bin/python -m app.serve --port "${PORT}" --data "$DATA" \
  >> "$DATA/server.log" 2>&1 &
echo $! > "$DATA/server.pid"

for _ in $(seq 1 40); do
  if curl -fs --max-time 1 "${URL}/api/health" >/dev/null 2>&1; then
    echo "켜졌어요 · ${URL}"
    open "${URL}"
    exit 0
  fi
  sleep 0.5
done
echo "켜지지 않았어요 · $DATA/server.log를 봐 주세요" >&2
exit 1
