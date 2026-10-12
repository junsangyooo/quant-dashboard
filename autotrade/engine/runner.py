"""Stage runner: executes due stages in order and applies the fills (ops notes step 6-7).

- A stage is due when its time has come and every stage it waits on is done.
- Fills are recorded at the stage's time (the paper price is that session's open), so the result
  does not depend on when the job happened to run.
- A stage that fails is sent again the next trading day at the same time ('다음 날 같은 시각');
  if that fails too, or the broker rejected the order, it becomes a manual action ('직접 할 일').
- When a stage completes, stages waiting on it move to their next slot after it.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from autotrade.broker.base import (
    Executor,
    Failed,
    FxFilled,
    FxRequest,
    Outcome,
    TradeFilled,
    TradeRequest,
    Waiting,
)
from autotrade.config import Config
from autotrade.db import repo
from autotrade.db.models import OrderRow, PlanRow, StageRow
from autotrade.domain.instruments import Currency, Market
from autotrade.domain.ledger import FxFill, TradeFill, apply_fx, apply_trade
from autotrade.domain.money import ZERO
from autotrade.domain.planner import FxDirection, Side
from autotrade.domain.stages import StageMarket
from autotrade.engine import sleeves
from autotrade.engine.common import (
    idem_key,
    refresh_cash_parts,
    slotter_for,
    withdraw_wait_amounts,
)
from autotrade.market.calendar import KRX, calendar_for
from autotrade.market.service import FetchErrors
from autotrade.timeutil import et_date, kst_date

DONE = "done"
PENDING = "pending"
FAILED = "failed"
TODO = "todo"


@dataclass
class StageResult:
    stage_id: int
    plan_id: int
    kind: str
    market: str
    status: str
    orders: list[dict[str, Any]] = field(default_factory=list)


def _session_date(stage: StageRow) -> date:
    return et_date(stage.due_at) if stage.market == "US" else kst_date(stage.due_at)


def _deadline_passed(cfg: Config, stage: StageRow, at: datetime) -> bool:
    if stage.market == "FX":
        d = kst_date(stage.due_at)
        return at > KRX.session_close(d)
    market = Market(stage.market)
    lag = cfg.kr_publication_lag if market is Market.KR else cfg.us_publication_lag
    return at > calendar_for(market).session_close(_session_date(stage)) + lag


def eligible_stages(conn: sqlite3.Connection, ledger_id: str, at: datetime) -> list[StageRow]:
    out: list[StageRow] = []
    by_plan: dict[int, list[StageRow]] = {}
    for stage in repo.pending_stages(conn, ledger_id):
        if stage.due_at > at:
            continue
        if stage.plan_id not in by_plan:
            by_plan[stage.plan_id] = repo.stages_of(conn, stage.plan_id)
        status = {s.seq: s.status for s in by_plan[stage.plan_id]}
        if all(status.get(dep) == DONE for dep in stage.depends_on):
            out.append(stage)
    return out


def _plan_fx_rate(conn: sqlite3.Connection, plan_id: int) -> Decimal | None:
    """Rate of the conversion this plan made (cost basis of its dollar buys)."""
    for fill in repo.fills_of_plan(conn, plan_id):
        if fill.kind == "fx" and fill.krw_rate is not None:
            return fill.krw_rate
    return None


def _execute(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    stage: StageRow,
    order: OrderRow,
    at: datetime,
    executor: Executor,
    fetch: FetchErrors,
) -> Outcome:
    # A rule spends and sells only its own part of the shared ledger (engine/sleeves.py).
    rule_id = repo.get_plan(conn, order.plan_id).rule_id
    state = sleeves.view(conn, ledger_id, rule_id)
    held = (
        withdraw_wait_amounts(repo.cash_parts(conn, ledger_id))
        if rule_id == sleeves.BASE_RULE
        else {}
    )
    deadline = _deadline_passed(cfg, stage, at)
    if order.side == "fx":
        if order.fx_direction is None:
            raise ValueError(f"order {order.order_id}: fx without direction")
        direction = FxDirection(order.fx_direction)
        source = direction.source
        return executor.fx(
            FxRequest(
                order_id=order.order_id,
                direction=direction,
                amount=order.est_amount,
                due_at=stage.due_at,
                available=state.cash_of(source) - held.get(source, ZERO),
                fetch_error=fetch.fx,
                deadline_passed=deadline,
            )
        )
    if order.instrument_id is None or order.qty is None:
        raise ValueError(f"order {order.order_id}: trade without instrument or qty")
    inst = repo.get_instrument(conn, order.instrument_id)
    return executor.trade(
        TradeRequest(
            order_id=order.order_id,
            instrument=inst,
            side=Side(order.side),
            qty=order.qty,
            session_date=_session_date(stage),
            due_at=stage.due_at,
            available_cash=state.cash_of(inst.currency) - held.get(inst.currency, ZERO),
            held_qty=state.qty_of(inst.instrument_id),
            fetch_error=fetch.bars.get(inst.instrument_id),
            deadline_passed=deadline,
        )
    )


def _apply_trade_fill(
    conn: sqlite3.Connection,
    ledger_id: str,
    plan: PlanRow,
    stage: StageRow,
    order: OrderRow,
    filled: TradeFilled,
    executor_name: str,
    at: datetime,
) -> dict[str, Any]:
    if order.instrument_id is None:
        raise ValueError("trade fill without instrument")
    inst = repo.get_instrument(conn, order.instrument_id)
    krw_rate: Decimal | None = None
    if inst.currency is Currency.USD:
        krw_rate = _plan_fx_rate(conn, plan.plan_id)
        if krw_rate is None:
            quote = repo.fx_at(conn, stage.due_at)
            if quote is None:
                raise ValueError("no rate to value a dollar trade")
            krw_rate = quote.rate
    fill = TradeFill(
        instrument_id=inst.instrument_id,
        currency=inst.currency,
        side=Side(order.side),
        qty=filled.qty,
        price=filled.price,
        fee=filled.fee,
        krw_rate=krw_rate,
        gross_amount=filled.gross,
    )
    state = apply_trade(repo.load_state(conn, ledger_id), fill)
    repo.save_state(conn, ledger_id, state, at)
    sleeves.apply_trade_fill(conn, ledger_id, plan.rule_id, fill, at)
    fee_krw = fill.to_krw(filled.fee)
    repo.insert_fill(
        conn,
        repo.NewFill(
            order_id=order.order_id,
            ledger_id=ledger_id,
            kind="trade",
            instrument_id=inst.instrument_id,
            side=order.side,
            fx_direction=None,
            currency=inst.currency,
            qty=filled.qty,
            price=filled.price,
            gross=filled.gross,
            fee=filled.fee,
            fee_krw=fee_krw,
            krw_rate=krw_rate,
            received=None,
            filled_at=filled.filled_at or stage.due_at,
            price_source=filled.price_source,
            executor=executor_name,
        ),
    )
    repo.mark_order_filled(conn, order.order_id, executor_name, at)
    return {
        "order_id": order.order_id,
        "outcome": "filled",
        "instrument_id": inst.instrument_id,
        "side": order.side,
        "qty": filled.qty,
        "price": filled.price,
        "gross": filled.gross,
        "fee": filled.fee,
        "fee_krw": fee_krw,
    }


def _apply_fx_fill(
    conn: sqlite3.Connection,
    ledger_id: str,
    stage: StageRow,
    order: OrderRow,
    filled: FxFilled,
    executor_name: str,
    at: datetime,
) -> dict[str, Any]:
    if order.fx_direction is None:
        raise ValueError("fx fill without direction")
    direction = FxDirection(order.fx_direction)
    fx_fill = FxFill(direction, filled.from_amount, filled.to_amount, filled.rate)
    state = apply_fx(repo.load_state(conn, ledger_id), fx_fill)
    repo.save_state(conn, ledger_id, state, at)
    sleeves.apply_fx_fill(conn, ledger_id, repo.get_plan(conn, order.plan_id).rule_id, fx_fill, at)
    repo.insert_fill(
        conn,
        repo.NewFill(
            order_id=order.order_id,
            ledger_id=ledger_id,
            kind="fx",
            instrument_id=None,
            side="fx",
            fx_direction=direction.value,
            currency=direction.source,
            qty=None,
            price=None,
            gross=filled.from_amount,
            fee=ZERO,
            fee_krw=ZERO,
            krw_rate=filled.rate,
            received=filled.to_amount,
            filled_at=filled.filled_at or stage.due_at,
            price_source=filled.price_source,
            executor=executor_name,
        ),
    )
    repo.mark_order_filled(conn, order.order_id, executor_name, at)
    return {
        "order_id": order.order_id,
        "outcome": "filled",
        "direction": direction.value,
        "from": filled.from_amount,
        "to": filled.to_amount,
        "rate": filled.rate,
    }


def _set_plan_status(
    conn: sqlite3.Connection,
    plan_id: int,
    status: str,
    at: datetime,
    completed: datetime | None = None,
) -> None:
    repo.set_plan_status(conn, plan_id, status, completed)
    event = repo.event_of_plan(conn, plan_id)
    if event is not None:
        repo.update_event(conn, event.event_id, at, status=status)


def _summarize_plan(conn: sqlite3.Connection, plan_id: int, at: datetime) -> None:
    fills = repo.fills_of_plan(conn, plan_id)
    event = repo.event_of_plan(conn, plan_id)
    if event is None:
        return
    payload = dict(event.payload)
    payload["fees_krw"] = sum((f.fee_krw for f in fills), ZERO)
    payload["fills"] = len(fills)
    retried = [
        o
        for o in repo.orders_of_ledger(conn, event.ledger_id)
        if o.plan_id == plan_id and o.attempt > 1
    ]
    payload["retried"] = bool(retried)
    repo.update_event(conn, event.event_id, at, payload=payload)


def _handle_failures(
    conn: sqlite3.Connection,
    cfg: Config,
    stage: StageRow,
    failed: list[tuple[OrderRow, Failed]],
    executor: Executor,
    at: datetime,
) -> str:
    slotter = slotter_for(cfg)
    retryable = stage.attempts == 0 and all(f.retryable for _, f in failed)
    detail = "; ".join(f"{o.instrument_id or 'FX'}: {f.detail}" for o, f in failed)
    if retryable:
        retry_at = slotter.retry_slot(StageMarket(stage.market), stage.due_at)
        for order, failure in failed:
            repo.mark_order_failed(
                conn,
                order.order_id,
                reason=failure.reason.value,
                detail=failure.detail,
                executor=executor.name,
                executed_at=at,
                retry_at=retry_at,
                manual=False,
            )
            plan = repo.get_plan(conn, order.plan_id)
            repo.insert_order(
                conn,
                repo.NewOrder(
                    idem_key=idem_key(
                        order.ledger_id,
                        plan.plan_date,
                        plan.rule_id,
                        order.stage,
                        order.market,
                        order.instrument_id or (order.fx_direction or "FX"),
                        order.attempt + 1,
                    ),
                    ledger_id=order.ledger_id,
                    plan_id=order.plan_id,
                    stage_id=order.stage_id,
                    stage=order.stage,
                    market=order.market,
                    instrument_id=order.instrument_id,
                    side=order.side,
                    fx_direction=order.fx_direction,
                    currency=order.currency,
                    qty=order.qty,
                    est_price=order.est_price,
                    est_amount=order.est_amount,
                    est_fee=order.est_fee,
                    est_rate=order.est_rate,
                    est_received=order.est_received,
                    attempt=order.attempt + 1,
                    retry_of=order.order_id,
                ),
                at,
            )
        repo.update_stage(
            conn,
            stage.stage_id,
            status=FAILED,
            due_at=retry_at,
            attempts=stage.attempts + 1,
            last_error=detail,
        )
        _set_plan_status(conn, stage.plan_id, "partial-failed", at)
        event = repo.event_of_plan(conn, stage.plan_id)
        if event is not None:
            payload = dict(event.payload)
            payload["retry_at"] = retry_at
            payload["failure"] = detail
            repo.update_event(conn, event.event_id, at, payload=payload)
        return FAILED
    for order, failure in failed:
        repo.mark_order_failed(
            conn,
            order.order_id,
            reason=failure.reason.value,
            detail=failure.detail,
            executor=executor.name,
            executed_at=at,
            retry_at=None,
            manual=True,
        )
    repo.update_stage(
        conn, stage.stage_id, status=TODO, attempts=stage.attempts + 1, last_error=detail
    )
    # Stages that wait on this one cannot run any more: release their orders and their cash.
    stages = repo.stages_of(conn, stage.plan_id)
    blocked = {stage.seq}
    for s in stages:  # in seq order, so dependencies come first
        if s.status == PENDING and any(dep in blocked for dep in s.depends_on):
            blocked.add(s.seq)
            repo.cancel_orders_of_stage(conn, s.stage_id)
            repo.update_stage(
                conn, s.stage_id, status=TODO, last_error=f"waits on stage {stage.seq}"
            )
    _set_plan_status(conn, stage.plan_id, "todo", at)
    return TODO


def _complete_stage(conn: sqlite3.Connection, cfg: Config, stage: StageRow, at: datetime) -> None:
    repo.update_stage(conn, stage.stage_id, status=DONE, completed_at=stage.due_at)
    slotter = slotter_for(cfg)
    stages = repo.stages_of(conn, stage.plan_id)
    finished = {s.seq: (s.completed_at or s.due_at) for s in stages if s.status == DONE}
    due_of = {s.seq: s.due_at for s in stages}
    for s in stages:
        if s.status != PENDING or not s.depends_on:
            continue
        after = max(finished.get(dep, due_of[dep]) for dep in s.depends_on)
        new_due = slotter.slot_after(StageMarket(s.market), after)
        if new_due > s.due_at:
            repo.update_stage(conn, s.stage_id, due_at=new_due)
            due_of[s.seq] = new_due
    stages = repo.stages_of(conn, stage.plan_id)
    if all(s.status == DONE for s in stages):
        _set_plan_status(conn, stage.plan_id, "done", at, completed=stage.due_at)
        _summarize_plan(conn, stage.plan_id, at)
    elif not any(s.status in (FAILED, TODO) for s in stages):
        plan = repo.get_plan(conn, stage.plan_id)
        if plan.status == "partial-failed":
            _set_plan_status(conn, stage.plan_id, "in-progress", at)


def execute_stage(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    stage: StageRow,
    at: datetime,
    executor: Executor,
    fetch: FetchErrors,
) -> StageResult:
    plan = repo.get_plan(conn, stage.plan_id)
    result = StageResult(stage.stage_id, stage.plan_id, stage.kind, stage.market, PENDING)
    failed: list[tuple[OrderRow, Failed]] = []
    waiting = False
    for order in repo.orders_of_stage(conn, stage.stage_id, [PENDING]):
        outcome = _execute(conn, cfg, ledger_id, stage, order, at, executor, fetch)
        if isinstance(outcome, TradeFilled):
            result.orders.append(
                _apply_trade_fill(conn, ledger_id, plan, stage, order, outcome, executor.name, at)
            )
        elif isinstance(outcome, FxFilled):
            result.orders.append(
                _apply_fx_fill(conn, ledger_id, stage, order, outcome, executor.name, at)
            )
        elif isinstance(outcome, Waiting):
            waiting = True
            result.orders.append(
                {"order_id": order.order_id, "outcome": "waiting", "detail": outcome.detail}
            )
        else:
            failed.append((order, outcome))
            result.orders.append(
                {
                    "order_id": order.order_id,
                    "outcome": "failed",
                    "reason": outcome.reason.value,
                    "detail": outcome.detail,
                }
            )
    if failed:
        result.status = _handle_failures(conn, cfg, stage, failed, executor, at)
    elif not waiting and not repo.orders_of_stage(conn, stage.stage_id, [PENDING]):
        _complete_stage(conn, cfg, stage, at)
        result.status = DONE
    refresh_cash_parts(conn, ledger_id, at)
    return result


def run_due_stages(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    at: datetime,
    executor: Executor,
    fetch: FetchErrors | None = None,
) -> list[StageResult]:
    """Execute every stage that is due at `at`, including ones that become due on the way."""
    errors = fetch or FetchErrors()
    tried: set[int] = set()
    results: list[StageResult] = []
    while True:
        due = [s for s in eligible_stages(conn, ledger_id, at) if s.stage_id not in tried]
        if not due:
            return results
        stage = due[0]
        tried.add(stage.stage_id)
        results.append(execute_stage(conn, cfg, ledger_id, stage, at, executor, errors))


def book_fill(
    conn: sqlite3.Connection,
    cfg: Config,
    ledger_id: str,
    order: OrderRow,
    filled: TradeFilled | FxFilled,
    executor_name: str,
    at: datetime,
) -> dict[str, Any] | None:
    """Book a fill the broker reported for `order` outside the stage loop: a conversion the
    reconciliation saw in the balances, or a fill that came after its plan was closed (live off,
    a resolved to-do). Once per order (fills.order_id is unique): None when already booked.
    A stage whose orders are all settled then completes as usual."""
    if repo.fill_of_order(conn, order.order_id) is not None:
        return None
    plan = repo.get_plan(conn, order.plan_id)
    stage = repo.get_stage(conn, order.stage_id)
    if isinstance(filled, FxFilled):
        out = _apply_fx_fill(conn, ledger_id, stage, order, filled, executor_name, at)
    else:
        out = _apply_trade_fill(conn, ledger_id, plan, stage, order, filled, executor_name, at)
    if (
        stage.status == PENDING
        and stage.due_at <= at
        and not repo.orders_of_stage(conn, stage.stage_id, [PENDING])
    ):
        done = {s.seq for s in repo.stages_of(conn, stage.plan_id) if s.status == DONE}
        if all(dep in done for dep in stage.depends_on):
            _complete_stage(conn, cfg, stage, at)
        # otherwise the runner completes it in its turn (its earlier stages first)
    refresh_cash_parts(conn, ledger_id, at)
    return out
