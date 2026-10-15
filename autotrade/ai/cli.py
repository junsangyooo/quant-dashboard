"""The subscription CLI, called exactly as T26/T27 did and the server will (PHASE2.md §6).

  claude -p <prompt> --safe-mode --model <m> --output-format json --json-schema <schema>
         --system-prompt <short> --no-session-persistence [--effort low]
         --tools ""                                              (no tools)
         --tools WebSearch,WebFetch --allowedTools WebSearch WebFetch
                         (the quarterly discovery and a sell confirmation set off by a shock)

- The child's environment (child_env) keeps what the CLI needs (HOME, PATH, the locale; its
  OAuth login is the file under ~/.claude) and drops whatever could send it to the paid API or
  is credential-shaped: ANTHROPIC_*, CLAUDE_CODE_USE_BEDROCK/_VERTEX/…, cloud-provider
  credentials (AWS_*, GOOGLE_*, AZURE_* …), *_KEY/*_TOKEN/*_SECRET/*_PASSWORD names, the
  repository's own keys (DART, KIS, KRX, Toss) and AUTOTRADE_* (the secrets file's path among
  them). Root ops notes §7: with ANTHROPIC_API_KEY the CLI bills the paid API.
- stdin is /dev/null and the working folder is an empty neutral one (no project files to read).
- No time limit (ops notes §7): the CLI's exit code is the failure signal. Its output is
  read as UTF-8 with bad bytes replaced (a broken byte must not lose a paid answer).
- The answer is the JSON envelope's `structured_output`; its `usage` gives the tokens (input,
  cache creation, cache read, output, all counted) and `total_cost_usd` the list-price value.
- Which CLI (find_claude): AUTOTRADE_CLAUDE_BIN, else `claude` on PATH, else
  /usr/local/bin/claude (the server's wrapper: it puts the newest nvm node first on PATH), else
  the newest ~/.nvm/versions/node/*/bin/claude with its folder put first on the child's PATH
  (that `claude` is a link next to the node it needs). cron's PATH is /usr/bin:/bin.

Real calls need AUTOTRADE_AI_CALLS=1 (the owner's go); the runner checks it before it gets here.
Tests run a fake executable (tests/autotrade/fake_claude.py).
"""

from __future__ import annotations

