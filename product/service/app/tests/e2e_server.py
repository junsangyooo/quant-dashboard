"""그림 비교용 서버(시험 전용): 가짜 전송 + 지어낸 일봉으로 켜요. 바깥으로 나가지 않아요.

    MVP_PORT=8799 .venv/bin/python -m tests.e2e_server <데이터 폴더> 8799
"""

from __future__ import annotations

import sys
from pathlib import Path
import tempfile
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


NAMES = {"005930": "삼성전자", "000660": "SK하이닉스", "373220": "LG에너지솔루션", "005380": "현대차", "035420": "NAVER"}


def seed_live(db) -> None:  # type: ignore[no-untyped-def]
    """그림 비교 '운용 중' 상태(V2-10 ~ V2-14): 지어낸 운용 · 보유 · 계획 · 체결 · 할 일을 바로 넣어요(가짜 · 시험 전용)."""
    import json

    from tests.test_live import body

    for sym, name in NAMES.items():
        db.run("INSERT OR IGNORE INTO stock_info(symbol, name, market) VALUES(?,?,?)", (sym, name, "KOSPI"))
    sid = db.run("INSERT INTO strategies(name,template,source,created_at) VALUES(?,?,?,?)", ("대형주 돌파", "event", None, "t"))
    vid = db.run("INSERT INTO versions(strategy_id,no,body,problems,created_at,format) VALUES(?,?,?,?,?,?)",
                 (sid, 3, json.dumps(body(syms=SYMS, top=3)), 0, "t", "blocks"))
    db.run("INSERT INTO backtest_runs(version_id,ran_at,start_d,end_d,cash) VALUES(?,?,?,?,?)",
           (vid, "t", "2021-01-04", "2025-08-01", 10_000_000))
    rid = db.run("INSERT INTO runs(strategy_id,version_id,status,amount,settings,account_tail,started_at) "
                 "VALUES(?,?,?,?,?,?,?)", (sid, vid, "running", 10_000_000, "{}", "4821", "2025-07-01T21:00:00+09:00"))
    pos = {"000660": {"qty": 9, "avg": 198_030.0, "entry_d": "2025-07-28", "peak": 214_500.0},
           "005380": {"qty": 7, "avg": 241_536.0, "entry_d": "2025-07-06", "peak": 241_536.0}}
    plans = [{"sym": "373220", "side": "buy", "value": 1_977_600, "close": 112_400.0, "rank": 1,
              "reason": ["② 20일 이동평균선 상향 돌파", "④ 신호 강도 1위"]},
             {"sym": "035420", "side": "buy", "value": 1_910_000, "close": 347_300.0, "rank": 2,
              "reason": ["② 20일 이동평균선 상향 돌파", "④ 신호 강도 2위"]}]
    st = {"cash": 4_699_116.0, "pos": pos, "plans": [], "day_no": 20, "sold": {}, "manual": ["005930"],
          "next": {"judged": "2025-08-01", "for_d": "2025-08-04", "plans": plans}, "sell_fail": {}}
    db.run("INSERT INTO live_state(run_id,state,updated_at) VALUES(?,?,?)", (rid, json.dumps(st), "t"))
    eq = 10_000_000.0
    for i in range(20):
        d = f"2025-07-{i + 7:02d}"
        eq += (i % 5 - 1.5) * 30_000
        db.run("INSERT OR IGNORE INTO run_equity(run_id,d,equity,cash) VALUES(?,?,?,?)", (rid, d, eq, 4_699_116.0))
    db.set_meta(f"live.{rid}.last_check", "2025-08-01")
    for k, (d, sym, side, qty, price) in enumerate([("2025-07-28", "000660", "buy", 9, 198_000),
                                                    ("2025-07-06", "005380", "buy", 7, 241_500)]):
        oid = db.run("INSERT INTO orders(run_id,d,symbol,side,round,client_order_id,kind,qty,price,status,reason,"
                     "created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (rid, d, sym, side, 1, f"seed-{k}", "open_buy", qty, price, "filled",
                      json.dumps({"why": ["④ 신호 강도 1위"]}, ensure_ascii=False), "t"))
        db.run("INSERT INTO fills(order_id,qty,price,commission,tax,filled_at) VALUES(?,?,?,?,?,?)",
               (oid, qty, price, 0, 0, d + "T09:00:00+09:00"))
    db.run("INSERT INTO todos(run_id,kind,severity,symbol,title,status,created_at,data) VALUES(?,?,?,?,?,?,?,?)",
           (rid, "unknown", "red", "005380", "결과 모르는 주문 [현대차]", "open", "2025-08-01T09:05:00+09:00",
            json.dumps({"order": 1})))


if __name__ == "__main__":
    folder, port = sys.argv[1], int(sys.argv[2])
    # 키 파일은 시험 임시 폴더에만(데이터 폴더 밖 · T-50)
    app = create_app(folder, bars_source=bars(), scheduler=False, port=port,
                     keyfile=Path(tempfile.mkdtemp(prefix="quant-e2e-kf-")) / "keyfile")
    if len(sys.argv) > 3 and sys.argv[3] == "live":
        seed_live(app.state.db)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
