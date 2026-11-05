"""구조 장치(ARCHITECTURE 7절 셈 규칙 · TASKS P1-04): 허용 목록(`tests/allow/*.txt`)과 '줄어들기만'.

    cd product/service/app && .venv/bin/python -m tests.structure_guards            # 모두 대조(종료 0 통과 · 1 어긋남 · 2 건너뜀)
    cd product/service/app && .venv/bin/python -m tests.structure_guards shrink     # 줄어든 수만 목록에 반영(늘리지 않음)
    cd product/service/app && .venv/bin/python -m tests.structure_guards retake web-same-css  # 합친 뒤 다시 재기(전체가 줄 때만)

셈은 기준선 도구를 그대로 써요(`tests/baseline/counts.py` · `webcounts.py` · 1단계는 지금 모듈 · 폴더를 ARCHITECTURE 2-1 ·
6절대로 층에 붙여 셈). 여기서는 셈 결과를 '키 → 수'로 묶어 허용 목록과 견주기만 해요.

허용 목록 한 줄 = `키 … 수  # [꼬리표] 까닭`(키에 줄 번호는 넣지 않아요 · 줄이 옮겨 가도 같은 키). 글이 키인 목록은 키를
JSON 문자열 하나로 적어요(`"그 전략이 없어요" 6  # …`). 꼬리표는 `[P1-05]` ~ `[P1-12]`(그 일감이 없앰) 또는
`[1단계 예외]`(ARCHITECTURE 6절 · 1단계 끝에 남는 것)예요.

판정(장치마다):
1. 키마다 지금 수 == 목록의 수(늘면 '새 어긋남' · 줄면 '목록을 줄여요' · 목록에 없는 키는 '새 어긋남'). `scripts/lint_allow.py`와
   같은 '정확히 같음' 규칙이라 목록은 줄어들기만 해요.
2. 목록 전체(줄의 수를 더한 값 · 글 목록은 줄 수) == 시작 숫자(`Guard.start`) · 지금 전체 ≤ 시작 숫자. 파일을 나눠 키가 갈라져도
   전체 수로 막고, 목록을 줄이면 같은 커밋에서 시작 숫자도 낮춰야 해요(`shrink` · `retake`가 `GUARDS`의 수를 함께 고침 ·
   시작 숫자는 P1-04 기록보다 올릴 수 없음 · `test_structure.py`).
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
ALLOW = APP / "tests" / "allow"
SOURCE = Path(__file__)  # set_start가 시작 숫자를 고치는 파일(시험은 사본으로 바꿔 끼움)
TAG = re.compile(r"^\[(P1-(0[5-9]|1[0-2])|1단계 예외)\]")

Key = tuple[str, ...]


@dataclass(frozen=True)
class Guard:
    name: str  # 허용 목록 파일 이름(`tests/allow/<name>.txt` · has_list=False면 목록 없이 0)
    what: str
    start: int  # P1-04 시작 숫자(줄어들기만 · 이 수를 넘으면 실패)
    found: Callable[[], Counter[Key]]
    text_key: bool = False  # 키가 글 하나(JSON 문자열)
    unit: str = "sum"  # sum: 줄의 수를 더함 · keys: 줄(키) 수
    has_list: bool = True  # False면 허용 목록 없이 0이어야 함
    new_reason: Callable[[Key], str] | None = None  # retake가 새 키에 붙이는 까닭(없으면 retake는 새 키를 받지 않음)


@dataclass
class Entry:
    count: int
    reason: str
    line: int


# ── 허용 목록 읽기 · 쓰기 ──────────────────────────────────────────────────────


def parse(text: str, *, text_key: bool, source: str = "?") -> dict[Key, Entry]:
    out: dict[Key, Entry] = {}
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if text_key:
            if not line.startswith('"'):
                raise ValueError(f"{source}:{n}: 글 키는 JSON 문자열이에요: {raw}")
            value, end = json.JSONDecoder().raw_decode(line)
            m = re.match(r"^\s+(\d+)\s*#\s*(.*)$", line[end:])
            if not m:
                raise ValueError(f"{source}:{n}: `\"글\" 수  # 까닭` 꼴이 아니에요: {raw}")
            key: Key = (value,)
            count, reason = int(m.group(1)), m.group(2).strip()
        else:
            code, sep, reason = line.partition("#")
            tokens = code.split()
            if not sep or len(tokens) < 2 or not tokens[-1].isdigit():
                raise ValueError(f"{source}:{n}: `키 … 수  # 까닭` 꼴이 아니에요: {raw}")
            key, count, reason = tuple(tokens[:-1]), int(tokens[-1]), reason.strip()
        if not reason:
            raise ValueError(f"{source}:{n}: 까닭이 없어요(줄마다 한 줄): {raw}")
        if not TAG.match(reason):
            raise ValueError(f"{source}:{n}: 까닭은 `[P1-05]` ~ `[P1-12]` 또는 `[1단계 예외]`로 시작해요: {raw}")
        if count <= 0:
            raise ValueError(f"{source}:{n}: 수가 0이면 줄을 지워요: {raw}")
        if key in out:
            raise ValueError(f"{source}:{n}: 같은 키가 {out[key].line}행에도 있어요: {raw}")
        out[key] = Entry(count, reason, n)
    return out


def format_line(key: Key, count: int, reason: str, *, text_key: bool) -> str:
    k = json.dumps(key[0], ensure_ascii=False) if text_key else " ".join(key)
    return f"{k} {count}  # {reason}"


def path_of(g: Guard) -> Path:
    return ALLOW / f"{g.name}.txt"


def load(g: Guard) -> dict[Key, Entry]:
    if not g.has_list:
        return {}
    p = path_of(g)
    return parse(p.read_text(encoding="utf-8"), text_key=g.text_key, source=p.relative_to(APP).as_posix())


def units(counts: dict[Key, int], unit: str) -> int:
    return len(counts) if unit == "keys" else sum(counts.values())


def compare(g: Guard, found: Counter[Key], allowed: dict[Key, Entry]) -> list[str]:
    """어긋남 목록(비면 통과)."""
    problems = []
    show = (lambda k: json.dumps(k[0], ensure_ascii=False)) if g.text_key else (lambda k: " ".join(k))
    for key in sorted(set(found) | set(allowed)):
        f, a = found.get(key, 0), allowed[key].count if key in allowed else 0
        if f > a:
            problems.append(f"{g.name}: 새 어긋남 {show(key)}: {a} → {f}" if a else f"{g.name}: 새 어긋남 {show(key)}: {f}")
        elif f < a:
            problems.append(f"{g.name}: 줄었어요 {show(key)}: {a} → {f} · 허용 목록 tests/allow/{g.name}.txt를 줄여요"
                            " (`python -m tests.structure_guards shrink`)")
    total_a = units({k: e.count for k, e in allowed.items()}, g.unit)
    total_f = units(dict(found), g.unit)
    if g.has_list and total_a != g.start:
        # 목록을 줄이면 같은 커밋에서 시작 숫자도 낮춰요(남는 여유로 뒤 일감이 줄을 되살리지 못하게 · shrink · retake가 함께 고침)
        problems.append(f"{g.name}: 허용 목록 전체 {total_a} ≠ 시작 숫자 {g.start} · 시작 숫자를 목록과 같게 낮춰요"
                        " (tests/structure_guards.py GUARDS · shrink · retake가 함께 고침 · 올리기는 안 됨)")
    if total_f > g.start:
        problems.append(f"{g.name}: 지금 {total_f} > P1-04 시작 숫자 {g.start}(줄어들기만)")
    return problems


# ── 셈(기준선 도구 그대로) ─────────────────────────────────────────────────────


def _counter(pairs: list[tuple[Key, int]]) -> Counter[Key]:
    c: Counter[Key] = Counter()
    for k, n in pairs:
        c[k] += n
    return c


def found_layers() -> Counter[Key]:
    from tests.baseline import counts

    out: Counter[Key] = Counter()
    for e in counts.layer_violations()["edges"]:
        to = e["to_layer"] if e["to_layer"] != "external" else "ext:" + e["import"].split(".")[0]
        out[(e["from"], to)] += 1
    return out


STORE = ("app/db.py",)
STORE_DIR = "app/store/"


def found_sql() -> Counter[Key]:
    from tests.baseline import counts

    out: Counter[Key] = Counter()
    for h in counts.sql_locations()["hits"]:
        if h["module"] not in STORE and not h["module"].startswith(STORE_DIR):
            out[(h["module"], h["kind"])] += 1
    return out


TIME_HOME = ("app/domain/markets/kr.py", "app/run/scheduler.py")
TIME_KIND = {"hh:mm": "hh:mm", "time()": "time()", "datetime()": "datetime()", "replace(hour=)": "replace(hour=)",
             ".at(h, m)": ".at(h,m)", "(h, m)": "(h,m)"}


def found_time_literals() -> Counter[Key]:
    from tests.baseline import counts

    out: Counter[Key] = Counter()
    for h in counts.time_literals()["hits"]:
        if h["module"] in TIME_HOME or h["module"].startswith("app/copy/"):  # 시각 표 · 장 시간 자리 · 글 목록은 뺌
            continue
        out[(h["module"], TIME_KIND[h["kind"]])] += 1
    return out


def found_same_text() -> Counter[Key]:
    from tests.baseline import counts

    return _counter([((t["text"],), len(t["where"])) for t in counts.same_text()["texts"]])


def found_py_duplicates() -> Counter[Key]:
    from tests.baseline import counts

    d = counts.duplicates()
    out: Counter[Key] = Counter()
    for group in d["same_body"]:
        out[("same-body", *sorted(f"{f['module']}:{f['name']}" for f in group))] += 1
    for name, modules in d["same_name"].items():
        out[("same-name", name, *modules)] += 1
    return out


def found_web_boundaries() -> Counter[Key]:
    from tests.baseline import webcounts

    out: Counter[Key] = Counter()
    bd = webcounts.boundary_violations()
    for e in bd["edges"]:
        out[(e["from"], e["to"])] += 1
    for u in bd["unresolved"]:  # 풀 수 없는 지정자(식이 든 템플릿 글 · 없는 파일)도 어긋남으로
        out[(u["from"], "unresolved:" + u["spec"].replace(" ", ""))] += 1
    return out


def _npm_env() -> dict[str, str]:
    """pytest는 HOME을 임시 폴더로 바꿔요(P1-02 ④) · jscpd는 진짜 npm 캐시에서(먼저 캐시 · 바깥 요청 없게)."""
    env = dict(os.environ)
    conftest = sys.modules.get("tests.conftest")  # pytest 안이면 바꾸기 전 HOME을 기억해 둔 곳
    real_home = getattr(conftest, "REAL_HOME", None) or os.environ.get("HOME", "")
    if real_home and "npm_config_cache" not in env and (Path(real_home) / ".npm").is_dir():
        env["npm_config_cache"] = str(Path(real_home) / ".npm")  # capture.temp_home과 같은 규칙
    env.setdefault("npm_config_prefer_offline", "true")
    return env


def found_web_duplication() -> Counter[Key]:
    from tests.baseline import webcounts

    out: Counter[Key] = Counter()
    for c in webcounts.jscpd(True, env=_npm_env())["clone_list"]:
        a, b = sorted((c["a"].rsplit(":", 1)[0], c["b"].rsplit(":", 1)[0]))
        out[(a, b)] += 1
    return out


def found_web_same_css() -> Counter[Key]:
    from tests.baseline import webcounts

    out: Counter[Key] = Counter()
    for g in webcounts.same_css(True)["group_list"]:
        out[tuple(sorted({r["where"].rsplit(":", 1)[0] for r in g["rules"]}))] += 1
    return out


def found_web_same_text() -> Counter[Key]:
    from tests.baseline import webcounts

    return _counter([((t["text"],), len(t["where"])) for t in webcounts.same_text()["web_texts"]])


def found_web_server_same_text() -> Counter[Key]:
    from tests.baseline import webcounts

    return _counter([((t["text"],), len(t["server"]) + len(t["web"]))
                     for t in webcounts.same_text()["server_web_shared"]])


# 빌드 결과는 JS 토큰(espree · ESLint가 쓰는 파서 · package-lock 고정 판)으로 문자열 · 템플릿 조각을 떼어 세요.
# `webcounts.same_text()`의 정규식(`STRING_RE`)은 줄인 묶음 안의 정규식 · 따옴표 섞인 글에서 짝이 어긋나 같은 글을 놓쳐요
# (P1-01c 셈 4 · 같은 묶음을 토큰으로 세면 20 · 묶음 끝에 일부러 넣은 같은 글 둘도 못 봄 · P1-04 보고). 기준선 기록 ·
# `test_baseline_web.py`는 그 셈 그대로 두고, 장치는 이 셈으로 해요. 규칙(8자 이상 · 한글 하나 이상 · 묶음 안 두 번 이상)은 같아요.
DIST_SCRIPT = r"""
import * as espree from 'espree';
import { readFileSync, readdirSync } from 'node:fs';
const dir = 'dist/assets';
const counts = {};
for (const f of readdirSync(dir).filter((f) => f.endsWith('.js')).sort()) {
  const code = readFileSync(`${dir}/${f}`, 'utf8');
  for (const t of espree.tokenize(code, { ecmaVersion: 'latest', sourceType: 'module' })) {
    let v;
    if (t.type === 'String') v = t.value.slice(1, -1);
    else if (t.type === 'Template') v = t.value.replace(/^[`}]/, '').replace(/(`|\$\{)$/, '');
    else continue;
    if (v.length >= 8 && /[가-힣]/.test(v)) counts[v] = (counts[v] ?? 0) + 1;
  }
}
console.log(JSON.stringify(counts));
"""


def found_web_dist_same_text() -> Counter[Key]:
    import subprocess

    from tests.baseline import webcounts

    if not sorted((webcounts.WEB / "dist" / "assets").glob("*.js")):
        raise RuntimeError("web/dist가 없어요 · `npm run build` 뒤에 돌려요(check.sh의 structure-dist 단계)")
    p = subprocess.run(["node", "--input-type=module", "-e", DIST_SCRIPT], cwd=webcounts.WEB, capture_output=True,
                       text=True, timeout=120)
    if p.returncode != 0:
        raise SystemExit(f"빌드 결과 토큰 셈 실패(exit {p.returncode}):\n{p.stderr[-2000:]}")
    return Counter({(t,): n for t, n in json.loads(p.stdout).items() if n > 1})


def found_web_raw_tokens() -> Counter[Key]:
    from tests.baseline import webcounts

    return Counter((h["file"],) for h in webcounts.raw_tokens()["raw_token_hits"])


def found_web_px() -> Counter[Key]:
    from tests.baseline import webcounts

    return Counter((h["file"], h["prop"]) for h in webcounts.raw_tokens()["px_literal_hits"])


BE = "src/screens/BlockEditor/"


def _dup_reason(key: Key) -> str:
    be = " · BlockEditor/*" if any(BE in k for k in key) else ""
    return "[1단계 예외] 웹 중복 1% 문턱은 3단계(P1-13 · 부품 합치기)" + be


def _css_reason(key: Key) -> str:
    be = " · BlockEditor/*" if any(BE in k for k in key) else ""
    return "[1단계 예외] 같은 CSS 0 문턱은 3단계(P1-13)" + be


def _token_reason(key: Key) -> str:
    return "[1단계 예외] BlockEditor/*(ARCHITECTURE 6절)" if key[0].startswith(BE) else "[P1-12] 같은 값의 의미 토큰으로"


# P1-04 시작 숫자(지운 뒤 · 서버는 P1-03a 보고 · 웹은 P1-03b 보고 5절 '지운 뒤' 열과 같음 · 빌드 결과 같은 글만 토큰 셈 20)
GUARDS: tuple[Guard, ...] = (
    Guard("layers", "파이썬 층 어긋남(ARCHITECTURE 2절 · 하위 폴더 · 함수 안 import 포함)", 12, found_layers),
    Guard("sql", "SQL 위치(`db.py` · `store/` 밖)", 203, found_sql),
    Guard("time-literals", "시각 숫자(`domain/markets/kr.py` · `run/scheduler.py` 밖 · 서버)", 23, found_time_literals),
    Guard("same-text", "같은 글(서버 · 8자 이상 한글)", 38, found_same_text, text_key=True, unit="keys"),
    Guard("py-duplicates", "중복 · 파이썬(같은 본문 · 모듈 사이 같은 이름)", 0, found_py_duplicates, has_list=False),
    Guard("web-boundaries", "화면 경계(ARCHITECTURE 3절 · 지금 폴더로 셈 · ESLint와 같은 규칙)", 33, found_web_boundaries),
    Guard("web-duplication", "중복 · 웹(jscpd 복제 수 · 파일 쌍)", 29, found_web_duplication, new_reason=_dup_reason),
    Guard("web-same-css", "같은 CSS 본문(선언 3개 이상 · 파일 묶음)", 20, found_web_same_css, new_reason=_css_reason),
    Guard("web-same-text", "같은 글(웹)", 20, found_web_same_text, text_key=True, unit="keys"),
    Guard("web-server-same-text", "같은 글(서버 ↔ 웹)", 28, found_web_server_same_text, text_key=True, unit="keys"),
    Guard("web-dist-same-text", "같은 글(빌드 결과 · JS 토큰으로 셈)", 20, found_web_dist_same_text, text_key=True, unit="keys"),
    Guard("web-raw-tokens", "원시 토큰 직접 사용(screens · components · charts)", 183, found_web_raw_tokens, new_reason=_token_reason),
    Guard("web-px", "위치 · 모서리 px 리터럴(screens · components · charts)", 9, found_web_px, new_reason=_token_reason),
)
BY_NAME = {g.name: g for g in GUARDS}


def set_start(g: Guard, new: int) -> str | None:
    """`GUARDS`에 있는 장치면 이 파일의 시작 숫자를 `new`로 낮춰요(올리지 않음 · 시험의 가짜 장치는 건드리지 않음)."""
    if BY_NAME.get(g.name) is not g or new >= g.start:
        return None
    src = SOURCE
    text = src.read_text(encoding="utf-8")
    pat = re.compile(r'(Guard\("' + re.escape(g.name) + r'", "[^"]*", )' + str(g.start) + r",")
    text, n = pat.subn(lambda m: m.group(1) + f"{new},", text)
    if n != 1:
        return f"{g.name}: 시작 숫자를 고칠 자리를 못 찾았어요 · 손으로 {g.start} → {new}"
    src.write_text(text, encoding="utf-8")
    return f"{g.name}: 시작 숫자 {g.start} → {new}(tests/structure_guards.py)"


def check(g: Guard) -> tuple[Counter[Key], list[str]]:
    found = g.found()
    return found, compare(g, found, load(g))


def shrink(g: Guard) -> list[str]:
    """줄어든 수만 목록에 반영(줄 지움 · 수 줄임 · 까닭 그대로). 늘거나 새 키는 바꾸지 않고 알려요."""
    if not g.has_list:
        return []
    p = path_of(g)
    found = g.found()
    allowed = load(g)
    notes = []
    lines = p.read_text(encoding="utf-8").splitlines()
    by_line = {e.line: (k, e) for k, e in allowed.items()}
    out = []
    for n, raw in enumerate(lines, 1):
        if n not in by_line:
            out.append(raw)
            continue
        key, e = by_line[n]
        f = found.get(key, 0)
        if f == 0:
            notes.append(f"{g.name}: 지움 {raw.strip()}")
            continue
        if f < e.count:
            notes.append(f"{g.name}: {e.count} → {f} {' '.join(key)}")
            out.append(format_line(key, f, e.reason, text_key=g.text_key))
        else:
            out.append(raw)
    for key in sorted(set(found) - set(allowed)):
        notes.append(f"{g.name}: 새 어긋남은 목록에 더하지 않아요 {key}: {found[key]}")
    p.write_text("\n".join(out) + "\n", encoding="utf-8")
    note = set_start(g, units({k: e.count for k, e in load(g).items()}, g.unit))
    return notes + ([note] if note else [])


def retake(g: Guard) -> list[str]:
    """다시 재기(다른 일감을 합친 뒤 · 예: P1-12 토큰 이름 바꿈으로 같은 CSS · 복제 묶음이 다른 파일 쌍으로 갈라짐).

    지금 셈으로 목록을 다시 써요. **지금 전체가 목록 전체 이하**일 때만(줄어들기만 · '수로 셈') · 있던 키의 까닭은 그대로 ·
    새 키는 `new_reason`(장치마다 정한 꼬리표)으로. `GUARDS`의 시작 숫자도 지금 전체로 낮춰요(`set_start`). 목록 diff는
    검토에서 봐요.
    """
    if not g.has_list:
        return []
    found, allowed = g.found(), load(g)
    total_f = units(dict(found), g.unit)
    total_a = units({k: e.count for k, e in allowed.items()}, g.unit)
    if total_f > total_a or total_f > g.start:
        return [f"{g.name}: 지금 {total_f} > 목록 {total_a}(또는 시작 {g.start}) · 다시 재지 않아요(새 어긋남을 고쳐요)"]
    new = sorted(set(found) - set(allowed))
    if new and g.new_reason is None:
        return [f"{g.name}: 새 키 {len(new)}개에 붙일 까닭이 정해지지 않은 장치예요 · 손으로 고쳐요: {new[:3]}"]
    p = path_of(g)
    head = [raw for raw in p.read_text(encoding="utf-8").splitlines() if raw.strip().startswith("#") or not raw.strip()]
    body = [format_line(k, found[k], allowed[k].reason if k in allowed else g.new_reason(k), text_key=g.text_key)  # type: ignore[misc]
            for k in sorted(found)]
    p.write_text("\n".join(head + body) + "\n", encoding="utf-8")
    note = set_start(g, total_f)
    return [f"{g.name}: 다시 잼 {total_a} → {total_f}(키 {len(allowed)} → {len(found)} · 새 키 {len(new)})"] + \
        ([note] if note else [])


def main(argv: list[str]) -> int:
    cmds = ("check", "shrink", "retake")
    cmd = argv[0] if argv and argv[0] in cmds else "check"
    names = [a for a in argv if a not in cmds] or [g.name for g in GUARDS]
    bad = skipped = 0
    for name in names:
        g = BY_NAME[name]
        try:
            if cmd in ("shrink", "retake"):
                lines = shrink(g) if cmd == "shrink" else retake(g)
            else:
                found, lines = check(g)
                print(f"{name}: 지금 {units(dict(found), g.unit)} · 시작 {g.start} · 어긋남 {len(lines)}")
                bad += bool(lines)
        except RuntimeError as e:
            print(f"{name}: 건너뜀(셀 수 없음) · {e}")
            skipped += 1
            continue
        for line in lines:
            print("  " + line)
    if skipped and not bad:
        print(f"건너뛴 장치 {skipped}개 · 종료 2(통과로 보지 않아요)")
    return 1 if bad else (2 if skipped else 0)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
