"""GET /api/mode (SCR-MODE) and the mode switch's checks (autotrade/PHASE3.md 2.6-2.7).

Everything here reads what the tick recorded: the web service cannot reach Toss. Turning live on
rests on a recent Toss check (broker_status), a quiet account snapshot and fresh market data, and
compares the preview the owner approved with one recomputed at that moment (인계 13).
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from autotrade.api.views import fmt
from autotrade.api.views import health as health_view
from autotrade.api.views import live as live_view
from autotrade.api.views.context import LedgerContext
from autotrade.api.views.history import DayData
from autotrade.api.views.orders import plan_stages
from autotrade.api.views.refs import initials
from autotrade.api.views.refs import instrument as instrument_json
from autotrade.api.views.series import long_record
from autotrade.config import Config
from autotrade.db import live_repo, repo
from autotrade.db.connection import transaction
from autotrade.domain.instruments import Currency, Instrument, Kind, Market
from autotrade.domain.money import usd_in_krw
from autotrade.domain.planner import Plan
from autotrade.domain.stages import StageMarket
from autotrade.engine import live
from autotrade.engine.live import NotComputable, PreviewData
from autotrade.rules.index_half import RULE_ID
from autotrade.timeutil import kst_date


def off_preview(ctx: LedgerContext) -> dict[str, Any] | None:
    """What turning live off leaves behind (SCR-MODE off modal): the live ledger's orders that
    would be cancelled and the cash that stays in the account. Null unless live is on."""
    if ctx.mode != "live":
        return None
    cancel: list[dict[str, Any]] = []
    for plan in repo.open_plans(ctx.conn, "live"):
        for stage in plan_stages(ctx.conn, plan.plan_id, ctx.instruments, "live"):
            cancel.extend(o for o in stage["orders"] if o["status"] == "pending")
    state = repo.load_state(ctx.conn, "live")
    quote = repo.fx_at(ctx.conn, ctx.now)
    rate = quote.rate if quote is not None else ctx.fx_rate
    cash: list[dict[str, Any]] = []
    for currency in Currency:
        amount = state.cash_of(currency)
        if amount <= 0:
            continue
        if currency is Currency.KRW:
            cash.append({"currency": "KRW", "krw": fmt.krw(amount)})
        else:
            cash.append(
                {
                    "currency": "USD",
                    "usd": fmt.usd(amount),
                    "krw": fmt.krw(usd_in_krw(amount, rate)),
                }
            )
    return {"cancel": cancel, "cash": cash}


def _weekdays(start: date, end: date) -> int:
    days = 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            days += 1
        d += timedelta(days=1)
    return days


def _performance(paper: LedgerContext) -> dict[str, Any]:
    """모의투자 성적: always the paper ledger's, whatever the mode."""
    data = DayData(paper)
    check_days = list(data.runs)
    fills = [f for f in repo.fills_of_ledger(paper.conn, "paper") if f.filled_at <= paper.now]
    ret = None
    baseline_pct = None
    if long_record(paper) and paper.contributions > 0:
        amount = paper.total - paper.contributions
        ret = {"pct": fmt.ret2(amount / paper.contributions), "amount": fmt.krw(amount)}
        last = paper.snapshots[-1]
        if last.baseline_krw is not None and last.contributions > 0:
            baseline_pct = fmt.ret2((last.baseline_krw - last.contributions) / last.contributions)
    return {
        "since": fmt.day(paper.start_date),
        "checks": len(check_days),
        "rebalances": sum(1 for e in paper.events if e.kind == "rebalance"),
        "failures": sum(1 for d in check_days if data.check_failed(d)),
        "paperFills": len(fills),
        "ret": ret,
        "baselinePct": baseline_pct,
    }


# ── the preview ──────────────────────────────────────────────────────────────────────────


def _outside_instrument(h: Any) -> dict[str, Any]:
    market = Market.US if h.currency is Currency.USD else Market.KR
    inst = Instrument(
        instrument_id=f"{market.value}:{h.symbol}",
        market=market,
        currency=h.currency,
        kind=Kind.STOCK,
        ticker=h.symbol,
        name=h.name,
        yahoo_symbol=h.symbol,
    )
    out = instrument_json(inst)
    out["initials"] = initials(inst)
    return out


