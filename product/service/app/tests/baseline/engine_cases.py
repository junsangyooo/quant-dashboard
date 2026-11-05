"""엔진 거래 기록(P1-01): 시험의 백테스트 · 모의투자 · 실전 사례의 거래 목록(날짜 · 종목 · 수량 · 가격 · 사유 · 건너뜀 ·
경고 글). P1-01a가 얼린 v3 사례 326개 **밖의** 사례예요.

네 가지:
- `backtest`: `app.domain.engine.run_backtest`(시험 `test_engine_v2.py`의 입력 꼴) · `app.backtest_v2.run`(API 백테스트가 쓰는
  길 · conftest의 가짜 일봉 파동). 경고 글(`notes` · 값 없음)이 실제로 나오는 사례와 건너뜀(`skipped`) · 실전 안내
  (`live_note`)가 나오는 사례를 넣었어요.
- `engine_rules`: 실전 · 모의 규칙 층(`rules.RuleLayer`)을 끼운 엔진을 하루씩 돌려 규칙 층의 건너뜀 글(가격 상한 ·
  하루 손실 한도 · 하루 주문 40건)이 나오는 사례.
- `paper`: `paper_v2` 흐름(시작 → tick → 체결 → 보유 · `test_paper_v2.py`의 사례) · 걸음마다 화면 값과 DB 판단 기록.
- `live`: `test_live.py`의 아침 흐름(계획 → 점검 → 시가 주문 → 체결 대조) · 주문(사유 · 건너뜀) · 할 일 · 알림.

지금 출력이 정답이에요(동작 변화 0 · 뒤 일감이 같아야 함). 가릴 필드(`mask.MASKED`)는 값을 가려요.
"""

from __future__ import annotations

import json
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app import backtest_v2 as bt2
from app.db import DB
from app.domain.engine import Engine, MarketData, live_note, run_backtest
from app.domain.indicators import Series
from app.domain.markets.kr import KST
from app.market import Market
from app.paper_v2 import PaperV2
from app.domain.rules import RuleLayer
from app.adapters.toss import RateLimiter
from tests.baseline.mask import mask_values
from tests.conftest import FakeBars, make_bars, wave
from tests.test_blocks import B, G, R
from tests.test_engine_v2 import bars, days, strategy


# ── 백테스트(run_backtest · MarketData 직접) ──────────────────────────────────


