"""포트: 바깥과의 약속(ARCHITECTURE 2절 포트 층 · 4절 확장 지점 · 6절 '바꿔 끼우기' · QUALITY E1 · E7).

실행 흐름(`run/` · `backtest_v2`)은 어댑터 클래스(`adapters/`) 대신 이 약속을 받아요.
어댑터를 고르고 넣어 주는 것은 조립(`main.create_app`)이에요(기본은 가짜 · 응답 없음 · `adapters/fake.py`).

- `Broker`: 계좌 · 주문(토스 어댑터 `adapters.toss.TossClient`가 맞춰요 · 증권사는 토스만 · 기능표는 두 번째 증권사 때).
- `MarketFeed`: 일봉 받기(`adapters.toss.TossSource` · 시험의 가짜 일봉).
- `Disclosures`: 재무 · 공시 읽기(DART 저장 `dart.DartStore` · 접수일 다음 거래일부터 · R-J9).
- `Notifier`: 알림 하나 보내기(`telegram.Telegram.notify` · 사건 이름 + 글).
- `Clock`: 지금 시각(한국 시간이 붙은 datetime · 기본 `market.now_kst` · 시험은 고정 시각).
- AI 제공사 포트(`AiProvider`)는 4단계예요.

약속은 `typing.Protocol`(모양만 맞으면 됨)이라 어댑터는 이 파일을 몰라도 돼요. 약속 이름은 지금 클래스 이름과 겹치지
않아요(`tests/test_ports.py`). 값 꼴(`HeldPosition` · `PlacedOrder` …)은 어댑터가 돌려주는 값에서 실행 흐름이 읽는 속성이에요.

오류: 포트를 부르다 나는 오류의 종류도 약속이에요(`BrokerError` · `NoAnswer` …). 어댑터 오류(`TossError` ·
`TransportError` …)가 이를 이어받고, 실행 흐름은 포트 쪽 이름으로 잡아요. 종류마다 이어받는 어댑터 오류는 하나씩이라 잡히는
것은 전과 같아요. 오류를 앱 오류 번호로 바꾸는 일은 열린 질문 Q-N23의 답 뒤예요(이 파일은 번호를 두지 않아요).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

# ── 시각 · 알림 ─────────────────────────────────────────────────────────────


class Clock(Protocol):
    """지금 시각. 한국 시간(`domain.markets.kr.KST`)이 붙은 datetime을 돌려줘요."""

    def __call__(self) -> datetime: ...


class Notifier(Protocol):
    """알림 하나: 사건 이름(`telegram.EVENTS`의 키)과 글. 보냈는지는 어댑터가 알아서 남겨요."""

    def __call__(self, event: str, text: str, /) -> object: ...


# ── 일봉 · 재무 · 공시 ─────────────────────────────────────────────────────


class MarketFeed(Protocol):
    """일봉 받기: start ~ end(오래된 순 · 수정주가) `{"d", "o", "h", "l", "c", "v"}` 목록.

    그 코드로는 일봉이 없으면 `SymbolNotFound`, 받을 연결이 없으면(토스 연결 전) `FeedNotConnected`를 내요."""

    def daily(self, symbol: str, start: date, end: date) -> list[dict[str, Any]]: ...


class LoadProgress(Protocol):
    """자료 받기 진행(DART 큐)."""

    @property
    def fast_done(self) -> bool: ...

    @property
    def pct(self) -> int: ...


class Disclosures(Protocol):
    """재무 · 공시 읽기. `on` 날 확인에 쓸 수 있는 행만(접수일 다음 거래일부터 · `next_open`으로 셈)."""

    def progress(self) -> LoadProgress: ...

    def financial_rows(self, stock: str, on: date, next_open: Callable[[date], date]) -> list[dict[str, Any]]: ...

    def disclosures_on(self, stock: str, on: date, next_open: Callable[[date], date]) -> list[dict[str, Any]]: ...


# ── 증권사 ──────────────────────────────────────────────────────────────────


class AccountRef(Protocol):
    @property
    def account_no(self) -> str | None: ...


class PriceQuote(Protocol):
    @property
    def symbol(self) -> str: ...

    @property
    def price(self) -> Decimal: ...

    @property
    def timestamp(self) -> str | None: ...


class PriceCheck(Protocol):
    """시세 목록: 쓸 수 있는 값(`items` · 종목 → `PriceQuote`) + 종목별 이상(`anomalies` · R-O14 · 그 종목 주문 0)."""

    @property
    def items(self) -> Mapping[str, Any]: ...

    @property
    def anomalies(self) -> Mapping[str, str]: ...


class HeldPosition(Protocol):
    @property
    def symbol(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def qty(self) -> Decimal: ...

    @property
    def avg_price(self) -> Decimal: ...

    @property
    def last_price(self) -> Decimal: ...


class OrderFill(Protocol):
    @property
    def filled_qty(self) -> Decimal: ...

    @property
    def avg_price(self) -> Decimal | None: ...

    @property
    def filled_amount(self) -> Decimal | None: ...

    @property
    def commission(self) -> Decimal | None: ...

    @property
    def tax(self) -> Decimal | None: ...

    @property
    def filled_at(self) -> str | None: ...


class PlacedOrder(Protocol):
    @property
    def order_id(self) -> str: ...

    @property
    def symbol(self) -> str: ...

    @property
    def side(self) -> str: ...

    @property
    def order_type(self) -> str: ...

    @property
    def tif(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def price(self) -> Decimal | None: ...

    @property
    def qty(self) -> Decimal: ...

    @property
    def ordered_at(self) -> str: ...

    @property
    def execution(self) -> OrderFill: ...


class StopLeg(Protocol):
    """조건주문의 다리 하나(손절 · 익절)."""

    @property
    def kind(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def side(self) -> str: ...

    @property
    def trigger(self) -> Decimal | None: ...

    @property
    def price(self) -> Decimal | None: ...

    @property
    def triggered_order_id(self) -> str | None: ...


class StopOrder(Protocol):
    """조건주문(SINGLE · OCO · OTO)."""

    @property
    def cond_id(self) -> str: ...

    @property
    def kind(self) -> str: ...

    @property
    def status(self) -> str: ...

    @property
    def symbol(self) -> str: ...

    @property
    def qty(self) -> Decimal: ...

    @property
    def order_type(self) -> str: ...

    @property
    def expire(self) -> str | None: ...

    @property
    def first(self) -> StopLeg: ...

    @property
    def second(self) -> StopLeg | None: ...

    @property
    def created_at(self) -> str: ...


class Broker(Protocol):
    """계좌 · 시세 · 주문 · 조건주문. 실행 흐름(실전)이 부르는 것만 적어요(모양은 토스 Open API 1.2.28 어댑터 그대로)."""

    @property
    def credentials(self) -> AccountRef: ...

    def token(self, *, force: bool = False) -> str: ...

    def account(self, *, force: bool = False) -> tuple[int, str]: ...

    def prices(self, symbols: Sequence[str]) -> Mapping[str, PriceQuote]: ...

    def prices_checked(self, symbols: Sequence[str], prev_close: Mapping[str, float | None] | None = None) -> PriceCheck: ...

    def holdings(self) -> Sequence[HeldPosition]: ...

    def buying_power(self, currency: str = "KRW") -> Decimal: ...

    def sellable_quantity(self, symbol: str) -> Decimal: ...

    def create_order(self, *, symbol: str, side: str, quantity: int | Decimal, order_type: str = "LIMIT",
                     price: Decimal | int | None = None, tif: str = "DAY", client_order_id: str | None = None,
                     confirm_high_value: bool = False) -> str: ...

    def order(self, order_id: str) -> PlacedOrder: ...

    def orders(self, status: str = "OPEN", *, symbol: str | None = None, from_: str | None = None,
               to: str | None = None, cursor: str | None = None,
               limit: int = 100) -> tuple[Sequence[PlacedOrder], str | None]: ...

    def cancel_order(self, order_id: str) -> str: ...

    def modify_order(self, order_id: str, *, order_type: str, quantity: int | Decimal | None = None,
                     price: Decimal | int | None = None) -> str: ...

    def create_conditional_order(self, *, symbol: str, kind: str, quantity: int | Decimal, expire: date,
                                 first: Mapping[str, Any], second: Mapping[str, Any] | None = None,
                                 order_type: str = "LIMIT", client_order_id: str | None = None) -> str: ...

    def conditional_order(self, cond_id: str) -> StopOrder: ...

    def cancel_conditional_order(self, cond_id: str) -> None: ...


# ── 오류 종류(어댑터 오류가 이어받아요) ─────────────────────────────────────


class NoAnswer(Exception):
    """전송이 답하지 않음: 연결 실패 · 시간 초과 · 가짜 전송의 '응답 없음'(`adapters.transport.TransportError`)."""


class BrokerError(Exception):
    """증권사를 부르다 난 오류(`adapters.toss.TossError`)."""


class BrokerUnreachable(BrokerError):
    """증권사에 닿지 않음(`adapters.toss.TossUnreachableError`)."""


class BrokerBadAnswer(BrokerError):
    """응답 이상: 성공 응답의 꼴이 약속과 달라요(R-O14 · `adapters.toss.TossShapeError`)."""


class BrokerRejected(BrokerError):
    """증권사가 거절한 응답: HTTP 상태와 오류 코드(`adapters.toss.TossApiError`)."""

    status: int
    code: str


class SymbolNotFound(Exception):
    """일봉 받기(`MarketFeed`): 그 코드로는 일봉이 없음(토스 404 · 없는 종목)."""


class FeedNotConnected(Exception):
    """일봉 받기(`MarketFeed`): 받을 연결이 없음(토스 연결 전 · `adapters.toss.TossSource`)."""
