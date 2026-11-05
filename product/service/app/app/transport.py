"""바깥으로 나가는 전송의 문 하나(TASKS T-00 · DEVELOPING 3절).

토스(시세 · 계좌 · 주문) · DART · 텔레그램 · 공인 IP 전송은 **기본이 가짜**예요. 실제 전송 객체는
아래 두 가지가 **둘 다** 있을 때만, 이 파일 안에서만 만들어요.

1. 환경 변수 `QUANT_LIVE_TRANSPORT=1`
2. 설치기(T-56)가 쓰는 설정 파일(`settings.LIVE_CONFIG_PATHS` 가운데 하나)에 `{"live_transport": true}`

두 열쇠를 읽는 것은 설정 층(`settings.live_enabled` · 환경 변수 · 설정 파일은 그 파일만 읽음)이고, 이 문은 그 판정으로만
실제 전송 객체를 만들어요(조립이 `settings.load()`로 한 번 읽은 값을 넘겨요).

개발 · 시험 · `./start.sh`는 이 둘을 만들지 않아요. 앱 코드의 다른 파일은 `urllib.request` ·
`http.client` · `socket`을 쓰지 않아요(`tests/test_no_orders.py`가 소스를 훑어 막아요).
"""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .settings import live_enabled

REQUEST_TIMEOUT_S = 20.0


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


@dataclass
class Transports:
    """앱이 쓰는 전송 묶음. 기본은 모두 가짜예요."""

    toss: Transport
    dart: Transport
    telegram: Transport
    ip_fetch: Callable[[str], bytes]
    is_live: bool = False

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
) -> Transports:
    if not live_enabled(env, config_paths):
        return fake_transports()
    return Transports(
        toss=_urllib_transport,
        dart=_urllib_transport,
        telegram=_urllib_transport,
        ip_fetch=_urllib_fetch,
        is_live=True,
    )


def is_fake(transport: object) -> bool:
    return isinstance(transport, FakeTransport | FakeFetch)

