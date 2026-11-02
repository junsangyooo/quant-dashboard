"""토스증권 Open API 1.2.28 클라이언트(TASKS T-10 · SPEC 11-1 순서 1 · DATA-CATALOG 2절).

- 꼴의 근거: `vendor/toss-openapi-1.2.28.json`(앱은 실행 중에 읽지 않아요 · 시험이 가짜 응답을 이 명세로 검사해요).
- 전송: `transport.py`의 문을 지나요. 기본은 가짜이고, 실제 전송은 두 열쇠가 다 있을 때만(T-00).
- 요청 한도: 명세의 'Rate Limits Group'마다 토큰 통(`RateLimiter`). 응답 헤더(`X-RateLimit-*`)로 통을 맞추고,
  429면 `Retry-After`만큼 쉬고 두 번까지 다시 보내요.
- 응답 꼴 검사(R-O14): 성공 응답의 `result` 꼴이 다르면 `TossShapeError`('응답 이상' · 전체 주문 멈춤 근거).
  목록 안 한 종목의 값 이상(가격 0 · 필요한 필드 없음 · 전일 대비 ±30% 넘음)은 `anomalies`로 따로 돌려줘요
  (그 종목 주문 0 근거).
- 토큰은 파일에 쓰지 않고 이 객체의 메모리에만 둬요. 토스가 보낸 오류 글은 담지 않아요(코드만).
- 주문 · 정정 · 취소 · 조건주문 함수가 있어요. 시험은 가짜 전송으로만 불러요(`tests/test_no_orders.py`).

출처: 이 레포의 autotrade/broker/toss_api.py(2026-10-29)에서 오류 읽기 · 토큰 · 계좌 찾기를 옮겨 고쳤어요.
가져오기(import)는 하지 않아요.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from .transport import FakeTransport, HttpRequest, HttpResponse, Transport, TransportError

__all__ = ["HttpRequest", "HttpResponse", "Transport", "TransportError"]

BASE = "https://openapi.tossinvest.com"
REFRESH_MARGIN_S = 600.0
KST = timezone(timedelta(hours=9))
CANDLE_PAGE = 200  # 명세: count 최대 200
RETRY_429 = 2
# 요청 한도(가정 · OPEN-QUESTIONS Q-T7): 명세는 그룹 이름과 헤더만 정하고 숫자는 응답 헤더로 알려 줘요.
# 처음에는 초당 DEFAULT_RATE로 보내고, 응답의 X-RateLimit-Limit을 받으면 그 값으로 바꿔요.
DEFAULT_RATE = 5.0
# 응답 이상(R-O14): 전일 대비 이 비율을 넘는 가격은 이상으로 봐요(가격 제한폭 ±30%)
MAX_DAILY_MOVE = Decimal("0.30")


# ── 오류 ────────────────────────────────────────────────────────────────────


class TossError(Exception):
    pass


class TossUnreachableError(TossError):
    pass


class TossShapeError(TossError):
    """응답 이상: 성공 응답의 꼴이 명세와 달라요(R-O14 · 머리 칩 '주문 멈춤 · 응답 이상')."""

    def __init__(self, path: str, what: str) -> None:
        super().__init__(f"{path}: {what}")
        self.path = path
        self.what = what
        self.code = "bad-shape"


@dataclass
class TossApiError(TossError):
    status: int
    code: str
    message: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:  # 토스가 보낸 글은 담지 않는다(코드만)
        return f"HTTP {self.status} {self.code}"


def error_of(status: int, payload: object) -> TossApiError:
    if isinstance(payload, Mapping):
        err = payload.get("error")
        if isinstance(err, Mapping):
            data = err.get("data")
            return TossApiError(
                status,
                str(err.get("code") or f"http-{status}"),
                str(err.get("message") or ""),
                data if isinstance(data, Mapping) else {},
            )
        if isinstance(err, str):
            return TossApiError(status, err, str(payload.get("error_description") or ""))
    return TossApiError(status, f"http-{status}")


def link_state(exc: BaseException) -> str:
    """auth · ip · unreachable · account · maintenance · shape · error"""
    if isinstance(exc, TossUnreachableError):
        return "unreachable"
    if isinstance(exc, TossShapeError):
        return "shape"
    if isinstance(exc, TossApiError):
        if exc.code in ("ip-not-allowed", "access_denied"):
            return "ip"
        if exc.code in ("invalid_client", "invalid_request", "unsupported_grant_type"):
            return "auth"
        if exc.status == 401 or exc.code in ("login-user-not-found", "forbidden"):
            return "auth"
        if exc.code in ("account-not-found", "account-ambiguous"):
            return "account"
        if exc.code == "maintenance":
            return "maintenance"
        if exc.status >= 500 or exc.status == 429:
            return "unreachable"
    return "error"


# ── 요청 한도 그룹 ──────────────────────────────────────────────────────────

# 명세 1.2.28의 'Rate Limits Group'(경로 → 그룹). 경로의 {…} 자리는 아무 값이나 맞아요.
RATE_GROUPS: list[tuple[str, str, str]] = [
    ("POST", "/oauth2/token", "AUTH"),
    ("GET", "/api/v1/orderbook", "MARKET_DATA"),
    ("GET", "/api/v1/prices", "MARKET_DATA"),
    ("GET", "/api/v1/trades", "MARKET_DATA"),
    ("GET", "/api/v1/price-limits", "MARKET_DATA"),
    ("GET", "/api/v1/candles", "MARKET_DATA_CHART"),
    ("GET", "/api/v1/stocks", "STOCK"),
    ("GET", "/api/v1/stocks/all", "STOCK_ALL"),
    ("GET", "/api/v1/stocks/{symbol}/warnings", "STOCK"),
    ("GET", "/api/v1/stocks/{symbol}/investor-trading", "STOCK_TRADING_TREND"),
    ("GET", "/api/v1/stocks/{symbol}/program-trades", "STOCK_TRADING_TREND"),
    ("GET", "/api/v1/stocks/{symbol}/short-selling", "STOCK_TRADING_TREND"),
    ("GET", "/api/v1/stocks/{symbol}/credit-trades", "STOCK_TRADING_TREND"),
    ("GET", "/api/v1/stocks/{symbol}/securities-lending", "STOCK_TRADING_TREND"),
    ("GET", "/api/v1/exchange-rate", "MARKET_INFO"),
    ("GET", "/api/v1/market-calendar/KR", "MARKET_INFO"),
    ("GET", "/api/v1/market-calendar/US", "MARKET_INFO"),
    ("GET", "/api/v1/rankings", "RANKING"),
    ("GET", "/api/v1/rankings/investor-trading", "RANKING"),
    ("GET", "/api/v1/market-indicators/prices", "MARKET_INDICATOR"),
    ("GET", "/api/v1/market-indicators/{symbol}/candles", "MARKET_INDICATOR_CHART"),
    ("GET", "/api/v1/market-indicators/{symbol}/investor-trading", "MARKET_INDICATOR"),
    ("GET", "/api/v1/sectors", "SECTOR"),
    ("GET", "/api/v1/sectors/rankings", "SECTOR_RANKING"),
    ("GET", "/api/v1/sectors/{sectorId}", "SECTOR"),
    ("GET", "/api/v1/sectors/{sectorId}/stocks", "SECTOR"),
    ("GET", "/api/v1/sectors/{sectorId}/etfs", "SECTOR"),
    ("GET", "/api/v1/accounts", "ACCOUNT"),
    ("GET", "/api/v1/holdings", "ASSET"),
    ("GET", "/api/v1/orders", "ORDER_HISTORY"),
    ("POST", "/api/v1/orders", "ORDER"),
    ("GET", "/api/v1/orders/{orderId}", "ORDER_HISTORY"),
    ("POST", "/api/v1/orders/{orderId}/modify", "ORDER"),
    ("POST", "/api/v1/orders/{orderId}/cancel", "ORDER"),
    ("POST", "/api/v1/conditional-orders", "CONDITIONAL_ORDER"),
    ("GET", "/api/v1/conditional-orders", "CONDITIONAL_ORDER_HISTORY"),
    ("GET", "/api/v1/conditional-orders/{conditionalOrderId}", "CONDITIONAL_ORDER_HISTORY"),
    ("DELETE", "/api/v1/conditional-orders/{conditionalOrderId}", "CONDITIONAL_ORDER"),
    ("POST", "/api/v1/conditional-orders/{conditionalOrderId}/modify", "CONDITIONAL_ORDER"),
    ("GET", "/api/v1/buying-power", "ORDER_INFO"),
    ("GET", "/api/v1/sellable-quantity", "ORDER_INFO"),
    ("GET", "/api/v1/commissions", "ORDER_INFO"),
]


def rate_group(method: str, path: str) -> str:
    parts = path.strip("/").split("/")
    for m, pattern, group in RATE_GROUPS:
        p = pattern.strip("/").split("/")
        if m == method and len(p) == len(parts) and all(a == b or a.startswith("{") for a, b in zip(p, parts)):
            return group
    return "OTHER"


class RateLimiter:
    """그룹마다 토큰 통. 시계 · 잠자기를 주입해 시험해요."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        default_rate: float = DEFAULT_RATE,
    ) -> None:
        self.clock = clock
        self.sleep = sleep
        self.default_rate = default_rate
        self.rate: dict[str, float] = {}
        self.tokens: dict[str, float] = {}
        self.stamp: dict[str, float] = {}
        self.waited: list[tuple[str, float]] = []

    def _refill(self, group: str) -> None:
        now = self.clock()
        rate = self.rate.get(group, self.default_rate)
        last = self.stamp.get(group, now)
        self.tokens[group] = min(rate, self.tokens.get(group, rate) + (now - last) * rate)
        self.stamp[group] = now

    def acquire(self, group: str) -> None:
        self._refill(group)
        if self.tokens[group] < 1:
            rate = self.rate.get(group, self.default_rate)
            wait = (1 - self.tokens[group]) / rate
            self.waited.append((group, wait))
            self.sleep(wait)
            self._refill(group)
        self.tokens[group] -= 1

    def observe(self, group: str, headers: Mapping[str, str]) -> None:
        h = {k.lower(): v for k, v in headers.items()}
        try:
            if "x-ratelimit-limit" in h:
                self.rate[group] = max(1.0, float(h["x-ratelimit-limit"]))
            if "x-ratelimit-remaining" in h:
                self._refill(group)
                self.tokens[group] = min(self.tokens[group], float(h["x-ratelimit-remaining"]))
        except ValueError:
            pass

    def backoff(self, group: str, headers: Mapping[str, str]) -> None:
        h = {k.lower(): v for k, v in headers.items()}
        try:
            wait = float(h.get("retry-after") or h.get("x-ratelimit-reset") or 1)
        except ValueError:
            wait = 1.0
        wait = min(max(wait, 0.0), 60.0)
        self.waited.append((group, wait))
        self.sleep(wait)
        self.tokens[group] = 0
        self.stamp[group] = self.clock()


