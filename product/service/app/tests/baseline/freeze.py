"""P1-01a: 지울 코드가 만드는 시험 입력과 정답을 `tests/baseline/frozen/`에 자기완결 파일로 얼려요.

    cd product/service/app && .venv/bin/python -m tests.baseline.freeze

만드는 것(모두 결정적 · 시각 · 경로 · 난수 없음 · 두 번 돌려도 바이트가 같아요):
- `frozen/bars.json`: 일봉 묶음 4개(회귀 씨앗 11 · 23 · 47 · 옛 예시용 대형주 10종목). 씨앗이 아니라 일봉 자체예요.
- `frozen/v3_cases.json`: v1 → v3 문턱(`tests/regression/threshold.py`)의 사례 326개. 사례마다 v1 본문 · v3 본문
  (`app.copytext.convert_v1` · v3 안의 변환) · 쓰는 일봉 묶음 이름 · 기간 · 현금 · v3 엔진(`app.engine.run_backtest`)의
  거래(사유 · 판단일 · 종류) · 건너뜀(까닭) · 값 없음 기록 · 끝 자산 · 남은 보유, 그리고 v1 엔진 거래와 문턱 판정.
- `frozen/v1_fixtures.json`: `app.v1` · `app.engine_v1` · `app.strategy`가 만드는 시험 입력 · 정답(회귀 본문 84개와
  `normalize` · `mode_of` · v3 변환, 옛 예시 4개와 복사 글, `helpers.legacy` 본문, `run_v1` 거래 한 건).
- `frozen/docs-before-f33e2a9/`: `f33e2a9` 바로 전 판 문서의 표(DATA-CATALOG 1절 · GLOSSARY 5절, 그리고 그 비교 논리가
  함께 읽는 SPEC 8-1 · ENGINE-RULES 11-3).

이 스크립트는 지울 모듈을 가져오므로 P1-03 뒤에는 돌지 않아요. 그 뒤에는 얼린 파일이 기준이고, 재생은
`tests/baseline/replay.py`(v3 엔진만)가 해요.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from app import copytext as ct
from app.engine import run_backtest
from app.engine_v1 import run_v1
from app.v1 import strategy as st1
from tests.helpers import legacy
from tests.regression import threshold as th
from tests.regression.cases import SEEDS, bar_set, bodies
from tests.regression.v1_inputs import example_bars, random_bars

FROZEN = Path(__file__).resolve().parent / "frozen"
DOCS = FROZEN / "docs-before-f33e2a9"
BASE_NOTE = "app code of origin/quant-service 125685d (service-v5 before P1-02)"
DOC_COMMIT = "f33e2a9^"

# 남는 시험 · 지울 시험이 `tests.helpers.legacy(template, name)` · `new_strategy(client, name, template)`로 부르는
# 인자 조합 전부(P1-01a 시점 grep). 이름은 본문 "name"에만 들어가요.
LEGACY_CALLS = [
    ("event", "옛 전략"),  # test_api_v2.py test_old_body_reads_as_v3
    ("event", "옛 글"),  # test_copytext.py
    ("event", "돌파"), ("rank", "순위"), ("target", "반반"), ("event", "x"), ("event", "API"),  # test_engine_paper.py
    ("event", "창"), ("event", "코드"), ("event", "끔"), ("event", "늦음"),  # test_fix1.py(반반은 위)
    ("rank", "x"),  # test_graph.py
    ("event", "기록"), ("event", "계획"), ("event", "검사"), ("event", "자동"),  # test_mvp_api.py
]


# ── 결정적으로 쓰기 ─────────────────────────────────────────────────────────


def _j(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, sort_keys=True)


def _record(rec: dict[str, Any], order: list[str], per_line: set[str], indent: str) -> str:
    """키는 `order` 차례로 · `per_line` 목록은 항목 하나가 한 줄 · 나머지는 한 줄 JSON."""
    lines = []
    for k in order:
        v = rec[k]
        if k in per_line:
            if not v:
                lines.append(f'{indent} "{k}": []')
                continue
            items = ",\n".join(f"{indent}  {_j(x)}" for x in v)
            lines.append(f'{indent} "{k}": [\n{items}\n{indent} ]')
        else:
            lines.append(f'{indent} "{k}": {_j(v)}')
    return f"{indent}{{\n" + ",\n".join(lines) + f"\n{indent}}}"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ── 1. 일봉 ──────────────────────────────────────────────────────────────────


def bar_sets() -> dict[str, dict[str, list[dict[str, Any]]]]:
    out = {f"seed-{s}": bar_set(s) for s in SEEDS}
    out["example-big10"] = example_bars()  # BIG10 종목 코드에 씨앗 11 · 12 일봉을 붙인 것
    return out


def write_bars(sets: dict[str, dict[str, list[dict[str, Any]]]]) -> None:
    parts = []
    for name in sorted(sets):
        syms = []
        for sym in sorted(sets[name]):
            rows = ",\n".join(f"    {_j(b)}" for b in sets[name][sym])
            syms.append(f'   "{sym}": [\n{rows}\n   ]')
        parts.append(f'  "{name}": {{\n' + ",\n".join(syms) + "\n  }")
    meta = _j({"base": BASE_NOTE, "what": "일봉 묶음 · 사례의 bars 이름이 가리켜요 · 종목마다 d o h l c v",
               "symbols": {name: sorted(sets[name]) for name in sorted(sets)},
               "days": {name: len(next(iter(sets[name].values()))) for name in sorted(sets)}})
    _write(FROZEN / "bars.json", '{\n "meta": ' + meta + ',\n "sets": {\n' + ",\n".join(parts) + "\n }\n}\n")


# ── 2. v3 사례 326개 ─────────────────────────────────────────────────────────

CASE_ORDER = ["id", "source", "name", "seed", "case", "template", "first", "last", "bars", "start", "end", "cash",
              "v1_body", "v3_body", "threshold", "v1_final", "final", "open", "notes", "trades", "skipped", "v1_trades"]
CASE_LINES = {"trades", "skipped", "v1_trades"}


def _case(cid: str, source: str, name: str, body_v1: dict[str, Any], bars_name: str,
          data: dict[str, list[dict[str, Any]]], fixed: dict[str, Any], start: str, end: str,
          **extra: Any) -> dict[str, Any]:
    v3 = ct.convert_v1(st1.normalize(body_v1))
    cash = float(th.V1["cash"])
    res = run_backtest(v3, data, None, start, end, cash, check=False)
    got = th.compare(fixed["trades"], [th.trade_key(t) for t in res["trades"]], th._calendar(data))
    assert got["ok"], (cid, got)
    rec = {"id": cid, "source": source, "name": name, "seed": None, "case": None, "template": None, "first": None,
           "last": None, "bars": bars_name, "start": start, "end": end, "cash": cash, "v1_body": body_v1,
           "v3_body": v3, "threshold": {k: got[k] for k in ("kind", "day", "syms", "switching")},
           "v1_final": fixed["final"], "final": res["final"], "open": res["open"], "notes": res["notes"],
           "trades": res["trades"], "skipped": res["skipped"], "v1_trades": fixed["trades"]}
    rec.update(extra)
    return rec


def cases() -> list[dict[str, Any]]:
    v1 = th.V1
    slots = bodies()
    out: list[dict[str, Any]] = []
    bars = {s: bar_set(s) for s in SEEDS}
    for f in v1["backtests"]:
        out.append(_case(f"regression-s{f['seed']}-c{f['case']:03d}", "regression",
                         f"백테스트 s{f['seed']}-c{f['case']} {f['template']}", slots[f["case"]], f"seed-{f['seed']}",
                         bars[f["seed"]], f, f["start"], f["end"], seed=f["seed"], case=f["case"],
                         template=f["template"]))
    cal = th._calendar(bars[SEEDS[0]])
    for f in v1["papers"]:
        out.append(_case(f"paper-c{f['case']:03d}", "paper", f"모의투자 c{f['case']} {f['template']}", slots[f["case"]],
                         f"seed-{SEEDS[0]}", bars[SEEDS[0]], f, cal[f["first"]], cal[f["last"]], seed=SEEDS[0],
                         case=f["case"], template=f["template"], first=f["first"], last=f["last"]))
    ex = example_bars()
    for f, e in zip(v1["examples"], st1.EXAMPLES, strict=True):
        assert f["body"] == st1.example_body(e["id"])
        out.append(_case(f"example-{e['id']}", "example", f"예시 {f['name']}", f["body"], "example-big10", ex, f,
                         f["start"], f["end"], seed=SEEDS[0]))
    for f in v1["randoms"]:
        bars_seed = SEEDS[f["seed"] % len(SEEDS)]
        assert random_bars(f["seed"]) == bars[bars_seed]
        out.append(_case(f"random-{f['seed']:02d}", "random", f"무작위 {f['seed']}", f["body"], f"seed-{bars_seed}",
                         bars[bars_seed], f, f["start"], f["end"], seed=f["seed"]))
    assert len(out) == 252 + 10 + 4 + 60
    return out


def write_cases(rows: list[dict[str, Any]]) -> None:
    counts: dict[str, int] = {}
    for r in rows:
        counts[r["source"]] = counts.get(r["source"], 0) + 1
    meta = _j({"base": BASE_NOTE, "count": len(rows), "by_source": counts,
               "v3_body": "app.copytext.convert_v1(app.v1.strategy.normalize(v1_body))",
               "engine": "app.engine.run_backtest(v3_body, bars[bars], None, start, end, cash, check=False)",
               "compared": ["trades", "skipped", "notes", "final", "open"],
               "v1_trades": "tests/fixtures/v1_trades.json (app/engine_v1.py) · 8 columns d sym side qty price amount cost pnl",
               "threshold": "tests/regression/threshold.py compare(v1_trades, v3 trades)"})
    body = ",\n".join(_record(r, CASE_ORDER, CASE_LINES, " ") for r in rows)
    _write(FROZEN / "v3_cases.json", '{\n "meta": ' + meta + ',\n "cases": [\n' + body + "\n ]\n}\n")


# ── 3. v1에서 나온 기대값 · 입력 ─────────────────────────────────────────────


def v1_fixtures() -> dict[str, Any]:
    slots = bodies()
    body_rows = []
    for i, b in enumerate(slots):
        norm = st1.normalize(b)
        body_rows.append({"index": i, "slots": b, "normalized": norm, "mode": st1.mode_of(norm),
                          "v3_from_normalized": ct.convert_v1(norm), "v3_from_slots": ct.read_body(b)})
    examples = []
    for e in st1.EXAMPLES:
        body = st1.example_body(e["id"])
        examples.append({"id": e["id"], "name": e["name"], "body": body, "mode": st1.mode_of(body),
                         "copy_text": st1.to_copy_text(body), "v3": ct.convert_v1(body)})
    legacy_rows = []
    for template, name in LEGACY_CALLS:
        body = legacy(template, name)
        legacy_rows.append({"template": template, "name": name, "body": body, "v3": ct.read_body(body)})
    # test_engine_v2.py test_R_B3_converted_v1_without_switching_is_identical
    data = bar_set(11)
    ds = sorted({x["d"] for r in data.values() for x in r})
    b1 = slots[1]
    r1 = run_v1(b1, data, ds[60], ds[-1], 1e7)
    key7 = ("d", "sym", "side", "qty", "price", "amount", "cost")
    return {
        "meta": {"base": BASE_NOTE,
                 "bodies": "tests/regression/cases.bodies() · normalized = app.v1.strategy.normalize · mode = "
                           "app.v1.strategy.mode_of · v3_from_normalized = app.copytext.convert_v1(normalized) · "
                           "v3_from_slots = app.copytext.read_body(slots)",
                 "examples": "app.v1.strategy.example_body(id) · copy_text = app.v1.strategy.to_copy_text(body)",
                 "legacy": "tests.helpers.legacy(template, name) · v3 = app.copytext.read_body(body)",
                 "R_B3": "app.engine_v1.run_v1(bodies()[1], bar_set(11), ds[60], ds[-1], 1e7) trades · 7 keys"},
        "bodies": body_rows,
        "examples": examples,
        "legacy": legacy_rows,
        "R_B3": {"body_index": 1, "bars": "seed-11", "start": ds[60], "end": ds[-1], "cash": 1e7,
                 "keys": list(key7), "v1_trades": [[t[k] for k in key7] for t in r1["trades"]]},
    }


def write_v1_fixtures(fx: dict[str, Any]) -> None:
    bodies_text = ",\n".join(_record(r, ["index", "mode", "slots", "normalized", "v3_from_normalized", "v3_from_slots"],
                                     set(), "  ") for r in fx["bodies"])
    ex_text = ",\n".join(_record(r, ["id", "name", "mode", "body", "copy_text", "v3"], set(), "  ")
                         for r in fx["examples"])
    lg_text = ",\n".join(_record(r, ["template", "name", "body", "v3"], set(), "  ") for r in fx["legacy"])
    rb3 = _record(fx["R_B3"], ["body_index", "bars", "start", "end", "cash", "keys", "v1_trades"], {"v1_trades"}, " ")
    _write(FROZEN / "v1_fixtures.json",
           '{\n "meta": ' + _j(fx["meta"]) + ',\n "bodies": [\n' + bodies_text + '\n ],\n "examples": [\n' + ex_text
           + '\n ],\n "legacy": [\n' + lg_text + '\n ],\n "R_B3":\n' + rb3 + "\n}\n")


# ── 4. f33e2a9 바로 전 문서 표 ───────────────────────────────────────────────

DOC_PARTS = [
    # (파일, 시작 줄 머리, 끝 줄 머리(여기 전까지), 얼릴 파일 이름)
    ("DATA-CATALOG.md", "## 1. 조건 카탈로그", "## 2.", "DATA-CATALOG-1.md"),
    ("GLOSSARY.md", "## 5.", None, "GLOSSARY-5.md"),
    ("SPEC.md", "### 8-1.", "### 8-2.", "SPEC-8-1.md"),
    ("ENGINE-RULES.md", "### 11-3.", "### 11-4.", "ENGINE-RULES-11-3.md"),
]


def _section(text: str, start: str, stop: str | None) -> str:
    lines = text.splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith(start))
    out = []
    for line in lines[i:]:
        if stop is not None and line.startswith(stop) and out:
            break
        out.append(line)
    return "\n".join(out).rstrip("\n") + "\n"


def write_docs() -> None:
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True,
                          cwd=Path(__file__).resolve().parent).stdout.strip()
    for name, start, stop, out in DOC_PARTS:
        text = subprocess.run(["git", "-C", root, "show", f"{DOC_COMMIT}:product/service/{name}"],
                              capture_output=True, text=True, check=True).stdout
        head = f"<!-- product/service/{name} · {DOC_COMMIT} 판 · 이 부분만 · P1-01a가 떼어 둠(Q-N18) -->\n\n"
        _write(DOCS / out, head + _section(text, start, stop))


def main() -> None:
    sets = bar_sets()
    write_bars(sets)
    write_cases(cases())
    write_v1_fixtures(v1_fixtures())
    if "--no-docs" not in sys.argv:
        write_docs()
    for p in sorted(FROZEN.rglob("*")):
        if p.is_file():
            print(f"{p.stat().st_size:>10}  {p.relative_to(FROZEN.parent.parent.parent)}")


if __name__ == "__main__":
    main()
