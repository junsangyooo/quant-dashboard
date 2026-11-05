"""P1-12 토큰 파이프라인 시험.

- 원시 토큰 직접 사용 0 · 화면 안 임의 변수 0: ARCHITECTURE 7절 셈 규칙(`webcounts.raw_tokens` · 1단계 범위 `screens/` ·
  `components/` · `charts/` · `BlockEditor/*` 뺌 · 6절).
- 내보내기 → `web/design/tokens.json` → `web/src/styles/tokens.css`: `node scripts/gen-tokens.ts --check`가 커밋된 두 파일과
  같다고 해요(Node 24가 있을 때만 · 없으면 건너뜀 · 같은 대조는 `web/tests/tokens-pipeline.test.ts`에도 있음).
"""

from __future__ import annotations

import json
import subprocess

import pytest

from tests.baseline import webcounts


def _node24() -> bool:
    try:
        return subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.startswith("v24.")
    except OSError:
        return False


def test_no_raw_token_uses_outside_block_editor() -> None:
    rt = webcounts.raw_tokens()
    hits = [h for h in rt["raw_token_hits"] if not h["file"].startswith(webcounts.BLOCK_EDITOR)]
    assert hits == [] and rt["raw_token_uses"]["without_block_editor"] == 0


def test_no_screen_custom_vars_outside_block_editor() -> None:
    rt = webcounts.raw_tokens()
    hits = [h for h in rt["custom_var_hits"] if not h["file"].startswith(webcounts.BLOCK_EDITOR)]
    assert hits == [] and rt["custom_vars"]["without_block_editor"] == 0


def test_scope_file_lists_every_export_token_once() -> None:
    export = json.loads((webcounts.SERVICE / "design" / "tokens-export.json").read_text(encoding="utf-8"))
    scope = json.loads((webcounts.WEB / "design" / "tokens-scope.json").read_text(encoding="utf-8"))
    names = [n for coll in export["collections"].values() for n in coll]
    assert len(scope["used"]) == 180 and len(scope["unused"]) == 43
    assert sorted(scope["used"] + scope["unused"]) == sorted(names)
    assert scope["used"] == [t["name"] for t in webcounts.tokens_json()]
    assert sorted(scope["unused"]) == webcounts.token_crosscheck()["unused_export_only_names"]
    assert scope["fontRename"] == {"Pretendard Variable": "Pretendard"}


@pytest.mark.skipif(not _node24(), reason="Node 24가 필요해요(scripts/gen-tokens.ts는 Node의 타입 지우기로 돌아요)")
def test_generated_token_files_are_committed() -> None:
    p = subprocess.run(["node", "scripts/gen-tokens.ts", "--check"], cwd=webcounts.WEB, capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr
