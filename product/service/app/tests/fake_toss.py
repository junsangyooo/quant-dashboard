"""가짜 토스 서버(시험 전용 · TASKS T-10 · 이후 T-11 · T-60이 같이 써요).

- 응답 꼴은 `vendor/toss-openapi-1.2.28.json`을 따르고 값은 지어내요. `strict=True`(기본)면 받은 요청과
  내보내는 응답을 명세로 검사해서 어긋나면 `spec_errors`에 적어요(시험이 0인지 봐요).
- 실제 네트워크에 나가지 않아요. 전송 함수(HttpRequest → HttpResponse)로 `TossClient`에 넣어요.
- 상태: 종목 · 일봉 · 지수 일봉 · 장 달력 · 계좌 · 보유 · 현금 · 주문 · 조건주문. 시험이 고쳐서 상황을 만들어요.
"""

from __future__ import annotations

import json
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.adapters.transport import HttpRequest, HttpResponse, TransportError
from tests import openapi_check as oc

KST = timezone(timedelta(hours=9))
CLIENT_ID = "cid-FAKE-0000"
CLIENT_SECRET = "sec-FAKE-value"
ACCOUNT_NO = "12345671234"  # 지어낸 값(DEVELOPING 3절)


def kst_ts(d: str, hh: int = 15, mm: int = 30) -> str:
    return datetime.fromisoformat(d).replace(hour=hh, minute=mm, tzinfo=KST).isoformat()


def regular_day(d: date, open_at: tuple[int, int] = (9, 0), close_at: tuple[int, int] = (15, 30)) -> dict[str, Any]:
    start = datetime(d.year, d.month, d.day, *open_at, tzinfo=KST)
    end = datetime(d.year, d.month, d.day, *close_at, tzinfo=KST)
    return {
        "date": d.isoformat(),
        "integrated": {
            "preMarket": {"startTime": start.replace(hour=8, minute=0).isoformat(),
                          "singlePriceAuctionStartTime": None, "endTime": start.isoformat()},
            "regularMarket": {"startTime": start.isoformat(),
                              "singlePriceAuctionStartTime": (end - timedelta(minutes=10)).isoformat(),
                              "endTime": end.isoformat()},
            "afterMarket": None,
        },
    }


def holiday(d: date) -> dict[str, Any]:
    return {"date": d.isoformat(), "integrated": None}


