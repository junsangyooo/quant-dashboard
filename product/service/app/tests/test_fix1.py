"""검토 지적 고친 것: 첫 확인 · 첫 체결 규칙, 잠그기 = 전체 잠금, 다시 켠 뒤 안내, 일봉 없는 코드."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import strategy as st
from app.main import create_app
from app.market import KST
from app.paper import first_schedule
from tests.helpers import legacy, new_strategy
from tests.conftest import PASSWORD, FakeBars, FakeIp, FakeToss, make_bars, setup_owner, wave
from tests.test_engine_paper import Now, _paper, _version, event_body

# 2025-06-02(월) … 일봉은 2024-01-01(월)부터 평일마다
CLOSES = [10, 10, 10, 9, 13, 13, 15, 15]


def _bars_until(last: str) -> FakeBars:
    allb = make_bars(wave(400, 1000, 100, 20), start=date(2024, 1, 1))
    return FakeBars({"111111": [b for b in allb if b["d"] <= last]})


def kst(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=KST)


@pytest.mark.parametrize(
    ("now", "last", "check_now", "check_d", "fill_d"),
    [
        # 평일 09:00 전: 어제 일봉으로 바로 확인 → 오늘 시가
        ("2025-06-03T08:10:00", "2025-06-02", True, "2025-06-03", "2025-06-03"),
        # 평일 09:00~15:50: 오늘 시가는 지났다 → 오늘 일봉으로 첫 확인(16:30) → 다음 거래일 시가
        ("2025-06-03T10:00:00", "2025-06-02", False, "2025-06-03", "2025-06-04"),
        # 15:50 뒤: 오늘 일봉으로 바로 확인 → 다음 거래일 시가
        ("2025-06-03T17:21:00", "2025-06-03", True, "2025-06-03", "2025-06-04"),
        # 금요일 15:50 뒤 → 월요일 시가
        ("2025-06-06T17:00:00", "2025-06-06", True, "2025-06-06", "2025-06-09"),
        # 주말: 금요일 일봉으로 바로 확인 → 월요일 시가
        ("2025-06-07T11:00:00", "2025-06-06", True, "2025-06-07", "2025-06-09"),
    ],
)
def test_first_schedule(now: str, last: str, check_now: bool, check_d: str, fill_d: str) -> None:
    f = first_schedule(kst(now), date.fromisoformat(last))
    assert (f["check_now"], f["check_d"], f["fill_d"]) == (check_now, check_d, fill_d)
    # 첫 체결은 시작한 시각 뒤에 열리는 시가다
    assert datetime.combine(date.fromisoformat(f["fill_d"]), datetime.min.time(), KST) + timedelta(hours=9) > kst(now)


def _vid(paper) -> int:  # type: ignore[no-untyped-def]
    return int(paper.db.one("SELECT MAX(id) AS v FROM versions")["v"])


def _start(tmp_path: Path, now: str, last: str):  # type: ignore[no-untyped-def]
    clock = Now(kst(now))
    db, paper = _paper(tmp_path, _bars_until(last), clock)
    body = event_body()
    body["slots"]["universe"][0]["params"]["symbols"] = ["111111"]
    vid = _version(db, body)
    return db, paper, clock, paper.start(vid, 1_000_000)


def test_start_intraday_makes_no_plan_and_first_fill_is_after_start(tmp_path: Path) -> None:
    db, paper, clock, res = _start(tmp_path, "2025-06-03T10:00:00", "2025-06-02")
    assert res["plans"] == [] and res["first"]["check_now"] is False
    assert res["first"]["check_d"] == "2025-06-03" and res["first"]["fill_d"] == "2025-06-04"
    assert paper.preview(_vid(paper))["fill_d"] == "2025-06-04"  # 창과 서버가 같은 값
    assert paper.plan()["last"] is None  # 아직 확인 전
    # 그날 16:30 뒤 첫 확인: 6/3 시가에는 아무것도 체결되지 않는다
    paper.market.source.data["111111"] = _bars_until("2025-06-03").data["111111"]
    clock.t = kst("2025-06-03T16:40:00")
    paper._clock["t"] += 3600  # type: ignore[attr-defined]
    out = paper.judge("auto")
    assert out["new_days"] == 1 and out["trades"] == []
    assert all(p["judged"] == "2025-06-03" for p in out["plans"])
    assert paper.run_view(res["run_id"])["first"]["fill_d"] == "2025-06-04"


def test_start_after_close_checks_now(tmp_path: Path) -> None:
    _, paper, _, res = _start(tmp_path, "2025-06-03T17:21:00", "2025-06-03")
    assert res["first"]["check_now"] is True and res["judged"] == "2025-06-03"
    assert res["first"]["fill_d"] == "2025-06-04"
    assert paper.plan()["last"]["how"] == "start"


def test_start_weekend_checks_friday(tmp_path: Path) -> None:
    _, paper, _, res = _start(tmp_path, "2025-06-07T11:00:00", "2025-06-06")
    assert res["judged"] == "2025-06-06" and res["first"]["fill_d"] == "2025-06-09"
    assert paper.preview(_vid(paper))["fill_d"] == "2025-06-09"


def test_preview_api_matches_start(app_client) -> None:  # type: ignore[no-untyped-def]
    from tests.test_engine_paper import _api_body

    setup_owner(app_client)
    sid = new_strategy(app_client, "창", "event")
    vid = app_client.post(f"/api/strategies/{sid}/versions", json={"body": _api_body()}).json()["version_id"]
    pre = app_client.get(f"/api/paper/preview?version_id={vid}").json()
    got = app_client.post("/api/paper/start", json={"version_id": vid, "cash": 10_000_000}).json()["first"]
    assert pre == got  # 월요일 17:00 → 바로 확인, 화요일 시가


def test_lock_ends_every_session_and_clears_the_key(tmp_path: Path, fake_toss: FakeToss, fake_bars: FakeBars, fake_ip: FakeIp) -> None:
    app = create_app(tmp_path / "d", bars_source=fake_bars, toss_transport=lambda: fake_toss, ip_fetch=fake_ip,
                     scrypt_n=2**12, scheduler=False, now=lambda: kst("2025-06-02T17:00:00"))
    with TestClient(app) as a, TestClient(app) as b:
        setup_owner(a)
        assert b.post("/api/login", json={"password": PASSWORD}).status_code == 200
        assert a.get("/api/state").json()["unlocked"] is True
        a.post("/api/logout")
        assert app.state.vault.unlocked is False
        assert b.get("/api/home").status_code == 401  # 다른 세션도 끝났다
        assert a.get("/api/state").json()["restarted"] is False  # 잠그기 뒤에는 '다시 켰어요' 안내 없음


def test_restarted_flag_until_first_login(tmp_path: Path, fake_bars: FakeBars) -> None:
    data = tmp_path / "d"
    with TestClient(create_app(data, bars_source=fake_bars, scrypt_n=2**12, scheduler=False)) as c:
        assert c.get("/api/state").json()["restarted"] is False  # 아직 계정 없음
        setup_owner(c)
        assert c.get("/api/state").json()["restarted"] is False
    with TestClient(create_app(data, bars_source=fake_bars, scrypt_n=2**12, scheduler=False)) as c:
        assert c.get("/api/state").json()["restarted"] is True  # 다시 켠 뒤 첫 로그인 전
        c.post("/api/login", json={"password": PASSWORD})
        assert c.get("/api/state").json()["restarted"] is False


def test_unknown_code_is_not_a_network_error(app_client, fake_bars: FakeBars) -> None:  # type: ignore[no-untyped-def]
    from tests.test_engine_paper import _api_body

    setup_owner(app_client)
    sid = new_strategy(app_client, "코드", "event")
    body = _api_body()
    body["slots"]["universe"][0]["params"]["symbols"] = ["005930", "999999"]
    vid = app_client.post(f"/api/strategies/{sid}/versions", json={"body": body}).json()["version_id"]
    req = {"version_id": vid, "start": "2024-02-01", "end": "2025-05-30", "cash": 10_000_000}
    r = app_client.post("/api/backtest", json=req)
    assert r.status_code == 400 and r.json()["kind"] == "symbol"
    assert r.json()["error"] == "일봉이 없는 종목 코드가 있어요 · 999999 · 종목 코드를 확인해 주세요"
    r = app_client.post("/api/paper/start", json={"version_id": vid, "cash": 10_000_000})
    assert r.status_code == 400 and "999999" in r.json()["error"]
    # 네트워크가 끊기면 지수도 안 받히니 '시세를 받지 못했어요'
    fake_bars.down = True
    body["slots"]["universe"][0]["params"]["symbols"] = ["000660"]
    vid2 = app_client.post(f"/api/strategies/{sid}/versions", json={"body": body}).json()["version_id"]
    r = app_client.post("/api/backtest", json={**req, "version_id": vid2})
    assert r.status_code == 502 and r.json()["kind"] == "market"


def test_target_sell_reasons_are_split() -> None:
    body = legacy("target", "반반")
    body["slots"]["universe"][0]["params"]["symbols"] = ["111111"]
    body["slots"]["weight"][1]["params"]["n"] = 1
    rows = st.reason_rows(body, ["필터 미충족", "신호 미충족", "상위 3종목 이탈", "리밸런싱"])
    assert [(r["circle"], r["display"]) for r in rows] == [
        ("③", "필터 미충족"),
        ("②", "신호 미충족"),
        ("④", "종목 선정 · 상위 3종목 이탈"),
        ("⑦", "비중 · 리밸런싱"),
    ]


# ── 휴장 · 야후 지연(검토 2차) ──────────────────────────────────────────


def _gap_bars(last: str, missing: set[str]) -> FakeBars:
    allb = make_bars(wave(400, 1000, 100, 20), start=date(2024, 1, 1))
    return FakeBars({"111111": [b for b in allb if b["d"] <= last and b["d"] not in missing]})


def _start_gap(tmp_path: Path, now: str, last: str, missing: set[str]):  # type: ignore[no-untyped-def]
    clock = Now(kst(now))
    db, paper = _paper(tmp_path, _gap_bars(last, missing), clock)
    # 목표 비중 템플릿: 신호 없이 날마다 비중을 맞추니 늘 매수 계획이 나온다(첫 체결 날짜만 본다)
    body = legacy("target", "반반")
    body["slots"]["universe"][0]["params"]["symbols"] = ["111111"]
    body["slots"]["weight"][1]["params"]["n"] = 1
    assert st.validate(body) == []
    vid = _version(db, body)
    pre = paper.preview(vid)
    res = paper.start(vid, 1_000_000)
    return paper, clock, pre, res


def _advance(paper, clock, now: str, last: str, missing: set[str]):  # type: ignore[no-untyped-def]
    paper.market.source.data["111111"] = _gap_bars(last, missing).data["111111"]
    clock.t = kst(now)
    paper._clock["t"] += 3600
    # 캐시는 '최근 7일' 판단에 실제 오늘을 쓴다: 시험 날짜(2025)에서는 받아 둔 범위를 지워 다시 받게 한다
    paper.db.run("DELETE FROM bar_meta")
    return paper.judge("auto")


@pytest.mark.parametrize(
    ("now", "last", "fill_d"),
    [
        # 휴장(금 6/6) 다음 월요일 08:30 시작: 목요일 일봉으로 바로 확인 → 월요일 시가
        ("2025-06-09T08:30:00", "2025-06-05", "2025-06-09"),
        # 야후 지연: 화요일 17:00인데 화요일 일봉이 아직 없다 → 월요일 일봉으로 바로 확인 → 수요일 시가
        ("2025-06-03T17:00:00", "2025-06-02", "2025-06-04"),
    ],
)
def test_schedule_with_missing_weekday(now: str, last: str, fill_d: str) -> None:
    f = first_schedule(kst(now), date.fromisoformat(last))
    assert f["check_now"] is True and f["bar_d"] == last and f["fill_d"] == fill_d
    # 첫 확인 시각은 시작 시각보다 앞서지 않는다
    assert f"{f['check_d']}T{f['check_time']}" >= now[:16]


def test_holiday_monday_before_open(tmp_path: Path) -> None:
    paper, clock, pre, res = _start_gap(tmp_path, "2025-06-09T08:30:00", "2025-06-05", {"2025-06-06"})
    assert pre == res["first"]  # 미리 보기 = 시작
    assert res["judged"] == "2025-06-05" and res["first"]["fill_d"] == "2025-06-09"
    assert res["plans"]  # 바로 확인해서 계획이 있다
    out = _advance(paper, clock, "2025-06-09T16:40:00", "2025-06-09", {"2025-06-06"})
    assert out["trades"] and {t["d"] for t in out["trades"]} == {"2025-06-09"}


def test_yahoo_late_bar_never_fills_before_start(tmp_path: Path) -> None:
    paper, clock, pre, res = _start_gap(tmp_path, "2025-06-03T17:00:00", "2025-06-02", set())
    assert pre == res["first"] and res["first"]["fill_d"] == "2025-06-04"
    # 화요일 일봉이 18:00에 늦게 온다: 화요일 시가(시작 전)에는 체결하지 않는다
    out = _advance(paper, clock, "2025-06-03T18:00:00", "2025-06-03", set())
    assert out["new_days"] == 1 and out["trades"] == []
    out = _advance(paper, clock, "2025-06-04T16:40:00", "2025-06-04", set())
    assert out["trades"] and {t["d"] for t in out["trades"]} == {"2025-06-04"}


def test_holiday_during_wait_checks_late(tmp_path: Path) -> None:
    # 금요일(휴장) 11:00 시작 → 16:30에 그날 일봉이 끝내 없다 → 목요일 일봉으로 확인 → 월요일 시가
    paper, clock, pre, res = _start_gap(tmp_path, "2025-06-06T11:00:00", "2025-06-05", set())
    assert res["plans"] == [] and res["first"]["check_d"] == "2025-06-06"
    out = _advance(paper, clock, "2025-06-06T16:31:00", "2025-06-05", set())
    assert out["new_days"] == 0 and out["plans"]
    first = paper.first_of(res["run_id"])
    assert first["fill_d"] == "2025-06-09" and first["check_time"] == "16:31"
    out = _advance(paper, clock, "2025-06-09T16:40:00", "2025-06-09", {"2025-06-06"})
    assert out["trades"] and {t["d"] for t in out["trades"]} == {"2025-06-09"}
    # 계획의 체결일도 같은 값
    assert all(p["fill_d"] >= "2025-06-09" for p in paper.plan()["plans"])


def test_lock_drops_the_toss_client(app_client, fake_toss: FakeToss) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    app_client.put("/api/connect/toss", json={"client_id": FakeToss.CLIENT_ID, "client_secret": FakeToss.SECRET})
    assert app_client.post("/api/connect/toss/check").json()["result"]["ok"] is True
    conns = app_client.app_ref.state.connections
    client = conns._client
    assert client is not None and client._token
    app_client.post("/api/logout")
    assert conns._client is None and client._token is None and client._account is None
    # 키 삭제 · 변경도 연결 객체를 버린다
    app_client.post("/api/login", json={"password": PASSWORD})
    app_client.post("/api/connect/toss/check")
    c2 = conns._client
    app_client.put("/api/connect/toss", json={"client_id": FakeToss.CLIENT_ID, "client_secret": FakeToss.SECRET})
    assert conns._client is None and c2._token is None
    app_client.post("/api/connect/toss/check")
    c3 = conns._client
    app_client.delete("/api/connect/toss")
    assert conns._client is None and c3._token is None


# ── 마지막 확인 지적(3차) ─────────────────────────────────────────────────────


def test_session_expiry_drops_the_toss_client(app_client, fake_toss: FakeToss) -> None:  # type: ignore[no-untyped-def]
    import time as _time

    setup_owner(app_client)
    app_client.put("/api/connect/toss", json={"client_id": FakeToss.CLIENT_ID, "client_secret": FakeToss.SECRET})
    app_client.post("/api/connect/toss/check")
    conns = app_client.app_ref.state.connections
    vault = app_client.app_ref.state.vault
    client = conns._client
    assert client is not None and client._token
    vault.clock = lambda: _time.time() + 13 * 3600  # 세션 12시간이 지났다
    assert vault.unlocked is False  # 키를 지우는 길(_purge)이 연결 객체도 버린다
    assert conns._client is None and client._token is None and client._account is None


def test_last_session_logout_drops_the_toss_client(app_client, fake_toss: FakeToss) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    app_client.put("/api/connect/toss", json={"client_id": FakeToss.CLIENT_ID, "client_secret": FakeToss.SECRET})
    app_client.post("/api/connect/toss/check")
    conns = app_client.app_ref.state.connections
    vault = app_client.app_ref.state.vault
    client = conns._client
    vault.logout(app_client.cookies.get("qm_session"))  # 마지막 세션 끝
    assert vault.unlocked is False and conns._client is None and client._token is None


def test_fill_notice_knows_days_the_app_was_off(tmp_path: Path, fake_bars: FakeBars) -> None:
    from tests.test_engine_paper import _api_body

    full = {k: list(v) for k, v in fake_bars.data.items()}
    for k in fake_bars.data:  # 일봉은 6/2(월)까지만 있다
        fake_bars.data[k] = [b for b in full[k] if b["d"] <= "2025-06-02"]
    clock = {"t": kst("2025-06-02T17:00:00")}  # 월 17:00
    app = create_app(tmp_path / "d", bars_source=fake_bars, scrypt_n=2**12, scheduler=False, now=lambda: clock["t"])
    with TestClient(app) as c:
        setup_owner(c)
        sid = new_strategy(c, "끔", "event")
        vid = c.post(f"/api/strategies/{sid}/versions", json={"body": _api_body()}).json()["version_id"]
        c.post("/api/paper/start", json={"version_id": vid, "cash": 10_000_000})
        tick = app.state.auto_tick
        assert tick() == "ran"  # 월요일 16:30 뒤: 앱이 켜져 있었다
        # 화 · 수에 앱이 꺼져 있었다 → 목요일에 사흘치를 이어서 채움
        for k in fake_bars.data:
            fake_bars.data[k] = [b for b in full[k] if b["d"] <= "2025-06-05"]
        app.state.db.run("DELETE FROM bar_meta")
        clock["t"] = kst("2025-06-05T16:40:00")
        assert tick() == "ran"
        fill = c.get("/api/home").json()["auto"]["last_fill"]
        assert fill["new_days"] == 3 and fill["off_days"] == ["2025-06-03", "2025-06-04"]


def test_fill_notice_no_off_day_when_only_the_bar_was_late(tmp_path: Path, fake_bars: FakeBars) -> None:
    from tests.test_engine_paper import _api_body

    full = {k: list(v) for k, v in fake_bars.data.items()}
    for k in fake_bars.data:  # 일봉은 6/2(월)까지만 있다
        fake_bars.data[k] = [b for b in full[k] if b["d"] <= "2025-06-02"]
    clock = {"t": kst("2025-06-02T17:00:00")}
    app = create_app(tmp_path / "d", bars_source=fake_bars, scrypt_n=2**12, scheduler=False, now=lambda: clock["t"])
    with TestClient(app) as c:
        setup_owner(c)
        sid = new_strategy(c, "늦음", "event")
        vid = c.post(f"/api/strategies/{sid}/versions", json={"body": _api_body()}).json()["version_id"]
        c.post("/api/paper/start", json={"version_id": vid, "cash": 10_000_000})
        tick = app.state.auto_tick
        clock["t"] = kst("2025-06-03T16:40:00")
        assert tick() == "ran"  # 화요일: 앱은 켜져 있었는데 일봉이 아직 없다
        for k in fake_bars.data:  # 화 · 수 일봉이 수요일에 같이 온다
            fake_bars.data[k] = [b for b in full[k] if b["d"] <= "2025-06-04"]
        app.state.db.run("DELETE FROM bar_meta")
        clock["t"] = kst("2025-06-04T16:40:00")
        assert tick() == "ran"
        fill = c.get("/api/home").json()["auto"]["last_fill"]
        assert fill["new_days"] == 2 and fill["off_days"] == []  # 꺼져 있던 날은 없다
