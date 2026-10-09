"""The subscription CLI, called exactly as T26/T27 did and the server will (PHASE2.md §6).

  claude -p <prompt> --safe-mode --model <m> --output-format json --json-schema <schema>
         --system-prompt <short> --no-session-persistence [--effort low]
         --tools ""                                              (no tools)
         --tools WebSearch,WebFetch --allowedTools WebSearch WebFetch
                         (the quarterly discovery and a sell confirmation set off by a shock)

- ANTHROPIC_API_KEY is removed from the environment: with it the CLI bills the paid API (root
  ops notes §7). Nothing else is added.
- stdin is /dev/null and the working folder is an empty neutral one (no project files to read).
- No time limit (ops notes §7): the CLI's exit code is the failure signal.
- The answer is the JSON envelope's `structured_output`; its `usage` gives the tokens (input,
  cache creation, cache read, output, all counted) and `total_cost_usd` the list-price value.

Real calls need AUTOTRADE_AI_CALLS=1 (the owner's go); the runner checks it before it gets here.
Tests run a fake executable (tests/autotrade/fake_claude.py).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from autotrade.timeutil import UTC

MODELS = ("haiku", "sonnet", "opus")
USAGE_KEYS = (
    "input_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
    "output_tokens",
)
WEB_TOOLS = ["--tools", "WebSearch,WebFetch", "--allowedTools", "WebSearch", "WebFetch"]
STDERR_KEEP = 1500
# Linux refuses one argument longer than 128 KiB (MAX_ARG_STRLEN); the prompt is an argument.
MAX_PROMPT_BYTES = 120_000


@dataclass(frozen=True)
class CliCall:
    purpose: str  # 'extract', 'sell-confirm#1' ...
    prompt: str
    system: str
    schema: Mapping[str, Any]
    model: str
    effort: str | None = None
    web: bool = False

    def __post_init__(self) -> None:
        if self.model not in MODELS:
            raise ValueError(f"model must be one of {MODELS}")
        if len(self.prompt.encode()) > MAX_PROMPT_BYTES:
            raise ValueError(f"{self.purpose}: prompt is over {MAX_PROMPT_BYTES} bytes")


@dataclass(frozen=True)
class CliResult:
    call: CliCall
    exit_code: int | None
    output: Any  # the structured output, None when the call failed
    usage: dict[str, Any] | None
    tokens: int
    cost_usd: Decimal | None
    duration_ms: int
    error: str | None
    started_at: datetime
    finished_at: datetime

    @property
    def ok(self) -> bool:
        return self.error is None and self.exit_code == 0 and self.output is not None


Runner = Callable[..., "subprocess.CompletedProcess[str]"]


def count_tokens(usage: Mapping[str, Any] | None) -> int:
    if not usage:
        return 0
    total = 0
    for key in USAGE_KEYS:
        value = usage.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            total += value
    return total


def _cost(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def parse_envelope(stdout: str) -> tuple[Any, dict[str, Any] | None, Decimal | None, str | None]:
    """(structured output, usage, cost, error) from the CLI's JSON envelope."""
    try:
        envelope = json.loads(stdout)
    except ValueError:
        return None, None, None, f"not a JSON envelope: {stdout[:200]!r}"
    if not isinstance(envelope, dict):
        return None, None, None, "the envelope is not an object"
    usage = envelope.get("usage") if isinstance(envelope.get("usage"), dict) else None
    cost = _cost(envelope.get("total_cost_usd"))
    if envelope.get("is_error"):
        detail = envelope.get("result") or envelope.get("subtype") or "error"
        return None, usage, cost, f"CLI error: {str(detail)[:300]}"
    output = envelope.get("structured_output")
    if output is None and isinstance(envelope.get("result"), str):
        try:  # an older CLI puts the JSON answer in 'result'
            output = json.loads(envelope["result"])
        except ValueError:
            output = None
    if not isinstance(output, dict):
        return None, usage, cost, "no structured output in the envelope"
    return output, usage, cost, None


class ClaudeCli:
    def __init__(
        self,
        binary: str,
        workdir: Path,
        runner: Runner | None = None,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self.binary = binary
        self.workdir = workdir
        self.runner = runner or subprocess.run
        self.now = now or (lambda: datetime.now(UTC))
        self.monotonic = monotonic or time.monotonic
        self.environ = environ

    def command(self, call: CliCall) -> list[str]:
        cmd = [
            self.binary,
            "-p",
            call.prompt,
            "--safe-mode",
            "--model",
            call.model,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(call.schema, ensure_ascii=False, separators=(",", ":")),
            "--system-prompt",
            call.system,
            "--no-session-persistence",
        ]
        if call.effort:
            cmd += ["--effort", call.effort]
        cmd += WEB_TOOLS if call.web else ["--tools", ""]
        return cmd

    def env(self) -> dict[str, str]:
        source = os.environ if self.environ is None else self.environ
        return {k: v for k, v in source.items() if k != "ANTHROPIC_API_KEY"}

    def run(self, call: CliCall) -> CliResult:
        self.workdir.mkdir(parents=True, exist_ok=True)
        started_at, t0 = self.now(), self.monotonic()
        exit_code: int | None = None
        output: Any = None
        usage: dict[str, Any] | None = None
        cost: Decimal | None = None
        try:
            done = self.runner(
                self.command(call),
                cwd=str(self.workdir),
                env=self.env(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as exc:  # the CLI is missing or cannot start
            error: str | None = f"{type(exc).__name__}: {exc}"
        else:
            exit_code = done.returncode
            output, usage, cost, error = parse_envelope(done.stdout or "")
            if exit_code != 0:
                tail = (done.stderr or "")[-STDERR_KEEP:].strip()
                error = f"exit {exit_code}: {tail or error or 'no output'}"
                output = None
        duration_ms = int((self.monotonic() - t0) * 1000)
        return CliResult(
            call=call,
            exit_code=exit_code,
            output=output,
            usage=usage,
            tokens=count_tokens(usage),
            cost_usd=cost,
            duration_ms=duration_ms,
            error=error,
            started_at=started_at,
            finished_at=self.now(),
        )
