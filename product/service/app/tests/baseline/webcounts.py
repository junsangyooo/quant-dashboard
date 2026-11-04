"""웹 쪽 숫자(ARCHITECTURE 7절 셈 규칙 · 1단계 범위 6절 · P1-04가 시험으로 쓸 수 있게 함수로 · P1-01c).

셈 범위는 `web/src/`(시험 · `node_modules` · `dist`는 뺌 · 빌드 결과는 '같은 글'에서만 따로 봄). 경로는 모두 `web/` 기준 상대
경로예요. 1단계에는 `ds/` · `features/` 폴더가 없어서 ARCHITECTURE 6절 '1단계 예외'대로 지금 폴더를 층에 붙여요:

- `screens/<기능>/` = features(기능 이름은 폴더 이름 · `screens/LoadError.tsx` · `NotFoundScreen.tsx`는 파일 이름이 기능) ·
  `components/` · `charts/` = ds · `api/` · `copy/`(+ `src/copy.ts`) · `lib/` · `shell/`(+ `src/routes.tsx`) · `main.tsx` = 조립 ·
  `styles/` = 토큰 · `graph/` = 지울 것(P1-03 · 셈에는 넣고 표시만).
- 화면 경계(3절 표를 지금 폴더로): ds → features · api · copy · shell 금지 / api → ds · features · shell 금지 / copy → src 안
  무엇이든 금지(copy끼리는 허용 · 가정) / lib → ds · api · copy · features · shell 금지 / features → **다른 features** · shell
  금지 / shell → api 금지 / main.tsx는 무엇이든. 정적 import(`import … from` · `export … from` · `import 'x'`)와 동적
  `import('x')` 모두 세요(주석은 뺌). CSS 모듈 import도 같은 규칙이에요. 바깥 패키지(react 등)는 세지 않아요.
  P1-13 줄의 묶음으로도 세요: 기능끼리(기능 쌍 수) · 기능 → shell(곳 수) · shell → api · lib → copy · lib ↔ charts 순환.
- 웹 중복: jscpd 5.4.2(`npx jscpd@5.4.2` · 고정 판 · `package.json` 수정 0) · 최소 50토큰 · 형식 typescript · tsx · css ·
  시험 · 생성 파일(`styles/tokens.css` · `styles/pretendard.css`) 뺌 · `BlockEditor/*` 포함 / 제외 두 번.
- 같은 CSS 본문: 규칙 `선택자 { 선언 }`(`@media` 안도 규칙마다 · `@font-face` · `@keyframes` 뺌)의 선언을 `속성:값`으로
  정리해 정렬한 묶음이 **3개 이상**이고 같은 묶음이 두 규칙 이상에 있는 것(파일 안 · 파일 사이 모두 · `tokens.css` 뺌) ·
  `BlockEditor/*` 포함 / 제외.
- 원시 토큰 직접 사용: `screens/` · `components/` · `charts/`의 CSS · TSX에서 `var(--<원시 토큰 이름>)`(`design/tokens.json`의
  `layer == "primitive"` 66개 · `/` → `-`) 쓰임 수 · `BlockEditor/*` 제외 / 포함.
- 위치 · 모서리 px 리터럴: 같은 범위의 CSS 선언 `top · right · bottom · left · inset*`과 `border-*radius`의 값에 `px`
  숫자가 직접 든 것(0 · `var()` · `%` · `100%`는 아님) + TSX 인라인 style의 같은 속성(`top: 12` · `'12px'`) ·
  `BlockEditor/*` 제외 / 포함. 덤으로 범위 안 CSS에 정의된 임의 변수(`--x:` 선언 · `tokens.css` 밖)도 세요.
- 토큰 내보내기 대조: `design/tokens-export.json`(Figma 3묶음 · 223) ↔ `web/design/tokens.json`(180) ↔
  `web/src/styles/tokens.css`(`--이름:` 선언): 이름 집합의 차(안 쓰는 43개 = 내보내기에만 있는 이름) · 원시 값 비교(Figma
  rgba 실수 → `#RRGGBB[AA]` 대문자 · FLOAT → 수 · 글꼴 이름 'Pretendard Variable' → 'Pretendard' 규칙 · P1-12) ·
  별칭 비교(`ref`의 `묶음/` 머리를 뗀 이름 == `alias`).
- 같은 글(웹): P1-01b `counts.same_text`와 같은 규칙 — **길이 8자 이상이고 한글(가-힣)이 하나 이상 든 문자열**(주석 뺌 ·
  문자열 리터럴 `'…'` `"…"` `` `…` `` + JSX 글)이 두 곳 이상(파일:줄). 빌드 결과(`web/dist/assets/*.js`)는 같은 규칙의
  문자열이 묶음 안에 두 번 이상 나오는 수. 서버 ↔ 웹은 `counts.py`의 서버 문자열과 웹 문자열의 교집합.
- 줄 수 · 파일 수: `web/src` · `web/tests`의 ts · tsx · css · json(파일마다 남는/지울 · `DELETED_WEB` = P1-01a 8-4).
"""

