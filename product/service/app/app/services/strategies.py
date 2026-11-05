"""전략 저장(쓰기 일 · ARCHITECTURE 2-1 `services/strategies.py` · TASKS P1-09): 새 전략 · 새 버전 · 지우기 · 백테스트 기록.

- 저장은 문제가 있어도 돼요(R-P 머리): 문제 수와 판정 방식(`mode`)을 같이 적어요.
- 이름이 겹치면 끝에 ' (2)'처럼 숫자를 더해요(붙여 넣기 · 예시 복사 · 새 전략 모두 · 60자 안).
- 검사(없는 전략 · 지울 수 없는 전략)와 오류 글은 API(`api/strategies.py`)가 해요. 기록 시각(`now`)은 조립이 넘겨요.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date
from typing import Any

from ..domain import blocks as bk
from ..store import strategies as strategy_store
from ..store.db import DB


def unique_name(db: DB, name: str, skip: int | None = None) -> tuple[str, bool]:
    """이름이 겹치면 끝에 ' (2)'처럼 숫자를 더한다(붙여 넣기 · 예시 복사 · 새 전략 모두)."""
    taken = {r["name"] for r in strategy_store.strategy_names(db) if r["id"] != skip}
    if name not in taken:
        return name, False
    n = 2
    while True:
        tail = f" ({n})"
        cand = name[: 60 - len(tail)] + tail
        if cand not in taken:
            return cand, True
        n += 1


def save_version(db: DB, sid: int, body: dict[str, Any], *, dart: bool, now: Callable[[], str]) -> dict[str, Any]:
    a = bk.analyze(body["graph"], dart=dart)
    vid, no = strategy_store.add_version(db, sid, json.dumps(body, ensure_ascii=False), len(a["problems"]), now(),
                                         name=body["name"], template=a["mode"] or "")
    return {"version_id": vid, "no": no, "problems": len(a["problems"])}


def create(db: DB, body: dict[str, Any], *, source: Any, dart: bool, now: Callable[[], str]) -> dict[str, Any]:
    """새 전략 + 첫 버전(이름은 겹치지 않게 · `source`는 붙여 넣은 복사 글의 출처 · 없으면 None)."""
    body["name"] = unique_name(db, body["name"])[0]
    sid = strategy_store.add_strategy(db, body["name"], bk.mode_of(body["graph"]) or "",
                                      json.dumps(source, ensure_ascii=False) if source else None, now())
    return {"id": sid, "name": body["name"], **save_version(db, sid, body, dart=dart, now=now)}


def delete(db: DB, sid: int) -> None:
    strategy_store.delete_strategy(db, sid)


def record_backtest(db: DB, vid: int, at: str, start: date, end: date, cash: float) -> None:
    strategy_store.add_backtest_run(db, vid, at, start.isoformat(), end.isoformat(), cash)
