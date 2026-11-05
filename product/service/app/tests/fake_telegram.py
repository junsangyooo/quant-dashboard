"""가짜 텔레그램 봇 API(시험 전용 · 나가지 않아요). 토큰 · 대화방 번호는 지어낸 값이에요."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.adapters.transport import HttpRequest, HttpResponse, TransportError

TOKEN = "1234567890:AAFakeFakeFakeFakeFakeFakeFakeFake0"
MY_CHAT = 555000111
OTHER_CHAT = 999000222


@dataclass
class FakeTelegram:
    down: bool = False
    blocked: bool = False  # 봇이 막힘(403)
    updates: list[dict[str, Any]] = field(default_factory=list)
    sent: list[dict[str, Any]] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    _next: int = 100

    def message(self, chat: int, text: str, kind: str = "private", name: str = "민수") -> None:
        self._next += 1
        self.updates.append({"update_id": self._next, "message": {
            "message_id": self._next, "text": text, "chat": {"id": chat, "type": kind, "first_name": name}}})

    def __call__(self, req: HttpRequest) -> HttpResponse:
        if self.down:
            raise TransportError("fake down")
        assert req.url.startswith("https://api.telegram.org/bot")
        token, method = req.url[len("https://api.telegram.org/bot"):].split("/", 1)
        self.calls.append(method)
        if token != TOKEN:
            return self._reply(401, {"ok": False, "error_code": 401, "description": "Unauthorized"})
        body = json.loads(req.body or b"{}")
        if method == "getMe":
            return self._reply(200, {"ok": True, "result": {"id": 1, "is_bot": True, "username": "my_quant_bot"}})
        if method == "getUpdates":
            off = int(body.get("offset") or 0)
            return self._reply(200, {"ok": True, "result": [u for u in self.updates if u["update_id"] >= off]})
        if method == "sendMessage":
            if self.blocked:
                return self._reply(403, {"ok": False, "error_code": 403, "description": "Forbidden"})
            self.sent.append(body)
            return self._reply(200, {"ok": True, "result": {"message_id": len(self.sent)}})
        return self._reply(404, {"ok": False})

    @staticmethod
    def _reply(status: int, data: Any) -> HttpResponse:
        return HttpResponse(status, {"content-type": "application/json"}, json.dumps(data).encode())
