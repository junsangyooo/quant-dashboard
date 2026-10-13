"""토스증권 Open API client for the live ledger (autotrade/PHASE3.md 2.2).

Moved from src/quant/broker/toss.py and src/quant/broker/__init__.py (D14: copied, never
imported; tests/autotrade/test_toss_api.py checks it again against a fake Toss). What changed:

- The HTTP transport is injected (`Transport`; the standard library's urllib by default, no new
  dependency). Tests pass a fake; nothing here reaches the network on its own.
- The credentials are passed in (`TossCredentials`, read from the secrets file by the tick only)
  and the token lives in its own 0600 file under data/autotrade-toss/ (atomic writes).
- The token request sends the client id and secret in the form body (the docs' form, 1.2.24).
- One token per client is valid (a new one revokes the old: 401 token-revoked). The token is
  renewed only inside its last 10 minutes or after a 401. On token-revoked the file is read again
  first (another run of this program may have renewed it); only then a new token is issued. Every
  token-revoked is counted (`revoked`): another program using the same client shows up on the
  health screen instead of the two silently revoking each other.
- The account is the BROKERAGE account whose number matches TOSS_ACCOUNT_NO (the old code took
  the first one); with no number given, the only one.
- One token bucket per API group (the documented limits; ORDER_INFO at its 09:00-09:10 peak rate
  all day), a 429 waits Retry-After (5 s at most) and is tried once more.
- Every amount is an exact Decimal from the strings Toss sends.
- No error message carries a secret, a token or a header.

Orders and cancellations need a `LivePermit`, which only autotrade/broker/toss.py hands out after
checking both keys (AUTOTRADE_LIVE_ORDERS=1 and the stored mode 'live').
"""

from __future__ import annotations

import contextlib
import http.client
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from autotrade.config import read_env_key
from autotrade.domain.instruments import Currency
from autotrade.timeutil import from_iso

BASE = "https://openapi.tossinvest.com"
REQUEST_TIMEOUT_S = 20.0
REFRESH_MARGIN_S = 600.0  # a 24 h token is renewed inside its last 10 minutes
RETRY_AFTER_CAP_S = 5.0

# Requests per second per API group (overview.md 'Rate Limits', 1.2.24). ORDER_INFO is 6/s but
# 3/s from 09:00 to 09:10 KST, when the Korean orders go out: 3 is used all day.
GROUP_RATES: Mapping[str, float] = {
    "AUTH": 5.0,
    "ACCOUNT": 1.0,
    "ASSET": 5.0,
    "STOCK": 5.0,
    "MARKET_INFO": 3.0,
    "MARKET_DATA": 15.0,
    "ORDER": 10.0,
    "ORDER_HISTORY": 5.0,
    "ORDER_INFO": 3.0,
    "CONDITIONAL_ORDER_HISTORY": 10.0,
}
DEFAULT_RATE = 2.0  # an unknown group goes slowly

# Order statuses that are over (openapi.json OrderStatus). CANCEL_REJECTED and REPLACE_REJECTED
# are records of their own; the original order goes back to its earlier state.
TERMINAL_STATUSES = frozenset({"FILLED", "CANCELED", "REJECTED", "REPLACED"})
# The one status in both lists of GET /api/v1/orders (its `status` parameter, 1.2.24): OPEN holds
# PENDING, PARTIAL_FILLED, PENDING_CANCEL and PENDING_REPLACE; CLOSED holds the terminal ones,
# CANCEL_REJECTED, REPLACE_REJECTED and PARTIAL_FILLED. A partly filled order keeps the status
# while the rest still trades and may keep it after the rest lapsed: it is over only when the
# CLOSED list has it or it carries canceledAt (jobs/live_tasks.py Sync.finished).
OPEN_OR_CLOSED = "PARTIAL_FILLED"
# Statuses only the OPEN list holds: never over, whatever else the record says.
PENDING_STATUSES = frozenset({"PENDING", "PENDING_CANCEL", "PENDING_REPLACE"})
# Records of a refused cancel or change: the original order keeps its own record and fills.
REQUEST_RECORDS = frozenset({"CANCEL_REJECTED", "REPLACE_REJECTED"})


