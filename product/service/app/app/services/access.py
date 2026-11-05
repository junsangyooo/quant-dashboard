"""설정 › 접속(V2-05 · V2-06 · V2-56 · TASKS P1-09): 설치 위치 고르기와 접속 보기.

설치 위치는 서버(클라우드 · 고정 IP) 또는 늘 켜 둔 PC예요. 처음 고르기는 로그인만, 바꾸기는 비밀번호를 다시 받아요(SPEC 7-4 ·
`confirm`은 API가 넘겨 주는 1회용 토큰 확인). Tailscale은 설치기가 serve를 설정하고 이름을 넘겨 줬으면 연결됨이에요(Q-N10).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..copy import texts as T
from ..security.vault import VaultError
from ..store.db import DB

PLACES = {"server": T.place_server, "pc": T.place_pc}
PLACE_META = "access.place"


def access_view(db: DB, *, ts_ok: list[str], port: int) -> dict[str, Any]:
    place = db.get_meta(PLACE_META)
    return {
        "place": place if place in PLACES else None,
        "place_name": PLACES.get(place or ""),
        # Tailscale: 설치기가 serve를 설정하고 이름을 넘겨 줬으면 연결됨(Q-N10)
        "tailscale": {"ok": bool(ts_ok), "name": ts_ok[0] if ts_ok else None,
                      "address": f"https://{ts_ok[0]}" if ts_ok else None},
        "local": f"127.0.0.1:{port}",
    }


def set_place(db: DB, place: str, *, confirm: Callable[[str], None]) -> None:
    if place not in PLACES:
        raise VaultError("서버 또는 PC를 골라 주세요")
    if db.get_meta(PLACE_META) and db.get_meta(PLACE_META) != place:
        confirm("install_place")  # 처음 고르기는 로그인만, 변경은 비밀번호(SPEC 7-4)
    db.set_meta(PLACE_META, place)


def place(db: DB) -> str | None:
    """고른 설치 위치(실전 운용 시작 확인 · 그대로의 저장 값)."""
    return db.get_meta(PLACE_META)
