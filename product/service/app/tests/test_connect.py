"""가짜 토스 전송으로 연결 확인: 성공 하나, 실패 셋(키 틀림 · 허용 IP 없음 · 응답 없음)."""

from __future__ import annotations

from tests.conftest import FakeToss, setup_owner


def _save(client, secret: str = FakeToss.SECRET, account: str | None = None) -> None:  # type: ignore[no-untyped-def]
    body = {"client_id": FakeToss.CLIENT_ID, "client_secret": secret}
    if account:
        body["account_no"] = account
    assert client.put("/api/connect/toss", json=body).status_code == 200


def _check(client) -> dict:  # type: ignore[no-untyped-def,type-arg]
    r = client.post("/api/connect/toss/check")
    assert r.status_code == 200, r.text
    return r.json()["result"]


def test_check_ok(app_client, fake_toss: FakeToss) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    _save(app_client)
    res = _check(app_client)
    assert res["ok"] is True
    assert res["line"] == "연결됐어요 · 계좌 끝 1234 · 삼성전자 71,300원"
    # 조회만: 토큰 받기(POST) 하나 말고는 모두 GET
    assert fake_toss.calls == [
        ("POST", "/oauth2/token"),
        ("GET", "/api/v1/accounts"),
        ("GET", "/api/v1/prices"),
    ]
    assert app_client.get("/api/connect").json()["toss"]["last_check"]["ok"] is True


def test_check_wrong_key(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    _save(app_client, secret="not-the-secret")
    res = _check(app_client)
    assert res["ok"] is False and res["kind"] == "auth"
    assert res["title"] == "API 키가 맞지 않아요"
    assert "다시 복사" in res["next"]
    assert res["step"] == "액세스 토큰 받기"
    assert [s["state"] for s in res["steps"]] == ["failed", "waiting", "waiting"]


def test_check_ip_not_allowed(app_client, fake_toss: FakeToss) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    _save(app_client)
    fake_toss.ip_allowed = False
    res = _check(app_client)
    assert res["kind"] == "ip"
    assert res["title"] == "허용 IP에 이 컴퓨터가 없어요"
    assert "허용 IP" in res["next"]


def test_check_no_answer(app_client, fake_toss: FakeToss) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    _save(app_client)
    fake_toss.down = True
    res = _check(app_client)
    assert res["kind"] == "unreachable"
    assert res["title"] == "토스가 응답하지 않아요"
    assert "인터넷" in res["next"]


def test_check_account_not_listed(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    _save(app_client, account="99998888777")
    res = _check(app_client)
    assert res["kind"] == "account" and res["step"] == "계좌 찾기"


def test_check_needs_keys(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    r = app_client.post("/api/connect/toss/check")
    assert r.status_code == 400 and "먼저 저장" in r.json()["error"]


def test_delete_keys(app_client) -> None:  # type: ignore[no-untyped-def]
    setup_owner(app_client)
    _save(app_client)
    r = app_client.delete("/api/connect/toss")
    assert r.json()["toss"]["saved"] is False
    assert r.json()["toss"]["secret_tail"] is None
