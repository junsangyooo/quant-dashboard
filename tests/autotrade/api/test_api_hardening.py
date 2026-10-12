"""Audit fixes on the app level: the schema guard instead of a migrating startup (A4), junk paths
and cookies that used to be 500s and the log of real 500s (A5), requests from sibling sites and the
__Host- cookie (A6), and the session check before the body (A9)."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import BaseModel

from autotrade.api.app import _describe, create_app, dev_clock, origin_allowed, same_host
from autotrade.api.routes import static as static_routes
from autotrade.api.schema import code_version
from autotrade.api.settings import ApiSettings, default_settings, dev_mode
from autotrade.api.views import home as home_view
from autotrade.config import REPO_ROOT, Config
from autotrade.db.connection import connect

from ..helpers import kst
from .support import COOKIE, PIN, owner_pin

# Reachable without a session (CONTRACT.md: '/api/auth/* 제외', plus the deploy health check).
OPEN_PATHS = {"/api/healthz", "/api/auth/pin", "/api/auth/logout"}
CODE = code_version()


# ── A4: the API serves only its own schema and never migrates ───────────────────────────────


def test_another_schema_is_503_on_every_api_route(
    client: TestClient, db: sqlite3.Connection, settings: ApiSettings
) -> None:
    owner_pin(db, settings)
    db.execute("DELETE FROM schema_migrations WHERE version = ?", (CODE,))  # code is newer
    older = {"error": "schema", "detail": {"stored": CODE - 1, "code": CODE}}
    for response in (
        client.get("/api/healthz"),
        client.get("/api/shell"),
        client.post("/api/auth/pin", json={"pin": PIN}),
        client.post("/api/auth/logout"),
    ):
        assert (response.status_code, response.json()) == (503, older)
        assert response.headers["cache-control"] == "no-store"
    db.execute("INSERT INTO schema_migrations VALUES (?, 'x', '2026-07-01T00:00:00Z')", (CODE,))
    db.execute("INSERT INTO schema_migrations VALUES (?, 'x', '2026-07-01T00:00:00Z')", (CODE + 1,))
    newer = client.get("/api/healthz")  # a rollback of the code over a migrated database
    assert (newer.status_code, newer.json()["detail"]) == (503, {"stored": CODE + 1, "code": CODE})
    db.execute("DELETE FROM schema_migrations WHERE version = ?", (CODE + 1,))
    assert client.get("/api/healthz").json() == {"ok": True, "schema": CODE}
    assert client.post("/api/auth/pin", json={"pin": PIN}).status_code == 204


def test_no_database_is_503_and_nothing_is_created(tmp_path: Path, settings: ApiSettings) -> None:
    cfg = Config(db_path=tmp_path / "none" / "autotrade.db")
    with TestClient(create_app(cfg, settings), base_url="https://testserver") as c:
        response = c.get("/api/healthz")
        assert (response.status_code, response.json()) == (
            503,
            {"error": "schema", "detail": {"stored": 0, "code": CODE}},
        )
        assert c.post("/api/auth/pin", json={"pin": PIN}).status_code == 503
    assert not cfg.db_path.exists()
    assert not cfg.db_path.parent.exists()


def test_startup_does_not_migrate(
    tmp_path: Path, settings: ApiSettings, caplog: pytest.LogCaptureFixture
) -> None:
    cfg = Config(db_path=tmp_path / "autotrade.db")
    connect(cfg.db_path).close()  # an empty database: no tables at all
    with (
        caplog.at_level(logging.WARNING, logger="autotrade.api"),
        TestClient(create_app(cfg, settings), base_url="https://testserver") as c,
    ):
        assert c.get("/api/healthz").json()["error"] == "schema"
    conn = connect(cfg.db_path)
    try:
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    finally:
        conn.close()
    assert tables == []
    assert f"schema 0 stored, {CODE} in the code" in caplog.text


def test_an_unreadable_database_is_503_db(tmp_path: Path, settings: ApiSettings) -> None:
    cfg = Config(db_path=tmp_path / "autotrade.db")
    cfg.db_path.write_bytes(b"not a database, " * 64)
    with TestClient(create_app(cfg, settings), base_url="https://testserver") as c:
        response = c.get("/api/healthz")
        assert (response.status_code, response.json()) == (503, {"error": "db"})


# ── A5: junk paths and cookies are 404 and 403, not 500; real 500s are logged ───────────────


@pytest.fixture
def web(tmp_path: Path, api_cfg: Config, settings: ApiSettings, db: sqlite3.Connection) -> Any:
    dist = settings.dist_dir
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>quant</title>")
    (dist / "assets" / "index-AbCd1234.js").write_text("console.log(1)")
    with TestClient(create_app(api_cfg, settings), base_url="https://testserver") as c:
        yield c


@pytest.mark.parametrize(
    "path",
    [
        "/%00",
        "/a%00b",
        "/assets/%00",
        "/assets/a%00.js",
        "/%0a",
        "/day/%1b",
        "/" + "a" * 300,
        "/assets/" + "b" * 300,
        "/x/" + "%C3%A9" * 130,  # 260 bytes in one segment
        "/" + "a/" * 600,  # over 1,024 characters
    ],
)
def test_junk_paths_are_404(web: TestClient, path: str) -> None:
    response = web.get(path)
    assert (response.status_code, response.text) == (404, "not found")
    assert response.headers["x-content-type-options"] == "nosniff"


def test_long_but_possible_paths_still_open_the_app(web: TestClient) -> None:
    for path in ("/" + "a" * 255, "/day/" + "é" * 120, "/x/" + "a/" * 400):
        response = web.get(path)
        assert response.status_code == 200, path
        assert "<title>quant</title>" in response.text


def test_filesystem_errors_count_as_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(self: Path, strict: bool = False) -> Path:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "resolve", broken)
    assert static_routes._file(tmp_path, "assets/x.js") is None


@pytest.mark.parametrize(
    "cookie",
    [
        "a.1.\xe9".encode(),
        "\xe9".encode(),
        b"\xff\xfe.1.x",
        b"a" * 300,
        b"x.y.z.w",
        b"",
    ],
)
def test_a_cookie_that_is_no_token_is_403_session(client: TestClient, cookie: bytes) -> None:
    header = COOKIE.encode() + b"=" + cookie
    for path in ("/api/shell", "/api/home", "/api/account"):
        response = client.get(path, headers=[(b"cookie", header)])
        assert (response.status_code, response.json()) == (403, {"error": "session"}), path
    assert client.post("/api/auth/logout", headers=[(b"cookie", header)]).status_code == 204


def test_the_old_cookie_name_is_ignored(logged_in: TestClient, app: FastAPI) -> None:
    token = logged_in.cookies.get(COOKIE)
    assert token
    with TestClient(app, base_url="https://testserver") as other:
        other.cookies.set("qsess", token)
        assert other.get("/api/shell").json() == {"error": "session"}


def test_unhandled_errors_are_logged_without_headers(
    logged_in: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("bug in the view")

    monkeypatch.setattr(home_view, "home", boom)
    token = logged_in.cookies.get(COOKIE)
    assert token
    with caplog.at_level(logging.ERROR, logger="autotrade.api"):
        response = logged_in.get(
            "/api/home?ledger=paper", headers={"x-note": "header-value-not-for-logs"}
        )
    assert (response.status_code, response.json()) == (500, {"error": "internal"})
    assert response.headers["content-security-policy"]
    assert "unhandled GET '/api/home': RuntimeError: bug in the view" in caplog.text
    assert "Traceback" in caplog.text
    for secret in (token, "header-value-not-for-logs", "ledger=paper", COOKIE):
        assert secret not in caplog.text


def test_a_validation_error_is_described_without_its_input() -> None:
    class Pin(BaseModel):
        pin: int

    try:
        Pin.model_validate({"pin": "my-pin-123456"})
    except Exception as exc:
        text = _describe(exc)
    assert text == "ValidationError at [('pin',)]"
    assert _describe(KeyError("x")) == "KeyError: 'x'"


# ── A6: sibling sites and the __Host- cookie ─────────────────────────────────────────────────

SIBLING = {"origin": "https://portfolio.jsyoo.dev", "sec-fetch-site": "same-site"}


def test_unsafe_requests_from_another_site_are_refused(
    logged_in: TestClient, db: sqlite3.Connection
) -> None:
    sessions_before = db.execute("SELECT COUNT(*) FROM sessions WHERE revoked_at IS NULL")
    open_before = sessions_before.fetchone()[0]
    for method, path in (
        ("POST", "/api/auth/logout-others"),
        ("POST", "/api/mode/paper"),
        ("POST", "/api/mode/cancel-retry"),
        ("PUT", "/api/account/notifications"),
        ("POST", "/api/account/pin"),
        ("POST", "/api/auth/pin"),
        ("POST", "/api/auth/logout"),
        ("DELETE", "/api/account/push"),
        ("POST", "/api/nope"),
    ):
        response = logged_in.request(method, path, headers=SIBLING, json={})
        assert (response.status_code, response.json()) == (403, {"error": "origin"}), path
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["cache-control"] == "no-store"
    open_after = db.execute("SELECT COUNT(*) FROM sessions WHERE revoked_at IS NULL").fetchone()
    assert open_after[0] == open_before
    assert logged_in.get("/api/shell", headers=SIBLING).status_code == 200  # reads are not refused
    same = {"origin": "https://testserver", "sec-fetch-site": "same-origin"}
    assert logged_in.post("/api/mode/paper", headers=same).status_code == 200
    assert logged_in.post("/api/mode/paper", headers={"origin": "https://testserver"}).json() == {
        "mode": "paper",
        "cancelFailed": [],
        "cancelPending": [],
    }


@pytest.mark.parametrize(
    ("method", "headers", "allowed"),
    [
        ("GET", {"origin": "https://evil.example", "host": "quant.jsyoo.dev"}, True),
        ("POST", {"host": "quant.jsyoo.dev"}, True),  # no browser headers: curl, deploy checks
        ("POST", {"sec-fetch-site": "same-origin"}, True),
        ("POST", {"sec-fetch-site": "none"}, True),
        ("POST", {"sec-fetch-site": "same-site", "host": "quant.jsyoo.dev"}, False),
        ("POST", {"sec-fetch-site": "cross-site", "host": "quant.jsyoo.dev"}, False),
        # Behind nginx: the app sees http and Host without a port; the browser's origin is https.
        ("POST", {"origin": "https://quant.jsyoo.dev", "host": "quant.jsyoo.dev"}, True),
        ("PUT", {"origin": "https://QUANT.jsyoo.dev", "host": "quant.jsyoo.dev"}, True),
        ("POST", {"origin": "https://quant.jsyoo.dev:443", "host": "quant.jsyoo.dev"}, True),
        ("POST", {"origin": "https://quant.jsyoo.dev", "host": "quant.jsyoo.dev:443"}, True),
        ("POST", {"origin": "https://quant.jsyoo.dev:8443", "host": "quant.jsyoo.dev"}, False),
        ("POST", {"origin": "https://portfolio.jsyoo.dev", "host": "quant.jsyoo.dev"}, False),
        (
            "POST",
            {"origin": "https://quant.jsyoo.dev.evil.example", "host": "quant.jsyoo.dev"},
            False,
        ),
        ("DELETE", {"origin": "null", "host": "quant.jsyoo.dev"}, False),
        ("POST", {"origin": "https://quant.jsyoo.dev"}, False),  # no Host
        ("POST", {"origin": "https://quant.jsyoo.dev", "host": "quant.jsyoo.dev:x"}, False),
        # Development and the e2e runs: plain http with a port.
        ("POST", {"origin": "http://127.0.0.1:4271", "host": "127.0.0.1:4271"}, True),
        ("POST", {"origin": "http://127.0.0.1:4272", "host": "127.0.0.1:4271"}, False),
        ("POST", {"origin": "http://[::1]:8890", "host": "[::1]:8890"}, True),
        # Sec-Fetch-Site decides when it says same-origin, whatever the Origin.
        ("POST", {"sec-fetch-site": "same-origin", "origin": "https://x.example"}, True),
    ],
)
def test_origin_rule(method: str, headers: dict[str, str], allowed: bool) -> None:
    assert origin_allowed(method, headers) is allowed


def test_same_host_edges() -> None:
    assert same_host("https://quant.jsyoo.dev", "quant.jsyoo.dev")
    assert not same_host("ftp://quant.jsyoo.dev", "quant.jsyoo.dev")  # no default port known
    assert not same_host("https://", "quant.jsyoo.dev")


def test_the_cookie_is_host_prefixed_in_production_only(
    tmp_path: Path, api_cfg: Config, db: sqlite3.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = default_settings(api_cfg)
    assert (settings.cookie_name, settings.cookie_secure) == ("__Host-qsess", True)
    dev = default_settings(api_cfg, dev=True)
    assert (dev.cookie_name, dev.cookie_secure) == ("qsess", False)
    # A dev-seed world over plain http: 'qsess' without Secure, the world's clock.
    owner_pin(db, ApiSettings(secret_path=dev.secret_path, dist_dir=dev.dist_dir, scrypt_n=2**10))
    monkeypatch.setenv("AUTOTRADE_DEV", "1")
    monkeypatch.setenv("AUTOTRADE_FAKE_NOW", "2026-07-01T16:10")
    with TestClient(create_app(api_cfg), base_url="http://127.0.0.1:4271") as c:
        response = c.post("/api/auth/pin", json={"pin": PIN})
        assert response.status_code == 204
        cookie = response.headers["set-cookie"]
        assert cookie.startswith("qsess=")
        assert "secure" not in cookie.lower()
        assert c.get("/api/shell").json()["now"] == "2026-07-01T16:10:00+09:00"


def test_dev_mode_is_ignored_for_the_server_database() -> None:
    data_db = REPO_ROOT / "data" / "autotrade.db"
    env = {"AUTOTRADE_DEV": "1", "AUTOTRADE_FAKE_NOW": "2026-10-07T16:10"}
    assert not dev_mode(env, data_db)  # the cookie stays __Host- and Secure
    assert dev_clock(env, data_db) is None  # the clock keeps running
    assert dev_mode(env, REPO_ROOT / "build" / "dev.db")
    fixed = dev_clock(env, REPO_ROOT / "build" / "dev.db")
    assert fixed is not None
    assert fixed() == kst("2026-10-07 16:10")
    assert not dev_mode({}, REPO_ROOT / "build" / "dev.db")


# ── A9: the session before the body ──────────────────────────────────────────────────────────


def test_no_protected_route_reads_its_body_before_the_session(app: FastAPI) -> None:
    routes = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/")]
    protected = [r for r in routes if r.path not in OPEN_PATHS]
    assert len(protected) >= 20
    for route in protected:
        # A body parameter makes FastAPI parse the JSON before any dependency runs; protected
        # routes take theirs from deps.session_body instead.
        assert route.body_field is None, route.path


def test_a_malformed_body_without_a_session_is_403(app: FastAPI) -> None:
    with TestClient(app, base_url="https://testserver") as stranger:
        for method, path in (
            ("PUT", "/api/account/notifications"),
            ("POST", "/api/account/pin"),
            ("POST", "/api/mode/live"),
        ):
            response = stranger.request(
                method, path, content=b"{not json", headers={"content-type": "application/json"}
            )
            assert (response.status_code, response.json()) == (403, {"error": "session"}), path


def test_body_errors_with_a_session_are_400(logged_in: TestClient) -> None:
    def put(content: bytes, content_type: str = "application/json") -> Any:
        return logged_in.put(
            "/api/account/notifications", content=content, headers={"content-type": content_type}
        )

    assert put(b"{not json").json() == {"error": "bad-request", "detail": {"fields": ["body"]}}
    assert put(b"").json()["error"] == "bad-request"
    assert put(b'{"hideAmounts": true}', "text/plain").json() == {
        "error": "bad-request",
        "detail": {"fields": ["body"]},
    }
    assert put(b'{"hideAmounts": true}', "application/merge-patch+json").status_code == 200
    no_type = logged_in.put("/api/account/notifications", content=b'{"hideAmounts": false}')
    assert no_type.status_code == 200  # no content type is read as JSON, as FastAPI does
    assert put(b'{"bogus": 1}').json() == {
        "error": "bad-request",
        "detail": {"fields": ["body.bogus"]},
    }
    missing = logged_in.post("/api/account/pin", json={"current": PIN})
    assert missing.json() == {"error": "bad-request", "detail": {"fields": ["body.next"]}}
    # Turning live on needs the confirmation and the preview's hash in the body.
    assert logged_in.post("/api/mode/live", json={"pin": PIN}).json() == {
        "error": "bad-request",
        "detail": {"fields": ["confirm"]},
    }


def test_a_broken_schema_table_is_503_db(client: TestClient, db: sqlite3.Connection) -> None:
    db.execute("ALTER TABLE schema_migrations RENAME TO schema_migrations_old")
    db.execute("CREATE TABLE schema_migrations (x INTEGER)")  # no version column
    response = client.get("/api/healthz")
    assert (response.status_code, response.json()) == (503, {"error": "db"})


def test_the_dev_flag_on_the_server_database_is_logged_and_ignored(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("AUTOTRADE_DEV", "1")
    monkeypatch.setenv("AUTOTRADE_FAKE_NOW", "2026-10-07T16:10")
    cfg = Config(db_path=REPO_ROOT / "data" / "autotrade.db")
    with caplog.at_level(logging.WARNING, logger="autotrade.api"):
        create_app(cfg)  # not started: nothing under data/ is opened
    assert "AUTOTRADE_DEV=1 ignored" in caplog.text
    assert "AUTOTRADE_FAKE_NOW ignored" in caplog.text