from __future__ import annotations

import json
import re
import subprocess
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

APP = Path(__file__).resolve().parents[2]
WEB = APP / "web"
SRC = WEB / "src"
SERVICE = APP.parent
HANGUL = re.compile(r"[가-힣]")
JSCPD_VERSION = "5.4.2"
COUNT_DIRS = ("src/screens", "src/components", "src/charts")  # 토큰 셈 범위(ARCHITECTURE 6절 · 1단계)
BLOCK_EDITOR = "src/screens/BlockEditor/"

# P1-01a 8-4 · P1-03 웹 지울 목록(web/ 기준)
DELETED_WEB: tuple[str, ...] = (
    "src/graph/layout.ts", "src/graph/rules.ts", "src/graph/text.ts",
    "src/components/graph/GraphView.tsx", "src/components/graph/PathsPanel.tsx", "src/components/graph/Graph.module.css",
    "src/copy/editor.ts", "src/copy/graph.ts", "src/copy/particles.ts",
    "src/components/Badges.tsx", "src/components/Badges.module.css", "src/components/Chips.tsx",
    "src/components/Chips.module.css", "src/components/Dots.tsx", "src/components/StageIcon.tsx",
    "src/components/StageIcon.module.css", "src/components/Text.tsx", "src/components/Text.module.css",
    "src/components/Toast.tsx", "src/components/Toast.module.css",
    "src/lib/money.ts", "src/lib/runDates.ts", "src/screens/LoadError.tsx",
    "src/api/mvp.ts",
    "tests/graphMirror.test.ts", "tests/particles.test.ts", "tests/money.test.tsx", "tests/runDates.test.ts",
    "tests/fixtures/graph_cases.json",
    "public/flags/kr.svg", "public/flags/us.svg", "public/licenses/flag-icons-MIT.txt",
)


def rel(p: Path) -> str:
    return p.relative_to(WEB).as_posix()


def is_kept(r: str) -> bool:
    return r not in DELETED_WEB


def src_files(exts: tuple[str, ...] = (".ts", ".tsx")) -> list[Path]:
    return sorted(p for p in SRC.rglob("*") if p.suffix in exts and p.is_file())


def strip_comments(code: str) -> str:
    """`/* */`와 `//` 주석을 지워요(URL의 `//`는 남김 · words.test.ts의 screenText와 같은 꼴)."""
    code = re.sub(r"/\*[\s\S]*?\*/", "", code)
    return re.sub(r"(^|[^:'\"`\\])//.*$", r"\1", code, flags=re.M)


# ── 층 · 화면 경계 ──────────────────────────────────────────────────────────


