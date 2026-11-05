"""화면 글 만들기(TASKS P1-11 · ARCHITECTURE 2절 '글' · 3절 '화면 글' · 7절 '같은 글').

    cd product/service/app && .venv/bin/python scripts/gen_texts.py          # 두 글 모듈을 다시 만들어요
    cd product/service/app && .venv/bin/python scripts/gen_texts.py --check  # 최신인지만(다르면 종료 1 · pytest가 불러요)

- 원본은 글 목록 `copy/texts.json` 하나예요(id → 지금 글 그대로 · 변수는 `{name}` 꼴). 묶음 셋:
  `both`(서버와 화면이 같이 씀) · `server`(서버만) · `web`(화면만).
- 서버 쪽 `app/copy/texts.py`(`both` + `server`)는 글마다 이름 하나(`T.<id>`) · 변수가 든 글은 부르는 쪽이 `.format(name=…)`으로
  채워요(지금 코드가 `str.format` · f-string으로 채우던 것과 같은 글).
- 화면 쪽 `web/src/copy/texts.gen.ts`(`both` + `web`)는 변수가 없으면 글 · 있으면 이름 있는 인자를 받는 함수(`String(v.name)`)예요.
- 바깥 도구 없이 표준 라이브러리로만 만들어요(같은 목록이면 늘 같은 글 · 시험 `tests/test_texts.py`가 최신인지 봐요).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
SOURCE = APP / "copy" / "texts.json"
PY_OUT = APP / "app" / "copy" / "texts.py"
TS_OUT = APP / "web" / "src" / "copy" / "texts.gen.ts"
GROUPS = ("both", "server", "web")
ID = re.compile(r"^[a-z][a-z0-9_]*$")
VAR = re.compile(r"\{([a-z][a-z0-9_]*)\}")
REBUILD = "다시 만들기: product/service/app/scripts/gen_texts.py(원본 copy/texts.json)"


def load(path: Path = SOURCE) -> dict[str, dict[str, str]]:
    """글 목록(묶음 → id → 글). 꼴이 맞지 않으면 ValueError(id 꼴 · 묶음 사이 같은 id · 같은 글 두 번)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, str]] = {}
    seen_ids: dict[str, str] = {}
    seen_texts: dict[str, str] = {}
    for group in GROUPS:
        texts = data.get(group, {})
        if not isinstance(texts, dict):
            raise ValueError(f"{group}: id → 글 표가 아니에요")
        for tid, text in texts.items():
            if not ID.match(tid) or not isinstance(text, str) or not text:
                raise ValueError(f"{group}.{tid}: id는 소문자 · 숫자 · '_' · 글은 빈 글이 아니어야 해요")
            if tid in seen_ids:
                raise ValueError(f"{tid}: id가 {seen_ids[tid]} · {group} 두 묶음에 있어요")
            if text in seen_texts:
                raise ValueError(f"{tid}: 같은 글이 {seen_texts[text]}에도 있어요(글 하나는 id 하나)")
            seen_ids[tid] = group
            seen_texts[text] = tid
        out[group] = dict(texts)
    extra = set(data) - set(GROUPS) - {"about"}
    if extra:
        raise ValueError(f"모르는 묶음: {sorted(extra)}")
    return out


def variables(text: str) -> list[str]:
    """글 속 변수 이름(나온 차례 · 겹치면 한 번)."""
    return list(dict.fromkeys(VAR.findall(text)))


def render_py(groups: dict[str, dict[str, str]]) -> str:
    lines = [
        '"""화면 글 · 서버 쪽(TASKS P1-11 · ARCHITECTURE 2절 \'글\' 층).',
        "",
        f"만든 파일이에요 · 손대지 않아요 · {REBUILD}.",
        "변수가 든 글(`{name}`)은 부르는 쪽이 `.format(name=…)`으로 채워요.",
        '"""',
        "",
    ]
    for group in ("both", "server"):
        lines.append(f"# ── {group} ──")
        for tid, text in groups[group].items():
            lines.append(f"{tid} = {json.dumps(text, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def _ts_template(text: str) -> str:
    parts = []
    pos = 0
    for m in VAR.finditer(text):
        parts.append(_ts_escape(text[pos:m.start()]))
        parts.append("${String(v." + m.group(1) + ")}")
        pos = m.end()
    parts.append(_ts_escape(text[pos:]))
    return "`" + "".join(parts) + "`"


def _ts_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


def render_ts(groups: dict[str, dict[str, str]]) -> str:
    lines = [
        f"// 만든 파일 · 손대지 않아요 · {REBUILD}",
        "// 화면 글 한 출처(TASKS P1-11): both(서버와 같이 씀) + web(화면만). 변수가 든 글은 이름 있는 인자를 받는 함수예요.",
        "export const texts = {",
    ]
    for group in ("both", "web"):
        lines.append(f"  // ── {group} ──")
        for tid, text in groups[group].items():
            names = variables(text)
            if names:
                arg = "{ " + "; ".join(f"{n}: number | string" for n in names) + " }"
                lines.append(f"  {tid}: (v: {arg}): string => {_ts_template(text)},")
            else:
                lines.append(f"  {tid}: {json.dumps(text, ensure_ascii=False)},")
    lines.append("} as const;")
    return "\n".join(lines) + "\n"


def outputs(source: Path = SOURCE) -> list[tuple[Path, str]]:
    groups = load(source)
    return [(PY_OUT, render_py(groups)), (TS_OUT, render_ts(groups))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gen_texts")
    ap.add_argument("--check", action="store_true", help="다시 만든 글이 지금 파일과 같은지만(다르면 종료 1)")
    a = ap.parse_args(argv)
    outs = outputs()
    if a.check:
        stale = [p for p, text in outs if not p.exists() or p.read_text(encoding="utf-8") != text]
        for p in stale:
            print(f"글 목록과 달라요 · scripts/gen_texts.py로 다시 만들어요: {p.relative_to(APP)}")
        return 1 if stale else 0
    for p, text in outs:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"썼어요: {p.relative_to(APP)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
