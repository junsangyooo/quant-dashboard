"""토스 1.2.28 클라이언트(TASKS T-10).

- 엔드포인트마다 가짜 응답 시험: 가짜 서버는 받은 요청과 내보낸 응답을 명세(`vendor/toss-openapi-1.2.28.json`)로
  검사하고(`spec_errors`), 클라이언트는 그 응답을 읽어요.
- 응답 필드가 빠지면 '응답 이상'(`TossShapeError`)으로 끝나요(R-O14).
- 주문 · 조건주문 · 내역은 가짜 전송으로만 불러요.
"""

from __future__ import annotations

import hashlib
from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from app.adapters import toss
from app.adapters.toss import RateLimiter, TossApiError, TossClient, TossCredentials, TossShapeError, link_state, rate_group
from tests import openapi_check as oc
from tests.conftest import make_bars
from tests.fake_toss import (
    ACCOUNT_NO,
    CLIENT_ID,
    CLIENT_SECRET,
    FakeTossServer,
    holiday,
    investor_row,
    regular_day,
    stock_row,
)


class Clock:
    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


@pytest.fixture
def server() -> FakeTossServer:
    s = FakeTossServer()
    s.stocks = {
        "005930": stock_row("005930", "삼성전자"),
        "035720": stock_row("035720", "카카오", list_date="2017-07-10"),
        "005935": stock_row("005935", "삼성전자우", common=False),
        "122630": stock_row("122630", "KODEX 레버리지", security_type="ETF", leverage="2"),
        "091990": stock_row("091990", "셀트리온헬스케어", "KOSDAQ"),
    }
    closes = [70000 + 100 * i for i in range(450)]
    s.bars = {"005930": make_bars(closes, start=date(2025, 1, 1))}
    s.index_bars = {"KOSPI": make_bars([2500 + i for i in range(300)], start=date(2025, 6, 2))}
    s.prices = {"005930": "71300", "035720": "0"}
    s.warnings = {"035720": [{"warningType": "INVESTMENT_WARNING", "exchange": "KRX", "startDate": "2026-10-30",
                              "endDate": None}]}
    s.sectors = [{"sectorId": "S1", "name": "반도체", "depth": 0, "parentSectorId": None},
                 {"sectorId": "S1-1", "name": "메모리", "depth": 1, "parentSectorId": "S1"}]
    s.sector_members = {"S1-1": ["005930"]}
    s.investor = {"005930": [investor_row(f"2026-10-{d:02d}", str(1000 * d), str(-500 * d)) for d in range(1, 31)]}
    s.holdings = {"005930": {"quantity": "10", "avg": "70000", "sellable": "10"}}
    return s


@pytest.fixture
def client(server: FakeTossServer) -> TossClient:
    clock = Clock()
    return TossClient(TossCredentials(CLIENT_ID, CLIENT_SECRET, ACCOUNT_NO), transport=server,
                      limiter=RateLimiter(clock=clock, sleep=clock.sleep))


def test_spec_file_is_the_vendor_file() -> None:
    assert hashlib.sha256(oc.SPEC_PATH.read_bytes()).hexdigest() == oc.SPEC_SHA256
    assert oc.spec()["info"]["version"] == "1.2.28"


# ── 요청 한도 그룹 ─────────────────────────────────────────────────────────


def test_every_spec_operation_has_its_rate_group() -> None:
    """명세의 경로 39개 · 메서드 42개가 모두 그룹이 있고, 설명의 그룹 이름과 같아요."""
    import json
    import re

    seen = 0
    for path, ops in oc.spec()["paths"].items():
        for method, op in ops.items():
            if method not in ("get", "post", "delete"):
                continue
            seen += 1
            named = re.findall(r"Rate Limits Group\*\*: `([A-Z_]+)`", json.dumps(op, ensure_ascii=False))
            concrete = path.replace("{symbol}", "005930").replace("{sectorId}", "S1").replace("{orderId}", "o1")
            concrete = concrete.replace("{conditionalOrderId}", "c1")
            group = rate_group(method.upper(), concrete)
            assert group != "OTHER", (method, path)
            if named:
                assert group == named[0], (method, path, named)
    assert seen == 42


def test_rate_limiter_waits_per_group() -> None:
    clock = Clock()
    lim = RateLimiter(clock=clock, sleep=clock.sleep, default_rate=2)
    for _ in range(4):
        lim.acquire("MARKET_DATA_CHART")
    lim.acquire("ORDER")  # 다른 그룹은 따로 세요
    assert [g for g, _ in lim.waited] == ["MARKET_DATA_CHART", "MARKET_DATA_CHART"]
    assert clock.slept == [0.5, 0.5]
    lim.observe("ORDER", {"X-RateLimit-Limit": "10", "X-RateLimit-Remaining": "0"})
    assert lim.rate["ORDER"] == 10
    lim.acquire("ORDER")
    assert lim.waited[-1] == ("ORDER", pytest.approx(0.1))


