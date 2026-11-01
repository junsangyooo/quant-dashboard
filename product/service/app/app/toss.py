"""토스증권 Open API 조회 전용 클라이언트.

출처: 이 레포의 autotrade/broker/toss_api.py (2026-10-29 기준)에서
조회에 필요한 부분만 옮겨 고쳤다. 가져오기(import)는 하지 않는다.

옮긴 것: 전송 주입(HttpRequest/HttpResponse/urllib_transport), 오류 읽기(error_of · link_state),
토큰 받기, 계좌 찾기, GET 요청 하나(call), 현재가(prices), 보유(holdings), 매수 가능 금액(buying_power).
바꾼 것:
- 토큰은 파일에 쓰지 않고 이 객체의 메모리에만 둔다(앱을 끄면 사라진다).
- 요청은 GET만 보낸다. POST는 토큰 받기 한 곳뿐이다.
- 요청 간격 조절(RateLimiter)은 뺐다. 연결 확인은 요청 세 번이다.
옮기지 않은 것: 돈이 움직이는 요청과 그 허가 장치 전부. 이 파일에는 그런 함수가 없다.
"""

from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

BASE = "https://openapi.tossinvest.com"
REQUEST_TIMEOUT_S = 20.0
REFRESH_MARGIN_S = 600.0


@dataclass(frozen=True)
class HttpRequest:
    method: str
    url: str
    headers: Mapping[str, str]
    body: bytes | None = None


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes


Transport = Callable[[HttpRequest], HttpResponse]


class TransportError(Exception):
    """응답 없음: 연결 실패나 시간 초과."""


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
        raise TransportError(type(exc).__name__) from None


def offline_transport(request: HttpRequest) -> HttpResponse:
    """MVP_TOSS_OFFLINE=1일 때: 네트워크에 나가지 않고 '응답 없음'으로 끝난다."""
    raise TransportError("offline")


class TossError(Exception):
    pass


class TossUnreachableError(TossError):
    pass


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
    """auth · ip · unreachable · account · maintenance · error"""
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


@dataclass(frozen=True)
class TossCredentials:
    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    account_no: str | None = field(default=None, repr=False)


def dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


@dataclass(frozen=True)
class Quote:
    symbol: str
    price: Decimal


@dataclass(frozen=True)
class Holding:
    symbol: str
    name: str
    qty: Decimal
    avg_price: Decimal
    last_price: Decimal


class TossClient:
    def __init__(
        self,
        credentials: TossCredentials,
        *,
        transport: Transport = urllib_transport,
        wall_clock: Callable[[], float] = time.time,
        base: str = BASE,
    ) -> None:
        self.credentials = credentials
        self.transport = transport
        self.wall_clock = wall_clock
        self.base = base
        self._token: str | None = None
        self._expires = 0.0
        self._account: tuple[int, str] | None = None

    def __repr__(self) -> str:
        return "TossClient(<keys hidden>)"

    def _send(self, request: HttpRequest) -> HttpResponse:
        try:
            return self.transport(request)
        except TransportError as exc:
            raise TossUnreachableError(str(exc)) from None

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
            )
        )
        payload = _json(resp)
        access = payload.get("access_token") if isinstance(payload, Mapping) else None
        if resp.status != 200 or not isinstance(access, str) or not access:
            raise error_of(resp.status, payload)
        self._token = access
        self._expires = self.wall_clock() + float(payload.get("expires_in") or 86400)
        return access

    def account(self, *, force: bool = False) -> tuple[int, str]:
        """(accountSeq, 계좌번호 끝 4자리)."""
        if self._account and not force:
            return self._account
        rows = self.call("/api/v1/accounts")
        accounts = [
            r for r in rows or [] if isinstance(r, Mapping) and r.get("accountType") == "BROKERAGE"
        ]
        wanted = _digits(self.credentials.account_no)
        if wanted:
            accounts = [r for r in accounts if _digits(str(r.get("accountNo") or "")) == wanted]
            if not accounts:
                raise TossApiError(404, "account-not-found")
        elif len(accounts) != 1:
            raise TossApiError(
                404 if not accounts else 409,
                "account-not-found" if not accounts else "account-ambiguous",
            )
        seq = int(accounts[0]["accountSeq"])
        tail = _digits(str(accounts[0].get("accountNo") or ""))[-4:]
        self._account = (seq, tail)
        return self._account

    def call(
        self, path: str, *, params: Mapping[str, Any] | None = None, account: bool = False
    ) -> Any:
        """GET 하나. 401이면 토큰을 새로 받아 한 번 더 보낸다."""
        query = {k: v for k, v in (params or {}).items() if v is not None}
        url = f"{self.base}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(query)
        renewed = False
        while True:
            token = self.token()
            headers = {"authorization": f"Bearer {token}", "accept": "application/json"}
            if account:
                headers["x-tossinvest-account"] = str(self.account()[0])
            resp = self._send(HttpRequest("GET", url, headers, None))
            payload = _json(resp)
            if 200 <= resp.status < 300 and not (isinstance(payload, Mapping) and "error" in payload):
                if isinstance(payload, Mapping) and "result" in payload:
                    return payload["result"]
                return payload
            err = error_of(resp.status, payload)
            if resp.status == 401 and not renewed:
                renewed = True
                self.token(force=True)
                continue
            raise err

    def prices(self, symbols: Sequence[str]) -> dict[str, Quote]:
        result = self.call("/api/v1/prices", params={"symbols": ",".join(symbols)})
        out: dict[str, Quote] = {}
        for row in result or []:
            if isinstance(row, Mapping):
                price = dec(row.get("lastPrice"))
                if price is not None and price > 0:
                    sym = str(row.get("symbol"))
                    out[sym] = Quote(sym, price)
        return out

    def holdings(self) -> list[Holding]:
        result = self.call("/api/v1/holdings", account=True)
        items = result.get("items") if isinstance(result, Mapping) else None
        out: list[Holding] = []
        for item in items or []:
            if not isinstance(item, Mapping) or dec(item.get("quantity")) is None:
                continue
            out.append(
                Holding(
                    symbol=str(item["symbol"]),
                    name=str(item.get("name") or item["symbol"]),
                    qty=dec(item.get("quantity")) or Decimal(0),
                    avg_price=dec(item.get("averagePurchasePrice")) or Decimal(0),
                    last_price=dec(item.get("lastPrice")) or Decimal(0),
                )
            )
        return out

    def buying_power(self, currency: str = "KRW") -> Decimal:
        result = self.call("/api/v1/buying-power", account=True, params={"currency": currency})
        value = dec(result.get("cashBuyingPower")) if isinstance(result, Mapping) else None
        if value is None:
            raise TossApiError(200, "bad-answer")
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
