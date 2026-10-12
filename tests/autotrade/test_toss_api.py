"""The Toss client against a fake Toss (autotrade/broker/toss_api.py, PHASE3.md 2.2).

No test reaches the network: the transport is the in-process fake (tests/autotrade/fake_toss.py)
or a scripted function. The laptop's secrets hold a live account; nothing here reads them.
"""

from __future__ import annotations

import io
import json
import stat
import urllib.error
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from autotrade.broker.toss_api import (
    HttpRequest,
    HttpResponse,
    LiveOrdersBlockedError,
    LivePermit,
    OrderRequest,
    RateLimiter,
    TossApiError,
    TossClient,
    TossCredentials,
    TossNotConfiguredError,
    TossUnreachableError,
    TransportError,
    error_of,
    link_state,
    order_from_api,
    price_text,
    read_credentials,
    urllib_transport,
)
from autotrade.domain.instruments import Currency
from autotrade.timeutil import KST

from .fake_toss import FakeToss

D = Decimal
NOW = datetime(2026, 7, 1, 9, 5, tzinfo=KST)


class Wall:
    """The client's wall clock (seconds), to age the token."""

    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


def creds(account: str | None = "123-456-78901") -> TossCredentials:
    return TossCredentials(FakeToss.CLIENT_ID, FakeToss.SECRET, account)


@pytest.fixture
def fake() -> FakeToss:
    toss = FakeToss(lambda: NOW)
    toss.cash["KRW"] = D("10000000")
    return toss


def client(fake: Any, folder: Path, wall: Callable[[], float] | None = None) -> TossClient:
    return TossClient(
        creds(),
        folder,
        transport=fake,
        wall_clock=wall or Wall(),
        sleep=lambda s: None,
        limiter=RateLimiter(sleep=lambda s: None),
    )


def test_the_token_is_issued_once_cached_0600_and_shared(fake: FakeToss, tmp_path: Path) -> None:
    folder = tmp_path / "toss"
    wall = Wall()
    first = client(fake, folder, wall)
    assert first.buying_power(Currency.KRW) == D("10000000")
    assert fake.tokens == ["tok-1"]
    token_file = folder / "token.json"
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    cached = json.loads(token_file.read_text())
    assert cached["token"] == "tok-1"
    assert (cached["account_seq"], cached["account_tail"]) == (7, "8901")
    # Another run of the program reads the file: no new token (a new one would revoke the first).
    second = client(fake, folder, wall)
    assert second.buying_power(Currency.USD) == D("0")
    assert fake.tokens == ["tok-1"]
    # Inside its last 10 minutes the token is renewed.
    wall.t += 86400 - 500
    assert second.buying_power(Currency.KRW) == D("10000000")
    assert fake.tokens == ["tok-1", "tok-2"]


def test_the_token_request_is_the_documented_form(tmp_path: Path) -> None:
    seen: list[HttpRequest] = []

    def transport(request: HttpRequest) -> HttpResponse:
        seen.append(request)
        body = {"access_token": "t", "token_type": "Bearer", "expires_in": 86400}
        return HttpResponse(200, {}, json.dumps(body).encode())

    c = TossClient(creds(), tmp_path, transport=transport, sleep=lambda s: None)
    assert c.token() == "t"
    sent = seen[0]
    assert sent.method == "POST" and sent.url.endswith("/oauth2/token")  # noqa: PT018
    assert sent.headers["content-type"] == "application/x-www-form-urlencoded"
    assert sent.body == (
        b"grant_type=client_credentials&client_id=tsck_live_test&client_secret=s3cret"
    )


def test_a_revoked_token_is_counted_and_replaced(fake: FakeToss, tmp_path: Path) -> None:
    c = client(fake, tmp_path / "toss")
    c.holdings()
    fake.revoke_from_elsewhere()  # the old quant issued a token with the same client
    assert c.holdings() == []
    assert c.revoked == 1
    assert fake.tokens[-1] == "tok-3"  # ours again, after one retry


def test_a_token_renewed_by_another_run_of_ours_is_reused(fake: FakeToss, tmp_path: Path) -> None:
    folder = tmp_path / "toss"
    b = client(fake, folder)
    raced = []

    def racing(request: HttpRequest) -> HttpResponse:
        # While a's request (with tok-1) is on its way, another run of the program renews.
        if not raced and "buying-power" in request.url:
            raced.append(True)
            b.token(force=True)
        return fake(request)

    a = client(racing, folder)
    a.holdings()
    assert a.buying_power(Currency.KRW) == D("10000000")
    # a got token-revoked, read the file, and used b's token: no third token was issued.
    assert (fake.tokens, a.revoked, a.issued) == (["tok-1", "tok-2"], 1, 1)


