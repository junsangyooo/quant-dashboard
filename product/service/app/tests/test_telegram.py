"""T-52 텔레그램: 가짜 봇 API로만. `/멈춤`이 켜는 쪽으로 가는 길 0 · 다른 대화방 명령 무시 · 기본 가짜 전송."""

from __future__ import annotations

import inspect
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from app.services import telegram as tg
from app.main import create_app
from app.domain.markets.kr import KST
from app.adapters.fake import FakeTransport
from app.adapters.transport import build_transports
from tests.conftest import PASSWORD, CsrfClient, confirm, setup_owner
from tests.fake_telegram import MY_CHAT, OTHER_CHAT, TOKEN, FakeTelegram

NOW = datetime(2026, 11, 2, 20, 10, tzinfo=KST)


def boot(tmp_path: Path, fake: FakeTelegram | None, **kw: Any) -> CsrfClient:
    app = create_app(tmp_path / "data", scrypt_n=2**12, scheduler=False, now=lambda: NOW,
                     telegram_transport=fake, **kw)
    c = CsrfClient(app)
    c.app_ref = app  # type: ignore[attr-defined]
    setup_owner(c)
    return c


def connected(tmp_path: Path, **kw: Any) -> tuple[CsrfClient, FakeTelegram]:
    fake = FakeTelegram()
    c = boot(tmp_path, fake, **kw)
    assert c.put("/api/telegram", json={"token": TOKEN}).status_code == 200
    fake.message(MY_CHAT, "/start")
    r = c.post("/api/telegram/find-chat")
    assert r.status_code == 200 and r.json()["chat"] is True
    return c, fake


def T(c: CsrfClient) -> tg.Telegram:
    return c.app_ref.state.telegram  # type: ignore[attr-defined,no-any-return]


# ── 기본 가짜 전송(T-00) ─────────────────────────────────────────────────────


def test_default_transport_is_fake(tmp_path: Path) -> None:
    assert isinstance(build_transports().telegram, FakeTransport)
    c = boot(tmp_path, None)  # 시험 전송을 주지 않으면 앱 기본(가짜)
    r = c.put("/api/telegram", json={"token": TOKEN})
    assert r.status_code == 502 and "닿지 않아요" in r.json()["error"]
    fake = c.app_ref.state.transports.telegram  # type: ignore[attr-defined]
    assert isinstance(fake, FakeTransport) and fake.calls  # 나가려던 요청은 가짜가 받았어요


# ── 연결(V2-08) ──────────────────────────────────────────────────────────────


def test_connect_find_chat_and_test_send(tmp_path: Path) -> None:
    c, fake = connected(tmp_path)
    v = c.get("/api/telegram").json()
    assert v["saved"] and v["bot"] == "@my_quant_bot" and v["chat"] and v["chat_name"] == "민수"
    assert TOKEN not in str(v)
    r = c.post("/api/telegram/test")
    assert r.status_code == 200 and r.json()["last_sent"].startswith("2026-11-02T20:10")
    assert fake.sent[-1] == {"chat_id": MY_CHAT, "text": tg.TEST_TEXT, "disable_web_page_preview": True}


def test_bad_token_and_no_chat(tmp_path: Path) -> None:
    fake = FakeTelegram()
    c = boot(tmp_path, fake)
    r = c.put("/api/telegram", json={"token": "nope"})
    assert r.status_code == 400 and r.json()["kind"] == "token" and fake.calls == []
    r = c.put("/api/telegram", json={"token": "1234567890:AAWrongWrongWrongWrongWrongWrong00"})
    assert r.status_code == 400 and r.json()["kind"] == "token"
    assert "AAWrong" not in r.text
    assert c.get("/api/telegram").json()["saved"] is False
    c.put("/api/telegram", json={"token": TOKEN})
    fake.message(MY_CHAT, "안녕")  # /start가 아님
    fake.message(OTHER_CHAT, "/start", kind="group")  # 개인 대화방이 아님
    r = c.post("/api/telegram/find-chat")
    assert r.status_code == 400 and r.json()["error"] == "대화방을 못 찾았어요 · 봇에게 /start를 보내고 다시 찾아요"


