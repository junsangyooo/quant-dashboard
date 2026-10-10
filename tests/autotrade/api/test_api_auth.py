"""PIN login, lockout, sessions (logout, logout-others, PIN change) and the CLI PIN commands."""

from __future__ import annotations

import io
import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autotrade.api.auth import device_from_user_agent
from autotrade.api.security import (
    hash_pin,
    is_valid_pin,
    load_or_create_secret,
    make_token,
    read_token,
    verify_pin,
)
from autotrade.api.settings import ApiSettings
from autotrade.config import Config
from autotrade.db import auth_repo
from autotrade.db.migrations import MIGRATIONS
from autotrade.jobs.cli import main as jobs_main

from .support import COOKIE, PIN, Clock, owner_pin

PROXY = ("127.0.0.1", 40000)


def login(client: TestClient, pin: str = PIN, ip: str | None = None) -> int:
    headers = {"x-forwarded-for": ip} if ip else {}
    return int(client.post("/api/auth/pin", json={"pin": pin}, headers=headers).status_code)


def test_login_sets_a_host_only_strict_secure_cookie(
    client: TestClient, db: sqlite3.Connection, settings: ApiSettings
) -> None:
    owner_pin(db, settings)
    response = client.post("/api/auth/pin", json={"pin": PIN})
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE}=")  # __Host-: Secure, Path=/, no Domain
    for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/", "Max-Age=2592000"):
        assert flag.lower() in cookie.lower()
    assert "domain" not in cookie.lower()
    assert client.get("/api/shell").status_code == 200


def test_no_pin_yet_and_bad_input(client: TestClient) -> None:
    assert client.post("/api/auth/pin", json={"pin": PIN}).json() == {"error": "no-pin"}
    bad = client.post("/api/auth/pin", json={"pin": "12345a"})
    assert (bad.status_code, bad.json()) == (400, {"error": "invalid-pin"})
    missing = client.post("/api/auth/pin", json={})
    assert missing.status_code == 400
    assert missing.json()["error"] == "bad-request"


def test_five_wrong_pins_lock_the_address_for_30_minutes(
    app: FastAPI, db: sqlite3.Connection, settings: ApiSettings, clock: Clock
) -> None:
    owner_pin(db, settings)
    with TestClient(app, base_url="https://testserver", client=PROXY) as c:
        for remaining in (4, 3, 2, 1):
            r = c.post(
                "/api/auth/pin", json={"pin": "000000"}, headers={"x-forwarded-for": "1.2.3.4"}
            )
            assert (r.status_code, r.json()) == (403, {"error": "pin", "remaining": remaining})
        fifth = c.post(
            "/api/auth/pin", json={"pin": "000000"}, headers={"x-forwarded-for": "1.2.3.4"}
        )
        assert fifth.status_code == 403
        assert fifth.json() == {
            "error": "locked",
            "until": "2026-07-01T16:40:00+09:00",
            "scope": "ip",
        }
        # Locked even with the right PIN; another address is not affected.
        assert (
            c.post(
                "/api/auth/pin", json={"pin": PIN}, headers={"x-forwarded-for": "1.2.3.4"}
            ).json()["error"]
            == "locked"
        )
        assert login(c, ip="5.6.7.8") == 204
        clock.now += timedelta(minutes=30)
        assert login(c, ip="1.2.3.4") == 204


def test_a_success_resets_the_count(
    app: FastAPI, db: sqlite3.Connection, settings: ApiSettings
) -> None:
    owner_pin(db, settings)
    with TestClient(app, base_url="https://testserver", client=PROXY) as c:
        for _ in range(4):
            login(c, "000000", ip="1.2.3.4")
        assert login(c, ip="1.2.3.4") == 204
        r = c.post("/api/auth/pin", json={"pin": "000000"}, headers={"x-forwarded-for": "1.2.3.4"})
        assert r.json() == {"error": "pin", "remaining": 4}


