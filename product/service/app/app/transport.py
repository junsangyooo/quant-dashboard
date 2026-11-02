"""바깥으로 나가는 전송의 문 하나(TASKS T-00 · DEVELOPING 3절).

토스 · DART · 텔레그램 · 공인 IP · 시세 전송은 **기본이 가짜**예요. 실제 전송 객체는
아래 두 가지가 **둘 다** 있을 때만, 이 파일 안에서만 만들어요.

1. 환경 변수 `QUANT_LIVE_TRANSPORT=1`
2. 설치기(T-56)가 쓰는 설정 파일(`LIVE_CONFIG_PATHS` 가운데 하나)에 `{"live_transport": true}`

개발 · 시험 · `./start.sh`는 이 둘을 만들지 않아요. 앱 코드의 다른 파일은 `urllib.request` ·
`http.client` · `socket`을 쓰지 않아요(`tests/test_no_orders.py`가 소스를 훑어 막아요).
"""

from __future__ import annotations

import http.client
import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REQUEST_TIMEOUT_S = 20.0
LIVE_ENV = "QUANT_LIVE_TRANSPORT"
# 설치기가 쓰는 자리: 서버(systemd)는 /etc, PC(launchd)는 사용자 설정 폴더. 레포 · 데이터 폴더 밖이에요.
LIVE_CONFIG_PATHS: tuple[Path, ...] = (
    Path("/etc/quant-service/live-transport.json"),
    Path.home() / ".config" / "quant-service" / "live-transport.json",
)


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None = None


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[HttpRequest], HttpResponse]


class TransportError(Exception):
    """응답 없음: 연결 실패나 시간 초과(가짜 전송이 나가지 않을 때도)."""


# ── 실제 전송 (이 파일 밖에서 부르지 않아요) ─────────────────────────────────


def _urllib_transport(request: HttpRequest, timeout: float = REQUEST_TIMEOUT_S) -> HttpResponse:
    req = urllib.request.Request(
        request.url, data=request.body, headers=dict(request.headers), method=request.method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return HttpResponse(int(resp.status), headers, resp.read())
    except urllib.error.HTTPError as exc:
        headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
        try:
            body = exc.read()
        except (OSError, http.client.HTTPException):
            body = b""
        return HttpResponse(int(exc.code), headers, body)
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        raise TransportError(type(exc).__name__) from None


def _urllib_fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=10.0) as resp:
        return bytes(resp.read(256))


# ── 가짜 전송 (기본) ────────────────────────────────────────────────────────


@dataclass
class FakeTransport:
    """나가지 않는 전송. 받은 요청을 적어 두고, 답이 없으면 '응답 없음'으로 끝나요.

    `responder`를 주면 그 함수가 가짜 응답을 만들어요(시험 · 가짜 토스 서버).
    """

    name: str
    responder: Transport | None = None
    calls: list[HttpRequest] = field(default_factory=list)

    is_live = False

    def __call__(self, request: HttpRequest) -> HttpResponse:
        self.calls.append(request)
        if self.responder is None:
            raise TransportError("fake-transport")
        return self.responder(request)


@dataclass
class FakeFetch:
    """공인 IP 보기의 가짜. 나가지 않아요."""

    calls: list[str] = field(default_factory=list)
    is_live = False

    def __call__(self, url: str) -> bytes:
        self.calls.append(url)
        raise OSError("fake-transport")


# ── 문 ──────────────────────────────────────────────────────────────────────


def _config_says_live(paths: Iterable[Path]) -> bool:
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("live_transport") is True:
            return True
    return False


def live_enabled(
    env: Mapping[str, str] | None = None, config_paths: Iterable[Path] | None = None
) -> bool:
    """환경 변수 **과** 설정 파일이 둘 다 '켬'일 때만 True."""
    env = os.environ if env is None else env
    if env.get(LIVE_ENV) != "1":
        return False
    return _config_says_live(LIVE_CONFIG_PATHS if config_paths is None else config_paths)


@dataclass
class Transports:
    """앱이 쓰는 전송 묶음. 기본은 모두 가짜예요."""

    toss: Transport
    dart: Transport
    telegram: Transport
    ip_fetch: Callable[[str], bytes]
    is_live: bool = False
    bars: Any = None  # 시세 출처(실제 전송일 때만 바깥 출처 · T-11에서 토스로 바뀌어요)

    def toss_factory(self) -> Callable[[], Transport]:
        return lambda: self.toss


def fake_transports() -> Transports:
    return Transports(
        toss=FakeTransport("toss"),
        dart=FakeTransport("dart"),
        telegram=FakeTransport("telegram"),
        ip_fetch=FakeFetch(),
        is_live=False,
    )


def build_transports(
    env: Mapping[str, str] | None = None,
    config_paths: Iterable[Path] | None = None,
    *,
    cache_dir: str | None = None,
) -> Transports:
    if not live_enabled(env, config_paths):
        return fake_transports()
    from .market import YahooSource  # 실제 전송일 때만 만들어요(T-11에서 토스 출처로 바뀌어요)

    return Transports(
        toss=_urllib_transport,
        dart=_urllib_transport,
        telegram=_urllib_transport,
        ip_fetch=_urllib_fetch,
        is_live=True,
        bars=YahooSource(cache_dir=cache_dir),
    )


def is_fake(transport: object) -> bool:
    return isinstance(transport, FakeTransport | FakeFetch)


class OfflineBars:
    """가짜 전송일 때의 시세 출처: 나가지 않고 '받지 못함'으로 끝나요."""

    is_live = False

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def daily(self, yahoo_symbol: str, start: Any, end: Any) -> list[dict[str, Any]]:
        self.calls.append((yahoo_symbol, str(start), str(end)))
        raise OSError("fake-transport")
