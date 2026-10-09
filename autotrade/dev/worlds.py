"""python -m autotrade.jobs dev-seed --db <path> --world <name> [--pin 123456]

A database for the web app, built by replaying the engine on a scripted market: the real jobs run
through the real 5-minute tick (autotrade/jobs/tick.py) at each day's times, the scripted CLI
(autotrade/dev/ai.py) answers where an AI flow asks, and nothing reaches the network or the
subscription CLI. A quote shows a session's open from the opening bell and its close once
published, as the real sources do. The PIN is set without asking (only dev-seed takes --pin).

Worlds (the clock to read them at, AUTOTRADE_FAKE_NOW, in parentheses):
  first-day   예시-값표 §4: the first day of a 10,000,000-won paper ledger, '지수 반반' alone
              (2026-07-01 16:10)
  paper       예시-값표 §1 with '지수 반반' alone (the momentum rule is only an example): 7/1 to
              10/7, rebalances on 8/21 and 10/7 (its US buy still waits for 22:30), a failed check
              on 9/9 closed on 9/10, the 9/30 dividend buying a share on 10/6 (2026-10-07 16:10)
  discovery   a 50,000,000-won paper ledger shared 80/20 with '3년 발굴' from 10/8: the 15 seed
              picks partly bought (a pick dearer than its share of the money waits), Q2 and Q3
              earnings read by the AI, a filing checked twice ('약화'), a price shock checked
              twice ('유지'), the November review and the Korean equal weight (2026-11-03 16:10)

It refuses a path under data/, the configured ledger (AUTOTRADE_DB) and an existing file: it only
ever creates a new database.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from autotrade.ai.cli import ClaudeCli
from autotrade.ai.runner import run_ai
from autotrade.config import REPO_ROOT, Config, load_config
from autotrade.db import ai_repo, repo
from autotrade.db.connection import connect
from autotrade.dev.ai import ScriptedRunner, review, sell
from autotrade.dev.market import KR, US, World
from autotrade.domain import metrics
from autotrade.domain.instruments import Market
from autotrade.engine.bootstrap import bootstrap
from autotrade.engine.seed import SeedPick, read_seed
from autotrade.jobs.tasks import JobContext, resolve_job
from autotrade.jobs.tick import TASKS as TICK_TASKS
from autotrade.jobs.tick import run_tick
from autotrade.market.calendar import calendar_for
from autotrade.market.types import Bar
from autotrade.rules.discovery import RULE_ID
from autotrade.timeutil import at_kst

D = Decimal
DATA_DIR = REPO_ROOT / "data"
DEFAULT_PIN = "123456"
INDEX_ONLY: Mapping[str, Mapping[str, Decimal]] = {
    "paper": {"index_half": D(100), "discovery_3y": D(0)},
    "live": {"index_half": D(100), "discovery_3y": D(0)},
}
# When the replay ticks each day (KST): dividends, the check, the AI runner's turn after the
# watch, the AI plan, the Korean and FX stages, the retry, the snapshot, the review queue and the
# runner after it, the NYSE open in and out of US daylight time.
TICKS = (
    time(8, 0),
    time(8, 30),
    time(8, 35),
    time(8, 40),
    time(9, 5),
    time(9, 10),
    time(9, 30),
    time(16, 0),
    time(22, 0),
    time(22, 5),
    time(22, 30),
    time(23, 30),
)
AI_TURNS = (time(8, 35), time(22, 5))
REPLAYED = tuple(t for t in TICK_TASKS if t != "backup")  # no copies of a dev database


class DevSeedRefusedError(Exception):
    """dev-seed will not write there (a real ledger, or a file that exists)."""


def guard(db: Path | None, env: Mapping[str, str]) -> Path:
    """The new database's path, or DevSeedRefusedError: never data/, never the configured ledger,
    never a file that exists."""
    if db is None:
        raise DevSeedRefusedError("give --db: dev-seed only writes where it is told")
    target = db.expanduser().resolve()
    data = DATA_DIR.resolve()
    if target == data or data in target.parents:
        raise DevSeedRefusedError(f"{target} is under {data}: dev-seed never touches a real ledger")
    if target == load_config(env).db_path.expanduser().resolve():
        raise DevSeedRefusedError(f"{target} is the configured ledger (AUTOTRADE_DB)")
    if target.exists():
        raise DevSeedRefusedError(f"{target} exists: dev-seed only creates a new database")
    return target


# ── the scripted market ─────────────────────────────────────────────────────────────────────


@dataclass
class Tape:
    """Daily bars as a quote source shows them: the open from the opening bell (the last price
    is the open until the close), the close once published (session close + the config's lag)."""

    world: World
    cfg: Config
    pending: list[tuple[datetime, Bar]] = field(default_factory=list)

    def session(self, iid: str, market: Market, d: date, open_: Decimal, close: Decimal) -> None:
        cal = calendar_for(market)
        lag = self.cfg.kr_publication_lag if market is Market.KR else self.cfg.us_publication_lag
        low, high = min(open_, close), max(open_, close)
        self.pending.append((cal.session_open(d), Bar(iid, d, open_, open_, open_, open_, "dev")))
        self.pending.append(
            (cal.session_close(d) + lag, Bar(iid, d, open_, high, low, close, "dev"))
        )

    def series(
        self,
        iid: str,
        market: Market,
        closes: Mapping[date, Decimal],
        opens: Mapping[date, Decimal] | None = None,
    ) -> None:
        """Sessions opening where the previous one closed, unless `opens` says otherwise."""
        previous: Decimal | None = None
        for d in sorted(closes):
            open_ = (opens or {}).get(d, previous or closes[d])
            self.session(iid, market, d, open_, closes[d])
            previous = closes[d]

    def publish(self, at: datetime) -> None:
        due = sorted(((t, b) for t, b in self.pending if t <= at), key=lambda tb: tb[0])
        self.pending = [(t, b) for t, b in self.pending if t > at]
        for _, bar in due:
            self.world.bars[(bar.instrument_id, bar.session_date)] = bar


def sessions(market: Market, start: date, end: date) -> list[date]:
    cal = calendar_for(market)
    return ([start] if cal.is_trading_day(start) else []) + cal.trading_days(start, end)


def lines(
    days: Sequence[date], anchors: Mapping[date, Decimal], step: Decimal
) -> dict[date, Decimal]:
    """Values on the days, straight between the anchors (counted in sessions), on `step`."""
    index = {d: i for i, d in enumerate(days)}
    points = sorted((index[d], v) for d, v in anchors.items() if d in index)
    out: dict[date, Decimal] = {}
    for d, i in index.items():
        lo = [p for p in points if p[0] <= i]
        hi = [p for p in points if p[0] >= i]
        if not lo or not hi:
            value = (hi or lo)[0 if hi else -1][1]
        else:
            (i0, v0), (i1, v1) = lo[-1], hi[0]
            value = v0 if i1 == i0 else v0 + (v1 - v0) * D(i - i0) / D(i1 - i0)
        out[d] = value.quantize(step)
    return out


def wave(
    days: Sequence[date], pivot: date, price: Decimal, drift: float, swing: float, phase: float
) -> dict[date, Decimal]:
    """A gentle path through `price` on `pivot`: a daily drift and a slow swing (no day moves
    more than about 1%, so no price shock is set off by accident)."""
    p0 = days.index(pivot)

    def shape(i: int) -> float:
        return (1 + drift * (i - p0)) * (1 + swing * math.sin(phase + 0.6 * i))

    base = shape(p0)
    step = D(1) if price >= 1000 else D("0.01")
    return {d: (price * D(shape(i) / base)).quantize(step) for i, d in enumerate(days)}


def rate_days(
    world: World,
    days: Sequence[date],
    anchors: Mapping[date, Decimal],
    extra: Mapping[datetime, str],
) -> None:
    """The rate on each day at 08:25, 09:10, 16:00 and 22:25, straight between the anchors."""
    daily = lines(days, anchors, D("0.1"))
    for d, rate in daily.items():
        for t in (time(8, 25), time(9, 10), time(16, 0), time(22, 25)):
            world.rate(at_kst(d, t), str(rate))
    for at, text in extra.items():
        world.rates = [(t, x) for t, x in world.rates if t != at]
        world.rate(at, text)


# ── the replay ──────────────────────────────────────────────────────────────────────────────


@dataclass
class Replay:
    """The engine on a scripted market: the tick at each of the day's times, and the AI runner's
    own turn after the watch and after the review queue."""

    ctx: JobContext
    tape: Tape
    scratch: Path
    runner: ScriptedRunner | None = None
    lines: list[dict[str, Any]] = field(default_factory=list)
    before: Callable[[datetime], None] = lambda at: None

    def run(self, first: date, until: datetime) -> None:
        d = first
        while at_kst(d, time()) < until:
            for t in TICKS:
                at = at_kst(d, t)
                if at >= until:
                    return
                self.before(at)
                self.tape.publish(at)
                if t in AI_TURNS:
                    self.ask(at)
                else:
                    self.tick(at)
            d += timedelta(days=1)

    def tick(self, at: datetime) -> None:
        def clock() -> datetime:
            return at

        run_tick(self.ctx, "paper", clock, self.scratch, self.lines.append, tasks=REPLAYED)

    def ask(self, at: datetime) -> None:
        if self.runner is None:
            return
        cfg = replace(self.ctx.cfg, ai_calls_enabled=True)  # the script answers, no CLI runs
        cli = ClaudeCli("claude", self.scratch / "ai-cwd", runner=self.runner, now=lambda: at)
        report = run_ai(self.ctx.conn, cfg, self.ctx.sources, cli, lambda: at, max_tasks=200)
        if report.get("result") != "nothing-due":
            self.lines.append({"at": at, "task": "ai", "result": report.get("result")})


# ── the worlds ──────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DevWorld:
    name: str
    now: datetime  # the screens' clock
    bootstrap_at: datetime
    start: date
    start_amount: Decimal
    shares: Mapping[str, Mapping[str, Decimal]]
    build: Callable[[Replay], None]


def build_first_day(r: Replay) -> None:
    """예시-값표 §4: the closes of 6/30 and 7/1, the rate at 08:25, 09:10 and 16:00."""
    for t, rate in ((time(8, 25), "1392.0"), (time(9, 10), "1392.0"), (time(16), "1391.5")):
        r.tape.world.rate(at_kst(date(2026, 7, 1), t), rate)
    r.tape.session(KR, Market.KR, date(2026, 6, 30), D(31900), D(32000))
    r.tape.session(KR, Market.KR, date(2026, 7, 1), D(32000), D(32050))
    r.tape.session(US, Market.US, date(2026, 6, 30), D("65.80"), D("66.00"))
    r.tape.session(US, Market.US, date(2026, 7, 1), D("66.00"), D("66.20"))
    r.run(date(2026, 7, 1), FIRST_DAY.now)


# 예시-값표 §1 with '지수 반반' alone: KOSPI200 ETF up from 32,000 to 36,250, the S&P 500 ETF down
# from $66 to $62.40, the rate from 1,392.0 to 1,382.4. The rule drifts past 2%p on the 8/20
# closes and again on the 10/6 closes, and nowhere else.
PAPER_KR = {
    date(2026, 6, 30): D(32000),
    date(2026, 7, 1): D(32050),
    date(2026, 8, 19): D(32900),
    date(2026, 8, 20): D(33300),
    date(2026, 8, 21): D(33700),
    date(2026, 10, 2): D(34900),
    date(2026, 10, 6): D(36360),
    date(2026, 10, 7): D(36250),
}
PAPER_KR_OPEN = {
    date(2026, 7, 1): D(32000),
    date(2026, 8, 21): D(33800),
    date(2026, 10, 6): D(36300),
    date(2026, 10, 7): D(36380),
}
PAPER_US = {
    date(2026, 6, 30): D("66.00"),
    date(2026, 7, 1): D("66.20"),
    date(2026, 8, 19): D("65.10"),
    date(2026, 8, 20): D("63.10"),
    date(2026, 8, 21): D("63.20"),
    date(2026, 10, 2): D("63.00"),
    date(2026, 10, 5): D("62.70"),
    date(2026, 10, 6): D("62.40"),
}
PAPER_US_OPEN = {
    date(2026, 6, 30): D("65.80"),
    date(2026, 7, 1): D("66.00"),
    date(2026, 8, 21): D("63.00"),
    date(2026, 10, 6): D("62.10"),
}
PAPER_RATE = {
    date(2026, 7, 1): D("1392.0"),
    date(2026, 8, 21): D("1389.6"),
    date(2026, 10, 7): D("1380.6"),
}
FAILED_CHECK_DAY = date(2026, 9, 9)  # '확인 실패 · 시세 응답 없음 → 9/10 정상'


def build_paper(r: Replay) -> None:
    world, end = r.tape.world, date(2026, 10, 7)
    start = date(2026, 6, 30)
    kr_days = sessions(Market.KR, start, end)
    us_days = [d for d in sessions(Market.US, start, end) if d < end]  # 10/7 has not opened
    r.tape.series(KR, Market.KR, lines(kr_days, PAPER_KR, D(1)), PAPER_KR_OPEN)
    r.tape.series(US, Market.US, lines(us_days, PAPER_US, D("0.01")), PAPER_US_OPEN)
    weekdays = sorted({*kr_days, *us_days} - {start})
    rate_days(
        world,
        weekdays,
        PAPER_RATE,
        {
            at_kst(date(2026, 7, 1), time(16, 0)): "1391.5",
            at_kst(date(2026, 10, 7), time(16, 0)): "1382.4",
        },
    )
    world.dividend(KR, "2026-09-23", "160", pay_date="2026-09-30")

    def outage(at: datetime) -> None:
        # 9/9: the US quote source answers nothing all morning, so the check and its retry fail
        # ('직접 할 일'); the quotes are back on 9/10 and the owner closes the item.
        morning = at_kst(FAILED_CHECK_DAY, time(8)) <= at <= at_kst(FAILED_CHECK_DAY, time(9, 30))
        world.fail_bars = {US} if morning else set()
        if at == at_kst(FAILED_CHECK_DAY + timedelta(days=1), time(8)):
            resolve_job(r.ctx, "paper", f"check-failed:{FAILED_CHECK_DAY}", at, note="quotes back")

    r.before = outage
    r.run(date(2026, 7, 1), PAPER.now)


# '3년 발굴' from 10/8 (the seed was picked on 10/6–10/7): every pick, both index ETFs and the two
# score benchmarks move gently from the pick day; 셀트리온 falls 9% against its index on 10/20.
DISCOVERY_START = date(2026, 10, 8)
SHOCK = ("KR:068270", date(2026, 10, 20), D("0.91"))
# SK바이오팜 runs ahead (+1.5% a session) so the November equal weight has a share to sell.
TRENDS = {"KR:326030": 0.015}
INDEX_PRICES = {  # instrument id or Yahoo symbol -> (market, pivot day, price)
    KR: (Market.KR, date(2026, 10, 7), D(108550)),
    US: (Market.US, date(2026, 10, 6), D("78.00")),
    "SPY": (Market.US, date(2026, 10, 6), D("779.09")),
}
DISCOVERY_RATE = {date(2026, 8, 17): D("1395.0"), date(2026, 11, 3): D("1410.0")}


def build_discovery(r: Replay) -> None:
    world, conn = r.tape.world, r.ctx.conn
    first, end = date(2026, 8, 17), DISCOVERY.now.date()
    days = {m: sessions(m, first, end) for m in (Market.KR, Market.US)}
    us_until = [d for d in days[Market.US] if d < end]  # the last US session has not opened
    seed = read_seed()
    for n, p in enumerate(seed.picks):
        inst = p.instrument
        span = days[inst.market] if inst.market is Market.KR else us_until
        drift = TRENDS.get(inst.instrument_id, 0.0004 * (n % 5 - 2))
        closes = wave(span, p.picked_on, p.close, drift, 0.012, n * 0.9)
        if inst.instrument_id == SHOCK[0]:
            _, day, factor = SHOCK
            closes = {d: (c * factor).quantize(D(1)) if d >= day else c for d, c in closes.items()}
        r.tape.series(inst.instrument_id, inst.market, closes)
        world.adjusted[inst.yahoo_symbol] = sorted(closes.items())
    for key, (market, pivot, price) in INDEX_PRICES.items():
        span = days[market] if market is Market.KR else us_until
        closes = wave(span, pivot, price, 0.0002, 0.006, 0.3)
        if key in (KR, US):
            r.tape.series(key, market, closes)
        if key != US:  # the score benchmarks: KOSPI200 ETF and SPY
            world.adjusted["069500.KS" if key == KR else key] = sorted(closes.items())
    rate_days(world, sorted({*days[Market.KR], *days[Market.US]}), DISCOVERY_RATE, {})
    filings(world, seed.picks)
    r.runner = ScriptedRunner(fallback=DevAnswers(conn))
    r.run(DISCOVERY_START, DISCOVERY.now)


def filings(world: World, picks: Sequence[SeedPick]) -> None:
    """Each pick's Q2 report (read once to fill its metric table), a contract cancellation
    (screened, then checked twice) and two Q3 earnings releases."""
    for n, p in enumerate(picks):
        iid, ticker = p.instrument.instrument_id, p.instrument.ticker
        if p.instrument.market is Market.KR:
            ref = f"2026081400{n:04d}"
            world.filing(iid, "dart", ref, "반기보고서 (2026.06)", "2026-08-14")
        elif ticker == "TSM":  # a foreign issuer reports on 6-K
            ref = f"0001046179-26-{n:06d}"
            world.filing(iid, "edgar", ref, "6-K", "2026-07-16", form="6-K")
        else:
            ref = f"0000000000-26-{n:06d}"
            world.filing(iid, "edgar", ref, "8-K", "2026-07-30", form="8-K", items="2.02,9.01")
        world.texts[ref] = (
            f"{p.instrument.name} 2026 2분기 실적: 매출, 영업이익, 순이익, 부문 실적."
        )
    world.filing("KR:042660", "dart", "20261023000444", "단일판매ㆍ공급계약해지", "2026-10-23")
    world.filing(
        "KR:012450",
        "dart",
        "20261027000555",
        "연결재무제표기준영업(잠정)실적(공정공시)",
        "2026-10-27",
    )
    world.filing(
        "US:AMZN", "edgar", "0001018724-26-000777", "8-K", "2026-10-29", form="8-K", items="2.02"
    )
    for ref in ("20261023000444", "20261027000555", "0001018724-26-000777"):
        world.texts[ref] = "2026 3분기: 매출, 영업이익, 부문 수주잔고, 계약 금액."


# Metric values the scripted extraction reports: (instrument, metric) -> (Q2, Q3). The sell
# conditions stay unmet except one that comes close (한화에어로스페이스's land-systems backlog,
# 38.3조 -> 33조 against a 30조 line: 64% of the way).
METRICS: Mapping[tuple[str, str], tuple[Decimal, Decimal]] = {
    ("KR:012450", "segment_backlog:지상방산"): (D("38300000000000"), D("33000000000000")),
    ("KR:012450", "segment_operating_income:지상방산"): (D("700000000000"), D("650000000000")),
    ("KR:012450", "segment_op_margin:지상방산"): (D("21.0"), D("20.4")),
    ("KR:009540", "new_orders"): (D("3000000000000"), D("2900000000000")),
    ("KR:009540", "revenue"): (D("2500000000000"), D("2600000000000")),
    ("KR:042660", "revenue"): (D("3000000000000"), D("3100000000000")),
    ("KR:042660", "operating_income"): (D("300000000000"), D("280000000000")),
    ("KR:267260", "revenue"): (D("1000000000000"), D("1050000000000")),
    ("KR:267260", "operating_income"): (D("240000000000"), D("250000000000")),
    ("KR:267260", "backlog"): (D("9000000000"), D("9300000000")),
    ("KR:267260", "new_orders"): (D("1300000000"), D("1250000000")),
    ("KR:068270", "operating_income"): (D("450000000000"), D("520000000000")),
    ("KR:003230", "revenue"): (D("600000000000"), D("640000000000")),
    ("KR:003230", "operating_income"): (D("132000000000"), D("140000000000")),
    ("KR:071050", "net_income"): (D("650000000000"), D("660000000000")),
    ("US:TSM", "monthly_revenue_yoy"): (D("30.0"), D("32.0")),
    ("US:AMZN", "segment_revenue:AWS"): (D("31000000000"), D("33000000000")),
    ("US:LLY", "guidance:2027 매출 성장"): (D("15.0"), D("15.0")),
    ("US:MTZ", "net_debt_to_ebitda"): (D("1.8"), D("1.7")),
    ("US:HII", "segment_op_margin:조선"): (D("6.2"), D("6.3")),
}
USD_MONEY = {"KR:267260": ("backlog", "new_orders")}  # orders booked in dollars


class DevAnswers:
    """The script of the discovery world, by question: the code's own numbers for an earnings
    read, '관련 있음' for the contract cancellation, '반증' then '유지' for it, '유지' twice for
    the shock (with one news item), and a review that keeps every condition but 한화오션's."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.asked: dict[str, int] = {}

    def __call__(self, kind: str, cmd: list[str]) -> Mapping[str, Any]:
        prompt = cmd[cmd.index("-p") + 1]
        found = re.search(r"\(([A-Z]{2}:[A-Z0-9]+)[,)]", prompt)
        iid = found.group(1) if found else ""
        if kind == "extract":
            return self.extract(iid, prompt, cmd)
        if kind == "screen":
            return {"relevant": True, "touches": [2], "reason": "계약 해지로 수주가 줄어든다"}
        if kind == "sell":
            n = self.asked[iid] = self.asked.get(iid, 0) + 1
            if iid == SHOCK[0]:
                news = {
                    "fact": "임상 결과 발표가 미뤄졌다",
                    "source": "yna.co.kr",
                    "date": "2026-10-20",
                }
                return sell("유지", [news] if n == 1 else None)
            return sell("반증" if n % 2 == 1 else "유지")
        if kind == "review":
            pick = ai_repo.open_pick(self.conn, "paper", RULE_ID, iid)
            if iid == "KR:042660":  # weaker: the margin line moves from 7% to 6%
                weaker = [
                    {
                        "type": "streak",
                        "metric": "operating_income",
                        "change": "yoy",
                        "direction": "down",
                        "periods": 2,
                    },
                    {"type": "level", "metric": "op_margin", "op": "<", "value": 6, "unit": "%"},
                ]
                return review("약화", weaker)
            return review("유지", list(pick.invalidate) if pick is not None else [])
        raise ValueError(f"the discovery world asks no {kind} question")

    def extract(self, iid: str, prompt: str, cmd: list[str]) -> Mapping[str, Any]:
        """One value per metric the call may answer with (the schema's list), for the quarter
        the filing reports (filed in October or later: Q3)."""
        schema = json.loads(cmd[cmd.index("--json-schema") + 1])
        keys = schema["properties"]["metrics"]["items"]["properties"]["metric"]["enum"]
        filed = re.search(r"· \d{4}-(\d{2})-\d{2} ·", prompt)
        q3 = filed is not None and int(filed.group(1)) >= 10
        items = []
        for key in keys:
            d, _ = metrics.resolve(key)
            dollars = iid.startswith("US:") or key in USD_MONEY.get(iid, ())
            if d.unit_kind == "money":
                unit, default = ("USD", D("5000000000")) if dollars else ("KRW", D("500000000000"))
            else:
                unit = {"pct": "%", "ratio": "x", "count": "count"}.get(d.unit_kind, "%")
                default = {"%": D("15.0"), "x": D("1.2"), "count": D(10)}[unit]
            value = METRICS.get((iid, key), (default, default))[1 if q3 else 0]
            if d.period_kind == "month":
                period = "2026-09" if q3 else "2026-06"
            else:
                period = "2026Q3" if q3 else "2026Q2"
            item = {"metric": key, "period": period, "value": float(value), "unit": unit}
            items.append({**item, "quote": "dev-seed"})
        return {"metrics": items, "notes": "dev-seed"}


FIRST_DAY = DevWorld(
    "first-day",
    at_kst(date(2026, 7, 1), time(16, 10)),
    at_kst(date(2026, 6, 30), time(12, 0)),
    date(2026, 7, 1),
    D("10000000"),
    INDEX_ONLY,
    build_first_day,
)
PAPER = DevWorld(
    "paper",
    at_kst(date(2026, 10, 7), time(16, 10)),
    at_kst(date(2026, 6, 30), time(12, 0)),
    date(2026, 7, 1),
    D("10000000"),
    INDEX_ONLY,
    build_paper,
)
DISCOVERY = DevWorld(
    "discovery",
    at_kst(date(2026, 11, 3), time(16, 10)),
    at_kst(date(2026, 10, 7), time(18, 0)),
    DISCOVERY_START,
    D("50000000"),
    Config().rule_shares,  # paper 80/20
    build_discovery,
)
WORLDS = {w.name: w for w in (FIRST_DAY, PAPER, DISCOVERY)}


def dev_seed(
    db: Path | None, name: str, pin: str | None = None, env: Mapping[str, str] | None = None
) -> dict[str, Any]:
    """Build the world into a new database at `db` and set the owner PIN. Raises DevSeedRefusedError
    before touching anything when the path is not allowed."""
    from autotrade.api.auth import set_pin  # the web API stack is only needed here
    from autotrade.api.security import is_valid_pin, load_or_create_secret
    from autotrade.api.settings import default_settings

    target = guard(db, os.environ if env is None else env)
    world_def = WORLDS[name]
    owner_pin = pin or DEFAULT_PIN
    if not is_valid_pin(owner_pin):
        raise DevSeedRefusedError("the PIN is 6 digits")
    cfg = Config(
        db_path=target,
        paper_start_date=world_def.start,
        paper_start_amount=world_def.start_amount,
        rule_shares=world_def.shares,
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(target)
    try:
        bootstrap(conn, cfg, world_def.bootstrap_at)
        world = World()
        with tempfile.TemporaryDirectory(prefix="autotrade-dev-") as scratch:
            replay = Replay(JobContext(conn, cfg, world.sources()), Tape(world, cfg), Path(scratch))
            world_def.build(replay)
        settings = default_settings(cfg)
        set_pin(
            conn,
            load_or_create_secret(settings.secret_path),
            owner_pin,
            settings.scrypt_n,
            world_def.now,
        )
        failed = [
            line for line in replay.lines if line.get("result") in ("failed", "todo", "error")
        ]
        report = {
            "job": "dev-seed",
            "result": "ok",
            "world": name,
            "db": str(target),
            "now": world_def.now,
            "pin": owner_pin,
            "env": f"AUTOTRADE_DEV=1 AUTOTRADE_FAKE_NOW={world_def.now.isoformat()} "
            f"AUTOTRADE_DB={target}",
            "events": len(repo.events_of_ledger(conn, "paper")),
            "plans": len(repo.plans_of_ledger(conn, "paper")),
            "ai_calls": len(ai_repo.last_calls(conn, 10_000)),
            "failed": [{k: line.get(k) for k in ("at", "task", "result")} for line in failed],
        }
    finally:
        conn.close()
    return report
