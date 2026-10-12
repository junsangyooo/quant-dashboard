"""한국 계좌 · 미국 계좌 on the home screen (CONTRACT.md HomeResponse.accounts, accounts.py).

The ledger's won P&L splits exactly into 한국 + 미국 in won + 환율 효과; each account is valued in
its own currency; conversions are transfers between the accounts, never P&L; dividends and fees
stay with the account of their currency; the 30-trading-day rule is each account's own record.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from autotrade.api.app import create_app
from autotrade.api.views.accounts import Accounts, snapshot_value
from autotrade.api.views.context import LedgerContext
from autotrade.config import Config
from autotrade.db import repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency
from autotrade.domain.ledger import CashFlowKind, apply_cash_flow
from autotrade.domain.money import round_won
from autotrade.domain.planner import FxDirection
from autotrade.jobs.tasks import JobContext, check_job, dividend_job, snapshot_job, stage_job
from autotrade.market.calendar import KRX, NYSE

from ..fakes import KR, US, World
from ..helpers import kst
from ..test_dev_seed import seed
from .support import PIN, Clock, first_day

D = Decimal
START = date(2026, 7, 1)
END = date(2026, 10, 7)


def relogin(client: TestClient, clock: Clock, when: str) -> None:
    clock.now = kst(when)
    assert client.post("/api/auth/pin", json={"pin": PIN}).status_code == 204


def account(home: dict[str, Any], account_id: str) -> dict[str, Any]:
    return next(a for a in home["accounts"]["list"] if a["id"] == account_id)


def rows(acc: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for g in acc["composition"]["groups"] for r in g["rows"]]


def cents(x: float) -> int:
    return round(x * 100)


def assert_composition_adds_up(acc: dict[str, Any]) -> None:
    """Rows add up to the account's total in its currency, groups to their rows, all to 100.0."""
    key = "usd" if acc["currency"] == "USD" else "krw"
    found = rows(acc)
    if acc["currency"] == "USD":
        assert sum(cents(r["usd"]) for r in found) == cents(acc["total"])
    else:
        assert sum(r[key] for r in found) == acc["total"]
    if found:
        assert sum(D(str(r["pct"])) for r in found) == D("100.0")
    for group in acc["composition"]["groups"]:
        assert D(str(group["pct"])) == sum(D(str(r["pct"])) for r in group["rows"])
        assert group["target"] is None  # targets are the ledger's


def assert_breakdown_adds_up(b: dict[str, Any]) -> None:
    parts = ("deposit", "withdrawal", "transfer", "market", "dividend", "fees")
    assert sum(cents(b[p]) for p in parts) == cents(b["end"]) - cents(b["start"])
    assert b["withdrawal"] <= 0
    assert b["fees"] <= 0


# ── 출시 첫날 (예시-값표 §4) ──────────────────────────────────────────────────────────────────


