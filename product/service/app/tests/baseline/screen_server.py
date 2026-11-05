"""화면 기준선용 서버(P1-01c): `tests/e2e_server.py`와 같은 가짜 세계에 **고정 시각 · 복구 코드 씨앗**을 더해 켜요.

    cd product/service/app && .venv/bin/python -m tests.baseline.screen_server <데이터 폴더> <포트> [live]

- 가짜 전송(기본) · 지어낸 일봉(`tests.e2e_server.bars`) · 스케줄러 없음 · 127.0.0.1에만 묶어요.
- 키 파일(0600)은 `QUANT_BASELINE_KEYFILE_DIR`(찍는 스크립트가 주는 임시 HOME · 서버가 끝나면 스크립트가 폴더째 지움) 아래에,
  없으면 임시 폴더를 만들어 두고 끝날 때 지워요. uvicorn은 받은 SIGTERM을 끝에 다시 일으켜 프로세스를 신호로 끝내므로(그러면
  `finally`가 돌지 않아요) SIGTERM 처리기를 미리 빈 것으로 두어 `run()`이 정상으로 돌아오게 해요.
- 켜기 전에 `tests.baseline.clock.freeze_plain()`으로 P1-01b와 같은 자리(서버 `now` · 직접 시계 5곳 · `secrets.choice`)를
  고정하고, 일봉 캐시 판단 시계(`Market.clock`)도 같은 시각으로 둬요. 화면 쪽은 Playwright `page.clock`이 같은 시각이에요.
- `live`를 주면 `tests.e2e_server.seed_live`로 '운용 중' 상태(V2-10 ~ V2-14)를 넣어요.
- 준비 신호는 따로 없어요: 찍는 스크립트(`screens.mjs`)가 `/api/state`가 응답할 때까지 기다려요.
"""

from __future__ import annotations

import os
import shutil
import signal
import sys
import tempfile
from pathlib import Path


def main(argv: list[str]) -> int:
    folder, port = argv[0], int(argv[1])
    seed = len(argv) > 2 and argv[2] == "live"

    from tests.baseline.clock import FIXED_NOW, freeze_plain

    freeze_plain()

    import uvicorn

    from app.app import create_app
    from tests.e2e_server import bars, seed_live

    given = os.environ.get("QUANT_BASELINE_KEYFILE_DIR")
    kf_dir = Path(given) if given else Path(tempfile.mkdtemp(prefix="quant-baseline-kf-"))
    kf_dir.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, lambda *_: None)  # uvicorn이 끝에 다시 일으키는 SIGTERM을 삼켜 finally까지 가게
    try:
        app = create_app(folder, bars_source=bars(), scheduler=False, port=port, keyfile=kf_dir / "keyfile")
        app.state.market.clock = lambda: FIXED_NOW.timestamp()
        if seed:
            seed_live(app.state.db)
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")  # SIGTERM을 받으면 정상으로 돌아와요
    finally:
        shutil.rmtree(kf_dir if not given else kf_dir / "keyfile", ignore_errors=True)  # 준 폴더는 스크립트가 지움
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
