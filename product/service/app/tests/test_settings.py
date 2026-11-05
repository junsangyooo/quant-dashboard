"""설정 한 곳(P1-05 · ARCHITECTURE 6절 '설정' · QUALITY X5): 환경 변수 · 설정 파일은 `app/settings.py`만 읽어요."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from app import settings
from app.app import create_app

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "app" / "settings.py"


def environ_hits(paths: list[Path]) -> list[str]:
    """`os.environ` · `os.getenv` · `os.putenv` · `from os import environ/getenv` · `os.environb`를 쓰는 자리."""
    hits = []
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("environ", "environb", "getenv", "putenv"):
                hits.append(f"{path.name}:{node.lineno}: .{node.attr}")
            elif isinstance(node, ast.ImportFrom) and node.module == "os":
                hits += [f"{path.name}:{node.lineno}: from os import {a.name}" for a in node.names
                         if a.name in ("environ", "environb", "getenv", "putenv")]
    return hits


def test_os_environ_only_in_settings() -> None:
    others = [p for p in sorted((ROOT / "app").rglob("*.py")) if p != SETTINGS]
    assert others and environ_hits(others) == []
    assert environ_hits([SETTINGS])  # settings는 읽어요(장치가 살아 있는지)


def test_environ_scan_catches_planted_reads(tmp_path: Path) -> None:
    planted = tmp_path / "planted.py"
    planted.write_text("import os\nfrom os import getenv\nA = os.environ.get('X')\nB = os.getenv('Y')\n", encoding="utf-8")
    assert len(environ_hits([planted])) == 3


def test_load_reads_the_contract_names_once() -> None:
    env = {"MVP_DATA_DIR": "/d", "MVP_PORT": "8799", "MVP_WEB_DIST": "/w", "QUANT_TS_NAME": "a.ts.net",
           "QUANT_LIVE_TRANSPORT": "1", "OTHER": "x"}
    cfg = settings.load(env, [])
    assert (cfg.data_dir, cfg.port, cfg.web_dist, cfg.ts_name) == ("/d", 8799, "/w", "a.ts.net")
    assert dict(cfg.live_env) == {"QUANT_LIVE_TRANSPORT": "1"} and cfg.live_config_paths == ()
    env["MVP_PORT"] = "1"  # 읽은 뒤 바뀌어도 값 묶음은 그대로
    assert cfg.port == 8799


def test_load_defaults_and_empty_values() -> None:
    cfg = settings.load({"MVP_DATA_DIR": "", "MVP_PORT": "", "MVP_WEB_DIST": ""}, None)
    assert (cfg.data_dir, cfg.port, cfg.web_dist, cfg.ts_name) == (None, 8765, None, None)
    assert cfg.live_env == {} and cfg.live_config_paths == settings.LIVE_CONFIG_PATHS
    with pytest.raises(ValueError):  # 숫자가 아닌 포트는 전처럼 쓸 때 실패
        _ = settings.load({"MVP_PORT": "abc"}).port


def test_create_app_uses_settings_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """조립이 settings의 값을 받아 써요(데이터 폴더 · 포트 Host 검사 · Tailscale 이름)."""
    monkeypatch.setenv("MVP_DATA_DIR", str(tmp_path / "from-env"))
    monkeypatch.setenv("MVP_PORT", "8791")
    app = create_app(scheduler=False)
    assert Path(app.state.db.path).parent == tmp_path / "from-env"
    from fastapi.testclient import TestClient

    with TestClient(app, base_url="http://127.0.0.1:8791") as c:
        assert c.get("/api/health").status_code == 200
    with TestClient(app, base_url="http://127.0.0.1:8765") as c:
        assert c.get("/api/health").status_code == 403


def test_live_gate_reads_settings_config(tmp_path: Path) -> None:
    on = tmp_path / "live-transport.json"
    on.write_text(json.dumps({"live_transport": True}), encoding="utf-8")
    cfg = settings.load({"QUANT_LIVE_TRANSPORT": "1"}, [on])
    assert settings.live_enabled(cfg.live_env, cfg.live_config_paths) is True
    assert settings.live_enabled(settings.load({}, [on]).live_env, [on]) is False
