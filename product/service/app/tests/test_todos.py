"""T-70 할 일 · 알림(SPEC 5-6): 표의 행마다 제목 · 심각도 · 막히는 범위 · 해결 길 · 텔레그램(종목 · 금액 뺌)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from app import telegram as tg
from app.adapters.toss import TossUnreachableError
from app.run.live import SCOPE, TODO
from tests.test_live import SYM, World, body, give_pos, morning, running
from tests.test_blocks import R

D = date(2026, 11, 3)


def todo(w: World, kind: str) -> dict:  # type: ignore[type-arg]
    row = w.db.one("SELECT * FROM todos WHERE kind=? AND status='open'", (kind,))
    assert row is not None, kind
    return dict(row)


def test_table_titles_and_severity() -> None:
    expect = {
        "precheck": ("red", "장 시작 전 점검 실패 · {why}"), "toss_down": ("red", "토스 연결이 끊겼어요"),
        "other_user": ("red", "다른 곳에서 같은 키를 쓰고 있어요"), "check_fail": ("red", "오늘 확인 실패"),
        "unknown": ("red", "결과 모르는 주문 · [{name}]"), "mismatch": ("red", "계좌 불일치 · [{name}]"),
        "corp": ("red", "권리 변동 · [{name}]"), "shape": ("red", "토스 응답이 예상과 달라요"),
        "sell_fail2": ("red", "안 팔린 종목 · [{name}]"),
        "missed_open": ("yellow", "시가 주문을 놓쳤어요 · 앱이 꺼져 있었어요"),
        "loss_limit": ("yellow", "하루 손실 한도 · 내일 새 매수 멈춤"),
        "huge": ("yellow", "큰 주문 확인 · [{name}] [{amount}]"),
        "cond_fail": ("yellow", "조건주문 다시 걸기 실패 · [{name}]"), "dart_error": ("yellow", "DART 연결 오류"),
        "cash_cut": ("yellow", "운용 현금이 줄었어요(출금)"),
    }
    for k, v in expect.items():
        assert TODO[k] == v, k
    assert tg.FAIL_TITLE == "텔레그램 보내기 실패"


def test_precheck_fail_title_scope_and_watch_off(tmp_path: Path) -> None:
    """빨강 '장 시작 전 점검 실패 · 허용 IP' · 그날 주문 0 · 장중 감시 멈춤 · 통과하면 풀림."""
    w = World(tmp_path)
    rid = running(w, body(sell=[R("stop_loss", value=7, exec_="intraday")]))
    give_pos(w, rid, SYM, 10, 10_000)
    w.server.today = D
    w.server.ip_allowed = False
    w.clock.at(D, 8, 30)
    w.live.precheck(rid)
    t = todo(w, "precheck")
    assert t["title"] == "장 시작 전 점검 실패 · 허용 IP" and t["severity"] == "red" and t["body"] == "그날 주문 0"
    w.server.ip_allowed = True
    w.server.prices[SYM] = "9000"
    w.clock.at(D, 10, 0)
    assert w.live.intraday_tick(rid) == []  # 장중 감시 멈춤(조건주문만)
    w.clock.at(D, 8, 40)
    assert w.live.precheck(rid)
    assert not w.db.one("SELECT 1 FROM todos WHERE kind='precheck' AND status='open'")


def test_toss_down(tmp_path: Path) -> None:
    w = World(tmp_path)
    rid = running(w)
    w.server.down = True
    w.server.today = D
    w.clock.at(D, 8, 30)
    assert w.live.precheck(rid) is False
    assert todo(w, "toss_down")["body"] == SCOPE["toss_down"]


def test_check_fail_blocks_next_buys(tmp_path: Path) -> None:
    w = World(tmp_path)
    rid = running(w)
    w.live.set_meta(rid, "check_failed", "2026-11-02T20:20:00+09:00")
    out = morning(w, D)
    assert out == [{"sym": SYM, "skip": "오늘 확인 실패"}] and w.orders() == []


def test_huge_title_has_amount_but_telegram_does_not(tmp_path: Path) -> None:
    w = World(tmp_path, cash="500000000")
    rid = running(w, amount=300_000_000)
    st = w.live.state(rid)
    st["next"]["plans"] = [{"sym": SYM, "side": "buy", "value": 120_000_000, "close": 10_000.0, "reason": []}]
    w.live.save(rid, st)
    morning(w, D)
    t = todo(w, "huge")
    assert t["title"] == "큰 주문 확인 · [종목30] [119,999,000원]" and t["severity"] == "yellow"
    sent = [x for e, x in w.sent if e == "todo_yellow"][-1]
    assert sent == "큰 주문 확인 · 앱에서 보기" and tg.safe_text(sent)
    # 해결: '보내기'(비밀번호 · API) → 한 번에 보내요
    res = w.live.send_big(rid, t["id"])
    assert res["status"] == "sent" and w.orders()[-1]["qty"] == 10_909


def test_red_todos_reach_telegram_without_symbol(tmp_path: Path) -> None:
    w = World(tmp_path)
    rid = running(w)
    give_pos(w, rid, SYM, 10, 10_000)
    w.holding(SYM, 8, 10_000)
    w.live.reconcile(rid)
    t = todo(w, "mismatch")
    assert t["title"] == "계좌 불일치 · [종목30]" and t["body"] == "그 종목 0"
    assert ("todo_red", "계좌 불일치 · 앱에서 보기") in w.sent
    w.live.match_account(rid, SYM)  # 해결: 계좌에 맞추기
    assert w.live.state(rid)["pos"][SYM]["qty"] == 8 and SYM not in w.live.state(rid)["blocked"]


def test_cond_fail_and_cash_cut_and_loss_limit(tmp_path: Path) -> None:
    w = World(tmp_path, cash="20000000")
    rid = running(w, body(sell=[R("stop_loss", value=7, exec_="broker")]))
    give_pos(w, rid, SYM, 10, 10_000)
    w.server.today = D
    w.clock.at(D, 9, 1)
    def broken(**_: object) -> str:
        raise TossUnreachableError("down")

    w.client.create_conditional_order = broken  # type: ignore[method-assign]
    w.live.place_conds(rid)
    assert todo(w, "cond_fail")["title"] == "조건주문 다시 걸기 실패 · [종목30]"
    w.server.cash = "100"
    w.live.reconcile(rid)
    assert todo(w, "cash_cut")["severity"] == "yellow"


def test_loss_limit_todo(tmp_path: Path) -> None:
    from tests.conftest import make_bars  # noqa: F401

    closes = [10_000.0] * 59 + [9_690.0]
    w = World(tmp_path, closes={SYM: closes})
    vid = w.version(body())
    w.clock.at(date(2026, 10, 30), 21, 0)
    rid = w.live.start(vid, 1_000_000)
    st = w.live.state(rid)
    st["cash"] = 0.0
    st["pos"] = {SYM: {"qty": 100, "avg": 10_000, "entry_d": "2026-10-01", "peak": 10_000}}
    st["last_equity"] = 1_000_000
    w.live.save(rid, st)
    w.clock.at(date(2026, 11, 2), 21, 0)
    w.live.check(rid)
    t = todo(w, "loss_limit")
    assert t["body"] == "다음 거래일 매수 0"


def test_dart_error_blocks_dart_strategy_buys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    w = World(tmp_path)
    rid = running(w)
    monkeypatch.setattr("app.run.live.DART_ITEMS", {"price"})  # 이 전략의 줄을 재무 조건으로 셈
    w.db.set_meta("dart.error", "key")
    w.clock.at(D, 21, 0)
    res = w.live.check(rid)
    assert [p for p in res["plans"] if p["side"] == "buy"] == []
    assert todo(w, "dart_error")["body"] == "재무 조건이 든 전략의 새 매수 0"


def test_telegram_locked_and_default_off() -> None:
    """끌 수 없음: 빨간 할 일 · 주문 실패 · 점검 결과 · 기본 꺼짐: 모의 체결(SPEC 5-6)."""
    locked = {k for k, v in tg.EVENTS.items() if v["locked"]}
    assert {"todo_red", "order_failed", "precheck"} <= locked
    assert tg.EVENTS["paper_fills"]["default"] is False


def test_info_events_go_to_alerts(tmp_path: Path) -> None:
    """정보: 새 매수를 멈췄어요 · 운용을 끝냈어요 · 배당 입금 · 업데이트 끝 → 알림(할 일 아님)."""
    w = World(tmp_path)
    rid = running(w)
    w.live.pause_new_buys()
    w.live.end(rid)
    texts = [t for e, t in w.sent if e == "info"]
    assert "새 매수를 멈췄어요 · 매도 · 손절은 그대로 나가요" in texts
    assert any(t.startswith("운용을 끝냈어요") for t in texts)
    assert json.dumps(w.todos()).count("info") == 0
