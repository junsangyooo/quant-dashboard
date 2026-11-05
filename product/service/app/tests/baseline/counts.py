"""서버 쪽 숫자(ARCHITECTURE 7절 셈 규칙 · P1-04가 시험으로 쓸 수 있게 함수로).

셈 범위는 `app/` 아래 파이썬 파일(하위 폴더 포함 · 시험 뺌)이고, 모듈마다 '남는/지울'(`scope.DELETED_MODULES`)을
붙여요. 1단계에는 `app/` 아래에 층 폴더가 아직 없어서, 층 어긋남은 **ARCHITECTURE 2-1 표의 '새 자리'로 모듈을 층에
붙인 뒤** 2절 표의 '가져와도 됨'으로 세요(가정 · 보고 10절). 모든 함수는 경로를 저장소 안 상대 경로로만 적어요.

- 줄 수: 파일의 줄 수(빈 줄 포함) · 모듈 수(남는/지울).
- 층 어긋남: 모듈 맨 위 · 함수 안 import 모두(`app.*`만) · 허용 표 밖 간선 수 + 바깥 금지(domain ← fastapi · sqlite3,
  run · services ← fastapi).
- 중복(파이썬): 맨 위 공개 함수(5줄 이상 · 이름 `main` 뺌)의 AST 본문 해시가 같은 묶음 · 모듈 사이 같은 이름.
- SQL 위치: sqlite3 호출(`sqlite3.x(...)` 호출만 · `except sqlite3.Error` 같은 참조는 아님) · 대문자 SQL 낱말로
  시작하는 문자열 · `db.py`(저장 층 자리) 밖.
- 시각 숫자: 독스트링을 뺀 문자열 속 `HH:MM` · 시각 생성자 `time(h, m)` · `.replace(hour=…)` · `.at(h, m)`(상수 두 개) ·
  모듈 맨 위 시각 상수 튜플 `NAME = (h, m)`(정수 두 개 · 0 ≤ h ≤ 23 · 0 ≤ m ≤ 59 · 이름에 VERSION이 들어가거나
  `_V<숫자>`로 끝나는 판 번호 튜플 · 함수 안 · 풀어 대입은 뺌).
- 같은 글: **길이 8자 이상이고 한글(가-힣)이 하나 이상 든 문자열**(독스트링 뺌)이 두 곳 이상에 있는 것(서버 쪽만 ·
  웹은 P1-01c).
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
# 옮긴 모듈(P1-05: `catalog` · `indicators` · `fundamentals` · `rules` · `blocks` · `engine` · `copytext` · `stock_names` →
# `app/domain/`)은 새 자리가 `LAYER_DIRS`로 층이 정해져요. 옛 줄은 2-1 표 그대로 남겨 둬요(옛 경로 파일은 없고 · 가져오는 곳 0은
# `tests/test_no_reexport.py`가 봐요 · `tests/test_layers.py`가 이 표를 2-1 표로 읽어요).
LAYER_OF: dict[str, str] = {
    "app/serve.py": "entry", "app/install.py": "entry", "app/main.py": "assembly", "app/__init__.py": "shared",
    "app/api_v2.py": "api", "app/updates.py": "services", "app/datamgmt.py": "services",
    "app/connect.py": "security", "app/vault.py": "security",
    "app/stock_names.py": "domain",  # P1-03: 옛 pieces.py의 종목 이름 사전
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
# ARCHITECTURE 2절 표의 새 자리(P1-05 ~ P1-09가 만듦 · 하위 폴더 포함). 옮긴 모듈은 `LAYER_OF` 줄 대신 이 표로 층이 정해져요
# (P1-04 · `tests/test_layers.py`). 어느 표에도 없는 `app/` 모듈은 'unknown'이고, 그 모듈의 import와 그 모듈로의 import는
# 모두 어긋남으로 세요(새 모듈은 층을 정해야 들어와요).
LAYER_FILES: dict[str, str] = {"app/app.py": "assembly", "app/ports.py": "ports", "app/settings.py": "settings"}
LAYER_DIRS: tuple[tuple[str, str], ...] = (
    ("app/api/", "api"), ("app/services/", "services"), ("app/run/", "run"), ("app/orders/", "orders"),
    ("app/store/", "store"), ("app/security/", "security"), ("app/adapters/", "adapters"), ("app/domain/", "domain"),
    ("app/copy/", "copy"),
)
FORBIDDEN_EXTERNAL: dict[str, set[str]] = {
    "domain": {"fastapi", "sqlite3", "starlette"},
    "run": {"fastapi", "starlette"},
    "services": {"fastapi", "starlette"},
    "store": {"fastapi", "starlette"},
}


def layer_of(module_rel: str) -> str:
    """`app/…py` → 층(`LAYER_OF` · `LAYER_FILES` · `LAYER_DIRS` 차례 · 없으면 'unknown')."""
    if module_rel in LAYER_OF:
        return LAYER_OF[module_rel]
    if module_rel in LAYER_FILES:
        return LAYER_FILES[module_rel]
    for prefix, layer in LAYER_DIRS:
        if module_rel.startswith(prefix):
            return layer
    return "unknown"


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
    pkg = module_rel.rsplit("/", 1)[0].replace("/", ".")  # app 또는 하위 패키지(P1-05 뒤 app.domain 등)

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
                    if mod == "app":  # from app import live → app.live(모듈이 아닌 이름이면 아래에서 'shared')
                        for a in child.names:
                            out.append((f"app.{a.name}", child.lineno, inside))
                        continue
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
        if c in DELETED_MODULES:
            return "deleted"
        if layer_of(c) != "unknown":
            return layer_of(c)
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
        layer = layer_of(r)
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


SQL_HEAD = re.compile(r"^\s*(" + "|".join(SQL_WORDS) + r")(\s+)(.*)$", re.I | re.S)
# 대문자가 아닌 SQL 낱말로 시작하는 글은 SQL 둘째 낱말이 같이 있어야 SQL로 봐요(영어 글 'Select a strategy' ·
# 'update available' · 'with care'는 아님 · 'select id from runs'는 SQL · PRAGMA는 글에 안 쓰는 낱말이라 하나로도).
SQL_SECOND = re.compile(r"\b(from|into|set|table|where|values|join|index|exists|view|trigger|transaction|returning|"
                        r"order\s+by|group\s+by|limit)\b", re.I)


def _is_sql(text: str, *, first_piece: bool = False) -> bool:
    """SQL 낱말 + 공백(줄바꿈 포함) + 이어지는 글. f-string의 첫 조각이면 낱말 + 공백만 봐요(뒤는 식 · 대소문자 ·
    둘째 낱말 규칙은 이어 붙인 글 전체에 따로 · `f"select {cols} from {t}"`). 식으로 시작하는 f-string
    (`f"{x}SELECT * FROM t"`)은 첫 조각이 글이 아니라 세지 않아요(알려진 빈틈 · 지금 `app/`에 0)."""
    m = SQL_HEAD.match(text)
    if not m or (not m.group(3).strip() and not first_piece):
        return False  # 단계 이름 'select' · HTTP 메서드 'DELETE' 같은 낱말 하나는 아님
    if first_piece:
        return True
    word = m.group(1)
    return word.isupper() or word.lower() == "pragma" or bool(SQL_SECOND.search(text))


def _module_aliases(tree: ast.AST, module: str) -> tuple[set[str], dict[str, str]]:
    """(`import module [as x]`의 이름들, `from module import a [as b]`의 b → a)."""
    mods: set[str] = set()
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == module:
                    mods.add(a.asname or a.name)
        elif isinstance(node, ast.ImportFrom) and node.module == module and not node.level:
            for a in node.names:
                names[a.asname or a.name] = a.name
    return mods, names


STORE_DIR = "app/store/"  # P1-07: 저장 층 폴더(ARCHITECTURE 2절 · 기준선 기록의 옛 자리 `app/db.py`는 그대로 셈)


def sql_locations(store_modules: tuple[str, ...] = ("app/db.py",)) -> dict[str, Any]:
    """sqlite3 호출(`import sqlite3 as x` · `from sqlite3 import connect` 이름도 따라감) · SQL 글(독스트링 뺌 ·
    f-string은 첫 조각으로 한 번 · 대소문자 규칙은 `_is_sql`)."""
    hits = []
    for p in app_files():
        if not is_kept(p):
            continue
        r = rel(p)
        tree = _parse(p)
        mods, names = _module_aliases(tree, "sqlite3")
        for node in ast.walk(tree):
            # sqlite3 '호출'만(`except sqlite3.Error` 같은 이름 참조는 아님)
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id in mods:
                    hits.append({"module": r, "line": node.lineno, "kind": "sqlite3", "text": f"sqlite3.{f.attr}()"})
                elif isinstance(f, ast.Name) and f.id in names:
                    hits.append({"module": r, "line": node.lineno, "kind": "sqlite3", "text": f"sqlite3.{names[f.id]}()"})
        in_fstring = {id(v) for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for v in n.values}
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr) and node.values and isinstance(node.values[0], ast.Constant) and \
                    isinstance(node.values[0].value, str):
                whole = "".join(v.value if isinstance(v, ast.Constant) else " ? " for v in node.values)
                if _is_sql(node.values[0].value, first_piece=True) and _is_sql(whole):
                    hits.append({"module": r, "line": node.lineno, "kind": "sql", "text": whole.strip()[:60]})
        docs = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs and \
                    id(node) not in in_fstring and _is_sql(node.value):
                hits.append({"module": r, "line": node.lineno, "kind": "sql", "text": node.value.strip()[:60]})
    hits.sort(key=lambda h: (h["module"], h["line"]))
    outside = [h for h in hits if h["module"] not in store_modules and not h["module"].startswith(STORE_DIR)]
    by_module: dict[str, int] = defaultdict(int)
    for h in outside:
        by_module[h["module"]] += 1
    return {"count_outside_store": len(outside), "count_all": len(hits), "store_modules": list(store_modules),
            "by_module": dict(sorted(by_module.items())), "hits": hits}


# ── 시각 숫자 ────────────────────────────────────────────────────────────────


def _is_clock(h: Any, m: Any) -> bool:
    return isinstance(h, int) and isinstance(m, int) and 0 <= h <= 23 and 0 <= m <= 59


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
        dt_mods, dt_names = _module_aliases(tree, "datetime")
        time_names = {"time"} | {k for k, v in dt_names.items() if v == "time"}
        datetime_names = {k for k, v in dt_names.items() if v == "datetime"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                f = node.func
                # 시각 생성자: `time(h, m)` · `dtime(…)`(별칭) · `datetime.time(…)`(모듈 · 별칭) · `time(hour=…)` /
                # `datetime(y, mo, d, h, m)` · `dt.datetime(…, hour=…)` — 시(hour)가 상수 정수면 셈
                is_time = (isinstance(f, ast.Name) and f.id in time_names) or \
                    (isinstance(f, ast.Attribute) and f.attr == "time" and isinstance(f.value, ast.Name) and f.value.id in dt_mods)
                is_datetime = (isinstance(f, ast.Name) and f.id in datetime_names) or \
                    (isinstance(f, ast.Attribute) and f.attr == "datetime" and isinstance(f.value, ast.Name) and
                     f.value.id in dt_mods)
                if is_time or is_datetime:
                    at = 0 if is_time else 3
                    kw = {k.arg: k.value for k in node.keywords}
                    hour = node.args[at] if len(node.args) > at else kw.get("hour")
                    minute = node.args[at + 1] if len(node.args) > at + 1 else kw.get("minute")
                    if isinstance(hour, ast.Constant) and isinstance(hour.value, int) and not isinstance(hour.value, bool):
                        mv = minute.value if isinstance(minute, ast.Constant) else ("…" if minute is not None else 0)
                        kind = "time()" if is_time else "datetime()"
                        hits.append({"module": r, "line": node.lineno, "kind": kind,
                                     "text": f"{kind[:-2]}({hour.value}, {mv})"})
                if isinstance(f, ast.Attribute) and f.attr == "replace" and \
                        any(k.arg == "hour" and isinstance(k.value, ast.Constant) for k in node.keywords):
                    hits.append({"module": r, "line": node.lineno, "kind": "replace(hour=)",
                                 "text": ", ".join(f"{k.arg}={getattr(k.value, 'value', '…')}" for k in node.keywords
                                                   if k.arg in ("hour", "minute"))})
                # `day.at(h, m)`(DayHours.at · 장 시작에 맞춰 옮기는 시각) · 상수 두 개를 그대로 넘기는 호출
                if isinstance(f, ast.Attribute) and f.attr == "at" and len(node.args) == 2 and \
                        all(isinstance(a, ast.Constant) and isinstance(a.value, int) for a in node.args) and \
                        _is_clock(node.args[0].value, node.args[1].value):  # type: ignore[attr-defined]
                    hits.append({"module": r, "line": node.lineno, "kind": ".at(h, m)",
                                 "text": f".at({node.args[0].value}, {node.args[1].value})"})  # type: ignore[attr-defined]
        # 시각 상수 튜플 `NAME = (h, m)`: 모듈 맨 위 · 이름 하나에 대입 · 정수 두 개 · 0 ≤ h ≤ 23 · 0 ≤ m ≤ 59.
        # 뺌: 이름에 VERSION이 들어가거나 `_V<숫자>`로 끝나는 판 번호 튜플(`APP_VERSION` · `APP_V2`) · 함수 안 ·
        # 풀어 대입(`a, b = 1, 1`). P1-04가 같은 규칙을 써요.
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and \
                    isinstance(node.value, ast.Tuple) and len(node.value.elts) == 2 and \
                    all(isinstance(e, ast.Constant) and isinstance(e.value, int) and not isinstance(e.value, bool)
                        for e in node.value.elts):
                name = node.targets[0].id
                h, m = (e.value for e in node.value.elts)  # type: ignore[attr-defined]
                if _is_clock(h, m) and "VERSION" not in name.upper() and not re.search(r"_V\d+$", name.upper()):
                    hits.append({"module": r, "line": node.lineno, "kind": "(h, m)", "text": f"{name} = ({h}, {m})"})
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
            # 규칙: 길이 8자 이상이고 한글(가-힣)이 하나 이상 든 문자열(숫자 · 기호가 섞인 화면 글도 들어가게)
            if len(text) >= 8 and HANGUL.search(text):
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
