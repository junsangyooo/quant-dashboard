"""`python -m autotrade.jobs live-discovery --pct N [--yes]`: give '3년 발굴' a share of the live
ledger and the paper ledger's picks (유준상 2026-10-15: 실전도 모의처럼 지수 반반 80 · 3년 발굴 20,
모의의 발굴 종목 15개를 실전에도).

The shares are the table's truth (bootstrap writes the configured ones once); this command is
how they change, not a migration: it shows what it would do first and writes only with --yes,
it can be run again (what is done already is left alone), and a rollback of the code does not
need to undo it.

- Only before the live ledger has started. The shares split money as it comes in (the start,
  deposits: engine/sleeves.py); the money of a started ledger stays where it is, so a change
  then would split the next deposit only. That is not what was decided, so it is refused.
- The picks are copied as judgments: the company, the day and price it was picked at (its
  score starts there), the benchmark, the theme, the reasons, the confirm / invalidate / buy
  conditions in their current form and words, and where the judgment stands (the last verdict,
  the weak months, a price-shock pause). Nothing of the paper ledger's money comes along: no
  shares, no fills, no orders, no pending decision. A pick the paper ledger is selling is not
  copied; one the live ledger has open already is skipped.
- Nothing is bought here. Turning live on (the mode screen) starts the ledger: the rule gets its
  share of the account's cash, and from the first weekday check on the tick plans its buys per
  currency like '지수 반반' (engine/discovery_plan.py, D47·D48).

One judgment, money per ledger (판단은 하나, 돈은 장부마다; 총괄 2026-10-15): the live ledger never
asks the AI anything of its own. Its tick runs no watch and no monthly or quarterly queue (no
filing screen, no sell or buy confirmation, no review, no discovery, no switch: every AI task
comes from those two). `follow` (the live tick's 'follow', database only) keeps its picks on the
paper ledger's judgment instead:
- a pick the paper ledger holds or watches is copied (a new pick of its quarterly discovery, a
  candidate it confirmed); one it is selling is not;
- an open live pick takes the paper pick's conditions as the monthly review rewrote them, its
  last verdict, weak months and shock pause, and its promotion from candidate to held;
- the paper ledger decides to sell (two '반증', a switch) or has sold: the live pick is to be
  sold ('sell'); the live planner sells its own shares, or closes it when it holds none;
- a candidate the paper ledger let expire closes the same way.
The live ledger buys a held pick it does not own with its own money, the same amount per pick.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_FLOOR, Decimal
from typing import Any

from autotrade.config import Config
from autotrade.db import ai_repo, live_repo, repo
from autotrade.domain.instruments import Currency
from autotrade.domain.money import CENT, WON, ZERO, usd_in_krw
from autotrade.engine.common import LIVE, PAPER
from autotrade.rules.discovery import RULE_ID
from autotrade.rules.index_half import RULE_ID as INDEX_RULE
from autotrade.timeutil import kst_date

OWNER_SOLD = "owner-app"  # a live pick whose shares the owner sold in the app (engine/live.py)
JOB = "live-discovery"
HUNDRED = Decimal(100)
COPIED_FIELDS = ("last_verdict", "last_verdict_at", "weak_months", "shock_until")


class LiveDiscoveryRefusedError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


@dataclass
class Change:
    pct: Decimal
    shares_before: dict[str, Decimal]
    shares_after: dict[str, Decimal]
    copy: list[ai_repo.PickRow] = field(default_factory=list)
    skipped: list[tuple[ai_repo.PickRow, str]] = field(default_factory=list)

    @property
    def shares_change(self) -> bool:
        return any(self.shares_before.get(r, ZERO) != v for r, v in self.shares_after.items())

    @property
    def nothing(self) -> bool:
        return not self.shares_change and not self.copy


def prepare(conn: sqlite3.Connection, pct: Decimal) -> Change:
    """What the command would change (reads only). Refuses a started live ledger."""
    if not ZERO <= pct < HUNDRED:
        raise LiveDiscoveryRefusedError("bad-pct", f"--pct must be 0 to 99, not {pct}")
    if repo.start_event(conn, LIVE) is not None:
        raise LiveDiscoveryRefusedError(
            "live-started",
            "the live ledger has started: its money stays where it is, a new share would only"
            " split the next deposit",
        )
    before = ai_repo.shares(conn, LIVE)
    after = {INDEX_RULE: HUNDRED - pct, RULE_ID: pct}
    change = Change(pct, before, after)
    if pct == 0:
        return change  # a share of 0 takes no picks (reviews.rule_active)
    for pick in ai_repo.picks_of(conn, PAPER, RULE_ID, ai_repo.OPEN_PICK):
        if pick.decision == "sell":
            change.skipped.append((pick, "selling-in-paper"))
        elif ai_repo.open_pick(conn, LIVE, RULE_ID, pick.instrument_id) is not None:
            change.skipped.append((pick, "in-live-already"))
        else:
            change.copy.append(pick)
    return change


def apply(conn: sqlite3.Connection, change: Change, at: datetime) -> list[int]:
    """Write the change (the caller owns the transaction). Returns the new picks' ids."""
    for rule_id, pct in change.shares_after.items():
        if change.shares_before.get(rule_id) != pct:
            ai_repo.set_share(conn, LIVE, rule_id, pct, at)
    ids = [copy_pick(conn, p, at) for p in change.copy]
    ai_repo.insert_job_run(
        conn,
        job=JOB,
        ledger_id=LIVE,
        run_date=kst_date(at),
        started_at=at,
        ended_at=at,
        result="applied",
        error=None,
        details={
            "shares": {r: str(v) for r, v in change.shares_after.items()},
            "copied": {p.pick_id: i for p, i in zip(change.copy, ids, strict=True)},
        },
    )
    return ids