def test_429_waits_retry_after_then_succeeds(server: FakeTossServer, client: TossClient) -> None:
    client.token()
    server.rate_limited = 2
    assert client.buying_power() == Decimal("10000000")
    assert [w for _, w in client.limiter.waited if w == 1.0] == [1.0, 1.0]
    server.rate_limited = 5
    with pytest.raises(TossApiError) as e:
        client.buying_power()
    assert e.value.status == 429 and link_state(e.value) == "unreachable"


# ── 엔드포인트마다 가짜 응답 ─────────────────────────────────────────────


def test_candles_before_and_adjusted(server: FakeTossServer, client: TossClient) -> None:
    page = client.candles("005930", count=3, before="2025-03-03T23:59:59+09:00")
    assert [c.d for c in page.candles] == ["2025-03-03", "2025-02-28", "2025-02-27"]  # 최신순
    assert page.next_before is not None
    req = next(r for r in server.calls if r[1] == "/api/v1/candles")
    assert req[0] == "GET"
    bars = client.daily_bars("005930", date(2025, 1, 1), date(2026, 9, 30))
    assert len(bars) == 450 and bars[0]["d"] == "2025-01-01" and bars[-1]["c"] == 70000 + 100 * 449
    assert bars == sorted(bars, key=lambda b: b["d"])
    assert server.spec_errors == []
    # adjusted=true 가 기본, 꺼서 보낼 수도 있어요(쿼리 'false')
    client.candles("005930", count=1, adjusted=False)
    assert server.spec_errors == []


def test_index_candles_and_prices(server: FakeTossServer, client: TossClient) -> None:
    bars = client.daily_bars("KOSPI", date(2025, 6, 1), date(2026, 12, 31), index=True)
    assert len(bars) == 300 and bars[0]["c"] == 2500
    assert client.index_prices(["KOSPI"])["KOSPI"].price == Decimal("2799")
    assert server.spec_errors == []


def test_stocks_all_and_stocks(server: FakeTossServer, client: TossClient) -> None:
    kospi = client.stocks_all("KOSPI")
    assert {s.symbol for s in kospi} == {"005930", "035720", "005935", "122630"}
    assert {s.symbol: s.common for s in kospi}["005935"] is False
    etf = client.stocks_all("KOSPI", security_type="ETF")
    assert [s.symbol for s in etf] == ["122630"]
    info = client.stocks(["005930", "122630", "035720"])
    assert info["122630"].leverage == Decimal("2") and info["005930"].leverage is None
    assert info["035720"].list_date == "2017-07-10" and info["005930"].shares == Decimal("100000000")
    assert server.spec_errors == []


def test_warnings_sectors_investor(server: FakeTossServer, client: TossClient) -> None:
    assert [w.kind for w in client.warnings("035720")] == ["INVESTMENT_WARNING"]
    assert client.warnings("005930") == []
    secs = client.sectors()
    assert [(s.sector_id, s.depth, s.parent) for s in secs] == [("S1", 0, None), ("S1-1", 1, "S1")]
    assert client.sector_stocks("S1-1") == ["005930"]
    rows, nxt = client.investor_trading("005930", count=10)
    assert [r.d for r in rows][:2] == ["2026-10-30", "2026-10-29"] and nxt == "2026-10-20"
    assert rows[0].foreign == Decimal("30000") and rows[0].institution == Decimal("-15000")
    assert rows[0].foreign_rate == Decimal("51.2")
    rows2, _ = client.investor_trading("005930", count=10, until=nxt)
    assert rows2[0].d == "2026-10-20"
    assert server.spec_errors == []


def test_market_calendar_regular_late_open_and_holiday(server: FakeTossServer, client: TossClient) -> None:
    cal = client.market_calendar(date(2026, 11, 2))
    assert cal.today.open and cal.today.regular is not None
    assert cal.today.regular.start.hour == 9 and cal.previous.d == date(2026, 10, 30)
    assert cal.next.d == date(2026, 11, 3)

    def special(d: date) -> dict[str, Any]:
        if d == date(2026, 11, 19):  # 수능일 · 1시간 늦게 열어요
            return regular_day(d, (10, 0), (16, 30))
        if d == date(2026, 11, 20) or d.weekday() >= 5:
            return holiday(d)
        return regular_day(d)

    server.calendar = special
    cal = client.market_calendar(date(2026, 11, 19))
    assert cal.today.regular is not None and cal.today.regular.start.hour == 10
    assert cal.next.d == date(2026, 11, 23)  # 휴장일 · 주말 건너뜀
    cal = client.market_calendar(date(2026, 11, 20))
    assert cal.today.open is False
    assert server.spec_errors == []


