"""서버 쪽 숫자(ARCHITECTURE 7절 셈 규칙 · P1-04가 시험으로 쓸 수 있게 함수로).

셈 범위는 `app/` 아래 파이썬 파일(하위 폴더 포함 · 시험 뺌)이고, 모듈마다 '남는/지울'(`scope.DELETED_MODULES`)을
붙여요. 1단계에는 `app/` 아래에 층 폴더가 아직 없어서, 층 어긋남은 **ARCHITECTURE 2-1 표의 '새 자리'로 모듈을 층에
붙인 뒤** 2절 표의 '가져와도 됨'으로 세요(가정 · 보고 10절). 모든 함수는 경로를 저장소 안 상대 경로로만 적어요.

- 줄 수: 파일의 줄 수(빈 줄 포함) · 모듈 수(남는/지울).
- 층 어긋남: 모듈 맨 위 · 함수 안 import 모두(`app.*`만) · 허용 표 밖 간선 수 + 바깥 금지(domain ← fastapi · sqlite3,
  run · services ← fastapi).
- 중복(파이썬): 맨 위 공개 함수(5줄 이상 · 이름 `main` 뺌)의 AST 본문 해시가 같은 묶음 · 모듈 사이 같은 이름.
- SQL 위치: sqlite3 호출(`sqlite3.` 속성) · SQL 낱말로 시작하는 문자열 · `db.py`(저장 층 자리) 밖.
- 시각 숫자: 독스트링을 뺀 문자열 속 `HH:MM` · 시각 생성자(`time(h, m)` · `.replace(hour=…)`).
- 같은 글: 8자 이상 한글이 든 문자열(독스트링 · 주석 뺌)이 두 곳 이상에 있는 것(서버 쪽만 · 웹은 P1-01c).
"""

from __future__ import annotations

import ast
import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from tests.baseline.scope import DELETED_MODULES

APP = Path(__file__).resolve().parents[2]  # product/service/app
HANGUL = re.compile(r"[가-힣]")
HHMM = re.compile(r"(?<![\d:])([01]?\d|2[0-3]):[0-5]\d(?![\d:])")
SQL_WORDS = ("SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "PRAGMA", "WITH", "DROP", "ALTER", "BEGIN", "COMMIT")

# ARCHITECTURE 2-1: 지금 모듈 → 새 층(1단계 셈용 · `__init__`은 어디서나 가져와도 되는 공용 값)
LAYER_OF: dict[str, str] = {
    "app/serve.py": "entry", "app/install.py": "entry", "app/main.py": "assembly", "app/__init__.py": "shared",
    "app/api_v2.py": "api", "app/updates.py": "services", "app/datamgmt.py": "services",
    "app/connect.py": "security", "app/vault.py": "security",
    "app/live.py": "run", "app/paper_v2.py": "run", "app/backtest_v2.py": "run", "app/schedule.py": "run",
    "app/market.py": "run",
    "app/toss.py": "adapters", "app/dart.py": "adapters", "app/telegram.py": "adapters",
    "app/transport.py": "adapters", "app/publicip.py": "adapters",
    "app/db.py": "store",
    "app/catalog.py": "domain", "app/indicators.py": "domain", "app/fundamentals.py": "domain",
    "app/rules.py": "domain", "app/blocks.py": "domain", "app/engine.py": "domain", "app/copytext.py": "domain",
}
ALL_LAYERS = {"entry", "assembly", "api", "services", "run", "orders", "store", "security", "adapters", "ports",
              "domain", "copy", "settings", "shared"}
ALLOWED: dict[str, set[str]] = {
    "entry": {"assembly", "settings"},
    "assembly": set(ALL_LAYERS),
    "api": {"services", "run", "store", "domain", "security", "copy"},
    "services": {"domain", "orders", "store", "ports", "security", "copy"},
    "run": {"domain", "orders", "ports", "store", "copy"},
    "orders": {"domain"},
    "store": {"domain"},
    "security": {"store", "domain"},
    "adapters": {"ports", "domain", "settings"},
    "ports": {"domain"},
    "domain": {"domain"},
    "copy": set(),
    "settings": set(),
    "shared": set(),
}
FORBIDDEN_EXTERNAL: dict[str, set[str]] = {
    "domain": {"fastapi", "sqlite3", "starlette"},
    "run": {"fastapi", "starlette"},
    "services": {"fastapi", "starlette"},
    "store": {"fastapi", "starlette"},
}


def rel(p: Path) -> str:
    return p.relative_to(APP).as_posix()


def app_files() -> list[Path]:
    return sorted(p for p in (APP / "app").rglob("*.py"))


def is_kept(p: Path) -> bool:
    return rel(p) not in DELETED_MODULES


def _parse(p: Path) -> ast.Module:
    return ast.parse(p.read_text(encoding="utf-8"))


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def _strings(tree: ast.AST) -> list[tuple[str, int]]:
    """독스트링을 뺀 문자열 상수(값 · 줄)."""
    docs = _docstring_nodes(tree)
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs:
            out.append((node.value, node.lineno))
    return out


# ── 줄 수 · 모듈 수 ──────────────────────────────────────────────────────────


def lines() -> dict[str, Any]:
    per = {}
    for p in app_files():
        per[rel(p)] = {"lines": len(p.read_text(encoding="utf-8").splitlines()), "kept": is_kept(p)}
    kept = [v for v in per.values() if v["kept"]]
    gone = [v for v in per.values() if not v["kept"]]
    return {"modules": len(per), "modules_kept": len(kept), "modules_deleted": len(gone),
            "lines": sum(v["lines"] for v in per.values()), "lines_kept": sum(v["lines"] for v in kept),
            "lines_deleted": sum(v["lines"] for v in gone), "per_module": per}


# ── 층 어긋남 ────────────────────────────────────────────────────────────────


def _imports(tree: ast.AST, module_rel: str) -> list[tuple[str, int, bool]]:
    """(가져오는 모듈 이름 · 줄 · 함수 안인가). 상대 import는 `app.x` 꼴로 풀어요."""
    out = []
    pkg = module_rel.rsplit("/", 1)[0].replace("/", ".")  # app 또는 app.v1

    def walk(node: ast.AST, inside: bool) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Import):
                for a in child.names:
                    out.append((a.name, child.lineno, inside))
            elif isinstance(child, ast.ImportFrom):
                if child.level:
                    base = pkg.rsplit(".", child.level - 1)[0] if child.level > 1 else pkg
                    mod = f"{base}.{child.module}" if child.module else base
                    if not child.module:  # from . import x → app.x
                        for a in child.names:
                            out.append((f"{base}.{a.name}", child.lineno, inside))
                        continue
                else:
                    mod = child.module or ""
                out.append((mod, child.lineno, inside))
            walk(child, inside or isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef))

    walk(tree, False)
    return out