def test_ip_and_credentials_refusals_name_their_cause(fake: FakeToss, tmp_path: Path) -> None:
    fake.ip_allowed = False
    with pytest.raises(TossApiError) as caught:
        client(fake, tmp_path / "a").holdings()
    assert (caught.value.status, caught.value.code) == (403, "access_denied")
    assert link_state(caught.value) == "ip"
    fake.ip_allowed = True
    bad = TossClient(
        TossCredentials("tsck_live_test", "wrong"),
        tmp_path / "b",
        transport=fake,
        sleep=lambda s: None,
    )
    with pytest.raises(TossApiError) as caught:
        bad.holdings()
    assert link_state(caught.value) == "auth"
    assert "wrong" not in str(caught.value)  # no secret in any message


def test_the_api_ip_refusal_after_a_token(fake: FakeToss, tmp_path: Path) -> None:
    c = client(fake, tmp_path / "toss")
    c.holdings()
    fake.ip_allowed = False
    with pytest.raises(TossApiError) as caught:
        c.holdings()
    assert (caught.value.code, link_state(caught.value)) == ("ip-not-allowed", "ip")


def test_the_account_is_the_one_whose_number_matches(fake: FakeToss, tmp_path: Path) -> None:
    fake.accounts = [
        {"accountNo": "11100000000", "accountSeq": 3, "accountType": "BROKERAGE"},
        {"accountNo": "12345678901", "accountSeq": 7, "accountType": "BROKERAGE"},
        {"accountNo": "99999999999", "accountSeq": 9, "accountType": "PENSION_SAVINGS"},
    ]
    assert client(fake, tmp_path / "a").account() == (7, "8901")
    other = TossClient(
        creds("000-0000"), tmp_path / "b", transport=fake, sleep=lambda s: None
    )
    with pytest.raises(TossApiError) as caught:
        other.account()
    assert (caught.value.code, link_state(caught.value)) == ("account-not-found", "account")
    unnamed = TossClient(creds(None), tmp_path / "c", transport=fake, sleep=lambda s: None)
    with pytest.raises(TossApiError) as caught:
        unnamed.account()
    assert caught.value.code == "account-ambiguous"
    fake.accounts = fake.accounts[1:2]
    assert unnamed.account() == (7, "8901")


def test_429_waits_and_tries_once_more_500_does_not(fake: FakeToss, tmp_path: Path) -> None:
    slept: list[float] = []
    c = TossClient(
        creds(),
        tmp_path,
        transport=fake,
        sleep=slept.append,
        limiter=RateLimiter(sleep=lambda s: None),
    )
    c.holdings()
    fake.fail_next = [(429, "rate-limit-exceeded")]
    assert c.holdings() == []
    assert slept == [0.0]  # Retry-After: 0
    fake.fail_next = [(429, "rate-limit-exceeded"), (429, "rate-limit-exceeded")]
    with pytest.raises(TossApiError) as caught:
        c.holdings()
    assert (caught.value.status, link_state(caught.value)) == (429, "unreachable")
    fake.fail_next = [(500, "internal-error")]
    with pytest.raises(TossApiError):
        c.holdings()
    assert fake.fail_next == []  # one call, no retry
    fake.fail_next = [(500, "maintenance")]
    with pytest.raises(TossApiError) as caught:
        c.holdings()
    assert link_state(caught.value) == "maintenance"


def test_no_answer_is_unreachable(fake: FakeToss, tmp_path: Path) -> None:
    fake.down = True
    with pytest.raises(TossUnreachableError):
        client(fake, tmp_path).holdings()
    assert link_state(TossUnreachableError("x")) == "unreachable"
    assert link_state(TossNotConfiguredError("x")) == "no-key"
    assert link_state(RuntimeError("x")) == "error"


def test_answers_are_exact_decimals(fake: FakeToss, tmp_path: Path) -> None:
    fake.hold("069500", D("10"), D("32000"), name="KODEX 200")
    fake.hold("SPYM", D("2.5"), D("66.123"), market="US")
    c = client(fake, tmp_path)
    holdings = {h.symbol: h for h in c.holdings()}
    assert (holdings["069500"].qty, holdings["069500"].last_price) == (D("10"), D("105650"))
    assert holdings["SPYM"].currency is Currency.USD
    assert holdings["SPYM"].qty == D("2.5")
    assert holdings["SPYM"].instrument_id == "US:SPYM"
    assert c.sellable_quantity("069500") == D("10")
    assert c.commissions() == {"KR": D("0.00015"), "US": D("0.001")}
    assert c.prices(["069500", "SPYM", "NOPE"])["SPYM"].price == D("91.64")
    infos = c.stocks(["069500", "SPYM"])
    assert infos["069500"].tradable
    assert infos["SPYM"].currency is Currency.USD
    assert c.exchange_rate().rate == D("1341.6")
    assert c.market_calendar("KR", date(2026, 7, 1))["today"] == {"date": "2026-07-01"}