def copy_pick(conn: sqlite3.Connection, p: ai_repo.PickRow, at: datetime) -> int:
    """The paper pick as a live pick: the judgment, none of the paper money (see the module)."""
    pick_id = ai_repo.insert_pick(
        conn,
        ai_repo.NewPick(
            ledger_id=LIVE,
            rule_id=RULE_ID,
            instrument_id=p.instrument_id,
            status=p.status,
            picked_on=p.picked_on,
            picked_price=p.picked_price,
            benchmark=p.benchmark,
            benchmark_price=p.benchmark_price,
            theme=p.theme,
            rationale=p.rationale,
            confirm=p.confirm,
            invalidate=p.invalidate,
            buy=p.buy,
            confidence=p.confidence,
            source=p.source,
            note=p.note,
            texts=p.texts,
        ),
        at,
    )
    state = {name: getattr(p, name) for name in COPIED_FIELDS}
    ai_repo.update_pick(conn, pick_id, at, **{k: v for k, v in state.items() if v})
    return pick_id


# The paper pick's judgment a live pick follows (texts stay the words it was picked with).
FOLLOWED = ("confirm", "invalidate", "buy", "last_verdict", "last_verdict_at", "weak_months")


def follows(conn: sqlite3.Connection) -> bool:
    """'3년 발굴' has a share of the live ledger: its picks follow the paper ledger's."""
    return ai_repo.shares(conn, LIVE).get(RULE_ID, ZERO) > 0


def _owner_sold(conn: sqlite3.Connection, p: ai_repo.PickRow) -> bool:
    """The owner sold the live ledger's shares of this judgment in the Toss app (engine/live.py
    OWNER_SOLD): the live ledger does not buy the company back while the paper judgment is the
    same one (the same pick day); a new judgment of it is copied again."""
    return any(
        mine.closed_reason == OWNER_SOLD and mine.picked_on == p.picked_on
        for mine in ai_repo.picks_of(conn, LIVE, RULE_ID, ("sold",))
        if mine.instrument_id == p.instrument_id
    )


def follow(conn: sqlite3.Connection, at: datetime) -> dict[str, list[str]]:
    """Bring the live picks to the paper ledger's judgment (the caller owns the transaction).
    Returns what changed, by instrument: added, updated, sell, closed (empty: nothing)."""
    out: dict[str, list[str]] = {"added": [], "updated": [], "sell": [], "closed": []}
    if not follows(conn):
        return out
    latest: dict[str, ai_repo.PickRow] = {}
    for p in ai_repo.picks_of(conn, PAPER, RULE_ID):  # by pick id: a later pick of a company wins
        latest[p.instrument_id] = p
    for iid, p in sorted(latest.items()):
        mine = ai_repo.open_pick(conn, LIVE, RULE_ID, iid)
        is_open = p.status in ai_repo.OPEN_PICK
        if mine is None:
            if is_open and p.decision != "sell" and not _owner_sold(conn, p):
                copy_pick(conn, p, at)
                out["added"].append(iid)
            continue
        fields: dict[str, Any] = {}
        selling = p.decision == "sell" or (not is_open and p.status == "sold")
        if mine.status == "held" and selling:
            if mine.decision != "sell":
                fields.update(decision="sell", decided_at=at)
                out["sell"].append(iid)
        elif not is_open:
            if mine.status == "candidate":
                fields.update(status=p.status, closed_on=p.closed_on, closed_reason=p.closed_reason)
                out["closed"].append(iid)
            elif p.status == "expired":  # a held pick is never let expire: kept as it is
                pass
        else:
            if mine.status == "candidate" and p.status == "held":
                fields["status"] = "held"
            if p.shock_until is not None and p.shock_until != mine.shock_until:
                fields["shock_until"] = p.shock_until
            for name in FOLLOWED:
                if getattr(p, name) != getattr(mine, name):
                    fields[name] = getattr(p, name)
            if fields:
                out["updated"].append(iid)
        if fields:
            ai_repo.update_pick(conn, mine.pick_id, at, **fields)
    return {k: v for k, v in out.items() if v}


