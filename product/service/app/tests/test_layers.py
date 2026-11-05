"""파이썬 층 장치(ARCHITECTURE 2절 · 7절 '파이썬 층' · TASKS P1-04).

표준 라이브러리 AST로 `app/` 아래 모든 모듈(하위 폴더 포함)의 import(모듈 맨 위 · 함수 안 모두)를 세요. 1단계에는 층 폴더가
아직 없어서 지금 모듈을 ARCHITECTURE 2-1 표의 새 자리로 층에 붙여 세요(`tests/baseline/counts.py` `LAYER_OF`). 옮긴 모듈은
폴더(`LAYER_DIRS` · `LAYER_FILES`)로 층이 정해져요. 지금 어긋난 곳은 `tests/allow/layers.txt`(줄마다 까닭)에 있고, 키마다
수가 정확히 같아야 하며 전체는 P1-04 시작 숫자(12) 이하예요(줄어들기만 · `tests/structure_guards.py`).
"""

from __future__ import annotations

import ast

from tests import structure_guards as sg
from tests.baseline import counts


def test_every_app_module_has_a_layer() -> None:
    """층이 정해지지 않은 모듈은 없어요(새 모듈은 2절 표의 폴더에 두거나 `LAYER_OF`에 적어야 들어와요)."""
    unknown = [counts.rel(p) for p in counts.app_files() if counts.layer_of(counts.rel(p)) == "unknown"]
    assert unknown == []


def test_layer_of_follows_architecture_2_1_and_new_folders() -> None:
    assert counts.layer_of("app/live.py") == "run" and counts.layer_of("app/db.py") == "store"
    assert counts.layer_of("app/engine.py") == "domain" and counts.layer_of("app/toss.py") == "adapters"
    assert counts.layer_of("app/serve.py") == "entry" and counts.layer_of("app/main.py") == "assembly"
    # P1-05 ~ P1-09가 만들 자리(하위 폴더까지)
    assert counts.layer_of("app/domain/markets/kr.py") == "domain"
    assert counts.layer_of("app/run/scheduler.py") == "run" and counts.layer_of("app/store/runs.py") == "store"
    assert counts.layer_of("app/adapters/toss.py") == "adapters" and counts.layer_of("app/api/live.py") == "api"
    assert counts.layer_of("app/ports.py") == "ports" and counts.layer_of("app/settings.py") == "settings"
    assert counts.layer_of("app/app.py") == "assembly" and counts.layer_of("app/somewhere.py") == "unknown"


def test_imports_resolve_relative_absolute_and_in_function() -> None:
    code = ("from ..store import runs\nfrom ...domain.markets import kr\nfrom . import scheduler\nimport app.adapters.toss\n"
            "from app import live\n\ndef f():\n    from app.domain import costs\n")
    got = counts._imports(ast.parse(code), "app/run/sub/flow.py")
    assert got == [("app.run.store", 1, False), ("app.domain.markets", 2, False), ("app.run.sub.scheduler", 3, False),
                   ("app.adapters.toss", 4, False), ("app.live", 5, False), ("app.domain", 8, True)]
    got = counts._imports(ast.parse("from ..store import runs\n"), "app/run/live.py")
    assert got == [("app.store", 1, False)]
    assert counts._layer_of_import("app.store") == "store" and counts._layer_of_import("app.live") == "run"
    assert counts._layer_of_import("app.adapters.toss") == "adapters" and counts._layer_of_import("app") == "shared"
    assert counts._layer_of_import("fastapi") is None


def test_allowed_table_is_architecture_2() -> None:
    """2절 표의 '가져와도 됨'(셈에 쓰는 표가 문서와 같은지 한 번 더)."""
    a = counts.ALLOWED
    assert a["api"] == {"services", "run", "store", "domain", "security", "copy"}
    assert a["services"] == {"domain", "orders", "store", "ports", "security", "copy"}
    assert a["run"] == {"domain", "orders", "ports", "store", "copy"}
    assert a["orders"] == {"domain"} and a["store"] == {"domain"} and a["security"] == {"store", "domain"}
    assert a["adapters"] == {"ports", "domain", "settings"} and a["ports"] == {"domain"} and a["domain"] == {"domain"}
    assert a["copy"] == set() and a["settings"] == set() and a["entry"] == {"assembly", "settings"}
    assert counts.FORBIDDEN_EXTERNAL["domain"] >= {"fastapi", "sqlite3"}


def test_layer_violations_only_decrease() -> None:
    found, problems = sg.check(sg.BY_NAME["layers"])
    assert problems == [], "\n".join(problems)
    assert sum(found.values()) <= 12