def test_first_day_dollars_waiting_split_adds_up(
    logged_in: TestClient, world: World, jobs: JobContext
) -> None:
    """7/1 16:10: 미국 계좌 holds only the dollars waiting for the 22:30 buy."""
    first_day(world, jobs)
    home = logged_in.get("/api/home").json()
    kr, us = account(home, "kr"), account(home, "us")

    # 한국: 156 × 32,050 + 40,252 = 5,040,052; in = 10,000,000 − 4,967,000 sent to buy dollars.
    assert (kr["currency"], kr["total"]) == ("KRW", 5040052)
    assert kr["pnl"] == {"amount": 7052, "pct": 0.14}  # +7,800 on the ETF − 748 fee
    # 미국: the $3,568.24 the 09:10 conversion bought, nothing else yet: no gain, no loss.
    assert (us["currency"], us["total"]) == ("USD", 3568.24)
    assert us["pnl"] == {"amount": 0.0, "pct": 0.0}
    [dollars] = rows(us)
    assert (dollars["kind"], dollars["usd"], dollars["krw"], dollars["pct"]) == (
        "cash",
        3568.24,
        4965206,
        100.0,
    )
    assert dollars["cash"] == {"currency": "USD", "country": "US"}
    assert dollars["chip"] == {"kind": "buy-wait", "instrumentName": "S&P 500 ETF", "qty": 54}

    # The won P&L in three parts, to the won: +5,258 = +7,052 + 0 + (−1,794).
    # 환율 효과: the dollars bought at 1,392.0 are worth 1,391.5 now: 3,568.24 × 1,391.5 =
    # 4,965,206 (rounded once) − 4,967,000 = −1,794.
    assert home["pnl"]["amount"] == 5258
    assert home["accounts"]["split"] == {"kr": 7052, "us": 0, "fx": -1794}
    assert sum(home["accounts"]["split"].values()) == home["pnl"]["amount"]

    for acc in (kr, us):
        assert_composition_adds_up(acc)
        trend = acc["trend"]
        assert (trend["periods"], trend["period"], trend["periodPnl"]) == (None, "all", None)
        assert trend["empty"] == "first-day"  # '그래프는 둘째 날부터'
        [point] = trend["series"]
        assert point["value"] == acc["total"]
        assert (point["baseline"], point["baselineRet"]) == (None, None)  # 전체만
        # 원금: money in by then — 10,000,000 − 4,967,000 won; the $3,568.24 the conversion bought.
        assert point["netIn"] == (5033000 if acc["id"] == "kr" else 3568.24)
        assert [m["kind"] for m in trend["events"]] == ["start"]
        assert acc["stale"] is False
    assert kr["composition"]["groups"][0]["rule"]["id"] == "index_half"
    assert kr["composition"]["groups"][-1]["label"] == "cash"


def test_before_the_first_fill_there_is_no_account_view(
    logged_in: TestClient, world: World, jobs: JobContext, clock: Clock
) -> None:
    relogin(logged_in, clock, "2026-06-30 18:00")
    assert logged_in.get("/api/home").json()["accounts"] is None  # before the first check
    world.bar(KR, "2026-06-30", close="32000", open_="31900")
    world.bar(US, "2026-06-30", close="66.00", open_="65.80")
    world.rate(kst("2026-07-01 08:25"), "1392.0")
    assert check_job(jobs, "paper", kst("2026-07-01 08:30"))["result"] == "rebalance"
    relogin(logged_in, clock, "2026-07-01 08:40")
    home = logged_in.get("/api/home").json()
    assert (home["pnl"], home["accounts"]) == (None, None)  # '손익 · 첫 체결 뒤': no switch


def test_after_the_korean_buy_before_the_conversion_the_us_account_is_empty(
    logged_in: TestClient, world: World, jobs: JobContext, clock: Clock
) -> None:
    world.bar(KR, "2026-06-30", close="32000", open_="31900")
    world.bar(US, "2026-06-30", close="66.00", open_="65.80")
    world.rate(kst("2026-07-01 08:25"), "1392.0")
    world.rate(kst("2026-07-01 09:10"), "1392.0")
    world.bar(KR, "2026-07-01", close="32050", open_="32000")
    check_job(jobs, "paper", kst("2026-07-01 08:30"))
    stage_job(jobs, "paper", kst("2026-07-01 09:05"))
    relogin(logged_in, clock, "2026-07-01 09:07")
    home = logged_in.get("/api/home").json()
    kr, us = account(home, "kr"), account(home, "us")
    # 08:30 prices on the ledger as it is now: 156 × 32,000 + the cash left after the buy.
    assert kr["total"] == home["total"] == 9999252
    assert kr["pnl"] == {"amount": -748, "pct": -0.01}  # the fee
    assert (us["total"], us["pnl"]) == (0.0, None)  # no money has reached it: empty
    assert (us["trend"]["series"], us["trend"]["empty"]) == ([], None)
    assert us["composition"]["groups"] == []
    assert home["accounts"]["split"] == {"kr": -748, "us": 0, "fx": 0}


