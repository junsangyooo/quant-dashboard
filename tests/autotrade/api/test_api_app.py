"""App level: security headers, health check, JSON 404, the session gate, the web app files."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from autotrade.api.app import CSP, create_app
from autotrade.api.settings import ApiSettings
from autotrade.config import Config

# Reachable without a session (CONTRACT.md: '/api/auth/* 제외', plus the deploy health check).
OPEN_PATHS = {"/api/healthz", "/api/auth/pin", "/api/auth/logout"}


def test_security_headers_on_every_kind_of_response(client: TestClient) -> None:
    for response in (
        client.get("/api/healthz"),  # 200 JSON
        client.get("/api/home"),  # 403
        client.get("/api/nope"),  # 404
        client.get("/"),  # 503 page (no build)
    ):
        assert response.headers["content-security-policy"] == CSP
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"
        assert response.headers["x-frame-options"] == "DENY"
    assert CSP == (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
        "form-action 'self'"
    )


def test_healthz_needs_no_session(client: TestClient) -> None:
    response = client.get("/api/healthz")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "schema": 2}
    assert response.headers["cache-control"] == "no-store"


def test_unknown_api_paths_are_json_404(client: TestClient) -> None:
    for response in (client.get("/api/nope"), client.get("/api"), client.post("/api/nope")):
        assert response.status_code in (404, 405)
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["error"] in ("not-found", "method-not-allowed")
    assert client.get("/api/nope").json() == {"error": "not-found"}


def test_api_docs_are_off(client: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        response = client.get(path)
        assert "swagger" not in response.text.lower()
        assert '"openapi"' not in response.text


def test_every_api_route_needs_a_session(app: FastAPI, client: TestClient) -> None:
    routes = [r for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/api/")]
    assert len(routes) >= 20
    for route in routes:
        if route.path in OPEN_PATHS:
            continue
        path = route.path.replace("{day}", "2026-07-01").replace("{rule_id}", "index_half")
        for method in route.methods:
            response = client.request(method, path, json={})
            assert response.status_code == 403, f"{method} {route.path}"
            assert response.json() == {"error": "session"}, f"{method} {route.path}"


def test_web_app_files(tmp_path: Path, api_cfg: Config, settings: ApiSettings) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>quant</title>")
    (dist / "assets" / "index-AbCd1234.js").write_text("console.log(1)")
    (dist / "favicon.ico").write_bytes(b"\x00\x01")
    (tmp_path / "secret.txt").write_text("outside")
    app = create_app(api_cfg, settings)
    with TestClient(app, base_url="https://testserver") as c:
        index = c.get("/")
        assert index.status_code == 200
        assert index.headers["cache-control"] == "no-cache"
        assert "<title>quant</title>" in index.text
        spa = c.get("/day/2026-08-21?ledger=paper")
        assert spa.status_code == 200
        assert spa.text == index.text
        asset = c.get("/assets/index-AbCd1234.js")
        assert asset.headers["cache-control"] == "public, max-age=31536000, immutable"
        assert asset.text == "console.log(1)"
        assert c.get("/assets/missing-00000000.js").status_code == 404
        assert c.get("/favicon.ico").headers["cache-control"] == "no-cache"
        escaped = c.get("/..%2Fsecret.txt")
        assert "outside" not in escaped.text
        assert c.head("/").status_code == 200


def test_without_a_build_the_root_is_a_plain_503(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("text/html")
    assert "web/dist" in response.text
