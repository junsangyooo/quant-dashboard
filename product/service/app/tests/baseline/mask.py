"""가릴 필드 목록(한 곳 · 까닭 한 줄씩).

API 모양 기록은 값을 빼고 키 · 타입만 남기지만, 아래 키는 타입도 `masked`로 적어요(시각 · 토큰 · 자동 번호처럼
실행마다 달라지거나 null ↔ 값이 오가는 것 · 비밀 값). 하루 흐름 · 엔진 기록처럼 값을 남기는 기록에서는 아래 키의 값을
`"<masked>"`로 바꿔요. 화면 기록(P1-01c)도 같은 목록을 써요.
"""

from __future__ import annotations

from typing import Any

MASKED: dict[str, str] = {
    # 시각(고정 시계로 같아야 하지만 패치 밖 경로 · 시험 자료의 'at' 값이 섞여요)
    "at": "시각",
    "ran_at": "백테스트 시각",
    "created_at": "만든 시각",
    "updated_at": "고친 시각",
    "started_at": "시작 시각",
    "ended_at": "끝낸 시각",
    "resolved_at": "해결 시각",
    "filled_at": "체결 시각",
    "triggered_at": "조건주문 발동 시각",
    "detected_at": "권리 변동 감지 시각",
    "applied_at": "권리 변동 적용 시각",
    "made_at": "모의 판단 시각",
    "checked_at": "연결 확인 시각",
    "last_check": "마지막 확인 시각",
    "last_login": "마지막 로그인 시각",
    "since": "기준 시각",
    "expires": "만료 시각",
    "expire": "조건주문 만료일",
    "timestamp": "토스 시세 시각",
    # 복구 코드 · 세션 · 쿠키 · 토큰 · 비밀 값
    "recovery_code": "복구 코드(씨앗으로 고정하지만 비밀 값)",
    "token": "확인 토큰 · 텔레그램 토큰",
    "session": "세션 id",
    "cookie": "쿠키",
    "csrf": "CSRF 값",
    "secret": "비밀 값",  # `key`는 가리지 않아요: 응답의 `key`는 모두 식별자(checks · steps · params · events)이고 DART 키는 `tail`로만 나와요
    "client_id": "토스 클라이언트 id",
    "client_secret": "토스 클라이언트 비밀",
    "account_no": "계좌번호",
    "account_tail": "계좌번호 끝자리",
    "tail": "비밀 값 끝자리",
    # 자동 번호 · 외부가 정하는 id
    "toss_order_id": "토스 주문 번호",
    "toss_cond_id": "토스 조건주문 번호",
    "request_id": "토스 요청 번호",
    "public_ip": "공인 IP",
    "ip": "공인 IP",
}

MASK_VALUE = "<masked>"


def mask_values(value: Any) -> Any:
    """값을 남기는 기록에서 가릴 키의 값을 바꿔요(깊이 제한 없음 · 새 객체)."""
    if isinstance(value, dict):
        return {k: (MASK_VALUE if k in MASKED and v is not None else mask_values(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_values(v) for v in value]
    return value


def as_record() -> list[dict[str, str]]:
    return [{"field": k, "why": v} for k, v in sorted(MASKED.items())]