def test_global_cap_stops_rotating_addresses(
    app: FastAPI, db: sqlite3.Connection, settings: ApiSettings, clock: Clock
) -> None:
    owner_pin(db, settings)
    with TestClient(app, base_url="https://testserver", client=PROXY) as c:
        for i in range(20):
            login(c, "000000", ip=f"10.0.0.{i}")
        blocked = c.post(
            "/api/auth/pin", json={"pin": PIN}, headers={"x-forwarded-for": "10.9.9.9"}
        )
        assert blocked.status_code == 403
        assert blocked.json() == {
            "error": "locked",
            "until": "2026-07-01T17:10:00+09:00",
            "scope": "global",
        }
        clock.now += timedelta(hours=1)
        assert login(c, ip="10.9.9.9") == 204


def test_forwarded_for_is_only_trusted_from_the_local_proxy(
    client: TestClient, db: sqlite3.Connection, settings: ApiSettings
) -> None:
    owner_pin(db, settings)
    for _ in range(5):
        login(client, "000000", ip="9.9.9.9")  # the peer is 'testclient', so the header is ignored
    assert login(client, ip="8.8.8.8") == 403  # the same (real) address is locked
    lock = auth_repo.get_lock(db, "testclient")
    assert lock.locked_until is not None


def test_session_is_required_and_checked(
    logged_in: TestClient, app: FastAPI, clock: Clock, settings: ApiSettings
) -> None:
    assert logged_in.get("/api/shell").status_code == 200
    with TestClient(app, base_url="https://testserver") as stranger:
        assert stranger.get("/api/shell").json() == {"error": "session"}
        stranger.cookies.set(COOKIE, "made.up.token")
        assert stranger.get("/api/shell").status_code == 403
        forged = make_token("nope", 4102444800, b"another-secret-of-32-bytes-long!")
        stranger.cookies.set(COOKIE, forged)
        assert stranger.get("/api/shell").status_code == 403
    clock.now += timedelta(days=31)
    assert logged_in.get("/api/shell").status_code == 403


def test_logout_revokes_the_session(logged_in: TestClient, app: FastAPI) -> None:
    token = logged_in.cookies.get(COOKIE)
    assert token
    response = logged_in.post("/api/auth/logout")
    assert response.status_code == 204
    assert "max-age=0" in response.headers["set-cookie"].lower()
    with TestClient(app, base_url="https://testserver") as other:
        other.cookies.set(COOKIE, token or "")
        assert other.get("/api/shell").status_code == 403
    assert logged_in.post("/api/auth/logout").status_code == 204  # idempotent


def test_logout_others_keeps_only_this_session(logged_in: TestClient, app: FastAPI) -> None:
    with TestClient(app, base_url="https://testserver") as phone:
        assert login(phone) == 204
        assert phone.get("/api/shell").status_code == 200
        assert logged_in.post("/api/auth/logout-others").status_code == 204
        assert phone.get("/api/shell").status_code == 403
        assert logged_in.get("/api/shell").status_code == 200


def test_pin_change(logged_in: TestClient, app: FastAPI) -> None:
    with TestClient(app, base_url="https://testserver") as phone:
        assert login(phone) == 204
        wrong = logged_in.post("/api/account/pin", json={"current": "000000", "next": "654321"})
        assert (wrong.status_code, wrong.json()) == (403, {"error": "current-pin"})
        bad = logged_in.post("/api/account/pin", json={"current": PIN, "next": "12"})
        assert (bad.status_code, bad.json()) == (400, {"error": "invalid-pin"})
        ok = logged_in.post("/api/account/pin", json={"current": PIN, "next": "654321"})
        assert ok.status_code == 204
        assert phone.get("/api/shell").status_code == 403  # every other session ends
        assert logged_in.get("/api/shell").status_code == 200
        assert login(phone, "654321") == 204
        assert login(phone, PIN) == 403