# ── 값 꼴 ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TossCredentials:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    account_no: str | None = field(default=None, repr=False)


def dec(value: Any) -> Decimal | None:
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        out = Decimal(str(value))
    except InvalidOperation:
        return None
    return out if out.is_finite() else None


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: Decimal
    timestamp: str | None = None


@dataclass(frozen=True)
class Holding:
    symbol: str
    name: str
    qty: Decimal
    avg_price: Decimal
    last_price: Decimal


@dataclass(frozen=True)
class Candle:
    d: str  # KST 날짜(일봉) · 분봉이면 시각
    o: float
    h: float
    l: float  # noqa: E741
    c: float
    v: float

    def bar(self) -> dict[str, Any]:
        return {"d": self.d, "o": self.o, "h": self.h, "l": self.l, "c": self.c, "v": self.v}


@dataclass(frozen=True)
class CandlePage:
    candles: list[Candle]  # 명세 그대로 최신순
    next_before: str | None


@dataclass(frozen=True)
class ListedStock:
    symbol: str
    name: str
    security_type: str
    common: bool
    isin: str


@dataclass(frozen=True)
class StockInfo:
    symbol: str
    name: str
    market: str
    security_type: str
    common: bool
    status: str
    list_date: str | None
    delist_date: str | None
    shares: Decimal
    leverage: Decimal | None
    liquidation: bool | None
    suspended: bool | None


