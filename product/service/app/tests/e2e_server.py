"""그림 비교용 서버(시험 전용): 가짜 전송 + 지어낸 일봉으로 켜요. 바깥으로 나가지 않아요.

    MVP_PORT=8799 .venv/bin/python -m tests.e2e_server <데이터 폴더> 8799
"""

from __future__ import annotations

import sys
from datetime import date

import uvicorn

from app.main import create_app
from tests.conftest import FakeBars, make_bars, wave

SYMS = ["005930", "000660", "373220", "005380", "035420"]


def bars() -> FakeBars:
    data = {s: make_bars(wave(1200, 50_000 + 40_000 * k, 6_000 + 1_000 * k, 37 + 7 * k, 0.0004),
                         start=date(2021, 1, 4), volume=2_000_000) for k, s in enumerate(SYMS)}
    data["KOSPI"] = make_bars(wave(1200, 2500, 120, 60, 0.0002), start=date(2021, 1, 4), volume=0)
    return FakeBars(data)


if __name__ == "__main__":
    folder, port = sys.argv[1], int(sys.argv[2])
    app = create_app(folder, bars_source=bars(), scheduler=False, port=port)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
