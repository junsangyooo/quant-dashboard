"""견본 일봉(코드로 만든 가짜 시세)으로 백테스트와 모의 체결 숫자를 손으로 맞춰 본다."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from app import strategy as st
from app.connect import Connections
from app.db import DB
from app.engine import FEE, SELL_TAX, Engine, Series, metrics, run_backtest
from app.market import KST, Market
from app.paper import Paper
from app.vault import Vault
from tests.helpers import legacy, new_strategy
from tests.conftest import FakeBars, business_days, make_bars, setup_owner

CASH = 1_000_000.0


def event_body(**over: object) -> dict:  # type: ignore[type-arg]
    body = legacy("event", "돌파")
    body["slots"]["universe"][0]["params"]["symbols"] = ["111111"]
    body["slots"]["signal"] = [{"piece": "ma_cross_up", "params": {"n": 3}}]
    body["slots"]["select"] = [{"piece": "top_n", "params": {"n": 1}}]
    body["slots"]["sell"] = [{"piece": "take_profit", "params": {"pct": 10}}]
    assert st.validate(body) == []
    return body


#            0   1   2   3  4   5   6   7
CLOSES = [10, 10, 10, 9, 13, 13, 15, 15]
OPENS = [10, 10, 10, 9, 13, 12, 15, 14]


def test_event_backtest_numbers_by_hand() -> None:
    bars = make_bars(CLOSES, opens=OPENS)
    days = [b["d"] for b in bars]
    res = run_backtest(event_body(), {"111111": bars}, None, days[0], days[-1], CASH)

    # 4일째(9→13) 종가가 3일 이동평균(10.667)을 아래에서 위로 넘음 → 5일째 시가 12에 매수
    qty = math.floor(CASH / (12 * (1 + FEE)))
    assert qty == 83320
    buy_cost = qty * 12 * FEE
    cash_after_buy = CASH - qty * 12 - buy_cost
    avg = (qty * 12 + buy_cost) / qty
    # 6일째 종가 15 ≥ 평균가 × 1.1 → 7일째 시가 14에 매도
    assert 15 >= avg * 1.1 > 13
    gross = qty * 14
    sell_cost = gross * (FEE + SELL_TAX)
    final = cash_after_buy + gross - sell_cost

    assert [(t["d"], t["side"], t["qty"], t["price"]) for t in res["trades"]] == [
        (days[5], "buy", qty, 12),
        (days[7], "sell", qty, 14),
    ]
    assert res["trades"][0]["reason"] == ["3일 이동평균선 상향 돌파"]
    assert res["trades"][1]["reason"] == ["익절 +10%"]
    assert res["final"] == pytest.approx(final, abs=1e-6)
    assert round(final) == 1_164_215
    assert res["total"] == pytest.approx(final / CASH - 1)
    assert res["trades_count"] == 2 and res["sells"] == 1 and res["win_rate"] == 1.0
    assert res["costs"] == pytest.approx(buy_cost + sell_cost)
    # 5일째 종가 평가: 현금 + 83320주 × 13
    assert res["curve"][5][1] == pytest.approx(cash_after_buy + qty * 13)
    # 고점은 6일째 종가(15) 평가, 7일째 시가 14에 팔아 그만큼 내려온다
    peak = cash_after_buy + qty * 15
    assert res["mdd"] == pytest.approx(final / peak - 1)


def test_stop_loss_and_mdd() -> None:
    closes = [10, 10, 10, 9, 13, 12, 11, 11]
    opens = [10, 10, 10, 9, 13, 12, 11, 10]
    body = event_body()
    body["slots"]["sell"] = [{"piece": "stop_loss", "params": {"pct": 10}}]
    bars = make_bars(closes, opens=opens)
    days = [b["d"] for b in bars]
    res = run_backtest(body, {"111111": bars}, None, days[0], days[-1], CASH)
    qty = math.floor(CASH / (12 * (1 + FEE)))
    # 평균가 ≈ 12.0018, 손절 선 ≈ 10.80: 6일째 종가 11 > 10.80 → 안 팖, 7일째도 11 → 안 팖
    assert [t["side"] for t in res["trades"]] == ["buy"]
    # 7일째 시가 10은 판단에 쓰지 않는다(종가 판단). 평가는 종가 11
    peak = res["curve"][4][1]  # 4일째는 아직 현금
    assert peak == CASH
    low = CASH - qty * 12 - qty * 12 * FEE + qty * 11
    assert res["curve"][-1][1] == pytest.approx(low)
    assert res["mdd"] == pytest.approx(low / CASH - 1)


def test_max_hold_and_cross_not_repeated() -> None:
    closes = [10, 10, 10, 9, 13, 14, 15, 16, 17, 18]
    body = event_body()
    body["slots"]["sell"] = [{"piece": "max_hold", "params": {"n": 2}}]
    bars = make_bars(closes)
    days = [b["d"] for b in bars]
    res = run_backtest(body, {"111111": bars}, None, days[0], days[-1], CASH)
    # 5일째 매수, 2거래일 지난 7일째 종가에 판단 → 8일째 시가 매도. 돌파는 다시 안 일어남
    assert [(t["d"], t["side"]) for t in res["trades"]] == [(days[5], "buy"), (days[8], "sell")]
    assert res["trades"][1]["reason"] == ["최대 보유 2거래일"]


def test_metrics_cagr() -> None:
    m = metrics([("2020-01-01", 100.0), ("2021-01-01", 110.0), ("2022-01-01", 121.0)], 100.0)
    assert m["total"] == pytest.approx(0.21)
    assert m["cagr"] == pytest.approx(0.1, abs=2e-4)
    m = metrics([("2020-01-01", 100.0), ("2020-02-01", 150.0), ("2020-03-01", 75.0)], 100.0)
    assert m["mdd"] == pytest.approx(-0.5)


def test_rank_holds_the_stronger() -> None:
    n = 30
    up = [100 + 2 * i for i in range(n)]
    flat = [100 + (i % 2) for i in range(n)]
    body = legacy("rank", "순위")
    body["slots"]["universe"][0]["params"]["symbols"] = ["111111", "222222"]
    body["slots"]["signal"] = [{"piece": "ma_cross_up", "params": {"n": 5}}]
    body["slots"]["select"][0]["params"]["n"] = 1
    body["slots"]["weight"][1]["params"]["n"] = 5
    assert st.validate(body) == []
    data = {"111111": make_bars(up), "222222": make_bars(flat)}
    days = [b["d"] for b in data["111111"]]
    res = run_backtest(body, data, None, days[5], days[-1], CASH)
    assert {t["sym"] for t in res["trades"]} == {"111111"}
    assert res["trades"][0]["reason"][0] == "상위 1종목 안"
    rows = st.reason_rows(body, res["trades"][0]["reason"])
    assert rows[0]["display"] == "종목 선정 · 상위 1종목 안" and rows[0]["circle"] == "④"


def test_target_equal_weight_split() -> None:
    body = legacy("target", "반반")
    body["slots"]["universe"][0]["params"]["symbols"] = ["111111", "222222"]
    body["slots"]["weight"][1]["params"]["n"] = 20
    assert st.validate(body) == []
    data = {"111111": make_bars([1000] * 5), "222222": make_bars([500] * 5)}
    days = [b["d"] for b in data["111111"]]
    res = run_backtest(body, data, None, days[0], days[-1], CASH)
    buys = {t["sym"]: t["qty"] for t in res["trades"] if t["side"] == "buy"}
    assert buys == {
        "111111": math.floor(500_000 / (1000 * (1 + FEE))),
        "222222": math.floor(500_000 / (500 * (1 + FEE))),
    }


def test_filters_block() -> None:
    body = event_body()
    body["slots"]["filter"] = [{"piece": "min_turnover", "params": {"n": 1000}}]  # 1,000억 원
    bars = make_bars(CLOSES, opens=OPENS, volume=1000)
    days = [b["d"] for b in bars]
    res = run_backtest(body, {"111111": bars}, None, days[0], days[-1], CASH)
    assert res["trades"] == []


def test_rsi_matches_wilder() -> None:
    closes = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28]
    s = Series(make_bars(closes))
    # Wilder 예제(14일). 오른 폭 합 3.34, 내린 폭 합 1.40 → RS = 3.34/1.40
    assert s.rsi(14)[14] == pytest.approx(100 - 100 / (1 + 3.34 / 1.40), abs=1e-9)
    # 하루 더(46.28→46.00, 0.28 하락) 넣으면 Wilder 평활로 이어진다
    s2 = Series(make_bars(closes + [46.00]))
    ag = (3.34 / 14 * 13 + 0) / 14
    al = (1.40 / 14 * 13 + 0.28) / 14
    assert s2.rsi(14)[15] == pytest.approx(100 - 100 / (1 + ag / al), abs=1e-9)


def test_benchmark_line() -> None:
    bars = make_bars(CLOSES, opens=OPENS)
    bench = make_bars([2000, 2000, 2100, 2200, 2000, 2000, 2400, 2500])
    days = [b["d"] for b in bars]
    res = run_backtest(event_body(), {"111111": bars}, bench, days[0], days[-1], CASH)
    assert res["bench"][-1][1] == pytest.approx(CASH * 2500 / 2000)
    assert res["bench_total"] == pytest.approx(0.25)


# ── 모의투자 ─────────────────────────────────────────────────────────────────


class Now:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


def _paper(tmp_path: Path, bars: FakeBars, now: Now) -> tuple[DB, Paper]:
    db = DB(tmp_path / "app.db")
    vault = Vault(db, scrypt_n=2**12)
    clock = {"t": 1e9}
    market = Market(db, bars, clock=lambda: clock["t"])
    conns = Connections(db, vault, lambda: (lambda r: (_ for _ in ()).throw(RuntimeError("no toss"))))
    paper = Paper(db, market, conns, now=now)
    paper._clock = clock  # type: ignore[attr-defined]
    return db, paper


def _version(db: DB, body: dict) -> int:  # type: ignore[type-arg]
    import json

    sid = db.run("INSERT INTO strategies(name,template,source,created_at) VALUES(?,?,?,?)", ("x", body["template"], None, "t"))
    return db.run(
        "INSERT INTO versions(strategy_id,no,body,problems,created_at) VALUES(?,?,?,?,?)",
        (sid, 1, json.dumps(body), len(st.validate(body)), "t"),
    )


def test_paper_judge_then_fill_next_open(tmp_path: Path) -> None:
    # 2025-03-03(월)부터 8거래일: 5번째 날(인덱스 4)에 돌파
    start = date(2025, 3, 3)
    all_bars = make_bars(CLOSES, start=start, opens=OPENS)
    days = [b["d"] for b in all_bars]
    src = FakeBars({"111111.KS": all_bars[:5]})
    now = Now(datetime.fromisoformat(days[4] + "T17:00:00").replace(tzinfo=KST))
    db, paper = _paper(tmp_path, src, now)
    vid = _version(db, event_body())

    started = paper.start(vid, CASH)
    assert started["judged"] == days[4]
    assert [(p["side"], p["sym"], p["reason"]) for p in started["plans"]] == [
        ("buy", "111111", ["3일 이동평균선 상향 돌파"])
    ]
    # 새 일봉이 없으면 아무것도 바뀌지 않는다
    same = paper.judge()
    assert same["new_days"] == 0 and "새 일봉이 아직 없어요" in same["message"]

    # 다음 날 장 마감 뒤: 그날 시가 12에 모의 체결
    src.data["111111.KS"] = all_bars[:6]
    now.t = datetime.fromisoformat(days[5] + "T17:00:00").replace(tzinfo=KST)
    paper._clock["t"] += 3600  # type: ignore[attr-defined]
    res = paper.judge()
    qty = math.floor(CASH / (12 * (1 + FEE)))
    assert res["new_days"] == 1
    assert [(t["d"], t["side"], t["qty"], t["price"]) for t in res["trades"]] == [(days[5], "buy", qty, 12)]
    home = paper.home()
    cash = CASH - qty * 12 - qty * 12 * FEE
    assert home["cash"] == pytest.approx(cash)
    assert home["holdings"][0]["qty"] == qty
    assert home["holdings"][0]["price"] == 13  # 토스 없음 → 야후 마지막 종가
    assert home["price_source"].startswith("야후 종가")
    assert home["total"] == pytest.approx(cash + qty * 13)
    assert [c[0] for c in home["curve"]] == [days[4], days[5]]

    # 이틀 뒤(이틀치 일봉이 한꺼번에): 6일째 종가로 익절 판단 → 7일째 시가 14 매도
    src.data["111111.KS"] = all_bars
    now.t = datetime.fromisoformat(days[7] + "T17:00:00").replace(tzinfo=KST)
    paper._clock["t"] += 3600  # type: ignore[attr-defined]
    res = paper.judge()
    assert res["new_days"] == 2
    assert [(t["d"], t["side"], t["price"]) for t in res["trades"]] == [(days[7], "sell", 14)]
    hist = paper.history()
    assert [(t["side"], t["reason"]) for t in hist["trades"]] == [
        ("sell", ["익절 +10%"]),
        ("buy", ["3일 이동평균선 상향 돌파"]),
    ]
    final = cash + qty * 14 * (1 - FEE - SELL_TAX)
    assert paper.home()["total"] == pytest.approx(final)
    # 백테스트와 같은 숫자
    bt = run_backtest(event_body(), {"111111": all_bars}, None, days[0], days[-1], CASH)
    assert bt["final"] == pytest.approx(final)


def test_paper_ignores_unfinished_today_bar(tmp_path: Path) -> None:
    start = date(2025, 3, 3)
    all_bars = make_bars(CLOSES, start=start, opens=OPENS)
    days = [b["d"] for b in all_bars]
    src = FakeBars({"111111.KS": all_bars[:5]})
    # 5번째 날 오전 11시: 그날 일봉은 아직 덜 됐으니 4번째 날까지로 판단
    now = Now(datetime.fromisoformat(days[4] + "T11:00:00").replace(tzinfo=KST))
    db, paper = _paper(tmp_path, src, now)
    vid = _version(db, event_body())
    assert paper.start(vid, CASH)["judged"] == days[3]


def test_paper_rejects_blank_version(tmp_path: Path) -> None:
    from app.vault import VaultError

    db, paper = _paper(tmp_path, FakeBars(), Now(datetime(2025, 3, 3, 17, tzinfo=KST)))
    vid = _version(db, legacy("event", "x"))
    with pytest.raises(VaultError, match="문제가 있는 버전"):
        paper.start(vid, CASH)


# ── API 흐름 + 저절로 한 번 ─────────────────────────────────────────────────


def _api_body() -> dict:  # type: ignore[type-arg]
    body = legacy("event", "API")
    body["slots"]["universe"][0]["params"]["symbols"] = ["005930", "000660"]
    body["slots"]["signal"] = [{"piece": "ma_cross_up", "params": {"n": 10}}]
    body["slots"]["select"] = [{"piece": "top_n", "params": {"n": 2}}]
    body["slots"]["sell"] = [
        {"piece": "stop_loss", "params": {"pct": 8}},
        {"piece": "ma_break_down", "params": {"n": 10}},
    ]
    return body


def test_backtest_and_paper_api(app_client, fake_bars: FakeBars) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    sid = new_strategy(app_client, "API", "event")
    blank_vid = app_client.get(f"/api/strategies/{sid}").json()["version"]["id"]
    r = app_client.post("/api/backtest", json={"version_id": blank_vid, "start": "2024-02-01", "end": "2025-05-30", "cash": 10_000_000})
    assert r.status_code == 400 and "문제가" in r.json()["error"]
    vid = app_client.post(f"/api/strategies/{sid}/versions", json={"body": _api_body()}).json()["version_id"]
    r = app_client.post("/api/backtest", json={"version_id": vid, "start": "2024-02-01", "end": "2025-05-30", "cash": 10_000_000})
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["trades_count"] > 0 and res["bench_name"] == "코스피" and res["bench"]
    assert all(t["reason"] for t in res["trades"])
    assert res["mdd"] <= 0
    # 일봉은 SQLite에 담겨 다시 받지 않는다
    calls = len(fake_bars.calls)
    app_client.post("/api/backtest", json={"version_id": vid, "start": "2024-02-01", "end": "2025-05-30", "cash": 10_000_000})
    assert len(fake_bars.calls) == calls
    # 모의투자
    r = app_client.post("/api/paper/start", json={"version_id": vid, "cash": 10_000_000})
    assert r.status_code == 200, r.text
    home = app_client.get("/api/home").json()
    assert home["running"] and home["total"] == 10_000_000
    assert app_client.post("/api/paper/judge").json()["new_days"] == 0
    # 저절로 한 번: 월요일 17:00(16:30 지남) → 한 번만 돈다
    tick = app_client.app_ref.state.auto_tick
    assert tick() == "ran"
    assert tick() is None
    assert app_client.get("/api/home").json()["auto"]["last"] == "2025-06-02"
    hist = app_client.get("/api/history").json()
    assert hist["runs"][0]["status"] == "running"


def test_market_down_says_so(app_client, fake_bars: FakeBars) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    fake_bars.down = True
    sid = new_strategy(app_client, "API", "event")
    vid = app_client.post(f"/api/strategies/{sid}/versions", json={"body": _api_body()}).json()["version_id"]
    r = app_client.post("/api/backtest", json={"version_id": vid, "start": "2024-02-01", "end": "2025-05-30", "cash": 10_000_000})
    assert r.status_code == 502 and r.json()["error"].startswith("시세를 받지 못했어요")


def test_engine_state_roundtrip() -> None:
    bars = make_bars(CLOSES, opens=OPENS)
    days = [b["d"] for b in bars]
    series = {"111111": Series(bars)}
    eng = Engine(event_body(), series, CASH)
    for d in days[:6]:
        eng.fill(d)
        eng.judge(d)
    import json

    again = Engine(event_body(), series, CASH, json.loads(json.dumps(eng.state)))
    assert again.equity(days[5]) == pytest.approx(eng.equity(days[5]))
    _ = business_days(date(2025, 1, 1), 3)
    _ = timedelta