@dataclass(frozen=True)
class Warning:
    kind: str
    start: str | None
    end: str | None


@dataclass(frozen=True)
class Sector:
    sector_id: str
    name: str
    depth: int
    parent: str | None


@dataclass(frozen=True)
class InvestorDay:
    d: str
    foreign: Decimal
    institution: Decimal
    individual: Decimal | None
    foreign_rate: Decimal | None


@dataclass(frozen=True)
class Session:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class MarketDay:
    d: date
    regular: Session | None  # None = 휴장
    pre: Session | None = None

    @property
    def open(self) -> bool:
        return self.regular is not None


@dataclass(frozen=True)
class MarketCalendar:
    today: MarketDay
    previous: MarketDay
    next: MarketDay


@dataclass(frozen=True)
class Commission:
    country: str
    rate: Decimal
    start: str | None
    end: str | None


@dataclass(frozen=True)
class Execution:
    filled_qty: Decimal
    avg_price: Decimal | None
    filled_amount: Decimal | None
    commission: Decimal | None
    tax: Decimal | None
    filled_at: str | None


@dataclass(frozen=True)
class Order:
    order_id: str
    symbol: str
    side: str
    order_type: str
    tif: str
    status: str
    price: Decimal | None
    qty: Decimal
    ordered_at: str
    execution: Execution


@dataclass(frozen=True)
class CondLeg:
    kind: str
    status: str
    side: str
    trigger: Decimal | None
    price: Decimal | None
    triggered_order_id: str | None


@dataclass(frozen=True)
class ConditionalOrder:
    cond_id: str
    kind: str  # SINGLE · OCO · OTO
    status: str
    symbol: str
    qty: Decimal
    order_type: str
    expire: str | None
    first: CondLeg
    second: CondLeg | None
    created_at: str


@dataclass
class Checked:
    """목록 응답: 쓸 수 있는 값 + 종목별 이상(R-O14 · 그 종목 주문 0)."""

    items: dict[str, Any]
    anomalies: dict[str, str] = field(default_factory=dict)


# ── 꼴 검사 도우미 ──────────────────────────────────────────────────────────


