"""'3년 발굴' in the live ledger (유준상 2026-10-15: 실전도 지수 반반 80 · 3년 발굴 20,
모의의 발굴 종목 15개를 실전에도): the `live-discovery` command, nothing ordered while live
is off, and the first live day against the fake Toss with the account as it was on 10-13
(499,975원 · $363.79).

The 20% is about 100,000원 and $72.75: the same amount per pick is about 13,000원, dearer than
one share of every pick, so the rule's won wait in one KOSPI200 ETF share and its dollars, less
than one SPYM share, wait as cash. '지수 반반' plans the other 80% as before (D47: per currency).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import date
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path
from typing import Any

import pytest

from autotrade.db import ai_repo, live_repo, repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency, Market
from autotrade.engine import discovery_plan, live, sleeves
from autotrade.engine import watch as watch_engine
from autotrade.engine.common import new_money_of_rule, new_money_waiting
from autotrade.engine.rebuild import verify_ledger
from autotrade.engine.sleeves import verify_sleeves
from autotrade.jobs.cli import main
from autotrade.jobs.tasks import live_discovery_job
from autotrade.rules.discovery import RULE_ID
from autotrade.rules.index_half import RULE_ID as INDEX

from .fakes import KR, US, World
from .helpers import kst
from .live_world import Live, make_live

D = Decimal
KODEX_CLOSE = "94805"
SPYM_CLOSE = "90.58"
RATE = "1343.6"
# The 10-14 closes of the 15 picks (the server's market_prices, 2026-10-15).
PICK_CLOSES = {
    "KR:012450": "842000",
    "KR:009540": "276000",
    "KR:042660": "67400",
    "KR:267260": "543000",
    "KR:068270": "179800",
    "KR:326030": "70300",
    "KR:003230": "1143000",
    "KR:071050": "157500",
    "US:AVGO": "346.25",
    "US:TSM": "430.00",
    "US:AMZN": "254.08",
    "US:LLY": "1208.74",
    "US:MTZ": "194.46",
    "US:MOD": "157.75",
    "US:HII": "264.53",
}
SESSIONS = (
    "2026-10-12",
    "2026-10-13",
    "2026-10-14",
    "2026-10-15",
    "2026-10-16",
    "2026-10-19",
    "2026-10-20",
)


def october(world: World) -> None:
    """The ETFs and the picks at their 10-14 closes, every session of the week; the rate."""
    world.bars.clear()
    world.rates.clear()
    for d in SESSIONS:
        world.bar(KR, d, close=KODEX_CLOSE, open_=KODEX_CLOSE)
        world.bar(US, d, close=SPYM_CLOSE, open_=SPYM_CLOSE)
        for iid, close in PICK_CLOSES.items():
            world.bar(iid, d, close=close, open_=close)
    for d in ("10-14", "10-15", "10-16", "10-19", "10-20"):
        for hm in ("08:25", "16:00", "22:25"):
            world.rate(kst(f"2026-{d} {hm}"), RATE)
    # Flat adjusted closes for the watch's 'vs index' line and its shock scan.
    for symbol, market in (("069500.KS", Market.KR), ("SPY", Market.US)):
        world.series(symbol, market, "2026-08-01", "2026-10-16", "100")
    for iid in PICK_CLOSES:
        market = Market.KR if iid.startswith("KR:") else Market.US
        symbol = iid.split(":")[1] + (".KS" if market is Market.KR else "")
        world.series(symbol, market, "2026-08-01", "2026-10-16", "100")


@pytest.fixture
def lw(tmp_path: Path, world: World, monkeypatch: pytest.MonkeyPatch) -> Iterator[Live]:
    monkeypatch.setenv("AUTOTRADE_LIVE_ORDERS", "1")
    for holder in make_live(tmp_path, world):
        october(world)
        holder.clock[0] = kst("2026-10-15 20:00")
        holder.fake.cash = {"KRW": D("499975"), "USD": D("363.79")}
        holder.fake.prices = {"069500": D(KODEX_CLOSE), "SPYM": D(SPYM_CLOSE)}
        holder.fake.prices.update({iid.split(":")[1]: D(c) for iid, c in PICK_CLOSES.items()})
        holder.fake.rate = D(RATE)
        yield holder


def decide(lw: Live, pct: int = 20, *, yes: bool = True) -> dict[str, Any]:
    return live_discovery_job(lw.ctx, lw.now(), pct=pct, yes=yes)


def sleeve(lw: Live) -> Any:
    return ai_repo.load_sleeve(lw.conn, "live", RULE_ID)


# ── the command ──────────────────────────────────────────────────────────────────────────────


def test_the_command_shows_first_then_writes_once(lw: Live) -> None:
    paper = ai_repo.picks_of(lw.conn, "paper", RULE_ID)
    assert len(paper) == 15
    with transaction(lw.conn):  # the paper ledger's judgment so far: carried over
        ai_repo.update_pick(lw.conn, paper[2].pick_id, lw.now(), last_verdict="hold", weak_months=1)
    shares_before = ai_repo.shares(lw.conn, "live")

    shown = decide(lw, yes=False)
    assert shown["result"] == "preview"
    assert shown["shares"] == {
        "before": {INDEX: "100", RULE_ID: "0"},
        "after": {INDEX: "80", RULE_ID: "20"},
    }
    assert len(shown["copy"]) == 15
    assert shown["apply"] == "python -m autotrade.jobs live-discovery --pct 20 --yes"
    # Nothing was written.
    assert ai_repo.shares(lw.conn, "live") == shares_before
    assert ai_repo.picks_of(lw.conn, "live", RULE_ID) == []

    done = decide(lw)
    assert done["result"] == "applied"
    assert len(done["new_picks"]) == 15
    assert ai_repo.shares(lw.conn, "live") == {INDEX: D(80), RULE_ID: D(20)}
    copies = {p.instrument_id: p for p in ai_repo.picks_of(lw.conn, "live", RULE_ID)}
    for p in paper:
        c = copies[p.instrument_id]
        # The judgment comes along as it stands...
        for name in (
            "status",
            "picked_on",
            "picked_price",
            "benchmark",
            "benchmark_price",
            "theme",
            "rationale",
            "confirm",
            "invalidate",
            "buy",
            "texts",
            "confidence",
            "source",
            "note",
        ):
            assert getattr(c, name) == getattr(p, name), (p.instrument_id, name)
        # ...and none of the paper ledger's money or pending decisions.
        assert c.decision is None
        assert c.decision_task_id is None
        assert c.closed_on is None
    assert (
        copies[paper[2].instrument_id].last_verdict,
        copies[paper[2].instrument_id].weak_months,
    ) == (
        "hold",
        1,
    )
    assert repo.load_state(lw.conn, "live").positions == {}
    assert sleeves.sleeve_rule_ids(lw.conn, "live") == [RULE_ID]
    assert ai_repo.sleeve_rules(lw.conn, "live") == []  # no money yet: it comes at the start
    assert [r.result for r in ai_repo.job_runs_of(lw.conn, "live-discovery", "live")] == ["applied"]

    again = decide(lw)
    assert again["result"] == "nothing-to-do"
    assert [s["why"] for s in again["skipped"]] == ["in-live-already"] * 15
    assert len(ai_repo.picks_of(lw.conn, "live", RULE_ID)) == 15


def test_the_command_leaves_out_a_pick_paper_is_selling(lw: Live) -> None:
    pick = ai_repo.picks_of(lw.conn, "paper", RULE_ID)[0]
    with transaction(lw.conn):
        ai_repo.update_pick(lw.conn, pick.pick_id, lw.now(), decision="sell")
    out = decide(lw)
    assert [(s["instrument_id"], s["why"]) for s in out["skipped"]] == [
        (pick.instrument_id, "selling-in-paper")
    ]
    assert ai_repo.open_pick(lw.conn, "live", RULE_ID, pick.instrument_id) is None
    assert len(ai_repo.picks_of(lw.conn, "live", RULE_ID)) == 14


def test_the_command_refuses_a_started_live_ledger(lw: Live) -> None:
    lw.turn_on("2026-10-15 21:00")
    out = decide(lw)
    assert (out["result"], out["reason"]) == ("refused", "live-started")
    assert ai_repo.shares(lw.conn, "live") == {INDEX: D(100), RULE_ID: D(0)}
    assert decide(lw, 120)["reason"] == "bad-pct"


def test_the_cli_previews_and_applies(lw: Live, tmp_path: Path) -> None:
    lines: list[str] = []
    env = {"AUTOTRADE_DB": str(lw.cfg.db_path)}
    at = ["--at", "2026-10-15T20:00"]
    assert main(["live-discovery", "--pct", "20", *at], env=env, out=lines.append) == 0
    assert json.loads(lines[-1])["result"] == "preview"
    assert main(["live-discovery", "--pct", "20", "--yes", *at], env=env, out=lines.append) == 0
    applied = json.loads(lines[-1])
    assert applied["result"] == "applied"
    # The estimate from the latest Toss snapshot (none yet in this database).
    assert applied["estimate"] is None
    with pytest.raises(SystemExit):
        main(["status", "--pct", "20"], env=env, out=lines.append)


def test_the_estimate_reads_the_last_toss_snapshot(lw: Live) -> None:
    lw.sync("2026-10-15 20:00")
    lw.market_data()
    est = decide(lw, yes=False)["estimate"]
    assert est["rule_cash_at_start"] == {"KRW": D("99995"), "USD": D("72.75")}
    # 99,995 + $72.75 x 1,343.6 = 197,741 won over 15 picks.
    assert est["per_pick_krw"] == D("13183")
    assert est["one_share_fits"] == []
    assert len(est["one_share_dearer"]) == 15


# ── live off: nothing moves ──────────────────────────────────────────────────────────────────


def test_while_live_is_off_nothing_is_planned_or_asked(lw: Live) -> None:
    decide(lw)
    for t in ("2026-10-16 08:30", "2026-10-16 09:05", "2026-10-16 22:30", "2026-11-02 08:30"):
        lw.tick(t)
    assert repo.start_event(lw.conn, "live") is None
    assert repo.orders_of_ledger(lw.conn, "live") == []
    assert repo.plans_of_ledger(lw.conn, "live") == []
    assert [t for t in ai_repo.tasks_of(lw.conn) if t.ledger_id == "live"] == []
    assert lw.fake.ours() == []


def test_turned_off_after_the_start_the_rule_rests_too(lw: Live) -> None:
    decide(lw)
    lw.turn_on("2026-10-15 21:00")
    lw.turn_off("2026-10-15 22:00")
    lines = lw.tick("2026-10-16 08:30")
    assert {line["task"] for line in lines} <= {"broker", "reconcile", "stages"}
    assert list(repo.plans_of_ledger(lw.conn, "live")) == []
    assert ai_repo.job_runs_of(lw.conn, watch_engine.JOB, "live") == []


# ── the first live day ───────────────────────────────────────────────────────────────────────


def test_the_preview_shows_both_rules_first_orders(lw: Live) -> None:
    decide(lw)
    lw.sync("2026-10-15 21:00")
    data = lw.preview()
    orders = [(o.side.value, o.instrument.instrument_id, o.qty) for o in data.plan.buys]
    # '지수 반반' 80%: 399,980원 -> 4 x 95,289 (limit 95,275 + fee); $291.04 -> 3 x $91.12.
    # '3년 발굴' 20%: no pick fits 13,183원; 99,995원 -> 1 ETF share, $72.75 < one SPYM.
    assert orders == [
        ("buy", "KR:069500", 4),
        ("buy", "US:SPYM", 3),
        ("buy", "KR:069500", 1),
    ]
    # The account as it is, not a rule's part of it.
    assert [(label, krw) for label, _, krw in data.current] == [
        ("krw-cash", D("499975")),
        ("usd-cash", D("488788")),
    ]


def test_the_first_live_day(lw: Live) -> None:
    decide(lw)
    lw.turn_on("2026-10-15 21:00")
    start = repo.start_event(lw.conn, "live")
    assert start is not None
    # The start gives '3년 발굴' its 20% of each currency.
    ai = sleeve(lw)
    assert (ai.cash_of(Currency.KRW), ai.cash_of(Currency.USD)) == (D("99995"), D("72.75"))
    assert ai.positions == {}

    first = lw.tick("2026-10-16 08:30")
    tasks = [(line["task"], line["result"]) for line in first]
    assert ("check", "rebalance") in tasks
    assert ("ai-plan", "planned") in tasks
    # One judgment: the live turn watches nothing and queues nothing for the AI.
    assert not {"watch", "ai-queue"} & {task for task, _ in tasks}
    plans = {p.rule_id: p for p in repo.plans_of_ledger(lw.conn, "live")}
    assert set(plans) == {INDEX, RULE_ID}
    by_rule = {
        rule: sorted(
            (o.instrument_id, o.side, o.qty) for o in repo.orders_of_plan(lw.conn, plan.plan_id)
        )
        for rule, plan in plans.items()
    }
    assert by_rule == {
        INDEX: [("KR:069500", "buy", 4), ("US:SPYM", "buy", 3)],
        RULE_ID: [("KR:069500", "buy", 1)],
    }
    run = ai_repo.job_runs_of(lw.conn, discovery_plan.JOB, "live")[-1]
    assert run.details["per_pick_krw"] == "13183"
    assert run.details["buy"] == [["KR:069500", 1]]
    assert run.details["fx"] is None  # never a conversion in the live ledger (D47)
    assert run.details["waiting"] == []

    # 09:05: both Korean buys go to Toss (limit 95,275, filled at the close).
    lw.fake.slip = D("470")
    lw.tick("2026-10-16 09:05")
    lw.tick("2026-10-16 09:10")
    assert [(o.symbol, o.quantity) for o in lw.fake.ours()] == [
        ("069500", D(4)),
        ("069500", D(1)),
    ]
    ai = sleeve(lw)
    assert ai.qty_of("KR:069500") == 1
    assert ai.cash_of(Currency.KRW) == D("99995") - D("94805") - D("14")
    assert ai.cash_of(Currency.USD) == D("72.75")

    # 22:30: '지수 반반''s three SPYM; the rule's dollars wait.
    lw.fake.slip = D("0.45")
    lw.tick("2026-10-16 22:30")
    lw.tick("2026-10-16 22:35")
    assert [(o.symbol, o.quantity) for o in lw.fake.ours()][-1] == ("SPYM", D(3))
    lw.sync("2026-10-16 23:00")
    lw.reconcile("2026-10-16 23:00")
    state = repo.load_state(lw.conn, "live")
    assert state.qty_of("KR:069500") == 5
    assert state.qty_of("US:SPYM") == 3
    assert state.cash_of(Currency.KRW) == lw.fake.cash["KRW"]
    assert state.cash_of(Currency.USD) == lw.fake.cash["USD"]
    assert sleeves.base_view(lw.conn, "live").qty_of("KR:069500") == 4
    assert verify_ledger(lw.conn, "live") == []
    assert verify_sleeves(lw.conn, "live") == []
    assert lw.status().reconcile_state == "match"
    # No AI was asked on the first day: no filing, no metric, no shock in this market.
    assert [t for t in ai_repo.tasks_of(lw.conn) if t.ledger_id == "live"] == []

    # The next morning: nothing new to plan (no pick fits, the cash under one share).
    lw.tick("2026-10-19 08:30")
    plans_after = [p for p in repo.plans_of_ledger(lw.conn, "live") if p.rule_id == RULE_ID]
    assert len(plans_after) == 1


def test_no_live_buy_of_a_company_the_owner_holds_himself(lw: Live) -> None:
    decide(lw)
    lw.fake.cash["KRW"] = D("50000000")
    lw.fake.hold("042660", D("10"), D("60000"), name="한화오션")  # his, outside the rules
    lw.turn_on("2026-10-15 21:00")
    lw.tick("2026-10-16 08:30")
    run = ai_repo.job_runs_of(lw.conn, discovery_plan.JOB, "live")[-1]
    assert run.details["outside_held"] == ["KR:042660"]
    bought = {iid for iid, _ in run.details["buy"]}
    assert "KR:042660" not in bought
    # 10,000,000 over 15 picks: the Korean picks under 666,666원 a share are bought.
    assert {"KR:009540", "KR:068270", "KR:326030", "KR:071050"} <= bought


# ── the owner's money with two rules in the live ledger ──────────────────────────────────────


def started(lw: Live) -> None:
    """Turned on 10-15 evening; the first day's Korean and US orders filled at the closes."""
    decide(lw)
    lw.turn_on("2026-10-15 21:00")
    lw.fake.slip = D("470")
    lw.tick("2026-10-16 08:30")
    lw.tick("2026-10-16 09:05")
    lw.tick("2026-10-16 09:10")
    lw.fake.slip = D("0.45")
    lw.tick("2026-10-16 22:30")
    lw.tick("2026-10-16 22:35")