def test_pin_hash_and_tokens(tmp_path: Path) -> None:
    secret = load_or_create_secret(tmp_path / "s" / "autotrade.secret")
    assert load_or_create_secret(tmp_path / "s" / "autotrade.secret") == secret
    assert ((tmp_path / "s" / "autotrade.secret").stat().st_mode & 0o777) == 0o600
    stored = hash_pin("123456", secret, n=2**10)
    assert stored.startswith("scrypt$1024$8$1$")
    assert verify_pin("123456", stored, secret)
    assert not verify_pin("123457", stored, secret)
    assert not verify_pin("123456", stored, b"x" * 32)  # the pepper matters
    assert not verify_pin("123456", None, secret)
    assert not verify_pin("123456", "md5$abc", secret)
    assert not verify_pin("123456", "scrypt$x$8$1$aa$bb", secret)
    assert hash_pin("123456", secret, n=2**10) != stored  # salted
    with pytest.raises(ValueError, match="six digits"):
        hash_pin("12345", secret)
    assert [is_valid_pin(p) for p in ("012345", "12345", "1234567", "١٢٣٤٥٦", 123456)] == [
        True,
        False,
        False,
        False,
        False,
    ]
    token = make_token("abc", 2000, secret)
    assert read_token(token, secret, now_unix=1999) == "abc"
    assert read_token(token, secret, now_unix=2000) is None
    assert read_token(token + "x", secret, now_unix=1) is None
    assert read_token("abc.notanumber." + token.split(".")[2], secret) is None
    assert read_token(None, secret) is None


def test_device_names_from_the_user_agent() -> None:
    iphone = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15"
    safari = f"{iphone} (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    app = f"{iphone} (KHTML, like Gecko) Mobile/15E148"
    mac = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        " (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
    )
    assert device_from_user_agent(safari) == ("iphone-safari", "iPhone · Safari")
    assert device_from_user_agent(app) == ("iphone-app", "iPhone")
    assert device_from_user_agent(mac) == ("mac", "Mac · Chrome")
    assert device_from_user_agent("Mozilla/5.0 (Windows NT 10.0) Firefox/130.0") == (
        "other",
        "Windows · Firefox",
    )
    assert device_from_user_agent("Mozilla/5.0 (Linux; Android 14) Edg/129.0") == (
        "other",
        "Android · Edge",
    )
    assert device_from_user_agent("Mozilla/5.0 (iPad; CPU OS 18_0) Safari/604.1") == (
        "other",
        "iPad · Safari",
    )
    assert device_from_user_agent(None) == ("other", "")


def run_cli(args: list[str], db_path: Path, stdin: str = "") -> tuple[int, dict[str, object]]:
    lines: list[str] = []
    code = jobs_main(
        [*args, "--db", str(db_path)], env={}, out=lines.append, stdin=io.StringIO(stdin)
    )
    return code, json.loads(lines[0])


def test_cli_migrate_and_set_pin(tmp_path: Path) -> None:
    db_path = tmp_path / "data" / "autotrade.db"
    expected = {"job": "migrate", "result": "ok", "schema": len(MIGRATIONS)}
    assert run_cli(["migrate"], db_path) == (0, expected)
    code, out = run_cli(["set-pin"], db_path, "123456\n654321\n")
    assert (code, out["error"]) == (1, "pin-mismatch")
    code, out = run_cli(["set-pin"], db_path, "12ab56\n12ab56\n")
    assert (code, out["error"]) == (1, "invalid-pin")
    code, out = run_cli(["set-pin"], db_path, "123456\n123456\n")
    assert (code, out) == (
        0,
        {
            "job": "set-pin",
            "result": "ok",
            "revokedSessions": 0,
            "clearedFailures": 0,
            "clearedLocks": 0,
            "wasClosed": False,
            "wasAlerted": False,
        },
    )
    secret = load_or_create_secret(tmp_path / "data" / "autotrade.secret")
    from autotrade.db.connection import connect

    conn = connect(db_path)
    try:
        assert verify_pin("123456", auth_repo.get_pin_hash(conn), secret)
    finally:
        conn.close()
    with pytest.raises(SystemExit):  # the PIN is never an argument
        jobs_main(["set-pin", "123456", "--db", str(db_path)], env={})


def test_cli_set_pin_reset_closes_sessions(logged_in: TestClient, api_cfg: Config) -> None:
    code, out = run_cli(["set-pin"], api_cfg.db_path, "222222\n222222\n")
    assert (code, out["revokedSessions"]) == (0, 1)
    assert logged_in.get("/api/shell").status_code == 403