class _Shape:
    def __init__(self, path: str) -> None:
        self.path = path

    def bad(self, what: str) -> TossShapeError:
        return TossShapeError(self.path, what)

    def obj(self, value: Any, what: str) -> Mapping[str, Any]:
        if not isinstance(value, Mapping):
            raise self.bad(f"{what}: object가 아니에요")
        return value

    def arr(self, value: Any, what: str) -> list[Any]:
        if not isinstance(value, list):
            raise self.bad(f"{what}: array가 아니에요")
        return value

    def s(self, row: Mapping[str, Any], key: str, *, null: bool = False) -> Any:
        if key not in row:
            raise self.bad(f"{key} 없음")
        value = row[key]
        if value is None and null:
            return None
        if not isinstance(value, str):
            raise self.bad(f"{key}: string이 아니에요")
        return value

    def d(self, row: Mapping[str, Any], key: str, *, null: bool = False) -> Decimal | None:
        raw = self.s(row, key, null=null)
        if raw is None:
            return None
        out = dec(raw)
        if out is None:
            raise self.bad(f"{key}: decimal이 아니에요")
        return out

    def b(self, row: Mapping[str, Any], key: str, *, null: bool = False) -> bool | None:
        if key not in row:
            raise self.bad(f"{key} 없음")
        value = row[key]
        if value is None and null:
            return None
        if not isinstance(value, bool):
            raise self.bad(f"{key}: boolean이 아니에요")
        return value

    def i(self, row: Mapping[str, Any], key: str) -> int:
        value = row.get(key)
        if key not in row or isinstance(value, bool) or not isinstance(value, int):
            raise self.bad(f"{key}: integer가 아니에요")
        return value

    def dt(self, row: Mapping[str, Any], key: str, *, null: bool = False) -> datetime | None:
        raw = self.s(row, key, null=null)
        if raw is None:
            return None
        try:
            out = datetime.fromisoformat(raw)
        except ValueError:
            raise self.bad(f"{key}: date-time이 아니에요") from None
        if out.tzinfo is None:
            raise self.bad(f"{key}: 시간대가 없어요")
        return out

    def day(self, row: Mapping[str, Any], key: str, *, null: bool = False) -> str | None:
        raw = self.s(row, key, null=null)
        if raw is None:
            return None
        try:
            date.fromisoformat(raw)
        except ValueError:
            raise self.bad(f"{key}: date가 아니에요") from None
        return raw


def price_anomaly(price: Decimal | None, prev_close: Decimal | float | None = None) -> str | None:
    """R-O14 값 이상: 가격 없음 · 0 이하 · 전일 대비 ±30% 넘음."""
    if price is None:
        return "가격 없음"
    if price <= 0:
        return "가격 0"
    if prev_close is not None:
        prev = Decimal(str(prev_close))
        if prev > 0 and abs(price / prev - 1) > MAX_DAILY_MOVE:
            return "전일 대비 30% 넘음"
    return None


# ── 클라이언트 ──────────────────────────────────────────────────────────────