def test_his_conversion_moves_no_money_between_the_rules(lw: Live) -> None:
    started(lw)
    ai_before = sleeve(lw)
    assert ai_before.cash_of(Currency.KRW) == D("5176")  # left after its one ETF share
    won = lw.fake.cash["KRW"]
    assert won == D("25879")  # 499,975 - 4 x 94,805 - 56 - 94,805 - 14
    # He converts all the won left into dollars (D47's suggestion), at 1,344.6.
    usd = (won / D("1344.6")).quantize(D("0.01"), rounding=ROUND_FLOOR)
    lw.fake.convert(won, usd)
    lw.sync("2026-10-17 10:00")
    out = lw.reconcile("2026-10-17 10:00")
    assert lw.status().reconcile_state == "match", out
    ai = sleeve(lw)
    # By the shares the rule would give 5,175원; '지수 반반' holds 20,703원 and cannot pay the
    # other 20,704, so the rule gives all its 5,176원, and gets the same part of the dollars.
    assert ai.cash_of(Currency.KRW) == 0
    assert sleeves.base_view(lw.conn, "live").cash_of(Currency.KRW) == 0
    got = ai.cash_of(Currency.USD) - ai_before.cash_of(Currency.USD)
    assert got == (usd * D("5176") / won).quantize(D("0.01"), rounding=ROUND_FLOOR)
    assert verify_sleeves(lw.conn, "live") == []
    assert verify_ledger(lw.conn, "live") == []


