"""엔진 v2(TASKS T-23): ENGINE-RULES 3절 · 4절 · 5절 R-X4 · 9절 · R-O2 · R-O7의 시험 예.

시험 이름의 번호가 규칙 번호예요. 일봉은 시험마다 지어낸 값이에요.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pytest

from app import engine as en
from app import fundamentals as fu
from app.blocks import new_block, new_row
from app.copytext import convert_v1
from app.engine import Engine, Judge, MarketData, RowResult, block_result, run_backtest
from app.indicators import Series

START = date(2026, 1, 5)  # 월요일


def days(n: int, start: date = START) -> list[str]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def bars(closes: list[float], *, opens: list[float] | None = None, highs: list[float] | None = None,
         lows: list[float] | None = None, vol: float = 1_000_000, start: date = START) -> list[dict[str, Any]]:
    ds = days(len(closes), start)
    out = []
    for k, (d, c) in enumerate(zip(ds, closes, strict=True)):
        o = opens[k] if opens else c
        out.append({"d": d, "o": o, "h": highs[k] if highs else max(o, c), "l": lows[k] if lows else min(o, c),
                    "c": c, "v": vol})
    return out


def R(item: str, op: str | None = None, value: Any = None, exec_: str | None = None, **params: Any) -> dict:  # type: ignore[type-arg]
    return new_row(item, op, value=value, params=params or None, exec_=exec_)


def B(bid: str, stage: str, rows: list[dict[str, Any]] | None = None, match: str | None = None) -> dict:  # type: ignore[type-arg]
    b = new_block(bid, stage)
    if rows is not None:
        b["rows"] = rows
    if match:
        b["match"] = match
    return b


def strategy(signal: list[dict[str, Any]] | None, sell: list[dict[str, Any]] | None, *, syms: list[str],
             top: int = 1, filt: list[dict[str, Any]] | None = None, cooldown: int = 1, weight: list | None = None,  # type: ignore[type-arg]
             sell_match: str = "any", sort: dict[str, Any] | None = None) -> dict[str, Any]:
    blocks = [B("u", "universe", [R("manual_list", value=syms)])]
    edges = []
    prev = "u"
    if signal is not None:
        blocks.append(B("s", "signal", signal))
        edges.append((prev, "s"))
        prev = "s"
    if filt is not None:
        blocks.append(B("f", "filter", filt))
        edges.append((prev, "f"))
        prev = "f"
    blocks.append(B("k", "select", [R("top_n", value=top, **(sort or {}))]))
    edges += [(prev, "k"), ("k", "b")]
    buy = B("b", "buy")
    buy["rows"][0]["value"] = cooldown
    blocks.append(buy)
    if sell is not None:
        blocks.append(B("x", "sell", sell, match=sell_match))
        edges.append(("b", "x"))
    w = B("w", "weight")
    if weight:
        w["rows"] += weight
    blocks.append(w)
    edges.append(("w", "b"))
    return {"name": "시험", "graph": {"blocks": blocks, "edges": [{"from": a, "to": b} for a, b in edges]}}


def judge_of(data: MarketData, rebalance: bool = False) -> Judge:
    return Judge(data, rebalance)


def one(closes: list[float], **kw: Any) -> MarketData:
    return MarketData(series={"111111": Series(bars(closes, **kw))})


# ── 3. 조건 줄 판정 ──────────────────────────────────────────────────────────


def test_R_J1_no_value_is_false_and_noted() -> None:
    data = one([10000] * 5)
    data.fundamentals = lambda sym, d: {"per": None}  # 적자라 PER 없음
    body = strategy([R("ma", "cross_up", n=2)], [R("max_hold", value=5)], syms=["111111"],
                    filt=[R("per", "lte", 15)])
    eng = Engine(body, data, 10_000_000)
    ok, _, _, _ = eng._entry("111111", days(5)[-1], {})
    assert ok is False
    res = judge_of(data).row(R("per", "lte", 15), "111111", days(5)[-1])
    assert res.ok is False and res.missing is True
    data2 = one([10000, 10000, 12000])
    data2.fundamentals = lambda sym, d: {"per": None}
    body2 = strategy(None, [R("max_hold", value=5)], syms=["111111"], filt=[R("per", "lte", 15)])
    e2 = Engine(body2, data2, 1e7)
    e2._entry("111111", days(3)[-1], {})
    assert e2.notes["111111"] == ["③ PER 값 없음"]


def test_R_J2_cross_equal_is_below() -> None:
    j = judge_of(one([10, 10, 12]))
    assert j.row(R("ma", "cross_up", n=2), "111111", days(3)[2]).ok is True  # 어제 종가 = 선 · 오늘 > 선
    j = judge_of(one([10, 10, 10]))
    assert j.row(R("ma", "cross_up", n=2), "111111", days(3)[2]).ok is False  # 오늘 종가 = 선
    j = judge_of(one([12, 10, 8]))
    assert j.row(R("ma", "cross_down", n=2), "111111", days(3)[2]).ok is False  # 어제 이미 아래
    j = judge_of(one([10, 10, 8]))
    assert j.row(R("ma", "cross_down", n=2), "111111", days(3)[2]).ok is True


def test_R_J3_investor_uses_yesterday() -> None:
    ds = days(3)
    data = one([10000] * 3)
    data.investor = {"111111": [{"d": ds[1], "foreign": 100.0}, {"d": ds[2], "foreign": 9_999_999.0}]}
    res = judge_of(data).row(R("net_buy", "gte", 1000, who="foreign", n=1, unit="shares"), "111111", ds[2])
    assert res.ok is False and res.value == 100.0  # 11/2 판단에 11/2 값을 쓰지 않아요


def test_R_J4_held_is_not_a_candidate() -> None:
    closes = [100, 100, 110, 100, 100, 112]
    data = one(closes)
    body = strategy([R("ma", "cross_up", n=2)], [R("max_hold", value=50)], syms=["111111"], top=2)
    eng = Engine(body, data, 1e7)
    ds = days(6)
    for d in ds[:3]:
        eng.fill(d)
        eng.judge(d)
    eng.fill(ds[3])
    assert "111111" in eng.pos
    for d in ds[3:]:
        eng.judge(d) if d == ds[3] else (eng.fill(d), eng.judge(d))
    assert [p for p in eng.plans if p["side"] == "buy"] == []


def _cooldown_run(n: int) -> list[str]:
    # 신호는 늘 맞고(주가 1원 이상), 최대 보유 1거래일로 팔아요: 0일 확인 → 1일 매수 → 2일 확인 매도 → 3일 매도
    data = MarketData(series={"111111": Series(bars([100] * 8))})
    body = strategy([R("price", "gte", 1)], [R("max_hold", value=1)], syms=["111111"], cooldown=n)
    res = run_backtest(body, data, None, days(8)[0], days(8)[-1], 1e7, check=False)
    return [f"{t['d']} {t['side']}" for t in res["trades"]]


def test_R_J5_cooldown_counts_from_sell_day() -> None:
    ds = days(8)
    # n=0: 판 날(3일) 확인부터 후보 → 4일 매수
    assert _cooldown_run(0)[:3] == [f"{ds[1]} buy", f"{ds[3]} sell", f"{ds[4]} buy"]
    # n=1: 판 날(그날 포함) 1거래일의 확인에서 제외 → 4일 확인부터 후보 → 5일 매수
    assert _cooldown_run(1)[:3] == [f"{ds[1]} buy", f"{ds[3]} sell", f"{ds[5]} buy"]


def test_R_J6_ties() -> None:
    ds = days(3)
    flat = [10, 10, 12]
    data = MarketData(series={"222222": Series(bars(flat, vol=10)), "111111": Series(bars(flat, vol=1000))})
    v3 = strategy([R("ma", "cross_up", n=2)], [R("max_hold", value=5)], syms=["222222", "111111"])
    eng = Engine(v3, data, 1e7)
    eng.judge(ds[2])
    assert [p["sym"] for p in eng.plans] == ["111111"]  # 강도 같음 → 거래대금 큰 쪽
    v1 = convert_v1({"name": "v1", "template": "event", "slots": {
        "universe": [{"piece": "manual_list", "params": {"symbols": ["222222", "111111"]}}],
        "signal": [{"piece": "ma_cross_up", "params": {"n": 2}}], "filter": [],
        "select": [{"piece": "top_n", "params": {"n": 1}}], "buy": [{"piece": "next_open", "params": {}}],
        "sell": [{"piece": "max_hold", "params": {"n": 5}}], "weight": [{"piece": "equal", "params": {}}]}})
    eng = Engine(v1, data, 1e7)
    eng.judge(ds[2])
    assert [p["sym"] for p in eng.plans] == ["222222"]  # v1: 먼저 적은 종목 먼저


def test_R_J7_zero_shares() -> None:
    data = MarketData(series={"111111": Series(bars([60000, 60000]))})
    eng = Engine(strategy([R("ma", "above", n=1)], [R("max_hold", value=5)], syms=["111111"]), data, 50_000)
    eng.state["plans"] = [{"sym": "111111", "side": "buy", "value": 50_000, "reason": [], "judged": days(2)[0]}]
    assert eng.fill(days(2)[1]) == []
    assert eng.skipped[0]["why"] == "매수 안 함 · 1주도 못 사요"


def test_R_J8_stop_first_when_both_touch() -> None:
    ds = days(3)
    data = MarketData(series={"111111": Series(bars([10000, 10000, 10000], opens=[10000, 10000, 10000],
                                                    highs=[10000, 10000, 11600], lows=[10000, 10000, 9200]))})
    body = strategy([R("ma", "above", n=1)], [R("stop_loss", value=7), R("take_profit", value=15)], syms=["111111"])
    eng = Engine(body, data, 1e7)
    eng.state["pos"] = {"111111": {"qty": 10, "avg": 10000.0, "entry_d": ds[0], "peak": 10000.0}}
    trades = eng.fill(ds[2])
    assert [(t["side"], t["price"], t["kind"]) for t in trades] == [("sell", 9300.0, "protect")]


def test_R_J9_disclosure_from_next_trading_day() -> None:
    ds = days(3)
    data = one([100, 100, 100])
    data.disclosures = lambda sym, d: [{"kind": "buyback", "usable_from": ds[2]}]  # ds[1] 접수 → ds[2]부터
    row = R("disclosure", "within_days", 5, kind="buyback")
    assert judge_of(data).row(row, "111111", ds[1]).ok is False
    assert judge_of(data).row(row, "111111", ds[2]).ok is True


def test_R_J10_locked_and_start_date() -> None:
    body = strategy([R("ma", "cross_up", n=2)], [R("max_hold", value=5)], syms=["111111"],
                    filt=[R("per", "lte", 15)])
    data = one([100] * 5)
    data.dart = False
    with pytest.raises(en.BacktestError, match="DART를 연결해야"):
        run_backtest(body, data, None, "2026-01-05", "2026-01-09", 1e7)
    data.dart = True
    with pytest.raises(en.BacktestError) as e:
        run_backtest(body, data, None, "2015-01-02", "2026-01-09", 1e7)
    assert e.value.message == "이 전략은 2016-04-01부터 볼 수 있어요 · DART 재무가 2015년 보고서부터예요"
    # '실전에서만 적용' 줄은 백테스트에 반영하지 않아요
    data.info = {"111111": {"warnings": ["INVESTMENT_WARNING"]}}
    assert judge_of(data).row(R("exclude_warning"), "111111", days(5)[0]).ok is True
    data.live = True
    assert judge_of(data).row(R("exclude_warning"), "111111", days(5)[0]).ok is False


# ── 4. 매매 방식 · 강도 · 정렬 · 목표 금액 ───────────────────────────────────


def test_R_M2_cross_means_differ_by_mode() -> None:
    data = one([10, 10, 12, 13])
    row = R("ma", "cross_up", n=2)
    ds = days(4)
    event = [judge_of(data, False).row(row, "111111", d).ok for d in ds]
    reb = [judge_of(data, True).row(row, "111111", d).ok for d in ds]
    assert event == [False, False, True, False] and reb == [False, False, True, True]


@pytest.mark.parametrize(
    ("closes", "highs", "lows", "row", "want"),
    [
        ([9700, 10300], None, None, R("ma", "cross_up", n=2), 0.03),  # 종가 10,300 · 선 10,000
        ([10300, 9700], None, None, R("ma", "cross_down", n=2), 0.03),
        ([9700, 10300], None, None, R("ma", "above", n=2), 0.03),
        ([10000, 10500], [10000, 10500], None, R("high_n", "cross_up", n=1), 0.05),
        ([10000, 9500], None, [10000, 9500], R("low_n", "cross_down", n=1), 0.05),
        ([100, 118], None, None, R("return_n", "gte", 10, n=1), 0.08),  # 18% · 기준 10%
        ([9800, 9800, 10200], None, None, R("ma_cross", "cross_up", short=1, long=2), 0.02),
        ([10200, 10200, 9800], None, None, R("ma_cross", "cross_down", short=1, long=2), 0.02),
    ],
)
def test_R_M3_strength_formulas(closes, highs, lows, row, want) -> None:  # type: ignore[no-untyped-def]
    data = MarketData(series={"111111": Series(bars(closes, highs=highs, lows=lows))})
    res = judge_of(data, True).row(row, "111111", days(len(closes))[-1])
    assert res.ok and res.strength == pytest.approx(want)


def test_R_M3_rsi_strength_and_no_strength_rows() -> None:
    closes = [100, 99, 98, 97, 96, 97, 95, 94, 93, 94, 92, 91, 90, 91, 89, 88, 87]
    data = one(closes)
    d = days(len(closes))[-1]
    r = Series(bars(closes)).rsi(14)[-1]
    assert r is not None and r < 30
    res = judge_of(data).row(R("rsi", "lt", 30, period=14), "111111", d)
    assert res.ok and res.strength == pytest.approx((30 - r) / 30)  # (기준 − RSI) ÷ 기준
    assert judge_of(data).row(R("rsi", "gte", 10, period=14), "111111", d).strength is None  # RSI 이상 · 강도 없음
    assert judge_of(data).row(R("turnover", "gte", 0.001), "111111", d).strength is None
    assert judge_of(data).row(R("price", "gte", 1), "111111", d).strength is None


def test_R_M4_M5_block_strength() -> None:
    blk = B("s", "signal", [R("ma", "cross_up", n=2), R("turnover", "gte", 1)])
    assert block_result(blk, [RowResult(True, 0.03), RowResult(True, None)]) == (True, 0.03)
    allb = B("s", "signal", [R("ma", "cross_up", n=2), R("rsi", "lt", 30, period=14)])
    ok, s = block_result(allb, [RowResult(True, 0.02), RowResult(True, 0.10)])
    assert ok and s == pytest.approx(0.06)
    assert block_result(B("s", "signal", [R("turnover", "gte", 1)]), [RowResult(True, None)]) == (True, None)
    anyb = {**allb, "match": "any"}
    assert block_result(anyb, [RowResult(True, 0.02), RowResult(False, 0.10)]) == (True, 0.02)


def test_R_M6_single_row_equals_v1_value() -> None:
    data = one([9700, 10300])
    body = strategy([R("ma", "cross_up", n=2)], [R("max_hold", value=5)], syms=["111111"])
    eng = Engine(body, data, 1e7)
    eng.judge_rows.rebalance = True
    ok, strength, reasons, _ = eng._entry("111111", days(2)[-1], {})
    assert ok and strength == pytest.approx(10300 / 10000 - 1)
    assert reasons == ["② 2일 이동평균선 상향 돌파"]


def test_R_M7_no_value_sorts_last() -> None:
    ds = days(2)
    data = MarketData(series={s: Series(bars([100, 100])) for s in ("111111", "222222", "333333")})
    per = {"111111": 12.0, "222222": None, "333333": 8.0}
    data.fundamentals = lambda sym, d: {"per": per[sym]}
    body = strategy(None, [R("max_hold", value=5)], syms=["111111", "222222", "333333"], top=3,
                    sort={"by": "per", "order": "asc"}, weight=[R("rebalance_every", value=1, how="rank")])
    body["graph"]["blocks"] = [b for b in body["graph"]["blocks"] if b["stage"] != "sell"]
    body["graph"]["edges"] = [e for e in body["graph"]["edges"] if e["to"] != "x"]
    eng = Engine(body, data, 1e7)
    eng.judge(ds[0])
    assert [p["sym"] for p in eng.plans] == ["333333", "111111", "222222"]  # 적자(값 없음)는 맨 뒤


def test_R_M9_event_target_amount() -> None:
    ds = days(2)
    syms = ["111111", "222222", "333333", "444444", "555555", "666666", "777777"]
    data = MarketData(series={s: Series(bars([100, 110])) for s in syms})
    body = strategy([R("ma", "cross_up", n=1)], [R("max_hold", value=1)], syms=syms, top=5)
    body["graph"]["blocks"][1]["rows"] = [R("price", "gte", 1)]  # 모두 후보
    eng = Engine(body, data, 0)
    eng.judge_rows.rebalance = True
    eng.state["cash"] = 10_000_000 - 3 * 110 * 1000
    eng.state["pos"] = {s: {"qty": 1000, "avg": 100.0, "entry_d": ds[0]} for s in syms[:3]}
    eng.judge(ds[1])
    sells = [p for p in eng.plans if p["side"] == "sell"]
    buys = [p for p in eng.plans if p["side"] == "buy"]
    assert len(sells) == 3  # 최대 보유 1거래일 → 모두 매도 예정
    eng2 = Engine(body, data, 0)
    eng2.state["cash"] = 10_000_000 - 3 * 110 * 1000
    eng2.state["pos"] = {s: {"qty": 1000, "avg": 100.0, "entry_d": ds[1]} for s in syms[:3]}
    eng2.state["plans"] = [{"sym": syms[0], "side": "sell", "qty": 1000, "reason": [], "judged": ds[0]}]
    eng2.judge(ds[1])
    buys = [p for p in eng2.plans if p["side"] == "buy"]
    assert len(buys) == 2  # n 5 − (보유 3) = 빈자리 2(매도 계획이 걸린 종목은 아직 보유)
    assert all(p["value"] == pytest.approx(10_000_000 / 5) for p in buys)  # E ÷ n = 200만


def test_R_M10_rebalance_days() -> None:
    data = one([100] * 45)
    body = strategy([R("price", "gte", 1)], None, syms=["111111"], weight=[R("rebalance_every", value=20, how="rank")])
    eng = Engine(body, data, 1e7)
    rebal = []
    for k, d in enumerate(days(45)):
        before = eng.state["day_no"]
        eng.fill(d)
        eng.judge(d)
        if before % 20 == 0:
            rebal.append(k + 1)
    assert rebal == [1, 21, 41]


def test_R_M11_target_weight() -> None:
    syms = ["111111", "222222", "333333", "444444"]
    data = MarketData(series={s: Series(bars([100, 100])) for s in syms})
    body = strategy(None, None, syms=syms, weight=[R("rebalance_every", value=5, how="target")])
    body["graph"]["blocks"] = [b for b in body["graph"]["blocks"] if b["stage"] != "select"]
    body["graph"]["edges"] = [{"from": "u", "to": "b"}, {"from": "w", "to": "b"}]
    eng = Engine(body, data, 10_000_000)
    eng.judge(days(2)[0])
    assert [round(p["value"]) for p in eng.plans] == [2_500_000] * 4


# ── 5. 실행 방식 계산 (R-X4) ─────────────────────────────────────────────────


def test_R_X4_intraday_touch_and_gap() -> None:
    ds = days(3)
    body = strategy([R("ma", "above", n=1)], [R("stop_loss", value=7)], syms=["111111"])
    # 저가가 감시가에 닿음 → 감시가 9,300
    d1 = MarketData(series={"111111": Series(bars([10000] * 3, lows=[10000, 10000, 9200]))})
    e = Engine(body, d1, 1e7)
    e.state["pos"] = {"111111": {"qty": 10, "avg": 10000.0, "entry_d": ds[0], "peak": 10000.0}}
    assert [t["price"] for t in e.fill(ds[2])] == [9300.0]
    # 갭 하락: 시가 < 감시가 → 시가
    d2 = MarketData(series={"111111": Series(bars([10000, 10000, 8800], opens=[10000, 10000, 8900]))})
    e = Engine(body, d2, 1e7)
    e.state["pos"] = {"111111": {"qty": 10, "avg": 10000.0, "entry_d": ds[0], "peak": 10000.0}}
    assert [t["price"] for t in e.fill(ds[2])] == [8900.0]
    # 종가 확인 줄은 장중에 팔지 않아요 → 종가로 판단해 다음 시가
    body_close = strategy([R("ma", "above", n=1)], [R("stop_loss", value=7, exec_="close")], syms=["111111"])
    e = Engine(body_close, d1, 1e7)
    e.state["pos"] = {"111111": {"qty": 10, "avg": 10000.0, "entry_d": ds[0], "peak": 10000.0}}
    assert e.fill(ds[2]) == []


def test_trailing_peak_is_until_yesterday() -> None:
    ds = days(3)
    body = strategy([R("ma", "above", n=1)], [R("trailing_stop", value=10)], syms=["111111"])
    data = MarketData(series={"111111": Series(bars([10000, 12000, 10500], opens=[10000, 12000, 12000],
                                                    highs=[10000, 12000, 13000], lows=[10000, 12000, 10700]))})
    e = Engine(body, data, 1e7)
    e.state["pos"] = {"111111": {"qty": 10, "avg": 10000.0, "entry_d": ds[0], "peak": 10000.0}}
    e.fill(ds[1])
    assert e.pos["111111"]["peak"] == 12000
    trades = e.fill(ds[2])  # 최고가 12,000(전날까지) × 0.9 = 10,800 · 오늘 고가 13,000은 안 봐요
    assert [t["price"] for t in trades] == [10800.0]


# ── 9. 백테스트 적용 규칙 · R-O2 · R-O7 ─────────────────────────────────────


def test_R_B1_costs_and_avg() -> None:
    ds = days(2)
    data = MarketData(series={"111111": Series(bars([10000, 11500], opens=[10000, 11500]))})
    e = Engine(strategy([R("ma", "above", n=1)], [R("max_hold", value=5)], syms=["111111"]), data, 1e7)
    e.state["plans"] = [{"sym": "111111", "side": "buy", "value": 100 * 11500 * 1.00015 + 1, "reason": [],
                         "judged": ds[0], "close": 10000.0}]
    t = e.fill(ds[1])[0]
    assert (t["qty"], t["price"]) == (100, 11500.0)  # 시가 +15% 갭에도 시가에 체결
    e2 = Engine(strategy([R("ma", "above", n=1)], [R("max_hold", value=5)], syms=["111111"]),
                MarketData(series={"111111": Series(bars([10000, 10000]))}), 1e7)
    e2.state["plans"] = [{"sym": "111111", "side": "buy", "value": 100 * 10000 * 1.00015 + 1, "reason": [],
                          "judged": ds[0]}]
    t2 = e2.fill(ds[1])[0]
    assert t2["qty"] == 100 and t2["cost"] == pytest.approx(150) and e2.pos["111111"]["avg"] == pytest.approx(10001.5)
    # 매도 세금 0.18% + 수수료 0.015%
    e2.state["plans"] = [{"sym": "111111", "side": "sell", "qty": 100, "reason": [], "judged": ds[1]}]
    s = e2.fill(ds[1])[0]
    assert s["cost"] == pytest.approx(100 * 10000 * 0.00195)


def test_R_B2_bench_is_kospi() -> None:
    data = MarketData(series={"111111": Series(bars([100] * 5))})
    res = run_backtest(strategy([R("ma", "cross_up", n=2)], [R("max_hold", value=5)], syms=["111111"]), data,
                       bars([2500, 2525, 2550, 2575, 2600]), days(5)[0], days(5)[-1], 1e7, check=False)
    assert res["bench_curve"][-1][1] == pytest.approx(1e7 * 2600 / 2500)


def test_R_O2_sale_money_buys_from_next_day() -> None:
    """같은 날 매도 → 그 돈으로 같은 날 매수 0(다음 거래일 시가로 넘겨요)."""
    ds = days(3)
    data = MarketData(series={"111111": Series(bars([100, 100, 100])), "222222": Series(bars([50, 50, 60]))})
    e = Engine(strategy([R("ma", "above", n=1)], [R("max_hold", value=5)], syms=["111111", "222222"]), data, 0)
    e.state["pos"] = {"111111": {"qty": 1000, "avg": 100.0, "entry_d": ds[0]}}
    e.state["plans"] = [{"sym": "111111", "side": "sell", "qty": 1000, "reason": [], "judged": ds[0]},
                        {"sym": "222222", "side": "buy", "value": 90_000, "reason": [], "judged": ds[0]}]
    trades = e.fill(ds[1])
    assert [t["side"] for t in trades] == ["sell"]  # 같은 날 매수 0
    assert e.plans[0]["sym"] == "222222" and e.plans[0]["deferred"] is True
    trades = e.fill(ds[2])
    assert [(t["d"], t["side"], t["sym"]) for t in trades] == [(ds[2], "buy", "222222")]


def test_R_O7_live_note() -> None:
    ds = days(3)
    data = MarketData(series={"111111": Series(bars([10000, 11200, 11200], opens=[10000, 11200, 11200])),
                              "222222": Series(bars([10000, 8800, 8800], opens=[10000, 8800, 8800]))})
    e = Engine(strategy([R("ma", "above", n=1)], [R("max_hold", value=5)], syms=["111111", "222222"]), data, 1e7)
    e.state["pos"] = {"222222": {"qty": 10, "avg": 10000.0, "entry_d": ds[0]}}
    e.state["plans"] = [
        {"sym": "222222", "side": "sell", "qty": 10, "reason": [], "judged": ds[0], "kind": "protect",
         "close": 10000.0},
        {"sym": "111111", "side": "buy", "value": 100_000, "reason": [], "judged": ds[0], "close": 10000.0},
    ]
    e.fill(ds[1])
    assert e.live_counts == {"no_buy": 1, "no_sell": 0}  # 갭 +12% 매수 1 · 갭 −12% 손절은 세지 않아요
    e.state["pos"] = {"222222": {"qty": 10, "avg": 10000.0, "entry_d": ds[0]}}
    e.state["plans"] = [{"sym": "222222", "side": "sell", "qty": 10, "reason": [], "judged": ds[1], "kind": "normal",
                         "close": 10000.0}]
    e.fill(ds[2])
    assert e.live_counts["no_sell"] == 1
    assert en.live_note(e.live_counts) == ("시가가 종가보다 10% 넘게 높아 실전에서 안 샀을 매수 1회 · 10% 넘게 낮아 안 "
                                           "팔렸을 매도 1회예요 · 손절은 가격 하한 없이 팔아요")


def test_sell_kind_protect_when_path_has_stop() -> None:
    """R-O4: '모두' 경로 [손절 + 최대 보유] 종가 확인 매도 → 보호 매도."""
    ds = days(3)
    data = MarketData(series={"111111": Series(bars([10000, 9000, 9000]))})
    body = strategy([R("ma", "above", n=1)], [R("stop_loss", value=7), R("max_hold", value=1)], syms=["111111"],
                    sell_match="all")
    e = Engine(body, data, 1e7)
    e.state["pos"] = {"111111": {"qty": 10, "avg": 10000.0, "entry_d": ds[0]}}
    e.judge(ds[1])
    assert [(p["side"], p["kind"]) for p in e.plans] == [("sell", "protect")]


# ── 수정 계수 주식 수 · 생존 편향 줄 ───────────────────────────────────────


def test_market_cap_with_adjust_factor() -> None:
    # 1:5 분할 전 날: 수정 종가 10,000(수정 전 50,000) · 주식 수 1,000만 → 5,000억 원
    assert fu.market_cap(10_000, 10_000_000, factor=5.0) == pytest.approx(5000)
    rows = [{"account": a, "year": 2025, "reprt": r, "amount": v} for a, r, v in [
        ("당기순이익", "11013", 10e9), ("당기순이익", "11012", 10e9), ("당기순이익", "11014", 10e9),
        ("당기순이익", "11011", 50e9), ("자본총계", "11011", 400e9), ("매출액", "11013", 100e9),
        ("매출액", "11012", 100e9), ("매출액", "11014", 100e9), ("매출액", "11011", 500e9)]]
    v = fu.values(rows, 10_000, 10_000_000, factor=5.0)
    assert v["per"] == pytest.approx(500e9 / 50e9)  # 시가총액 5,000억 ÷ TTM 순이익 500억(4분기 = 50 − 30 = 20)
    assert v["pbr"] == pytest.approx(500e9 / 400e9) and v["psr"] == pytest.approx(1.0)
    loss = [dict(r, amount=-r["amount"]) if r["account"] == "당기순이익" else r for r in rows]
    assert fu.values(loss, 10_000, 10_000_000)["per"] is None  # 적자는 값 없음


def test_backtest_carries_survivor_line_and_wide_flag() -> None:
    data = MarketData(series={"111111": Series(bars([100] * 5))}, info={"111111": {"market": "KOSPI"}})
    res = run_backtest(strategy([R("ma", "cross_up", n=2)], [R("max_hold", value=5)], syms=["111111"]), data, None,
                       days(5)[0], days(5)[-1], 1e7, check=False)
    assert res["survivor_line"] == ("과거 결과는 앞으로의 수익을 뜻하지 않아요 · 상장폐지된 종목은 포함되지 않아요 · "
                                    "실제보다 좋게 나올 수 있어요")
    assert res["wide_universe"] is False
    wide = strategy([R("ma", "cross_up", n=2)], [R("max_hold", value=5)], syms=["111111"])
    wide["graph"]["blocks"][0]["rows"] = [R("market", value=["KOSPI"])]
    res = run_backtest(wide, data, None, days(5)[0], days(5)[-1], 1e7, check=False)
    assert res["wide_universe"] is True  # 시장 전체 유니버스면 노란 카드


def test_R_M8_reason_from_strongest_path() -> None:
    """갈래 둘 통과 → 강도 큰 갈래의 줄만."""
    data = one([9700, 10300])
    body = {"name": "x", "graph": {"blocks": [
        B("u", "universe", [R("manual_list", value=["111111"])]),
        B("s1", "signal", [R("ma", "cross_up", n=2)]),  # 강도 0.03
        B("s2", "signal", [R("return_n", "gte", 1, n=1)]),  # 강도 (6.19 − 1) ÷ 100 ≈ 0.052
        B("k", "select", [R("top_n", value=1)]), B("b", "buy"), B("x", "sell", [R("max_hold", value=5)]),
        B("w", "weight")],
        "edges": [{"from": a, "to": b} for a, b in [("u", "s1"), ("u", "s2"), ("s1", "k"), ("s2", "k"), ("k", "b"),
                                                    ("b", "x"), ("w", "b")]]}}
    eng = Engine(body, data, 1e7)
    ok, strength, reasons, _ = eng._entry("111111", days(2)[-1], {})
    assert ok and strength == pytest.approx((10300 / 9700 - 1) - 0.01)
    assert reasons == ["② n일 수익률 6.2% · 1% 이상"]


def test_R_B3_converted_v1_without_switching_is_identical() -> None:
    """같은 날 갈아타기가 없는 v1 전략 → 비용 · 수량까지 같음(R-C10 문턱은 T-24 · 여기는 한 건)."""
    from app.engine_v1 import run_v1
    from tests.regression.cases import bar_set, bodies

    b = bodies()[1]
    data = bar_set(11)
    ds = sorted({x["d"] for r in data.values() for x in r})
    r1 = run_v1(b, data, ds[60], ds[-1], 1e7)
    r2 = run_backtest(convert_v1(b), data, None, ds[60], ds[-1], 1e7, check=False)
    key = lambda t: (t["d"], t["sym"], t["side"], t["qty"], t["price"], t["amount"], t["cost"])  # noqa: E731
    assert [key(t) for t in r1["trades"]] == [key(t) for t in r2["trades"]]
