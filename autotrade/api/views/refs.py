"""Instrument and RuleRef objects of CONTRACT.md 공통 타입."""

from __future__ import annotations

from typing import Any

from autotrade.domain.instruments import Instrument
from autotrade.rules.model import RuleDef

# Figma draws these logo stand-ins (디자인 page, read 2026-10-09): KOSPI200 ETF 'K2',
# S&P 500 ETF 'SP', 삼성전자 '삼', NVDA 'NV', BTC 'B'. Cash rows get currency symbols in the web.
INITIALS_OVERRIDE = {"069500": "K2", "SPYM": "SP", "SPLG": "SP"}


def initials(inst: Instrument) -> str:
    """Logo stand-in, following Figma: an explicit value for the index ETFs, otherwise the first
    Hangul syllable of a Korean name, the first letter of a coin ticker, or the first two
    letters of the ticker."""
    if inst.ticker in INITIALS_OVERRIDE:
        return INITIALS_OVERRIDE[inst.ticker]
    first = inst.name[:1]
    if "\uac00" <= first <= "\ud7a3":
        return first
    if inst.ticker.isdigit() and first.isascii() and first.isalpha():
        # A Korean company named in Latin letters first: 'HD현대일렉트릭' 'HD', 'SK바이오팜' 'SK'.
        lead = ""
        for ch in inst.name:
            if not (ch.isascii() and ch.isalpha()) or len(lead) == 2:
                break
            lead += ch
        return lead.upper()
    letters = [c for c in inst.ticker if c.isalnum()]
    return "".join(letters[: 1 if inst.kind.value == "coin" else 2]).upper()


def instrument(inst: Instrument) -> dict[str, Any]:
    return {
        "id": inst.instrument_id,
        "name": inst.name,
        "kind": inst.kind.value,
        "market": inst.market.value,
        "currency": inst.currency.value,
        "initials": initials(inst),
    }


def rule_ref(rule: RuleDef, color_index: int = 0) -> dict[str, Any]:
    return {
        "id": rule.rule_id,
        "name": rule.name,
        "ai": rule.kind == "ai",
        "colorIndex": color_index,
    }