def test_a_withdrawal_bigger_than_the_rules_cash_share_does_not_stop_the_account(lw: Live) -> None:
    started(lw)
    ai_won = sleeve(lw).cash_of(Currency.KRW)
    base_won = sleeves.base_view(lw.conn, "live").cash_of(Currency.KRW)
    # He takes out all the won the account has left: 20% of it is more than the rule's cash.
    total = lw.fake.cash["KRW"]
    assert total * D("0.2") > ai_won or base_won < total
    lw.fake.withdraw("KRW", total)
    lw.sync("2026-10-17 10:00")
    out = lw.reconcile("2026-10-17 10:00")
    assert lw.status().reconcile_state == "match", out
    assert sleeve(lw).cash_of(Currency.KRW) == 0
    assert sleeves.base_view(lw.conn, "live").cash_of(Currency.KRW) == 0
    assert verify_sleeves(lw.conn, "live") == []


def test_his_new_money_waits_a_day_in_each_rule(lw: Live) -> None:
    started(lw)
    lw.fake.deposit("KRW", D("1000000"))
    lw.sync("2026-10-17 10:00")
    lw.reconcile("2026-10-17 10:00")
    at = kst("2026-10-17 10:05")
    assert new_money_waiting(lw.conn, "live", at) == {Currency.KRW: D("1000000")}
    assert new_money_of_rule(lw.conn, "live", RULE_ID, at) == {Currency.KRW: D("200000")}
    assert new_money_of_rule(lw.conn, "live", INDEX, at) == {Currency.KRW: D("800000")}


