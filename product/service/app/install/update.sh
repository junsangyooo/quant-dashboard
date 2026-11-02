#!/bin/bash
# 업데이트(SPEC 5-10): sudo bash install/update.sh <새 앱 폴더> <버전>   (서버 · PC 같음)
#
# 거래일 16:00~20:00(그날 20:10 확인 전)에만 해요. 순서: 스케줄러 멈춤 → 백업 → 데이터 구조 바꿈 → 다시 켬 → 대조.
# 단계는 데이터 폴더 update.json에 적고(앱이 '업데이트 중' 칩 · 끝나면 텔레그램), 실패하면 이전 버전 + 백업으로 되돌려요.
set -euo pipefail
umask 077
NEW="${1:?새 앱 폴더}"
VER="${2:?버전}"
if [ -d /opt/quant-service/app ]; then
  APP=/opt/quant-service/app; DATA=/var/lib/quant-service/data; KIND=server
else
  APP="$HOME/quant-service/app"; DATA="$HOME/quant-service/data"; KIND=pc
fi
PY="$APP/.venv/bin/python"
PORT="$(grep -o 'MVP_PORT=[0-9]*' /etc/systemd/system/quant-service.service 2>/dev/null | cut -d= -f2 || true)"
PORT="${PORT:-8765}"
step() { (cd "$APP" && "$PY" -m app.install step "$DATA" "$1" "$2" "$VER"); }
svc() {
  if [ "$KIND" = server ]; then systemctl "$1" quant-service
  elif [ "$1" = stop ]; then launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/kr.quant.service.plist" || true
  else launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/kr.quant.service.plist"; fi
}
(cd "$APP" && "$PY" -m app.install can-update --data "$DATA") || exit 1

CUR=stop
rollback() {
  step "$CUR" failed || true
  echo "업데이트가 실패했어요 · 이전 버전과 백업으로 되돌려요" >&2
  svc stop || true
  if [ -d "$APP.prev" ]; then rm -rf "$APP"; mv "$APP.prev" "$APP"; fi
  [ -f "$BACKUP" ] && cp "$BACKUP" "$DATA/app.db" && rm -f "$DATA/app.db-wal" "$DATA/app.db-shm"
  svc start || true
}
BACKUP=""
trap rollback ERR

step stop running; svc stop; step stop done
CUR=backup; step backup running
mkdir -p "$DATA/backups"
BACKUP="$DATA/backups/app-before-$VER-$(date +%Y%m%d-%H%M).db"
cp "$DATA/app.db" "$BACKUP"
step backup done
CUR=migrate; step migrate running
rm -rf "$APP.prev"; cp -a "$APP" "$APP.prev"
(cd "$NEW" && tar --exclude=.venv --exclude=data --exclude=web/node_modules -cf - .) | (cd "$APP" && tar -xf -)
PIP_NO_CACHE_DIR=1 "$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"
step migrate done   # 데이터 구조는 앱이 켜질 때 바꿔요(db.py · 바꾸기 전 사본 .v1-backup)
CUR=restart; step restart running
svc start
for _ in $(seq 1 60); do curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1 && break; sleep 0.5; done
curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null
step restart done
CUR=reconcile; step reconcile running
# 대조(R-L6)는 앱이 켜질 때 스스로 해요 · 여기서는 앱이 살아 있는지만 다시 봐요
curl -fs "http://127.0.0.1:$PORT/api/health" >/dev/null
step reconcile done
trap - ERR
echo "업데이트 끝 · 버전 $VER"
