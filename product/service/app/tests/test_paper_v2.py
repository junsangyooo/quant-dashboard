"""모의투자 v2(TASKS T-40): ENGINE-RULES 8절 R-V1 ~ R-V5 · 20:10 확인 · 놓친 날 이어서 채우기."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from app.db import DB
from app.market import KST, Market
from app.paper_v2 import ALREADY, PaperError, PaperV2
from app.rules import buy_cap
from tests.conftest import FakeBars, make_bars
from tests.test_blocks import B, G, R

MON = date(2026, 3, 2)  # 월요일


class Now:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t

    def at(self, d: str, hh: int, mm: int = 0) -> None:
        self.t = datetime.fromisoformat(d).replace(hour=hh, minute=mm, tzinfo=KST)


def body(syms: list[str], sell: list[dict[str, Any]] | None = None, signal: dict[str, Any] | None = None,
         top: int = 1) -> dict[str, Any]:
    g = G([B("u", "universe", [R("manual_list", value=syms)]),
           B("s", "signal", [signal or R("price", "gte", 1)]),
           B("k", "select", [R("top_n", value=top)]), B("b", "buy"),
           B("x", "sell", sell or [R("max_hold", value=50)]), B("w", "weight")],
          ("u", "s"), ("s", "k"), ("k", "b"), ("b", "x"), ("w", "b"))
    return {"name": "모의", "graph": g}


def save(db: DB, b: dict[str, Any], name: str = "모의") -> int:
    sid = db.run("INSERT INTO strategies(name,template,source,created_at) VALUES(?,?,?,?)", (name, "event", None, "t"))
    return db.run("INSERT INTO versions(strategy_id,no,body,problems,created_at,format) VALUES(?,?,?,?,?,?)",
                  (sid, 1, json.dumps(b), 0, "t", "blocks"))


def setup(tmp_path: Path, bars: dict[str, list[dict[str, Any]]], now: Now) -> tuple[DB, PaperV2, FakeBars]:
    db = DB(tmp_path / "p.db")
    src = FakeBars(bars)
    market = Market(db, src, calendar=None)
    market.calendar.fetch = None  # 달력 없이 평일 = 거래일
    return db, PaperV2(db, market, now=now), src


def flat(n: int, price: float = 10_000, **kw: Any) -> list[dict[str, Any]]:
    return make_bars([price] * n, start=MON, **kw)


def test_first_check_at_2010_then_fill_next_open(tmp_path: Path) -> None:
    now = Now(datetime(2026, 3, 3, 15, 0, tzinfo=KST))  # 화요일 장중에 시작
    db, paper, src = setup(tmp_path, {"111111": flat(10)}, now)
    vid = save(db, body(["111111"]))
    v = paper.start(vid, 10_000_000)
    assert v["plans"] == [] and v["last_date"] == "2026-03-02"
    now.at("2026-03-03", 20, 5)
    paper.tick()
    assert paper.view(v["id"])["plans"] == []  # 20:00 전 일봉은 확정 전 · 20:05면 확정됐지만…
    now.at("2026-03-03", 20, 10)
    paper.tick()
    assert [p["sym"] for p in paper.view(v["id"])["plans"]] == ["111111"]  # 그날 20:10 첫 확인
    now.at("2026-03-04", 20, 10)
    paper.tick()
    t = paper.view(v["id"])["trades"]
    assert [(x["d"], x["side"], x["price"]) for x in t] == [("2026-03-04", "buy", 10_000.0)]  # 다음 거래일 시가


def test_R_V2_intraday_stop_uses_low(tmp_path: Path) -> None:
    bars = make_bars([10_000, 10_000, 10_000, 10_000, 10_000], start=MON)
    bars[3]["l"] = 9_000  # 목요일 저가 −10%
    now = Now(datetime(2026, 3, 2, 21, 0, tzinfo=KST))
    db, paper, _ = setup(tmp_path, {"111111": bars}, now)
    vid = save(db, body(["111111"], sell=[R("stop_loss", value=7)]))
    rid = paper.start(vid, 10_000_000)["id"]
    now.at("2026-03-05", 21, 0)
    paper.tick()
    t = paper.view(rid)["trades"]
    assert [x["side"] for x in t] == ["buy", "sell"]
    assert t[1]["d"] == "2026-03-05" and t[1]["price"] == pytest.approx(t[0]["price"] * 1.00015 * 0.93)


def test_R_V3_one_per_strategy_many_strategies(tmp_path: Path) -> None:
    now = Now(datetime(2026, 3, 2, 21, 0, tzinfo=KST))
    db, paper, _ = setup(tmp_path, {"111111": flat(5), "222222": flat(5)}, now)
    a = save(db, body(["111111"]), "가")
    b = save(db, body(["222222"]), "나")
    paper.start(a, 1_000_000)
    paper.start(b, 2_000_000)  # 여러 전략 동시에
    with pytest.raises(PaperError) as e:
        paper.start(a, 1_000_000)
    assert e.value.message == ALREADY == "이 전략은 이미 모의투자 중이에요"
    with pytest.raises(PaperError, match="10만 원 ~ 100억 원"):
        paper.start(save(db, body(["111111"]), "다"), 50_000)
    assert len(paper.list()) == 2


def test_R_V4_days_off_are_filled_one_by_one(tmp_path: Path) -> None:
    closes = [10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000, 10_000]
    now = Now(datetime(2026, 3, 2, 21, 0, tzinfo=KST))
    db, paper, _ = setup(tmp_path, {"111111": make_bars(closes, start=MON)}, now)
    vid = save(db, body(["111111"], sell=[R("max_hold", value=1)]))
    rid = paper.start(vid, 10_000_000)["id"]
    now.at("2026-03-05", 21, 0)  # 화 · 수 · 목 3거래일 꺼져 있었어요
    paper.tick()
    judged = [x["d"] for x in db.all("SELECT d FROM paper_judgements WHERE run_id=? ORDER BY id", (rid,))]
    assert judged == ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05"]  # 3일치를 하루씩
    t = paper.view(rid)["trades"]
    assert [(x["d"], x["side"]) for x in t] == [("2026-03-03", "buy"), ("2026-03-05", "sell")]
    assert [d for d, _ in paper.view(rid)["curve"]] == ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05"]


def test_R_V1_daily_loss_blocks_next_day_buys(tmp_path: Path) -> None:
    """모의 하루 손실 −3% 넘음 → 다음 날 모의 새 매수 0(매도는 계속)."""
    a = make_bars([10_000, 10_000, 9_000, 9_000, 9_000], start=MON)  # 수요일 종가 −10% → 자산 약 −4%
    b = flat(5)
    c = make_bars([4_000, 4_000, 6_000, 6_000, 6_000], start=MON)  # 수요일에야 신호(주가 5,000원 이상)
    now = Now(datetime(2026, 3, 2, 21, 0, tzinfo=KST))
    db, paper, _ = setup(tmp_path, {"111111": a, "222222": b, "333333": c}, now)
    vid = save(db, body(["111111", "222222", "333333"], signal=R("price", "gte", 5_000), top=3))
    rid = paper.start(vid, 10_000_000)["id"]
    now.at("2026-03-03", 21, 0)
    paper.tick()
    assert sorted(t["symbol"] for t in paper.view(rid)["trades"]) == ["111111", "222222"]
    now.at("2026-03-04", 21, 0)
    paper.tick()
    state = json.loads(db.one("SELECT state FROM paper_runs WHERE id=?", (rid,))["state"])
    assert state["loss_block_d"] == "2026-03-04"
    assert [p for p in paper.view(rid)["plans"] if p["side"] == "buy"] == []  # 333333 신호가 있어도 매수 0
    now.at("2026-03-05", 21, 0)
    paper.tick()
    assert [p["sym"] for p in paper.view(rid)["plans"] if p["side"] == "buy"] == ["333333"]  # 그다음 날 다시 사요


def test_R_V1_price_cap_like_live(tmp_path: Path) -> None:
    """가격 상한도 실전과 같아요: 시가가 종가보다 12% 높으면 매수 안 함."""
    bars = make_bars([10_000, 10_000, 10_000], start=MON, opens=[10_000, 11_200, 10_000])
    now = Now(datetime(2026, 3, 2, 21, 0, tzinfo=KST))
    db, paper, _ = setup(tmp_path, {"111111": bars}, now)
    vid = save(db, body(["111111"]))
    rid = paper.start(vid, 10_000_000)["id"]
    assert buy_cap(10_000) == 11_000
    now.at("2026-03-03", 21, 0)
    paper.tick()
    assert paper.view(rid)["trades"] == []
    run = db.one("SELECT state FROM paper_runs WHERE id=?", (rid,))
    assert json.loads(run["state"])["pos"] == {}


def test_R_V5_paper_numbers_stay_in_paper_tab(tmp_path: Path) -> None:
    now = Now(datetime(2026, 3, 2, 21, 0, tzinfo=KST))
    db, paper, _ = setup(tmp_path, {"111111": flat(5)}, now)
    rid = paper.start(save(db, body(["111111"])), 10_000_000)["id"]
    now.at("2026-03-04", 21, 0)
    paper.tick()
    assert paper.view(rid)["trades"]  # 모의 체결 1
    for table in ("runs", "positions", "orders", "fills", "todos", "run_cash", "run_equity"):
        assert db.one(f"SELECT COUNT(*) n FROM {table}")["n"] == 0, table  # 실전 표 · 할 일 배지 0
    alerts = db.all("SELECT live, title FROM alerts")
    assert [(a["live"], a["title"]) for a in alerts] == [(0, "모의 · 모의 체결 1건")]  # 첫 낱말 '모의'


def test_stop_and_holiday_skip(tmp_path: Path) -> None:
    now = Now(datetime(2026, 3, 6, 21, 0, tzinfo=KST))  # 금요일 밤
    db, paper, _ = setup(tmp_path, {"111111": flat(10)}, now)
    rid = paper.start(save(db, body(["111111"])), 10_000_000)["id"]
    now.at("2026-03-08", 21, 0)  # 일요일: 확인할 새 거래일 없음
    assert paper.tick() == []
    now.at("2026-03-09", 21, 0)
    assert paper.tick() == [rid]
    assert paper.stop(rid)["status"] == "ended"
    now.at("2026-03-10", 21, 0)
    assert paper.tick() == []


def test_paper_api(app_client) -> None:  # type: ignore[no-untyped-def]
    from tests.conftest import setup_owner

    setup_owner(app_client)
    sid = app_client.post("/api/v2/strategies", json={"body": body(["005930"])}).json()["id"]
    vid = app_client.get(f"/api/v2/strategies/{sid}").json()["version"]["id"]
    r = app_client.post("/api/v2/paper/start", json={"version_id": vid, "cash": 10_000_000})
    assert r.status_code == 200, r.text
    again = app_client.post("/api/v2/paper/start", json={"version_id": vid, "cash": 10_000_000})
    assert again.status_code == 409 and again.json()["error"] == "이 전략은 이미 모의투자 중이에요"
    assert app_client.get(f"/api/v2/strategies/{sid}").json()["running"]["kind"] == "paper"
    rid = r.json()["id"]
    assert app_client.get(f"/api/v2/paper/{rid}").json()["diff_lines"]
    assert app_client.post(f"/api/v2/paper/{rid}/stop").json()["status"] == "ended"