def _stage_orders(data: PreviewData) -> list[dict[str, Any]]:
    """The first orders as CONTRACT Stage objects (sell -> buy, approximate amounts). The live
    ledger never converts (D47): no 'fx' stage; the conversion that would bring the mix to the
    targets is the preview's `fxSuggestion`, the owner's to make."""
    plan: Plan = data.plan
    due_of = {(spec.kind, spec.market): data.due[spec.seq] for spec in data.specs}
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for n, o in enumerate((*plan.sells, *plan.buys), start=1):
        at = due_of[(o.stage, StageMarket(o.market.value))]
        order: dict[str, Any] = {
            "id": f"preview-{n}",
            "market": o.market.value,
            "side": o.side.value,
            "instrument": instrument_json(o.instrument),
            "qty": o.qty,
            "price": fmt.krw(o.est_price) if o.currency is Currency.KRW else fmt.usd(o.est_price),
            "approx": True,
            "at": fmt.iso(at),
            "status": "pending",
        }
        if o.currency is Currency.KRW:
            order["amountKrw"] = fmt.krw(o.est_gross)
            order["fee"] = {"krw": fmt.krw(o.est_fee)}
        else:
            order["amountUsd"] = fmt.usd(o.est_gross)
            order["fee"] = {"usd": fmt.usd(o.est_fee)}
        by_kind.setdefault(o.stage.value, []).append(order)
    out: list[dict[str, Any]] = []
    for kind in ("sell", "buy"):
        orders = by_kind.get(kind)
        if not orders:
            continue
        orders.sort(key=lambda o: str(o["at"]))
        out.append({"kind": kind, "status": "pending", "at": orders[0]["at"], "orders": orders})
    return out


def preview_json(data: PreviewData | NotComputable) -> dict[str, Any]:
    if isinstance(data, NotComputable):
        return {"kind": "not-computable", "at": fmt.iso(data.at), "cause": data.cause}
    return {
        "kind": "ok",
        "computedAt": fmt.iso(data.computed_at),
        "hash": data.hash,
        "basis": {
            "balanceAt": fmt.iso(data.snapshot.confirmed_at),
            "priceAt": fmt.iso(data.price_at or data.computed_at),
            "fxRate": fmt.rate(data.rate.rate),
            "fxAt": fmt.iso(data.rate.as_of),
        },
        "current": [
            {"label": label, "krw": fmt.krw(krw)}
            | ({} if inst is None else {"instrument": instrument_json(inst)})
            for label, inst, krw in data.current
        ],
        "target": [
            {"ruleId": RULE_ID, "instrument": instrument_json(inst), "pct": float(pct)}
            for inst, pct in data.targets
        ],
        "stages": _stage_orders(data),
        "outside": [
            {"instrument": _outside_instrument(h), "qty": float(h.qty), "approxKrw": fmt.krw(krw)}
            for h, krw in data.outside
        ],
        # D48: the owner's money of the next check's day, which that check leaves for the next.
        "newMoney": None
        if not data.new_money or data.new_money_from is None
        else live_view.new_money_json(data.new_money, data.new_money_from),
        "fxSuggestion": live_view.fx_suggestion_json(data.suggestion),  # D47
    }


# ── the checks ───────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Checks:
    preflight: list[dict[str, Any]]
    preview: PreviewData | NotComputable
    can_turn_on: dict[str, Any]


def _health_row(paper: LedgerContext) -> dict[str, Any]:
    """'작동 정상': the engine's own data (the paper ledger's health) has no stale source and
    no red to-do."""
    report = health_view.health(paper, include_live=False)
    summary = report["summary"]
    stale = [s for s in report["sources"] if s["state"] in ("stale", "maintenance")]
    red = [t for t in report["todos"] if t["severity"] == "red"]
    if not stale and not red:
        return {"id": "health", "ok": True, "facts": {"lastCheckAt": summary["lastCheckAt"] or ""}}
    source = stale[0]["id"] if stale else red[0]["kind"]
    return {
        "id": "health",
        "ok": False,
        "facts": {"count": len(stale) + len(red), "source": source},
    }


def _link_row(cfg: Config, conn: sqlite3.Connection, now: datetime) -> dict[str, Any]:
    check = live.link_check(conn, cfg, now)
    facts: dict[str, Any] = {}
    if check.ok:
        if check.checked_at is not None:
            facts["checkedAt"] = fmt.iso(check.checked_at)
        if check.account_tail:
            facts["account"] = check.account_tail
    elif check.cause:
        facts["cause"] = check.cause
    if check.key_expires is not None and check.days_left is not None:
        facts["expiresAt"] = fmt.day(check.key_expires)
        facts["daysLeft"] = check.days_left
    return {"id": "toss-link", "ok": check.ok, "facts": facts}


