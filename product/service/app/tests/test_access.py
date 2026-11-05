"""T-51 접속 보안: Host · Origin · CSRF · SameSite=Strict · 127.0.0.1에만 묶기 · 한 번만 실행 · 스케줄러."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.store.db import DB
from app.main import create_app, ts_names_from
from app.domain.markets.kr import KST
from app.run.data import Calendar
from app.run.scheduler import Scheduler
from app.serve import AlreadyRunning, acquire_lock
from tests.conftest import PASSWORD, CsrfClient, FakeBars, FakeIp, FakeToss, setup_owner

APP = Path(__file__).resolve().parents[1]
TS = "quant.tail1234.ts.net"


def make(tmp_path: Path, **kw: Any) -> Any:
    return create_app(tmp_path / "data", scrypt_n=2**12, scheduler=False, keyfile=False, port=8765, **kw)


# ── Host · Origin ──────────────────────────────────────────────────────────


def test_hosts(tmp_path: Path) -> None:
    c = CsrfClient(make(tmp_path, ts_names=[TS]))
    ok = {"127.0.0.1:8765", "localhost:8765", TS, f"{TS}:443"}
    for h in ok:
        assert c.get("/api/health", headers={"host": h}).status_code == 200, h
    for h in ["127.0.0.1:9999", "evil.example", "quant.other.ts.net", f"{TS}.evil.com", "0.0.0.0:8765",
              "192.168.0.10:8765", ""]:
        assert c.get("/api/health", headers={"host": h}).status_code == 403, h


def test_unregistered_ts_name_is_refused(tmp_path: Path) -> None:
    c = CsrfClient(make(tmp_path))  # 등록한 이름 없음
    assert c.get("/api/health", headers={"host": TS}).status_code == 403


def test_ts_name_from_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANT_TS_NAME", f" {TS.upper()} , evil.com, a.ts.net.evil.com")
    c = CsrfClient(make(tmp_path))
    assert c.get("/api/health", headers={"host": TS}).status_code == 200
    assert c.get("/api/health", headers={"host": "evil.com"}).status_code == 403
    assert ts_names_from("quant.tail1.ts.net,-bad-.ts.net,ts.net, x..ts.net") == ["quant.tail1.ts.net"]


def test_origins(tmp_path: Path) -> None:
    c = CsrfClient(make(tmp_path, ts_names=[TS]))
    setup_owner(c)
    body = {"password": PASSWORD, "action": "live_start"}
    for o in ["http://evil.example", f"https://{TS}.evil.com", f"http://{TS}", "null", "http://127.0.0.1:9999"]:
        r = c.post("/api/confirm", json=body, headers={"origin": o})
        assert r.status_code == 403, o
    for o in [f"https://{TS}", "http://127.0.0.1:8765", "http://localhost:8765"]:
        assert c.post("/api/confirm", json=body, headers={"origin": o}).status_code == 200, o


# ── CSRF · 쿠키 ────────────────────────────────────────────────────────────


def test_csrf_needed_for_changes(tmp_path: Path) -> None:
    c = TestClient(make(tmp_path))  # 머리글을 붙이지 않는 클라이언트
    r = c.post("/api/setup", json={"password": PASSWORD, "password2": PASSWORD, "adult": True, "terms": True})
    assert r.status_code == 200
    cookies = r.headers.get_list("set-cookie")
    session = next(x for x in cookies if x.startswith("qm_session="))
    csrf = next(x for x in cookies if x.startswith("qm_csrf="))
    assert "HttpOnly" in session and "SameSite=strict" in session
    assert "HttpOnly" not in csrf and "SameSite=strict" in csrf
    token = c.cookies.get("qm_csrf")
    assert token
    url, new = "/api/confirm", {"password": PASSWORD, "action": "live_start"}
    # 읽기는 그대로
    assert c.get("/api/v2/strategies").status_code == 200
    # 바꾸기: 없음 · 틀림 → 403, 맞음 → 통과
    r = c.post(url, json=new)
    assert r.status_code == 403 and r.json()["csrf"] is True
    assert c.post(url, json=new, headers={"x-csrf-token": "0" * 64}).status_code == 403
    assert c.delete("/api/connect/dart").status_code == 403
    assert c.post(url, json=new, headers={"x-csrf-token": token}).status_code == 200
    # 다시 로그인하면 새 값 · 옛 값은 안 돼요
    c.post("/api/logout", headers={"x-csrf-token": token})
    c.post("/api/login", json={"password": PASSWORD})
    assert c.cookies.get("qm_csrf") != token
    assert c.post(url, json=new, headers={"x-csrf-token": token}).status_code == 403


def test_csrf_is_per_process(tmp_path: Path) -> None:
    a = CsrfClient(make(tmp_path))
    setup_owner(a)
    b_app = make(tmp_path)
    # 다른 프로세스(재시작)는 세션도 CSRF 키도 새로: 옛 쿠키로는 아무것도 못 해요
    b = TestClient(b_app, cookies=dict(a.cookies))
    assert b.post("/api/v2/strategies", json={}, headers={"x-csrf-token": a.cookies.get("qm_csrf") or ""}).status_code == 401


# ── 127.0.0.1에만 · 한 번만 실행 ─────────────────────────────────────────────


def _listening(port: int) -> list[str]:
    """/proc/net/tcp(6)에서 그 포트로 LISTEN(0A)인 주소들."""
    out = []
    for name in ("tcp", "tcp6"):
        p = Path("/proc/net") / name
        if not p.exists():
            continue
        for line in p.read_text().splitlines()[1:]:
            cols = line.split()
            local, state = cols[1], cols[3]
            addr, hexport = local.rsplit(":", 1)
            if state == "0A" and int(hexport, 16) == port:
                out.append(f"{name}:{addr}")
    return out


def _get(port: int, path: str) -> str:
    """루프백 소켓으로 직접(시험은 create_connection을 막아 둬요)."""
    import socket

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(("127.0.0.1", port))
        s.sendall(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nConnection: close\r\n\r\n".encode())
        chunks = []
        while True:
            b = s.recv(65536)
            if not b:
                break
            chunks.append(b)
        return b"".join(chunks).decode("utf-8", "replace")
    finally:
        s.close()


def _free_port() -> int:
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _serve(data: Path, port: int, *extra: str) -> subprocess.Popen[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("QUANT_LIVE_TRANSPORT", "QUANT_TS_NAME")}
    return subprocess.Popen([sys.executable, "-m", "app.serve", "--port", str(port), "--data", str(data), *extra],
                            cwd=APP, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


@pytest.mark.skipif(not Path("/proc/net/tcp").exists(), reason="리눅스 /proc 필요")
def test_serve_binds_loopback_only_and_runs_once(tmp_path: Path) -> None:
    port = _free_port()
    data = tmp_path / "data"
    first = _serve(data, port)
    try:
        for _ in range(100):
            try:
                assert '"app":"quant-mvp"' in _get(port, "/api/health")
                break
            except OSError:
                time.sleep(0.1)
        else:
            raise AssertionError(first.stderr.read() if first.stderr else "no start")
        # 열린 곳은 127.0.0.1 하나(0100007F) · 공개 인터페이스 · IPv6 0개
        assert _listening(port) == ["tcp:0100007F"]
        # 두 번째 실행은 잠금 파일로 거절
        second = _serve(data, _free_port())
        _, err = second.communicate(timeout=60)
        assert second.returncode == 3 and "이미 실행 중이에요" in err
        assert (data / "app.lock").stat().st_mode & 0o777 == 0o600
    finally:
        first.terminate()
        first.communicate(timeout=30)


def test_serve_refuses_other_hosts(tmp_path: Path) -> None:
    for host in ("0.0.0.0", "::", "192.168.0.10", "localhost.evil"):
        p = _serve(tmp_path / "d", _free_port(), "--host", host)
        _, err = p.communicate(timeout=60)
        assert p.returncode != 0 and "127.0.0.1에만 묶어요" in err
    assert not (tmp_path / "d" / "app.lock").exists()


def test_lock_released_after_exit(tmp_path: Path) -> None:
    fd = acquire_lock(tmp_path)
    with pytest.raises(AlreadyRunning):
        acquire_lock(tmp_path)
    os.close(fd)  # 프로세스가 끝난 것과 같아요
    os.close(acquire_lock(tmp_path))


# ── 스케줄러(market-calendar) ──────────────────────────────────────────────


class Clock:
    def __init__(self, t: datetime) -> None:
        self.t = t

    def __call__(self) -> datetime:
        return self.t


def _cal(db: DB, d: date, open_: bool, start: str | None = "09:00") -> None:
    st = datetime.combine(d, datetime.min.time(), KST).replace(hour=int(start[:2]), minute=int(start[3:])) \
        if open_ and start else None
    db.set_meta(f"cal.{d.isoformat()}", json.dumps({"open": open_, "start": st.isoformat() if st else None}))


def test_scheduler_follows_market_calendar(tmp_path: Path) -> None:
    db = DB(tmp_path / "s.db")
    mon, tue, wed = date(2026, 11, 2), date(2026, 11, 3), date(2026, 11, 4)
    _cal(db, mon, True)
    _cal(db, tue, False)  # 쉬는 날(토스 달력)
    _cal(db, wed, True, "10:00")  # 1시간 늦게 여는 날
    clock = Clock(datetime(2026, 11, 2, 20, 9, tzinfo=KST))
    ran: list[str] = []
    s = Scheduler(db, Calendar(db, None), clock)
    s.add("check", 20, 10, lambda: ran.append("check"))
    s.add("open_order", 8, 35, lambda: ran.append("open"), follow_open=True)
    assert s.run_due() == ["open_order"]  # 월 08:35는 이미 지남 → 한 번
    assert s.run_due() == []  # 20:09: 확인 전
    clock.t = datetime(2026, 11, 2, 20, 10, tzinfo=KST)
    assert s.run_due() == ["check"]
    assert s.run_due() == []  # 하루 한 번
    # 다시 켜도(새 스케줄러) 같은 날은 다시 안 돌아요
    s2 = Scheduler(db, Calendar(db, None), clock)
    s2.add("check", 20, 10, lambda: ran.append("check"))
    assert s2.run_due() == []
    # 쉬는 날은 아무것도
    clock.t = datetime(2026, 11, 3, 21, 0, tzinfo=KST)
    assert s.run_due() == []
    # 늦게 여는 날: 08:35 주문이 09:35로
    clock.t = datetime(2026, 11, 4, 9, 34, tzinfo=KST)
    assert "open_order" not in s.due()
    clock.t = datetime(2026, 11, 4, 9, 35, tzinfo=KST)
    assert s.run_due() == ["open_order"]
    assert ran == ["open", "check", "open"]


def test_scheduler_retries_failed_job(tmp_path: Path) -> None:
    db = DB(tmp_path / "s.db")
    _cal(db, date(2026, 11, 2), True)
    clock = Clock(datetime(2026, 11, 2, 20, 10, tzinfo=KST))
    calls = []

    def flaky() -> None:
        calls.append(clock.t)
        if len(calls) == 1:
            raise RuntimeError("down")

    s = Scheduler(db, Calendar(db, None), clock)
    s.add("check", 20, 10, flaky)
    assert s.run_due() == []
    clock.t += timedelta(minutes=5)
    assert s.run_due() == []  # 10분 안에는 다시 안 해요
    clock.t += timedelta(minutes=5)
    assert s.run_due() == ["check"]
    assert len(calls) == 2


def test_app_scheduler_has_paper_check(tmp_path: Path) -> None:
    app = make(tmp_path)
    assert [j.name for j in app.state.scheduler.jobs] == ["paper_check", "live_check"]


# ── 설치 위치 · Tailscale 상태(V2-05 · V2-06 · V2-56) ───────────────────────


def test_place_and_tailscale(tmp_path: Path) -> None:
    from tests.conftest import confirm

    c = CsrfClient(make(tmp_path, ts_names=[TS]))
    setup_owner(c)
    v = c.get("/api/access").json()
    assert v["place"] is None and v["tailscale"] == {"ok": True, "name": TS, "address": f"https://{TS}"}
    assert c.put("/api/access/place", json={"place": "laptop"}).status_code == 400
    assert c.put("/api/access/place", json={"place": "server"}).json()["place_name"] == "서버(클라우드 · 고정 IP)"
    assert c.put("/api/access/place", json={"place": "server"}).status_code == 200  # 같은 값
    r = c.put("/api/access/place", json={"place": "pc"})
    assert r.status_code == 403 and r.json()["action"] == "install_place"
    r = c.put("/api/access/place", json={"place": "pc"}, headers=confirm(c, "install_place"))
    assert r.json()["place"] == "pc"
    c2 = CsrfClient(make(tmp_path / "b"))
    setup_owner(c2)
    assert c2.get("/api/access").json()["tailscale"]["ok"] is False


# ── 공인 IP · 바깥 전송 · 화면 파일 내주기(P1-03에서 `test_mvp_api.py`에서 옮김 · 단언 그대로) ─────────────


def test_public_ip_only_when_asked(app_client, fake_ip: FakeIp, fake_toss: FakeToss) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    # 다른 화면 API를 불러도 공인 IP 서비스는 부르지 않는다
    for path in ("/api/connect",):  # P1-03: 지운 MVP 라우트(/api/home · /api/plan · /api/strategies)는 뺌
        app_client.get(path)
    assert fake_ip.calls == []
    r = app_client.post("/api/public-ip")
    assert r.status_code == 200 and r.json() == {"ip": "123.45.67.89"}
    assert fake_ip.calls == ["https://api.ipify.org?format=json"]
    assert fake_toss.calls == []  # 토스는 부르지 않는다
    fake_ip.down = True
    r = app_client.post("/api/public-ip")
    assert r.status_code == 502 and "공인 IP" in r.json()["error"]
    fake_ip.down = False
    fake_ip.body = b"<html>"
    assert app_client.post("/api/public-ip").status_code == 502


def test_public_ip_needs_login(app_client, fake_ip: FakeIp) -> None:  # type: ignore[no-untyped-def]
    assert app_client.post("/api/public-ip").status_code == 401
    assert fake_ip.calls == []


def test_offline_env_never_reaches_out(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MVP_TOSS_OFFLINE", "1")
    app = create_app(tmp_path / "d", bars_source=FakeBars(), scrypt_n=2**12, scheduler=False)
    with CsrfClient(app) as c:
        setup_owner(c)
        r = c.post("/api/public-ip")
        assert r.status_code == 502


def test_serves_built_screens(tmp_path: Path, fake_bars: FakeBars, monkeypatch: pytest.MonkeyPatch) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>quant</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("nope", encoding="utf-8")
    monkeypatch.setenv("MVP_WEB_DIST", str(dist))
    app = create_app(tmp_path / "d", bars_source=fake_bars, scrypt_n=2**12, scheduler=False)
    with CsrfClient(app) as c:
        assert c.get("/").text.startswith("<!doctype html>")
        assert c.get("/plan").text.startswith("<!doctype html>")  # 화면 주소는 index.html
        r = c.get("/assets/app.js")
        assert r.status_code == 200 and "immutable" in r.headers["cache-control"]
        assert "content-security-policy" in r.headers
        assert "nope" not in c.get("/../secret.txt").text
        assert "nope" not in c.get("/assets/../../secret.txt").text
        assert c.get("/api/nothing").status_code == 401  # API는 index.html로 넘어가지 않는다