def test_adopting_the_broker_never_leaves_less_than_the_rules_part(lw: Live) -> None:
    started(lw)
    # The account shows four fewer ETF shares with no trade listed (moved out of the account):
    # '지수 반반' holds four, the rule one; adopting would take shares only the rule holds.
    lw.fake.holdings["069500"].qty -= D(5)
    lw.sync("2026-10-17 10:00")
    out = lw.reconcile("2026-10-17 10:00")
    assert (out["result"], out["reason"]) == ("mismatch", "positions"), out
    with transaction(lw.conn):
        adopted = live.adopt_broker(lw.conn, lw.cfg, lw.now(), "moved out")
    assert adopted["result"] == "refused"
    assert adopted["reason"].startswith("sleeves:")
    assert repo.load_state(lw.conn, "live").qty_of("KR:069500") == 5  # nothing was written


# ── the audit of 2026-10-15 (each finding reproduced first) ─────────────────────────────────


def rich(lw: Live) -> None:
    """5천만 원 · $5,000: the rule's 20% buys one share of most Korean picks."""
    decide(lw)
    lw.fake.cash["KRW"] = D("50000000")
    lw.fake.cash["USD"] = D("5000")
    lw.turn_on("2026-10-15 21:00")
    lw.tick("2026-10-16 08:30")