def layer_of(r: str) -> tuple[str, str | None]:
    """web/ 기준 경로 → (층, 기능 이름). 층: features · ds · api · copy · lib · shell · assembly · tokens · graph · other."""
    if not r.startswith("src/"):
        return "other", None
    s = r[4:]
    if s.startswith("screens/"):
        rest = s[len("screens/"):]
        return "features", rest.split("/")[0] if "/" in rest else Path(rest).stem
    if s.startswith(("components/", "charts/")):
        return "ds", None
    if s.startswith("api/"):
        return "api", None
    if s.startswith("copy/") or s == "copy.ts":
        return "copy", None
    if s.startswith("lib/"):
        return "lib", None
    if s.startswith("shell/") or s == "routes.tsx":
        return "shell", None
    if s == "main.tsx":
        return "assembly", None
    if s.startswith("styles/"):
        return "tokens", None
    if s.startswith("graph/"):
        return "graph", None
    return "other", None


FORBIDDEN: dict[str, set[str]] = {
    "ds": {"features", "api", "copy", "shell"},
    "api": {"ds", "features", "shell"},
    "copy": {"ds", "api", "lib", "features", "shell", "assembly", "tokens", "graph"},
    "lib": {"ds", "api", "copy", "features", "shell"},
    "features": {"shell"},  # 다른 features는 아래에서 따로(같은 기능 안은 허용)
    "shell": {"api"},
    "assembly": set(),
    "tokens": {"ds", "api", "copy", "lib", "features", "shell"},
    "graph": set(),  # 지울 것 · 규칙 없음
    "other": set(),
}

IMPORT_RE = re.compile(
    r"""(?:^|[^\w$])(?:import|export)\s+(?:type\s+)?(?:[\w$*{}\s,]+?\s+from\s+)?['"]([^'"]+)['"]"""
    r"""|(?:^|[^\w$.])import\(\s*['"]([^'"]+)['"]\s*\)""",
    re.M,
)


def imports_of(path: Path) -> list[tuple[str, int, bool]]:
    """(지정자, 줄, 동적인가). 주석을 뺀 코드에서 정적 import · export-from · 동적 import()."""
    code = strip_comments(path.read_text(encoding="utf-8"))
    out = []
    for m in IMPORT_RE.finditer(code):
        spec = m.group(1) or m.group(2)
        line = code.count("\n", 0, m.start()) + 1
        out.append((spec, line, m.group(2) is not None))
    return out


def resolve(spec: str, from_file: Path) -> str | None:
    """상대 지정자 → web/ 기준 경로(.ts · .tsx · .css · /index.ts). 바깥 패키지면 None."""
    if not spec.startswith("."):
        return None
    base = (from_file.parent / spec).resolve()
    candidates = [base] if base.suffix in (".ts", ".tsx", ".css", ".json", ".svg", ".txt") else []
    candidates += [base.with_suffix(base.suffix + e) if base.suffix and base.suffix not in (".ts", ".tsx") else
                   Path(str(base) + e) for e in (".ts", ".tsx")]
    candidates += [base / "index.ts", base / "index.tsx"]
    for c in candidates:
        if c.is_file():
            return rel(c)
    return rel(base) + "(?)"


