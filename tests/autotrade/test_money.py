"""Rounding rules, reverse-engineered from Vault 7-웹기획/예시-값표.md."""

from __future__ import annotations

from decimal import Decimal

import pytest

from autotrade.domain.instruments import Currency
from autotrade.domain.money import (
    FeeRates,
    ceil_cents,
    ceil_to_step,
    dec,
    floor_div,
    kr_fee,
    krw_to_usd,
    normalize_price,
    quantize_amount,
    round_rate,
    trade_fee,
    us_fee,
    usd_in_krw,
    usd_to_krw,
)

FEES = FeeRates()
D = Decimal


@pytest.mark.parametrize(
    ("gross", "fee"),
    [
        ("169000", "25"),  # 8/21 sell 5 x 33,800 = 169,000 -> 25.35 -> 25
        ("181900", "27"),  # 10/7 sell 5 x 36,380 = 181,900 -> 27.285 -> 27
        ("4992000", "748"),  # §4 first day 156 x 32,000 -> 748.8 -> 748 (floor, not 749)
        ("832500", "124"),  # 7/1 Samsung 15 x 55,500 -> 124.875 -> 124 (fee total 5,667)
        ("4000000", "600"),  # 7/1 KOSPI200 ETF 125 x 32,000
        ("181850", "27"),  # live 10/7 sell 5 x 36,370
    ],
)
def test_korean_fee_is_floored_to_the_won(gross: str, fee: str) -> None:
    assert kr_fee(D(gross), FEES.kr) == D(fee)


@pytest.mark.parametrize(
    ("gross", "fee"),
    [
        ("126.00", "0.13"),  # 8/21 buy 2 x $63.00 -> 0.126 -> 0.13 (floor would be 0.12)
        ("124.80", "0.12"),  # 10/7 buy 2 x ~$62.40 -> 0.1248 -> 0.12
        ("2904.00", "2.90"),  # 7/1 S&P 44 x $66.00
        ("516.00", "0.52"),  # 7/1 NVDA 3 x $172.00
        ("3564.00", "3.56"),  # §4 S&P 54 x $66.00
    ],
)
def test_us_fee_is_rounded_half_up_to_the_cent(gross: str, fee: str) -> None:
    assert us_fee(D(gross), FEES.us) == D(fee)


def test_fee_dispatch_by_currency() -> None:
    assert trade_fee(Currency.KRW, D("169000"), FEES) == D("25")
    assert trade_fee(Currency.USD, D("126.00"), FEES) == D("0.13")
    assert FEES.rate_for(Currency.KRW) == D("0.00015")
    assert FEES.rate_for(Currency.USD) == D("0.001")


@pytest.mark.parametrize(
    ("krw", "rate", "usd"),
    [
        ("175000", "1389.6", "125.93"),  # 8/21
        ("173000", "1380.6", "125.30"),  # 10/7
        ("4967000", "1392.0", "3568.24"),  # §4 first day
        ("4768000", "1392.0", "3425.28"),  # 7/1, two-rule world
        ("173000", "1381.5", "125.22"),  # live 10/7
        ("4705000", "1382.4", "3403.50"),  # §1.6 preview '약 $3,403'
    ],
)
def test_krw_to_usd_truncates_to_the_cent(krw: str, rate: str, usd: str) -> None:
    assert krw_to_usd(D(krw), D(rate)) == D(usd)


@pytest.mark.parametrize(
    ("usd", "rate", "krw"),
    [
        ("0.13", "1389.6", "181"),  # 8/21 US fee in won: 180.648 -> 181
        ("126.96", "1382.4", "175510"),  # §1.1 dollar cash: 175,509.504 -> 175,510
        ("3568.24", "1391.5", "4965206"),  # §4 dollar cash: 4,965,205.96 -> 4,965,206
        ("125.67", "1382.4", "173726"),  # §2.2 live dollar cash
        ("0.45", "1382.4", "622"),  # §2.3 dollar cash $0.45 -> 622
    ],
)
def test_dollars_are_valued_half_up_to_the_won(usd: str, rate: str, krw: str) -> None:
    assert usd_in_krw(D(usd), D(rate)) == D(krw)


def test_usd_to_krw_conversion_floors() -> None:
    assert usd_to_krw(D("125.31"), D("1380.6")) == D("173002")  # 173,002.986 -> 173,002
    assert usd_to_krw(D("1.00"), D("1380.65")) == D("1380")


def test_rate_price_and_amount_quantization() -> None:
    assert round_rate(dec(1382.43994140625)) == D("1382.4")
    assert round_rate(D("1382.45")) == D("1382.5")
    assert normalize_price(Currency.KRW, dec(36250.0)) == D("36250")
    assert normalize_price(Currency.USD, dec(62.400001525878906)) == D("62.40")
    assert quantize_amount(Currency.KRW, D("10.5")) == D("11")
    assert quantize_amount(Currency.USD, D("0.125")) == D("0.13")
    assert dec("1.5") == D("1.5")
    assert dec(7) == D(7)
    assert dec(D("2.5")) == D("2.5")


def test_ceil_helpers() -> None:
    assert ceil_to_step(D("4966049.088"), D("1000")) == D("4967000")
    assert ceil_to_step(D("173000"), D("1000")) == D("173000")
    assert ceil_cents(D("125.301")) == D("125.31")
    with pytest.raises(ValueError, match="step"):
        ceil_to_step(D("1"), D("0"))


def test_floor_div() -> None:
    assert floor_div(D("188946.5"), D("33790")) == 5
    assert floor_div(D("-1"), D("10")) == 0
    with pytest.raises(ValueError, match="unit"):
        floor_div(D("1"), D("0"))
