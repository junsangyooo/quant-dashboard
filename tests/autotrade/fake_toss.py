"""A fake 토스증권 Open API: the transport the live tests pass instead of the network.

It answers like the documented API (openapi.json 1.2.24, PHASE3.md 1): OAuth2 in the flat shape,
everything else in the {"result": ...} / {"error": {...}} envelope, numbers as decimal strings.
It keeps an account (cash per currency, holdings), places, fills, partly fills, refuses and
cancels orders, keeps client order ids for 10 minutes (the same id and body return the first
order; a different body is idempotency-key-conflict), and lets a test act as the owner in the app
(trades, deposits, withdrawals, conversions) or break the link (IP, unreachable, 500, 429).
No socket is involved: the autotrade tests block the network.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from autotrade.broker.toss_api import HttpRequest, HttpResponse, TransportError
from autotrade.timeutil import KST

D = Decimal
ZERO = Decimal(0)


@dataclass
class Holding:
    symbol: str
    market: str
    currency: str
    qty: Decimal
    avg: Decimal
    name: str = ""


@dataclass
class FakeOrder:
    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: Decimal
    price: Decimal | None
    currency: str
    ordered_at: datetime
    status: str = "PENDING"
    filled: Decimal = ZERO
    amount: Decimal = ZERO
    commission: Decimal = ZERO
    tax: Decimal = ZERO
    filled_at: datetime | None = None
    settlement: date | None = None
    canceled_at: datetime | None = None
    client_order_id: str | None = None
    body: dict[str, Any] = field(default_factory=dict)

    def as_api(self) -> dict[str, Any]:
        filled = self.filled > 0
        return {
            "orderId": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "orderType": self.order_type,
            "timeInForce": "DAY",
            "status": self.status,
            "price": None if self.price is None else str(self.price),
            "quantity": str(self.quantity),
            "orderAmount": None,
            "currency": self.currency,
            "orderedAt": self.ordered_at.astimezone(KST).isoformat(),
            "canceledAt": None
            if self.canceled_at is None
            else self.canceled_at.astimezone(KST).isoformat(),
            "execution": {
                "filledQuantity": str(self.filled),
                "averageFilledPrice": str(self.amount / self.filled) if filled else None,
                "filledAmount": str(self.amount) if filled else None,
                "commission": str(self.commission) if filled else None,
                "tax": str(self.tax) if filled else None,
                "filledAt": None
                if self.filled_at is None
                else self.filled_at.astimezone(KST).isoformat(),
                "settlementDate": None if self.settlement is None else self.settlement.isoformat(),
            },
        }


TERMINAL = ("FILLED", "CANCELED", "REJECTED", "REPLACED")
PUBLIC_PATHS = ("/api/v1/prices", "/api/v1/stocks", "/api/v1/exchange-rate")  # no account header


class FakeToss:
    CLIENT_ID = "tsck_live_test"
    SECRET = "s3cret"

    def __init__(self, clock: Callable[[], datetime]) -> None:
        self.clock = clock
        self.cash: dict[str, Decimal] = {"KRW": D(0), "USD": D(0)}
        self.holdings: dict[str, Holding] = {}
        self.prices: dict[str, Decimal] = {"069500": D("105650"), "SPYM": D("91.64")}
        self.stock_status: dict[str, dict[str, Any]] = {}
        self.commission = {"KR": D("0.00015"), "US": D("0.001")}
        self.rate = D("1341.6")
        self.accounts = [{"accountNo": "12345678901", "accountSeq": 7, "accountType": "BROKERAGE"}]
        self.orders: dict[str, FakeOrder] = {}
        self.client_ids: dict[str, tuple[datetime, FakeOrder]] = {}
        self.tokens: list[str] = []
        self.calls: list[tuple[str, str]] = []
        self.next_id = 1
        # behaviour
        self.fill_mode = "fill"  # fill | open | partial | reject-later
        self.partial_qty: Decimal | None = None
        self.refuse: dict[
            str, tuple[int, str, dict[str, Any]]
        ] = {}  # symbol -> (status, code, data)
        self.refuse_once: list[tuple[int, str, dict[str, Any]]] = []
        self.ip_allowed = True
        self.down = False
        self.lose_response = False  # create the order, then fail the transport
        self.fail_next: list[tuple[int, str]] = []  # (status, code) for the next calls
        self.slip = D(0)  # fill price = limit - slip (buys) / limit + slip (sells)
        self.tax_rate = D(0)

    # ── the owner, in the app ────────────────────────────────────────────────────────────

    def deposit(self, currency: str, amount: Decimal) -> None:
        self.cash[currency] += amount

    def withdraw(self, currency: str, amount: Decimal) -> None:
        self.cash[currency] -= amount

    def convert(self, krw: Decimal, usd: Decimal) -> None:
        """The owner converts krw won into usd dollars in the app."""
        self.cash["KRW"] -= krw
        self.cash["USD"] += usd

    def hold(
        self, symbol: str, qty: Decimal, avg: Decimal, market: str = "KR", name: str = ""
    ) -> None:
        currency = "USD" if market == "US" else "KRW"
        self.holdings[symbol] = Holding(symbol, market, currency, qty, avg, name or symbol)

    def app_trade(
        self,
        symbol: str,
        side: str,
        qty: Decimal,
        price: Decimal,
        *,
        market: str = "KR",
        commission: Decimal = ZERO,
        tax: Decimal = ZERO,
        settlement: date | None = None,
        at: datetime | None = None,
    ) -> str:
        """A trade the owner made in the app: it fills at once and moves cash and holdings."""
        currency = "USD" if market == "US" else "KRW"
        order = self._new_order(symbol, side, "LIMIT", qty, price, currency, at or self.clock())
        self._fill(order, qty, price, commission=commission, tax=tax, settlement=settlement)
        return order.order_id

    # ── helpers ──────────────────────────────────────────────────────────────────────────

    def _new_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: Decimal,
        price: Decimal | None,
        currency: str,
        at: datetime,
    ) -> FakeOrder:
        order_id = f"ord-{self.next_id:04d}"
        self.next_id += 1
        order = FakeOrder(order_id, symbol, side, order_type, qty, price, currency, at)
        self.orders[order_id] = order
        return order

    def _fill(
        self,
        order: FakeOrder,
        qty: Decimal,
        price: Decimal,
        *,
        commission: Decimal | None = None,
        tax: Decimal = ZERO,
        settlement: date | None = None,
    ) -> None:
        gross = price * qty
        market = "US" if order.currency == "USD" else "KR"
        unit = D("0.01") if order.currency == "USD" else D(1)
        fee = (
            commission
            if commission is not None
            else (gross * self.commission[market]).quantize(unit)
        )
        if order.side == "BUY":
            self.cash[order.currency] -= gross + fee + tax
            h = self.holdings.get(order.symbol)
            if h is None:
                self.holdings[order.symbol] = Holding(
                    order.symbol, market, order.currency, qty, price, order.symbol
                )
            else:
                h.avg = (h.avg * h.qty + price * qty) / (h.qty + qty)
                h.qty += qty
        else:
            self.cash[order.currency] += gross - fee - tax
            h = self.holdings[order.symbol]
            h.qty -= qty
            if h.qty == 0:
                del self.holdings[order.symbol]
        order.filled += qty
        order.amount += gross
        order.commission += fee
        order.tax += tax
        order.filled_at = self.clock()
        order.settlement = settlement or (self.clock().astimezone(KST).date() + timedelta(days=2))
        order.status = "FILLED" if order.filled == order.quantity else "PARTIAL_FILLED"

    def fill_open(
        self, order_id: str, qty: Decimal | None = None, price: Decimal | None = None
    ) -> None:
        """The market reaches an open order (all of it, or qty)."""
        order = self.orders[order_id]
        left = order.quantity - order.filled
        self._fill(order, qty or left, price or order.price or D(0))

    def expire_open(self) -> None:
        """The session ends: open day orders are cancelled with what they filled."""
        for order in self.orders.values():
            if order.status in ("PENDING", "PARTIAL_FILLED"):
                order.status = "CANCELED"
                order.canceled_at = self.clock()

    def ours(self) -> list[FakeOrder]:
        return [o for o in self.orders.values() if o.client_order_id is not None]

    # ── the transport ────────────────────────────────────────────────────────────────────

    def __call__(self, request: HttpRequest) -> HttpResponse:
        url = urllib.parse.urlsplit(request.url)
        path = url.path
        query = dict(urllib.parse.parse_qsl(url.query))
        self.calls.append((request.method, path))
        if self.down:
            raise TransportError("ConnectionError: no route")
        if path == "/oauth2/token":
            return self._token(request)
        auth = request.headers.get("authorization", "")
        if not self.ip_allowed:
            return self._err(403, "ip-not-allowed", "허용되지 않은 IP 주소입니다.")
        if self.fail_next:
            status, code = self.fail_next.pop(0)
            headers = {"retry-after": "0"} if status == 429 else {}
            return self._err(status, code, "fake failure", headers=headers)
        token = auth.removeprefix("Bearer ")
        if not self.tokens or token not in self.tokens:
            return self._err(401, "invalid-token", "유효하지 않은 토큰입니다.")
        if token != self.tokens[-1]:
            return self._err(401, "token-revoked", "새로 발급된 토큰으로 대체되었습니다.")
        if path == "/api/v1/accounts":
            return self._ok(self.accounts)
        public = path in PUBLIC_PATHS or path.startswith("/api/v1/market-calendar")
        if not public and request.headers.get("x-tossinvest-account") != "7":
            return self._err(404, "account-not-found", "계좌를 찾을 수 없습니다.")
        body = json.loads(request.body.decode()) if request.body else {}
        return self._route(request.method, path, query, body)

    def _route(
        self, method: str, path: str, query: dict[str, str], body: dict[str, Any]
    ) -> HttpResponse:
        if path == "/api/v1/holdings":
            return self._ok({"items": [self._holding(h) for h in self.holdings.values()]})
        if path == "/api/v1/buying-power":
            return self._ok(
                {
                    "currency": query["currency"],
                    "cashBuyingPower": str(self.cash[query["currency"]]),
                }
            )
        if path == "/api/v1/sellable-quantity":
            h = self.holdings.get(query["symbol"])
            return self._ok({"sellableQuantity": str(h.qty if h else D(0))})
        if path == "/api/v1/commissions":
            return self._ok(
                [
                    {
                        "marketCountry": k,
                        "commissionRate": str(v),
                        "startDate": None,
                        "endDate": None,
                    }
                    for k, v in self.commission.items()
                ]
            )
        if path == "/api/v1/prices":
            out: list[dict[str, Any]] = []
            for sym in query["symbols"].split(","):
                if sym in self.prices:
                    out.append(
                        {
                            "symbol": sym,
                            "timestamp": self.clock().isoformat(),
                            "lastPrice": str(self.prices[sym]),
                            "currency": "USD" if sym.isalpha() else "KRW",
                        }
                    )
            return self._ok(out)
        if path == "/api/v1/stocks":
            out = []
            for sym in query["symbols"].split(","):
                info = {
                    "symbol": sym,
                    "name": sym,
                    "market": "NYSE" if sym.isalpha() else "KOSPI",
                    "securityType": "ETF",
                    "status": "ACTIVE",
                    "currency": "USD" if sym.isalpha() else "KRW",
                    "koreanMarketDetail": None
                    if sym.isalpha()
                    else {"liquidationTrading": False, "krxTradingSuspended": False},
                }
                info.update(self.stock_status.get(sym, {}))
                if info.get("status") != "GONE":
                    out.append(info)
            return self._ok(out)
        if path == "/api/v1/exchange-rate":
            return self._ok(
                {
                    "baseCurrency": "USD",
                    "quoteCurrency": "KRW",
                    "rate": str(self.rate),
                    "midRate": str(self.rate - 1),
                    "basisPoint": "7",
                    "rateChangeType": "UP",
                    "validFrom": self.clock().isoformat(),
                    "validUntil": self.clock().isoformat(),
                }
            )
        if path.startswith("/api/v1/market-calendar/"):
            return self._ok({"today": {"date": self.clock().date().isoformat()}})
        if path == "/api/v1/orders" and method == "POST":
            return self._create(body)
        if path == "/api/v1/orders" and method == "GET":
            return self._list(query)
        if path.startswith("/api/v1/orders/") and path.endswith("/cancel"):
            return self._cancel(path.split("/")[4])
        if path.startswith("/api/v1/orders/"):
            order = self.orders.get(urllib.parse.unquote(path.split("/")[4]))
            if order is None:
                return self._err(404, "order-not-found", "주문을 찾을 수 없습니다.")
            return self._ok(order.as_api())
        return self._err(404, "edge-blocked", "no such path")

    def _token(self, request: HttpRequest) -> HttpResponse:
        form = dict(urllib.parse.parse_qsl((request.body or b"").decode()))
        if not self.ip_allowed:
            return self._json(
                403, {"error": "access_denied", "error_description": "IP address not allowed"}
            )
        if form.get("client_id") != self.CLIENT_ID or form.get("client_secret") != self.SECRET:
            return self._json(
                401,
                {"error": "invalid_client", "error_description": "Client authentication failed."},
            )
        token = f"tok-{len(self.tokens) + 1}"
        self.tokens.append(token)
        return self._json(200, {"access_token": token, "token_type": "Bearer", "expires_in": 86400})

    def revoke_from_elsewhere(self) -> None:
        """Another program issues a token with the same client (the old quant)."""
        self.tokens.append(f"tok-other-{len(self.tokens) + 1}")

    def _holding(self, h: Holding) -> dict[str, Any]:
        last = self.prices.get(h.symbol, h.avg)
        return {
            "symbol": h.symbol,
            "name": h.name,
            "marketCountry": h.market,
            "currency": h.currency,
            "quantity": str(h.qty),
            "lastPrice": str(last),
            "averagePurchasePrice": str(h.avg),
        }

    def _create(self, body: dict[str, Any]) -> HttpResponse:
        now = self.clock()
        cid = body.get("clientOrderId")
        if cid:
            known = self.client_ids.get(cid)
            if known is not None and now - known[0] < timedelta(minutes=10):
                if known[1].body != body:
                    return self._err(422, "idempotency-key-conflict", "다른 내용")
                return self._ok({"orderId": known[1].order_id, "clientOrderId": cid})
        if self.refuse_once:
            status, code, data = self.refuse_once.pop(0)
            return self._err(status, code, "refused", data=data)
        symbol = str(body["symbol"])
        if symbol in self.refuse:
            status, code, data = self.refuse[symbol]
            return self._err(status, code, "refused", data=data)
        qty = D(str(body["quantity"]))
        price = D(str(body["price"])) if body.get("price") else None
        currency = "USD" if symbol.isalpha() else "KRW"
        side = str(body["side"])
        market = "US" if currency == "USD" else "KR"
        if side == "BUY" and price is not None:
            need = price * qty * (1 + self.commission[market])
            if need > self.cash[currency]:
                return self._err(422, "insufficient-buying-power", "주문 가능 금액이 부족합니다.")
        if side == "SELL":
            h = self.holdings.get(symbol)
            if h is None or h.qty < qty:
                return self._err(
                    422, "insufficient-sellable-quantity", "매도 가능 수량이 부족합니다."
                )
        order = self._new_order(symbol, side, str(body["orderType"]), qty, price, currency, now)
        order.client_order_id = cid
        order.body = body
        if cid:
            self.client_ids[cid] = (now, order)
        fill_price = (price or D(0)) - self.slip if side == "BUY" else (price or D(0)) + self.slip
        unit = D("0.01") if currency == "USD" else D(1)
        tax = (fill_price * qty * self.tax_rate).quantize(unit) if side == "SELL" else D(0)
        if self.fill_mode == "fill":
            self._fill(order, qty, fill_price, tax=tax)
        elif self.fill_mode == "partial":
            self._fill(order, self.partial_qty or D(1), fill_price, tax=tax)
        elif self.fill_mode == "reject-later":
            order.status = "REJECTED"
        if self.lose_response:
            self.lose_response = False
            raise TransportError("TimeoutError: the answer never came")
        return self._ok({"orderId": order.order_id, "clientOrderId": cid})

    def _list(self, query: dict[str, str]) -> HttpResponse:
        status = query["status"]
        start = date.fromisoformat(query["from"]) if query.get("from") else None
        end = date.fromisoformat(query["to"]) if query.get("to") else None
        out = []
        for o in self.orders.values():
            is_open = o.status in ("PENDING", "PARTIAL_FILLED", "PENDING_CANCEL")
            if (status == "OPEN") != is_open:
                continue
            if query.get("symbol") and o.symbol != query["symbol"]:
                continue
            day = o.ordered_at.astimezone(KST).date()
            if (start and day < start) or (end and day > end):
                continue
            out.append(o.as_api())
        return self._ok({"orders": out, "nextCursor": None, "hasNext": False})

    def _cancel(self, order_id: str) -> HttpResponse:
        order = self.orders.get(order_id)
        if order is None:
            return self._err(404, "order-not-found", "주문을 찾을 수 없습니다.")
        if order.status == "FILLED":
            return self._err(409, "already-filled", "이미 체결된 주문입니다.")
        if order.status == "CANCELED":
            return self._err(409, "already-canceled", "이미 취소된 주문입니다.")
        if "cancel" in self.refuse:
            status, code, data = self.refuse["cancel"]
            return self._err(status, code, "refused", data=data)
        order.status = "CANCELED"
        order.canceled_at = self.clock()
        return self._ok({"orderId": f"{order_id}-c"})

    # ── answers ──────────────────────────────────────────────────────────────────────────

    def _json(
        self, status: int, payload: Any, headers: dict[str, str] | None = None
    ) -> HttpResponse:
        return HttpResponse(
            status, {"x-request-id": "req-1", **(headers or {})}, json.dumps(payload).encode()
        )

    def _ok(self, result: Any) -> HttpResponse:
        return self._json(200, {"result": result})

    def _err(
        self,
        status: int,
        code: str,
        message: str,
        *,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> HttpResponse:
        err: dict[str, Any] = {"requestId": "req-1", "code": code, "message": message}
        if data:
            err["data"] = data
        return self._json(status, {"error": err}, headers)