class TossClient:
    def __init__(
        self,
        credentials: TossCredentials,
        *,
        transport: Transport | None = None,
        wall_clock: Callable[[], float] = time.time,
        base: str = BASE,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.credentials = credentials
        self.transport: Transport = transport if transport is not None else FakeTransport("toss")
        self.wall_clock = wall_clock
        self.base = base
        self.limiter = limiter or RateLimiter()
        self._token: str | None = None
        self._expires = 0.0
        self._account: tuple[int, str] | None = None

    def __repr__(self) -> str:
        return "TossClient(<keys hidden>)"

    # 보내기 ─────────────────────────────────────────────────────────────

    def _send(self, request: HttpRequest, group: str) -> HttpResponse:
        for attempt in range(RETRY_429 + 1):
            self.limiter.acquire(group)
            try:
                resp = self.transport(request)
            except TransportError as exc:
                raise TossUnreachableError(str(exc)) from None
            self.limiter.observe(group, resp.headers)
            if resp.status == 429 and attempt < RETRY_429:
                self.limiter.backoff(group, resp.headers)
                continue
            return resp
        raise AssertionError("unreachable")  # pragma: no cover

    def token(self, *, force: bool = False) -> str:
        if not force and self._token and self._expires - self.wall_clock() > REFRESH_MARGIN_S:
            return self._token
        body = urllib.parse.urlencode(
            {
                "grant_type": "client_credentials",
                "client_id": self.credentials.client_id,
                "client_secret": self.credentials.client_secret,
            }
        ).encode()
        resp = self._send(
            HttpRequest(
                "POST",
                f"{self.base}/oauth2/token",
                {"content-type": "application/x-www-form-urlencoded", "accept": "application/json"},
                body,
            ),
            "AUTH",
        )
        payload = _json(resp)
        access = payload.get("access_token") if isinstance(payload, Mapping) else None
        if resp.status != 200 or not isinstance(access, str) or not access:
            raise error_of(resp.status, payload)
        self._token = access
        expires = payload.get("expires_in")
        self._expires = self.wall_clock() + (float(expires) if isinstance(expires, int | float) else 86400.0)
        return access

    def account(self, *, force: bool = False) -> tuple[int, str]:
        """(accountSeq, 계좌번호 끝 4자리)."""
        if self._account and not force:
            return self._account
        sh = _Shape("/api/v1/accounts")
        rows = sh.arr(self.call("/api/v1/accounts"), "result")
        accounts = []
        for r in rows:
            r = sh.obj(r, "account")
            if sh.s(r, "accountType") == "BROKERAGE":
                accounts.append((sh.i(r, "accountSeq"), sh.s(r, "accountNo")))
        wanted = _digits(self.credentials.account_no)
        if wanted:
            accounts = [a for a in accounts if _digits(a[1]) == wanted]
            if not accounts:
                raise TossApiError(404, "account-not-found")
        elif len(accounts) != 1:
            raise TossApiError(
                404 if not accounts else 409,
                "account-not-found" if not accounts else "account-ambiguous",
            )
        seq, number = accounts[0]
        self._account = (seq, _digits(number)[-4:])
        return self._account

    def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        account: bool = False,
    ) -> Any:
        """요청 하나. 401이면 토큰을 새로 받아 한 번 더 보내요. 성공이면 `result`를 돌려줘요."""
        query = {k: _q(v) for k, v in (params or {}).items() if v is not None}
        url = f"{self.base}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        group = rate_group(method, path)
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        renewed = False
        while True:
            headers = {"authorization": f"Bearer {self.token()}", "accept": "application/json"}
            if account:
                headers["x-tossinvest-account"] = str(self.account()[0])
            if data is not None:
                headers["content-type"] = "application/json"
            resp = self._send(HttpRequest(method, url, headers, data), group)
            if resp.status == 204:
                return None
            payload = _json(resp)
            if 200 <= resp.status < 300:
                if not isinstance(payload, Mapping) or "result" not in payload or "error" in payload:
                    raise TossShapeError(path, "result 없음")
                return payload["result"]
            if resp.status == 401 and not renewed:
                renewed = True
                self.token(force=True)
                continue
            raise error_of(resp.status, payload)

    def call(self, path: str, *, params: Mapping[str, Any] | None = None, account: bool = False) -> Any:
        return self.request("GET", path, params=params, account=account)

    # 시세 ───────────────────────────────────────────────────────────────

    def prices(self, symbols: Sequence[str]) -> dict[str, Quote]:
        return self.prices_checked(symbols).items

    def prices_checked(self, symbols: Sequence[str], prev_close: Mapping[str, float] | None = None) -> Checked:
        sh = _Shape("/api/v1/prices")
        rows = sh.arr(self.call("/api/v1/prices", params={"symbols": ",".join(symbols)}), "result")
        out = Checked({})
        for row in rows:
            row = sh.obj(row, "price")
            sym = sh.s(row, "symbol")
            price = dec(row.get("lastPrice")) if isinstance(row.get("lastPrice"), str) else None
            bad = price_anomaly(price, (prev_close or {}).get(sym))
            if bad:
                out.anomalies[sym] = bad
                continue
            assert price is not None
            ts = row.get("timestamp")
            out.items[sym] = Quote(sym, price, ts if isinstance(ts, str) else None)
        for sym in symbols:
            if sym not in out.items and sym not in out.anomalies:
                out.anomalies[sym] = "가격 없음"
        return out

    def candles(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        count: int = CANDLE_PAGE,
        before: str | None = None,
        adjusted: bool = True,
        index: bool = False,
    ) -> CandlePage:
        """일봉 · 분봉 한 쪽(최신순). index=True면 지수(KOSPI · KOSDAQ) 캔들."""
        path = f"/api/v1/market-indicators/{symbol}/candles" if index else "/api/v1/candles"
        params: dict[str, Any] = {"interval": interval, "count": min(count, CANDLE_PAGE), "before": before}
        if not index:
            params |= {"symbol": symbol, "adjusted": adjusted}
        sh = _Shape(path)
        result = sh.obj(self.call(path, params=params), "result")
        rows = sh.arr(result.get("candles"), "candles")
        out = []
        for row in rows:
            row = sh.obj(row, "candle")
            ts = sh.dt(row, "timestamp")
            assert ts is not None
            vals = [sh.d(row, k) for k in ("openPrice", "highPrice", "lowPrice", "closePrice", "volume")]
            o, h, lo, c, v = (float(x) for x in vals if x is not None)
            local = ts.astimezone(KST)
            d = local.date().isoformat() if interval == "1d" else local.isoformat()
            out.append(Candle(d, o, h, lo, c, v))
        nb = result.get("nextBefore")
        if nb is not None and not isinstance(nb, str):
            raise sh.bad("nextBefore: string이 아니에요")
        return CandlePage(out, nb)

    def daily_bars(self, symbol: str, start: date, end: date, *, index: bool = False, adjusted: bool = True,
                   max_pages: int = 60) -> list[dict[str, Any]]:
        """start ~ end 일봉(오래된 순 · 수정주가). `before`로 거슬러 올라가며 받아요."""
        before: str | None = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=KST).isoformat()
        seen: dict[str, dict[str, Any]] = {}
        for _ in range(max_pages):
            page = self.candles(symbol, before=before, adjusted=adjusted, index=index)
            for c in page.candles:
                if start.isoformat() <= c.d <= end.isoformat():
                    seen[c.d] = c.bar()
            oldest = min((c.d for c in page.candles), default=None)
            if not page.candles or page.next_before is None or (oldest is not None and oldest < start.isoformat()):
                break
            before = page.next_before
        return [seen[d] for d in sorted(seen)]

    def index_prices(self, symbols: Sequence[str]) -> dict[str, Quote]:
        sh = _Shape("/api/v1/market-indicators/prices")
        rows = sh.arr(self.call("/api/v1/market-indicators/prices", params={"symbols": ",".join(symbols)}), "result")
        out = {}
        for row in rows:
            row = sh.obj(row, "price")
            sym = sh.s(row, "symbol")
            price = sh.d(row, "lastPrice")
            assert price is not None
            out[sym] = Quote(sym, price, row.get("timestamp") if isinstance(row.get("timestamp"), str) else None)
        return out

    # 종목 · 섹터 · 수급 ─────────────────────────────────────────────────

    def stocks_all(self, market: str, *, status: str = "ACTIVE", security_type: str | None = None,
                   common_share: bool | None = None) -> list[ListedStock]:
        sh = _Shape("/api/v1/stocks/all")
        params = {"market": market, "status": status, "securityType": security_type, "commonShare": common_share}
        rows = sh.arr(self.call("/api/v1/stocks/all", params=params), "result")
        out = []
        for row in rows:
            row = sh.obj(row, "stock")
            out.append(ListedStock(sh.s(row, "symbol"), sh.s(row, "name"), sh.s(row, "securityType"),
                                   bool(sh.b(row, "isCommonShare")), sh.s(row, "isinCode")))
        return out

    def stocks(self, symbols: Sequence[str]) -> dict[str, StockInfo]:
        sh = _Shape("/api/v1/stocks")
        rows = sh.arr(self.call("/api/v1/stocks", params={"symbols": ",".join(symbols)}), "result")
        out = {}
        for row in rows:
            row = sh.obj(row, "stock")
            detail = row.get("koreanMarketDetail")
            liq = susp = None
            if detail is not None:
                detail = sh.obj(detail, "koreanMarketDetail")
                liq = sh.b(detail, "liquidationTrading")
                susp = sh.b(detail, "krxTradingSuspended")
            shares = sh.d(row, "sharesOutstanding")
            assert shares is not None
            info = StockInfo(
                symbol=sh.s(row, "symbol"), name=sh.s(row, "name"), market=sh.s(row, "market"),
                security_type=sh.s(row, "securityType"), common=bool(sh.b(row, "isCommonShare")),
                status=sh.s(row, "status"), list_date=sh.day(row, "listDate", null=True) if "listDate" in row else None,
                delist_date=sh.day(row, "delistDate", null=True) if "delistDate" in row else None,
                shares=shares,
                leverage=sh.d(row, "leverageFactor", null=True) if "leverageFactor" in row else None,
                liquidation=liq, suspended=susp,
            )
            out[info.symbol] = info
        return out

    def warnings(self, symbol: str) -> list[Warning]:
        path = f"/api/v1/stocks/{symbol}/warnings"
        sh = _Shape(path)
        out = []
        for row in sh.arr(self.call(path), "result"):
            row = sh.obj(row, "warning")
            out.append(Warning(sh.s(row, "warningType"),
                               sh.day(row, "startDate", null=True) if "startDate" in row else None,
                               sh.day(row, "endDate", null=True) if "endDate" in row else None))
        return out

    def sectors(self) -> list[Sector]:
        sh = _Shape("/api/v1/sectors")
        result = sh.obj(self.call("/api/v1/sectors"), "result")
        out = []
        for row in sh.arr(result.get("sectors"), "sectors"):
            row = sh.obj(row, "sector")
            out.append(Sector(sh.s(row, "sectorId"), sh.s(row, "name"), sh.i(row, "depth"),
                              sh.s(row, "parentSectorId", null=True)))
        return out

    def sector_stocks(self, sector_id: str, market_country: str = "KR") -> list[str]:
        path = f"/api/v1/sectors/{urllib.parse.quote(sector_id, safe='')}/stocks"
        sh = _Shape(path)
        result = sh.obj(self.call(path, params={"marketCountry": market_country}), "result")
        return [sh.s(sh.obj(r, "stock"), "symbol") for r in sh.arr(result.get("stocks"), "stocks")]

    def investor_trading(self, symbol: str, *, count: int = 100, until: str | None = None
                         ) -> tuple[list[InvestorDay], str | None]:
        """(날짜별 순매수 · 다음 쪽 until). 늦게 확정되는 값이라 판단에는 어제 확정치만 써요(R-J3)."""
        path = f"/api/v1/stocks/{symbol}/investor-trading"
        sh = _Shape(path)
        result = sh.obj(self.call(path, params={"count": min(count, 100), "until": until}), "result")
        out = []
        for row in sh.arr(result.get("records"), "records"):
            row = sh.obj(row, "record")

            def net(key: str, *, required: bool, row: Mapping[str, Any] = row) -> Decimal | None:
                part = row.get(key)
                if part is None:
                    if required:
                        raise sh.bad(f"{key} 없음")
                    return None
                return sh.d(sh.obj(part, key), "netBuyVolume")

            holding = row.get("foreignerHolding")
            rate = sh.d(sh.obj(holding, "foreignerHolding"), "holdingRate") if holding is not None else None
            foreign = net("foreigner", required=True)
            inst = net("institution", required=True)
            assert foreign is not None and inst is not None
            out.append(InvestorDay(str(sh.day(row, "date")), foreign, inst, net("individual", required=False), rate))
        nu = result.get("nextUntil")
        return out, nu if isinstance(nu, str) else None

    def market_calendar(self, on: date | None = None) -> MarketCalendar:
        path = "/api/v1/market-calendar/KR"
        sh = _Shape(path)
        result = sh.obj(self.call(path, params={"date": on.isoformat() if on else None}), "result")

        def day(key: str) -> MarketDay:
            row = sh.obj(result.get(key), key)
            d = date.fromisoformat(str(sh.day(row, "date")))
            hours = row.get("integrated")
            if hours is None:
                return MarketDay(d, None)
            hours = sh.obj(hours, "integrated")

            def session(name: str) -> Session | None:
                raw = hours.get(name)
                if raw is None:
                    return None
                raw = sh.obj(raw, name)
                start, end = sh.dt(raw, "startTime"), sh.dt(raw, "endTime")
                assert start is not None and end is not None
                return Session(start, end)

            return MarketDay(d, session("regularMarket"), session("preMarket"))

        return MarketCalendar(day("today"), day("previousBusinessDay"), day("nextBusinessDay"))

    # 계좌 ───────────────────────────────────────────────────────────────

    def holdings(self) -> list[Holding]:
        sh = _Shape("/api/v1/holdings")
        result = sh.obj(self.call("/api/v1/holdings", account=True), "result")
        out: list[Holding] = []
        for item in sh.arr(result.get("items"), "items"):
            item = sh.obj(item, "item")
            qty, avg, last = (sh.d(item, k) for k in ("quantity", "averagePurchasePrice", "lastPrice"))
            assert qty is not None and avg is not None and last is not None
            out.append(Holding(sh.s(item, "symbol"), sh.s(item, "name"), qty, avg, last))
        return out

    def buying_power(self, currency: str = "KRW") -> Decimal:
        sh = _Shape("/api/v1/buying-power")
        result = sh.obj(self.call("/api/v1/buying-power", account=True, params={"currency": currency}), "result")
        value = sh.d(result, "cashBuyingPower")
        assert value is not None
        return value

    def sellable_quantity(self, symbol: str) -> Decimal:
        sh = _Shape("/api/v1/sellable-quantity")
        result = sh.obj(self.call("/api/v1/sellable-quantity", account=True, params={"symbol": symbol}), "result")
        value = sh.d(result, "sellableQuantity")
        assert value is not None
        return value

    def commissions(self) -> list[Commission]:
        sh = _Shape("/api/v1/commissions")
        out = []
        for row in sh.arr(self.call("/api/v1/commissions", account=True), "result"):
            row = sh.obj(row, "commission")
            rate = sh.d(row, "commissionRate")
            assert rate is not None
            out.append(Commission(sh.s(row, "marketCountry"), rate,
                                  sh.day(row, "startDate", null=True) if "startDate" in row else None,
                                  sh.day(row, "endDate", null=True) if "endDate" in row else None))
        return out

    # 주문 (가짜 전송으로만 시험) ────────────────────────────────────────

    def create_order(self, *, symbol: str, side: str, quantity: int | Decimal, order_type: str = "LIMIT",
                     price: Decimal | int | None = None, tif: str = "DAY", client_order_id: str | None = None,
                     confirm_high_value: bool = False) -> str:
        body: dict[str, Any] = {"symbol": symbol, "side": side, "orderType": order_type, "timeInForce": tif,
                                "quantity": str(quantity)}
        if price is not None:
            body["price"] = str(price)
        if client_order_id:
            body["clientOrderId"] = client_order_id
        if confirm_high_value:
            body["confirmHighValueOrder"] = True
        sh = _Shape("/api/v1/orders")
        result = sh.obj(self.request("POST", "/api/v1/orders", body=body, account=True), "result")
        return str(sh.s(result, "orderId"))

    def order(self, order_id: str) -> Order:
        path = f"/api/v1/orders/{urllib.parse.quote(order_id, safe='')}"
        return _order(_Shape(path), self.call(path, account=True))

    def orders(self, status: str = "OPEN", *, symbol: str | None = None, from_: str | None = None,
               to: str | None = None, cursor: str | None = None, limit: int = 100) -> tuple[list[Order], str | None]:
        sh = _Shape("/api/v1/orders")
        params = {"status": status, "symbol": symbol, "from": from_, "to": to, "cursor": cursor, "limit": limit}
        result = sh.obj(self.call("/api/v1/orders", params=params, account=True), "result")
        rows = [_order(sh, r) for r in sh.arr(result.get("orders"), "orders")]
        if not isinstance(result.get("hasNext"), bool):
            raise sh.bad("hasNext 없음")
        nxt = result.get("nextCursor")
        return rows, nxt if result["hasNext"] and isinstance(nxt, str) else None

    def cancel_order(self, order_id: str) -> str:
        path = f"/api/v1/orders/{urllib.parse.quote(order_id, safe='')}/cancel"
        sh = _Shape(path)
        return str(sh.s(sh.obj(self.request("POST", path, body={}, account=True), "result"), "orderId"))

    def modify_order(self, order_id: str, *, order_type: str, quantity: int | Decimal | None = None,
                     price: Decimal | int | None = None) -> str:
        path = f"/api/v1/orders/{urllib.parse.quote(order_id, safe='')}/modify"
        body: dict[str, Any] = {"orderType": order_type}
        if quantity is not None:
            body["quantity"] = str(quantity)
        if price is not None:
            body["price"] = str(price)
        sh = _Shape(path)
        return str(sh.s(sh.obj(self.request("POST", path, body=body, account=True), "result"), "orderId"))

    # 조건주문 (가짜 전송으로만 시험) ────────────────────────────────────

    def create_conditional_order(self, *, symbol: str, kind: str, quantity: int | Decimal, expire: date,
                                 first: Mapping[str, Any], second: Mapping[str, Any] | None = None,
                                 order_type: str = "LIMIT", client_order_id: str | None = None) -> str:
        body: dict[str, Any] = {"symbol": symbol, "type": kind, "quantity": str(quantity), "orderType": order_type,
                                "expireDate": expire.isoformat(), "first": _leg(first)}
        if second is not None:
            body["second"] = _leg(second)
        if client_order_id:
            body["clientOrderId"] = client_order_id
        sh = _Shape("/api/v1/conditional-orders")
        result = sh.obj(self.request("POST", "/api/v1/conditional-orders", body=body, account=True), "result")
        return str(sh.s(result, "conditionalOrderId"))

    def conditional_orders(self, status: str = "OPEN", *, symbol: str | None = None, cursor: str | None = None,
                           limit: int = 100) -> tuple[list[ConditionalOrder], str | None]:
        sh = _Shape("/api/v1/conditional-orders")
        params = {"status": status, "symbol": symbol, "cursor": cursor, "limit": limit}
        result = sh.obj(self.call("/api/v1/conditional-orders", params=params, account=True), "result")
        rows = [_cond(sh, r) for r in sh.arr(result.get("conditionalOrders"), "conditionalOrders")]
        nxt = result.get("nextCursor")
        return rows, nxt if result.get("hasNext") is True and isinstance(nxt, str) else None

    def conditional_order(self, cond_id: str) -> ConditionalOrder:
        path = f"/api/v1/conditional-orders/{urllib.parse.quote(cond_id, safe='')}"
        return _cond(_Shape(path), self.call(path, account=True))

    def cancel_conditional_order(self, cond_id: str) -> None:
        path = f"/api/v1/conditional-orders/{urllib.parse.quote(cond_id, safe='')}"
        self.request("DELETE", path, account=True)

    def modify_conditional_order(self, cond_id: str, *, kind: str, quantity: int | Decimal, expire: date,
                                 first: Mapping[str, Any], second: Mapping[str, Any] | None = None,
                                 order_type: str = "LIMIT") -> str:
        path = f"/api/v1/conditional-orders/{urllib.parse.quote(cond_id, safe='')}/modify"
        body: dict[str, Any] = {"type": kind, "quantity": str(quantity), "orderType": order_type,
                                "expireDate": expire.isoformat(), "first": _leg(first)}
        if second is not None:
            body["second"] = _leg(second)
        sh = _Shape(path)
        return str(sh.s(sh.obj(self.request("POST", path, body=body, account=True), "result"), "conditionalOrderId"))