def test_a_conversion_counts_from_when_the_ledger_took_it(
    db: sqlite3.Connection, api_cfg: Config, world: World, jobs: JobContext
) -> None:
    """A stage that runs late is stamped with its due time (09:10) but the ledger took it at
    09:30: the money moved then, so a moment in between still has the won in 한국 계좌."""
    world.bar(KR, "2026-06-30", close="32000", open_="31900")
    world.bar(US, "2026-06-30", close="66.00", open_="65.80")
    world.rate(kst("2026-07-01 08:25"), "1392.0")
    world.rate(kst("2026-07-01 09:10"), "1392.0")
    check_job(jobs, "paper", kst("2026-07-01 08:30"))
    stage_job(jobs, "paper", kst("2026-07-01 09:05"))
    stage_job(jobs, "paper", kst("2026-07-01 09:30"))  # the 09:10 conversion, late
    [fx] = [f for f in repo.fills_of_ledger(db, "paper") if f.kind == "fx"]
    assert fx.filled_at == kst("2026-07-01 09:10")
    accounts = Accounts(LedgerContext(db, api_cfg, "paper", kst("2026-07-01 10:00")))
    assert accounts.net_in(Currency.USD, kst("2026-07-01 09:20")) == 0
    assert accounts.net_in(Currency.USD, kst("2026-07-01 09:30")) == D("3568.24")
    assert accounts.net_in(Currency.KRW, kst("2026-07-01 09:20")) == D("10000000")
    assert accounts.net_in(Currency.KRW) == D("10000000") - fx.gross


def test_bad_account_is_a_bad_request(
    logged_in: TestClient, world: World, jobs: JobContext
) -> None:
    first_day(world, jobs)
    response = logged_in.get("/api/home/breakdown?account=jp")
    assert response.status_code == 400
    assert response.json()["error"] == "bad-request"


# ── a long record with a moving rate, a deposit and two dividends ────────────────────────────


def rate_on(n: int) -> str:
    return f"{1390 + n * D('0.3'):.1f}"  # 1,390.3 → 1,411.3: the dollar gains on the won


@pytest.fixture
def long_world(db: sqlite3.Connection, world: World, jobs: JobContext) -> None:
    day = START - timedelta(days=1)
    world.bar(KR, day.isoformat(), close="32000", open_="32000")
    world.bar(US, day.isoformat(), close="66.00", open_="66.00")
    world.dividend(US, "2026-09-11", "0.239", pay_date="2026-09-15")
    world.dividend(KR, "2026-09-23", "160", pay_date="2026-09-30")
    n = 0
    d = START
    while d <= END:
        if d.weekday() < 5:
            n += 1
            for t in ("07:55", "08:25", "09:10", "16:00", "22:30"):
                world.rate(kst(f"{d.isoformat()} {t}"), rate_on(n))
            if KRX.is_trading_day(d):
                kospi = 32000 + 60 * n
                world.bar(KR, d.isoformat(), close=str(kospi), open_=str(kospi - 30))
            if NYSE.is_trading_day(d):
                spym = D("66.00") - D("0.02") * n
                world.bar(US, d.isoformat(), close=str(spym), open_=str(spym + D("0.01")))
            dividend_job(jobs, "paper", kst(f"{d.isoformat()} 08:00"))
            if d == date(2026, 10, 6):
                at = kst("2026-10-06 12:00")
                with transaction(db):
                    state = apply_cash_flow(
                        repo.load_state(db, "paper"), CashFlowKind.DEPOSIT, D("1000000")
                    )
                    repo.save_state(db, "paper", state, at)
                    repo.insert_event(
                        db,
                        ledger_id="paper",
                        kind="deposit",
                        event_date=d,
                        occurred_at=at,
                        amount=D("1000000"),
                        currency=Currency.KRW,
                    )
            check_job(jobs, "paper", kst(f"{d.isoformat()} 08:30"))
            stage_job(jobs, "paper", kst(f"{d.isoformat()} 09:30"))
            snapshot_job(jobs, "paper", kst(f"{d.isoformat()} 16:00"))
            stage_job(jobs, "paper", kst(f"{d.isoformat()} 23:59"))
        d += timedelta(days=1)