def _freshness_row(
    data: PreviewData | NotComputable, conn: sqlite3.Connection, cfg: Config, now: datetime
) -> dict[str, Any]:
    if isinstance(data, PreviewData):
        return {
            "id": "freshness",
            "ok": True,
            "facts": {
                "balanceAt": fmt.iso(data.snapshot.confirmed_at),
                "priceAt": fmt.iso(data.price_at or data.computed_at),
                "fxAt": fmt.iso(data.rate.as_of),
            },
        }
    snap = live_repo.latest_snapshot(conn)
    if snap is None or now - snap.confirmed_at > cfg.broker_max_age or not snap.quiet:
        facts: dict[str, Any] = {"source": "toss-balance"}
        if snap is not None:
            facts["basisDate"] = fmt.day(kst_date(snap.confirmed_at))
        return {"id": "freshness", "ok": False, "facts": facts}
    for series in ("kr-quotes", "us-quotes", "fx"):
        row = repo.get_freshness(conn, series)
        if row is not None and row.state == "stale":
            return {
                "id": "freshness",
                "ok": False,
                "facts": {"source": series, "basisDate": str(row.basis or "")[:10]},
            }
    return {"id": "freshness", "ok": False, "facts": {"source": "other"}}


def checks(paper: LedgerContext, now: datetime) -> Checks:
    conn, cfg = paper.conn, paper.cfg
    data = live.preview_data(conn, cfg, now)
    health = _health_row(paper)
    link = _link_row(cfg, conn, now)
    fresh = _freshness_row(data, conn, cfg, now)
    if (
        not fresh["ok"]
        and not health["ok"]
        and fresh["facts"].get("source") == health["facts"].get("source")
    ):
        fresh["sameCauseAs"] = "health"
    elif not fresh["ok"] and not link["ok"] and fresh["facts"].get("source") == "toss-balance":
        # No fresh account picture because the tick cannot look at Toss: one cause, not two.
        fresh["sameCauseAs"] = "toss-link"
    push = {"id": "push", "ok": True, "warn": True, "facts": {"devices": 0}}
    preflight = [health, link, fresh, push]
    if live.cancel_failed(conn) or live.cancel_pending(conn):
        # An order of the last live period may still fill: its cancel must finish first (the
        # open order also keeps the account busy, so the freshness row fails with it).
        can: dict[str, Any] = {"ok": False, "cause": "cancel-pending"}
    elif any(not r["ok"] for r in preflight):
        can = {"ok": False, "cause": "checks"}
    elif isinstance(data, NotComputable):
        can = {"ok": False, "cause": "preview"}
    else:
        can = {"ok": True}
    return Checks(preflight, data, can)


def store(
    conn: sqlite3.Connection, data: PreviewData | NotComputable, payload: dict[str, Any]
) -> None:
    if isinstance(data, PreviewData):
        live.store_preview(conn, data, payload)


# ── GET /api/mode ────────────────────────────────────────────────────────────────────────


def mode(ctx: LedgerContext) -> dict[str, Any]:
    conn, cfg, now = ctx.conn, ctx.cfg, ctx.now
    paper = ctx if ctx.ledger_id == "paper" else LedgerContext(conn, cfg, "paper", now)
    current = live.mode_of(conn)
    live_json: dict[str, Any] | None = None
    off_json: dict[str, Any] | None = None
    periods = live.live_periods(conn)
    if periods:
        on_at, off_at = periods[-1]
        if current == "live" and off_at is None:
            since = kst_date(on_at)
            live_json = {"since": fmt.day(since), "days": _weekdays(since, kst_date(now))}
        elif off_at is not None:
            off_json = {
                "from": fmt.day(kst_date(on_at)),
                "to": fmt.day(kst_date(off_at)),
                "offAt": fmt.iso(off_at),
            }
    failed = live_view.cancel_failed_orders(conn)
    pending = live_view.cancel_pending_orders(conn)
    out: dict[str, Any] = {
        "mode": current,
        "live": live_json,
        "liveOff": off_json,
        "twoLedgers": None,
        "performance": _performance(paper),
        "preflight": None,
        "preview": None,
        "cancelFailed": failed or None,
        "cancelPending": pending or None,
        "canTurnOn": {"ok": True},
        "offPreview": off_preview(ctx) if current == "live" else None,
        "liveCash": None,
    }
    if current == "live":
        live_ctx = ctx if ctx.ledger_id == "live" else LedgerContext(conn, cfg, "live", now)
        out["liveCash"] = live_view.live_cash(live_ctx)
    if current == "paper":
        found = checks(paper, now)
        out["preflight"] = found.preflight
        out["preview"] = preview_json(found.preview)
        out["canTurnOn"] = found.can_turn_on
        if isinstance(found.preview, PreviewData):
            with transaction(conn):
                store(conn, found.preview, out["preview"])
    return out
