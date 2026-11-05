"""T-56 설치기: 서비스 파일 · 업데이트 시간 · 단계 기록 · 스크립트 꼴 · 서비스 재시작(재부팅 흉내).

깨끗한 Ubuntu · macOS에 실제로 설치하고 컴퓨터를 다시 켜는 확인은 이 컨테이너에서 할 수 없어요(systemd가 PID 1이 아님 ·
macOS 없음) → OPEN-QUESTIONS Q-N11. 여기서는 유닛이 부르는 명령 그대로 프로세스를 켜고 끄고 다시 켜요(가짜 전송 · 오프라인).
"""

from __future__ import annotations

import json
import os
import plistlib
import re
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime
from pathlib import Path

import pytest

from app import install, updates
from app.store.db import DB
from app.domain.markets.kr import KST
from app.run.data import Calendar

APP = Path(__file__).resolve().parents[1]
SCRIPTS = APP / "install"


# ── 서비스 파일 ──────────────────────────────────────────────────────────────


def test_systemd_unit() -> None:
    u = install.systemd_unit(Path("/opt/quant-service/app"), Path("/var/lib/quant-service/data"), "quant", 8765,
                             "quant.tail1234.ts.net", Path("/var/lib/quant-service"))
    assert "ExecStart=/opt/quant-service/app/.venv/bin/python -m app.serve --port 8765 --data /var/lib/quant-service/data" in u
    assert "Restart=always" in u and "WantedBy=multi-user.target" in u and "User=quant" in u
    assert "Environment=QUANT_TS_NAME=quant.tail1234.ts.net" in u
    assert "ReadWritePaths=/var/lib/quant-service/data /var/lib/quant-service/.config/quant-service" in u
    assert "UMask=0077" in u and "ProtectSystem=strict" in u
    assert "0.0.0.0" not in u and "--host" not in u
    assert "QUANT_LIVE_TRANSPORT" not in u  # 실제 전송은 유닛에 없어요(--live 드롭인만)
    assert "QUANT_TS_NAME" not in install.systemd_unit(Path("/a"), Path("/d"), "quant")


def test_launchd_plist() -> None:
    p = plistlib.loads(install.launchd_plist(Path("/Users/me/quant-service/app"), Path("/Users/me/quant-service/data"),
                                             8765).encode())
    assert p["Label"] == "kr.quant.service" and p["RunAtLoad"] is True and p["KeepAlive"] is True
    assert p["ProgramArguments"] == ["/Users/me/quant-service/app/.venv/bin/python", "-m", "app.serve", "--port",
                                     "8765", "--data", "/Users/me/quant-service/data"]
    assert p["Umask"] == 0o77 and "EnvironmentVariables" not in p


# ── 업데이트 할 수 있는 때(5-10) ─────────────────────────────────────────────


def test_update_window(tmp_path: Path) -> None:
    db = DB(tmp_path / "a.db")
    db.set_meta("cal.2026-11-03", json.dumps({"open": False, "start": None}))  # 휴장(토스 달력)
    cal = Calendar(db, None)
    at = lambda d, h, m: datetime(*d, h, m, tzinfo=KST)  # noqa: E731
    mon, tue, sat = (2026, 11, 2), (2026, 11, 3), (2026, 11, 7)
    assert install.update_window(at(mon, 16, 0), cal) == (True, "")
    assert install.update_window(at(mon, 19, 59), cal)[0] is True
    for d, h, m in ((mon, 15, 59), (mon, 20, 0), (mon, 20, 10), (mon, 8, 40), (tue, 17, 0), (sat, 17, 0)):
        ok, why = install.update_window(at(d, h, m), cal)
        assert not ok and install.WINDOW_TEXT in why, (d, h, m)
    assert "거래일이 아니에요" in install.update_window(at(tue, 17, 0), cal)[1]
    assert install.update_window(at(mon, 17, 0), None)[0] is True  # 달력 없으면 평일 규칙


def test_update_steps_feed_app_status(tmp_path: Path) -> None:
    install.write_step(tmp_path, "migrate", "running", "1.1")
    s = updates.status(tmp_path)
    assert s["updating"] and s["chip"] == "업데이트 중" and s["version"] == "1.1"
    install.write_step(tmp_path, "reconcile", "done", "1.1")
    assert updates.status(tmp_path)["state"] == "done"
    with pytest.raises(ValueError):
        install.write_step(tmp_path, "nope", "done", "1.1")
    assert install.main(["step", str(tmp_path), "backup", "failed", "1.2"]) == 0
    assert updates.status(tmp_path)["steps"][1]["state"] == "failed"


# ── 스크립트 ─────────────────────────────────────────────────────────────────