# ── transport ────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None = None


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]  # lower-case names
    body: bytes


Transport = Callable[[HttpRequest], HttpResponse]


class TransportError(Exception):
    """No answer: the connection failed or timed out. The request may have arrived."""


def urllib_transport(request: HttpRequest, timeout: float = REQUEST_TIMEOUT_S) -> HttpResponse:
    req = urllib.request.Request(
        request.url, data=request.body, headers=dict(request.headers), method=request.method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            return HttpResponse(int(resp.status), headers, resp.read())
    except urllib.error.HTTPError as exc:
        headers = {k.lower(): v for k, v in (exc.headers or {}).items()}
        try:
            body = exc.read()
        except (OSError, http.client.HTTPException):
            body = b""
        return HttpResponse(int(exc.code), headers, body)
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        raise TransportError(f"{type(exc).__name__}: {exc}") from exc


# ── errors ───────────────────────────────────────────────────────────────────────────────


class TossError(Exception):
    """Any failure talking to Toss."""


class TossUnreachableError(TossError):
    """No answer from Toss. For an order: it may or may not have been placed."""


class TossNotConfiguredError(TossError):
    """No Toss keys (the secrets file is missing them)."""


class LiveOrdersBlockedError(PermissionError):
    """An order or a cancellation without both keys (ops notes 안전)."""


@dataclass
class TossApiError(TossError):
    """An answer that is an error: the HTTP status, Toss's code, and its hints (`data`)."""

    status: int
    code: str
    message: str = ""
    data: Mapping[str, Any] = field(default_factory=dict)
    request_id: str | None = None

    def __str__(self) -> str:
        text = f"HTTP {self.status} {self.code}".strip()
        return f"{text}: {self.message}" if self.message else text


def error_of(status: int, payload: object, headers: Mapping[str, str]) -> TossApiError:
    """Read either error shape: the API's {"error": {"code", "message", "data", "requestId"}}
    and OAuth2's flat {"error": "access_denied", "error_description": "..."} (the old client
    read the nested shape out of the flat one and lost an IP refusal for four days). Anything
    else becomes a code of its own; the error path never raises a second error."""
    request_id = headers.get("x-request-id")
    if isinstance(payload, Mapping):
        err = payload.get("error")
        if isinstance(err, Mapping):
            data = err.get("data")
            return TossApiError(
                status,
                str(err.get("code") or f"http-{status}"),
                str(err.get("message") or ""),
                data if isinstance(data, Mapping) else {},
                str(err.get("requestId") or request_id or "") or None,
            )
        if isinstance(err, str):
            return TossApiError(
                status, err, str(payload.get("error_description") or ""), {}, request_id
            )
    return TossApiError(status, f"http-{status}", "", {}, request_id)


def link_state(exc: BaseException) -> str:
    """What a failure says about the link, as broker_status.state (the health screen's cause)."""
    if isinstance(exc, TossNotConfiguredError):
        return "no-key"
    if isinstance(exc, TossUnreachableError):
        return "unreachable"
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


# ── credentials and the token file ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class TossCredentials:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    account_no: str | None = field(default=None, repr=False)


def read_credentials(path: Path | None) -> TossCredentials | None:
    """The Toss keys from the secrets file (one line each); None when either key is missing."""
    if path is None:
        return None
    client_id = read_env_key(path, "TOSS_CLIENT_ID")
    secret = read_env_key(path, "TOSS_CLIENT_SECRET")
    if not client_id or not secret:
        return None
    return TossCredentials(client_id, secret, read_env_key(path, "TOSS_ACCOUNT_NO"))


class TokenStore:
    """token.json in its own 0700 folder: {token, expires_at, account_seq, account_tail}.
    Written atomically with 0600 whatever the umask (it is a live trading credential)."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self.path = folder / "token.json"

    def read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def write(self, data: Mapping[str, Any]) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            self.folder.chmod(0o700)
        tmp = self.path.with_name("token.json.tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(dict(data), fh)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)


# ── rate limits ──────────────────────────────────────────────────────────────────────────


class RateLimiter:
    """Requests of one group are spaced 1/rate seconds apart (no bursts: the safe side)."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        rates: Mapping[str, float] = GROUP_RATES,
    ) -> None:
        self.clock = clock
        self.sleep = sleep
        self.rates = rates
        self.next_at: dict[str, float] = {}

    def take(self, group: str) -> None:
        interval = 1.0 / self.rates.get(group, DEFAULT_RATE)
        now = self.clock()
        due = self.next_at.get(group, now)
        if due > now:
            self.sleep(due - now)
            now = due
        self.next_at[group] = now + interval