def _layer_of_import(name: str) -> str | None:
    """`app.x` → 층. 지워질 모듈이나 app 밖이면 None."""
    if not name.startswith("app"):
        return None
    parts = name.split(".")
    if len(parts) < 2:
        return "shared"
    candidates = ["app/" + "/".join(parts[1:]) + ".py", "app/" + "/".join(parts[1:]) + "/__init__.py"]
    for c in candidates:
        if c in LAYER_OF:
            return LAYER_OF[c]
        if c in DELETED_MODULES:
            return "deleted"
    parent = "app/" + "/".join(parts[1:-1] + ["__init__.py"]) if len(parts) > 2 else "app/__init__.py"
    if parent in LAYER_OF:  # `from . import APP_VERSION_TEXT`처럼 패키지 안의 이름
        return LAYER_OF[parent]
    if parent in DELETED_MODULES:
        return "deleted"
    return "unknown"


def layer_violations() -> dict[str, Any]:
    edges = []
    for p in app_files():
        if not is_kept(p):
            continue
        r = rel(p)
        layer = LAYER_OF.get(r, "unknown")
        for name, line, inside in _imports(_parse(p), r):
            target = _layer_of_import(name)
            top = name.split(".")[0]
            if target is None:
                if top in FORBIDDEN_EXTERNAL.get(layer, set()):
                    edges.append({"from": r, "layer": layer, "import": name, "to_layer": "external", "line": line,
                                  "in_function": inside, "why": f"{layer} ← {top} 금지"})
                continue
            if target in ("deleted", "shared") or target == layer:
                continue
            if target not in ALLOWED.get(layer, set()):
                edges.append({"from": r, "layer": layer, "import": name, "to_layer": target, "line": line,
                              "in_function": inside, "why": f"{layer} ← {target} 허용 표 밖"})
    edges.sort(key=lambda e: (e["from"], e["line"], e["import"]))
    by_module: dict[str, int] = defaultdict(int)
    for e in edges:
        by_module[e["from"]] += 1
    return {"count": len(edges), "by_module": dict(sorted(by_module.items())), "edges": edges,
            "layer_of": LAYER_OF}


# ── 중복(파이썬) ─────────────────────────────────────────────────────────────


def _body_hash(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    body = fn.body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) and \
            isinstance(body[0].value.value, str):
        body = body[1:]
    text = "\n".join(ast.dump(n, annotate_fields=True, include_attributes=False) for n in body)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def duplicates() -> dict[str, Any]:
    funcs = []
    for p in app_files():
        if not is_kept(p):
            continue
        for node in _parse(p).body:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not node.name.startswith("_") \
                    and node.name != "main":
                span = (node.end_lineno or node.lineno) - node.lineno + 1
                if span >= 5:
                    funcs.append({"module": rel(p), "name": node.name, "line": node.lineno, "lines": span,
                                  "hash": _body_hash(node)})
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_name: dict[str, set[str]] = defaultdict(set)
    for f in funcs:
        by_hash[f["hash"]].append(f)
        by_name[f["name"]].add(f["module"])
    same_body = [[{k: f[k] for k in ("module", "name", "line")} for f in v] for v in by_hash.values() if len(v) > 1]
    same_name = {n: sorted(m) for n, m in by_name.items() if len(m) > 1}
    return {"functions": len(funcs), "same_body_groups": len(same_body), "same_body": sorted(same_body, key=str),
            "same_name_across_modules": len(same_name), "same_name": dict(sorted(same_name.items()))}


