#!/bin/bash
# 늘 켜 둔 PC(macOS) 설치 · 다시 설치: bash install/install-mac.sh [--port 8765] [--live]
#
# - 앱 ~/quant-service/app · 데이터 ~/quant-service/data(700) · launchd(로그인할 때 자동 시작 · 꺼지면 다시)
# - 127.0.0.1에만 묶어요. 휴대폰으로 보려면 Tailscale 앱을 깔고 serve를 켜요(선택)
# - 실제 전송은 --live를 줄 때만 켜요(설정 파일 + 환경 변수 두 열쇠)
set -euo pipefail
umask 077
PORT=8765
LIVE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --live) LIVE=1; shift ;;
    *) echo "모르는 옵션이에요: $1" >&2; exit 2 ;;
  esac
done
SRC="$(cd "$(dirname "$0")/.." && pwd)"
BASE="$HOME/quant-service"
APP="$BASE/app"
DATA="$BASE/data"
PLIST="$HOME/Library/LaunchAgents/kr.quant.service.plist"
PY="$(command -v python3.12 || echo /opt/homebrew/bin/python3.12)"
[ -x "$PY" ] || { echo "Python 3.12가 없어요 · brew install python@3.12" >&2; exit 1; }

echo "1/4 앱 복사"
mkdir -p "$BASE" "$DATA" "$HOME/.config/quant-service"
chmod 700 "$BASE" "$DATA" "$HOME/.config/quant-service"
rm -rf "$APP.new"
mkdir -p "$APP.new"
(cd "$SRC" && tar --exclude=.venv --exclude=data --exclude=web/node_modules --exclude=tests/.tmp -cf - .) | (cd "$APP.new" && tar -xf -)
[ -d "$APP" ] && rm -rf "$APP.prev" && mv "$APP" "$APP.prev"
mv "$APP.new" "$APP"

echo "2/4 파이썬 · 화면"
"$PY" -m venv "$APP/.venv"
PIP_NO_CACHE_DIR=1 "$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
if [ ! -f "$APP/web/dist/index.html" ]; then
  (cd "$APP/web" && npm ci --no-audit --no-fund --loglevel=error && npm run build >/dev/null)
fi

echo "3/4 서비스 등록(launchd)"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || true
"$APP/.venv/bin/python" -m app.install plist --app "$APP" --data "$DATA" --port "$PORT" > "$PLIST"
rm -f "$HOME/.config/quant-service/live-transport.json"
if [ "$LIVE" = 1 ]; then
  printf '{"live_transport": true}\n' > "$HOME/.config/quant-service/live-transport.json"
  /usr/libexec/PlistBuddy -c "Add :EnvironmentVariables dict" -c "Add :EnvironmentVariables:QUANT_LIVE_TRANSPORT string 1" "$PLIST"
fi
launchctl bootstrap "gui/$(id -u)" "$PLIST"

echo "4/4 확인"
for _ in $(seq 1 40); do curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break; sleep 0.5; done
echo "설치했어요 · http://127.0.0.1:$PORT"
echo "절전 모드를 꺼 두어요(시스템 설정 › 배터리 › 전원 어댑터 › 디스플레이가 꺼져도 잠자기 안 함)"