def _floor(amount: Decimal, currency: Currency) -> Decimal:
    return amount.quantize(WON if currency is Currency.KRW else CENT, rounding=ROUND_FLOOR)


def estimate(
    conn: sqlite3.Connection, cfg: Config, change: Change, at: datetime
) -> dict[str, Any] | None:
    """A rough first look from the latest Toss snapshot and closes (None without a snapshot):
    the rule's part of the account's cash at the start, the same amount per pick, and the picks
    whose one share (the close, the send's 0.5% limit and the fee) fits in it. The tick plans
    the real orders at the first weekday check after turning on."""
    snap = live_repo.latest_snapshot(conn)
    if snap is None or change.pct <= 0:
        return None
    quote = repo.fx_at(conn, at)
    rate = None if quote is None else quote.rate
    parts = {c: _floor(snap.cash_of(c) * change.pct / HUNDRED, c) for c in Currency}
    total = parts[Currency.KRW] + (usd_in_krw(parts[Currency.USD], rate) if rate else ZERO)
    held = [p for p in change.copy if p.status == "held"]
    held += [
        p
        for p in ai_repo.picks_of(conn, LIVE, RULE_ID, ("held",))
        if p.instrument_id not in {h.instrument_id for h in held}
    ]
    per_pick = (total / len(held)).quantize(WON) if held else ZERO
    fits: list[str] = []
    dearer: list[str] = []
    for p in held:
        inst = repo.get_instrument(conn, p.instrument_id)
        bar = repo.latest_bar(conn, p.instrument_id, kst_date(at))
        if bar is None or (inst.currency is Currency.USD and rate is None):
            dearer.append(f"{inst.name}: no price")
            continue
        unit = bar.close * (1 + cfg.live_limit_slippage) * (1 + cfg.fees.rate_for(inst.currency))
        unit_krw = unit if inst.currency is Currency.KRW else usd_in_krw(unit, rate or ZERO)
        (fits if unit_krw <= per_pick else dearer).append(f"{inst.name} {unit_krw:,.0f}")
    return {
        "snapshot_at": snap.taken_at,
        "account_cash": {c.value: snap.cash_of(c) for c in Currency},
        "rule_cash_at_start": {c.value: v for c, v in parts.items()},
        "krw_rate": rate,
        "per_pick_krw": per_pick,
        "one_share_fits": fits,
        "one_share_dearer": dearer,
        "rest": "the cash no pick takes waits in the index ETF of its currency (whole shares)",
    }


def report(
    conn: sqlite3.Connection, cfg: Config, change: Change, at: datetime, *, applied: bool
) -> dict[str, Any]:
    def pick_json(p: ai_repo.PickRow) -> dict[str, Any]:
        inst = repo.get_instrument(conn, p.instrument_id)
        return {
            "paper_pick": p.pick_id,
            "instrument_id": p.instrument_id,
            "name": inst.name,
            "status": p.status,
            "picked_on": p.picked_on,
            "picked_price": p.picked_price,
            "conditions": {"confirm": len(p.confirm), "invalidate": len(p.invalidate)},
            "last_verdict": p.last_verdict,
        }

    result = "nothing-to-do" if change.nothing else "applied" if applied else "preview"
    out: dict[str, Any] = {
        "job": JOB,
        "result": result,
        "shares": {
            "before": {r: str(v) for r, v in sorted(change.shares_before.items())},
            "after": {r: str(v) for r, v in sorted(change.shares_after.items())},
        },
        "copy": [pick_json(p) for p in change.copy],
        "skipped": [{**pick_json(p), "why": why} for p, why in change.skipped],
        "estimate": estimate(conn, cfg, change, at),
    }
    if result == "preview":
        out["apply"] = f"python -m autotrade.jobs live-discovery --pct {change.pct} --yes"
    return out
