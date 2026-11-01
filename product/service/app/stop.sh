#!/bin/bash
# 앱 끄기. 끄면 풀려 있던 키가 메모리에서 사라져요(다음에 켜면 비밀번호로 다시 열어요).
set -euo pipefail
cd "$(dirname "$0")"
DATA="${MVP_DATA_DIR:-data}"
if [ -f "$DATA/server.pid" ]; then
  PID="$(cat "$DATA/server.pid")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    for _ in $(seq 1 40); do
      kill -0 "$PID" 2>/dev/null || break
      sleep 0.25
    done
    if kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID" 2>/dev/null || true
    fi
    echo "껐어요"
  else
    echo "이미 꺼져 있어요"
  fi
  rm -f "$DATA/server.pid"
else
  echo "켜진 앱을 찾지 못했어요"
fi
