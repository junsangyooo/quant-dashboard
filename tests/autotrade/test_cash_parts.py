"""What the cash is for: buy-wait, sub-share leftover, withdraw-wait, new (pending_cash)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from autotrade.domain.cash import (
    CashPart,
    Claim,
    Purpose,
    WithdrawWait,
    amount_by_purpose,
    buy_wait_by_instrument,
    partition,
    split_pro_rata,
)
from autotrade.domain.instruments import Currency

D = Decimal
K = "KR:069500"
S = "US:SPYM"


def test_1007_dollars_wait_in_full_and_won_is_a_leftover() -> None:
    # §1.1 at 10/07 16:00: '$126.96 매수 대기 (S&P 500 ETF 2주 몫)',
    # '원화 현금 · 1주 미만 대기 56,548'.
    parts = partition(
        {Currency.KRW: D("56548"), Currency.USD: D("126.96")},
        [],
        [Claim(Currency.USD, D("124.92"), {S: D(1)})],
        {},
    )
    assert parts == [
        CashPart(Currency.KRW, Purpose.SUB_SHARE, D("56548")),
        CashPart(Currency.USD, Purpose.BUY_WAIT, D("126.96"), instrument_id=S),
    ]
    assert buy_wait_by_instrument(parts) == {S: {Currency.USD: D("126.96")}}


def test_start_amount_is_new_cash_until_the_first_check() -> None:
    parts = partition({Currency.KRW: D("10000000")}, [], [], {Currency.KRW: D("10000000")})
    assert parts == [CashPart(Currency.KRW, Purpose.NEW, D("10000000"))]


def test_before_the_first_orders_the_won_is_split_between_the_two_buys() -> None:
    parts = partition(
        {Currency.KRW: D("10000000")},
        [],
        [
            Claim(Currency.KRW, D("4992748.8"), {K: D(1)}),
            Claim(Currency.KRW, D("4967000"), {S: D("3567.56")}),
        ],
        {Currency.KRW: D("10000000")},
    )
    waits = buy_wait_by_instrument(parts)
    assert waits[K][Currency.KRW] + waits[S][Currency.KRW] == D("10000000")
    assert waits[K][Currency.KRW] == D("5012926")  # 10,000,000 x 4,992,748.8 / 9,959,748.8


def test_withdraw_wait_comes_first_and_is_never_free() -> None:
    # §2.3: 500,425 won waits for withdrawal until 10/12; the rest is ordinary cash.
    parts = partition(
        {Currency.KRW: D("577566"), Currency.USD: D("0.45")},
        [WithdrawWait(Currency.KRW, D("500425"), date(2026, 10, 12))],
        [],
        {},
    )
    assert amount_by_purpose(parts, Purpose.WITHDRAW_WAIT) == {Currency.KRW: D("500425")}
    assert amount_by_purpose(parts, Purpose.SUB_SHARE) == {
        Currency.KRW: D("77141"),
        Currency.USD: D("0.45"),
    }
    assert parts[0].until == date(2026, 10, 12)


def test_new_cash_is_capped_by_the_free_cash() -> None:
    parts = partition({Currency.KRW: D("100")}, [], [], {Currency.KRW: D("500")})
    assert parts == [CashPart(Currency.KRW, Purpose.NEW, D("100"))]
    assert partition({Currency.KRW: D("0")}, [], [], {}) == []


def test_split_pro_rata_is_exact() -> None:
    out = split_pro_rata(D("100"), [("a", D(1)), ("b", D(1)), ("c", D(1))], D("1"))
    assert out == {"a": D("33"), "b": D("33"), "c": D("34")}
    assert split_pro_rata(D("5"), [("a", D(0))], D("1")) == {"a": D("5")}
    assert split_pro_rata(D("5"), [], D("1")) == {}