def boundary_violations() -> dict[str, Any]:
    edges = []
    unresolved = []
    for p in src_files():
        r = rel(p)
        layer, feature = layer_of(r)
        for spec, line, dynamic in imports_of(p):
            target = resolve(spec, p)
            if target is None:
                continue
            if target.endswith("(?)"):
                unresolved.append({"from": r, "line": line, "spec": spec})
                continue
            t_layer, t_feature = layer_of(target)
            why = None
            if t_layer in FORBIDDEN.get(layer, set()):
                why = f"{layer} → {t_layer}"
            elif layer == "features" and t_layer == "features" and t_feature != feature:
                why = f"features → other feature ({feature} → {t_feature})"
            if why:
                edges.append({"from": r, "line": line, "to": target, "from_layer": layer, "to_layer": t_layer,
                              "from_feature": feature, "to_feature": t_feature, "dynamic": dynamic, "why": why,
                              "kept": is_kept(r) and is_kept(target)})
    edges.sort(key=lambda e: (e["from"], e["line"], e["to"]))
    feature_pairs = sorted({(e["from_feature"], e["to_feature"]) for e in edges
                            if e["from_layer"] == "features" and e["to_layer"] == "features"})
    lib_to_charts = [e for e in edges if e["from_layer"] == "lib" and e["to"].startswith("src/charts/")]
    charts_to_lib = [e for e in edges if e["from"].startswith("src/charts/") and e["to_layer"] == "lib"]
    # charts → lib 는 허용(ds가 lib의 차트 계산을 씀 · 가정)이라 edges에 없으니 따로 세요
    charts_to_lib_all = [{"from": rel(p), "line": line, "to": resolve(spec, p)} for p in src_files()
                         if rel(p).startswith("src/charts/") for spec, line, _ in imports_of(p)
                         if (resolve(spec, p) or "").startswith("src/lib/")]
    groups = {
        "feature_to_feature_pairs": [f"{a} → {b}" for a, b in feature_pairs],
        "feature_to_feature_places": sum(1 for e in edges if e["from_layer"] == "features" and e["to_layer"] == "features"),
        "feature_to_shell_places": sum(1 for e in edges if e["from_layer"] == "features" and e["to_layer"] == "shell"),
        "shell_to_api_places": sum(1 for e in edges if e["from_layer"] == "shell" and e["to_layer"] == "api"),
        "lib_to_copy_places": sum(1 for e in edges if e["from_layer"] == "lib" and e["to_layer"] == "copy"),
        "lib_to_charts_places": len(lib_to_charts),
        "charts_to_lib_places": len(charts_to_lib) + len(charts_to_lib_all),
        "lib_charts_cycle": bool(lib_to_charts) and bool(charts_to_lib or charts_to_lib_all),
        "ds_to_api_places": sum(1 for e in edges if e["from_layer"] == "ds" and e["to_layer"] == "api"),
    }
    by_kind: dict[str, int] = defaultdict(int)
    for e in edges:
        by_kind[e["why"] if "other feature" not in e["why"] else "features → other feature"] += 1
    return {"count": len(edges), "count_kept": sum(1 for e in edges if e["kept"]), "by_kind": dict(sorted(by_kind.items())),
            "groups": groups, "edges": edges, "unresolved": unresolved,
            "layer_of": {rel(p): layer_of(rel(p))[0] for p in src_files()}}


# ── 웹 중복(jscpd) ──────────────────────────────────────────────────────────


def jscpd(include_block_editor: bool = True) -> dict[str, Any]:
    ignore = ["**/src/styles/tokens.css", "**/src/styles/pretendard.css"]
    if not include_block_editor:
        ignore.append("**/src/screens/BlockEditor/**")
    with tempfile.TemporaryDirectory(prefix="quant-baseline-jscpd-") as d:
        cmd = ["npx", "--yes", f"jscpd@{JSCPD_VERSION}", "src", "--min-tokens", "50", "--reporters", "json", "--output", d,
               "--ignore", ",".join(ignore), "--format", "typescript,tsx,css", "--silent"]
        p = subprocess.run(cmd, cwd=WEB, capture_output=True, text=True)
        report = Path(d) / "jscpd-report.json"
        if p.returncode != 0 or not report.exists():
            raise SystemExit(f"jscpd 실패(exit {p.returncode}):\n{(p.stdout + p.stderr)[-2000:]}")
        data = json.loads(report.read_text(encoding="utf-8"))
    total = data["statistics"]["total"]
    clones = []
    for c in data["duplicates"]:
        a, b = c["firstFile"], c["secondFile"]
        clones.append({"a": f"src/{a['name']}:{a['start']}-{a['end']}", "b": f"src/{b['name']}:{b['start']}-{b['end']}",
                       "lines": c["lines"], "tokens": c["tokens"], "format": c["format"],
                       "block_editor": "BlockEditor/" in a["name"] or "BlockEditor/" in b["name"]})
    clones.sort(key=lambda c: (c["a"], c["b"]))
    return {"version": JSCPD_VERSION, "min_tokens": 50, "include_block_editor": include_block_editor,
            "percentage_lines": round(float(total["percentage"]), 3),
            "percentage_tokens": round(float(total["percentageTokens"]), 3),
            "clones": total["clones"], "duplicated_lines": total["duplicatedLines"], "lines": total["lines"],
            "sources": total["sources"], "clone_list": clones}


