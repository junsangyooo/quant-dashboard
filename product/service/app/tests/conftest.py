"""시험 공통: 네트워크 차단, 가짜 토스, 가짜 일봉, 앱 클라이언트."""

from __future__ import annotations

import json
import socket
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.market import KST
from app.toss import HttpRequest, HttpResponse, TransportError


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """시험 안에서는 바깥 네트워크에 절대 나가지 않는다."""

    def refuse(self: socket.socket, address: Any) -> None:
        if self.family == socket.AF_UNIX:
            return original(self, address)
        raise RuntimeError(f"network blocked in tests: {address!r}")

    original = socket.socket.connect
    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("network blocked")))


# ── 가짜 토스 ────────────────────────────────────────────────────────────────


class FakeToss:
    CLIENT_ID = "cid-REAL-0000-abcd"
    SECRET = "sec-TOP-SECRET-value-wxyz"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.down = False
        self.ip_allowed = True
        self.tokens: list[str] = []
        self.accounts = [{"accountNo": "12345671234", "accountSeq": 7, "accountType": "BROKERAGE"}]
        self.prices = {"005930": "71300", "000660": "180500"}

    def __call__(self, request: HttpRequest) -> HttpResponse:
        url = urllib.parse.urlsplit(request.url)
        path = url.path
        query = dict(urllib.parse.parse_qsl(url.query))
        self.calls.append((request.method, path))
        if self.down:
            raise TransportError("ConnectionError")
        if path == "/oauth2/token":
            form = dict(urllib.parse.parse_qsl((request.body or b"").decode()))
            if not self.ip_allowed:
                return self._json(403, {"error": "access_denied", "error_description": "IP address not allowed"})
            if form.get("client_id") != self.CLIENT_ID or form.get("client_secret") != self.SECRET:
                return self._json(401, {"error": "invalid_client", "error_description": "Client authentication failed."})
            tok = f"tok-{len(self.tokens) + 1}"
            self.tokens.append(tok)
            return self._json(200, {"access_token": tok, "token_type": "Bearer", "expires_in": 86400})
        if not self.ip_allowed:
            return self._json(403, {"error": {"code": "ip-not-allowed", "message": "허용되지 않은 IP"}})
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if token not in self.tokens:
            return self._json(401, {"error": {"code": "invalid-token", "message": "x"}})
        if path == "/api/v1/accounts":
            return self._json(200, {"result": self.accounts})
        if path == "/api/v1/prices":
            out = [
                {"symbol": s, "lastPrice": self.prices[s], "timestamp": "2026-10-29T10:00:00+09:00"}
                for s in query["symbols"].split(",")
                if s in self.prices
            ]
            return self._json(200, {"result": out})
        return self._json(404, {"error": {"code": "edge-blocked", "message": "no such path"}})

    @staticmethod
    def _json(status: int, payload: Any) -> HttpResponse:
        return HttpResponse(status, {"x-request-id": "req-1"}, json.dumps(payload).encode())


# ── 가짜 일봉 ────────────────────────────────────────────────────────────────


def business_days(start: date, n: int) -> list[str]:
    out = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def make_bars(closes: list[float], start: date = date(2024, 1, 1), opens: list[float] | None = None,
              volume: float = 1_000_000) -> list[dict[str, Any]]:
    days = business_days(start, len(closes))
    out = []
    for i, (d, c) in enumerate(zip(days, closes, strict=True)):
        o = opens[i] if opens else c
        out.append({"d": d, "o": o, "h": max(o, c), "l": min(o, c), "c": c, "v": volume})
    return out


class FakeBars:
    """yahoo 기호 -> 일봉 목록. 받은 요청을 적어 둔다."""

    def __init__(self, data: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.data = data or {}
        self.calls: list[tuple[str, str, str]] = []
        self.down = False

    def daily(self, yahoo_symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        self.calls.append((yahoo_symbol, start.isoformat(), end.isoformat()))
        if self.down:
            raise OSError("no network")
        rows = self.data.get(yahoo_symbol, [])
        return [dict(b) for b in rows if start.isoformat() <= b["d"] <= end.isoformat()]


def wave(n: int, base: float, amp: float, period: int, drift: float = 0.0) -> list[float]:
    import math

    return [round(base * (1 + drift * i) + amp * math.sin(2 * math.pi * i / period), 0) for i in range(n)]


class FakeIp:
    """공인 IP 서비스 가짜. 부른 주소를 적어 둔다."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.down = False
        self.body = b'{"ip":"123.45.67.89"}'

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        if self.down:
            raise OSError("no network")
        return self.body


@pytest.fixture
def fake_ip() -> FakeIp:
    return FakeIp()


@pytest.fixture
def fake_toss() -> FakeToss:
    return FakeToss()


@pytest.fixture
def fake_bars() -> FakeBars:
    a = wave(400, 70000, 6000, 40, 0.0005)
    b = wave(400, 150000, 15000, 30, 0.001)
    k = wave(400, 2500, 100, 50, 0.0002)
    return FakeBars(
        {
            "005930.KS": make_bars(a),
            "000660.KS": make_bars(b),
            "^KS11": make_bars(k, volume=0),
        }
    )


FIXED_NOW = datetime(2025, 6, 2, 17, 0, tzinfo=KST)  # 월요일 17:00


@pytest.fixture
def app_client(tmp_path: Path, fake_toss: FakeToss, fake_bars: FakeBars, fake_ip: FakeIp):  # type: ignore[no-untyped-def]
    app = create_app(
        tmp_path / "data",
        bars_source=fake_bars,
        toss_transport=lambda: fake_toss,
        ip_fetch=fake_ip,
        scrypt_n=2**12,
        scheduler=False,
        now=lambda: FIXED_NOW,
    )
    with TestClient(app) as client:
        client.app_ref = app  # type: ignore[attr-defined]
        yield client


PASSWORD = "correct horse 9"


def setup_owner(client: TestClient) -> str:
    r = client.post(
        "/api/setup",
        json={"password": PASSWORD, "password2": PASSWORD, "adult": True, "terms": True},
    )
    assert r.status_code == 200, r.text
    return r.json()["recovery_code"]
