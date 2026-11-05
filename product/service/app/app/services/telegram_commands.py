"""텔레그램 명령 받기(T-52 · SPEC 5-6 · QUALITY S12 · ARCHITECTURE 2-1 `services/telegram_commands.py`).

- 받는 명령은 `/상태`와 `/멈춤`(새 매수 멈춤) 둘뿐이고, 등록한 대화방에서 온 것만 받아요. 켜는 쪽 명령은 없어요
  (`ENGINE-RULES.md` R-L9 · R-L13). 다른 대화방은 무시하고 회신도 안 해요.
- 앱 루프(`app.py` `auto_loop`)가 30초마다 `poll`을 불러요. 상태 글(`status`)과 새 매수 멈춤 켜기(`pause`)는 조립이 넣어 줘요
  (실전 상태는 주인 `run/live.py`만 바꿔요 · 끄는 길은 주지 않아요).
- 설정 · 알림 · 보내기 · 본문 만들기는 `services/telegram.py`(`Telegram`)이고, 여기는 그것을 이어받아 받는 쪽만 더해요
  (`app.state.telegram`은 이 클래스의 객체 하나).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ..ports import Clock, TelegramError
from ..security.vault import Vault
from ..store.db import DB
from .telegram import ALREADY_PAUSED, HELP_REPLY, PAUSED_REPLY, BotFor, Telegram, msg_status

log = logging.getLogger("quant-mvp")


class TelegramCommands(Telegram):
    """`Telegram`(설정 · 알림 · 보내기) + 명령 받기(`poll`)."""

    def __init__(self, db: DB, vault: Vault, bot: BotFor, *, now: Clock,
                 status: Callable[[], dict[str, Any]], pause: Callable[[str], bool],
                 link: Callable[[], str | None] = lambda: None) -> None:
        super().__init__(db, vault, bot, now=now, link=link)
        self.status = status
        self.pause = pause  # 새 매수 멈춤을 켜요(이미 켜져 있으면 False). 끄는 길은 주지 않아요.

    def poll(self) -> list[str]:
        """새 메시지를 읽고 등록한 대화방의 두 명령만 처리해요. 처리한 명령 이름을 돌려줘요."""
        bot = self._bot()
        chat = self.chat_id
        if bot is None or chat is None:
            return []
        offset = int(self._meta("offset") or 0)
        try:
            updates = bot.call("getUpdates", {"offset": offset, "timeout": 0, "allowed_updates": ["message"]}) or []
        except TelegramError as exc:
            log.info("telegram poll: %s", exc.kind)
            return []
        done: list[str] = []
        for u in updates:
            self._set("offset", str(int(u.get("update_id", offset)) + 1))
            m = u.get("message") or {}
            if int((m.get("chat") or {}).get("id") or 0) != chat:
                continue  # 다른 대화방은 무시(회신도 안 해요)
            cmd = str(m.get("text") or "").strip().split("@")[0].split(" ")[0]
            if cmd == "/상태":
                self._send(msg_status(self.status()))
                done.append("status")
            elif cmd == "/멈춤":
                changed = self.pause("telegram")
                self._send(PAUSED_REPLY if changed else ALREADY_PAUSED)
                done.append("pause")
            elif cmd.startswith("/"):
                self._send(HELP_REPLY)
        return done
