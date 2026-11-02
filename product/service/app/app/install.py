"""설치기 도움(T-56 · SPEC 5-10 · 10 설치기): 서비스 파일 만들기 · 업데이트 시간 검사 · 업데이트 단계 기록.

설치 스크립트(`install/*.sh`)가 이 모듈을 불러 systemd 유닛 · launchd plist를 만들고, 업데이트 때 단계를
데이터 폴더 `update.json`에 적어요(앱은 읽기만 · `updates.py`).

    python -m app.install systemd --app <앱 폴더> --data <데이터 폴더> --user quant [--port 8765] [--ts-name …]
    python -m app.install plist --app <앱 폴더> --data <데이터 폴더> [--port 8765]
    python -m app.install can-update [--data <데이터 폴더>]       # 거래일 16:00~20:00만 0, 아니면 이유 + 1
    python -m app.install step <데이터 폴더> <단계> <running|done|failed> <버전>

- 실제 전송(QUANT_LIVE_TRANSPORT)은 유닛에 넣지 않아요. 켜려면 설치 스크립트의 `--live`가 설정 파일과 함께 따로
  써요(DEVELOPING 3절 · 두 열쇠). 시험 · 기본 설치는 늘 가짜 전송이에요.
- 앱은 127.0.0.1에만 묶어요(`app.serve`). 바깥은 Tailscale serve가 https로 받아 넘겨요.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, time
from pathlib import Path
from xml.sax.saxutils import escape

from .market import KST, Calendar

LABEL = "kr.quant.service"
UPDATE_FROM = time(16, 0)
UPDATE_UNTIL = time(20, 0)
WINDOW_TEXT = "업데이트는 거래일 16:00~20:00(그날 20:10 확인 전)에만 해요"


def systemd_unit(app: Path, data: Path, user: str, port: int = 8765, ts_name: str | None = None,
                 home: Path | None = None) -> str:
    """서버(systemd) 서비스. 키 파일 폴더(`~/.config/quant-service`)는 설치 스크립트가 먼저 만들어요(700)."""
    home = home or Path(f"/home/{user}")
    env = [f"MVP_DATA_DIR={data}", f"MVP_PORT={port}"]
    if ts_name:
        env.append(f"QUANT_TS_NAME={ts_name}")
    env_lines = "\n".join(f"Environment={e}" for e in env)
    return f"""[Unit]
Description=quant 실전 운용 앱(127.0.0.1:{port})
Wants=network-online.target
After=network-online.target tailscaled.service

[Service]
Type=simple
User={user}
WorkingDirectory={app}
{env_lines}
ExecStart={app}/.venv/bin/python -m app.serve --port {port} --data {data}
Restart=always
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths={data} {home}/.config/quant-service

[Install]
WantedBy=multi-user.target
"""


def launchd_plist(app: Path, data: Path, port: int = 8765) -> str:
    args = [f"{app}/.venv/bin/python", "-m", "app.serve", "--port", str(port), "--data", str(data)]
    arg_xml = "\n".join(f"    <string>{escape(a)}</string>" for a in args)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>{LABEL}</string>
  <key>ProgramArguments</key>
  <array>
{arg_xml}
  </array>
  <key>WorkingDirectory</key>
  <string>{escape(str(app))}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>Umask</key>
  <integer>63</integer>
  <key>StandardOutPath</key>
  <string>{escape(str(data))}/server.log</string>
  <key>StandardErrorPath</key>
  <string>{escape(str(data))}/server.log</string>
</dict>
</plist>
"""


def update_window(now: datetime, cal: Calendar | None = None) -> tuple[bool, str]:
    """SPEC 5-10: 거래일 16:00~20:00(그날 20:10 확인 전)에만. 아니면 거절 이유."""
    local = now.astimezone(KST)
    is_open = cal.is_open(local.date()) if cal is not None else local.weekday() < 5
    if not is_open:
        return False, f"오늘은 거래일이 아니에요 · {WINDOW_TEXT}"
    if not (UPDATE_FROM <= local.time() < UPDATE_UNTIL):
        return False, f"지금은 할 수 없어요 · {WINDOW_TEXT}"
    return True, ""


def write_step(data: Path, step: str, state: str, version: str) -> None:
    from .updates import FILE, STEPS

    if step not in [k for k, _ in STEPS] or state not in ("running", "done", "failed"):
        raise ValueError("step")
    p = data / FILE
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({"version": version, "step": step, "state": state,
                               "at": datetime.now(KST).isoformat(timespec="seconds")}), encoding="utf-8")
    tmp.replace(p)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="app.install")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("systemd")
    s.add_argument("--app", required=True)
    s.add_argument("--data", required=True)
    s.add_argument("--user", required=True)
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--ts-name")
    s.add_argument("--home")
    m = sub.add_parser("plist")
    m.add_argument("--app", required=True)
    m.add_argument("--data", required=True)
    m.add_argument("--port", type=int, default=8765)
    c = sub.add_parser("can-update")
    c.add_argument("--data")
    w = sub.add_parser("step")
    w.add_argument("data")
    w.add_argument("step")
    w.add_argument("state")
    w.add_argument("version")
    a = p.parse_args(argv)
    if a.cmd == "systemd":
        sys.stdout.write(systemd_unit(Path(a.app), Path(a.data), a.user, a.port, a.ts_name,
                                      Path(a.home) if a.home else None))
    elif a.cmd == "plist":
        sys.stdout.write(launchd_plist(Path(a.app), Path(a.data), a.port))
    elif a.cmd == "can-update":
        cal = None
        if a.data and (Path(a.data) / "app.db").exists():
            from .db import DB

            cal = Calendar(DB(Path(a.data) / "app.db"), None)  # 앱이 받아 둔 토스 장 달력(없으면 평일 규칙)
        ok, why = update_window(datetime.now(KST), cal)
        if not ok:
            print(why, file=sys.stderr)
            return 1
    elif a.cmd == "step":
        write_step(Path(a.data), a.step, a.state, a.version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
