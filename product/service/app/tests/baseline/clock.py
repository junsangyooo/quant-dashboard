"""P1-01 기준선의 고정 시각 · 씨앗 · 패치 자리(한 곳 · P1-01b · P1-01c · 뒤 일감이 같이 써요).

- 서버 `now`(`create_app`의 `now` 기본값 = `market.now_kst` → `Live.now()` · `Scheduler.now` · `PaperV2.now` ·
  `Telegram.now`)와 직접 시계를 읽는 5곳(`api_v2.py:237` · `connect.py:79` · `vault.py:91` · `main.py:1267` ·
  `backtest_v2.py:120` · 줄 번호는 `8b67df6` 기준)을 **같은 고정 시각** `FIXED_NOW`로 고정해요.
- 복구 코드(`vault.py:109` `secrets.choice`)는 씨앗 `RECOVERY_SEED`로 고정해요(세션 · 확인 토큰은 가릴 필드라 그대로).
- 앱 코드는 바꾸지 않고 모듈 전역 이름을 monkeypatch로 바꿔 끼워요(`freeze(monkeypatch)`). 시험에서는
  `tests/baseline/plugin.py`의 autouse 픽스처가, 기록 스크립트에서는 `freeze_plain()`이 불러요.
- Playwright `page.clock`(P1-01c)은 `FIXED_NOW_EPOCH_MS`를 써요.
"""

from __future__ import annotations

import random
import secrets as _secrets
import types
from datetime import datetime, timedelta, timezone
from typing import Any

KST = timezone(timedelta(hours=9))

# conftest.FIXED_NOW(월요일 17:00 KST · 16:30 자동 확인 뒤 · 20:10 전)와 같은 값
FIXED_NOW = datetime(2025, 6, 2, 17, 0, tzinfo=KST)
FIXED_NOW_UTC_ISO = "2025-06-02T08:00:00+00:00"  # `datetime.now(timezone.utc).isoformat(timespec="seconds")` 꼴
FIXED_NOW_EPOCH_MS = 1748851200000  # Playwright `page.clock.setFixedTime` 값
RECOVERY_SEED = 20250602
# `random.Random(RECOVERY_SEED).choice(RC_ALPHABET)` 16번 · 설치 직후 첫 복구 코드(`vault.new_recovery_code`)
RECOVERY_CODE = "2PAJB9JHYDYBA7DH"

# (모듈, 이름, 어느 줄(8b67df6)이 읽는가)
CLOCK_SITES: tuple[tuple[str, str, str], ...] = (
    ("app.api_v2", "datetime", "api_v2.py:237 백테스트 기본 기간(default_range)"),
    ("app.connect", "datetime", "connect.py:79 _now · 연결 확인 시각"),
    ("app.vault", "datetime", "vault.py:91 _now_iso · 금고 · 세션 기록 시각"),
    ("app.main", "datetime", "main.py:1267 _now · 전략 저장 시각(api_v2 now 인자)"),
    ("app.backtest_v2", "datetime", "backtest_v2.py:120 ran_at"),
    ("app.market", "datetime", "market.py:79 now_kst · create_app now 기본값 → Live · Scheduler · PaperV2 · Telegram"),
)
SEED_SITE = ("app.vault", "secrets", "vault.py:109 new_recovery_code의 secrets.choice")


class FrozenDatetime(datetime):
    """`datetime.now()`만 고정 시각을 돌려주는 datetime(나머지 생성자 · 셈은 그대로)."""

    @classmethod
    def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
        if tz is None:
            return FIXED_NOW.replace(tzinfo=None)
        return FIXED_NOW.astimezone(tz)

    @classmethod
    def utcnow(cls) -> datetime:  # type: ignore[override]
        return FIXED_NOW.astimezone(timezone.utc).replace(tzinfo=None)


def seeded_secrets(seed: int = RECOVERY_SEED) -> types.SimpleNamespace:
    """`secrets` 모듈 대신 끼우는 이름 묶음 · `choice`만 씨앗 난수 · 나머지는 진짜 `secrets`."""
    rng = random.Random(seed)
    return types.SimpleNamespace(
        choice=rng.choice,
        token_urlsafe=_secrets.token_urlsafe,
        token_bytes=_secrets.token_bytes,
        token_hex=_secrets.token_hex,
        compare_digest=_secrets.compare_digest,
    )


def freeze(monkeypatch: Any) -> None:
    """pytest monkeypatch로 시계 6자리 + 복구 코드 씨앗을 끼워요(시험이 끝나면 되돌아가요)."""
    import importlib

    for module, name, _ in CLOCK_SITES:
        monkeypatch.setattr(importlib.import_module(module), name, FrozenDatetime)
    module, name, _ = SEED_SITE
    monkeypatch.setattr(importlib.import_module(module), name, seeded_secrets())


def freeze_plain() -> None:
    """monkeypatch 없이(기록 스크립트) 같은 자리에 끼워요. 되돌리지 않아요(프로세스가 끝날 때까지)."""
    import importlib

    for module, name, _ in CLOCK_SITES:
        setattr(importlib.import_module(module), name, FrozenDatetime)
    module, name, _ = SEED_SITE
    setattr(importlib.import_module(module), name, seeded_secrets())


def as_record() -> dict[str, Any]:
    """기준선 본체에 남기는 값(두 번 같음)."""
    return {
        "fixed_now_kst": FIXED_NOW.isoformat(),
        "fixed_now_utc_iso": FIXED_NOW_UTC_ISO,
        "fixed_now_epoch_ms": FIXED_NOW_EPOCH_MS,
        "recovery_seed": RECOVERY_SEED,
        "recovery_code": RECOVERY_CODE,
        "clock_sites": [{"module": m, "name": n, "where": w} for m, n, w in CLOCK_SITES],
        "seed_site": {"module": SEED_SITE[0], "name": SEED_SITE[1], "where": SEED_SITE[2]},
    }