def test_orders_need_a_granted_permit(fake: FakeToss, tmp_path: Path) -> None:
    c = client(fake, tmp_path)
    request = OrderRequest("at-x", "069500", "BUY", 1, D("32000"), Currency.KRW)
    with pytest.raises(LiveOrdersBlockedError):
        c.create_order(LivePermit("live", NOW), request)  # a bare permit is refused
    with pytest.raises(LiveOrdersBlockedError):
        c.cancel_order(LivePermit("live", NOW), "ord-0001")
    assert fake.orders == {}
    granted = LivePermit("live", NOW, _granted=True)
    order_id, client_id = c.create_order(granted, request)
    assert (order_id, client_id) == ("ord-0001", "at-x")
    # The same client order id and body: the first order comes back, no second one.
    assert c.create_order(granted, request) == ("ord-0001", "at-x")
    assert len(fake.orders) == 1
    view = c.order(order_id)
    assert (view.status, view.filled_qty, view.filled_amount) == ("FILLED", D(1), D("32000"))
    assert c.orders("CLOSED", start=date(2026, 7, 1))[0].order_id == "ord-0001"
    with pytest.raises(TossApiError) as caught:
        c.cancel_order(granted, order_id)
    assert caught.value.code == "already-filled"


def test_closed_orders_are_read_page_by_page(tmp_path: Path) -> None:
    pages = {
        None: {"orders": [{"orderId": "a", "status": "FILLED"}], "nextCursor": "c2", "hasNext": True},
        "c2": {"orders": [{"orderId": "b", "status": "CANCELED"}], "nextCursor": None, "hasNext": False},
    }

    def transport(request: HttpRequest) -> HttpResponse:
        if request.url.endswith("/oauth2/token"):
            body: Any = {"access_token": "t", "expires_in": 86400}
        elif "/accounts" in request.url:
            body = {"result": [{"accountNo": "1", "accountSeq": 1, "accountType": "BROKERAGE"}]}
        else:
            cursor = "c2" if "cursor=c2" in request.url else None
            body = {"result": pages[cursor]}
        return HttpResponse(200, {}, json.dumps(body).encode())

    c = TossClient(creds(None), tmp_path, transport=transport, sleep=lambda s: None)
    assert [o.order_id for o in c.orders("CLOSED")] == ["a", "b"]

    def endless(request: HttpRequest) -> HttpResponse:
        if request.url.endswith("/oauth2/token"):
            return HttpResponse(200, {}, b'{"access_token": "t", "expires_in": 86400}')
        if "/accounts" in request.url:
            return HttpResponse(
                200, {}, b'{"result": [{"accountNo": "1", "accountSeq": 1, "accountType": "BROKERAGE"}]}'
            )
        page = {"orders": [], "nextCursor": "again", "hasNext": True}
        return HttpResponse(200, {}, json.dumps({"result": page}).encode())

    loop = TossClient(creds(None), tmp_path / "x", transport=endless, sleep=lambda s: None)
    with pytest.raises(TossApiError, match="too-many-pages"):
        loop.orders("CLOSED", max_pages=3)


def test_both_error_shapes_are_read_and_never_raise_twice() -> None:
    nested = {"error": {"code": "order-hours-closed", "message": "m", "data": {"retryAfterAt": "x"}}}
    err = error_of(422, nested, {"x-request-id": "r1"})
    assert (err.code, err.data["retryAfterAt"], err.request_id) == ("order-hours-closed", "x", "r1")
    flat = error_of(403, {"error": "access_denied", "error_description": "IP"}, {})
    assert (flat.code, flat.message) == ("access_denied", "IP")
    assert error_of(502, "<html>", {}).code == "http-502"
    assert error_of(500, {"message": "x"}, {}).code == "http-500"
    assert str(error_of(400, {"error": {"code": "invalid-request"}}, {})) == "HTTP 400 invalid-request"


def test_a_non_json_answer_is_an_error_not_a_crash(tmp_path: Path) -> None:
    def transport(request: HttpRequest) -> HttpResponse:
        return HttpResponse(502, {}, b"<html>bad gateway</html>")

    c = TossClient(creds(), tmp_path, transport=transport, sleep=lambda s: None)
    with pytest.raises(TossApiError) as caught:
        c.token()
    assert caught.value.status == 502