# ── SQL 위치 ─────────────────────────────────────────────────────────────────


def sql_locations(store_modules: tuple[str, ...] = ("app/db.py",)) -> dict[str, Any]:
    hits = []
    for p in app_files():
        if not is_kept(p):
            continue
        r = rel(p)
        tree = _parse(p)
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "sqlite3":
                hits.append({"module": r, "line": node.lineno, "kind": "sqlite3", "text": f"sqlite3.{node.attr}"})
        for text, line in _strings(tree):
            head = text.lstrip()
            # 대문자 SQL 낱말 + 공백 + 이어지는 글(단계 이름 'select' · HTTP 메서드 'DELETE' 같은 낱말 하나는 아님)
            if any(head.startswith(w + " ") and len(head) > len(w) + 1 for w in SQL_WORDS):
                hits.append({"module": r, "line": line, "kind": "sql", "text": text.strip()[:60]})
    hits.sort(key=lambda h: (h["module"], h["line"]))
    outside = [h for h in hits if h["module"] not in store_modules]
    by_module: dict[str, int] = defaultdict(int)
    for h in outside:
        by_module[h["module"]] += 1
    return {"count_outside_store": len(outside), "count_all": len(hits), "store_modules": list(store_modules),
            "by_module": dict(sorted(by_module.items())), "hits": hits}


# ── 시각 숫자 ────────────────────────────────────────────────────────────────


def time_literals() -> dict[str, Any]:
    hits = []
    for p in app_files():
        if not is_kept(p):
            continue
        r = rel(p)
        tree = _parse(p)
        for text, line in _strings(tree):
            for m in HHMM.finditer(text):
                hits.append({"module": r, "line": line, "kind": "hh:mm", "text": m.group(0)})
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name) and f.id == "time" and len(node.args) >= 2 and \
                        all(isinstance(a, ast.Constant) for a in node.args):
                    hits.append({"module": r, "line": node.lineno, "kind": "time()",
                                 "text": "time(" + ", ".join(str(a.value) for a in node.args) + ")"})  # type: ignore[attr-defined]
                if isinstance(f, ast.Attribute) and f.attr == "replace" and \
                        any(k.arg == "hour" and isinstance(k.value, ast.Constant) for k in node.keywords):
                    hits.append({"module": r, "line": node.lineno, "kind": "replace(hour=)",
                                 "text": ", ".join(f"{k.arg}={getattr(k.value, 'value', '…')}" for k in node.keywords
                                                   if k.arg in ("hour", "minute"))})
    hits.sort(key=lambda h: (h["module"], h["line"], h["text"]))
    by_module: dict[str, int] = defaultdict(int)
    for h in hits:
        by_module[h["module"]] += 1
    return {"count": len(hits), "by_module": dict(sorted(by_module.items())), "hits": hits}


# ── 같은 글 ──────────────────────────────────────────────────────────────────


def same_text() -> dict[str, Any]:
    where: dict[str, list[str]] = defaultdict(list)
    for p in app_files():
        if not is_kept(p):
            continue
        r = rel(p)
        for text, line in _strings(_parse(p)):
            if len(text) >= 8 and len(HANGUL.findall(text)) >= 8:
                where[text].append(f"{r}:{line}")
    dup = {t: sorted(set(v)) for t, v in where.items() if len(set(v)) > 1}
    return {"count": len(dup), "occurrences": sum(len(v) for v in dup.values()),
            "texts": [{"text": t, "where": w} for t, w in sorted(dup.items())]}


def run_all() -> dict[str, Any]:
    ln = lines()
    lv = layer_violations()
    du = duplicates()
    sq = sql_locations()
    tl = time_literals()
    st = same_text()
    return {
        "summary": {
            "lines": ln["lines"], "lines_kept": ln["lines_kept"], "lines_deleted": ln["lines_deleted"],
            "modules": ln["modules"], "modules_kept": ln["modules_kept"], "modules_deleted": ln["modules_deleted"],
            "layer_violations": lv["count"], "duplicate_bodies": du["same_body_groups"],
            "duplicate_names": du["same_name_across_modules"], "sql_outside_store": sq["count_outside_store"],
            "time_literals": tl["count"], "same_text": st["count"],
        },
        "lines": ln, "layers": lv, "duplicates": du, "sql": sq, "time_literals": tl, "same_text": st,
    }


if __name__ == "__main__":
    import json

    print(json.dumps(run_all()["summary"], ensure_ascii=False, indent=1))
