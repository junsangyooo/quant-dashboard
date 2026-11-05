"""앱의 기본 가짜 전송: **응답 없음**(TASKS T-00 · P1-06 · DEVELOPING 3절).

받은 요청을 적어 두기만 하고 바깥으로 나가지 않아요. 답을 만드는 함수(`responder`)가 없으면 늘 '응답 없음'(`TransportError`)으로
끝나요. 앱은 `responder`를 넣지 않아요(실제 전송의 두 열쇠가 없을 때 `transport.build_transports`가 이 가짜만 만들어요).
응답이 있는 가짜 토스 · 텔레그램 서버는 시험에만 있어요(`tests/fake_toss.py` · `tests/fake_telegram.py` · `tests/conftest.py`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .transport import HttpRequest, HttpResponse, Transport, TransportError


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
