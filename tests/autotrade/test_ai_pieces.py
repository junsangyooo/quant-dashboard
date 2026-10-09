"""Phase 2: the pieces under the AI flows — tax numbers (D36: inside the deduction, over it,
losses offsetting), cutting a long filing, and the data packets' field keys."""

from __future__ import annotations

import json
import sqlite3
from datetime import date
from decimal import Decimal

from autotrade.ai import packets as pk
from autotrade.ai.text import GAP, focus, keywords
from autotrade.db import ai_repo, repo
from autotrade.db.connection import transaction
from autotrade.domain.conditions import parse_condition
from autotrade.domain.instruments import Market
from autotrade.domain.tax import SoldLot, numbers, realized_in, tax_due
from autotrade.engine.tax import sold_lots, us_tax
from autotrade.jobs.ai_tasks import plan_job
from autotrade.jobs.tasks import JobContext, stage_job
from autotrade.rules.discovery import RULE_ID

from .fakes import World
from .helpers import kst
from .phase2 import pick_of, put_metric
from .test_discovery_plan import seed_prices

D = Decimal
RATE, DEDUCTION = D("0.22"), D(2500000)


# ── tax (D36) ────────────────────────────────────────────────────────────────────────────────


def test_tax_inside_the_deduction_over_it_and_losses() -> None:
    inside = numbers(2026, D(1000000), D(1000000), RATE, DEDUCTION)
    assert (inside.deduction_left_krw, inside.tax_if_sold_krw) == (D(1500000), D(0))
    over = numbers(2026, D(2000000), D(1000000), RATE, DEDUCTION)
    assert over.tax_if_sold_krw == D(110000)  # (3,000,000 - 2,500,000) x 22%
    # Selling at a loss offsets this year's gains: the tax already due goes down.
    loss = numbers(2026, D(3000000), D(-1000000), RATE, DEDUCTION)
    assert (loss.deduction_left_krw, loss.tax_if_sold_krw) == (D(0), D(-110000))
    # Earlier losses this year offset a gain now.
    offset = numbers(2026, D(-1000000), D(4000000), RATE, DEDUCTION)
    assert (offset.deduction_left_krw, offset.tax_if_sold_krw) == (D(2500000), D(110000))
    assert tax_due(D("2500001.9"), RATE, DEDUCTION) == D(0)  # floored to the won
    lots = [SoldLot(2026, D(100), D(70)), SoldLot(2025, D(10), D(90)), SoldLot(2026, D(5), D(15))]
    assert realized_in(lots, 2026) == D(20)