# ── CSS ───────────────────────────────────────────────────────────────────


def css_rules(text: str, file: str) -> list[dict[str, Any]]:
    """`선택자 { 선언 }` 목록(`@media` · `@supports` · `@layer` 안도 펼침 · `@font-face` · `@keyframes` · `@import`는 뺌)."""
    text = re.sub(r"/\*[\s\S]*?\*/", "", text)
    rules: list[dict[str, Any]] = []

    def walk(s: str, offset: int, context: str) -> None:
        i = 0
        while True:
            j = s.find("{", i)
            if j < 0:
                return
            head = s[i:j].strip().split(";")[-1].strip()  # `@import …;` 같은 앞 문장은 버림
            depth, k = 1, j + 1
            while k < len(s) and depth:
                depth += s[k] == "{"
                depth -= s[k] == "}"
                k += 1
            body = s[j + 1:k - 1]
            line = text.count("\n", 0, offset + i + s[i:j].rfind(head) if head else offset + j) + 1
            if head.startswith("@"):
                if head.startswith(("@media", "@supports", "@layer", "@container")):
                    walk(body, offset + j + 1, f"{context}{head} ")
            else:
                decls = sorted(f"{p.strip()}:{v.strip()}" for p, v in
                               (d.split(":", 1) for d in body.split(";") if ":" in d))
                rules.append({"file": file, "line": line, "selector": (context + head).strip(), "decls": decls})
            i = k

    walk(text, 0, "")
    return rules


def same_css(include_block_editor: bool = True, min_decls: int = 3) -> dict[str, Any]:
    by_body: dict[str, list[dict[str, Any]]] = defaultdict(list)
    n_rules = 0
    for p in src_files((".css",)):
        r = rel(p)
        if r == "src/styles/tokens.css" or (not include_block_editor and r.startswith(BLOCK_EDITOR)):
            continue
        for rule in css_rules(p.read_text(encoding="utf-8"), r):
            n_rules += 1
            if len(rule["decls"]) >= min_decls:
                by_body["\n".join(rule["decls"])].append({"where": f"{rule['file']}:{rule['line']}", "selector": rule["selector"]})
    groups = [{"decls": k.split("\n"), "rules": v} for k, v in by_body.items() if len(v) > 1]
    groups.sort(key=lambda g: g["rules"][0]["where"])
    return {"include_block_editor": include_block_editor, "min_decls": min_decls, "rules": n_rules,
            "groups": len(groups), "rules_in_groups": sum(len(g["rules"]) for g in groups), "group_list": groups}


# ── 토큰 ──────────────────────────────────────────────────────────────────


def tokens_json() -> list[dict[str, Any]]:
    return json.loads((WEB / "design" / "tokens.json").read_text(encoding="utf-8"))


def css_var(name: str) -> str:
    return "--" + name.replace("/", "-")


def _count_files() -> list[Path]:
    out = []
    for d in COUNT_DIRS:
        out += sorted(p for p in (WEB / d).rglob("*") if p.suffix in (".css", ".tsx") and p.is_file())
    return out


POS_PROPS = re.compile(r"^(top|right|bottom|left|inset(?:-[a-z-]+)?|border(?:-[a-z]+)*-radius)$")
PX_LITERAL = re.compile(r"(?<![\w-])-?\d*\.?\d+px")
TSX_POS = re.compile(r"\b(top|right|bottom|left|inset|border(?:TopLeft|TopRight|BottomLeft|BottomRight)?Radius)\s*:\s*"
                     r"(?:-?\d*\.?\d+(?![\w.%])|['\"]-?\d*\.?\d+px['\"])")