def test_account_endpoints(server: FakeTossServer, client: TossClient) -> None:
    assert client.account() == (7, "1234")
    assert client.buying_power() == Decimal("10000000")
    assert client.sellable_quantity("005930") == Decimal("10")
    assert client.sellable_quantity("035720") == Decimal("0")
    assert [(c.country, c.rate) for c in client.commissions()] == [("KR", Decimal("0.00015"))]
    h = client.holdings()
    assert [(x.symbol, x.qty, x.avg_price) for x in h] == [("005930", Decimal("10"), Decimal("70000"))]
    # 계좌 헤더는 명세의 X-Tossinvest-Account
    assert server.spec_errors == []


def test_prices_anomalies(server: FakeTossServer, client: TossClient) -> None:
    got = client.prices_checked(["005930", "035720", "999999"], prev_close={"005930": 50000})
    assert got.items == {}
    assert got.anomalies == {"005930": "전일 대비 30% 넘음", "035720": "가격 0", "999999": "가격 없음"}
    got = client.prices_checked(["005930"], prev_close={"005930": 70000})
    assert got.items["005930"].price == Decimal("71300") and got.anomalies == {}


# ── 주문 · 조건주문 · 내역 (가짜 전송으로만) ─────────────────────────────


def test_orders_on_fake_only(server: FakeTossServer, client: TossClient) -> None:
    oid = client.create_order(symbol="005930", side="BUY", quantity=90, price=Decimal("77000"), tif="OPG",
                              client_order_id="r1-20261103-005930-B-1")
    assert oid == "ord-1"
    sent = server.bodies[-1]
    assert sent[:2] == ("POST", "/api/v1/orders")
    assert sent[2] == {"symbol": "005930", "side": "BUY", "orderType": "LIMIT", "timeInForce": "OPG",
                       "quantity": "90", "price": "77000", "clientOrderId": "r1-20261103-005930-B-1"}
    # 같은 주문 번호 다시 → 409 중복(R-O11 · 회차를 올려 다시 내요)
    with pytest.raises(TossApiError) as e:
        client.create_order(symbol="005930", side="BUY", quantity=90, price=77000, tif="OPG",
                            client_order_id="r1-20261103-005930-B-1")
    assert e.value.status == 409
    server.fill(oid, "10", "76500")
    o = client.order(oid)
    assert o.status == "PARTIAL_FILLED" and o.execution.filled_qty == Decimal("10")
    assert o.execution.avg_price == Decimal("76500")
    opened, cursor = client.orders("OPEN")
    assert [x.order_id for x in opened] == ["ord-1"] and cursor is None
    assert client.modify_order(oid, order_type="LIMIT", price=76000) == oid
    assert client.cancel_order(oid) == oid
    with pytest.raises(TossApiError) as e:
        client.cancel_order(oid)
    assert e.value.status == 409
    closed, _ = client.orders("CLOSED")
    assert [x.status for x in closed] == ["CANCELED"]
    assert server.spec_errors == []


def test_conditional_orders_on_fake_only(server: FakeTossServer, client: TossClient) -> None:
    cid = client.create_conditional_order(
        symbol="005930", kind="OCO", quantity=10, expire=date(2027, 11, 2),
        first={"side": "SELL", "trigger": 65100, "price": 63147},
        second={"side": "SELL", "trigger": 80500, "price": 72450},
    )
    assert server.bodies[-1][2]["first"] == {"orderSide": "SELL", "triggerPrice": "65100", "orderPrice": "63147"}
    rows, _ = client.conditional_orders("OPEN")
    assert [(r.cond_id, r.kind, r.qty) for r in rows] == [(cid, "OCO", Decimal("10"))]
    assert rows[0].second is not None and rows[0].second.trigger == Decimal("80500")
    client.modify_conditional_order(cid, kind="SINGLE", quantity=5, expire=date(2027, 11, 2),
                                    first={"side": "SELL", "trigger": 65100})
    assert client.conditional_order(cid).kind == "SINGLE"
    client.cancel_conditional_order(cid)
    assert client.conditional_order(cid).first.status == "CANCELED"
    assert ("DELETE", f"/api/v1/conditional-orders/{cid}") in server.calls
    assert server.spec_errors == []


