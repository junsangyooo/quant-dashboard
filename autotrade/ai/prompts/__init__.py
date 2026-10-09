"""The prompts and answer schemas of the AI rule, one pair of files per kind of question.

  <name>.md           '# 시스템' (the short system prompt) and '# 지시' (the steps); the data
                      packet the code builds is appended after the steps, as in T26
  <name>.schema.json  the JSON schema of the answer (D26: every answer has a fixed shape)

Placeholders in a schema: "__CONDITION__" is one condition in the fixed form, "__PICK__" one
company of a discovery, and {"enum": ["__METRICS__"]} the metric keys a call may answer with.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from autotrade.domain.metrics import UNITS

HERE = Path(__file__).resolve().parent
NAMES = (
    "extract",
    "screen",
    "sell_confirm",
    "buy_confirm",
    "monthly_review",
    "discovery",
    "switch",
)
CONFIDENCE = ["상", "중상", "중", "중하", "하"]

CONDITION: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["type"],
    "properties": {
        "type": {"enum": ["level", "streak", "event", "price", "valuation"]},
        "metric": {"type": ["string", "null"], "maxLength": 80},
        "op": {"enum": ["<", "<=", ">", ">=", None]},
        "value": {"type": ["number", "null"]},
        "unit": {"enum": [*UNITS, None]},
        "change": {"enum": ["yoy", "qoq", None]},
        "direction": {"enum": ["down", "up", None]},
        "periods": {"type": ["integer", "null"], "minimum": 1, "maximum": 8},
        "period": {"type": ["string", "null"], "maxLength": 10},
        "kind": {"type": ["string", "null"], "maxLength": 40},
        "text": {"type": ["string", "null"], "maxLength": 120},
        "note": {"type": ["string", "null"], "maxLength": 200},
    },
}

PICK: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "market",
        "ticker",
        "name",
        "yahoo",
        "theme",
        "rationale",
        "priced_in",
        "risks",
        "confidence",
        "confirm",
        "invalidate",
        "buy",
        "sources",
    ],
    "properties": {
        "market": {"enum": ["KR", "US"]},
        "ticker": {"type": "string", "pattern": "^[0-9A-Z.\\-]{1,12}$"},
        "name": {"type": "string", "maxLength": 60},
        "yahoo": {"type": "string", "maxLength": 20},
        "theme": {"type": "string", "maxLength": 60},
        "rationale": {"type": "string", "maxLength": 600},
        "priced_in": {"type": "string", "maxLength": 300},
        "risks": {"type": "string", "maxLength": 300},
        "confidence": {"enum": CONFIDENCE},
        "confirm": {"type": "array", "maxItems": 4, "items": CONDITION},
        "invalidate": {"type": "array", "minItems": 1, "maxItems": 4, "items": CONDITION},
        "buy": {"type": "array", "maxItems": 2, "items": CONDITION},
        "sources": {
            "type": "array",
            "maxItems": 6,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["title", "url", "date"],
                "properties": {
                    "title": {"type": "string", "maxLength": 160},
                    "url": {"type": "string", "maxLength": 300},
                    "date": {"type": "string", "maxLength": 10},
                },
            },
        },
    },
}


class PromptError(ValueError):
    pass


@dataclass(frozen=True)
class Prompt:
    name: str
    system: str
    steps: str
    schema: dict[str, Any]

    def with_metrics(self, keys: list[str]) -> dict[str, Any]:
        """The schema with the metric keys this call may answer with."""
        schema = copy.deepcopy(self.schema)

        def fill(node: Any) -> Any:
            if isinstance(node, dict):
                if node.get("enum") == ["__METRICS__"]:
                    return {"enum": list(keys)}
                return {k: fill(v) for k, v in node.items()}
            if isinstance(node, list):
                return [fill(v) for v in node]
            return node

        filled: dict[str, Any] = fill(schema)
        return filled


def _expand(node: Any) -> Any:
    if node == "__CONDITION__":
        return copy.deepcopy(CONDITION)
    if node == "__PICK__":
        return copy.deepcopy(PICK)
    if isinstance(node, dict):
        return {k: _expand(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_expand(v) for v in node]
    return node


def _sections(text: str, name: str) -> tuple[str, str]:
    parts: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        if line.startswith("# "):
            current = line[2:].strip()
            parts[current] = []
        elif current is not None:
            parts[current].append(line)
    if "시스템" not in parts or "지시" not in parts:
        raise PromptError(f"{name}.md needs '# 시스템' and '# 지시'")
    return "\n".join(parts["시스템"]).strip(), "\n".join(parts["지시"]).strip()


def load(name: str, folder: Path = HERE) -> Prompt:
    if name not in NAMES:
        raise PromptError(f"no prompt named {name}")
    system, steps = _sections((folder / f"{name}.md").read_text(encoding="utf-8"), name)
    schema = _expand(json.loads((folder / f"{name}.schema.json").read_text(encoding="utf-8")))
    if not isinstance(schema, dict):
        raise PromptError(f"{name}.schema.json is not an object")
    return Prompt(name, system, steps, schema)
