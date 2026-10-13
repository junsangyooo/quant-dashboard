"""The rule status chip: one per rule, by fixed priority (인계 12).

시세 대기 > 일부 실패 > 리밸런싱 중 > 휴장 > 리밸런싱 예정 > 환전 제안 > 목표 범위 안.
Values follow autotrade/CONTRACT.md (RuleStatus).

There is no '출금 대기' status: only the live ledger has withdrawal waits, and they hold their own
money without stopping any order (PHASE3.md 2.5); the composition row shows the money and date.

'환전 제안' is the live ledger's alone (D47, 2026-10-13): its won and dollars are off the rule's
targets by more than the band, and only the owner can move money between them (in the Toss app).
Nothing waits on it; it is a word on the chip, and the screens say how much to convert.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RuleStatus(str, Enum):
    QUOTE_WAIT = "quote-wait"
    PARTIAL_FAILED = "partial-failed"
    IN_PROGRESS = "in-progress"
    HOLIDAY = "holiday"
    SCHEDULED = "scheduled"
    FX_SUGGEST = "fx-suggest"
    IN_RANGE = "in-range"


PRIORITY: tuple[RuleStatus, ...] = (
    RuleStatus.QUOTE_WAIT,
    RuleStatus.PARTIAL_FAILED,
    RuleStatus.IN_PROGRESS,
    RuleStatus.HOLIDAY,
    RuleStatus.SCHEDULED,
    RuleStatus.FX_SUGGEST,
    RuleStatus.IN_RANGE,
)


@dataclass(frozen=True)
class StatusFlags:
    quote_wait: bool = False
    partial_failed: bool = False
    in_progress: bool = False
    holiday: bool = False
    scheduled: bool = False
    fx_suggest: bool = False


def rule_status(flags: StatusFlags) -> RuleStatus:
    active = {
        RuleStatus.QUOTE_WAIT: flags.quote_wait,
        RuleStatus.PARTIAL_FAILED: flags.partial_failed,
        RuleStatus.IN_PROGRESS: flags.in_progress,
        RuleStatus.HOLIDAY: flags.holiday,
        RuleStatus.SCHEDULED: flags.scheduled,
        RuleStatus.FX_SUGGEST: flags.fx_suggest,
    }
    for status in PRIORITY:
        if active.get(status, False):
            return status
    return RuleStatus.IN_RANGE
