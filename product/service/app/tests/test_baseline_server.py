"""P1-01b 서버 관측 시험(기준선 조각 둘째): 시계 고정이 닿는 자리 · 앱 루프 한 바퀴 · 주문 기록 순서 · 화면 라우트 ·
하루 흐름 뼈대 · 엔진 사례 묶음.

기준선 파일(`tests/baseline/server/`)과의 대조는 `python -m tests.baseline.compare`가 해요(여기서는 파일을 읽지 않음).
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from app import connect, vault
from app import main as main_mod
from app.main import create_app
from app.market import now_kst
from tests.baseline import clock as bclock
from tests.baseline.clock import FIXED_NOW, FIXED_NOW_UTC_ISO, RECOVERY_CODE
from tests.conftest import CsrfClient, FakeBars, FakeIp, FakeToss, setup_owner
from tests.test_blocks import B, G, R


@pytest.fixture
def frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    bclock.freeze(monkeypatch)


def _body() -> dict[str, Any]:
    g = G([B("u", "universe", [R("manual_list", value=["005930", "000660"])]), B("s", "signal", [R("ma", "cross_up", n=5)]),
           B("k", "select", [R("top_n", value=2)]), B("b", "buy"),
           B("x", "sell", [R("stop_loss", value=7), R("max_hold", value=10)]), B("w", "weight")],
          ("u", "s"), ("s", "k"), ("k", "b"), ("b", "x"), ("w", "b"))
    return {"name": "기준선", "graph": g}


# ── B. 시계 고정이 5곳 + Live.now() + 복구 코드에 닿음 ───────────────────────


def test_clock_reaches_the_three_iso_sites_and_now_kst(frozen: None) -> None:
    """connect.py:79 · vault.py:91 · main.py:1267(8b67df6) · market.now_kst(서버 now 기본값)."""
    assert connect._now() == FIXED_NOW_UTC_ISO
    assert vault._now_iso() == FIXED_NOW_UTC_ISO
    assert main_mod._now() == FIXED_NOW_UTC_ISO
    assert now_kst() == FIXED_NOW


def test_clock_reaches_backtest_default_range_and_ran_at(frozen: None, app_client: Any) -> None:
    """api_v2.py:237(기본 기간의 끝 = 고정 날짜) · backtest_v2.py:120(ran_at = 고정 시각)."""
    setup_owner(app_client)
    sid = app_client.post("/api/v2/strategies", json={"body": _body()}).json()["id"]
    vid = app_client.get(f"/api/v2/strategies/{sid}").json()["version"]["id"]
    inp = app_client.get(f"/api/v2/versions/{vid}/backtest").json()
    assert inp["range"]["end"] == FIXED_NOW.date().isoformat() == "2025-06-02"
    assert inp["range"]["start"] == "2021-01-04"
    r = app_client.post("/api/v2/backtest", json={"version_id": vid, "start": "2024-03-01", "end": "2025-05-30",
                                                  "cash": 10_000_000})
    assert r.status_code == 200, r.text
    assert r.json()["ran_at"] == FIXED_NOW_UTC_ISO


def test_clock_reaches_server_now_when_create_app_uses_its_default(frozen: None, tmp_path: Path,
                                                                   fake_bars: FakeBars) -> None:
    """`create_app(now=…)`를 주지 않아도 Live · Scheduler · PaperV2 · Telegram의 now가 고정 시각."""
    app = create_app(tmp_path / "data", bars_source=fake_bars, scrypt_n=2**12, scheduler=False, keyfile=False)
    assert app.state.live.now() == FIXED_NOW
    assert app.state.scheduler.now() == FIXED_NOW
    assert app.state.paper2.now() == FIXED_NOW
    assert app.state.telegram.now() == FIXED_NOW


def test_recovery_code_is_seeded(frozen: None, monkeypatch: pytest.MonkeyPatch, app_client: Any) -> None:
    """vault.py:109 `secrets.choice` → 씨앗 난수 · 첫 복구 코드가 늘 같음(설치 응답에서도)."""
    assert vault.new_recovery_code() == RECOVERY_CODE
    assert vault.new_recovery_code() != RECOVERY_CODE  # 둘째 코드는 다른 값(난수는 이어짐)
    bclock.freeze(monkeypatch)  # 씨앗을 다시 → 설치 직후 첫 코드
    code = setup_owner(app_client)
    assert vault.normalize_recovery_code(code) == RECOVERY_CODE
    assert code == vault.format_recovery_code(RECOVERY_CODE)


def test_clock_sites_list_matches_the_code(frozen: None) -> None:
    """패치 자리 목록이 실제로 모듈 전역 이름으로 있고, 고정 뒤 그 이름이 FrozenDatetime임."""
    import importlib

    for module, name, _ in bclock.CLOCK_SITES:
        assert getattr(importlib.import_module(module), name) is bclock.FrozenDatetime, module
    module, name, _ = bclock.SEED_SITE
    assert getattr(importlib.import_module(module), name).choice is not __import__("secrets").choice


# ── E. `_auto_loop` 한 바퀴 · 주문 기록 순서 ─────────────────────────────────


def test_auto_loop_runs_one_lap_in_order(frozen: None, tmp_path: Path, fake_bars: FakeBars, fake_toss: FakeToss,
                                        fake_ip: FakeIp, monkeypatch: pytest.MonkeyPatch) -> None:
    """main.py:1205(8b67df6) `_auto_loop` 한 바퀴: auto_tick → (첫 바퀴) paper2.tick · updates.announce →
    sched.run_due → live_tick → telegram.poll → sleep(30). 둘째 바퀴는 돌지 않게 sleep을 붙잡아요."""
    app = create_app(tmp_path / "data", bars_source=fake_bars, toss_transport=lambda: fake_toss, ip_fetch=fake_ip,
                     scrypt_n=2**12, scheduler=True, now=lambda: FIXED_NOW, keyfile=False)
    db = app.state.db
    calls: list[tuple[str, str | None]] = []
    lap_done = threading.Event()
    real_sleep = asyncio.sleep

    async def fake_sleep(seconds: float, *a: Any, **k: Any) -> Any:
        if seconds == 30:
            calls.append(("sleep(30)", db.get_meta("auto.last")))
            lap_done.set()
            await asyncio.Event().wait()  # 취소될 때까지(둘째 바퀴 없음)
        return await real_sleep(seconds, *a, **k)

    def wrap(name: str, fn: Any) -> Any:
        def inner(*a: Any, **k: Any) -> Any:
            calls.append((name, db.get_meta("auto.last")))
            return fn(*a, **k)
        return inner

    monkeypatch.setattr(main_mod.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(app.state.paper2, "tick", wrap("paper2.tick", app.state.paper2.tick))
    monkeypatch.setattr(main_mod.updates, "announce", wrap("updates.announce", main_mod.updates.announce))
    monkeypatch.setattr(app.state.scheduler, "run_due", wrap("sched.run_due", app.state.scheduler.run_due))
    monkeypatch.setattr(main_mod, "live_tick", wrap("live_tick", main_mod.live_tick))
    monkeypatch.setattr(app.state.telegram, "poll", wrap("telegram.poll", app.state.telegram.poll))
    with CsrfClient(app) as c:
        assert lap_done.wait(10), calls
        assert c.get("/api/health").status_code == 200
    assert [n for n, _ in calls] == ["paper2.tick", "updates.announce", "sched.run_due", "live_tick", "telegram.poll",
                                     "sleep(30)"]
    # auto_tick(16:30 자동 확인)이 첫 호출 전에 이미 돌았어요(월요일 17:00 · 모의투자 없음 → 건너뜀)
    assert all(last == "2025-06-02" for _, last in calls)
    assert db.get_meta("auto.last_result") == "실행 중인 모의투자가 없어 건너뛰었어요"
    assert json.loads(db.get_meta("auto.ran_days") or "[]") == ["2025-06-02"]


def test_auto_tick_on_app_state(frozen: None, tmp_path: Path, fake_bars: FakeBars) -> None:
    """`app.state.auto_tick`(바깥 약속): 첫 호출 'skip'(모의투자 없음) · 같은 날 둘째 호출 None."""
    app = create_app(tmp_path / "data", bars_source=fake_bars, scrypt_n=2**12, scheduler=False, keyfile=False)
    assert app.state.auto_tick() == "skip"
    assert app.state.auto_tick() is None
    assert app.state.db.get_meta("auto.last") == "2025-06-02"


def test_sending_row_exists_when_fake_toss_receives_the_order(tmp_path: Path) -> None:
    """live.py `_send`(S9): 가짜 토스가 주문 POST를 받는 순간 DB에 같은 clientOrderId의 'sending' 행이 이미 있어요.
    순서가 어긋나면(토스 먼저 · 기록 나중) 행이 없어 실패해요."""
    from tests.test_live import World, morning, running

    w = World(tmp_path)
    seen: list[tuple[str, str | None]] = []
    server = w.server

    def spy(req: Any) -> Any:
        if req.method == "POST" and req.url.endswith("/api/v1/orders"):
            cid = json.loads(req.body)["clientOrderId"]
            row = w.db.one("SELECT status FROM orders WHERE client_order_id=?", (cid,))
            seen.append((cid, row["status"] if row else None))
        return server(req)

    w.client.transport = spy
    rid = running(w)
    out = morning(w, date(2026, 11, 3))
    assert out[0]["status"] == "sent"
    assert seen == [(f"q{rid}-20261103-005930-B-1", "sending")]
    assert w.orders()[0]["status"] == "sent"


# ── C. 화면 라우트 관측(시험이 부르지 않던 라우트) ──────────────────────────


def test_screen_routes_respond(app_client: Any) -> None:
    """자산 · 계획 · 기록 · 모의투자 · 소개 화면이 부르는 라우트(운용 전 상태)."""
    setup_owner(app_client)
    about = app_client.get("/api/about").json()
    assert about["version"] == "0.2"
    live = app_client.get("/api/live").json()
    assert live["running"] is False
    screen = app_client.get("/api/live/screen").json()
    assert screen["running"] is False and "todos" in screen
    sid = app_client.post("/api/v2/strategies", json={"body": _body()}).json()["id"]
    vid = app_client.get(f"/api/v2/strategies/{sid}").json()["version"]["id"]
    pv = app_client.get(f"/api/live/preview?version_id={vid}").json()
    assert pv["ok"] is False and [c["key"] for c in pv["checks"]]
    assert app_client.get("/api/v2/paper").json() == {"runs": []}
    assert app_client.post("/api/v2/paper/check").json() == {"advanced": []}
    r = app_client.post("/api/live/pause")  # 로그인만(SPEC 7-4)
    assert r.status_code == 200 and r.json()["paused"] is True


# ── D. 하루 흐름 뼈대(창 방식 · 점검 실패 = 다시 시도) ─────────────────────


def test_dayflow_normal_day_has_the_windows(tmp_path: Path) -> None:
    from tests.baseline import dayflow

    day = dayflow.run_day("normal", tmp_path / "normal")
    s = day["summary"]
    assert day["laps"] == 2880
    assert s["tick_first_last"]["reconcile"] == ["08:20:00", "08:20:00"]
    assert s["precheck_times"] == ["08:30:00"] and s["precheck_messages"][0]["text"].startswith("장 시작 전 점검 · 통과")
    assert s["tick_first_last"]["open"] == ["08:35:00", "08:35:00"]
    assert s["tick_first_last"]["after_open"] == ["09:01:00", "09:01:00"]
    assert s["intraday_minutes"] == 380 and s["tick_first_last"]["intraday"] == ["09:01:00", "15:20:00"]  # 1분마다
    assert s["sched"] == {"paper_check": ["20:10:00"], "live_check": ["20:10:00"]}
    kinds = [o["kind"] for ev in day["events"] for o in ev.get("db", {}).get("orders", {}).get("added", [])]
    assert kinds == ["open_buy", "intraday_protect"]


def test_dayflow_precheck_fail_then_retry_then_recover(tmp_path: Path) -> None:
    """08:30 실패(False) → 5분 뒤 다시 → 08:40 통과 → 바로 주문(08:30 ~ 08:50 창 · 5분마다)."""
    from tests.baseline import dayflow

    day = dayflow.run_day("precheck_fail_recover", tmp_path / "fail")
    s = day["summary"]
    assert s["precheck_times"] == ["08:30:00", "08:35:00", "08:40:00"]
    assert [m["text"][:14] for m in s["precheck_messages"]] == ["장 시작 전 점검 · 실패", "장 시작 전 점검 · 실패",
                                                                 "장 시작 전 점검 · 통과"]
    assert s["tick_first_last"]["open"] == ["08:40:00", "08:40:00"]
    todos = [t["kind"] for ev in day["events"] for t in ev.get("db", {}).get("todos", {}).get("added", [])]
    assert todos == ["precheck"]


def test_dayflow_precheck_exhausted_stops_at_the_window_end(tmp_path: Path) -> None:
    """08:30 ~ 08:50 창(`<=` 경계): 5번 모두 실패 → 08:55부터는 점검하지 않음 · 그날 시가 주문 0 · 보유가 없어 장중 감시할 것이 없음."""
    from tests.baseline import dayflow

    day = dayflow.run_day("precheck_exhausted", tmp_path / "exhausted")
    s = day["summary"]
    assert s["precheck_times"] == ["08:30:00", "08:35:00", "08:40:00", "08:45:00", "08:50:00"]
    assert all(m["text"].startswith("장 시작 전 점검 · 실패") for m in s["precheck_messages"])
    assert "open" not in s["tick_counts"]
    assert not [o for ev in day["events"] for o in ev.get("db", {}).get("orders", {}).get("added", [])]


def test_engine_cases_cover_notes_skips_and_paper_flow() -> None:
    from tests.baseline import engine_cases

    res = engine_cases.run_all()
    assert res["by_kind"] == {"backtest": 11, "backtest_v2": 3, "engine_rules": 5, "live": 7, "paper": 7}
    assert "notes_per_missing" in res["with_notes"] and len(res["with_notes"]) >= 5
    assert {"skip_one_share", "rules_daily_loss", "rules_forty_orders"} <= set(res["with_skipped"])
    by_id = {c["id"]: c for c in res["cases"]}
    assert by_id["notes_per_missing"]["notes"] == {"111111": ["③ PER 값 없음"] * 5}
    assert by_id["skip_one_share"]["skipped"][0]["why"] == "매수 안 함 · 1주도 못 사요"
    assert by_id["rules_forty_orders"]["skipped"][0]["why"] == "매수 안 함 · 하루 주문 40건"
    paper = by_id["paper_first_check_2010"]
    assert [(t["d"], t["side"]) for t in paper["trades"]] == [("2026-03-04", "buy")]
    assert [s["step"] for s in paper["trail"]] == ["start", "tick", "tick", "tick", "tick"]
