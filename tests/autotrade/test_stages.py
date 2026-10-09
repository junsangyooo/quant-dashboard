"""Stage plan and times: KR 09:05, FX 09:10, US at the open (22:30 / 23:30 KST)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from autotrade.domain.instruments import kr_etf, us_etf
from autotrade.domain.money import FeeRates
from autotrade.domain.planner import Plan, PlanInput, PlanItem, StageKind, plan_rule
from autotrade.domain.stages import Slotter, StageMarket, StageSpec, schedule, stage_specs
from autotrade.market.calendar import KRX, NYSE
from autotrade.timeutil import KST

D = Decimal
KOSPI = kr_etf("069500", "KOSPI200 ETF")
SNP = us_etf("SPYM", "S&P 500 ETF")
SLOT = Slotter(KRX, NYSE)


def kst(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=KST)


def plan(kq: int, kp: str, sq: int, sp: str, rate: str, krw: str, usd: str = "0") -> Plan:
    return plan_rule(
        PlanInput(
            items=(PlanItem(KOSPI, D("0.5"), kq, D(kp)), PlanItem(SNP, D("0.5"), sq, D(sp))),
            threshold=D("0.02"),
            fx_rate=D(rate),
            free_krw=D(krw),
            free_usd=D(usd),
            fees=FeeRates(),
        )
    )


def times(specs: list[StageSpec], due: dict[int, datetime]) -> list[tuple[str, str, str]]:
    return [
        (s.kind.value, s.market.value, due[s.seq].astimezone(KST).strftime("%m-%d %H:%M"))
        for s in specs
    ]


def test_kr_overweight_sell_fx_buy_on_one_day() -> None:
    specs = stage_specs(plan(120, "36360", 46, "62.40", "1380.6", "47675", "1.66"))
    assert [(s.kind, s.market, s.depends_on) for s in specs] == [
        (StageKind.SELL, StageMarket.KR, ()),
        (StageKind.FX, StageMarket.FX, (1,)),
        (StageKind.BUY, StageMarket.US, (2,)),
    ]
    due = schedule(specs, kst("2026-10-07 08:30"), SLOT)
    # 10/07 is in US daylight time: the US buy is at 22:30 KST.
    assert times(specs, due) == [
        ("sell", "KR", "10-07 09:05"),
        ("fx", "FX", "10-07 09:10"),
        ("buy", "US", "10-07 22:30"),
    ]


def test_first_day_korean_buy_does_not_wait_for_the_conversion() -> None:
    specs = stage_specs(plan(0, "32000", 0, "66.00", "1392.0", "10000000"))
    due = schedule(specs, kst("2026-07-01 08:30"), SLOT)
    assert times(specs, due) == [
        ("fx", "FX", "07-01 09:10"),
        ("buy", "KR", "07-01 09:05"),
        ("buy", "US", "07-01 22:30"),
    ]


def test_us_buy_after_standard_time_starts_at_2330() -> None:
    due = SLOT.slot_after(StageMarket.US, kst("2026-11-02 09:10"))
    assert due.astimezone(KST) == kst("2026-11-02 23:30")


def test_us_holiday_rolls_the_us_buy_to_the_next_session() -> None:
    # 2026-07-03 is a US holiday: Korea sells and converts that day, the buy waits for 7/6.
    assert SLOT.slot_after(StageMarket.US, kst("2026-07-03 09:10")).astimezone(KST) == kst(
        "2026-07-06 22:30"
    )


def test_korean_holiday_rolls_korean_and_fx_stages() -> None:
    assert SLOT.slot_after(StageMarket.KR, kst("2026-10-09 08:30")) == kst("2026-10-12 09:05")
    assert SLOT.slot_after(StageMarket.FX, kst("2026-10-09 08:30")) == kst("2026-10-12 09:10")


def test_us_overweight_converts_next_morning_and_buys_after_it() -> None:
    specs = stage_specs(plan(100, "30000", 40, "66.00", "1390.0", "0"))
    due = schedule(specs, kst("2026-10-07 08:30"), SLOT)
    assert times(specs, due) == [
        ("sell", "US", "10-07 22:30"),
        ("fx", "FX", "10-08 09:10"),
        ("buy", "KR", "10-08 09:15"),  # right after the conversion, not the next day's 09:05
    ]


def test_late_open_days_shift_korean_orders_and_fx() -> None:
    assert SLOT.nominal(StageMarket.KR, kst("2026-11-19 00:00").date()) == kst("2026-11-19 10:05")
    assert SLOT.nominal(StageMarket.FX, kst("2026-11-19 00:00").date()) == kst("2026-11-19 10:10")
    assert SLOT.nominal(StageMarket.FX, kst("2026-11-18 00:00").date()) == kst("2026-11-18 09:10")


def test_a_plan_made_by_the_0930_retry_runs_five_minutes_later() -> None:
    assert SLOT.slot_after(StageMarket.KR, kst("2026-10-07 09:30")) == kst("2026-10-07 09:35")
    assert SLOT.slot_after(StageMarket.FX, kst("2026-10-07 09:35")) == kst("2026-10-07 09:40")
    # Too late in the day: the next session.
    assert SLOT.slot_after(StageMarket.KR, kst("2026-10-07 15:25")) == kst("2026-10-08 09:05")


@pytest.mark.parametrize(
    ("market", "failed", "retry"),
    [
        (StageMarket.US, "2026-10-07 22:30", "2026-10-08 22:30"),  # §3 일부 실패: 다시 10/08 22:30
        (StageMarket.KR, "2026-09-14 09:05", "2026-09-15 09:05"),
        (StageMarket.KR, "2026-09-23 09:05", "2026-09-28 09:05"),  # over 추석
        (StageMarket.FX, "2026-10-08 09:10", "2026-10-12 09:10"),  # over 한글날 and the weekend
        (StageMarket.US, "2026-07-02 22:30", "2026-07-06 22:30"),  # over July 3
    ],
)
def test_retry_is_the_next_trading_day_at_the_same_time(
    market: StageMarket, failed: str, retry: str
) -> None:
    assert SLOT.retry_slot(market, kst(failed)) == kst(retry)
