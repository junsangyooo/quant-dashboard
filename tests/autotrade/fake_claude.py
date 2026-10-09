"""A fake `claude` executable for the end-to-end AI test (never the real CLI).

It records how it was called (arguments, working folder, whether ANTHROPIC_API_KEY reached it,
what stdin held) as one JSON line in $FAKE_CLAUDE_LOG, and prints the CLI's JSON envelope with
the first answer of $FAKE_CLAUDE_ANSWERS (a JSON list; the answer is removed from the file).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    args = sys.argv[1:]
    log = Path(os.environ["FAKE_CLAUDE_LOG"])
    answers_path = Path(os.environ["FAKE_CLAUDE_ANSWERS"])
    with log.open("a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "args": args,
                    "cwd": os.getcwd(),
                    "api_key": "ANTHROPIC_API_KEY" in os.environ,
                    "stdin": sys.stdin.read(),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
    answers = json.loads(answers_path.read_text(encoding="utf-8"))
    answer = answers.pop(0)
    answers_path.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")
    if answer.get("__exit__"):
        sys.stderr.write(str(answer.get("__stderr__", "boom")))
        return int(answer["__exit__"])
    sys.stdout.write(
        json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "duration_ms": 900,
                "result": "",
                "total_cost_usd": 0.0018,
                "usage": {
                    "input_tokens": 7000,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 1700,
                    "output_tokens": 513,
                },
                "structured_output": answer,
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
