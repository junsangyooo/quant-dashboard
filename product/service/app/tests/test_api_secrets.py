"""비밀 값이 응답 · 로그 · DB 평문에 나오지 않는다. 입장 쿠키와 문 단속."""

from __future__ import annotations

import logging

import pytest

from tests.conftest import PASSWORD, FakeToss, setup_owner

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
    assert app_client.get("/api/home").status_code == 401
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
    r = app_client.post("/api/paper/stop", headers={"origin": "http://evil.example"})
    assert r.status_code == 403
    r = app_client.post("/api/login", content="password=x", headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.status_code == 415
