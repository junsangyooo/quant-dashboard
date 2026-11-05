"""텔레그램(T-52 · SPEC 5-6 · V2-08 · V2-52): 고객 자신의 봇 하나 · 등록한 대화방 하나 · 명령 둘.

- 봇 API 보내기는 어댑터 `adapters/telegram.py`(`Bot` · 전송은 `transport.Transports.telegram` · 기본 가짜 · T-00)예요.
  조립(`app.py`)이 토큰으로 봇을 만드는 함수(`bot`)를 넣어 줘요(쓰기 일은 어댑터를 몰라요).
  이 파일은 설정 · 알림(`Notifier` 포트 · `notify`) · 본문 만들기예요. 명령 받기(`/상태` · `/멈춤`)는
  `services/telegram_commands.py`예요. 소켓을 쓰지 않아요.
- 봇 토큰은 금고(`vault`)에, 대화방 번호 · 봇 이름 · 마지막 보낸 시각은 meta에. 토큰은 글 · 예외 · 로그에 넣지 않아요.
- 본문에는 종목 · 금액을 넣지 않아요(`safe_text`가 막아요). 종목은 앱 안 할 일 제목에만.
- 명령은 `/상태`와 `/멈춤`(새 매수 멈춤) 둘뿐이고, 등록한 대화방에서 온 것만 받아요. 켜는 쪽 명령은 없어요.
- 보내기 실패는 할 일 노랑 '텔레그램 보내기 실패'(열린 것이 있으면 하나만).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from ..copy import texts as T
from ..ports import Clock, TelegramError
from ..security.vault import Vault, VaultError
from ..store import todos as todo_store
from ..store.db import DB

TOKEN = "telegram_token"
TOKEN_RE = re.compile(r"^\d{5,12}:[A-Za-z0-9_-]{30,64}$")
FAIL_TITLE = "텔레그램 보내기 실패"
TEST_TEXT = "시험 보내기 · 이 대화방으로 알림이 와요"
LINK_TAIL = "앱에서 보기"

# 사건 스위치(V2-52). locked = 끌 수 없음(SPEC 5-6), default = 처음 값.
EVENTS: dict[str, dict[str, Any]] = {
    "precheck": {"title": T.event_precheck, "locked": True, "default": True},
    "check_done": {"title": T.event_check_done, "locked": False, "default": True},
    "fills": {"title": "체결", "locked": False, "default": True},
    "order_failed": {"title": "주문 실패", "locked": True, "default": True},
    "todo_red": {"title": "급한 할 일", "locked": True, "default": True},
    "todo_yellow": {"title": "확인할 할 일", "locked": False, "default": True},
    "info": {"title": "새 매수 멈춤 · 운용 끝 · 업데이트 끝", "locked": False, "default": True},
    "paper_fills": {"title": "모의 체결", "locked": False, "default": False},
}

# 본문에 들어가면 안 되는 것: 종목 코드(6자리) · 금액(원 · 쉼표 숫자)
_SYMBOL = re.compile(r"(?<!\d)\d{6}(?!\d)")
_MONEY = re.compile(r"\d[\d,]*\s*원|\d{1,3}(,\d{3})+")


def safe_text(text: str) -> str:
    """종목 · 금액이 섞이면 보내지 않아요(코드 실수를 시험이 잡게)."""
    if _SYMBOL.search(text) or _MONEY.search(text):
        raise ValueError("텔레그램 본문에 종목 · 금액을 넣지 않아요")
    return text


# ── 본문 만들기(SPEC 5-6 '매일' · 5-5 할 일) ─────────────────────────────────


def msg_precheck(passed: bool, orders: int) -> str:
    if passed:
        return T.precheck_passed.format(n=orders)
    return T.precheck_failed


def msg_check_done(orders: int) -> str:
    return T.notify_check_done.format(n=orders)


def msg_fills(n: int, live: bool = True) -> str:
    return T.notify_fills.format(mode='실전' if live else '모의', n=n)


def msg_order_failed(n: int) -> str:
    return T.notify_order_failed.format(n=n)


def msg_todo(title: str) -> str:
    """할 일 제목에서 [종목]을 빼고 보내요(SPEC 5-5 표 머리)."""
    plain = re.sub(r"\s*\[[^\]]*\]\s*", " ", title).strip()
    return f"{plain} · {LINK_TAIL}"


def msg_status(state: dict[str, Any]) -> str:
    """`/상태` 회신: '운용 중 · 오늘 +0.8% · 내일 주문 3건 · 할 일 1'."""
    parts = [state.get("label") or "운용 전"]
    if state.get("today_pct") is not None:
        parts.append(f"오늘 {state['today_pct']:+.1f}%")
    if state.get("orders") is not None:
        parts.append(f"내일 주문 {int(state['orders'])}건")
    parts.append(f"할 일 {int(state.get('todos') or 0)}")
    return " · ".join(parts)


PAUSED_REPLY = "새 매수를 멈췄어요 · 매도 · 손절은 그대로 나가요 · 다시 켜기는 앱에서 비밀번호로"
ALREADY_PAUSED = "이미 새 매수 멈춤이에요 · 다시 켜기는 앱에서 비밀번호로"
HELP_REPLY = "명령은 /상태 · /멈춤 둘이에요"


# ── 서비스 ───────────────────────────────────────────────────────────────────

# 봇 만들기: 토큰 → 봇(`call(method, params)` · 조립이 어댑터 `adapters.telegram.Bot`로 넣어 줘요)
BotFor = Callable[[str], Any]


class Telegram:
    """설정(V2-08 · V2-52) · 알림(`notify`) · 보내기. 명령 받기는 `telegram_commands.TelegramCommands`가 이어받아 더해요."""

    def __init__(self, db: DB, vault: Vault, bot: BotFor, *, now: Clock,
                 link: Callable[[], str | None] = lambda: None) -> None:
        self.db = db
        self.vault = vault
        self.bot = bot
        self.now = now
        self.link = link

    # 저장된 값
    def _meta(self, key: str) -> str | None:
        return self.db.get_meta(f"tg.{key}")

    def _set(self, key: str, value: str | None) -> None:
        self.db.set_meta(f"tg.{key}", value)

    def _bot(self) -> Any:
        if not self.vault.has_secret(TOKEN) or not self.vault.can_read:
            return None
        token = self.vault.get_secret(TOKEN)
        return self.bot(token) if token else None

    @property
    def chat_id(self) -> int | None:
        raw = self._meta("chat")
        return int(raw) if raw else None

    def events(self) -> dict[str, bool]:
        saved = json.loads(self._meta("events") or "{}")
        return {k: (True if v["locked"] else bool(saved.get(k, v["default"]))) for k, v in EVENTS.items()}

    def view(self) -> dict[str, Any]:
        on = self.events()
        return {
            "saved": self.vault.has_secret(TOKEN),
            "bot": self._meta("bot"),
            "chat": self.chat_id is not None,
            "chat_name": self._meta("chat_name"),
            "last_sent": self._meta("last_sent"),
            "last_error": self._meta("last_error"),
            "events": [{"key": k, "title": v["title"], "locked": v["locked"], "on": on[k]}
                       for k, v in EVENTS.items()],
            "commands": ["/상태", "/멈춤"],
        }

    # 연결(V2-08)
    def save_token(self, token: str) -> dict[str, Any]:
        t = (token or "").strip()
        if not TOKEN_RE.match(t):
            raise TelegramError("봇 토큰 꼴이 아니에요 · '숫자:글자' 모양 전체를 입력해요", "token")
        me = self.bot(t).call("getMe")
        self.vault.put_secret(TOKEN, t)
        self._set("bot", f"@{me.get('username')}" if isinstance(me, dict) and me.get("username") else None)
        for k in ("chat", "chat_name", "offset", "last_sent", "last_error"):
            self._set(k, None)
        return self.view()

    def delete(self) -> dict[str, Any]:
        self.vault.delete_secret(TOKEN)
        for k in ("bot", "chat", "chat_name", "offset", "last_sent", "last_error"):
            self._set(k, None)
        return self.view()

    def find_chat(self) -> dict[str, Any]:
        """봇에게 /start를 보낸 개인 대화방을 찾아요(getUpdates · 마지막 것)."""
        bot = self._need()
        updates = bot.call("getUpdates", {"timeout": 0, "allowed_updates": ["message"]}) or []
        found = None
        last = None
        for u in updates:
            last = u.get("update_id", last)
            m = u.get("message") or {}
            chat = m.get("chat") or {}
            if chat.get("type") == "private" and str(m.get("text") or "").startswith("/start"):
                found = chat
        if last is not None:
            self._set("offset", str(int(last) + 1))
        if not found:
            raise TelegramError("대화방을 못 찾았어요 · 봇에게 /start를 보내고 다시 찾아요", "chat")
        self._set("chat", str(int(found["id"])))
        self._set("chat_name", str(found.get("first_name") or "")[:40] or None)
        return self.view()

    def test_send(self) -> dict[str, Any]:
        self._send(TEST_TEXT, raise_errors=True)
        return self.view()

    def set_event(self, key: str, on: bool) -> dict[str, Any]:
        if key not in EVENTS:
            raise TelegramError("없는 알림이에요")
        if EVENTS[key]["locked"]:
            raise TelegramError("이 알림은 끌 수 없어요", "locked")
        saved = json.loads(self._meta("events") or "{}")
        saved[key] = bool(on)
        self._set("events", json.dumps(saved))
        return self.view()

    def _need(self) -> Any:
        bot = self._bot()
        if bot is None:
            if self.vault.has_secret(TOKEN):
                raise VaultError(T.locked_retry, 423)
            raise TelegramError("봇 토큰을 먼저 입력해 주세요", "token")
        return bot

    # 보내기
    def _send(self, text: str, *, raise_errors: bool = False) -> bool:
        body = safe_text(text)
        link = self.link()
        if link:
            body = f"{body}\n{link}"
        bot = self._bot()
        chat = self.chat_id
        try:
            if bot is None or chat is None:
                raise TelegramError("텔레그램이 연결되지 않았어요 · 설정 › 알림", "chat")
            bot.call("sendMessage", {"chat_id": chat, "text": body, "disable_web_page_preview": True})
        except TelegramError as exc:
            self._set("last_error", exc.message)
            self._fail_todo()
            if raise_errors:
                raise
            return False
        self._set("last_sent", self.now().isoformat(timespec="seconds"))
        self._set("last_error", None)
        todo_store.resolve_open(self.db, self.now().isoformat(timespec="seconds"), "telegram_fail")
        return True

    def _fail_todo(self) -> None:
        if todo_store.has_open_todo(self.db, "telegram_fail"):
            return
        todo_store.add_todo(self.db, None, "telegram_fail", "yellow", None, FAIL_TITLE, "봇 토큰 · 대화방을 확인해요 · 설정 › 알림",
                            None, self.now().isoformat(timespec="seconds"))

    def notify(self, event: str, text: str, *, live: bool = True, title: str | None = None) -> bool:
        """알림함에 남기고(실전 · 모의 칩) 켜진 사건이면 텔레그램으로 보내요."""
        safe_text(text)
        sent = False
        if self.events().get(event, False) and self.vault.has_secret(TOKEN):
            sent = self._send(text)
        todo_store.add_alert(self.db, self.now().isoformat(timespec="seconds"), 1 if live else 0, event, title or text,
                             text, "sent" if sent else None)
        return sent
