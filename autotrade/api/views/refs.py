"""Instrument and RuleRef objects of CONTRACT.md 공통 타입."""

from __future__ import annotations

from typing import Any

from autotrade.domain.instruments import Instrument
from autotrade.rules.model import RuleDef


def initials(name: str) -> str:
    """Logo stand-in: the first two letters or digits of the name ('KOSPI200 ETF' -> 'KO',
    'S&P 500 ETF' -> 'SP', '삼성전자' -> '삼성')."""
    chars = [c for c in name if c.isalnum()]
    return "".join(chars[:2]).upper()


def instrument(inst: Instrument) -> dict[str, Any]:
    return {
        "id": inst.instrument_id,
        "name": inst.name,
        "kind": inst.kind.value,
        "market": inst.market.value,
        "currency": inst.currency.value,
        "initials": initials(inst.name),
    }


def rule_ref(rule: RuleDef, color_index: int = 0) -> dict[str, Any]:
    return {
        "id": rule.rule_id,
        "name": rule.name,
        "ai": rule.kind == "ai",
        "colorIndex": color_index,
    }
