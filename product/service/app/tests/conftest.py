"""시험 공통: 임시 HOME, 네트워크 차단, 가짜 토스, 가짜 일봉, 앱 클라이언트."""

from __future__ import annotations

import atexit
import json
import os
import shutil
import socket
import tempfile
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

# ── 시험 중 HOME은 임시 폴더(P1-02 ④) ─────────────────────────────────────────
# 앱은 import할 때 `Path.home()`으로 키 파일 · 실제 전송 설정 파일의 기본 경로를 정해요(`app/vault.py` · `app/transport.py`).
# 그래서 앱을 import하기 **전에** HOME을 운영체제 임시 폴더로 바꿔 두어, 시험(과 시험이 띄우는 자식 프로세스 · 환경을 물려받음)이
# 실제 `~/.config/quant-service/`를 만들거나 읽지 않게 해요. 레포 안(tests/.tmp)이 아닌 까닭: 레포 안 키 파일은 앱이 거절해요.
REAL_HOME = os.environ.get("HOME", "")
REAL_CONFIG_DIR = Path(REAL_HOME) / ".config" / "quant-service" if REAL_HOME else None
REAL_CONFIG_EXISTED_AT_START = bool(REAL_CONFIG_DIR and REAL_CONFIG_DIR.exists())
# pytest 프로세스에서만 바꿔요(pytest가 `PYTEST_VERSION`을 둬요). 이 모듈을 가짜 서버(`tests/e2e_server.py` ·
# `tests/baseline/screen_server.py`)가 도우미로 import할 때는 띄우는 쪽이 준 HOME · 키 파일 폴더를 그대로 써요(빈 폴더가 남지 않게).
UNDER_PYTEST = "PYTEST_VERSION" in os.environ
TEST_HOME = Path(tempfile.mkdtemp(prefix="quant-test-home-")) if UNDER_PYTEST else Path(REAL_HOME)
if UNDER_PYTEST:
    os.environ["HOME"] = str(TEST_HOME)
    atexit.register(shutil.rmtree, TEST_HOME, ignore_errors=True)  # sessionfinish가 못 돌아도 지워요

from app.main import create_app  # noqa: E402  (HOME을 바꾼 뒤에 import해요)
from app.market import KST  # noqa: E402
from app.toss import HttpRequest, HttpResponse, TransportError  # noqa: E402


# ── 화면처럼 CSRF 값을 되돌려 보내는 시험 클라이언트(T-51) ─────────────────


class CsrfClient(TestClient):
    """화면 스크립트처럼 qm_csrf 쿠키를 X-CSRF-Token 머리글로 붙여요. 빼고 보내기 시험은 TestClient를 그대로 써요."""

    def request(self, method: str, url: Any, **kw: Any) -> Any:  # type: ignore[override]
        if method.upper() not in ("GET", "HEAD", "OPTIONS"):
            token = self.cookies.get("qm_csrf")
            headers = dict(kw.pop("headers", None) or {})
            if token and not any(k.lower() == "x-csrf-token" for k in headers):
                headers["x-csrf-token"] = token
            kw["headers"] = headers
        return super().request(method, url, **kw)


# ── 컴퓨터 키 파일은 시험 임시 폴더에만(T-50) ──────────────────────────────


# basetemp가 레포 안(tests/.tmp)이라 키 파일만은 운영체제 임시 폴더에 둬요(레포 안 키 파일은 앱이 거절해요).


@pytest.fixture(autouse=True)
def keyfile_path(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    with tempfile.TemporaryDirectory(prefix="quant-test-kf-") as d:
        path = Path(d) / "keyfile"
        monkeypatch.setattr("app.vault.KEYFILE_PATH", path)
        yield path


# ── 바깥 소켓 0개 (T-00 ③) ─────────────────────────────────────────────────
# 시험 전체에서 바깥(유닉스 소켓 · 루프백이 아닌 곳)으로 이으려 한 시도를 모두 적어 두고,
# 시험이 끝날 때 0이 아니면 실패로 끝내요(코드가 예외를 삼켜도 잡혀요).

OUTBOUND_ATTEMPTS: list[str] = []
_LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _outbound(where: str, address: Any) -> None:
    OUTBOUND_ATTEMPTS.append(f"{where}: {address!r}")
    raise RuntimeError(f"network blocked in tests: {address!r}")


def _is_local(address: Any) -> bool:
    return isinstance(address, tuple) and bool(address) and str(address[0]) in _LOOPBACK


_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_getaddrinfo = socket.getaddrinfo


def _guard_connect(self: socket.socket, address: Any) -> Any:
    if self.family == socket.AF_UNIX or _is_local(address):
        return _original_connect(self, address)
    return _outbound("connect", address)


def _guard_connect_ex(self: socket.socket, address: Any) -> Any:
    if self.family == socket.AF_UNIX or _is_local(address):
        return _original_connect_ex(self, address)
    return _outbound("connect_ex", address)


def _guard_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
    if host is None or str(host) in _LOOPBACK:
        return _original_getaddrinfo(host, *args, **kwargs)
    return _outbound("getaddrinfo", host)


def pytest_configure(config: pytest.Config) -> None:
    socket.socket.connect = _guard_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _guard_connect_ex  # type: ignore[method-assign]
    socket.getaddrinfo = _guard_getaddrinfo  # type: ignore[assignment]
    # 실제 전송의 두 열쇠가 개발 컴퓨터에 있어도 시험은 늘 가짜(T-00 ②)
    os.environ.pop("QUANT_LIVE_TRANSPORT", None)
    import app.transport as transport

    transport.LIVE_CONFIG_PATHS = ()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    if OUTBOUND_ATTEMPTS:
        print("\n바깥으로 나가려 한 시도:", *OUTBOUND_ATTEMPTS, sep="\n  ")
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
    if UNDER_PYTEST:
        shutil.rmtree(TEST_HOME, ignore_errors=True)  # 임시 HOME(키 파일이 남지 않게)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """시험 안에서는 바깥 네트워크에 절대 나가지 않는다(위 감시에 더해 create_connection도 막아요)."""
    monkeypatch.setattr(
        socket, "create_connection", lambda address, *a, **k: _outbound("create_connection", address)
    )
    monkeypatch.delenv("QUANT_LIVE_TRANSPORT", raising=False)


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
    """종목 코드(지수는 KOSPI) -> 일봉 목록. 받은 요청을 적어 둔다."""

    def __init__(self, data: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self.data = data or {}
        self.calls: list[tuple[str, str, str]] = []
        self.down = False

    def daily(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]:
        self.calls.append((symbol, start.isoformat(), end.isoformat()))
        if self.down:
            raise OSError("no network")
        if symbol not in self.data:  # 토스는 없는 코드에 404를 줘요(TossSource → SymbolNotFound)
            from app.market import SymbolNotFound

            raise SymbolNotFound(symbol)
        rows = self.data[symbol]
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
            "005930": make_bars(a),
            "000660": make_bars(b),
            "KOSPI": make_bars(k, volume=0),
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
    with CsrfClient(app) as client:
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


def confirm(client: TestClient, action: str, password: str = PASSWORD) -> dict[str, str]:
    """비밀번호 다시 받기(V2-33) → 1회용 토큰 머리글."""
    r = client.post("/api/confirm", json={"password": password, "action": action})
    assert r.status_code == 200, r.text
    return {"x-confirm-token": r.json()["token"]}
