"""설정 값 한 곳(ARCHITECTURE 2절 설정 층 · 6절 '설정' · QUALITY X5).

환경 변수와 실제 전송 설정 파일은 **이 파일만** 읽어요. 조립(`app.create_app` · 입구 `serve.main`)이 `load()`를 한 번 불러
값 묶음(`Settings`)을 받고, 그 값을 아래 층에 넘겨요. 다른 파일에서 `os.environ`은 0이에요(`tests/test_settings.py`).

환경 값(모두 선택 · 이름은 바깥 약속 · ARCHITECTURE 5절):
- `MVP_DATA_DIR`: 데이터 폴더(없으면 조립이 정한 기본 폴더)
- `MVP_PORT`: 포트(기본 8765 · Host 검사에도 써요)
- `MVP_WEB_DIST`: 화면 파일 폴더(없으면 `web/dist`)
- `QUANT_TS_NAME`: 등록한 Tailscale 이름(설치기가 서비스 파일에 씀 · 쉼표로 여럿)
- `QUANT_LIVE_TRANSPORT=1`: 실제 전송의 두 열쇠 가운데 하나. 다른 하나는 설치기가 쓰는 설정 파일(`LIVE_CONFIG_PATHS`)의
  `{"live_transport": true}`예요. 둘 다 있어야 `transport.build_transports`가 실제 전송을 만들어요(TASKS T-00).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

ENV_DATA_DIR = "MVP_DATA_DIR"
ENV_PORT = "MVP_PORT"
ENV_WEB_DIST = "MVP_WEB_DIST"
ENV_TS_NAME = "QUANT_TS_NAME"
LIVE_ENV = "QUANT_LIVE_TRANSPORT"
DEFAULT_PORT = 8765
# 설치기가 쓰는 자리: 서버(systemd)는 /etc, PC(launchd)는 사용자 설정 폴더. 레포 · 데이터 폴더 밖이에요.
LIVE_CONFIG_PATHS: tuple[Path, ...] = (
    Path("/etc/quant-service/live-transport.json"),
    Path.home() / ".config" / "quant-service" / "live-transport.json",
)


@dataclass(frozen=True)
class Settings:
    """`load()`가 한 번 읽은 값. 빈 글자는 '없음'(None)과 같게 둬요(전과 같은 `or` 규칙)."""

    data_dir: str | None = None
    port_text: str | None = None
    web_dist: str | None = None
    ts_name: str | None = None
    # 실제 전송 열쇠 ①(환경 변수)의 글자 그대로와 열쇠 ②(설정 파일) 자리 · 판정은 `live_enabled`(전송 문이 불러요)
    live_env: Mapping[str, str] = field(default_factory=dict)
    live_config_paths: tuple[Path, ...] = ()

    @property
    def port(self) -> int:
        """`MVP_PORT`(없으면 8765). 글자가 숫자가 아니면 전처럼 쓰는 순간 ValueError예요."""
        return int(self.port_text or DEFAULT_PORT)


def load(env: Mapping[str, str] | None = None, config_paths: Iterable[Path] | None = None) -> Settings:
    """환경 변수를 한 번 읽어 값 묶음으로(조립이 한 번 불러요)."""
    env = os.environ if env is None else env
    live = env.get(LIVE_ENV)
    return Settings(
        data_dir=env.get(ENV_DATA_DIR) or None,
        port_text=env.get(ENV_PORT) or None,
        web_dist=env.get(ENV_WEB_DIST) or None,
        ts_name=env.get(ENV_TS_NAME),
        live_env={} if live is None else {LIVE_ENV: live},
        live_config_paths=tuple(LIVE_CONFIG_PATHS if config_paths is None else config_paths),
    )


def _config_says_live(paths: Iterable[Path]) -> bool:
    for path in paths:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("live_transport") is True:
            return True
    return False


def live_enabled(
    env: Mapping[str, str] | None = None, config_paths: Iterable[Path] | None = None
) -> bool:
    """환경 변수 **과** 설정 파일이 둘 다 '켬'일 때만 True."""
    env = os.environ if env is None else env
    if env.get(LIVE_ENV) != "1":
        return False
    return _config_says_live(LIVE_CONFIG_PATHS if config_paths is None else config_paths)
