"""모의투자 v2 라우터(T-40 · T-41 · TASKS P1-09): 목록 · 시작 전 확인 · 시작 · 보기 · 멈추기 · 확인 돌리기.

일은 실행 흐름 `run/paper.py`(`PaperV2` · 20:10 확인 · 다음 거래일 일봉 시가 체결)예요.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import Field

from ..copy import texts as T
from ..run.paper import PaperV2
from ..security.vault import VaultError
from .http import ERRORS, json_body
from .models import ApiModel, Int, Num, Str, opt


class PaperHolding(ApiModel):
    sym: Str
    qty: Int
    avg: Num
    entry_d: Str = opt()
    peak: Num = opt()


class PaperPlan(ApiModel):
    sym: Str
    side: Literal["buy", "sell"]
    value: Num = opt()
    qty: Int = opt()
    reason: list[Str]
    judged: Str = opt()
    kind: Str = opt()
    close: Num | None = opt()
    rank: Int = opt()  # 순위 교체 · 목표 비중의 순위(매수 계획)


class PaperTrade(ApiModel):
    id: Int
    run_id: Int
    d: Str
    symbol: Str
    side: Literal["buy", "sell"]
    qty: Int
    price: Num
    amount: Num
    cost: Num
    pnl: Num | None
    reason: list[Str]


class PaperRunV2(ApiModel):
    id: Int
    status: Literal["running", "ended"]
    strategy_id: Int | None
    name: Str
    version_no: Int | None
    cash0: Num
    cash: Num
    total: Num
    return_: Num = Field(alias="return")
    holdings: list[PaperHolding]
    plans: list[PaperPlan]
    trades: list[PaperTrade]
    curve: list[tuple[Str, Num]]
    last_date: Str | None
    started_at: Str
    ended_at: Str | None
    diff_line: Str
    first_check: Str
    bench_return: Num | None


class PaperRuns(ApiModel):
    runs: list[PaperRunV2]


class PaperPreview(ApiModel):
    name: Str
    version_no: Int
    limits: Str
    line: Str
    already: Str
    running_id: Int | None
    check: Str
    fill: Str
    first_line: Str


class PaperChecked(ApiModel):
    advanced: list[Int]  # 확인을 이어 돈 모의투자 id


def paper_router(*, paper2: PaperV2) -> APIRouter:
    r = APIRouter(responses=ERRORS)
    run: dict[str, Any] = {"response_model": PaperRunV2, "response_model_exclude_unset": True}

    @r.get("/api/v2/paper", response_model=PaperRuns, response_model_exclude_unset=True)
    def paper2_list() -> dict[str, Any]:
        return {"runs": paper2.list()}

    @r.post("/api/v2/paper/start", **run)
    async def paper2_start(request: Request) -> dict[str, Any]:
        b = await json_body(request)
        try:
            vid = int(b.get("version_id"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise VaultError(T.pick_version) from None
        return await asyncio.to_thread(paper2.start, vid, b.get("cash"))

    @r.get("/api/v2/paper/preview", response_model=PaperPreview, response_model_exclude_unset=True)
    def paper2_preview(version_id: int) -> dict[str, Any]:
        return paper2.preview(version_id)

    @r.get("/api/v2/paper/{rid}", **run)
    def paper2_view(rid: int) -> dict[str, Any]:
        return paper2.view(rid)

    @r.post("/api/v2/paper/{rid}/stop", **run)
    def paper2_stop(rid: int) -> dict[str, Any]:
        return paper2.stop(rid)

    @r.post("/api/v2/paper/check", response_model=PaperChecked, response_model_exclude_unset=True)
    async def paper2_check() -> dict[str, Any]:
        return {"advanced": await asyncio.to_thread(paper2.tick)}

    return r