def opens_higher(lw: Live, pct: str = "1.03") -> None:
    for iid, close in PICK_CLOSES.items():
        if iid.startswith("KR:"):
            lw.fake.prices[iid.split(":")[1]] = (D(close) * D(pct)).quantize(D(1))
    lw.fake.prices["069500"] = (D(KODEX_CLOSE) * D(pct)).quantize(D(1))


def test_audit_1_buys_sent_together_never_spend_the_rules_cash_twice(lw: Live) -> None:
    rich(lw)
    opens_higher(lw)  # every Korean quote 3% over the close the plan used
    lines = lw.tick("2026-10-16 09:05") + lw.tick("2026-10-16 09:10")
    assert [line for line in lines if line.get("result") == "failed"] == []
    ai = sleeve(lw)
    assert ai.cash_of(Currency.KRW) >= 0
    # The last buy (the index ETF that holds the rest) took what the earlier ones left.
    sent = [(o.symbol, o.quantity) for o in lw.fake.ours() if o.symbol == "069500"]
    assert sent[-1][1] < 68
    assert lw.status().reconcile_state == "match"
    assert verify_sleeves(lw.conn, "live") == []
    assert verify_ledger(lw.conn, "live") == []


def test_audit_1_a_fill_the_rule_cannot_pay_stops_sending_until_adopted(lw: Live) -> None:
    decide(lw)
    lw.turn_on("2026-10-15 21:00")
    lw.tick("2026-10-16 08:30")
    lw.fake.fill_mode = "open"
    lw.tick("2026-10-16 09:05")  # both Korean buys go out and wait at Toss
    index_order, rule_order = lw.fake.ours()
    lw.fake.fill_open(index_order.order_id, price=D(KODEX_CLOSE))
    # The rule's one share fills 6,000원 over its limit (it never should): its 5,176원 left
    # cannot pay that.
    assert rule_order.price is not None
    lw.fake.fill_open(rule_order.order_id, price=rule_order.price + D("6000"))
    lines = lw.tick("2026-10-16 09:10")
    assert [line for line in lines if line.get("result") == "failed"] == []
    assert lw.status().reconcile_state == "mismatch"
    assert lw.status().reconcile_detail["reason"] == "rule-cash"
    sent = len(lw.fake.ours())
    lw.fake.fill_mode = "fill"
    lw.tick("2026-10-16 22:30")
    lw.tick("2026-10-16 22:35")
    assert len(lw.fake.ours()) == sent  # the US orders do not go out on a mismatch
    lw.sync("2026-10-17 10:00")
    with transaction(lw.conn):
        adopted = live.adopt_broker(lw.conn, lw.cfg, lw.now(), "fills checked")
    assert adopted["result"] in ("adopted", "nothing-to-adopt"), adopted
    assert adopted.get("lateFills")
    lw.reconcile("2026-10-17 10:00")
    assert lw.status().reconcile_state == "match"
    assert sleeve(lw).cash_of(Currency.KRW) == 0  # '지수 반반' covered the rest
    assert verify_sleeves(lw.conn, "live") == []
    assert verify_ledger(lw.conn, "live") == []


