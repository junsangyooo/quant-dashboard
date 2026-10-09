"""Stand-ins for the subscription CLI (no real call anywhere, PHASE2.md §6).

- ScriptedRunner replaces subprocess.run inside ClaudeCli: it answers from a script keyed by
  the kind of question (recognised by the answer schema's required fields) and records every
  command line, working folder, environment and stdin it was given.
- fake_claude.py is a real executable for the end-to-end test of `python -m autotrade.jobs ai`.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

# The answer schema's required fields name the question.
KINDS = {
    ("metrics", "notes"): "extract",
    ("relevant", "touches", "reason"): "screen",
    ("trigger", "invalidate", "confirm", "bear_case", "bull_case", "verdict", "conviction"): "sell",
    ("why_here", "valuation", "decision", "reason", "risks", "conviction"): "buy",
    (
        "facts",
        "confirm",
        "invalidate",
        "valuation",
        "bear_case",
        "verdict",
        "conviction",
        "watch_next",
        "sell_conditions",
    ): "review",
    ("macro", "flows", "picks", "candidates"): "discovery",
    ("sold", "bought", "beats_cost", "decision", "reason"): "switch",
}
USAGE = {
    "input_tokens": 1200,
    "cache_creation_input_tokens": 300,
    "cache_read_input_tokens": 2500,
    "output_tokens": 400,
}  # 4,400 tokens a call


def kind_of(cmd: list[str]) -> str:
    schema = json.loads(cmd[cmd.index("--json-schema") + 1])
    return KINDS[tuple(schema["required"])]


Answer = Mapping[str, Any] | Callable[[list[str]], Mapping[str, Any]]


def envelope(output: Mapping[str, Any] | None, *, error: str | None = None) -> str:
    body: dict[str, Any] = {
        "type": "result",
        "subtype": "success" if error is None else "error_during_execution",
        "is_error": error is not None,
        "duration_ms": 1234,
        "result": error or "",
        "total_cost_usd": 0.0123,
        "usage": dict(USAGE),
    }
    if output is not None:
        body["structured_output"] = dict(output)
    return json.dumps(body, ensure_ascii=False)


@dataclass
class ScriptedRunner:
    """answers: kind -> list of answers, used in order. An answer is the structured output, or
    {'__exit__': code, '__stderr__': text} for a failed call, or a function of the command."""

    answers: dict[str, list[Answer]] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)

    def add(self, kind: str, *answers: Answer) -> None:
        self.answers.setdefault(kind, []).extend(answers)

    def __call__(self, cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        kind = kind_of(cmd)
        self.calls.append({"kind": kind, "cmd": cmd, **kwargs})
        queue = self.answers.get(kind)
        if not queue:
            raise AssertionError(f"no scripted answer for a {kind} call")
        answer = queue.pop(0)
        if callable(answer):
            answer = answer(cmd)
        if "__exit__" in answer:
            return subprocess.CompletedProcess(
                cmd, int(answer["__exit__"]), "", str(answer.get("__stderr__", ""))
            )
        if "__error__" in answer:
            return subprocess.CompletedProcess(
                cmd, 0, envelope(None, error=answer["__error__"]), ""
            )
        return subprocess.CompletedProcess(cmd, 0, envelope(answer), "")

    def prompts(self, kind: str) -> list[str]:
        return [c["cmd"][c["cmd"].index("-p") + 1] for c in self.calls if c["kind"] == kind]


def sell(verdict: str) -> dict[str, Any]:
    return {
        "trigger": "급락의 원인은 수주 취소 공시다",
        "invalidate": [{"index": 1, "status": "걸림", "evidence": "metric.op_margin.2026Q2 5.0"}],
        "confirm": [],
        "bear_case": "수주가 끊겼다",
        "bull_case": "잔고가 남았다",
        "verdict": verdict,
        "conviction": "중",
    }


def review(verdict: str, conditions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "facts": [{"key": "metric.op_margin.2026Q2", "value": 5.0, "meaning": "이익률이 낮다"}],
        "confirm": [],
        "invalidate": [],
        "valuation": {"state": "적정", "evidence": "PER 12"},
        "bear_case": "이익률 하락",
        "verdict": verdict,
        "conviction": "중",
        "watch_next": ["3분기 이익률"],
        "sell_conditions": conditions
        if conditions is not None
        else [{"type": "level", "metric": "op_margin", "op": "<", "value": 6, "unit": "%"}],
    }


def buy(decision: str) -> dict[str, Any]:
    return {
        "why_here": "시장 전체가 내렸다",
        "valuation": {"state": "싸다", "evidence": "now.per_fwd 18"},
        "decision": decision,
        "reason": "근거는 그대로다",
        "risks": ["경쟁"],
        "conviction": "중",
    }


def switch(decision: str, beats: bool = True) -> dict[str, Any]:
    return {
        "sold": "약화가 이어졌다",
        "bought": "흐름이 숫자에 나타난다",
        "beats_cost": beats,
        "decision": decision,
        "reason": "비용 0.5%를 넘는 차이",
    }