def test_this_year_s_foreign_gains_come_from_the_ledger_s_fills(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    for t in ("2026-07-02 08:25", "2026-07-02 09:10", "2026-07-08 08:25", "2026-07-08 22:25"):
        world.rate(kst(t), "1400.0")
    seed_prices(p2conn, world, ["2026-07-01", "2026-07-02"], "50")
    plan_job(p2ctx, "paper", kst("2026-07-02 08:40"))
    for t in ("09:05", "09:10", "22:30"):
        stage_job(p2ctx, "paper", kst(f"2026-07-02 {t}"))
    assert ai_repo.load_sleeve(p2conn, "paper", RULE_ID).qty_of("US:AVGO") == 1
    avgo = pick_of(p2conn, "US:AVGO")
    decided = kst("2026-07-08 08:35")
    with transaction(p2conn):
        ai_repo.update_pick(p2conn, avgo.pick_id, decided, decision="sell", decided_at=decided)
    seed_prices(p2conn, world, ["2026-07-06", "2026-07-07", "2026-07-08"], "50")
    world.bar("US:AVGO", "2026-07-08", close="60", open_="60")
    report = plan_job(p2ctx, "paper", kst("2026-07-08 08:40"))
    assert ["US:AVGO", 1] in [list(x) for x in report["sell"]]
    stage_job(p2ctx, "paper", kst("2026-07-08 22:30"))
    lots = sold_lots(p2conn, "paper")
    # Bought at $50 + $0.05 fee at 1,400 = 70,070; sold at $60 - $0.06 = $59.94 = 83,916.
    assert lots == [SoldLot(2026, D(83916), D(70070))]
    tax = us_tax(p2conn, p2ctx.cfg, "paper", 2026, D(0))
    assert (tax.realized_krw, tax.deduction_left_krw, tax.tax_if_sold_krw) == (
        D(13846),
        D(2486154),
        D(0),
    )


# ── cutting a long filing ────────────────────────────────────────────────────────────────────


def test_a_long_filing_keeps_its_head_and_the_lines_around_the_metrics() -> None:
    assert focus("짧은 글", ["매출"]) == "짧은 글"
    filler = [f"기타 사항 {i} " + "가" * 60 for i in range(400)]
    lines = ["반기보고서 표지", *filler[:100], "지상방산 부문 수주잔고는 38.3조원", *filler[100:]]
    text = "\n".join(lines)
    cut = focus(text, keywords(["segment_backlog:지상방산"]), limit=6000)
    assert len(cut) <= 6000
    assert cut.startswith("반기보고서 표지")
    assert "지상방산 부문 수주잔고는 38.3조원" in cut
    assert GAP.strip("\n") in cut
    words = keywords(["segment_revenue:엑스코프리 미국", "guidance:FY27 AI 매출 성장", "revenue"])
    assert {"엑스코프리 미국", "엑스코프리", "미국", "FY27", "매출", "revenue"} <= set(words)
    assert len(words) == len({w.lower() for w in words})


# ── packets ──────────────────────────────────────────────────────────────────────────────────


def test_conditions_in_words() -> None:
    cases = {
        '{"type":"level","metric":"op_margin","op":"<","value":7,"unit":"%"}': "이익률 < 7%",
        (
            '{"type":"level","metric":"revenue","change":"yoy","op":"<","value":10,"unit":"%",'
            '"periods":2}'
        ): "매출 전년 대비 증가율 < 10%, 2기 연속",
        '{"type":"level","metric":"revenue","change":"qoq","op":">=","value":5,"unit":"%"}': (
            "매출 직전 기간 대비 증가율 ≥ 5%"
        ),
        (
            '{"type":"level","metric":"operating_income","op":"<","value":450000000000,'
            '"unit":"KRW","period":"2026Q3"}'
        ): "영업이익 < 450000000000KRW (2026Q3)",
        '{"type":"level","metric":"guidance:신규 고객 수","op":">","value":3,"unit":"count"}': (
            "신규 고객 수 > 3"
        ),
        '{"type":"streak","metric":"backlog","change":"qoq","direction":"down","periods":2}': (
            "수주잔고이 직전 기간보다 줄어듦, 2기 연속"
        ),
        '{"type":"streak","metric":"revenue","change":"yoy","direction":"up","periods":1}': (
            "매출이 전년 같은 기간보다 늘어남, 1기 연속"
        ),
        '{"type":"event","kind":"capex_cut","text":"설비투자 축소"}': "사건: 설비투자 축소",
        '{"type":"price","op":"<=","value":74100}': "종가 ≤ 74100",
        '{"type":"valuation","metric":"per_fwd","op":"<=","value":15}': "per_fwd ≤ 15",
    }
    for text, words in cases.items():
        assert pk.describe(parse_condition(json.loads(text))) == words
    assert pk.num(None) == "모름"
    assert pk.num(D("12.50")) == "12.50"
    assert pk.num(D("1E+3")) == "1000"
    assert pk.pct(None) == "모름"
    assert pk.clean({"a": 1, "b": None}) == {"a": 1}


def test_packets_carry_every_number_with_its_key(
    p2ctx: JobContext, p2conn: sqlite3.Connection, world: World
) -> None:
    ocean = pick_of(p2conn, "KR:042660")
    inst = repo.get_instrument(p2conn, "KR:042660")
    put_metric(p2conn, "KR:042660", "revenue", "2026Q2", "3000000000000", "KRW")
    put_metric(p2conn, "KR:042660", "operating_income", "2026Q2", "150000000000", "KRW")
    with transaction(p2conn):
        fid, _ = ai_repo.insert_filing(
            p2conn,
            instrument_id="KR:042660",
            source="dart",
            source_ref="R1",
            form="반기보고서",
            items=None,
            title="반기보고서 (2026.06)",
            filed_on=date(2026, 8, 14),
            url=None,
            kind="earnings",
            status="done",
            at=kst("2026-10-12 08:00"),
        )
        ai_repo.upsert_metric_value(
            p2conn,
            instrument_id="KR:042660",
            metric="net_income",
            period="2026Q2",
            value=D("100000000000"),
            unit="KRW",
            filing_id=fid,
            quote="순이익 1,000억",
            source="extract",
            call_id=None,
            at=kst("2026-10-12 08:00"),
        )
    rows = "\n".join(pk.metric_rows(p2conn, "KR:042660"))
    assert "| metric.op_margin.2026Q2 | 5 | % | 계산 |" in rows
    assert (
        "| metric.net_income.2026Q2 | 100000000000 | KRW | 반기보고서 (2026.06) 2026-08-14 |"
        in rows
    )
    assert "| metric.revenue.2026Q2 | 3000000000000 | KRW | test |" in rows
    assert pk.metric_rows(p2conn, "KR:000000")[-1].startswith("| (없음)")
    world.series("042660.KS", Market.KR, "2026-08-03", "2026-10-12", lambda i, d: str(100 + i))
    world.series("069500.KS", Market.KR, "2026-08-03", "2026-10-12", "100")
    world.valuations["042660.KS"] = {"per_fwd": D("12.345")}
    quotes = pk.quotes_for_pick(p2ctx.sources, ocean, inst, date(2026, 10, 12))
    prices = "\n".join(pk.price_rows(ocean, inst, quotes))
    assert "| now.close |" in prices
    assert "| now.return_20d_pct |" in prices
    assert "| now.per_fwd | 12.35 |" in prices
    assert "| now.excess_since_pick_pp |" in prices
    empty = pk.Quotes()
    assert pk.price_rows(ocean, inst, empty)[-1] == "| now.close | 모름 (시세를 받지 못함) |"
    assert "## 지금 보유 (3년 발굴)" in pk.sleeve_rows(p2conn, "paper")[0]
    assert pk.filing_rows(p2conn, "KR:042660", date(2026, 10, 12))[1].startswith(
        "- 2026-08-14 · DART"
    )