def test_long_record_accounts(
    long_world: None,
    logged_in: TestClient,
    clock: Clock,
    db: sqlite3.Connection,
    api_cfg: Config,
) -> None:
    relogin(logged_in, clock, "2026-10-07 16:10")
    home = logged_in.get("/api/home").json()
    kr, us = account(home, "kr"), account(home, "us")
    split = home["accounts"]["split"]
    rate = D(str(home["basis"]["fxRate"]))

    # The split adds up to the won, and each part is what it says.
    assert split["kr"] + split["us"] + split["fx"] == home["pnl"]["amount"]
    assert split["kr"] == kr["pnl"]["amount"]
    assert split["us"] == int(round_won(D(str(us["pnl"]["amount"])) * rate))
    # 환율 효과 = the dollars the conversions bought at today's rate − the won they cost (to the
    # rounding of the dollar rows): the dollar rose, so it is a gain.
    fills = repo.fills_of_ledger(db, "paper")
    sent = sum(
        (f.gross if f.fx_direction == FxDirection.KRW_TO_USD.value else -(f.received or 0))
        for f in fills
        if f.kind == "fx"
    )
    bought = sum(
        ((f.received or 0) if f.fx_direction == FxDirection.KRW_TO_USD.value else -f.gross)
        for f in fills
        if f.kind == "fx"
    )
    assert abs(D(split["fx"]) - (bought * rate - sent)) <= 2
    assert split["fx"] > 0

    # Each account in its own currency, its rows adding up to it.
    assert (kr["currency"], us["currency"]) == ("KRW", "USD")
    assert kr["total"] + int(round_won(D(str(us["total"])) * rate)) - home["total"] in (-1, 0, 1)
    for acc in (kr, us):
        assert_composition_adds_up(acc)
    [spym] = [r for r in rows(us) if r["kind"] == "holding"]
    close = D(str(repo.latest_bar(db, US, date(2026, 10, 6)).close))  # type: ignore[union-attr]
    assert D(str(spym["usd"])) == close * spym["qty"]
    assert spym["avgCost"]["currency"] == "USD"
    assert spym["pnlPct"] < 0  # in dollars the ETF fell; the rate is not in it

    # The deposit is money into 한국 계좌; the dividends are P&L of their currency's account.
    contributions = D("11000000")
    assert home["total"] - home["pnl"]["amount"] == contributions
    kr_markers = {m["date"]: m["kinds"] for m in kr["trend"]["events"]}
    us_markers = {m["date"]: m["kinds"] for m in us["trend"]["events"]}
    assert "deposit" in kr_markers["2026-10-06"]
    assert "deposit" not in us_markers.get("2026-10-06", [])
    assert "dividend" in kr_markers["2026-09-30"]
    assert "2026-09-30" not in us_markers
    assert "dividend" in us_markers["2026-09-15"]
    assert "2026-09-15" not in kr_markers
    assert "rebalance" in kr_markers["2026-10-06"]
    assert "rebalance" in us_markers["2026-10-06"]

    # Period chips: both accounts have the whole record (71 snapshots), so they follow the period.
    for acc in (kr, us):
        trend = acc["trend"]
        assert (trend["periods"], trend["period"]) == (["1m", "3m", "1y", "all"], "3m")
        assert trend["series"][0]["date"] == "2026-07-07"
        assert trend["series"][-1]["value"] == acc["total"]
    month = logged_in.get("/api/home?period=1m").json()
    assert account(month, "us")["trend"]["series"][0]["date"] == "2026-09-07"
    assert account(month, "us")["trend"]["period"] == "1m"
    whole = logged_in.get("/api/home?period=all").json()
    assert account(whole, "kr")["trend"]["periodPnl"] is None
    assert account(whole, "kr")["trend"]["series"][0]["date"] == "2026-07-01"

    # The period P&L of an account: now − its value at the period start − what came in since.
    ctx = LedgerContext(db, api_cfg, "paper", clock.now)
    accounts = Accounts(ctx)
    snaps = {s.date: s for s in repo.snapshots_of_ledger(db, "paper")}
    start = snaps[date(2026, 7, 7)]
    for acc, currency in ((kr, Currency.KRW), (us, Currency.USD)):
        value = snapshot_value(start, currency)
        came_in = accounts.net_in(currency) - accounts.net_in(currency, start.valued_at)
        amount = D(str(acc["total"])) - value - came_in
        assert D(str(acc["trend"]["periodPnl"]["amount"])) == amount
        # And the breakdown of each period adds up, conversions as money in or out.
        for period in ("1m", "3m", "1y", "all"):
            b = logged_in.get(f"/api/home/breakdown?period={period}&account={acc['id']}").json()
            assert b["currency"] == acc["currency"]
            assert_breakdown_adds_up(b)
            assert b["end"] == acc["total"]
    all_kr = logged_in.get("/api/home/breakdown?period=all&account=kr").json()
    all_us = logged_in.get("/api/home/breakdown?period=all&account=us").json()
    assert (all_kr["start"], all_us["start"]) == (10000000, 0.0)
    assert (all_kr["deposit"], all_us["deposit"]) == (1000000, 0.0)
    assert all_kr["transfer"] == -int(sent)
    assert D(str(all_us["transfer"])) == bought
    assert all_kr["dividend"] > 0
    assert all_us["dividend"] > 0
    # The whole ledger's breakdown is unchanged: no currency, no transfer.
    whole_b = logged_in.get("/api/home/breakdown?period=all").json()
    assert "currency" not in whole_b
    assert "transfer" not in whole_b