def test_audit_2_his_sale_of_a_pick_is_the_rules_sale(lw: Live) -> None:
    rich(lw)
    lw.tick("2026-10-16 09:05")
    lw.tick("2026-10-16 09:10")
    held = sleeve(lw).qty_of("KR:042660")
    assert held > 3
    cash_before = sleeve(lw).cash_of(Currency.KRW)
    lw.at("2026-10-16 10:00")
    lw.fake.app_trade("042660", "SELL", D(3), D("67400"), commission=D("30"))
    lw.sync("2026-10-16 10:05")
    lw.reconcile("2026-10-16 10:05")
    assert lw.status().reconcile_state == "match"
    assert sleeve(lw).qty_of("KR:042660") == held - 3
    assert sleeve(lw).cash_of(Currency.KRW) == cash_before + 3 * D("67400") - D("30")
    assert live_pick(lw, "KR:042660").status == "held"
    # He sells the rest: the pick closes and is not bought back on the same judgment.
    lw.at("2026-10-16 10:30")
    lw.fake.app_trade("042660", "SELL", D(held - 3), D("67400"), commission=D("60"))
    lw.sync("2026-10-16 10:35")
    lw.reconcile("2026-10-16 10:35")
    assert lw.status().reconcile_state == "match"
    assert live_pick(lw, "KR:042660").status == "sold"
    assert live_pick(lw, "KR:042660").closed_reason == "owner-app"
    lw.tick("2026-10-19 08:30")
    assert ai_repo.open_pick(lw.conn, "live", RULE_ID, "KR:042660") is None
    bought = [o for o in repo.orders_of_ledger(lw.conn, "live") if o.instrument_id == "KR:042660"]
    assert all(o.plan_id == bought[0].plan_id for o in bought)  # only the first day's buy
    assert verify_sleeves(lw.conn, "live") == []
    assert verify_ledger(lw.conn, "live") == []


def test_audit_2_his_sale_beyond_the_long_term_rules_etf_takes_the_rules_share(lw: Live) -> None:
    started(lw)  # '지수 반반' 4 ETF shares, '3년 발굴' 1
    lw.fake.app_trade("069500", "SELL", D("5"), D(KODEX_CLOSE), commission=D("71"))
    lw.sync("2026-10-17 10:00")
    lw.reconcile("2026-10-17 10:00")
    assert lw.status().reconcile_state == "match"
    assert sleeves.base_view(lw.conn, "live").qty_of("KR:069500") == 0
    assert sleeve(lw).qty_of("KR:069500") == 0
    assert verify_sleeves(lw.conn, "live") == []
    assert verify_ledger(lw.conn, "live") == []


def test_audit_3_his_buy_of_a_pick_stays_his(lw: Live) -> None:
    rich(lw)
    lw.tick("2026-10-16 09:05")
    lw.tick("2026-10-16 09:10")
    held_before = sleeve(lw).qty_of("KR:042660")
    lw.at("2026-10-16 10:00")
    lw.fake.deposit("KRW", D("1000000"))
    lw.fake.app_trade("042660", "BUY", D(2), D("67400"), commission=D("20"))
    lw.sync("2026-10-16 10:05")
    lw.reconcile("2026-10-16 10:05")
    assert lw.status().reconcile_state == "match"
    held = sleeve(lw).qty_of("KR:042660")
    assert held == held_before > 0
    assert sleeves.base_view(lw.conn, "live").qty_of("KR:042660") == 0
    assert repo.load_state(lw.conn, "live").qty_of("KR:042660") == held  # his 2 are outside
    with transaction(lw.conn):
        adopted = live.adopt_broker(lw.conn, lw.cfg, lw.now(), "mine")
    assert adopted["result"] == "nothing-to-adopt"
    # He sells his two: outside money, the rule keeps its nine.
    lw.at("2026-10-16 11:00")
    lw.fake.app_trade("042660", "SELL", D(2), D("67500"), commission=D("20"))
    lw.sync("2026-10-16 11:05")
    lw.reconcile("2026-10-16 11:05")
    assert lw.status().reconcile_state == "match"
    assert sleeve(lw).qty_of("KR:042660") == held
    assert verify_sleeves(lw.conn, "live") == []
    assert verify_ledger(lw.conn, "live") == []


def test_audit_4_no_rule_plan_on_an_account_not_matched_lately(lw: Live) -> None:
    decide(lw)
    lw.turn_on("2026-10-15 21:00")
    first = lw.tick("2026-10-16 08:30")
    assert ("ai-plan", "planned") in [(line["task"], line["result"]) for line in first]
    with transaction(lw.conn):
        status = lw.status()
        live_repo.save_status(
            lw.conn, replace(status, reconcile_state="busy"), kst("2026-10-19 08:31")
        )
    from autotrade.jobs.schedule import live_checked_today

    assert not live_checked_today(lw.conn, lw.cfg, kst("2026-10-16 08:40"))


def test_audit_5_the_rule_waits_for_the_first_check_that_read_the_account(lw: Live) -> None:
    decide(lw)
    lw.turn_on("2026-10-15 21:00")
    # The Korean close of 10-15 never came: the check waits for quotes.
    for iid in [KR, *PICK_CLOSES]:
        lw.world.remove_bar(iid, "2026-10-15")
    with transaction(lw.conn):
        lw.conn.execute("DELETE FROM market_prices WHERE session_date = '2026-10-15'")
    lines = lw.tick("2026-10-16 08:30")
    tasks = [(line["task"], line["result"]) for line in lines]
    assert ("check", "quote-wait") in tasks
    assert not [t for t in tasks if t[0] == "ai-plan"]
    assert repo.plans_of_ledger(lw.conn, "live") == []


# ── one judgment, the paper ledger's ────────────────────────────────────────────────────────


