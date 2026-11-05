"""금고의 기록 시각과 복구 코드(기준선 시계 · 씨앗 고정 자리 · 열린 질문 Q-N24).

금고 · 세션 · 비밀번호 다시 받기는 `app/security/vault.py`(보안 층 · TASKS P1-09)로 옮겼어요. 이 파일에는 **정의**만 남아요:
- `_now_iso`: 금고 · 세션 기록 시각(UTC ISO 초 단위 · 지금 시계를 직접 읽음).
- `new_recovery_code`(`secrets.choice`) · `format_recovery_code` · `normalize_recovery_code`: 복구 코드 만들기와 꼴.

까닭: 기준선 도구(`tests/baseline/clock.py`)가 `CLOCK_SITES`의 `("app.vault", "datetime")` · `SEED_SITE`의
`("app.vault", "secrets")`로 **이 모듈 이름**의 전역을 바꿔 끼워 시각 · 복구 코드를 고정해요. 옮기면 그 기록과 시험의 '닿는
자리'를 고쳐야 해서(단언 · 기준선 기록 변경) Q-N24의 답 전까지 여기 둬요. 보안 층(`security/vault.py`)이 이 함수들을 불러요.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

# Crockford base32: 0~9와 I L O U를 뺀 영문. 16자 = 80비트.
RC_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
RC_LEN = 16


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_recovery_code() -> str:
    return "".join(secrets.choice(RC_ALPHABET) for _ in range(RC_LEN))


def format_recovery_code(code: str) -> str:
    return "-".join(code[i : i + 4] for i in range(0, len(code), 4))


def normalize_recovery_code(text: str) -> str:
    out = []
    for ch in (text or "").upper():
        if ch in " -_\t\n":
            continue
        ch = {"O": "0", "I": "1", "L": "1"}.get(ch, ch)
        out.append(ch)
    return "".join(out)