def raw_tokens() -> dict[str, Any]:
    prim = {css_var(t["name"]) for t in tokens_json() if t["layer"] == "primitive"}
    prim_re = re.compile(r"var\((" + "|".join(sorted(map(re.escape, prim), key=len, reverse=True)) + r")\)")
    hits_raw, hits_px, custom = [], [], []
    for p in _count_files():
        r = rel(p)
        code = p.read_text(encoding="utf-8")
        for m in prim_re.finditer(code):
            hits_raw.append({"file": r, "line": code.count("\n", 0, m.start()) + 1, "token": m.group(1)})
        if p.suffix == ".css":
            clean = re.sub(r"/\*[\s\S]*?\*/", "", code)
            for m in re.finditer(r"([\w-]+)\s*:\s*([^;{}]+);", clean):
                prop, value = m.group(1), m.group(2).strip()
                line = clean.count("\n", 0, m.start()) + 1
                if prop.startswith("--"):
                    custom.append({"file": r, "line": line, "name": prop})
                elif POS_PROPS.match(prop) and PX_LITERAL.search(value) and "var(" not in value:
                    hits_px.append({"file": r, "line": line, "prop": prop, "value": value})
        else:
            clean = strip_comments(code)
            for m in TSX_POS.finditer(clean):
                hits_px.append({"file": r, "line": clean.count("\n", 0, m.start()) + 1, "prop": m.group(1),
                                "value": m.group(0).split(":", 1)[1].strip()})

    def split(hits: list[dict[str, Any]]) -> dict[str, Any]:
        outside = [h for h in hits if not h["file"].startswith(BLOCK_EDITOR)]
        by_file: dict[str, int] = defaultdict(int)
        for h in outside:
            by_file[h["file"]] += 1
        return {"all": len(hits), "without_block_editor": len(outside), "by_file_without_block_editor": dict(sorted(by_file.items()))}

    return {"primitive_tokens": len(prim), "raw_token_uses": split(hits_raw), "px_literals": split(hits_px),
            "custom_vars": split(custom), "raw_token_hits": hits_raw, "px_literal_hits": hits_px, "custom_var_hits": custom}


def _figma_value(v: Any, type_: str) -> Any:
    if isinstance(v, dict) and v.get("type") == "VARIABLE_ALIAS":
        return {"alias": v["ref"].split("/", 1)[1]}
    if type_ == "COLOR":
        r, g, b, a = (round(v[k] * 255) for k in ("r", "g", "b", "a"))
        return f"#{r:02X}{g:02X}{b:02X}" + ("" if a == 255 else f"{a:02X}")
    if type_ == "STRING" and v == "Pretendard Variable":
        return "Pretendard"
    return v


def token_crosscheck() -> dict[str, Any]:
    export = json.loads((SERVICE / "design" / "tokens-export.json").read_text(encoding="utf-8"))
    items = tokens_json()
    css = (SRC / "styles" / "tokens.css").read_text(encoding="utf-8")
    css_vars = re.findall(r"^\s*(--[\w-]+):\s*(.+);$", css, flags=re.M)
    css_names = {n for n, _ in css_vars}
    exp: dict[str, dict[str, Any]] = {}
    for layer, coll in export["collections"].items():
        for name, rec in coll.items():
            exp[name] = {"layer": layer, "type": rec["type"], "value": _figma_value(rec["value"][0]["value"], rec["type"])}
    json_by = {t["name"]: t for t in items}
    json_names = set(json_by)
    only_export = sorted(set(exp) - json_names)
    only_json = sorted(json_names - set(exp))
    value_mismatch, alias_mismatch, layer_mismatch = [], [], []
    for name, t in json_by.items():
        e = exp.get(name)
        if e is None:
            continue
        if e["layer"] != t["layer"]:
            layer_mismatch.append({"name": name, "export": e["layer"], "json": t["layer"]})
        if "alias" in t:
            if not (isinstance(e["value"], dict) and e["value"].get("alias") == t["alias"]):
                alias_mismatch.append({"name": name, "export": e["value"], "json": t["alias"]})
        elif e["value"] != t.get("value"):
            value_mismatch.append({"name": name, "export": e["value"], "json": t.get("value")})
    json_css_names = {css_var(n) for n in json_names}
    return {
        "export_count": len(exp), "export_by_layer": {k: len(v) for k, v in export["collections"].items()},
        "export_text_styles": len(export.get("textStyles", [])),
        "json_count": len(items), "json_by_layer": {l: sum(1 for t in items if t["layer"] == l) for l in ("primitive", "semantic", "component")},
        "css_count": len(css_vars),
        "used_in_json": len(json_names & set(exp)), "unused_export_only": len(only_export), "unused_export_only_names": only_export,
        "json_not_in_export": only_json,
        "css_not_in_json": sorted(css_names - json_css_names), "json_not_in_css": sorted(json_css_names - css_names),
        "value_mismatch": value_mismatch, "alias_mismatch": alias_mismatch, "layer_mismatch": layer_mismatch,
        "font_rename_rule": "'Pretendard Variable' → 'Pretendard'",
    }


