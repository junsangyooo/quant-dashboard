#!/bin/bash
# 지우기: sudo bash install/uninstall.sh [--purge]   (--purge: 데이터 · 키 파일까지)
set -euo pipefail
PURGE=0
[ "${1:-}" = --purge ] && PURGE=1
if [ -f /etc/systemd/system/quant-service.service ]; then
  systemctl disable --now quant-service || true
  rm -rf /etc/systemd/system/quant-service.service /etc/systemd/system/quant-service.service.d /etc/quant-service
  systemctl daemon-reload
  rm -rf /opt/quant-service
  [ "$PURGE" = 1 ] && rm -rf /var/lib/quant-service
else
  launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/kr.quant.service.plist" 2>/dev/null || true
  rm -f "$HOME/Library/LaunchAgents/kr.quant.service.plist"
  rm -rf "$HOME/quant-service/app" "$HOME/quant-service/app.prev"
  [ "$PURGE" = 1 ] && rm -rf "$HOME/quant-service" "$HOME/.config/quant-service"
fi
echo "지웠어요"