@dataclass
class FakeTossServer:
    strict: bool = True
    calls: list[tuple[str, str]] = field(default_factory=list)
    bodies: list[tuple[str, str, Any]] = field(default_factory=list)
    spec_errors: list[str] = field(default_factory=list)
    down: bool = False
    ip_allowed: bool = True
    tokens: list[str] = field(default_factory=list)
    rate_limited: int = 0  # 앞으로 n번은 429
    # 데이터
    stocks: dict[str, dict[str, Any]] = field(default_factory=dict)
    bars: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # 종목 → 오래된 순 일봉 {d,o,h,l,c,v}
    index_bars: dict[str, list[dict[str, Any]]] = field(default_factory=dict)  # KOSPI · KOSDAQ
    prices: dict[str, str] = field(default_factory=dict)
    warnings: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    sectors: list[dict[str, Any]] = field(default_factory=list)
    sector_members: dict[str, list[str]] = field(default_factory=dict)
    investor: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    calendar: Callable[[date], dict[str, Any]] | None = None
    today: date = date(2026, 11, 2)
    cash: str = "10000000"
    holdings: dict[str, dict[str, str]] = field(default_factory=dict)  # 종목 → {quantity, avg, sellable}
    orders: dict[str, dict[str, Any]] = field(default_factory=dict)
    conds: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 응답을 일부러 망가뜨리기: 경로 → 응답 JSON을 받아 바꾸는 함수
    mangle: dict[str, Callable[[Any], Any]] = field(default_factory=dict)

    # ── 공통 ─────────────────────────────────────────────────────────────

    def __call__(self, request: HttpRequest) -> HttpResponse:
        url = urllib.parse.urlsplit(request.url)
        path = url.path
        query = dict(urllib.parse.parse_qsl(url.query))
        self.calls.append((request.method, path))
        if self.down:
            raise TransportError("ConnectionError")
        if path == "/oauth2/token":
            return self._token(request)
        if self.rate_limited > 0:
            self.rate_limited -= 1
            return self._json(429, self._err("too-many-requests", "요청 한도 초과"),
                              {"retry-after": "1", "x-ratelimit-limit": "10", "x-ratelimit-remaining": "0"})
        if not self.ip_allowed:
            return self._json(403, self._err("ip-not-allowed", "허용되지 않은 IP"))
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if token not in self.tokens:
            return self._json(401, self._err("invalid-token", "x"))
        body = json.loads(request.body) if request.body else None
        if self.strict:
            self.spec_errors += [f"{request.method} {path} 요청: {e}" for e in
                                 oc.query_errors(request.method, path, query, dict(request.headers))]
            if body is not None:
                self.spec_errors += [f"{request.method} {path} 요청 본문: {e}" for e in
                                     oc.request_errors(request.method, path, body)]
        if body is not None:
            self.bodies.append((request.method, path, body))
        status, payload = self.route(request.method, path, query, body)
        for key, fn in self.mangle.items():
            if path == key:
                payload = fn(payload)
        if self.strict and not self.mangle:
            self.spec_errors += [f"{request.method} {path} 응답 {status}: {e}" for e in
                                 oc.response_errors(request.method, path, status, payload)]
        if status == 204:
            return HttpResponse(204, {"x-request-id": "req-1"}, b"")
        return self._json(status, payload)

    def _token(self, request: HttpRequest) -> HttpResponse:
        form = dict(urllib.parse.parse_qsl((request.body or b"").decode()))
        if not self.ip_allowed:
            return self._json(403, {"error": "access_denied", "error_description": "IP address not allowed"})
        if form.get("client_id") != CLIENT_ID or form.get("client_secret") != CLIENT_SECRET:
            return self._json(401, {"error": "invalid_client", "error_description": "Client authentication failed."})
        tok = f"tok-{len(self.tokens) + 1}"
        self.tokens.append(tok)
        return self._json(200, {"access_token": tok, "token_type": "Bearer", "expires_in": 86400})

    @staticmethod
    def _err(code: str, message: str) -> dict[str, Any]:
        return {"error": {"requestId": "req-1", "code": code, "message": message}}

    @staticmethod
    def _json(status: int, payload: Any, headers: dict[str, str] | None = None) -> HttpResponse:
        return HttpResponse(status, {"x-request-id": "req-1", **(headers or {})}, json.dumps(payload).encode())

    # ── 경로 ─────────────────────────────────────────────────────────────

    def route(self, method: str, path: str, q: dict[str, str], body: Any) -> tuple[int, Any]:  # noqa: C901
        parts = path.strip("/").split("/")[2:]  # api/v1/ 뒤
        if method == "GET" and parts == ["accounts"]:
            return 200, {"result": [{"accountNo": ACCOUNT_NO, "accountSeq": 7, "accountType": "BROKERAGE"}]}
        if method == "GET" and parts == ["prices"]:
            out = [{"symbol": s, "timestamp": kst_ts(self.today.isoformat(), 10, 0), "lastPrice": self.prices[s],
                    "currency": "KRW"} for s in q["symbols"].split(",") if s in self.prices]
            return 200, {"result": out}
        if method == "GET" and parts == ["candles"]:
            return self._candles(self.bars.get(q["symbol"]), q, with_currency=True)
        if method == "GET" and parts[:1] == ["market-indicators"] and parts[-1] == "candles":
            return self._candles(self.index_bars.get(parts[1]), q, with_currency=False)
        if method == "GET" and parts == ["market-indicators", "prices"]:
            out = [{"symbol": s, "timestamp": None, "lastPrice": str(self.index_bars[s][-1]["c"])}
                   for s in q["symbols"].split(",") if s in self.index_bars]
            return 200, {"result": out}
        if method == "GET" and parts == ["stocks", "all"]:
            rows = [s for s in self.stocks.values() if s["market"] == q["market"]]
            if q.get("securityType"):
                rows = [s for s in rows if s["securityType"] == q["securityType"]]
            return 200, {"result": [{k: s[k] for k in ("symbol", "name", "securityType", "isCommonShare", "isinCode")}
                                    for s in rows]}
        if method == "GET" and parts == ["stocks"]:
            return 200, {"result": [self.stocks[s] for s in q["symbols"].split(",") if s in self.stocks]}
        if method == "GET" and parts[:1] == ["stocks"] and parts[-1] == "warnings":
            if parts[1] not in self.stocks:
                return 404, self._err("stock-not-found", "종목을 찾을 수 없습니다.")
            return 200, {"result": self.warnings.get(parts[1], [])}
        if method == "GET" and parts[:1] == ["stocks"] and parts[-1] == "investor-trading":
            rows = self.investor.get(parts[1], [])
            until = q.get("until")
            rows = [r for r in rows if until is None or r["date"] <= until]
            rows = sorted(rows, key=lambda r: r["date"], reverse=True)
            n = int(q.get("count", 10))
            page, rest = rows[:n], rows[n:]
            return 200, {"result": {"records": page, "nextUntil": rest[0]["date"] if rest else None}}
        if method == "GET" and parts == ["sectors"]:
            return 200, {"result": {"sectors": self.sectors}}
        if method == "GET" and parts[:1] == ["sectors"] and parts[-1] == "stocks":
            rows = [{"symbol": s, "name": self.stocks.get(s, {}).get("name", s), "volume": None, "tradingAmount": None,
                     "marketCapitalization": None, "currency": "KRW"} for s in self.sector_members.get(parts[1], [])]
            return 200, {"result": {"stocks": rows}}
        if method == "GET" and parts == ["market-calendar", "KR"]:
            on = date.fromisoformat(q["date"]) if q.get("date") else self.today
            return 200, {"result": self._calendar(on)}
        if method == "GET" and parts == ["holdings"]:
            return 200, {"result": self._holdings()}
        if method == "GET" and parts == ["buying-power"]:
            return 200, {"result": {"currency": q["currency"], "cashBuyingPower": self.cash}}
        if method == "GET" and parts == ["sellable-quantity"]:
            h = self.holdings.get(q["symbol"])
            return 200, {"result": {"sellableQuantity": h["sellable"] if h else "0"}}
        if method == "GET" and parts == ["commissions"]:
            return 200, {"result": [{"marketCountry": "KR", "commissionRate": "0.00015", "startDate": None,
                                     "endDate": None}]}
        if parts[:1] == ["orders"]:
            return self._orders(method, parts, q, body)
        if parts[:1] == ["conditional-orders"]:
            return self._conds(method, parts, q, body)
        return 404, self._err("not-found", "no such path")

    def _candles(self, rows: list[dict[str, Any]] | None, q: dict[str, str], *, with_currency: bool) -> tuple[int, Any]:
        if rows is None:
            return 404, self._err("stock-not-found", "종목을 찾을 수 없습니다.")
        before = q.get("before")
        count = int(q.get("count", 100))
        pick = [r for r in rows if before is None or kst_ts(r["d"]) <= before]
        pick = sorted(pick, key=lambda r: r["d"], reverse=True)
        page, rest = pick[:count], pick[count:]
        out = []
        for r in page:
            c = {"timestamp": kst_ts(r["d"]), "openPrice": str(r["o"]), "highPrice": str(r["h"]),
                 "lowPrice": str(r["l"]), "closePrice": str(r["c"]), "volume": str(r["v"])}
            if with_currency:
                c["currency"] = "KRW"
            out.append(c)
        return 200, {"result": {"candles": out, "nextBefore": kst_ts(rest[0]["d"]) if rest else None}}

    def _calendar(self, on: date) -> dict[str, Any]:
        def day(d: date) -> dict[str, Any]:
            if self.calendar:
                return self.calendar(d)
            return regular_day(d) if d.weekday() < 5 else holiday(d)

        def step(d: date, k: int) -> date:
            d += timedelta(days=k)
            while day(d)["integrated"] is None:
                d += timedelta(days=k)
            return d

        return {"today": day(on), "previousBusinessDay": day(step(on, -1)), "nextBusinessDay": day(step(on, 1))}

    def _holdings(self) -> dict[str, Any]:
        def won(v: float) -> dict[str, Any]:
            return {"krw": str(v), "usd": None}

        items = []
        for sym, h in self.holdings.items():
            qty = float(h["quantity"])
            last = float(self.prices.get(sym, h["avg"]))
            amount = qty * last
            buy = qty * float(h["avg"])
            items.append({
                "symbol": sym, "name": self.stocks.get(sym, {}).get("name", sym), "marketCountry": "KR",
                "currency": "KRW", "quantity": h["quantity"], "lastPrice": str(last),
                "averagePurchasePrice": h["avg"],
                "marketValue": {"purchaseAmount": str(buy), "amount": str(amount), "amountAfterCost": str(amount)},
                "profitLoss": {"amount": str(amount - buy), "amountAfterCost": str(amount - buy),
                               "rate": "0", "rateAfterCost": "0"},
                "dailyProfitLoss": {"amount": "0", "rate": "0"},
                "cost": {"commission": "0", "tax": None},
            })
        total = sum(float(i["marketValue"]["amount"]) for i in items)
        buy = sum(float(i["marketValue"]["purchaseAmount"]) for i in items)
        return {
            "totalPurchaseAmount": won(buy),
            "marketValue": {"amount": won(total), "amountAfterCost": won(total)},
            "profitLoss": {"amount": won(total - buy), "amountAfterCost": won(total - buy), "rate": "0",
                           "rateAfterCost": "0"},
            "dailyProfitLoss": {"amount": won(0), "rate": "0"},
            "items": items,
        }

    # ── 주문 ─────────────────────────────────────────────────────────────

    def _order_view(self, o: dict[str, Any]) -> dict[str, Any]:
        return {k: v for k, v in o.items() if not k.startswith("_")}

    def _orders(self, method: str, parts: list[str], q: dict[str, str], body: Any) -> tuple[int, Any]:
        if method == "POST" and parts == ["orders"]:
            cid = body.get("clientOrderId")
            if cid and any(o["_client"] == cid for o in self.orders.values()):
                return 409, self._err("duplicate-order", "중복 요청")
            oid = f"ord-{len(self.orders) + 1}"
            self.orders[oid] = {
                "orderId": oid, "symbol": body["symbol"], "side": body["side"], "orderType": body["orderType"],
                "timeInForce": body.get("timeInForce", "DAY"), "status": "PENDING",
                "price": body.get("price"), "quantity": body["quantity"], "orderAmount": None, "currency": "KRW",
                "orderedAt": kst_ts(self.today.isoformat(), 8, 35), "canceledAt": None,
                "execution": {"filledQuantity": "0", "averageFilledPrice": None, "filledAmount": None,
                              "commission": None, "tax": None, "filledAt": None, "settlementDate": None},
                "_client": cid,
            }
            return 200, {"result": {"orderId": oid, "clientOrderId": cid}}
        if method == "GET" and parts == ["orders"]:
            want = q["status"]
            rows = [self._order_view(o) for o in self.orders.values()
                    if (o["status"] in ("PENDING", "PARTIAL_FILLED")) == (want == "OPEN")
                    and (not q.get("symbol") or o["symbol"] == q["symbol"])]
            return 200, {"result": {"orders": rows, "nextCursor": None, "hasNext": False}}
        oid = parts[1] if len(parts) > 1 else ""
        if oid not in self.orders:
            return 404, self._err("order-not-found", "주문을 찾을 수 없습니다.")
        o = self.orders[oid]
        if method == "GET" and len(parts) == 2:
            return 200, {"result": self._order_view(o)}
        if method == "POST" and parts[-1] == "cancel":
            if o["status"] not in ("PENDING", "PARTIAL_FILLED"):
                return 409, self._err("order-not-cancelable", "취소 불가 상태")
            o["status"] = "CANCELED"
            o["canceledAt"] = kst_ts(self.today.isoformat(), 9, 1)
            return 200, {"result": {"orderId": oid}}
        if method == "POST" and parts[-1] == "modify":
            o["orderType"] = body["orderType"]
            o["price"] = body.get("price", o["price"])
            o["quantity"] = body.get("quantity", o["quantity"])
            return 200, {"result": {"orderId": oid}}
        return 404, self._err("not-found", "no such path")

    def fill(self, order_id: str, qty: str, price: str) -> None:
        """시험이 체결을 만들어요."""
        o = self.orders[order_id]
        o["status"] = "FILLED" if qty == o["quantity"] else "PARTIAL_FILLED"
        amount = str(float(qty) * float(price))
        o["execution"] = {"filledQuantity": qty, "averageFilledPrice": price, "filledAmount": amount,
                          "commission": "0", "tax": "0", "filledAt": kst_ts(self.today.isoformat(), 9, 0),
                          "settlementDate": (self.today + timedelta(days=2)).isoformat()}

    def _conds(self, method: str, parts: list[str], q: dict[str, str], body: Any) -> tuple[int, Any]:
        def leg(raw: dict[str, Any], kind: str) -> dict[str, Any]:
            return {"type": kind, "status": "WATCHING", "orderSide": raw["orderSide"],
                    "triggerPrice": raw["triggerPrice"], "targetProfitRate": None,
                    "orderPrice": raw.get("orderPrice"), "triggeredOrderId": None}

        if method == "POST" and parts == ["conditional-orders"]:
            cid = f"cond-{len(self.conds) + 1}"
            self.conds[cid] = {
                "conditionalOrderId": cid, "type": body["type"], "status": "WATCHING", "symbol": body["symbol"],
                "market": "KR", "quantity": body["quantity"], "orderType": body["orderType"],
                "expireDate": body["expireDate"], "first": leg(body["first"], "STOP"),
                "createdAt": kst_ts(self.today.isoformat(), 9, 1),
            }
            if body.get("second"):  # 명세: second는 null이 아니라 빠져요
                self.conds[cid]["second"] = leg(body["second"], "STOP")
            return 200, {"result": {"conditionalOrderId": cid, "clientOrderId": body.get("clientOrderId")}}
        if method == "GET" and parts == ["conditional-orders"]:
            want = q["status"]
            rows = [c for c in self.conds.values() if (c["status"] == "WATCHING") == (want == "OPEN")]
            return 200, {"result": {"conditionalOrders": rows, "nextCursor": None, "hasNext": False}}
        cid = parts[1] if len(parts) > 1 else ""
        if cid not in self.conds:
            return 404, self._err("conditional-order-not-found", "조건주문 없음")
        c = self.conds[cid]
        if method == "GET":
            return 200, {"result": c}
        if method == "DELETE":
            c["status"] = "EXPIRED"
            for key in ("first", "second"):
                if c.get(key):
                    c[key]["status"] = "CANCELED"
            return 204, None
        if method == "POST" and parts[-1] == "modify":
            c.update({"type": body["type"], "quantity": body["quantity"], "orderType": body["orderType"],
                      "expireDate": body["expireDate"], "first": leg(body["first"], "STOP")})
            c.pop("second", None)
            if body.get("second"):
                c["second"] = leg(body["second"], "STOP")
            return 200, {"result": {"conditionalOrderId": cid}}
        return 404, self._err("not-found", "no such path")