def test_default_client_cannot_send_orders() -> None:
    """전송을 주지 않은 클라이언트의 주문은 가짜 전송에 적히고 끝나요(T-00)."""
    c = TossClient(TossCredentials("a", "b"))
    with pytest.raises(toss.TossUnreachableError):
        c.create_order(symbol="005930", side="SELL", quantity=1, price=1)
    assert [r.url.rsplit("/", 1)[-1] for r in c.transport.calls] == ["token"]  # type: ignore[attr-defined]


# ── 응답 이상 (R-O14) ─────────────────────────────────────────────────────

MISSING = [
    ("/api/v1/candles", lambda c: c.candles("005930", count=2), lambda p: _drop(p, "result.candles.0.closePrice")),
    ("/api/v1/candles", lambda c: c.candles("005930", count=2), lambda p: _drop(p, "result.candles")),
    ("/api/v1/stocks/all", lambda c: c.stocks_all("KOSPI"), lambda p: _drop(p, "result.0.isCommonShare")),
    ("/api/v1/stocks", lambda c: c.stocks(["005930"]), lambda p: _drop(p, "result.0.sharesOutstanding")),
    ("/api/v1/stocks/035720/warnings", lambda c: c.warnings("035720"), lambda p: _drop(p, "result.0.warningType")),
    ("/api/v1/sectors", lambda c: c.sectors(), lambda p: _drop(p, "result.sectors.0.depth")),
    ("/api/v1/stocks/005930/investor-trading", lambda c: c.investor_trading("005930"),
     lambda p: _drop(p, "result.records.0.foreigner")),
    ("/api/v1/market-calendar/KR", lambda c: c.market_calendar(), lambda p: _drop(p, "result.nextBusinessDay")),
    ("/api/v1/buying-power", lambda c: c.buying_power(), lambda p: _drop(p, "result.cashBuyingPower")),
    ("/api/v1/sellable-quantity", lambda c: c.sellable_quantity("005930"),
     lambda p: _drop(p, "result.sellableQuantity")),
    ("/api/v1/commissions", lambda c: c.commissions(), lambda p: _drop(p, "result.0.commissionRate")),
    ("/api/v1/holdings", lambda c: c.holdings(), lambda p: _drop(p, "result.items.0.quantity")),
    ("/api/v1/market-indicators/KOSPI/candles", lambda c: c.candles("KOSPI", index=True),
     lambda p: _drop(p, "result.candles.0.timestamp")),
    ("/api/v1/buying-power", lambda c: c.buying_power(), lambda p: {"nothing": 1}),
    ("/api/v1/buying-power", lambda c: c.buying_power(), lambda p: _set(p, "result.cashBuyingPower", "abc")),
]


def _walk(payload: Any, dotted: str) -> tuple[Any, str]:
    keys = dotted.split(".")
    cur = payload
    for k in keys[:-1]:
        cur = cur[int(k)] if isinstance(cur, list) else cur[k]
    return cur, keys[-1]


def _drop(payload: Any, dotted: str) -> Any:
    cur, last = _walk(payload, dotted)
    del cur[last]
    return payload


def _set(payload: Any, dotted: str, value: Any) -> Any:
    cur, last = _walk(payload, dotted)
    cur[last] = value
    return payload


@pytest.mark.parametrize(("path", "call", "mangle"), MISSING, ids=[f"{i}-{m[0]}" for i, m in enumerate(MISSING)])
def test_missing_field_is_bad_answer(server: FakeTossServer, client: TossClient, path: str, call, mangle) -> None:  # type: ignore[no-untyped-def]
    client.account()
    server.mangle[path] = mangle
    with pytest.raises(TossShapeError) as e:
        call(client)
    assert link_state(e.value) == "shape" and e.value.path == path


def test_order_list_missing_field_is_bad_answer(server: FakeTossServer, client: TossClient) -> None:
    client.create_order(symbol="005930", side="BUY", quantity=1, price=70000)
    server.mangle["/api/v1/orders"] = lambda p: _drop(p, "result.orders.0.execution") if "orders" in p["result"] else p
    with pytest.raises(TossShapeError):
        client.orders("OPEN")


def test_connection_check_names_bad_answer() -> None:
    from app.connect import FAILURES

    assert FAILURES["shape"][0] == "토스 응답 이상이에요"
    assert {"auth", "ip", "unreachable", "account", "maintenance", "shape", "error"} == set(FAILURES)