def test_prices_on_the_wire() -> None:
    assert price_text(Currency.KRW, D("106175")) == "106175"
    assert price_text(Currency.USD, D("91.6")) == "91.60"
    assert price_text(Currency.USD, D("0.51234")) == "0.5123"
    body = OrderRequest("at-1", "SPYM", "BUY", 3, D("92.1"), Currency.USD).body()
    assert body == {
        "clientOrderId": "at-1",
        "symbol": "SPYM",
        "side": "BUY",
        "orderType": "LIMIT",
        "timeInForce": "DAY",
        "quantity": "3",
        "price": "92.10",
    }
    again = OrderRequest.from_json(OrderRequest("at-1", "SPYM", "BUY", 3, D("92.1"), Currency.USD).to_json())
    assert again.price == D("92.10") and again.currency is Currency.USD  # noqa: PT018


def test_an_order_from_the_api() -> None:
    raw = {
        "orderId": "o1",
        "symbol": "005930",
        "side": "BUY",
        "orderType": "LIMIT",
        "timeInForce": "DAY",
        "status": "PARTIAL_FILLED",
        "price": "70000",
        "quantity": "10",
        "currency": "KRW",
        "orderedAt": "2026-03-28T09:30:00.000+09:00",
        "execution": {
            "filledQuantity": "3",
            "averageFilledPrice": "70000",
            "filledAmount": "210000",
            "commission": "31",
            "tax": "0",
            "filledAt": "2026-03-28T09:31:15Z",
            "settlementDate": "2026-03-30",
        },
    }
    order = order_from_api(raw)
    assert (order.filled_qty, order.filled_amount, order.terminal) == (D(3), D("210000"), False)
    assert order.filled_at is not None and order.filled_at.utcoffset() == timedelta(0)  # noqa: PT018
    assert order.settlement_date == date(2026, 3, 30)
    assert order.instrument_id == "KR:005930"
    assert type(order).from_json(order.to_json()) == order
    blank = order_from_api({"orderId": "o2", "execution": None, "orderedAt": "garbage"})
    assert (blank.filled_qty, blank.ordered_at, blank.status) == (D(0), None, "")


def test_the_rate_limiter_spaces_one_group() -> None:
    now = [0.0]
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(round(s, 3))
        now[0] += s

    limiter = RateLimiter(clock=lambda: now[0], sleep=sleep, rates={"ACCOUNT": 1.0, "ORDER": 10.0})
    limiter.take("ACCOUNT")
    limiter.take("ACCOUNT")
    limiter.take("ORDER")
    limiter.take("ORDER")
    assert slept == [1.0, 0.1]
    limiter.take("UNKNOWN")  # an unknown group is slow but not stuck
    assert slept[-1] == 0.1 or len(slept) == 2


def test_credentials_come_from_the_secrets_file_only(tmp_path: Path) -> None:
    assert read_credentials(None) is None
    secrets = tmp_path / "secrets.env"
    secrets.write_text("TOSS_CLIENT_ID=abc\nexport TOSS_CLIENT_SECRET='xyz'\n")
    found = read_credentials(secrets)
    assert found is not None
    assert (found.client_id, found.client_secret, found.account_no) == ("abc", "xyz", None)
    assert "xyz" not in repr(found)  # never printed
    secrets.write_text("TOSS_CLIENT_ID=abc\n")
    assert read_credentials(secrets) is None
    assert read_credentials(tmp_path / "missing.env") is None


def test_the_urllib_transport_maps_answers_and_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    class Answer(io.BytesIO):
        status = 200
        headers = {"X-Request-Id": "r9"}

        def __enter__(self) -> Answer:
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

    def ok(req: Any, timeout: float) -> Answer:
        assert timeout == 20.0
        return Answer(b'{"result": 1}')

    monkeypatch.setattr("urllib.request.urlopen", ok)
    resp = urllib_transport(HttpRequest("GET", "https://example.test/x", {}))
    assert (resp.status, resp.headers["x-request-id"], resp.body) == (200, "r9", b'{"result": 1}')

    def http_error(req: Any, timeout: float) -> Any:
        raise urllib.error.HTTPError(
            "https://example.test/x", 422, "no", {"Retry-After": "1"}, io.BytesIO(b"{}")  # type: ignore[arg-type]
        )

    monkeypatch.setattr("urllib.request.urlopen", http_error)
    resp = urllib_transport(HttpRequest("GET", "https://example.test/x", {}))
    assert (resp.status, resp.headers["retry-after"], resp.body) == (422, "1", b"{}")

    def down(req: Any, timeout: float) -> Any:
        raise urllib.error.URLError("no route")

    monkeypatch.setattr("urllib.request.urlopen", down)
    with pytest.raises(TransportError):
        urllib_transport(HttpRequest("GET", "https://example.test/x", {}))
