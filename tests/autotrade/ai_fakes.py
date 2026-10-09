"""Stand-ins for the subscription CLI in the tests: autotrade/dev/ai.py (no real call anywhere).

fake_claude.py is a real executable for the end-to-end test of `python -m autotrade.jobs ai`.
"""

from autotrade.dev.ai import (
    KINDS,
    USAGE,
    Answer,
    NoScriptedAnswerError,
    ScriptedRunner,
    buy,
    envelope,
    kind_of,
    review,
    sell,
    switch,
)

__all__ = [
    "KINDS",
    "USAGE",
    "Answer",
    "NoScriptedAnswerError",
    "ScriptedRunner",
    "buy",
    "envelope",
    "kind_of",
    "review",
    "sell",
    "switch",
]