def stock_row(symbol: str, name: str, market: str = "KOSPI", *, security_type: str = "STOCK", common: bool = True,
              list_date: str | None = "2000-01-04", shares: str = "100000000", leverage: str | None = None,
              liquidation: bool = False, suspended: bool = False) -> dict[str, Any]:
    return {
        "symbol": symbol, "name": name, "englishName": name, "isinCode": f"KR7{symbol}003",
        "market": market, "securityType": security_type, "isCommonShare": common, "status": "ACTIVE",
        "currency": "KRW", "listDate": list_date, "delistDate": None, "sharesOutstanding": shares,
        "leverageFactor": leverage,
        "koreanMarketDetail": {"liquidationTrading": liquidation, "nxtSupported": True,
                               "krxTradingSuspended": suspended, "nxtTradingSuspended": None},
    }


def investor_row(d: str, foreign: str, inst: str, indiv: str = "0", rate: str = "51.2") -> dict[str, Any]:
    def vol(net: str) -> dict[str, str]:
        n = float(net)
        return {"buyVolume": str(max(n, 0)), "sellVolume": str(max(-n, 0)), "netBuyVolume": net}

    return {"date": d, "updatedAt": kst_ts(d, 18, 0), "individual": vol(indiv), "foreigner": vol(foreign),
            "institution": {**vol(inst), "breakdown": None}, "otherCorporation": None,
            "foreignerHolding": {"holdingQuantity": "1000", "limitQuantity": "2000", "holdingRate": rate}, "cfd": None}