# ── what Toss answers ────────────────────────────────────────────────────────────────────


def dec(value: Any) -> Decimal | None:
    """Toss sends numbers as decimal strings; null is a real 'none'."""
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def _req_dec(value: Any, what: str) -> Decimal:
    out = dec(value)
    if out is None:
        raise TossApiError(200, "bad-answer", f"{what} is not a number")
    return out


def _time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return from_iso(str(value))
    except ValueError:
        return None


def _day(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


@dataclass(frozen=True)
class BrokerHolding:
    symbol: str
    market: str  # 'KR' | 'US'
    currency: Currency
    name: str
    qty: Decimal
    avg_price: Decimal
    last_price: Decimal

    def to_json(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "market": self.market,
            "currency": self.currency.value,
            "name": self.name,
            "qty": str(self.qty),
            "avg_price": str(self.avg_price),
            "last_price": str(self.last_price),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> BrokerHolding:
        return cls(
            symbol=str(data["symbol"]),
            market=str(data["market"]),
            currency=Currency(str(data["currency"])),
            name=str(data.get("name") or data["symbol"]),
            qty=Decimal(str(data["qty"])),
            avg_price=Decimal(str(data.get("avg_price") or "0")),
            last_price=Decimal(str(data.get("last_price") or "0")),
        )

    @property
    def instrument_id(self) -> str:
        return f"{self.market}:{self.symbol}"


@dataclass(frozen=True)
class BrokerOrder:
    """One order as GET /api/v1/orders(/{id}) shows it: fills summed per order (FAQ)."""

    order_id: str
    symbol: str
    side: str  # 'BUY' | 'SELL'
    order_type: str  # 'LIMIT' | 'MARKET'
    time_in_force: str
    status: str
    price: Decimal | None
    quantity: Decimal
    currency: Currency
    ordered_at: datetime | None
    canceled_at: datetime | None
    filled_qty: Decimal
    avg_price: Decimal | None
    filled_amount: Decimal | None
    commission: Decimal | None
    tax: Decimal | None
    filled_at: datetime | None
    settlement_date: date | None

    @property
    def terminal(self) -> bool:
        """Over by its own record: a terminal status, or a cancel time on an order that is not
        pending. A PARTIAL_FILLED order without one may still trade or may be over
        (OPEN_OR_CLOSED: the CLOSED list tells)."""
        if self.status in TERMINAL_STATUSES:
            return True
        return self.canceled_at is not None and self.status not in PENDING_STATUSES

    @property
    def market(self) -> str:
        return "US" if self.currency is Currency.USD else "KR"

    @property
    def instrument_id(self) -> str:
        return f"{self.market}:{self.symbol}"

    def to_json(self) -> dict[str, Any]:
        def text(v: object) -> str | None:
            if v is None:
                return None
            if isinstance(v, datetime):
                return v.isoformat()
            if isinstance(v, date):
                return v.isoformat()
            return str(v)

        return {
            "order_id": self.order_id,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "time_in_force": self.time_in_force,
            "status": self.status,
            "price": text(self.price),
            "quantity": text(self.quantity),
            "currency": self.currency.value,
            "ordered_at": text(self.ordered_at),
            "canceled_at": text(self.canceled_at),
            "filled_qty": text(self.filled_qty),
            "avg_price": text(self.avg_price),
            "filled_amount": text(self.filled_amount),
            "commission": text(self.commission),
            "tax": text(self.tax),
            "filled_at": text(self.filled_at),
            "settlement_date": text(self.settlement_date),
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> BrokerOrder:
        return cls(
            order_id=str(data["order_id"]),
            symbol=str(data["symbol"]),
            side=str(data["side"]),
            order_type=str(data.get("order_type") or ""),
            time_in_force=str(data.get("time_in_force") or ""),
            status=str(data["status"]),
            price=dec(data.get("price")),
            quantity=Decimal(str(data["quantity"])),
            currency=Currency(str(data["currency"])),
            ordered_at=_time(data.get("ordered_at")),
            canceled_at=_time(data.get("canceled_at")),
            filled_qty=dec(data.get("filled_qty")) or Decimal(0),
            avg_price=dec(data.get("avg_price")),
            filled_amount=dec(data.get("filled_amount")),
            commission=dec(data.get("commission")),
            tax=dec(data.get("tax")),
            filled_at=_time(data.get("filled_at")),
            settlement_date=_day(data.get("settlement_date")),
        )


def order_from_api(raw: Mapping[str, Any]) -> BrokerOrder:
    ex = raw.get("execution")
    execution: Mapping[str, Any] = ex if isinstance(ex, Mapping) else {}
    currency = Currency(str(raw.get("currency") or "KRW"))
    return BrokerOrder(
        order_id=str(raw["orderId"]),
        symbol=str(raw.get("symbol") or ""),
        side=str(raw.get("side") or "").upper(),
        order_type=str(raw.get("orderType") or "").upper(),
        time_in_force=str(raw.get("timeInForce") or "").upper(),
        status=str(raw.get("status") or "").upper(),
        price=dec(raw.get("price")),
        quantity=dec(raw.get("quantity")) or Decimal(0),
        currency=currency,
        ordered_at=_time(raw.get("orderedAt")),
        canceled_at=_time(raw.get("canceledAt")),
        filled_qty=dec(execution.get("filledQuantity")) or Decimal(0),
        avg_price=dec(execution.get("averageFilledPrice")),
        filled_amount=dec(execution.get("filledAmount")),
        commission=dec(execution.get("commission")),
        tax=dec(execution.get("tax")),
        filled_at=_time(execution.get("filledAt")),
        settlement_date=_day(execution.get("settlementDate")),
    )


@dataclass(frozen=True)
class ConditionalOrder:
    """One 조건주문 as GET /api/v1/conditional-orders lists it (every channel's: the app's, the
    old quant's). Armed, it places an order of its own when its trigger is reached."""

    conditional_order_id: str
    type: str  # SINGLE | OCO | OTO
    status: str  # OPEN: WATCHING | PAUSED | ORDERING | ORDERED; CLOSED: COMPLETED | EXPIRED
    symbol: str
    market: str  # 'KR' | 'US'
    quantity: Decimal
    sides: tuple[str, ...]  # its legs' orderSide (BUY | SELL), first then second
    created_at: datetime | None

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.conditional_order_id,
            "type": self.type,
            "status": self.status,
            "symbol": self.symbol,
            "market": self.market,
            "quantity": str(self.quantity),
            "sides": list(self.sides),
            "created_at": None if self.created_at is None else self.created_at.isoformat(),
        }


def conditional_from_api(raw: Mapping[str, Any]) -> ConditionalOrder:
    sides: list[str] = []
    for key in ("first", "second"):
        leg = raw.get(key)
        if isinstance(leg, Mapping) and leg.get("orderSide"):
            sides.append(str(leg["orderSide"]).upper())
    return ConditionalOrder(
        conditional_order_id=str(raw["conditionalOrderId"]),
        type=str(raw.get("type") or "").upper(),
        status=str(raw.get("status") or "").upper(),
        symbol=str(raw.get("symbol") or ""),
        market=str(raw.get("market") or ""),
        quantity=dec(raw.get("quantity")) or Decimal(0),
        sides=tuple(sides),
        created_at=_time(raw.get("createdAt")),
    )


@dataclass(frozen=True)
class StockInfo:
    symbol: str
    name: str
    market: str  # KOSPI | KOSDAQ | NYSE | NASDAQ | AMEX | KR_ETC | US_ETC
    security_type: str
    status: str  # SCHEDULED | ACTIVE | DELISTED
    currency: Currency
    liquidation: bool
    suspended: bool

    @property
    def tradable(self) -> bool:
        return self.status == "ACTIVE" and not self.liquidation and not self.suspended


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: Decimal
    at: datetime | None


@dataclass(frozen=True)
class FxInfo:
    rate: Decimal  # buying rate (1 USD = rate KRW)
    mid_rate: Decimal
    valid_from: datetime | None


@dataclass(frozen=True)
class OrderRequest:
    """What one live order sends (POST /api/v1/orders). Whole shares, limit orders, DAY."""

    client_order_id: str
    symbol: str
    side: str  # 'BUY' | 'SELL'
    quantity: int
    price: Decimal
    currency: Currency

    def body(self) -> dict[str, Any]:
        return {
            "clientOrderId": self.client_order_id,
            "symbol": self.symbol,
            "side": self.side,
            "orderType": "LIMIT",
            "timeInForce": "DAY",
            "quantity": str(self.quantity),
            "price": price_text(self.currency, self.price),
        }

    def to_json(self) -> dict[str, Any]:
        return {**self.body(), "currency": self.currency.value}

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> OrderRequest:
        return cls(
            client_order_id=str(data["clientOrderId"]),
            symbol=str(data["symbol"]),
            side=str(data["side"]),
            quantity=int(str(data["quantity"])),
            price=Decimal(str(data["price"])),
            currency=Currency(str(data["currency"])),
        )


def price_text(currency: Currency, price: Decimal) -> str:
    """Won are whole; dollars take 2 decimals at $1 and up, 4 below (the API cuts the rest)."""
    if currency is Currency.KRW:
        return str(int(price))
    places = Decimal("0.01") if price >= 1 else Decimal("0.0001")
    return str(price.quantize(places))


@dataclass(frozen=True)
class LivePermit:
    """Proof that both keys were checked just before an order or a cancellation. Only
    autotrade/broker/toss.py makes one (permit_for); a bare instance is refused."""

    ledger_id: str
    checked_at: datetime
    _granted: bool = field(default=False, repr=False)


# ── the client ───────────────────────────────────────────────────────────────────────────


class TossClient:
    def __init__(
        self,
        credentials: TossCredentials,
        token_folder: Path,
        *,
        transport: Transport = urllib_transport,
        wall_clock: Callable[[], float] = time.time,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
        base: str = BASE,
    ) -> None:
        self.credentials = credentials
        self.store = TokenStore(token_folder)
        self.transport = transport
        self.wall_clock = wall_clock
        self.sleep = sleep
        self.limiter = limiter or RateLimiter(sleep=sleep)
        self.base = base
        self.revoked = 0  # token-revoked answers seen (another program uses this client)
        self.issued = 0  # tokens issued by this client object

    # ── token and account ────────────────────────────────────────────────────────────────

    def _send(self, request: HttpRequest) -> HttpResponse:
        try:
            return self.transport(request)
        except TransportError as exc:
            raise TossUnreachableError(str(exc)) from exc

    def token(self, *, force: bool = False) -> str:
        cached = self.store.read()
        expires = float(cached.get("expires_at") or 0)
        token = cached.get("token")
        if not force and isinstance(token, str) and expires - self.wall_clock() > REFRESH_MARGIN_S:
            return token
        self.limiter.take("AUTH")
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
            )
        )
        payload = _json(resp)
        access = payload.get("access_token") if isinstance(payload, Mapping) else None
        if resp.status != 200 or not isinstance(access, str) or not access:
            raise error_of(resp.status, payload, resp.headers)
        lifetime = float(payload.get("expires_in") or 86400)
        # A new token says nothing new about the account: keep the cached account.
        self.store.write(
            {
                "token": access,
                "expires_at": self.wall_clock() + lifetime,
                "account_seq": cached.get("account_seq"),
                "account_tail": cached.get("account_tail"),
            }
        )
        self.issued += 1
        return access

    def _after_revoked(self, used: str) -> None:
        """401 token-revoked: a newer token exists. Ours (from the file) if another run of this
        program renewed it; otherwise someone else holds the client, and a new one is issued."""
        self.revoked += 1
        cached = self.store.read()
        if cached.get("token") not in (None, used):
            return
        self.token(force=True)

    def account(self, *, force: bool = False) -> tuple[int, str]:
        """(accountSeq, last 4 digits of the account number). Cached beside the token: the
        lookup is limited to 1 request a second (ACCOUNT)."""
        cached = self.store.read()
        if not force and cached.get("account_seq") and cached.get("token"):
            return int(cached["account_seq"]), str(cached.get("account_tail") or "")
        rows = self.call("GET", "/api/v1/accounts", group="ACCOUNT")
        accounts = [
            r for r in rows or [] if isinstance(r, Mapping) and r.get("accountType") == "BROKERAGE"
        ]
        wanted = _digits(self.credentials.account_no)
        if wanted:
            accounts = [r for r in accounts if _digits(str(r.get("accountNo") or "")) == wanted]
            if not accounts:
                raise TossApiError(404, "account-not-found", "TOSS_ACCOUNT_NO is not listed")
        elif len(accounts) != 1:
            raise TossApiError(
                404 if not accounts else 409,
                "account-not-found" if not accounts else "account-ambiguous",
                "no single brokerage account; set TOSS_ACCOUNT_NO",
            )
        seq = int(accounts[0]["accountSeq"])
        tail = _digits(str(accounts[0].get("accountNo") or ""))[-4:]
        cached = self.store.read()
        cached.update({"account_seq": seq, "account_tail": tail})
        if cached.get("token"):
            self.store.write(cached)
        return seq, tail

    # ── one request ──────────────────────────────────────────────────────────────────────

    def call(
        self,
        method: str,
        path: str,
        *,
        group: str,
        params: Mapping[str, Any] | None = None,
        body: Mapping[str, Any] | None = None,
        account: bool = False,
    ) -> Any:
        """One API request; returns `result`. Raises TossApiError or TossUnreachableError.

        Sent again only after a 401 (with a renewed token) or a 429 (after Retry-After): neither
        reached the order system, and an order carries its client order id anyway. Anything
        else surfaces at once: an order that failed is never retried here."""
        query = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"{self.base}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None if body is None else json.dumps(dict(body)).encode()
        renewed = waited = False
        while True:
            self.limiter.take(group)
            token = self.token()
            headers = {"authorization": f"Bearer {token}", "accept": "application/json"}
            if account:
                headers["x-tossinvest-account"] = str(self.account()[0])
            if data is not None:
                headers["content-type"] = "application/json"
            resp = self._send(HttpRequest(method, url, headers, data))
            payload = _json(resp)
            if 200 <= resp.status < 300 and not (
                isinstance(payload, Mapping) and "error" in payload
            ):
                if isinstance(payload, Mapping) and "result" in payload:
                    return payload["result"]
                return payload
            err = error_of(resp.status, payload, resp.headers)
            if resp.status == 401 and not renewed:
                renewed = True
                if err.code == "token-revoked":
                    self._after_revoked(token)
                else:
                    self.token(force=True)
                continue
            if resp.status == 429 and not waited:
                waited = True
                self.sleep(_retry_after(resp.headers))
                continue
            raise err

    # ── account and market ───────────────────────────────────────────────────────────────

    def holdings(self) -> list[BrokerHolding]:
        result = self.call("GET", "/api/v1/holdings", group="ASSET", account=True)
        items = result.get("items") if isinstance(result, Mapping) else None
        out: list[BrokerHolding] = []
        for item in items or []:
            if not isinstance(item, Mapping):
                continue
            currency = Currency(str(item.get("currency") or "KRW"))
            market = str(item.get("marketCountry") or ("US" if currency is Currency.USD else "KR"))
            out.append(
                BrokerHolding(
                    symbol=str(item["symbol"]),
                    market=market,
                    currency=currency,
                    name=str(item.get("name") or item["symbol"]),
                    qty=_req_dec(item.get("quantity"), "quantity"),
                    avg_price=dec(item.get("averagePurchasePrice")) or Decimal(0),
                    last_price=dec(item.get("lastPrice")) or Decimal(0),
                )
            )
        return out

    def buying_power(self, currency: Currency) -> Decimal:
        result = self.call(
            "GET",
            "/api/v1/buying-power",
            group="ORDER_INFO",
            account=True,
            params={"currency": currency.value},
        )
        if not isinstance(result, Mapping):
            raise TossApiError(200, "bad-answer", "buying power")
        return _req_dec(result.get("cashBuyingPower"), "cashBuyingPower")

    def sellable_quantity(self, symbol: str) -> Decimal:
        result = self.call(
            "GET",
            "/api/v1/sellable-quantity",
            group="ORDER_INFO",
            account=True,
            params={"symbol": symbol},
        )
        if not isinstance(result, Mapping):
            raise TossApiError(200, "bad-answer", "sellable quantity")
        return _req_dec(result.get("sellableQuantity"), "sellableQuantity")

    def commissions(self, today: date) -> dict[str, Decimal]:
        """The commission rate of each market on `today` (KST): the row whose startDate..endDate
        (either may be null: open-ended) holds it. A market with no such row (a promotion ended
        and nothing else is listed) takes its highest rate: a fee counted too low sizes a buy
        the broker refuses (422 insufficient-buying-power)."""
        result = self.call("GET", "/api/v1/commissions", group="ORDER_INFO", account=True)
        valid: dict[str, Decimal] = {}
        other: dict[str, Decimal] = {}
        for row in result or []:
            if not isinstance(row, Mapping):
                continue
            rate = dec(row.get("commissionRate"))
            if rate is None:
                continue
            market = str(row.get("marketCountry") or "")
            start, end = _day(row.get("startDate")), _day(row.get("endDate"))
            now = (start is None or start <= today) and (end is None or today <= end)
            into = valid if now else other
            into[market] = max(rate, into.get(market, rate))
        return {**other, **valid}

    def prices(self, symbols: Sequence[str]) -> dict[str, Quote]:
        result = self.call(
            "GET", "/api/v1/prices", group="MARKET_DATA", params={"symbols": ",".join(symbols)}
        )
        out: dict[str, Quote] = {}
        for row in result or []:
            if isinstance(row, Mapping):
                price = dec(row.get("lastPrice"))
                if price is not None and price > 0:
                    sym = str(row.get("symbol"))
                    out[sym] = Quote(sym, price, _time(row.get("timestamp")))
        return out

    def stocks(self, symbols: Sequence[str]) -> dict[str, StockInfo]:
        result = self.call(
            "GET", "/api/v1/stocks", group="STOCK", params={"symbols": ",".join(symbols)}
        )
        out: dict[str, StockInfo] = {}
        for row in result or []:
            if not isinstance(row, Mapping):
                continue
            detail = row.get("koreanMarketDetail")
            kr: Mapping[str, Any] = detail if isinstance(detail, Mapping) else {}
            sym = str(row.get("symbol"))
            out[sym] = StockInfo(
                symbol=sym,
                name=str(row.get("name") or sym),
                market=str(row.get("market") or ""),
                security_type=str(row.get("securityType") or ""),
                status=str(row.get("status") or ""),
                currency=Currency(str(row.get("currency") or "KRW")),
                liquidation=bool(kr.get("liquidationTrading")),
                suspended=bool(kr.get("krxTradingSuspended")),
            )
        return out

    def exchange_rate(self) -> FxInfo:
        result = self.call(
            "GET",
            "/api/v1/exchange-rate",
            group="MARKET_INFO",
            params={"baseCurrency": "USD", "quoteCurrency": "KRW"},
        )
        if not isinstance(result, Mapping):
            raise TossApiError(200, "bad-answer", "exchange rate")
        return FxInfo(
            _req_dec(result.get("rate"), "rate"),
            _req_dec(result.get("midRate"), "midRate"),
            _time(result.get("validFrom")),
        )

    def market_calendar(self, country: str, day: date | None = None) -> Mapping[str, Any]:
        result = self.call(
            "GET",
            f"/api/v1/market-calendar/{country}",
            group="MARKET_INFO",
            params={"date": None if day is None else day.isoformat()},
        )
        return result if isinstance(result, Mapping) else {}

    # ── orders ───────────────────────────────────────────────────────────────────────────

    def order(self, order_id: str) -> BrokerOrder:
        path = f"/api/v1/orders/{urllib.parse.quote(order_id, safe='')}"
        result = self.call("GET", path, group="ORDER_HISTORY", account=True)
        if not isinstance(result, Mapping):
            raise TossApiError(200, "bad-answer", "order")
        return order_from_api(result)

    def orders(
        self,
        status: str,
        *,
        symbol: str | None = None,
        start: date | None = None,
        end: date | None = None,
        max_pages: int = 20,
    ) -> list[BrokerOrder]:
        """OPEN (all of them) or CLOSED (every page, 100 a page) orders of the account, from
        every channel (the app and WTS too). `start`/`end` filter by the KST order date."""
        out: list[BrokerOrder] = []
        cursor: str | None = None
        for _ in range(max_pages):
            result = self.call(
                "GET",
                "/api/v1/orders",
                group="ORDER_HISTORY",
                account=True,
                params={
                    "status": status,
                    "symbol": symbol,
                    "from": None if start is None else start.isoformat(),
                    "to": None if end is None else end.isoformat(),
                    "limit": 100 if status == "CLOSED" else None,
                    "cursor": cursor,
                },
            )
            if not isinstance(result, Mapping):
                break
            out.extend(
                order_from_api(o) for o in result.get("orders") or [] if isinstance(o, Mapping)
            )
            cursor = result.get("nextCursor")
            if status != "CLOSED" or not result.get("hasNext") or not cursor:
                return out
        raise TossApiError(200, "too-many-pages", f"more than {max_pages} pages of {status}")

    def conditional_orders(
        self, status: str = "OPEN", *, max_pages: int = 20
    ) -> list[ConditionalOrder]:
        """The account's 조건주문 (OPEN: watching, paused or ordering; CLOSED: completed or
        expired), from every channel, 100 a page. Reads only: the engine never arms one."""
        out: list[ConditionalOrder] = []
        cursor: str | None = None
        for _ in range(max_pages):
            result = self.call(
                "GET",
                "/api/v1/conditional-orders",
                group="CONDITIONAL_ORDER_HISTORY",
                account=True,
                params={"status": status, "limit": 100, "cursor": cursor},
            )
            if not isinstance(result, Mapping):
                return out
            out.extend(
                conditional_from_api(o)
                for o in result.get("conditionalOrders") or []
                if isinstance(o, Mapping) and o.get("conditionalOrderId")
            )
            cursor = result.get("nextCursor")
            if not result.get("hasNext") or not cursor:
                return out
        raise TossApiError(200, "too-many-pages", f"more than {max_pages} pages of {status}")

    def create_order(self, permit: LivePermit, request: OrderRequest) -> tuple[str, str | None]:
        """Place one order. Returns (orderId, clientOrderId). Within 10 minutes the same client
        order id and content return the first order instead of a new one (PHASE3.md 1.7)."""
        _check_permit(permit)
        result = self.call(
            "POST", "/api/v1/orders", group="ORDER", account=True, body=request.body()
        )
        if not isinstance(result, Mapping) or not result.get("orderId"):
            raise TossApiError(200, "bad-answer", "order created without an id")
        client = result.get("clientOrderId")
        return str(result["orderId"]), None if client is None else str(client)

    def cancel_order(self, permit: LivePermit, order_id: str) -> str:
        """Cancel an open order; returns the id Toss gives the cancellation."""
        _check_permit(permit)
        path = f"/api/v1/orders/{urllib.parse.quote(order_id, safe='')}/cancel"
        result = self.call("POST", path, group="ORDER", account=True, body={})
        return str(result.get("orderId") or "") if isinstance(result, Mapping) else ""


def _check_permit(permit: object) -> None:
    if not isinstance(permit, LivePermit) or not permit._granted:
        raise LiveOrdersBlockedError("an order needs AUTOTRADE_LIVE_ORDERS=1 and the mode 'live'")


def _digits(text: str | None) -> str:
    return "".join(ch for ch in (text or "") if ch.isdigit())


def _json(resp: HttpResponse) -> Any:
    if not resp.body:
        return {}
    try:
        return json.loads(resp.body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {"error": {"code": f"http-{resp.status}", "message": "not JSON"}}


def _retry_after(headers: Mapping[str, str]) -> float:
    try:
        wait = float(headers.get("retry-after", "1"))
    except ValueError:
        wait = 1.0
    return max(0.0, min(wait, RETRY_AFTER_CAP_S))
