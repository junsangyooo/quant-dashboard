"""앱 프로세스 입구(T-51 · R-L5): 127.0.0.1에만 묶고, 같은 데이터 폴더로 두 번째 실행을 막아요.

    .venv/bin/python -m app.serve [--port 8765] [--data <폴더>]

- 묶는 곳은 늘 127.0.0.1이에요. 바깥(휴대폰 · 노트북)은 Tailscale serve가 https로 받아 여기로 넘겨요.
  다른 주소를 달라고 하면 켜지 않아요(공개 인터페이스에 열린 포트 0).
- 한 번만 실행: 데이터 폴더의 `app.lock`을 flock으로 잡아요. 프로세스가 죽으면 운영체제가 풀어 줘요(재부팅 뒤 남은 잠금 없음).
"""

from __future__ import annotations

import argparse
import fcntl
import ipaddress
import os
import sys
from pathlib import Path

from . import settings

LOOPBACK = "127.0.0.1"
LOCK_NAME = "app.lock"


class AlreadyRunning(RuntimeError):
    pass


def acquire_lock(data: Path) -> int:
    """잠금 파일을 잡고 그 fd를 돌려줘요(프로세스가 끝날 때까지 쥐고 있어요). 이미 잡혀 있으면 AlreadyRunning."""
    data.mkdir(parents=True, exist_ok=True)
    fd = os.open(data / LOCK_NAME, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise AlreadyRunning("이미 실행 중이에요 · 같은 컴퓨터에서 두 번 켜지 않아요") from None
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    return fd


def check_host(host: str) -> str:
    """루프백(127.0.0.1)만 받아요."""
    try:
        ok = ipaddress.ip_address(host) == ipaddress.ip_address(LOOPBACK)
    except ValueError:
        ok = False
    if not ok:
        raise SystemExit("127.0.0.1에만 묶어요 · 바깥 접속은 Tailscale serve로 받아요")
    return host


def main(argv: list[str] | None = None) -> None:
    cfg = settings.load()  # MVP_PORT · MVP_DATA_DIR(환경 변수는 settings만 읽어요)
    p = argparse.ArgumentParser(prog="app.serve")
    p.add_argument("--host", default=LOOPBACK)
    p.add_argument("--port", type=int, default=cfg.port)
    p.add_argument("--data", default=cfg.data_dir)
    args = p.parse_args(argv)
    host = check_host(args.host)

    from .main import ROOT, create_app

    data = Path(args.data or ROOT / "data")
    try:
        lock_fd = acquire_lock(data)
    except AlreadyRunning as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(3) from None

    import uvicorn

    app = create_app(data, port=args.port)
    try:
        uvicorn.run(app, host=host, port=args.port, server_header=False, log_level="warning")
    finally:
        os.close(lock_fd)


if __name__ == "__main__":
    main()
