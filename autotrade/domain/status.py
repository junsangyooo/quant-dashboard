"""The rule status chip: one per rule, by fixed priority (인계 12).

시세 대기 > 일부 실패 > 리밸런싱 중 > 출금 대기 > 휴장 > 리밸런싱 예정 > 목표 범위 안.
Values follow autotrade/CONTRACT.md (RuleStatus).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RuleStatus(str, Enum):
    QUOTE_WAIT = "quote-wait"
    PARTIAL_FAILED = "partial-failed"
    IN_PROGRESS = "in-progress"
    WITHDRAW_WAIT = "withdraw-wait"
    HOLIDAY = "holiday"
    SCHEDULED = "scheduled"
    IN_RANGE = "in-range"


PRIORITY: tuple[RuleStatus, ...] = (
    RuleStatus.QUOTE_WAIT,
    RuleStatus.PARTIAL_FAILED,
    RuleStatus.IN_PROGRESS,
    RuleStatus.WITHDRAW_WAIT,
    RuleStatus.HOLIDAY,
    RuleStatus.SCHEDULED,
    RuleStatus.IN_RANGE,
)


@dataclass(frozen=True)
class StatusFlags:
    quote_wait: bool = False
    partial_failed: bool = False
    in_progress: bool = False
    withdraw_wait: bool = False
    holiday: bool = False
    scheduled: bool = False


def rule_status(flags: StatusFlags) -> RuleStatus:
    active = {
        RuleStatus.QUOTE_WAIT: flags.quote_wait,
        RuleStatus.PARTIAL_FAILED: flags.partial_failed,
        RuleStatus.IN_PROGRESS: flags.in_progress,
        RuleStatus.WITHDRAW_WAIT: flags.withdraw_wait,
        RuleStatus.HOLIDAY: flags.holiday,
        RuleStatus.SCHEDULED: flags.scheduled,
    }
    for status in PRIORITY:
        if active.get(status, False):
            return status
    return RuleStatus.IN_RANGE