def test_scripts_shape() -> None:
    names = sorted(p.name for p in SCRIPTS.glob("*.sh"))
    assert names == ["install-mac.sh", "install-server.sh", "uninstall.sh", "update.sh"]
    for p in SCRIPTS.glob("*.sh"):
        assert subprocess.run(["bash", "-n", str(p)], capture_output=True).returncode == 0, p.name
        text = p.read_text(encoding="utf-8")
        assert "0.0.0.0" not in text and "set -euo pipefail" in text
    # 실제 전송 두 열쇠는 --live 안에서만
    for name in ("install-server.sh", "install-mac.sh"):
        text = (SCRIPTS / name).read_text(encoding="utf-8")
        live_block = text[text.index('if [ "$LIVE" = 1 ]; then'):]
        live_block = live_block[: live_block.index("\nfi\n")]
        outside = text.replace(live_block, "")
        assert "live_transport" in live_block and "QUANT_LIVE_TRANSPORT" in live_block
        assert "live_transport" not in outside and "QUANT_LIVE_TRANSPORT=1" not in outside
    up = (SCRIPTS / "update.sh").read_text(encoding="utf-8")
    assert "can-update" in up and "trap rollback ERR" in up
    assert [m for m in re.findall(r"step (\w+) running", up)] == [k for k, _ in updates.STEPS]


# ── 서비스 재시작(재부팅 흉내): 유닛의 ExecStart 그대로 ─────────────────────


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _http(port: int, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    raw = json.dumps(body).encode() if body is not None else b""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    try:
        s.connect(("127.0.0.1", port))
        head = (f"{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n"
                f"Content-Type: application/json\r\nContent-Length: {len(raw)}\r\n\r\n")
        s.sendall(head.encode() + raw)
        out = b""
        while chunk := s.recv(65536):
            out += chunk
    finally:
        s.close()
    head_b, _, payload = out.partition(b"\r\n\r\n")
    status = int(head_b.split()[1])
    return status, json.loads(payload or b"{}")


def _start(cmd: list[str], env: dict[str, str], port: int) -> subprocess.Popen[str]:
    p = subprocess.Popen(cmd, cwd=APP, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    for _ in range(150):
        try:
            if _http(port, "GET", "/api/health")[0] == 200:
                return p
        except OSError:
            time.sleep(0.1)
    p.kill()
    raise AssertionError(p.stderr.read() if p.stderr else "no start")


def test_service_restart_runs_without_login(tmp_path: Path) -> None:
    port = _free_port()
    # basetemp가 레포 안이라 HOME(키 파일 자리)은 운영체제 임시 폴더에(레포 안 키 파일은 앱이 거절해요)
    home_dir = tempfile.TemporaryDirectory(prefix="quant-test-home-")
    home, data = Path(home_dir.name), tmp_path / "data"
    unit = install.systemd_unit(APP, data, "quant", port)
    cmd = shlex.split(re.search(r"^ExecStart=(.+)$", unit, re.M).group(1))  # type: ignore[union-attr]
    # 키 파일은 시험 임시 HOME에만 · 실제 전송 열쇠 없음
    env = {k: v for k, v in os.environ.items() if k not in ("QUANT_LIVE_TRANSPORT", "QUANT_TS_NAME")}
    env |= {"HOME": str(home), "MVP_DATA_DIR": str(data), "MVP_PORT": str(port)}

    first = _start(cmd, env, port)
    try:
        st, body = _http(port, "POST", "/api/setup", {"password": "correct horse 9", "password2": "correct horse 9",
                                                     "adult": True, "terms": True})
        assert st == 200, body
        assert _http(port, "GET", "/api/state")[1]["auto"] is True
    finally:
        first.send_signal(signal.SIGTERM)  # 컴퓨터가 꺼진 것처럼
        first.communicate(timeout=30)
    keyfile = home / ".config" / "quant-service" / "keyfile"
    assert keyfile.exists() and keyfile.stat().st_mode & 0o777 == 0o600

    second = _start(cmd, env, port)  # 다시 켬(서비스 자동 시작)
    try:
        state = _http(port, "GET", "/api/state")[1]
        assert state["setup"] is True and state["logged_in"] is False  # 화면은 비밀번호로
        assert state["auto"] is True  # 운용은 로그인 없이 이어져요
        assert state["restarted"] is True
    finally:
        second.send_signal(signal.SIGTERM)
        second.communicate(timeout=30)
    home_dir.cleanup()


def test_install_cli_renders(capsys: pytest.CaptureFixture[str]) -> None:
    assert install.main(["systemd", "--app", "/opt/a", "--data", "/d", "--user", "quant"]) == 0
    assert "ExecStart=/opt/a/.venv/bin/python -m app.serve" in capsys.readouterr().out
    assert install.main(["plist", "--app", "/a", "--data", "/d"]) == 0
    assert "<key>RunAtLoad</key>" in capsys.readouterr().out
    assert sys.executable
    assert date.today()
