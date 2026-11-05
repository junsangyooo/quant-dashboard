"""비밀 값이 응답 · 로그 · DB 평문에 나오지 않는다. 입장 쿠키와 문 단속."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import pytest

from app.app import create_app
from app.domain.markets.kr import KST
from tests.conftest import PASSWORD, CsrfClient, FakeBars, FakeIp, FakeToss, confirm, setup_owner

SECRETS = [FakeToss.CLIENT_ID, FakeToss.SECRET, "DARTKEY-abcdef-998877"]
ACCOUNT = "12345671234"


def _no_secret(text: str) -> None:
    for s in SECRETS:
        assert s not in text
        assert s[:-4] not in text  # 끝 4자리 말고는 어떤 부분도
    assert ACCOUNT not in text


def test_state_and_cookie(app_client) -> None:  # type: ignore[no-untyped-def]
    r = app_client.get("/api/state")
    assert r.json()["setup"] is False
    assert app_client.get("/api/live").status_code == 401
    r = app_client.post(
        "/api/setup", json={"password": PASSWORD, "password2": PASSWORD, "adult": True, "terms": True}
    )
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Max-Age=43200" in cookie
    assert app_client.get("/api/state").json()["logged_in"] is True


def test_secrets_never_leave(app_client, caplog: pytest.LogCaptureFixture) -> None:  # type: ignore[no-untyped-def]
    caplog.set_level(logging.DEBUG)
    setup_owner(app_client)
    texts = []
    r = app_client.put(
        "/api/connect/toss",
        json={"client_id": FakeToss.CLIENT_ID, "client_secret": FakeToss.SECRET, "account_no": ACCOUNT},
    )
    assert r.status_code == 200
    texts.append(r.text)
    view = r.json()["toss"]
    assert view["saved"] and view["client_id_tail"] == "abcd" and view["secret_tail"] == "wxyz"
    assert view["account_tail"] == "1234"
    r = app_client.put("/api/connect/dart", json={"key": SECRETS[2]})
    texts.append(r.text)
    assert r.json()["dart"]["tail"] == "8877"
    texts.append(app_client.get("/api/connect").text)
    r = app_client.post("/api/connect/toss/check")
    texts.append(r.text)
    assert r.json()["result"]["ok"] is True
    # 모양이 틀린 요청 · 모르는 주소도 받은 값을 되돌려 보내지 않는다
    texts.append(app_client.put("/api/connect/toss", content=f'{{"client_id": "{SECRETS[1]}"', headers={"content-type": "application/json"}).text)
    texts.append(app_client.put("/api/connect/toss", json={"client_id": SECRETS[1]}).text)
    texts.append(app_client.put("/api/connect/toss", json=[SECRETS[1]]).text)
    texts.append(app_client.get(f"/api/nope/{SECRETS[1]}").text)
    for t in texts:
        _no_secret(t)
    # 앱(서버) 쪽 로그. httpx는 시험 클라이언트가 보낸 주소를 적는 것이라 뺀다
    server_logs = "\n".join(r.getMessage() for r in caplog.records if not r.name.startswith("httpx"))
    _no_secret(server_logs)
    db_path = app_client.app_ref.state.db.path
    raw = db_path.read_bytes()
    for s in SECRETS + [ACCOUNT]:
        assert s.encode() not in raw


def test_fail_result_has_no_secret(app_client, fake_toss: FakeToss) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    app_client.put("/api/connect/toss", json={"client_id": FakeToss.CLIENT_ID, "client_secret": "WRONG-secret-zzzz"})
    r = app_client.post("/api/connect/toss/check")
    assert r.json()["result"]["kind"] == "auth"
    assert "WRONG-secret" not in r.text


def test_restart_is_locked(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    app_client.put("/api/connect/toss", json={"client_id": FakeToss.CLIENT_ID, "client_secret": FakeToss.SECRET})
    app_client.app_ref.state.vault.lock_now()  # 앱을 다시 켠 것과 같다
    st = app_client.get("/api/state").json()
    assert st["logged_in"] is False and st["unlocked"] is False
    assert app_client.get("/api/connect").status_code == 401
    r = app_client.post("/api/login", json={"password": PASSWORD})
    assert r.status_code == 200
    assert app_client.get("/api/connect").json()["toss"]["secret_tail"] == "wxyz"


def test_login_lock_via_api(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    app_client.post("/api/logout")
    for _ in range(4):
        assert app_client.post("/api/login", json={"password": "bad-password"}).status_code == 401
    r = app_client.post("/api/login", json={"password": "bad-password"})
    assert r.status_code == 429 and "잠금" in r.json()["error"]
    assert app_client.post("/api/login", json={"password": PASSWORD}).status_code == 429


def test_recover_via_api(app_client) -> None:  # type: ignore[no-untyped-def]
    code = setup_owner(app_client)
    app_client.post("/api/logout")
    r = app_client.post("/api/recover", json={"recovery_code": code, "password": "brand-new-pw", "password2": "brand-new-pw"})
    assert r.status_code == 200
    assert r.json()["recovery_code"] != code
    app_client.post("/api/logout")
    assert app_client.post("/api/login", json={"password": "brand-new-pw"}).status_code == 200


def test_host_and_origin_guard(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    assert app_client.get("/api/state", headers={"host": "evil.example"}).status_code == 403
    r = app_client.post("/api/live/pause", headers={"origin": "http://evil.example"})
    assert r.status_code == 403
    r = app_client.post("/api/login", content="password=x", headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415


# ── 비밀번호 변경(P1-03에서 `test_mvp_api.py`에서 옮김 · 단언 그대로) ──────────────────────────────────

NEW_PW = "brand new pass 42"


def test_password_change(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    app_client.put("/api/connect/toss", json={"client_id": FakeToss.CLIENT_ID, "client_secret": FakeToss.SECRET})
    # 새 비밀번호 두 칸이 다르면 횟수를 세지 않는다
    r = app_client.post("/api/password", json={"current": PASSWORD, "password": NEW_PW, "password2": "x" * 9})
    assert r.status_code == 400 and "달라요" in r.json()["error"]
    # 지금 비밀번호가 틀리면 로그인과 같이 센다
    r = app_client.post("/api/password", json={"current": "wrong pass 1", "password": NEW_PW, "password2": NEW_PW})
    assert r.status_code == 401 and r.json()["tries_left"] == 4 and "지금 비밀번호" in r.json()["error"]
    r = app_client.post("/api/password", json={"current": PASSWORD, "password": NEW_PW, "password2": NEW_PW})
    assert r.status_code == 200, r.text
    assert NEW_PW not in r.text and PASSWORD not in r.text
    # 다시 켠 것처럼 잠그고: 옛 비밀번호는 안 되고 새 비밀번호로 열면 저장한 키가 그대로 풀린다
    app_client.app_ref.state.vault.lock_now()
    assert app_client.post("/api/login", json={"password": PASSWORD}).status_code == 401
    assert app_client.post("/api/login", json={"password": NEW_PW}).status_code == 200
    assert app_client.get("/api/connect").json()["toss"]["secret_tail"] == FakeToss.SECRET[-4:]


def test_password_change_counts_toward_lock(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    for _ in range(4):
        r = app_client.post("/api/password", json={"current": "nope nope 1", "password": NEW_PW, "password2": NEW_PW})
        assert r.status_code == 401
    r = app_client.post("/api/password", json={"current": "nope nope 1", "password": NEW_PW, "password2": NEW_PW})
    assert r.status_code == 429 and "잠금" in r.json()["error"]
    # 잠긴 동안에는 맞는 비밀번호도 받지 않는다
    r = app_client.post("/api/password", json={"current": PASSWORD, "password": NEW_PW, "password2": NEW_PW})
    assert r.status_code == 429


def test_password_change_keeps_recovery_code(app_client) -> None:  # type: ignore[no-untyped-def]
    code = setup_owner(app_client)
    assert app_client.post("/api/password", json={"current": PASSWORD, "password": NEW_PW, "password2": NEW_PW}).status_code == 200
    r = app_client.post("/api/recover", json={"recovery_code": code, "password": PASSWORD, "password2": PASSWORD})
    assert r.status_code == 200, r.text


def test_password_change_needs_login(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    app_client.post("/api/logout")
    r = app_client.post("/api/password", json={"current": PASSWORD, "password": NEW_PW, "password2": NEW_PW})
    assert r.status_code == 401


# ── 잠그기 = 전체 잠금 · 다시 켠 뒤 안내 · 세션 끝 · 키 연결 객체 버리기(P1-03에서 `test_fix1.py`에서 옮김 · 단언 그대로) ──


def kst(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=KST)


def test_lock_ends_every_session_and_clears_the_key(tmp_path: Path, fake_toss: FakeToss, fake_bars: FakeBars, fake_ip: FakeIp) -> None:
    app = create_app(tmp_path / "d", bars_source=fake_bars, toss_transport=lambda: fake_toss, ip_fetch=fake_ip,
                     scrypt_n=2**12, scheduler=False, now=lambda: kst("2025-06-02T17:00:00"))
    with CsrfClient(app) as a, CsrfClient(app) as b:
        setup_owner(a)
        assert b.post("/api/login", json={"password": PASSWORD}).status_code == 200
        assert a.get("/api/state").json()["unlocked"] is True
        a.post("/api/logout")
        assert app.state.vault.unlocked is False
        assert b.get("/api/live").status_code == 401  # 다른 세션도 끝났다
        assert a.get("/api/state").json()["restarted"] is False  # 잠그기 뒤에는 '다시 켰어요' 안내 없음


def test_restarted_flag_until_first_login(tmp_path: Path, fake_bars: FakeBars) -> None:
    data = tmp_path / "d"
    with CsrfClient(create_app(data, bars_source=fake_bars, scrypt_n=2**12, scheduler=False)) as c:
        assert c.get("/api/state").json()["restarted"] is False  # 아직 계정 없음
        setup_owner(c)
        assert c.get("/api/state").json()["restarted"] is False
    with CsrfClient(create_app(data, bars_source=fake_bars, scrypt_n=2**12, scheduler=False)) as c:
        assert c.get("/api/state").json()["restarted"] is True  # 다시 켠 뒤 첫 로그인 전
        c.post("/api/login", json={"password": PASSWORD})
        assert c.get("/api/state").json()["restarted"] is False


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
    app_client.put("/api/connect/toss", json={"client_id": FakeToss.CLIENT_ID, "client_secret": FakeToss.SECRET},
                   headers=confirm(app_client, "toss_key_change"))
    assert conns._client is None and c2._token is None
    app_client.post("/api/connect/toss/check")
    c3 = conns._client
    app_client.delete("/api/connect/toss", headers=confirm(app_client, "toss_key_delete"))
    assert conns._client is None and c3._token is None


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
