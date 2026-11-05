"""주문 바꾸기 규칙(P1-08 · `app/orders/transform.py`): 순수 함수 · 값은 옮기기 전 `live.py`와 같음.

실전 흐름을 통한 확인은 `tests/test_live.py` · 하루 흐름 기준선(`tests/baseline/dayflow.py`)이 해요. 여기서는 규칙 하나하나의
경계값과 '순수'(시각 · 저장 · 전송 · 실행 · API를 모름)를 봐요.
"""

from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

from app.domain.engine import FEE
from app.domain.markets.kr import lower_limit, tick_round, ticks_below
from app.domain.rules import sell_floor
from app.orders import transform as tf

ORDERS = Path(__file__).resolve().parent.parent / "app" / "orders"


def test_orders_import_only_the_domain_and_never_read_the_clock() -> None:
    for p in sorted(ORDERS.rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                assert (node.module or "").startswith("domain"), (p.name, node.module)
            if isinstance(node, ast.Attribute):
                assert node.attr not in ("now", "today", "time", "monotonic"), (p.name, node.attr)


def test_client_order_id() -> None:
    assert tf.client_order_id(7, "2026-11-03", "005930", "BUY", 1) == "q7-20261103-005930-B-1"
    assert tf.client_order_id(7, "2026-11-03", "005930", "SELL", 2) == "q7-20261103-005930-S-2"


def test_buy_quantity_floors_then_fits_the_cash_with_fee() -> None:
    assert tf.buy_quantity(1_000_000, 11_000, 10_000_000) == 90  # ⌊1,000,000 ÷ 11,000⌋
    cash = 90 * 11_000 * (1 + FEE)
    assert tf.buy_quantity(1_000_000, 11_000, cash) == 90
    assert tf.buy_quantity(1_000_000, 11_000, cash - 1) == 89  # 묶이는 돈이 1원 넘으면 1주 줄임
    assert tf.buy_quantity(10_000, 11_000, 10_000_000) == 0


def test_sell_prices() -> None:
    assert tf.open_sell_price(10_000, protect=True) == lower_limit(10_000)
    assert tf.open_sell_price(10_000, protect=False) == sell_floor(10_000)
    assert tf.intraday_sell_price(9_200) == ticks_below(9_200, 2)


def test_widen_steps_r_o6() -> None:
    assert tf.widen_step("intraday_protect", 1, 9_000) == ("LIMIT", ticks_below(9_000, 5))
    assert tf.widen_step("intraday_protect", 2, 9_000) == ("MARKET", None)
    assert tf.widen_step("intraday_protect", 3, 9_000) is None
    assert tf.widen_step("intraday_take", 1, 12_000, 11_990) == ("LIMIT", 11_990)  # 하한 아래로 안 내려감
    assert tf.widen_step("intraday_take", 1, 12_000, 0.0) == ("LIMIT", ticks_below(12_000, 5))
    assert tf.widen_step("intraday_take", 2, 12_000, 0.0) is None  # 익절은 한 걸음만


def test_conditional_order_legs() -> None:
    assert tf.cond_triggers(9_303.0, None) == (tick_round(9_303.0), None)
    kind, legs = tf.cond_legs(9_300.0, 11_500.0)
    assert kind == "OCO" and legs == [
        {"side": "SELL", "trigger": 9_300, "price": int(tick_round(9_300.0 * (1 - tf.COND_STOP_GAP)))},
        {"side": "SELL", "trigger": 11_500, "price": 11_500}]
    assert tf.cond_legs(None, 11_500.0)[0] == "SINGLE"
    today = date(2026, 11, 3)
    assert tf.cond_expire(today) == date(2027, 11, 2)
    assert tf.cond_renew_due("2026-12-03", today) and not tf.cond_renew_due("2026-12-04", today)
    assert not tf.cond_renew_due(None, today)


def test_unfilled_and_closed_status() -> None:
    assert tf.unfilled_buy_close(0, 90) == ("canceled", "미체결 · 취소")
    assert tf.unfilled_buy_close(30, 90) == ("partial_closed", "일부 체결 30/90주")
    assert tf.closed_status(0) == "failed" and tf.closed_status(5) == "partial_closed"
