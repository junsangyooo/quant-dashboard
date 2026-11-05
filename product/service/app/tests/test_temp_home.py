"""시험 중 키 파일 · HOME은 임시 폴더(P1-02 ④ · QUALITY S1 · ARCHITECTURE 7절 '자식 프로세스는 HOME을 임시 폴더로').

- conftest가 앱을 import하기 전에 HOME을 운영체제 임시 폴더로 바꿔요. 키 파일 경로(`app.vault.KEYFILE_PATH`)도 autouse
  fixture가 임시 폴더로 바꿔요. 실제 `~/.config/quant-service/`는 만들지도 읽지도 않아요.
- 임시 폴더가 `tests/.tmp`(basetemp)가 아니라 운영체제 임시 폴더인 까닭: 레포 안 키 파일은 앱이 거절해요(`Vault(forbidden_dirs=…)`).
- 자식 프로세스: 시험이 띄우는 pytest(`test_no_orders.py`) · 기준선 도구가 띄우는 pytest · npm · node(`tests.baseline.capture`
  의 `temp_home()`) · 서버(`tests/e2e_server.py` · `tests/baseline/screen_server.py`)가 임시 HOME을 받고 키 파일을 그 아래에만
  만드는 것을 실제로 띄워 확인해요.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from app import vault as vault_mod
from tests import conftest
from tests.baseline import capture
from tests.test_install import _free_port, _http  # 루프백 소켓으로 직접(conftest가 create_connection을 막아요)

APP = Path(__file__).resolve().parent.parent
REPO = APP.parents[2]
TMP = Path(tempfile.gettempdir()).resolve()


def _under_os_tmp(p: Path) -> bool:
    return p.resolve().is_relative_to(TMP)


def test_home_is_a_temp_folder() -> None:
    home = Path(os.environ["HOME"])
    assert home == conftest.TEST_HOME and home.name.startswith("quant-test-home-")
    assert _under_os_tmp(home) and home.is_dir()
    assert not home.is_relative_to(REPO)
    assert str(home) != conftest.REAL_HOME
    assert Path.home() == home  # 앱이 쓰는 Path.home()도 같은 곳


def test_keyfile_path_is_a_temp_folder(keyfile_path: Path) -> None:
    assert vault_mod.KEYFILE_PATH == keyfile_path
    assert keyfile_path.parent.name.startswith("quant-test-kf-") and _under_os_tmp(keyfile_path)
    assert not keyfile_path.is_relative_to(REPO)
    # 앱의 기본 경로도 임시 HOME 아래(실제 홈이 아님)
    assert vault_mod.DEFAULT_KEYFILE_PATH == conftest.TEST_HOME / ".config" / "quant-service" / "keyfile"
    if conftest.REAL_CONFIG_DIR is not None:
        assert not keyfile_path.is_relative_to(conftest.REAL_CONFIG_DIR)
        assert not vault_mod.DEFAULT_KEYFILE_PATH.is_relative_to(conftest.REAL_CONFIG_DIR)


def test_real_config_dir_is_not_created_or_read() -> None:
    """실제 `~/.config/quant-service/`는 conftest가 import될 때와 같아요(항목 · 크기 · 바뀐 시각 · 없었으면 여전히 없음 ·
    끝날 때는 conftest `pytest_sessionfinish`가 한 번 더 봐요). 실제 전송 설정 파일 자리도 비워 둬요."""
    if conftest.REAL_CONFIG_DIR is not None:
        assert conftest.REAL_CONFIG_DIR.exists() == conftest.REAL_CONFIG_EXISTED_AT_START
        assert conftest.config_tree(conftest.REAL_CONFIG_DIR) == conftest.REAL_CONFIG_TREE_AT_START
    import app.settings as settings

    assert settings.LIVE_CONFIG_PATHS == ()


# ── 자식 프로세스 ──────────────────────────────────────────────────────────────


def _wait_http(port: int, proc: subprocess.Popen[str], seconds: float = 60) -> None:
    t0 = time.time()
    while time.time() - t0 < seconds:
        if proc.poll() is not None:
            raise AssertionError(f"서버가 바로 꺼졌어요(exit {proc.returncode}):\n{proc.stderr.read() if proc.stderr else ''}")
        try:
            if _http(port, "GET", "/api/health")[0] == 200:
                return
        except (OSError, ValueError):
            time.sleep(0.1)
    raise AssertionError("서버가 60초 안에 응답하지 않아요")


def _setup(port: int) -> None:
    st, body = _http(port, "POST", "/api/setup", {"password": "correct horse 9", "password2": "correct horse 9",
                                                 "adult": True, "terms": True})
    assert st == 200, body


def _stop(proc: subprocess.Popen[str]) -> None:
    proc.terminate()
    try:
        proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()


def test_temp_home_env_for_children(tmp_path: Path) -> None:
    """`capture.temp_home()`이 주는 환경으로 띄운 자식은 HOME이 임시 폴더예요(진짜 HOME · 시험 HOME 둘 다 아님)."""
    with capture.temp_home() as env:
        home = Path(env["HOME"])
        assert home.name.startswith("quant-baseline-home-") and _under_os_tmp(home) and home.is_dir()
        assert env["HOME"] != conftest.REAL_HOME and env["HOME"] != os.environ["HOME"]
        if "npm_config_cache" in env:  # npx 캐시만 진짜 것을 가리켜요(임시 HOME 밖 · 키와 무관)
            assert Path(env["npm_config_cache"]).is_dir() and not Path(env["npm_config_cache"]).is_relative_to(home)
        out = subprocess.run([sys.executable, "-c", "import os, pathlib; print(os.environ['HOME'], pathlib.Path.home())"],
                             env=env, capture_output=True, text=True, check=True).stdout.split()
        assert out == [str(home), str(home)]
        # 자식 pytest도 같은 환경을 물려받아 HOME 아래에 키 파일 기본 경로를 둬요
        out2 = subprocess.run([sys.executable, "-c", "from app import vault; print(vault.DEFAULT_KEYFILE_PATH)"],
                              env=env, cwd=APP, capture_output=True, text=True, check=True).stdout.strip()
        assert out2 == str(home / ".config" / "quant-service" / "keyfile")
    assert not home.exists()  # 끝나면 지워요


@pytest.mark.parametrize("server", ["tests.e2e_server", "tests.baseline.screen_server"])
def test_child_servers_keep_keyfile_under_temp_home(tmp_path: Path, server: str) -> None:
    """가짜 전송 서버 둘을 임시 HOME · 임시 키 파일 폴더로 띄워 계정을 만들면 키 파일이 그 아래에만 생겨요."""
    port = _free_port()
    # 시험 HOME(`conftest.TEST_HOME`)은 다른 시험이 기본 키 파일 경로로 쓸 수 있어요 → 자식이 거기에 손대지 않았는지는 전후 비교로.
    test_home_before = _tree(conftest.TEST_HOME / ".config")
    with capture.temp_home() as env:
        home = Path(env["HOME"])
        kf_dir = home / "kf"
        env = {**env, "QUANT_E2E_KEYFILE_DIR": str(kf_dir), "QUANT_BASELINE_KEYFILE_DIR": str(kf_dir)}
        data = tmp_path / "data"
        proc = subprocess.Popen([sys.executable, "-m", server, str(data), str(port)], cwd=APP, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            _wait_http(port, proc)
            _setup(port)
            keyfile = kf_dir / "keyfile"
            assert keyfile.exists() and keyfile.stat().st_mode & 0o777 == 0o600
            assert not (data / "keyfile").exists()
            assert conftest.config_tree(conftest.REAL_CONFIG_DIR) == conftest.REAL_CONFIG_TREE_AT_START
            assert _tree(conftest.TEST_HOME / ".config") == test_home_before
            assert [p for p in home.rglob("*") if p.is_file()] == [keyfile]  # 임시 HOME 아래 파일은 키 파일 하나뿐
        finally:
            _stop(proc)
    assert not home.exists()


def _tree(root: Path) -> list[tuple[str, int]]:
    return sorted((p.relative_to(root).as_posix(), p.stat().st_mtime_ns) for p in root.rglob("*")) if root.exists() else []