# ── 같은 글 ───────────────────────────────────────────────────────────────

STRING_RE = re.compile(r"""(['"`])((?:\\.|(?!\1)[^\\])*)\1""")
JSX_TEXT_RE = re.compile(r">([^<>{}]*[가-힣][^<>{}]*)<")


def screen_strings(code: str) -> list[tuple[str, int]]:
    """(글, 줄): 주석을 뺀 코드의 문자열 리터럴 + JSX 글(words.test.ts `screenText`와 같은 꼴)."""
    clean = strip_comments(code)
    out = []
    for m in STRING_RE.finditer(clean):
        out.append((m.group(2), clean.count("\n", 0, m.start()) + 1))
    for m in JSX_TEXT_RE.finditer(clean):
        out.append((m.group(1).strip(), clean.count("\n", 0, m.start()) + 1))
    return out


def _eligible(text: str) -> bool:
    return len(text) >= 8 and bool(HANGUL.search(text))


def same_text() -> dict[str, Any]:
    where: dict[str, list[str]] = defaultdict(list)
    web_texts: set[str] = set()
    for p in src_files():
        r = rel(p)
        for text, line in screen_strings(p.read_text(encoding="utf-8")):
            if _eligible(text):
                where[text].append(f"{r}:{line}")
                web_texts.add(text)
    dup = {t: sorted(set(v)) for t, v in where.items() if len(set(v)) > 1}
    dup_kept = {t: v for t, v in dup.items() if sum(1 for w in v if is_kept(w.rsplit(":", 1)[0])) > 1}
    # 빌드 결과
    dist = WEB / "dist" / "assets"
    dist_dup: dict[str, int] = {}
    dist_files = sorted(dist.glob("*.js")) if dist.exists() else []
    if dist_files:
        counts: dict[str, int] = defaultdict(int)
        for f in dist_files:
            for m in STRING_RE.finditer(f.read_text(encoding="utf-8")):
                t = m.group(2)
                if _eligible(t):
                    counts[t] += 1
        dist_dup = {t: n for t, n in counts.items() if n > 1}
    # 서버 ↔ 웹
    from tests.baseline import counts as server_counts
    server_texts: dict[str, list[str]] = defaultdict(list)
    for p in server_counts.app_files():
        if not server_counts.is_kept(p):
            continue
        for text, line in server_counts._strings(server_counts._parse(p)):
            if _eligible(text):
                server_texts[text].append(f"{server_counts.rel(p)}:{line}")
    shared = sorted(set(server_texts) & web_texts)
    return {
        "web_count": len(dup), "web_count_kept_files_only": len(dup_kept),
        "web_occurrences": sum(len(v) for v in dup.values()),
        "web_texts": [{"text": t, "where": w} for t, w in sorted(dup.items())],
        "dist_files": [f.name for f in dist_files], "dist_count": len(dist_dup),
        "dist_texts": [{"text": t, "times": n} for t, n in sorted(dist_dup.items())],
        "server_web_shared_count": len(shared),
        "server_web_shared": [{"text": t, "server": server_texts[t], "web": sorted(set(where[t]))} for t in shared],
    }


# ── 줄 수 · 파일 수 ────────────────────────────────────────────────────────