def _bt(id_: str, note: str, body: dict[str, Any], data: MarketData, start: str, end: str, cash: float,
        bench: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    res = run_backtest(body, data, bench, start, end, cash, check=False)
    return {
        "id": id_, "kind": "backtest", "note": note,
        "input": {"body": body, "series": {s: {"d": v.d, "o": v.o, "h": v.h, "l": v.l, "c": v.c}
                                           for s, v in sorted(data.series.items())},
                  "start": start, "end": end, "cash": cash},
        "trades": res["trades"], "skipped": res["skipped"], "notes": res["notes"],
        "live_counts": res["live_counts"], "live_note": res["live_note"], "final": res["final"], "open": res["open"],
        "buys": res["buys"], "sells": res["sells"], "costs": res["costs"],
    }


def backtest_cases() -> list[dict[str, Any]]:
    out = []
    ds5 = days(5)
    # test_backtest_carries_survivor_line_and_wide_flag
    body = strategy([R("ma", "cross_up", n=2)], [R("max_hold", value=5)], syms=["111111"])
    data = MarketData(series={"111111": Series(bars([100] * 5))}, info={"111111": {"market": "KOSPI"}})
    out.append(_bt("flat_cross_up_no_trade", "평평한 일봉 · 교차 없음 · 거래 0", body, data, ds5[0], ds5[-1], 1e7))
    # 교차가 있는 일봉 · 최대 보유 2일 매도 · 쿨다운
    body = strategy([R("ma", "cross_up", n=2)], [R("max_hold", value=2)], syms=["111111"])
    data = MarketData(series={"111111": Series(bars([100, 100, 110, 112, 105, 100, 108, 115, 116, 110]))})
    ds = days(10)
    out.append(_bt("cross_up_max_hold_2", "교차 매수 · 최대 보유 2일 매도 · 쿨다운 1일", body, data, ds[0], ds[-1], 1e7))
    # 경고 글(notes · R-J1): PER 값 없음(적자) → 그 줄은 거짓 · 기록에 남음
    body = strategy(None, [R("max_hold", value=5)], syms=["111111"], filt=[R("per", "lte", 15)])
    data = MarketData(series={"111111": Series(bars([10000, 10000, 12000, 12500, 12000]))})
    data.fundamentals = lambda sym, d: {"per": None}
    out.append(_bt("notes_per_missing", "경고 글 · 재무 PER 값 없음(③ PER 값 없음)", body, data, ds5[0], ds5[-1], 1e7))
    # 경고 글: 수급(외국인 순매수) 자료 없음
    body = strategy([R("net_buy", "gte", 1000, who="foreign", n=1, unit="shares")], [R("max_hold", value=5)],
                    syms=["111111"])
    data = MarketData(series={"111111": Series(bars([10000] * 5))})
    out.append(_bt("notes_net_buy_missing", "경고 글 · 수급 자료 없음", body, data, ds5[0], ds5[-1], 1e7))
    # 경고 글: 종목 둘 · 하나만 재무 있음
    body = strategy([R("price", "gte", 1)], [R("max_hold", value=5)], syms=["111111", "222222"],
                    filt=[R("pbr", "lte", 3)])
    data = MarketData(series={"111111": Series(bars([100, 101, 102, 103, 104])),
                              "222222": Series(bars([50, 51, 52, 53, 54]))})
    data.fundamentals = lambda sym, d: {"pbr": 1.2} if sym == "111111" else {"pbr": None}
    out.append(_bt("notes_one_of_two_missing", "경고 글 · 두 종목 중 하나만 PBR 없음 · 다른 하나는 매수", body, data,
                   ds5[0], ds5[-1], 1e7))
    # 건너뜀: 1주도 못 사요(현금이 적음)
    body = strategy([R("price", "gte", 1)], [R("max_hold", value=5)], syms=["111111"])
    data = MarketData(series={"111111": Series(bars([10000, 10100, 10200, 10300, 10400]))})
    out.append(_bt("skip_one_share", "건너뜀 · 매수 안 함 · 1주도 못 사요(현금 5,000원)", body, data, ds5[0], ds5[-1],
                   5_000))
    # 건너뜀: 일봉이 없어 체결하지 못했어요(둘째 종목은 셋째 날부터 일봉 없음)
    body = strategy([R("price", "gte", 1)], [R("max_hold", value=5)], syms=["111111", "222222"], top=2)
    b2 = bars([50, 51, 52, 53, 54, 55, 56, 57])[:2]
    data = MarketData(series={"111111": Series(bars([100, 101, 102, 103, 104, 105, 106, 107])), "222222": Series(b2)})
    ds8 = days(8)
    out.append(_bt("skip_missing_bar", "건너뜀 · 일봉이 없어 체결하지 못했어요(3번 시도 뒤)", body, data, ds8[0], ds8[-1],
                   1e7))
    # 실전 안내(R-O7): 시가가 종가보다 10% 넘게 높은 매수 · 낮은 일반 매도
    body = strategy([R("price", "gte", 1)], [R("max_hold", value=1)], syms=["111111"])
    data = MarketData(series={"111111": Series(bars([10000, 10100, 11300, 11400, 10000, 10050],
                                                     opens=[10000, 10100, 11300, 9900, 10000, 10050]))})
    ds6 = days(6)
    out.append(_bt("live_note_gaps", "실전 안내 · 갭 +12% 매수 · 최대 보유 1일 매도가 갭 −13%", body, data, ds6[0], ds6[-1],
                   1e7))
    # 같은 날 매도 대금은 다음 거래일 매수부터(R-O2) · 두 종목 교대
    body = strategy([R("price", "gte", 1)], [R("max_hold", value=1)], syms=["111111", "222222"], top=1,
                    cooldown=0)
    data = MarketData(series={"111111": Series(bars([100, 100, 100, 100, 100, 100])),
                              "222222": Series(bars([50, 50, 60, 60, 60, 60]))})
    out.append(_bt("sale_money_next_day", "R-O2 · 판 돈은 다음 거래일 매수부터(미뤄진 계획)", body, data, ds6[0], ds6[-1],
                   1e7))
    # 보호 매도(손절 + 최대 보유 '모두')
    body = strategy([R("price", "gte", 1)], [R("stop_loss", value=7), R("max_hold", value=1)], syms=["111111"],
                    sell_match="all")
    data = MarketData(series={"111111": Series(bars([10000, 10100, 9000, 9100, 9000]))})
    out.append(_bt("protect_sell_all_match", "R-O4 · 손절 + 최대 보유 '모두' → 보호 매도", body, data, ds5[0], ds5[-1], 1e7))
    # 비중 · 손절 · 익절 · 추적 손절(장중 R-X4)
    body = strategy([R("price", "gte", 1)],
                    [R("stop_loss", value=5, exec_="intraday"), R("take_profit", value=8, exec_="intraday")],
                    syms=["111111"])
    data = MarketData(series={"111111": Series(bars([100, 101, 102, 103, 104, 105, 106, 107],
                                                     highs=[100, 101, 102, 112, 104, 105, 106, 107],
                                                     lows=[100, 101, 102, 103, 104, 95, 106, 107]))})
    out.append(_bt("intraday_stop_take", "R-X4 · 장중 익절(고가) · 장중 손절(저가)", body, data, ds8[0], ds8[-1], 1e7))
    return out


# ── backtest_v2.run(API 백테스트 길 · 가짜 일봉 파동 · 코스피 비교) ──────────


def _v2_body(filt: list[dict[str, Any]] | None = None, sell: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    g = G([B("u", "universe", [R("manual_list", value=["005930", "000660"])]),
           B("s", "signal", [R("ma", "cross_up", n=5)]),
           B("f", "filter", filt or [R("price", "gte", 1)]),
           B("k", "select", [R("top_n", value=2)]), B("b", "buy"),
           B("x", "sell", sell or [R("stop_loss", value=7), R("max_hold", value=10)]), B("w", "weight")],
          ("u", "s"), ("s", "f"), ("f", "k"), ("k", "b"), ("b", "x"), ("w", "b"))
    return {"name": "백테스트 시험", "graph": g}


def fake_wave_bars() -> dict[str, list[dict[str, Any]]]:
    """conftest `fake_bars` 픽스처와 같은 일봉(파동 · 결정적)."""
    a = wave(400, 70000, 6000, 40, 0.0005)
    b = wave(400, 150000, 15000, 30, 0.001)
    k = wave(400, 2500, 100, 50, 0.0002)
    return {"005930": make_bars(a), "000660": make_bars(b), "KOSPI": make_bars(k, volume=0)}


def backtest_v2_cases(tmp: Path) -> list[dict[str, Any]]:
    out = []
    data = fake_wave_bars()
    specs = [
        ("api_wave_cross_up_5", "test_backtest_v2 입력 · ma 교차(5) · 손절 7 · 최대 보유 10 · 2024-03-01 ~ 2025-05-30",
         _v2_body(), "2024-03-01", "2025-05-30", 10_000_000),
        ("api_wave_long_range", "같은 전략 · 2024-01-02 ~ 2025-07-11(일봉 끝까지)", _v2_body(), "2024-01-02",
         "2025-07-11", 50_000_000),
        ("api_wave_trailing", "추적 손절 5 · 최대 보유 20", _v2_body(sell=[R("trailing_stop", value=5),
                                                                      R("max_hold", value=20)]),
         "2024-03-01", "2025-05-30", 10_000_000),
    ]
    for i, (id_, note, body, start, end, cash) in enumerate(specs):
        db = DB(tmp / f"bt2-{i}.db")
        market = Market(db, FakeBars(data), clock=lambda: 0.0, calendar=None)
        market.calendar.fetch = None
        res = bt2.run(body, market=market, db=db, dart=None, has_dart=False, toss_ready=True,
                      start=date.fromisoformat(start), end=date.fromisoformat(end), cash=cash, info={},
                      names=lambda s: {"005930": "삼성전자", "000660": "SK하이닉스"}.get(s, s))
        rec = {k: res[k] for k in ("trades", "skipped", "notes", "live_counts", "live_note", "final", "total", "cagr",
                                   "mdd", "buys", "sells", "win_rate", "costs", "bench_total", "bench_cagr",
                                   "bench_mdd", "open", "trade_count", "chips", "judge_line", "wide_title",
                                   "survivor_line", "wide_universe", "recent")}
        rec["curve_len"] = len(res["curve"])
        rec["curve_last"] = res["curve"][-1]
        rec["bench_curve_len"] = len(res["bench_curve"])
        out.append({"id": id_, "kind": "backtest_v2", "note": note,
                    "input": {"body": body, "bars": "conftest fake_bars wave(400) 005930 · 000660 · KOSPI",
                              "start": start, "end": end, "cash": cash}, **mask_values(rec)})
    return out


# ── 규칙 층을 끼운 엔진(실전 · 모의 규칙의 건너뜀 글) ───────────────────────


def _rules_run(id_: str, note: str, body: dict[str, Any], data: MarketData, cash: float, amount: float | None = None,
               **rule_kw: Any) -> dict[str, Any]:
    cal = sorted({d for s in data.series.values() for d in s.d})
    eng = Engine(body, data, cash, calendar=cal, rules=RuleLayer(amount=amount or cash, **rule_kw))
    trades: list[dict[str, Any]] = []
    plans_by_day: dict[str, list[dict[str, Any]]] = {}
    for d in cal:
        trades += eng.fill(d)
        plans_by_day[d] = json.loads(json.dumps(eng.judge(d)))
    return {"id": id_, "kind": "engine_rules", "note": note,
            "input": {"body": body, "series": {s: {"d": v.d, "o": v.o, "c": v.c} for s, v in sorted(data.series.items())},
                      "cash": cash, "rules": {"amount": amount or cash, **rule_kw}},
            "trades": trades, "skipped": eng.skipped, "notes": eng.notes, "live_counts": dict(eng.live_counts),
            "live_note": live_note(eng.live_counts), "plans_by_day": plans_by_day, "state": eng.state,
            "open": [{"sym": s, "qty": p["qty"], "avg": p["avg"]} for s, p in eng.pos.items()]}


def engine_rules_cases() -> list[dict[str, Any]]:
    out = []
    # 가격 상한: 시가가 종가 × 1.1을 넘으면 매수 안 함(규칙 층 buy_block)
    body = strategy([R("price", "gte", 1)], [R("max_hold", value=5)], syms=["111111"])
    data = MarketData(series={"111111": Series(bars([10000, 10100, 10200, 10300], opens=[10000, 11300, 10200, 10300]))})
    out.append(_rules_run("rules_price_cap", "규칙 층 · 시가 +12% → 매수 안 함(가격 상한)", body, data, 10_000_000))
    # 일반 매도 하한: 시가가 종가 × 0.9 아래면 일반 매도 안 함 · 보호 매도는 팔아요
    body = strategy([R("price", "gte", 1)], [R("max_hold", value=1)], syms=["111111"])
    data = MarketData(series={"111111": Series(bars([10000, 10100, 10200, 8800, 8900, 9000],
                                                     opens=[10000, 10100, 10200, 8800, 8900, 9000]))})
    out.append(_rules_run("rules_sell_floor", "규칙 층 · 일반 매도 시가 −14% → 매도 안 함(하한) · 다음 날 다시", body, data,
                          10_000_000))
    # 하루 손실 한도 −3% → 다음 날 새 매수 0
    body = strategy([R("price", "gte", 5000)], [R("max_hold", value=10)], syms=["111111", "222222", "333333"], top=3)
    data = MarketData(series={"111111": Series(bars([10000, 10000, 9000, 9000, 9000])),
                              "222222": Series(bars([10000] * 5)),
                              "333333": Series(bars([4000, 4000, 6000, 6000, 6000]))})
    out.append(_rules_run("rules_daily_loss", "규칙 층 · 하루 손실 한도(−3%) → 다음 날 새 매수 0 · 그다음 날 다시", body,
                          data, 10_000_000))
    # 하루 주문 40건: 매수 후보 45 → 40건만(순위 순) · 나머지 '하루 주문 40건'
    syms = [f"{i:06d}" for i in range(100001, 100046)]
    body = strategy([R("price", "gte", 1)], [R("max_hold", value=10)], syms=syms, top=45)
    data = MarketData(series={s: Series(bars([1000 + i, 1001 + i, 1002 + i])) for i, s in enumerate(syms)})
    out.append(_rules_run("rules_forty_orders", "규칙 층 · 매수 후보 45 → 40건 · 나머지 '하루 주문 40건'", body, data,
                          100_000_000))
    # 종목당 한도 40% · 주문 크기 2,000만 원
    body = strategy([R("price", "gte", 1)], [R("max_hold", value=10)], syms=["111111"], top=1)
    data = MarketData(series={"111111": Series(bars([10000, 10000, 10000]))})
    out.append(_rules_run("rules_per_stock_cap", "규칙 층 · 종목당 한도 40% · 주문 크기 2,000만 원(목표 금액 깎임)", body,
                          data, 100_000_000))
    return out


# ── 모의투자 v2 흐름(test_paper_v2 사례) ─────────────────────────────────────


class _Now:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t

    def at(self, d: str, hh: int, mm: int = 0) -> None:
        self.t = datetime.fromisoformat(d).replace(hour=hh, minute=mm, tzinfo=KST)


PAPER_MON = date(2026, 3, 2)


def _paper_body(syms: list[str], sell: list[dict[str, Any]] | None = None, signal: dict[str, Any] | None = None,
                top: int = 1) -> dict[str, Any]:
    g = G([B("u", "universe", [R("manual_list", value=syms)]),
           B("s", "signal", [signal or R("price", "gte", 1)]),
           B("k", "select", [R("top_n", value=top)]), B("b", "buy"),
           B("x", "sell", sell or [R("max_hold", value=50)]), B("w", "weight")],
          ("u", "s"), ("s", "k"), ("k", "b"), ("b", "x"), ("w", "b"))
    return {"name": "모의", "graph": g}


def _paper_world(tmp: Path, bars_: dict[str, list[dict[str, Any]]], now: _Now) -> tuple[DB, PaperV2]:
    db = DB(tmp / "p.db")
    market = Market(db, FakeBars(bars_), clock=lambda: 0.0, calendar=None)
    market.calendar.fetch = None
    return db, PaperV2(db, market, now=now)


def _save(db: DB, b: dict[str, Any], name: str = "모의") -> int:
    sid = db.run("INSERT INTO strategies(name,template,source,created_at) VALUES(?,?,?,?)", (name, "event", None, "t"))
    return db.run("INSERT INTO versions(strategy_id,no,body,problems,created_at,format) VALUES(?,?,?,?,?,?)",
                  (sid, 1, json.dumps(b), 0, "t", "blocks"))


def _paper_snapshot(db: DB, paper: PaperV2, rid: int) -> dict[str, Any]:
    v = paper.view(rid)
    judged = [dict(x) | {"plans": json.loads(x["plans"])} for x in
              db.all("SELECT * FROM paper_judgements WHERE run_id=? ORDER BY id", (rid,))]
    alerts = [dict(a) for a in db.all("SELECT live, kind, title, body FROM alerts ORDER BY id")]
    state = json.loads(db.one("SELECT state FROM paper_runs WHERE id=?", (rid,))["state"])
    return mask_values({"view": v, "judgements": judged, "alerts": alerts, "state": state})


def _flat(n: int, price: float = 10_000, **kw: Any) -> list[dict[str, Any]]:
    return make_bars([price] * n, start=PAPER_MON, **kw)


def paper_cases(tmp: Path) -> list[dict[str, Any]]:
    out = []

    def run(id_: str, note: str, bars_: dict[str, list[dict[str, Any]]], start_at: tuple[str, int, int],
            body: dict[str, Any], cash: float, steps: list[tuple[str, int, int, str]]) -> None:
        now = _Now(datetime(2026, 1, 1, tzinfo=KST))
        now.at(*start_at)
        db, paper = _paper_world(tmp / id_, bars_, now)
        vid = _save(db, body)
        first = paper.preview(vid)
        v = paper.start(vid, cash)
        rid = int(v["id"])
        trail = [{"now": now.t.isoformat(), "step": "start", "preview": first, **_paper_snapshot(db, paper, rid)}]
        for d, hh, mm, what in steps:
            now.at(d, hh, mm)
            if what == "tick":
                res: Any = paper.tick()
            elif what == "stop":
                res = paper.stop(rid)["status"]
            else:
                raise ValueError(what)
            trail.append({"now": now.t.isoformat(), "step": what, "result": res, **_paper_snapshot(db, paper, rid)})
        out.append({"id": id_, "kind": "paper", "note": note,
                    "input": {"body": body, "bars": bars_, "start_at": list(start_at), "cash": cash,
                              "steps": [list(s) for s in steps]},
                    "trail": trail, "trades": trail[-1]["view"]["trades"]})

    run("paper_first_check_2010", "화요일 장중 시작 → 그날 20:10 첫 확인 → 수요일 시가 체결", {"111111": _flat(10)},
        ("2026-03-03", 15, 0), _paper_body(["111111"]), 10_000_000,
        [("2026-03-03", 20, 5, "tick"), ("2026-03-03", 20, 10, "tick"), ("2026-03-04", 20, 10, "tick"),
         ("2026-03-05", 20, 10, "tick")])
    b = make_bars([10_000, 10_000, 10_000, 10_000, 10_000], start=PAPER_MON)
    b[3]["l"] = 9_000
    run("paper_intraday_stop_low", "R-V2 · 장중 손절은 그날 저가로(목요일 저가 −10%)", {"111111": b},
        ("2026-03-02", 21, 0), _paper_body(["111111"], sell=[R("stop_loss", value=7)]), 10_000_000,
        [("2026-03-03", 21, 0, "tick"), ("2026-03-04", 21, 0, "tick"), ("2026-03-05", 21, 0, "tick")])
    run("paper_days_off_filled", "R-V4 · 3거래일 꺼짐 → 하루씩 이어서 채움(매수 · 최대 보유 1일 매도)",
        {"111111": make_bars([10_000] * 8, start=PAPER_MON)}, ("2026-03-02", 21, 0),
        _paper_body(["111111"], sell=[R("max_hold", value=1)]), 10_000_000, [("2026-03-05", 21, 0, "tick")])
    run("paper_daily_loss", "R-V1 · 하루 손실 −3% 넘음 → 다음 날 새 매수 0 · 그다음 날 다시",
        {"111111": make_bars([10_000, 10_000, 9_000, 9_000, 9_000], start=PAPER_MON), "222222": _flat(5),
         "333333": make_bars([4_000, 4_000, 6_000, 6_000, 6_000], start=PAPER_MON)},
        ("2026-03-02", 21, 0), _paper_body(["111111", "222222", "333333"], signal=R("price", "gte", 5_000), top=3),
        10_000_000, [("2026-03-03", 21, 0, "tick"), ("2026-03-04", 21, 0, "tick"), ("2026-03-05", 21, 0, "tick")])
    run("paper_price_cap", "R-V1 · 시가가 종가보다 12% 높으면 매수 안 함(가격 상한)",
        {"111111": make_bars([10_000, 10_000, 10_000], start=PAPER_MON, opens=[10_000, 11_200, 10_000])},
        ("2026-03-02", 21, 0), _paper_body(["111111"]), 10_000_000, [("2026-03-03", 21, 0, "tick")])
    run("paper_stop_and_holiday", "금요일 밤 시작 · 일요일 확인 없음 · 월요일 확인 뒤 끝냄 → 화요일 확인 없음",
        {"111111": _flat(10)}, ("2026-03-06", 21, 0), _paper_body(["111111"]), 10_000_000,
        [("2026-03-08", 21, 0, "tick"), ("2026-03-09", 21, 0, "tick"), ("2026-03-09", 21, 1, "stop"),
         ("2026-03-10", 21, 0, "tick")])
    run("paper_two_symbols_rotation", "두 종목 · 최대 보유 2일 · 상위 1 → 교대 매수 · 모의 체결 알림 수",
        {"111111": make_bars([100, 100, 110, 112, 105, 100, 108, 115], start=PAPER_MON),
         "222222": make_bars([50, 60, 50, 50, 70, 80, 50, 50], start=PAPER_MON)}, ("2026-03-02", 21, 0),
        _paper_body(["111111", "222222"], sell=[R("max_hold", value=2)], signal=R("price", "gte", 55)), 1_000_000,
        [(d, 21, 0, "tick") for d in ("2026-03-03", "2026-03-04", "2026-03-05", "2026-03-06", "2026-03-09",
                                       "2026-03-10", "2026-03-11")])
    return out


# ── 실전 아침 흐름(test_live 사례) ───────────────────────────────────────────


def _fast(w: Any) -> None:
    """요청 한도 대기 · 토큰 만료 · 일봉 캐시의 바깥 시계를 모의 시계로(기록 스크립트는 잠자지 않아요)."""
    epoch = lambda: w.clock.t.timestamp()  # noqa: E731
    w.market.clock = epoch
    w.client.wall_clock = epoch
    w.client.limiter = RateLimiter(clock=epoch, sleep=lambda s: None)


def _live_snapshot(w: Any, rid: int) -> dict[str, Any]:
    st = w.live.state(rid)
    orders = [dict(o) | {"reason": json.loads(o["reason"] or "{}")} for o in w.db.all("SELECT * FROM orders ORDER BY id")]
    todos = [dict(t) for t in w.db.all("SELECT kind, severity, symbol, title, body, status FROM todos ORDER BY id")]
    return mask_values({"state": {k: st.get(k) for k in ("cash", "pos", "next", "blocked", "manual", "sell_fail")},
                        "orders": orders, "todos": todos, "sent": [{"event": e, "text": t} for e, t in w.sent]})


def live_cases(tmp: Path) -> list[dict[str, Any]]:
    from tests.test_live import SYM, World, body, give_pos, morning, running

    out = []
    d = date(2026, 11, 3)

    def case(id_: str, note: str, w: Any, rid: int, steps: list[dict[str, Any]], input_: dict[str, Any]) -> None:
        out.append({"id": id_, "kind": "live", "note": note, "input": input_, "steps": steps,
                    "final": _live_snapshot(w, rid)})

    # test_day_flow_buy_size_cap_and_fill
    w = World(tmp / "a")
    _fast(w)
    rid = running(w)
    steps = [{"step": "start(월 21:00)", **_live_snapshot(w, rid)}]
    res = morning(w, d)
    steps.append({"step": "morning(08:30 점검 · 08:35 주문)", "open_orders": mask_values(res)})
    o = w.orders()[0]
    w.server.fill(o["toss_order_id"], str(o["qty"]), "10100")
    w.clock.at(d, 9, 1)
    w.live.after_open(rid)
    steps.append({"step": "09:01 체결 대조(10,100원 체결)", **_live_snapshot(w, rid)})
    case("live_day_flow_fill", "R-L11 → 계획 → 점검 → 시가 지정가(상한) → 체결 대조", w, rid, steps,
         {"closes": "10,000 × 60", "amount": 10_000_000, "body": "manual_list 005930 · price ≥ 1 · top 1 · max_hold 50"})
    # 보호 매도(하한가) vs 일반 매도(종가 × 0.9)
    for kind, reason, id_ in (("protect", ["손절"], "live_protect_sell_price"), ("normal", ["최대 보유"],
                                                                                "live_normal_sell_price")):
        w = World(tmp / id_)
        _fast(w)
        rid = running(w)
        give_pos(w, rid, SYM, 20, 10_000)
        st = w.live.state(rid)
        st["next"] = {"judged": "2026-11-02", "for_d": "2026-11-03", "plans": [
            {"sym": SYM, "side": "sell", "qty": 20, "kind": kind, "close": 10_000.0, "reason": reason}]}
        w.live.save(rid, st)
        res = morning(w, d)
        case(id_, f"R-O4 · R-O5 · {kind} 매도 가격", w, rid, [{"step": "morning", "open_orders": mask_values(res)}],
             {"pos": {SYM: {"qty": 20, "avg": 10_000}}, "plan": {"side": "sell", "kind": kind}})
    # 큰 주문 · 너무 큰 주문 → 할 일 · 보내지 않음
    w = World(tmp / "huge", cash="500000000")
    _fast(w)
    rid = running(w, amount=300_000_000)
    st = w.live.state(rid)
    st["next"]["plans"] = [{"sym": SYM, "side": "buy", "value": 120_000_000, "close": 10_000.0, "reason": []}]
    w.live.save(rid, st)
    res = morning(w, d)
    case("live_huge_order_todo", "R-O9 · 1억 이상 → 할 일 · 주문 0", w, rid, [{"step": "morning",
                                                                             "open_orders": mask_values(res)}],
         {"plan_value": 120_000_000, "amount": 300_000_000})
    # 확인 실패 → 새 매수 0(건너뜀 '오늘 확인 실패')
    w = World(tmp / "checkfail")
    _fast(w)
    rid = running(w)
    w.live.set_meta(rid, "check_failed", "2026-11-02T20:20:00+09:00")
    res = morning(w, d)
    case("live_check_failed_skip", "R-L4 · 확인 실패 → 시가 매수 건너뜀(오늘 확인 실패)", w, rid,
         [{"step": "morning", "open_orders": mask_values(res)}], {"meta": {"check_failed": "set"}})
    # 새 매수 멈춤 → 건너뜀 '새 매수 멈춤'
    w = World(tmp / "paused")
    _fast(w)
    rid = running(w)
    w.live.pause_new_buys()
    res = morning(w, d)
    case("live_paused_skip", "새 매수 멈춤 → 시가 매수 건너뜀(새 매수 멈춤)", w, rid,
         [{"step": "morning", "open_orders": mask_values(res)}], {"paused": True})
    # 3거래일 꺼짐 → 지난 날 매수 0 · 매도 신호만
    closes = [10_000.0] * 60
    w = World(tmp / "missed", closes={SYM: closes, "000660": closes}, today=date(2026, 11, 6))
    _fast(w)
    vid = w.version(body(sell=[R("max_hold", value=1)], syms=[SYM, "000660"], top=2))
    w.clock.at(date(2026, 10, 30), 15, 0)
    rid = w.live.start(vid, 10_000_000)
    w.live.set_meta(rid, "last_check", "2026-10-30")
    give_pos(w, rid, SYM, 10, 10_000)
    w.clock.at(date(2026, 11, 5), 21, 0)
    res = w.live.check(rid)
    case("live_missed_days_sells_only", "R-L1 · 3거래일 꺼짐 → 지난 날 매수 0 · 매도 신호만 다음 시가", w, rid,
         [{"step": "check(목 21:00)", "check": mask_values(res)}], {"off_days": "11-02 ~ 11-05", "pos": SYM})
    return out


def run_all() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="quant-baseline-engine-") as d:
        tmp = Path(d)
        cases = backtest_cases() + backtest_v2_cases(tmp / "bt2") + engine_rules_cases() + paper_cases(tmp / "paper") \
            + live_cases(tmp / "live")
    ids = [c["id"] for c in cases]
    assert len(ids) == len(set(ids)), "사례 id 중복"
    notes_cases = [c["id"] for c in cases if c.get("notes")]
    skipped_cases = [c["id"] for c in cases if c.get("skipped")]
    return {"count": len(cases), "by_kind": {k: sum(1 for c in cases if c["kind"] == k)
                                             for k in sorted({c["kind"] for c in cases})},
            "with_notes": notes_cases, "with_skipped": skipped_cases, "cases": cases}


if __name__ == "__main__":
    import sys

    from tests.baseline.clock import freeze_plain

    freeze_plain()
    res = run_all()
    print(res["count"], res["by_kind"], "notes:", res["with_notes"], "skipped:", res["with_skipped"])
    for c in res["cases"]:
        print(c["kind"], c["id"], "trades", len(c.get("trades", [])), "skipped", len(c.get("skipped", [])),
              "notes", c.get("notes"))
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(json.dumps(res, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