def judged(lw: Live, iid: str, **fields: Any) -> None:
    """The paper ledger's AI decides something about one of its picks."""
    pick = ai_repo.open_pick(lw.conn, "paper", RULE_ID, iid)
    assert pick is not None
    with transaction(lw.conn):
        ai_repo.update_pick(lw.conn, pick.pick_id, lw.now(), **fields)


def live_pick(lw: Live, iid: str) -> ai_repo.PickRow:
    rows = [p for p in ai_repo.picks_of(lw.conn, "live", RULE_ID) if p.instrument_id == iid]
    assert rows, iid
    return rows[-1]


def test_the_live_ledger_asks_the_ai_nothing_and_follows_the_paper_judgment(lw: Live) -> None:
    lw.fake.cash["KRW"] = D("50000000")  # enough for one share of most Korean picks
    started(lw)
    owned = sleeves.view(lw.conn, "live", RULE_ID).positions
    assert {"KR:042660", "KR:326030"} <= set(owned)

    # A month of paper judgments: a rewritten sell condition and a 'weak' verdict, then two
    # '반증' on 한화오션 (sell), a candidate that expires, a new pick confirmed by its buy check.
    new_cond = [{"type": "level", "metric": "op_margin", "op": "<", "value": "5"}]
    judged(lw, "KR:009540", invalidate=new_cond, last_verdict="weaken", weak_months=1)
    judged(lw, "KR:042660", decision="sell", decided_at=lw.now())
    lines = lw.tick("2026-10-17 10:00")
    follow = [line for line in lines if line["task"] == "follow"]
    assert len(follow) == 1
    assert follow[0]["changes"] == {"updated": ["KR:009540"], "sell": ["KR:042660"]}
    assert live_pick(lw, "KR:009540").invalidate == new_cond
    assert live_pick(lw, "KR:009540").weak_months == 1
    assert live_pick(lw, "KR:042660").decision == "sell"
    assert lw.tick("2026-10-17 10:05") == []  # nothing new: nothing written

    # The next morning the live ledger sells its own 한화오션 shares (its money, its count).
    lw.tick("2026-10-19 08:30")
    sells = [
        (o.instrument_id, o.qty) for o in repo.orders_of_ledger(lw.conn, "live") if o.side == "sell"
    ]
    assert sells == [("KR:042660", owned["KR:042660"].qty)]
    lw.tick("2026-10-19 09:05")
    lw.tick("2026-10-19 09:10")
    lw.tick("2026-10-20 08:30")  # the planner closes the pick once its shares are gone
    assert live_pick(lw, "KR:042660").status == "sold"
    # Paper has not sold yet: the live ledger does not take the company back in meanwhile.
    assert ai_repo.open_pick(lw.conn, "live", RULE_ID, "KR:042660") is None

    # Never an AI task of the live ledger, whatever happened.
    assert [t for t in ai_repo.tasks_of(lw.conn) if t.ledger_id == "live"] == []
    assert ai_repo.job_runs_of(lw.conn, watch_engine.JOB, "live") == []


def test_a_pick_paper_sold_or_added_reaches_the_live_ledger(lw: Live) -> None:
    started(lw)
    # Paper sold 셀트리온 (the live ledger never held it): the live pick closes.
    judged(lw, "KR:068270", status="sold", closed_on=date(2026, 10, 16))
    # Paper's quarterly discovery added a candidate and confirmed another into a held pick.
    with transaction(lw.conn):
        paper = ai_repo.open_pick(lw.conn, "paper", RULE_ID, "KR:071050")
        assert paper is not None
        for iid, status in (("KR:000660", "candidate"), ("KR:005930", "held")):
            repo.upsert_instrument(
                lw.conn,
                replace(
                    repo.get_instrument(lw.conn, "KR:071050"),
                    instrument_id=iid,
                    ticker=iid[3:],
                    name=iid,
                    yahoo_symbol=f"{iid[3:]}.KS",
                ),
                lw.now(),
            )
            ai_repo.insert_pick(
                lw.conn,
                ai_repo.NewPick(
                    ledger_id="paper",
                    rule_id=RULE_ID,
                    instrument_id=iid,
                    status=status,
                    picked_on=date(2026, 10, 16),
                    picked_price=D(1000),
                    benchmark=paper.benchmark,
                    benchmark_price=D(100),
                    theme="t",
                    rationale="r",
                    confirm=[],
                    invalidate=[],
                    buy=[],
                    confidence=None,
                    source="discovery:2026-12",
                ),
                lw.now(),
            )
    lw.tick("2026-10-17 10:00")
    assert live_pick(lw, "KR:068270").decision == "sell"
    assert live_pick(lw, "KR:000660").status == "candidate"
    assert live_pick(lw, "KR:005930").status == "held"
    lw.tick("2026-10-19 08:30")
    assert live_pick(lw, "KR:068270").status == "sold"  # nothing to sell: closed
    # The candidate expires in paper: the live one too.
    judged(lw, "KR:000660", status="expired", closed_on=date(2026, 10, 19))
    lw.tick("2026-10-19 15:00")
    assert live_pick(lw, "KR:000660").status == "expired"


