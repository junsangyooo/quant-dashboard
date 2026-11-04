"""'남는 것 / 지울 것'의 경계(P1-01a 8절 분류 표 · TASKS P1-03 목록을 그대로 옮김).

기준선 기록은 이 경계로 '남는 것'과 '지울 것'을 나누고, 대조(`compare.py`)는 '남는 것'만 봐요.
라우트 · 모듈 · 시험 파일 · 시험 함수의 네 가지예요. 줄 번호는 `8b67df6` 기준이에요.

P1-03a가 실제로 지운 것과 같아요(`tests/baseline/reports/P1-03a.md`): 라우트 21 · 모듈 11 · 시험 파일 9 모두 통째로 지움 ·
부분 파일의 '남는(옮긴)' 함수는 `tests/test_api_secrets.py` · `tests/test_access.py` · `tests/test_words.py`로 옮겨 갔어요
(아래 표의 함수 이름 그대로 · 기준선 `api_shapes.json`의 관측은 옛 nodeid 기준이라 이 표는 그대로 둬요). `test_copytext.py`의
API 시험 2건(`test_import_api_flow` · `test_import_api_rejects_bad_links`)은 지운 MVP 라우트의 응답 모양을 단언해서 옮기지 못하고
지웠어요(P1-03a 보고 · 가정). 그래서 그 파일도 통째로 사라졌어요.
"""

from __future__ import annotations

# `main.py` 699-1107행 · 1223-1262행의 라우트(MVP 전략 · MVP 백테스트 · MVP 모의투자 · MVP 화면)
DELETED_ROUTES: frozenset[str] = frozenset({
    "GET /api/catalog",
    "GET /api/strategies",
    "POST /api/strategies",
    "GET /api/strategies/{sid}",
    "POST /api/strategies/{sid}/versions",
    "POST /api/strategies/{sid}/check",
    "GET /api/versions/{vid}",
    "GET /api/strategies/{sid}/copytext",
    "POST /api/import/preview",
    "POST /api/import/accept",
    "DELETE /api/strategies/{sid}",
    "POST /api/backtest",
    "POST /api/paper/start",
    "GET /api/paper/preview",
    "POST /api/paper/judge",
    "POST /api/paper/stop",
    "GET /api/home",
    "GET /api/plan",
    "GET /api/paper/runs",
    "GET /api/paper/runs/{rid}",
    "GET /api/history",
})

# 통째로 지우는 서버 모듈(`app/` 기준 상대 경로)
DELETED_MODULES: frozenset[str] = frozenset({
    "app/v1/__init__.py", "app/v1/engine.py", "app/v1/graph.py", "app/v1/pieces.py", "app/v1/strategy.py",
    "app/engine_v1.py", "app/strategy.py", "app/engine_mvp.py", "app/paper.py", "app/graph.py", "app/pieces.py",
})

# 통째로 지우는 시험 파일 · 도구
DELETED_TEST_FILES: frozenset[str] = frozenset({
    "tests/test_engine_paper.py", "tests/test_fix1.py", "tests/test_graph.py", "tests/test_graph_engine.py",
    "tests/test_graph_mirror.py", "tests/test_mvp_api.py", "tests/test_regression.py", "tests/test_engine_v1.py",
    "tests/test_threshold.py",
})

# 파일은 남지만(또는 옮겨지지만) 함수 일부만 지우는 경우: 파일 → 남는(옮기는) 함수 이름. 그 밖은 지움.
KEPT_FUNCS_IN_PARTIAL_FILES: dict[str, frozenset[str]] = {
    "tests/test_mvp_api.py": frozenset({
        "test_password_change", "test_password_change_counts_toward_lock", "test_password_change_keeps_recovery_code",
        "test_password_change_needs_login", "test_public_ip_only_when_asked", "test_public_ip_needs_login",
        "test_offline_env_never_reaches_out", "test_serves_built_screens",
    }),
    "tests/test_fix1.py": frozenset({
        "test_lock_ends_every_session_and_clears_the_key", "test_restarted_flag_until_first_login",
        "test_lock_drops_the_toss_client", "test_session_expiry_drops_the_toss_client",
        "test_last_session_logout_drops_the_toss_client",
    }),
    "tests/test_copytext.py": frozenset({  # 금지어 3건만 옮김(tests/test_words.py) · API 2건은 지움(P1-03a 가정)
        "test_forbidden_list_is_the_glossary", "test_forbidden_rule_catches_and_allows", "test_server_text_forbidden_words",
    }),
}

# 남는 파일 안에서 지우는 함수(접두어로 · `test_baseline_frozen.py` 2부)
DELETED_FUNC_PREFIXES: dict[str, tuple[str, ...]] = {
    "tests/test_baseline_frozen.py": ("test_v1_",),
}


def route_is_kept(method: str, path: str) -> bool:
    return f"{method.upper()} {path}" not in DELETED_ROUTES


def module_is_kept(rel: str) -> bool:
    return rel not in DELETED_MODULES


def test_is_kept(nodeid: str) -> bool:
    """pytest nodeid(`tests/test_x.py::test_f[param]`)가 P1-03 뒤에도 남는 시험인가."""
    file, _, rest = nodeid.partition("::")
    func = rest.split("[", 1)[0].split("::")[-1]
    if file in DELETED_TEST_FILES and file not in KEPT_FUNCS_IN_PARTIAL_FILES:
        return False
    if file in KEPT_FUNCS_IN_PARTIAL_FILES:
        return func in KEPT_FUNCS_IN_PARTIAL_FILES[file]
    for prefix in DELETED_FUNC_PREFIXES.get(file, ()):
        if func.startswith(prefix):
            return False
    return True