def _leg(leg: Mapping[str, Any]) -> dict[str, Any]:
    out = {"orderSide": str(leg["side"]), "triggerPrice": str(leg["trigger"])}
    if leg.get("price") is not None:
        out["orderPrice"] = str(leg["price"])
    return out


def _order(sh: _Shape, raw: Any) -> Order:
    row = sh.obj(raw, "order")
    ex = sh.obj(row.get("execution"), "execution")
    filled = sh.d(ex, "filledQuantity")
    qty = sh.d(row, "quantity")
    assert filled is not None and qty is not None
    return Order(
        order_id=sh.s(row, "orderId"), symbol=sh.s(row, "symbol"), side=sh.s(row, "side"),
        order_type=sh.s(row, "orderType"), tif=sh.s(row, "timeInForce"), status=sh.s(row, "status"),
        price=sh.d(row, "price", null=True) if "price" in row else None, qty=qty,
        ordered_at=sh.s(row, "orderedAt"),
        execution=Execution(
            filled, sh.d(ex, "averageFilledPrice", null=True), sh.d(ex, "filledAmount", null=True),
            sh.d(ex, "commission", null=True), sh.d(ex, "tax", null=True), sh.s(ex, "filledAt", null=True),
        ),
    )


def _cond(sh: _Shape, raw: Any) -> ConditionalOrder:
    row = sh.obj(raw, "conditionalOrder")

    def leg(key: str) -> CondLeg | None:
        part = row.get(key)
        if part is None:
            if key == "first":
                raise sh.bad("first 없음")
            return None
        part = sh.obj(part, key)
        return CondLeg(
            sh.s(part, "type"), sh.s(part, "status"), sh.s(part, "orderSide"),
            sh.d(part, "triggerPrice", null=True) if "triggerPrice" in part else None,
            sh.d(part, "orderPrice", null=True) if "orderPrice" in part else None,
            sh.s(part, "triggeredOrderId", null=True) if "triggeredOrderId" in part else None,
        )

    first = leg("first")
    qty = sh.d(row, "quantity")
    assert first is not None and qty is not None
    return ConditionalOrder(
        cond_id=sh.s(row, "conditionalOrderId"), kind=sh.s(row, "type"), status=sh.s(row, "status"),
        symbol=sh.s(row, "symbol"), qty=qty, order_type=sh.s(row, "orderType"),
        expire=sh.day(row, "expireDate") if "expireDate" in row else None, first=first, second=leg("second"),
        created_at=sh.s(row, "createdAt"),
    )


def _q(value: Any) -> Any:
    if isinstance(value, bool):
        return "true" if value else "false"
    return value


def _digits(text: str | None) -> str:
    return "".join(ch for ch in (text or "") if ch.isdigit())


def _json(resp: HttpResponse) -> Any:
    if not resp.body:
        return {}
    try:
        return json.loads(resp.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {"error": {"code": f"http-{resp.status}", "message": "not JSON"}}
