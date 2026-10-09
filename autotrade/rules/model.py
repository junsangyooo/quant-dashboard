"""Rule definitions: what a rule holds and when it acts. Stored as JSON in the rules table.

A fixed rule names its instruments, their in-rule targets, the drift threshold and its share of
the assets. 'display' carries the numbers the rules screen draws (tiles for fixed rules); the web
writes the words (autotrade/CONTRACT.md).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class RuleTarget:
    instrument_id: str
    weight: Decimal


@dataclass(frozen=True)
class RuleDef:
    rule_id: str
    name: str
    kind: str  # 'fixed' | 'ai'
    asset_share: Decimal  # target share of all assets (1 = 100%)
    targets: tuple[RuleTarget, ...]
    threshold: Decimal  # drift band, fraction (0.02 = 2%p)
    check_time: str = "08:30"
    display: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        total = sum((t.weight for t in self.targets), Decimal(0))
        if total != Decimal(1):
            raise ValueError(f"{self.rule_id}: targets sum to {total}, not 1")
        if not Decimal(0) < self.threshold < Decimal(1):
            raise ValueError(f"{self.rule_id}: threshold {self.threshold} out of range")

    @property
    def instrument_ids(self) -> tuple[str, ...]:
        return tuple(t.instrument_id for t in self.targets)

    def target_of(self, instrument_id: str) -> Decimal:
        for t in self.targets:
            if t.instrument_id == instrument_id:
                return t.weight
        raise KeyError(instrument_id)

    def to_json(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "name": self.name,
            "kind": self.kind,
            "asset_share": str(self.asset_share),
            "targets": [
                {"instrument_id": t.instrument_id, "weight": str(t.weight)} for t in self.targets
            ],
            "threshold": str(self.threshold),
            "check_time": self.check_time,
            "display": self.display,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> RuleDef:
        return cls(
            rule_id=str(data["rule_id"]),
            name=str(data["name"]),
            kind=str(data["kind"]),
            asset_share=Decimal(str(data["asset_share"])),
            targets=tuple(
                RuleTarget(str(t["instrument_id"]), Decimal(str(t["weight"])))
                for t in data["targets"]
            ),
            threshold=Decimal(str(data["threshold"])),
            check_time=str(data.get("check_time", "08:30")),
            display=dict(data.get("display", {})),
        )