def test_the_live_equal_weight_waits_for_the_paper_reviews(lw: Live) -> None:
    started(lw)
    month = date(2026, 11, 1)
    assert discovery_plan.ew_month(lw.conn, "live", month, 3) is None  # paper queued nothing
    with transaction(lw.conn):
        ai_repo.insert_job_run(
            lw.conn,
            job="ai-queue",
            ledger_id="paper",
            run_date=month,
            started_at=kst("2026-10-31 22:00"),
            ended_at=kst("2026-10-31 22:00"),
            result="ok",
            error=None,
            details={},
        )
    assert discovery_plan.ew_month(lw.conn, "live", month, 3) == "2026-11"


# ── the screens read a live ledger shared by two rules ───────────────────────────────────────


def test_the_screens_read_the_live_ledger_with_the_rule(lw: Live, tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from autotrade.api.app import create_app
    from autotrade.api.settings import ApiSettings

    from .api.support import PIN, owner_pin

    started(lw)
    lw.fake.slip = D("0.45")
    lw.tick("2026-10-16 22:30")
    lw.tick("2026-10-16 22:35")
    lw.tick("2026-10-17 06:00")
    settings = ApiSettings(
        secret_path=tmp_path / "autotrade.secret", dist_dir=tmp_path / "dist", scrypt_n=2**10
    )
    owner_pin(lw.conn, settings)
    app = create_app(lw.cfg, settings, lw.now)
    with TestClient(app, base_url="https://testserver") as web:
        assert web.post("/api/auth/pin", json={"pin": PIN}).status_code == 204
        for path in (
            "/api/shell",
            "/api/home",
            "/api/home/breakdown",
            "/api/plan",
            "/api/history",
            "/api/day/2026-10-16",
            "/api/rules",
            "/api/rules/discovery_3y",
            "/api/rules/index_half",
            "/api/health",
            "/api/mode",
            "/api/account",
        ):
            r = web.get(path)
            assert r.status_code == 200, (path, r.text[:300])
        rule = web.get("/api/rules/discovery_3y").json()
        assert rule["share"] == {"pct": 20.0, "target": 20.0}
        plan = json.dumps(web.get("/api/plan").json(), ensure_ascii=False)
        assert "한화오션" in plan, plan[:500]


# ── the plan itself (pure) ───────────────────────────────────────────────────────────────────


def test_the_live_plan_never_converts_and_sizes_as_the_send_pays() -> None:
    from autotrade.domain.discovery_plan import DiscoveryInput, Holding, plan_discovery
    from autotrade.domain.instruments import Instrument, Kind, kr_etf, us_etf
    from autotrade.domain.money import FeeRates

    kr = kr_etf("069500", "KOSPI200 ETF")
    us = us_etf("SPYM", "S&P 500 ETF")
    stock = Instrument("US:CCC", Market.US, Currency.USD, Kind.STOCK, "CCC", "CCC", "CCC")
    holdings = {
        kr.instrument_id: Holding(kr, 0, D(33000), buy_unit=D("33170")),
        us.instrument_id: Holding(us, 0, D("66.00"), buy_unit=D("66.40")),
        stock.instrument_id: Holding(stock, 0, D(100), buy_unit=D("100.60")),
    }
    inp = DiscoveryInput(
        holdings=holdings,
        sell=(),
        buy=(stock.instrument_id,),
        equalize=(),
        parking={Currency.KRW: kr.instrument_id, Currency.USD: us.instrument_id},
        per_pick_krw=D(700000),
        cash_krw=D(700000),
        cash_usd=D("150.00"),
        fx_rate=D(1400),
        fees=FeeRates(),
    )
    paper = plan_discovery(inp)
    # Paper converts won to buy 4 shares of the US pick (700,000 / (100.60 x 1,400) = 4.97).
    assert paper.fx is not None
    assert {o.instrument.instrument_id: o.qty for o in paper.buys}[stock.instrument_id] == 4
    live_plan = plan_discovery(replace(inp, convert=False))
    assert live_plan.fx is None
    buys = {o.instrument.instrument_id: o.qty for o in live_plan.buys}
    # The dollars pay one share at the send's 100.60; the won wait in the ETF at 33,170 a share.
    assert buys == {stock.instrument_id: 1, kr.instrument_id: 21}


def test_his_app_trade_of_the_index_etf_is_the_long_term_rules(lw: Live) -> None:
    started(lw)
    # He sells the four shares '지수 반반' holds (D47: to convert); the rule's one share stays.
    lw.fake.app_trade("069500", "SELL", D("4"), D(KODEX_CLOSE), commission=D("56"))
    lw.sync("2026-10-17 10:00")
    out = lw.reconcile("2026-10-17 10:00")
    assert lw.status().reconcile_state == "match", out
    assert sleeves.base_view(lw.conn, "live").qty_of("KR:069500") == 0
    assert sleeve(lw).qty_of("KR:069500") == 1
    assert verify_ledger(lw.conn, "live") == []
