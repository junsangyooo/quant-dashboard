"""텔레그램 봇 API 보내기(T-52 · SPEC 5-6): 고객 자신의 봇 하나에 요청 하나를 보내고 답을 읽어요.

- 전송은 `transport.Transports.telegram`(기본 가짜 · 응답 없음 · T-00). 이 파일은 소켓을 쓰지 않아요.
- 봇 토큰은 요청 주소에만 넣고 글 · 예외 · 기록에 남기지 않아요(`Bot.__repr__`도 가림).
- 설정 · 알림은 `services/telegram.py`(`Telegram`) · 명령 받기는 `services/telegram_commands.py`예요. 봇 오류
  `TelegramError`는 포트 파일(`ports.py`)에 있어요(쓰기 일도 내서).
"""

from __future__ import annotations

import json
from typing import Any

from ..ports import TelegramError
from .transport import HttpRequest, Transport, TransportError

API = "https://api.telegram.org"


# ── 봇 API ───────────────────────────────────────────────────────────────────


class Bot:
    def __init__(self, token: str, transport: Transport) -> None:
        self._token = token
        self.transport = transport

    def __repr__(self) -> str:  # 토큰을 남기지 않아요
        return "Bot(<token hidden>)"

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        req = HttpRequest(
            "POST", f"{API}/bot{self._token}/{method}", {"Content-Type": "application/json"},
            json.dumps(params or {}).encode(),
        )
        try:
            res = self.transport(req)
        except TransportError:
            raise TelegramError("텔레그램에 닿지 않아요 · 인터넷 연결을 확인해 주세요", "send", 502) from None
        try:
            data = json.loads(res.body or b"{}")
        except ValueError:
            data = {}
        if res.status in (401, 404):
            raise TelegramError("봇 토큰이 맞지 않아요 · BotFather에서 받은 토큰을 확인해요", "token")
        if res.status == 403:
            raise TelegramError("봇이 대화방에 보낼 수 없어요 · 봇에게 /start를 다시 보내 주세요", "chat")
        if res.status >= 400 or not data.get("ok"):
            raise TelegramError("텔레그램이 요청을 받지 않았어요 · 잠시 뒤 다시 해 주세요", "send", 502)
        return data.get("result")