import errno
import json
import os
import re
import shutil
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
# The tier names above are what flows and the database speak; the CLI gets a pinned id. A bare
# alias followed whatever the CLI release called 'sonnet' (2.1.268: Sonnet 5, Haiku 4.5) and
# changed models without a commit. 2.1.280 or newer knows the 5.5 ids (checked on the server
# with 2.1.300, 2026-10-15).
MODEL_IDS = {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5", "opus": "claude-opus-5-5"}
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

# Environment names never passed to the CLI (child_env). Prefixes route the CLI to another biller
# or carry cloud credentials; suffixes are credential-shaped (the old backend's _SENSITIVE_ENV,
# src/research/llm_backend.py, widened); AUTOTRADE_* is this program's own configuration.
_DROP_PREFIXES = (
    "ANTHROPIC_",
    "CLAUDE_CODE_USE_",
    "AWS_",
    "AZURE_",
    "GOOGLE_",
    "GCLOUD_",
    "GCP_",
    "CLOUDSDK_",
    "CLOUD_ML_",
    "VERTEX_",
    "BEDROCK_",
    "OPENAI_",
    "OPENROUTER_",
    "AUTOTRADE_",
    "DART_",
    "KIS_",
    "KRX_",
    "TOSS_",
)
_DROP_SUFFIX = re.compile(
    r"(KEY|TOKEN|SECRET|SECRETS|PASSWORD|PASSWD|_PW|_PASS|CREDENTIAL|CREDENTIALS|_AUTH|COOKIE"
    r"|_WEBHOOK_URL)$",
    re.IGNORECASE,
)
SYSTEM_CLAUDE = Path("/usr/local/bin/claude")
NVM_GLOB = ".nvm/versions/node/*/bin/claude"


def child_env(source: Mapping[str, str], path_prefix: str | None = None) -> dict[str, str]:
    """The CLI's environment: the runner's, without anything that bills elsewhere or is a
    credential; `path_prefix` goes first on PATH (the nvm node the CLI needs)."""
    env = {
        k: v
        for k, v in source.items()
        if not k.upper().startswith(_DROP_PREFIXES) and not _DROP_SUFFIX.search(k)
    }
    if path_prefix:
        rest = env.get("PATH", "")
        env["PATH"] = path_prefix if not rest else f"{path_prefix}{os.pathsep}{rest}"
    return env


def _executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def _node_version(path: Path) -> tuple[int, ...]:
    """(24, 14, 1) of '~/.nvm/versions/node/v24.14.1/bin/claude'; () when unreadable."""
    found = re.fullmatch(r"v?(\d+(?:\.\d+)*)", path.parent.parent.name)
    return tuple(int(x) for x in found.group(1).split(".")) if found else ()


@dataclass(frozen=True)
class ClaudeBinary:
    path: str | None  # None: no CLI found
    path_prefix: str | None = None  # a folder the CLI needs first on PATH
    tried: tuple[str, ...] = ()

    @property
    def error(self) -> str | None:
        if self.path is not None:
            return None
        return "claude CLI not found (tried " + ", ".join(self.tried or ("nothing",)) + ")"


def find_claude(
    configured: str | None,
    environ: Mapping[str, str],
    home: Path | None = None,
    system: Path | None = None,
) -> ClaudeBinary:
    """The CLI to run: AUTOTRADE_CLAUDE_BIN, `claude` on PATH, /usr/local/bin/claude, then the
    newest nvm install (its folder first on the child's PATH)."""
    tried: list[str] = []
    search = environ.get("PATH", os.defpath)
    if configured:
        tried.append(f"AUTOTRADE_CLAUDE_BIN={configured}")
        found = shutil.which(configured, path=search)
        if found is not None:
            return ClaudeBinary(found, tried=tuple(tried))
    tried.append("PATH")
    on_path = shutil.which("claude", path=search)
    if on_path is not None:
        return ClaudeBinary(on_path, tried=tuple(tried))
    wrapper = SYSTEM_CLAUDE if system is None else system
    tried.append(str(wrapper))
    if _executable(wrapper):
        return ClaudeBinary(str(wrapper), tried=tuple(tried))
    base = home if home is not None else Path(environ.get("HOME") or Path.home())
    tried.append(str(base / NVM_GLOB))
    nvm = sorted((p for p in base.glob(NVM_GLOB) if _executable(p)), key=_node_version)
    if nvm:
        return ClaudeBinary(str(nvm[-1]), str(nvm[-1].parent), tuple(tried))
    return ClaudeBinary(None, tried=tuple(tried))


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
    # False: the CLI could not even start (missing, not executable). That is a source being
    # down, not a failed call: no model was asked and no attempt is counted (runner.py).
    launched: bool = True

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
        binary: str | None,
        workdir: Path,
        runner: Runner | None = None,
        now: Callable[[], datetime] | None = None,
        monotonic: Callable[[], float] | None = None,
        environ: Mapping[str, str] | None = None,
        path_prefix: str | None = None,
        missing: str | None = None,
    ) -> None:
        self.binary = binary  # None: no CLI was found (`missing` says where it looked)
        self.workdir = workdir
        self.runner = runner or subprocess.run
        self.now = now or (lambda: datetime.now(UTC))
        self.monotonic = monotonic or time.monotonic
        self.environ = environ
        self.path_prefix = path_prefix
        self.missing = missing

    @classmethod
    def found(
        cls, binary: ClaudeBinary, workdir: Path, now: Callable[[], datetime] | None = None
    ) -> ClaudeCli:
        return cls(
            binary.path, workdir, now=now, path_prefix=binary.path_prefix, missing=binary.error
        )

    def command(self, call: CliCall) -> list[str]:
        # A NUL in an argument makes exec fail; filing texts can carry one.
        cmd = [
            self.binary or "claude",
            "-p",
            call.prompt.replace("\x00", ""),
            "--safe-mode",
            "--model",
            MODEL_IDS.get(call.model, call.model),
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(call.schema, ensure_ascii=False, separators=(",", ":")),
            "--system-prompt",
            call.system.replace("\x00", ""),
            "--no-session-persistence",
        ]
        if call.effort:
            cmd += ["--effort", call.effort]
        cmd += WEB_TOOLS if call.web else ["--tools", ""]
        return cmd

    def env(self) -> dict[str, str]:
        return child_env(os.environ if self.environ is None else self.environ, self.path_prefix)

    def run(self, call: CliCall) -> CliResult:
        started_at, t0 = self.now(), self.monotonic()
        exit_code: int | None = None
        output: Any = None
        usage: dict[str, Any] | None = None
        cost: Decimal | None = None
        launched = True
        try:
            if self.binary is None:
                raise FileNotFoundError(self.missing or "claude CLI not found")
            # A working folder that cannot be made is like a CLI that cannot start.
            self.workdir.mkdir(parents=True, exist_ok=True)
            done = self.runner(
                self.command(call),
                cwd=str(self.workdir),
                env=self.env(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except OSError as exc:
            error: str | None = f"{type(exc).__name__}: {exc}"
            # Missing, not executable, not a program: the CLI is down. An argument list too
            # long is this call's own fault.
            launched = exc.errno == errno.E2BIG
        except (ValueError, subprocess.SubprocessError) as exc:  # the call could not be made
            error = f"{type(exc).__name__}: {exc}"
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
            launched=launched,
        )
