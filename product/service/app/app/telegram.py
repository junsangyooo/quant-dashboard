"""텔레그램(T-52 · SPEC 5-6 · V2-08 · V2-52): 고객 자신의 봇 하나 · 등록한 대화방 하나 · 명령 둘.

- 전송은 `transport.Transports.telegram`(기본 가짜 · T-00). 이 파일은 소켓을 쓰지 않아요.
- 봇 토큰은 금고(`vault`)에, 대화방 번호 · 봇 이름 · 마지막 보낸 시각은 meta에. 토큰은 글 · 예외 · 로그에 넣지 않아요.
- 본문에는 종목 · 금액을 넣지 않아요(`safe_text`가 막아요). 종목은 앱 안 할 일 제목에만.
- 명령은 `/상태`와 `/멈춤`(새 매수 멈춤) 둘뿐이고, 등록한 대화방에서 온 것만 받아요. 켜는 쪽 명령은 없어요.
- 보내기 실패는 할 일 노랑 '텔레그램 보내기 실패'(열린 것이 있으면 하나만).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from .db import DB
from .transport import HttpRequest, Transport, TransportError
from .vault import Vault, VaultError

log = logging.getLogger("quant-mvp")

API = "https://api.telegram.org"
TOKEN = "telegram_token"
TOKEN_RE = re.compile(r"^\d{5,12}:[A-Za-z0-9_-]{30,64}$")
FAIL_TITLE = "텔레그램 보내기 실패"
TEST_TEXT = "시험 보내기 · 이 대화방으로 알림이 와요"
LINK_TAIL = "앱에서 보기"

# 사건 스위치(V2-52). locked = 끌 수 없음(SPEC 5-6), default = 처음 값.
EVENTS: dict[str, dict[str, Any]] = {
    "precheck": {"title": "08:30 장 시작 전 점검", "locked": True, "default": True},
    "check_done": {"title": "20:10 확인 끝", "locked": False, "default": True},
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


class TelegramError(Exception):
    """화면에 그대로 보여도 되는 글(토큰 없음). kind: token · chat · send · locked."""

    def __init__(self, message: str, kind: str = "send", status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.kind = kind
        self.status = status


def safe_text(text: str) -> str:
    """종목 · 금액이 섞이면 보내지 않아요(코드 실수를 시험이 잡게)."""
    if _SYMBOL.search(text) or _MONEY.search(text):
        raise ValueError("텔레그램 본문에 종목 · 금액을 넣지 않아요")
    return text


# ── 본문 만들기(SPEC 5-6 '매일' · 5-5 할 일) ─────────────────────────────────


def msg_precheck(passed: bool, orders: int) -> str:
    if passed:
        return f"장 시작 전 점검 · 통과 · 08:35 주문 {orders}건"
    return f"장 시작 전 점검 · 실패 · 오늘 주문 멈춤 · {LINK_TAIL}"


def msg_check_done(orders: int) -> str:
    return f"확인 끝 · 내일 주문 {orders}건"


def msg_fills(n: int, live: bool = True) -> str:
    return f"{'실전' if live else '모의'} · 체결 {n}건 · {LINK_TAIL}"


def msg_order_failed(n: int) -> str:
    return f"실전 · 주문 실패 {n}건 · {LINK_TAIL}"


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


# ── 서비스 ───────────────────────────────────────────────────────────────────


class Telegram:
    def __init__(self, db: DB, vault: Vault, transport: Transport, *, now: Callable[[], datetime],
                 status: Callable[[], dict[str, Any]], pause: Callable[[str], bool],
                 link: Callable[[], str | None] = lambda: None) -> None:
        self.db = db
        self.vault = vault
        self.transport = transport
        self.now = now
        self.status = status
        self.pause = pause  # 새 매수 멈춤을 켜요(이미 켜져 있으면 False). 끄는 길은 주지 않아요.
        self.link = link

    # 저장된 값
    def _meta(self, key: str) -> str | None:
        return self.db.get_meta(f"tg.{key}")

    def _set(self, key: str, value: str | None) -> None:
        self.db.set_meta(f"tg.{key}", value)

    def _bot(self) -> Bot | None:
        if not self.vault.has_secret(TOKEN) or not self.vault.can_read:
            return None
        token = self.vault.get_secret(TOKEN)
        return Bot(token, self.transport) if token else None

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
        me = Bot(t, self.transport).call("getMe")
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

    def _need(self) -> Bot:
        bot = self._bot()
        if bot is None:
            if self.vault.has_secret(TOKEN):
                raise VaultError("잠금 · 비밀번호를 입력하면 다시 실행돼요", 423)
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
        self.db.run("UPDATE todos SET status='resolved', resolved_at=? WHERE kind='telegram_fail' AND status='open'",
                    (self.now().isoformat(timespec="seconds"),))
        return True

    def _fail_todo(self) -> None:
        if self.db.one("SELECT 1 FROM todos WHERE kind='telegram_fail' AND status='open'"):
            return
        self.db.run(
            "INSERT INTO todos(run_id, kind, severity, title, body, status, created_at) VALUES(NULL,?,?,?,?, 'open', ?)",
            ("telegram_fail", "yellow", FAIL_TITLE, "봇 토큰 · 대화방을 확인해요 · 설정 › 알림",
             self.now().isoformat(timespec="seconds")),
        )

    def notify(self, event: str, text: str, *, live: bool = True, title: str | None = None) -> bool:
        """알림함에 남기고(실전 · 모의 칩) 켜진 사건이면 텔레그램으로 보내요."""
        safe_text(text)
        sent = False
        if self.events().get(event, False) and self.vault.has_secret(TOKEN):
            sent = self._send(text)
        self.db.run("INSERT INTO alerts(at, live, kind, title, body, telegram) VALUES(?,?,?,?,?,?)",
                    (self.now().isoformat(timespec="seconds"), 1 if live else 0, event, title or text, text,
                     "sent" if sent else None))
        return sent

    # 명령(`/상태` · `/멈춤`)
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