def test_token_change_and_delete_need_password(tmp_path: Path) -> None:
    c, _ = connected(tmp_path)
    assert c.put("/api/telegram", json={"token": TOKEN}).status_code == 403
    assert c.delete("/api/telegram").status_code == 403
    assert c.delete("/api/telegram", headers=confirm(c, "telegram_key_delete")).json()["saved"] is False


# ── 본문: 종목 · 금액 없음 ────────────────────────────────────────────────────


def test_messages_have_no_symbol_or_money() -> None:
    texts = [tg.msg_precheck(True, 3), tg.msg_precheck(False, 0), tg.msg_check_done(2), tg.msg_fills(3),
             tg.msg_fills(1, live=False), tg.msg_order_failed(1), tg.msg_todo("결과 모르는 주문 [삼성전자]"),
             tg.msg_status({"label": "운용 중", "today_pct": 0.8, "orders": 3, "todos": 1}), tg.TEST_TEXT,
             tg.PAUSED_REPLY, tg.ALREADY_PAUSED, tg.HELP_REPLY]
    for t in texts:
        assert tg.safe_text(t) == t
    assert tg.msg_precheck(True, 3) == "장 시작 전 점검 · 통과 · 08:35 주문 3건"
    assert tg.msg_check_done(2) == "확인 끝 · 내일 주문 2건"
    assert tg.msg_fills(3) == "실전 · 체결 3건 · 앱에서 보기"
    assert tg.msg_fills(1, live=False).startswith("모의 · ")
    assert tg.msg_todo("결과 모르는 주문 [삼성전자]") == "결과 모르는 주문 · 앱에서 보기"
    assert tg.msg_status({"label": "운용 중", "today_pct": 0.8, "orders": 3, "todos": 1}) == \
        "운용 중 · 오늘 +0.8% · 내일 주문 3건 · 할 일 1"
    for bad in ("005930 체결", "매수 1,250,000원", "현금 300원"):
        with pytest.raises(ValueError):
            tg.safe_text(bad)


def test_notify_events_and_link(tmp_path: Path) -> None:
    c, fake = connected(tmp_path, ts_names=["quant.tail1234.ts.net"])
    t = T(c)
    assert t.notify("check_done", tg.msg_check_done(2)) is True
    assert fake.sent[-1]["text"] == "확인 끝 · 내일 주문 2건\nhttps://quant.tail1234.ts.net"
    # 모의 체결은 기본 꺼짐 · 알림함에는 남아요(live 0)
    n = len(fake.sent)
    assert t.notify("paper_fills", tg.msg_fills(1, live=False), live=False) is False
    assert len(fake.sent) == n
    row = c.app_ref.state.db.one("SELECT live, telegram FROM alerts ORDER BY id DESC LIMIT 1")  # type: ignore[attr-defined]
    assert row["live"] == 0 and row["telegram"] is None
    # 끌 수 없는 것
    r = c.put("/api/telegram/events", json={"key": "precheck", "on": False})
    assert r.status_code == 400 and r.json()["kind"] == "locked"
    assert c.put("/api/telegram/events", json={"key": "check_done", "on": False}).json()["events"][1]["on"] is False
    assert t.notify("check_done", tg.msg_check_done(1)) is False
    assert t.notify("precheck", tg.msg_precheck(True, 1)) is True
    with pytest.raises(ValueError):
        t.notify("fills", "005930 체결 1건")


def test_send_failure_makes_one_yellow_todo(tmp_path: Path) -> None:
    c, fake = connected(tmp_path)
    t = T(c)
    fake.blocked = True
    assert t.notify("fills", tg.msg_fills(1)) is False
    fake.down = True
    assert t.notify("fills", tg.msg_fills(2)) is False
    db = c.app_ref.state.db  # type: ignore[attr-defined]
    rows = db.all("SELECT severity, title FROM todos WHERE kind='telegram_fail' AND status='open'")
    assert [(r["severity"], r["title"]) for r in rows] == [("yellow", "텔레그램 보내기 실패")]
    assert c.get("/api/telegram").json()["last_error"]
    fake.blocked = fake.down = False
    assert t.notify("fills", tg.msg_fills(1)) is True
    assert not db.all("SELECT 1 FROM todos WHERE kind='telegram_fail' AND status='open'")


