#!/bin/bash
# 서버(Ubuntu LTS) 설치 · 다시 설치: sudo bash install/install-server.sh [--port 8765] [--live]
#
# - 서비스 사용자 quant · 앱 /opt/quant-service/app · 데이터 /var/lib/quant-service/data(700)
# - systemd 서비스 quant-service(재부팅 뒤 자동 시작 · 127.0.0.1에만 묶음 · 로그인 없이 운용 이어짐)
# - Tailscale이 없으면 설치하고 로그인 링크를 보여 줘요 · serve로 https 화면 주소를 열어요
# - 실제 전송(토스 주문 · 텔레그램 · DART)은 --live를 줄 때만 켜요(설정 파일 + 환경 변수 두 열쇠 · DEVELOPING 3절)
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
[ "$(id -u)" = 0 ] || { echo "sudo로 실행해 주세요" >&2; exit 1; }

SRC="$(cd "$(dirname "$0")/.." && pwd)"
SVC_USER=quant
HOME_DIR=/var/lib/quant-service
APP=/opt/quant-service/app
DATA="$HOME_DIR/data"

echo "1/6 서비스 사용자 · 폴더"
id "$SVC_USER" >/dev/null 2>&1 || useradd --system --home-dir "$HOME_DIR" --create-home --shell /usr/sbin/nologin "$SVC_USER"
install -d -m 700 -o "$SVC_USER" -g "$SVC_USER" "$HOME_DIR" "$DATA" "$HOME_DIR/.config" "$HOME_DIR/.config/quant-service"

echo "2/6 앱 복사"
install -d -m 755 /opt/quant-service
rm -rf "$APP.new"
mkdir -p "$APP.new"
(cd "$SRC" && tar --exclude=.venv --exclude=data --exclude=web/node_modules --exclude=tests/.tmp -cf - .) | (cd "$APP.new" && tar -xf -)
[ -d "$APP" ] && rm -rf "$APP.prev" && mv "$APP" "$APP.prev"
mv "$APP.new" "$APP"

echo "3/6 파이썬 · 화면"
python3 -m venv "$APP/.venv"
PIP_NO_CACHE_DIR=1 "$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
if [ ! -f "$APP/web/dist/index.html" ]; then
  (cd "$APP/web" && npm ci --no-audit --no-fund --loglevel=error && npm run build >/dev/null)
fi
chown -R root:root "$APP"
chmod -R go-w,o+rX "$APP"

echo "4/6 Tailscale"
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
tailscale status >/dev/null 2>&1 || tailscale up   # 처음이면 로그인 링크가 나와요
TS_NAME="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))' 2>/dev/null || true)"

echo "5/6 서비스 등록"
"$APP/.venv/bin/python" -m app.install systemd --app "$APP" --data "$DATA" --user "$SVC_USER" --home "$HOME_DIR" \
  --port "$PORT" ${TS_NAME:+--ts-name "$TS_NAME"} > /etc/systemd/system/quant-service.service
rm -f /etc/systemd/system/quant-service.service.d/live.conf
if [ "$LIVE" = 1 ]; then
  install -d -m 755 /etc/quant-service /etc/systemd/system/quant-service.service.d
  printf '{"live_transport": true}\n' > /etc/quant-service/live-transport.json
  chmod 644 /etc/quant-service/live-transport.json
  printf '[Service]\nEnvironment=QUANT_LIVE_TRANSPORT=1\n' > /etc/systemd/system/quant-service.service.d/live.conf
fi
systemctl daemon-reload
systemctl enable --now quant-service

echo "6/6 화면 주소"
for _ in $(seq 1 40); do curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break; sleep 0.5; done
if [ -n "$TS_NAME" ]; then
  tailscale serve --bg --https=443 "http://127.0.0.1:$PORT"
  echo "화면 주소 · https://$TS_NAME"
else
  echo "Tailscale 이름을 찾지 못했어요 · tailscale up으로 로그인한 뒤 다시 실행해 주세요"
fi
echo "설치했어요 · 재부팅하면 자동으로 켜지고 운용이 이어져요"
