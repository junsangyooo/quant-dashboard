"""옮긴 모듈을 옛 경로에서 다시 내보내지 않아요(ARCHITECTURE 5 · 6절 · P1-02 ④).

`MOVED`는 '옛 경로 → 새 경로' 목록이에요(지금은 비어 있음 · P1-05 ~ P1-09가 모듈을 옮기며 채워요). 목록의 옛 경로마다:
- 옛 경로의 파일(`app/옛.py` · `app/옛/__init__.py`)이 없어야 하고,
- 옛 경로를 import할 수 없어야 하고(`sys.modules`에 끼워 넣는 꼴도 잡혀요),
- 앱 · 시험 코드 어디서도 옛 경로를 import하지 않아야 해요(시험의 막기(monkeypatch) 경로가 진짜 모듈에 닿게).
- 옛 경로에 같은 이름을 내보내는 모듈을 만들면(`from app.새 import 이름` · `이름 = …`) 위 첫 둘에 걸려요.
- 옛 경로의 부모 패키지 `__init__.py`가 새 경로를 import해 이름을 내보내는 꼴(`app/__init__.py`의 `from app.adapters.publicip
  import fetch_ip` → `app.fetch_ip`)도 잡아요.
장치는 **모듈 단위**예요: 옛 경로(모듈)가 있는지 · import되는지 · 쓰이는지를 봐요. 남는 다른 모듈이 새 경로의 이름을 import해 쓰는
것은 정상이라 보지 않아요(그 모듈이 그 이름을 '다시 내보내는지'는 쓰임과 구별할 수 없어요 · 그런 꼴은 검토에서 봐요).
목록이 비어 있어도 장치는 돌아요: 아래 `test_mechanism_catches_a_planted_reexport`가 임시 폴더에 옛 경로를 만들어 잡는 것을 보여요.
"""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (옛 경로, 새 경로). 예: ("app.publicip", "app.adapters.publicip").
MOVED: list[tuple[str, str]] = []


def _module_files(root: Path, dotted: str) -> list[Path]:
    rel = Path(*dotted.split("."))
    return [p for p in (root / rel.with_suffix(".py"), root / rel / "__init__.py") if p.exists()]


def _imports_of(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names}
    return out


def _importable(dotted: str, root: Path) -> bool:
    """`root`를 맨 앞에 두고 옛 경로를 import해 봐요(임시 폴더의 가짜 패키지도 같은 방법으로 봐요)."""
    saved_path, saved_mods = list(sys.path), dict(sys.modules)
    sys.path.insert(0, str(root))
    for name in [m for m in sys.modules if m == dotted.split(".")[0] or m.startswith(dotted.split(".")[0] + ".")]:
        if root != ROOT:
            del sys.modules[name]  # 임시 폴더 검사는 진짜 app 패키지가 가리지 않게
    try:
        importlib.invalidate_caches()
        importlib.import_module(dotted)
        return True
    except ImportError:
        return False
    finally:
        sys.path[:] = saved_path
        sys.modules.clear()
        sys.modules.update(saved_mods)


def reexport_problems(moved: list[tuple[str, str]], root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    sources = sorted((root / "app").rglob("*.py")) + sorted(
        p for p in (root / "tests").rglob("*.py") if ".tmp" not in p.relative_to(root).parts  # 시험 임시 폴더는 뺌
    )
    for old, new in moved:
        for f in _module_files(root, old):
            problems.append(f"{old}: 옛 경로 파일이 있어요 · {f.relative_to(root).as_posix()}")
        if _importable(old, root):
            problems.append(f"{old}: 옛 경로를 import할 수 있어요(새 경로 {new}만 있어야 해요)")
        for src in sources:
            mods = _imports_of(src)
            if old in mods or any(m.startswith(old + ".") for m in mods):
                problems.append(f"{src.relative_to(root).as_posix()}: 옛 경로 {old}를 import해요 · {new}를 써요")
        # 옛 경로의 부모 패키지들(`app` · `app.x`)의 __init__.py가 새 경로를 import하면 패키지 이름으로 다시 내보내는 꼴
        parts = old.split(".")
        for i in range(1, len(parts)):
            init = root / Path(*parts[:i]) / "__init__.py"
            if init.exists() and any(m == new or m.startswith(new + ".") for m in _imports_of(init)):
                problems.append(f"{init.relative_to(root).as_posix()}: 패키지가 {new}를 import해 다시 내보내요(옛 경로 {old} 자리)")
    return problems


def test_no_old_path_reexports() -> None:
    assert reexport_problems(MOVED) == []


def test_moved_entries_point_at_existing_new_paths() -> None:
    """목록의 새 경로는 실제 모듈이어야 해요(오타 · 지운 모듈을 적어 두는 일이 없게)."""
    for old, new in MOVED:
        assert old != new
        assert _module_files(ROOT, new), f"{new}: 새 경로 모듈이 없어요"


def test_mechanism_catches_a_planted_reexport(tmp_path: Path) -> None:
    """목록이 비어 있어도 장치가 도는 것: 임시 폴더에 '새 경로 + 옛 경로 다시 내보내기 + 옛 경로를 쓰는 시험'을 만들면 셋 다 잡혀요."""
    app = tmp_path / "app"
    (app / "adapters").mkdir(parents=True)
    (app / "__init__.py").write_text("", encoding="utf-8")
    (app / "adapters" / "__init__.py").write_text("", encoding="utf-8")
    (app / "adapters" / "publicip.py").write_text("def fetch_ip() -> str:\n    return '203.0.113.1'\n", encoding="utf-8")
    (app / "publicip.py").write_text("from app.adapters.publicip import fetch_ip  # 옛 경로 다시 내보내기\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_ip.py").write_text("from app.publicip import fetch_ip\n", encoding="utf-8")
    problems = reexport_problems([("app.publicip", "app.adapters.publicip")], root=tmp_path)
    assert problems == [
        "app.publicip: 옛 경로 파일이 있어요 · app/publicip.py",
        "app.publicip: 옛 경로를 import할 수 있어요(새 경로 app.adapters.publicip만 있어야 해요)",
        "tests/test_ip.py: 옛 경로 app.publicip를 import해요 · app.adapters.publicip를 써요",
    ]
    # 옛 경로 파일과 그것을 쓰는 시험을 지우면 깨끗해요
    (app / "publicip.py").unlink()
    (tests / "test_ip.py").unlink()
    assert reexport_problems([("app.publicip", "app.adapters.publicip")], root=tmp_path) == []
    # 부모 패키지 __init__.py로 다시 내보내는 꼴도 잡혀요
    (app / "__init__.py").write_text("from app.adapters.publicip import fetch_ip\n", encoding="utf-8")
    assert reexport_problems([("app.publicip", "app.adapters.publicip")], root=tmp_path) == [
        "app/__init__.py: 패키지가 app.adapters.publicip를 import해 다시 내보내요(옛 경로 app.publicip 자리)",
    ]