# ── 명령 ─────────────────────────────────────────────────────────────────────


def test_status_and_pause_from_registered_chat(tmp_path: Path) -> None:
    c, fake = connected(tmp_path)
    t, db = T(c), c.app_ref.state.db  # type: ignore[attr-defined]
    fake.message(MY_CHAT, "/상태")
    assert t.poll() == ["status"]
    assert fake.sent[-1]["text"] == "운용 전 · 할 일 0"
    fake.message(MY_CHAT, "/멈춤")
    assert t.poll() == ["pause"]
    assert db.get_meta("live.new_buys_paused") == "1" and db.get_meta("live.new_buys_paused_by") == "telegram"
    assert fake.sent[-1]["text"] == tg.PAUSED_REPLY
    fake.message(MY_CHAT, "/멈춤@my_quant_bot")
    assert t.poll() == ["pause"] and fake.sent[-1]["text"] == tg.ALREADY_PAUSED
    fake.message(MY_CHAT, "/상태")
    t.poll()
    assert fake.sent[-1]["text"].startswith("새 매수 멈춤 · ")
    # 같은 메시지를 두 번 처리하지 않아요(offset)
    n = len(fake.sent)
    assert t.poll() == [] and len(fake.sent) == n


def test_other_chat_commands_are_ignored(tmp_path: Path) -> None:
    c, fake = connected(tmp_path)
    t, db = T(c), c.app_ref.state.db  # type: ignore[attr-defined]
    n = len(fake.sent)
    for text in ("/멈춤", "/상태", "/start"):
        fake.message(OTHER_CHAT, text, name="남")
        fake.message(OTHER_CHAT, text, kind="group")
    assert t.poll() == []
    assert len(fake.sent) == n  # 회신도 없어요
    assert db.get_meta("live.new_buys_paused") is None


def test_no_command_turns_anything_on(tmp_path: Path) -> None:
    """`/멈춤`이 켜는 쪽으로 가는 길 0: 어떤 글을 보내도 새 매수 멈춤이 풀리지 않아요."""
    c, fake = connected(tmp_path)
    t, db = T(c), c.app_ref.state.db  # type: ignore[attr-defined]
    fake.message(MY_CHAT, "/멈춤")
    t.poll()
    for text in ["/켜기", "/시작", "/재개", "/resume", "/start", "/unpause", "/멈춤 해제", "/멈춤 off", "/상태 켜기",
                 "/buy 005930", "/매수", "/멈춤해제", "다시 켜", "/settings", "/멈춤 0", ""]:
        fake.message(MY_CHAT, text)
    t.poll()
    assert db.get_meta("live.new_buys_paused") == "1"
    # 코드에도 끄는 길이 없어요: pause 콜백은 켜기만, 텔레그램 모듈은 멈춤 값을 쓰지 않아요
    src = inspect.getsource(tg)
    assert "new_buys_paused" not in src and "resume" not in src.lower()
    assert set(tg.EVENTS) and {"/상태", "/멈춤"} == set(c.get("/api/telegram").json()["commands"])


def test_runner_polls_after_restart(tmp_path: Path) -> None:
    """재부팅 뒤 로그인 없이도(키 파일) `/멈춤`을 받아요."""
    c, fake = connected(tmp_path)
    c.post("/api/logout")
    app = create_app(tmp_path / "data", scrypt_n=2**12, scheduler=False, now=lambda: NOW, telegram_transport=fake)
    assert not app.state.vault.unlocked
    fake.message(MY_CHAT, "/멈춤")
    assert app.state.telegram.poll() == ["pause"]
    assert PASSWORD  # 비밀번호 없이