def test_every_snapshot_splits_into_its_accounts(
    long_world: None, db: sqlite3.Connection, api_cfg: Config
) -> None:
    """Each snapshot's money in, split per account at its moment, adds back up to the ledger's:
    the transfers are timed as the snapshots saw them."""
    ctx = LedgerContext(db, api_cfg, "paper", kst("2026-10-07 16:10"))
    accounts = Accounts(ctx)
    for snap in ctx.snapshots:
        kr_in = accounts.net_in(Currency.KRW, snap.valued_at)
        fx_sent = sum(
            (
                f.gross
                for applied, f in accounts.fills
                if f.kind == "fx" and applied <= snap.valued_at
            ),
            D(0),
        )
        assert kr_in + fx_sent == snap.contributions, snap.date
        us_value = snapshot_value(snap, Currency.USD)
        kr_value = snapshot_value(snap, Currency.KRW)
        assert abs(kr_value + us_value * snap.fx_rate - snap.total_krw) <= 2, snap.date


# ── the discovery world: a plan marks only the accounts it traded in ─────────────────────────


def test_the_ai_rule_s_korean_plan_marks_only_the_korean_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = seed(tmp_path / "discovery.db", "discovery")
    for pair in report["env"].split():
        key, _, value = pair.partition("=")
        monkeypatch.setenv(key, value)
    with TestClient(create_app(), base_url="https://testserver") as client:
        assert client.post("/api/auth/pin", json={"pin": PIN}).status_code == 204
        home = client.get("/api/home").json()
    kr, us = account(home, "kr"), account(home, "us")
    kr_days = {m["date"] for m in kr["trend"]["events"]}
    us_days = {m["date"] for m in us["trend"]["events"]}
    # 10/8: the start bought in both markets; 11/2: equal weights among the Korean picks only.
    assert {"2026-10-08", "2026-11-02"} <= kr_days
    assert "2026-10-08" in us_days
    assert "2026-11-02" not in us_days
    assert sum(home["accounts"]["split"].values()) == home["pnl"]["amount"]
    for acc in (kr, us):
        assert_composition_adds_up(acc)
        rules = {g.get("rule", {}).get("id") for g in acc["composition"]["groups"]}
        assert {"index_half", "discovery_3y"} <= rules  # both rules hold money in both
