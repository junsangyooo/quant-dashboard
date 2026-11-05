"""바깥 문(ARCHITECTURE 2절 보안 층 · QUALITY S4 · TASKS P1-09): 호스트 · 출처 허용 목록과 CSRF 값.

- 서버는 127.0.0.1에만 묶어요. 받는 호스트는 `127.0.0.1:포트` · `localhost:포트` · 시험 클라이언트(`testserver`)와
  Tailscale serve가 https로 받아 넘기는 등록한 `*.ts.net` 이름뿐이에요(T-51 · SPEC 10).
- CSRF 값은 세션 토큰의 HMAC(프로세스마다 새 키 · 세션도 메모리에만)이라 세션과 짝이 맞아야 해요(두 번 보내기).
- 요청을 막는 미들웨어(fastapi)는 API 층 `api/guard.py`예요. 여기는 값만 셈해요.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets

TS_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.ts\.net$")


def ts_names_from(text: str | None) -> list[str]:
    """등록한 Tailscale 이름(설치기가 QUANT_TS_NAME으로 넘겨요 · 쉼표로 여럿). 꼴이 맞지 않으면 버려요."""
    out = []
    for part in (text or "").split(","):
        name = part.strip().lower().rstrip(".")
        if name and TS_NAME.match(name):
            out.append(name)
    return out


def allowed_hosts_and_origins(port: int, ts_ok: list[str]) -> tuple[set[str], set[str]]:
    """받는 Host 머리글 · Origin 머리글 목록(등록한 ts.net 이름은 https · 443으로만)."""
    allowed_hosts = {
        f"127.0.0.1:{port}",
        f"localhost:{port}",
        "testserver",
    }
    allowed_origins = {f"http://{h}" for h in allowed_hosts}
    for name in ts_ok:
        allowed_hosts |= {name, f"{name}:443"}
        allowed_origins.add(f"https://{name}")
    return allowed_hosts, allowed_origins


class Csrf:
    """세션 토큰 → CSRF 값(HMAC-SHA256 · 키는 프로세스마다 새로)."""

    def __init__(self) -> None:
        self._key = secrets.token_bytes(32)

    def value_for(self, session: str) -> str:
        return hmac.new(self._key, session.encode(), hashlib.sha256).hexdigest()

    def matches(self, sent: str, session: str) -> bool:
        return hmac.compare_digest(sent, self.value_for(session))