def lines_files() -> dict[str, Any]:
    per: dict[str, dict[str, Any]] = {}
    for d in ("src", "tests"):
        for p in sorted((WEB / d).rglob("*")):
            if p.is_file() and p.suffix in (".ts", ".tsx", ".css", ".json"):
                r = rel(p)
                per[r] = {"lines": len(p.read_text(encoding="utf-8").splitlines()), "kept": is_kept(r), "ext": p.suffix[1:]}
    by_ext: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for v in per.values():
        key = "kept" if v["kept"] else "deleted"
        by_ext[v["ext"]][key + "_files"] += 1
        by_ext[v["ext"]][key + "_lines"] += v["lines"]
    deleted_present = [d for d in DELETED_WEB if (WEB / d).exists()]
    return {"files": len(per), "files_kept": sum(1 for v in per.values() if v["kept"]),
            "files_deleted": sum(1 for v in per.values() if not v["kept"]),
            "lines": sum(v["lines"] for v in per.values()), "lines_kept": sum(v["lines"] for v in per.values() if v["kept"]),
            "lines_deleted": sum(v["lines"] for v in per.values() if not v["kept"]),
            "src_lines": sum(v["lines"] for r, v in per.items() if r.startswith("src/")),
            "src_files": sum(1 for r in per if r.startswith("src/")),
            "by_ext": {k: dict(v) for k, v in sorted(by_ext.items())},
            "deleted_list": list(DELETED_WEB), "deleted_present": len(deleted_present), "per_file": per}


def run_all(*, with_jscpd: bool = True) -> dict[str, Any]:
    bd = boundary_violations()
    cs_all, cs_no = same_css(True), same_css(False)
    rt = raw_tokens()
    tk = token_crosscheck()
    st = same_text()
    lf = lines_files()
    out: dict[str, Any] = {
        "summary": {
            "boundary_violations": bd["count"], "boundary_violations_kept": bd["count_kept"],
            "feature_pairs": len(bd["groups"]["feature_to_feature_pairs"]),
            "feature_to_shell": bd["groups"]["feature_to_shell_places"],
            "shell_to_api": bd["groups"]["shell_to_api_places"], "lib_to_copy": bd["groups"]["lib_to_copy_places"],
            "lib_charts_cycle": bd["groups"]["lib_charts_cycle"],
            "same_css_groups": cs_all["groups"], "same_css_groups_without_block_editor": cs_no["groups"],
            "raw_token_uses": rt["raw_token_uses"]["all"], "raw_token_uses_without_block_editor": rt["raw_token_uses"]["without_block_editor"],
            "px_literals": rt["px_literals"]["all"], "px_literals_without_block_editor": rt["px_literals"]["without_block_editor"],
            "custom_vars": rt["custom_vars"]["all"], "custom_vars_without_block_editor": rt["custom_vars"]["without_block_editor"],
            "tokens_export": tk["export_count"], "tokens_json": tk["json_count"], "tokens_css": tk["css_count"],
            "tokens_unused_export_only": tk["unused_export_only"],
            "tokens_value_mismatch": len(tk["value_mismatch"]), "tokens_alias_mismatch": len(tk["alias_mismatch"]),
            "same_text_web": st["web_count"], "same_text_dist": st["dist_count"], "same_text_server_web": st["server_web_shared_count"],
            "files": lf["files"], "files_kept": lf["files_kept"], "files_deleted": lf["files_deleted"],
            "lines": lf["lines"], "lines_kept": lf["lines_kept"], "lines_deleted": lf["lines_deleted"],
        },
        "boundaries": bd, "same_css": cs_all, "same_css_without_block_editor": cs_no, "tokens": rt,
        "token_crosscheck": tk, "same_text": st, "lines": lf,
    }
    if with_jscpd:
        j_all, j_no = jscpd(True), jscpd(False)
        out["summary"].update({"jscpd_pct_lines": j_all["percentage_lines"], "jscpd_clones": j_all["clones"],
                               "jscpd_pct_lines_without_block_editor": j_no["percentage_lines"],
                               "jscpd_clones_without_block_editor": j_no["clones"]})
        out["jscpd"] = j_all
        out["jscpd_without_block_editor"] = j_no
    return out


if __name__ == "__main__":
    import sys

    print(json.dumps(run_all(with_jscpd="--no-jscpd" not in sys.argv)["summary"], ensure_ascii=False, indent=1))
