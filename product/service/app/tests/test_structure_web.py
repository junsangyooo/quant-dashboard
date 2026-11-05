"""구조 장치 · 웹(ARCHITECTURE 3절 · 6절 · 7절 · TASKS P1-04): 화면 경계 · 웹 중복 · 같은 CSS · 같은 글 · 토큰.

1단계 셈은 지금 폴더로 해요(ARCHITECTURE 6절: `screens/` = features · `components/` · `charts/` = ds). 셈은
`tests/baseline/webcounts.py`(P1-01c 셈 규칙 그대로), 허용 목록과 견주기는 `tests/structure_guards.py`예요.

화면 경계는 두 군데서 막아요: ESLint(`web/eslint.boundaries.js` · `npm run lint`가 허용 목록 밖 (파일 → 대상) 쌍을 오류로)와
여기(쌍마다 곳 수 · 전체가 시작 숫자 이하). 둘의 층 규칙이 같은지는 ESLint를 허용 목록 없이 돌려 이 셈과 견줘 확인해요.
빌드 결과의 같은 글은 `web/dist`가 있어야 해서 check.sh의 structure-dist 단계(빌드 뒤 · `QUANT_STRUCTURE_DIST=1`)에서 봐요.
"""

from __future__ import annotations

import json
import os
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from tests import structure_guards as sg
from tests.baseline import webcounts

WEB = webcounts.WEB
WEB_GUARDS = ("web-boundaries", "web-duplication", "web-same-css", "web-same-text", "web-server-same-text",
              "web-raw-tokens", "web-px")


def _node24() -> bool:
    try:
        return subprocess.run(["node", "-v"], capture_output=True, text=True).stdout.startswith("v24.")
    except OSError:
        return False


@pytest.mark.parametrize("name", WEB_GUARDS)
def test_web_guard_only_decreases(name: str) -> None:
    g = sg.BY_NAME[name]
    found, problems = sg.check(g)
    assert problems == [], "\n".join(problems)
    assert sg.units(dict(found), g.unit) <= g.start


@pytest.mark.skipif(os.environ.get("QUANT_STRUCTURE_DIST") != "1",
                    reason="빌드 결과(web/dist)가 지금 src로 만든 것일 때만 · check.sh structure-dist 단계가 돌려요")
def test_web_dist_same_text_only_decreases() -> None:
    found, problems = sg.check(sg.BY_NAME["web-dist-same-text"])
    assert problems == [], "\n".join(problems)


ESLINT_SCRIPT = r"""
import { ESLint } from 'eslint';
import tseslint from 'typescript-eslint';
import { boundaryConfigs } from './eslint.boundaries.js';
const allow = process.argv[1] === 'allow';
const files = process.argv.slice(2);
const eslint = new ESLint({
  cwd: process.cwd(),
  overrideConfigFile: true,
  overrideConfig: [
    { files: ['src/**/*.{ts,tsx}'], languageOptions: { parser: tseslint.parser },
      linterOptions: { reportUnusedDisableDirectives: 'off' } },
    ...boundaryConfigs({ allow }),
  ],
});
const out = [];
for (const r of await eslint.lintFiles(files.length ? files : ['src/**/*.{ts,tsx}']))
  for (const m of r.messages)
    if (m.ruleId === 'no-restricted-imports' || m.ruleId === 'no-restricted-syntax')
      out.push({ file: r.filePath, line: m.line, rule: m.ruleId, message: m.message });
console.log(JSON.stringify(out));
"""


def eslint_boundaries(*, allow: bool, files: tuple[str, ...] = ()) -> list[dict[str, object]]:
    """경계 규칙만 켠 ESLint(형 검사 없음 · 몇 초) → [{file(web/ 기준), line, rule, message}]."""
    p = subprocess.run(["node", "--input-type=module", "-e", ESLINT_SCRIPT, "allow" if allow else "none", *files],
                       cwd=WEB, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-2000:]
    rows = json.loads(p.stdout)
    for r in rows:
        r["file"] = Path(str(r["file"])).resolve().relative_to(WEB).as_posix()
    return rows


def _target(row: dict[str, object]) -> str | None:
    spec = str(row["message"]).split("'")[1]
    return webcounts.resolve(spec, WEB / str(row["file"]))


@pytest.mark.skipif(not _node24(), reason="Node 24가 필요해요(check.sh는 Node 24에서만 돌아요)")
def test_eslint_rule_and_python_count_see_the_same_violations() -> None:
    """허용 목록 없이 돌린 ESLint의 (파일 → 대상) 쌍 · 곳 수 == `webcounts.boundary_violations()`(33)."""
    rows = eslint_boundaries(allow=False)
    from_eslint = Counter((str(r["file"]), _target(r)) for r in rows)
    assert all(r["rule"] == "no-restricted-imports" for r in rows)  # 지금 동적 import는 없어요
    assert from_eslint == sg.found_web_boundaries()
    assert sum(from_eslint.values()) <= sg.BY_NAME["web-boundaries"].start


@pytest.mark.skipif(not _node24(), reason="Node 24가 필요해요(check.sh는 Node 24에서만 돌아요)")
def test_eslint_with_the_allow_list_reports_nothing() -> None:
    """`npm run lint`(warnings 0)가 통과하는 까닭: 허용 목록의 쌍만 빠지고 그 밖은 0."""
    assert eslint_boundaries(allow=True) == []


@pytest.mark.skipif(not _node24(), reason="Node 24가 필요해요(check.sh는 Node 24에서만 돌아요)")
def test_eslint_catches_static_and_dynamic_imports_outside_the_list() -> None:
    """일부러 넣은 어긋남(임시 파일 · 지운 뒤 확인): ds → api 정적 · features → 다른 features 동적 · features → shell."""
    planted = {
        WEB / "src/components/ZzPlanted.tsx": "import { api } from '../api/client';\nexport const z = api;\n",
        WEB / "src/screens/Live/ZzPlanted.ts": ("export const load = () => import('../Setup/Wizard');\n"
                                                "export { pageTitle } from '../../shell/page';\n"),
    }
    try:
        for p, text in planted.items():
            p.write_text(text, encoding="utf-8")
        rows = eslint_boundaries(allow=True, files=tuple(p.relative_to(WEB).as_posix() for p in planted))
        got = sorted((str(r["file"]), int(str(r["line"])), str(r["rule"])) for r in rows)
        assert got == [("src/components/ZzPlanted.tsx", 1, "no-restricted-imports"),
                       ("src/screens/Live/ZzPlanted.ts", 1, "no-restricted-syntax"),
                       ("src/screens/Live/ZzPlanted.ts", 2, "no-restricted-imports")]
        assert all("화면 경계(ARCHITECTURE 3절" in str(r["message"]) for r in rows)
        _found, problems = sg.check(sg.BY_NAME["web-boundaries"])
        assert sorted(problems) == ["web-boundaries: 새 어긋남 src/components/ZzPlanted.tsx src/api/client.ts: 1",
                                    "web-boundaries: 새 어긋남 src/screens/Live/ZzPlanted.ts src/screens/Setup/Wizard.tsx: 1",
                                    "web-boundaries: 새 어긋남 src/screens/Live/ZzPlanted.ts src/shell/page.ts: 1",
                                    "web-boundaries: 지금 36 > P1-04 시작 숫자 33(줄어들기만)"]
    finally:
        for p in planted:
            p.unlink(missing_ok=True)
    assert not any(p.exists() for p in planted)
