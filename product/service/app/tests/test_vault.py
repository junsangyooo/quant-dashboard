"""비밀번호 · 복구 코드 · 암호화 왕복 · 잠금."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag

from app.db import DB
from app.vault import (
    LOCK_S,
    Vault,
    VaultError,
    normalize_recovery_code,
    seal,
    unseal,
)

N = 2**12
PW = "first-password"


class Clock:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


def make(tmp_path: Path, clock: Clock | None = None) -> Vault:
    return Vault(DB(tmp_path / "app.db"), scrypt_n=N, clock=clock or Clock())


def test_seal_roundtrip_and_tamper() -> None:
    key = b"k" * 32
    blob = seal(key, b"hello", b"aad")
    assert unseal(key, blob, b"aad") == b"hello"
    with pytest.raises(InvalidTag):
        unseal(b"x" * 32, blob, b"aad")
    with pytest.raises(InvalidTag):
        unseal(key, blob, b"other")
    broken = blob[:-1] + bytes([blob[-1] ^ 1])
    with pytest.raises(InvalidTag):
        unseal(key, broken, b"aad")


def test_setup_rules(tmp_path: Path) -> None:
    v = make(tmp_path)
    with pytest.raises(VaultError, match="8자"):
        v.setup("short", "short", adult=True, terms=True)
    with pytest.raises(VaultError, match="달라요"):
        v.setup(PW, PW + "x", adult=True, terms=True)
    with pytest.raises(VaultError, match="19세"):
        v.setup(PW, PW, adult=False, terms=True)
    with pytest.raises(VaultError, match="동의"):
        v.setup(PW, PW, adult=True, terms=False)
    token, code = v.setup(PW, PW, adult=True, terms=True)
    assert re.fullmatch(r"[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{4}){3}", code)
    assert len(normalize_recovery_code(code)) == 16
    assert v.session_ok(token)
    with pytest.raises(VaultError, match="이미"):
        v.setup(PW, PW, adult=True, terms=True)


def test_secret_roundtrip_survives_restart(tmp_path: Path) -> None:
    v = make(tmp_path)
    v.setup(PW, PW, adult=True, terms=True)
    v.put_secret("toss.client_secret", "S3CRET-VALUE-1234")
    assert v.get_secret("toss.client_secret") == "S3CRET-VALUE-1234"
    assert v.tail("toss.client_secret") == "1234"
    raw = (tmp_path / "app.db").read_bytes()
    assert b"S3CRET-VALUE" not in raw

    # 앱을 다시 켠다: 같은 DB, 새 금고 = 잠김
    v2 = make(tmp_path)
    assert not v2.unlocked
    assert v2.tail("toss.client_secret") is None
    with pytest.raises(VaultError) as e:
        v2.get_secret("toss.client_secret")
    assert e.value.status == 423 and "잠금" in e.value.message
    v2.login(PW)
    assert v2.get_secret("toss.client_secret") == "S3CRET-VALUE-1234"


def test_logout_and_expiry_lock_the_key(tmp_path: Path) -> None:
    clock = Clock()
    v = make(tmp_path, clock)
    token, _ = v.setup(PW, PW, adult=True, terms=True)
    v.put_secret("a", "b")
    v.logout(token)
    assert not v.unlocked
    t2 = v.login(PW)
    clock.t += 12 * 3600 + 1
    assert not v.session_ok(t2)
    assert not v.unlocked


def test_five_fails_lock_five_minutes(tmp_path: Path) -> None:
    clock = Clock()
    v = make(tmp_path, clock)
    v.setup(PW, PW, adult=True, terms=True)
    for i in range(4):
        with pytest.raises(VaultError) as e:
            v.login("wrong-password")
        assert e.value.status == 401
        assert e.value.extra["tries_left"] == 4 - i
    with pytest.raises(VaultError) as e:
        v.login("wrong-password")
    assert e.value.status == 429
    # 잠긴 동안은 맞는 비밀번호도 안 된다
    with pytest.raises(VaultError) as e:
        v.login(PW)
    assert e.value.status == 429
    assert 0 < v.locked_for() <= LOCK_S
    clock.t += LOCK_S + 1
    assert v.locked_for() == 0
    assert v.session_ok(v.login(PW))


def test_recovery_code_resets_password(tmp_path: Path) -> None:
    v = make(tmp_path)
    old_token, code = v.setup(PW, PW, adult=True, terms=True)
    v.put_secret("dart.api_key", "dart-key-5678")
    with pytest.raises(VaultError) as e:
        v.recover("AAAA-BBBB-CCCC-DDDD", "new-password-1", "new-password-1")
    assert e.value.status == 401 and "복구 코드" in e.value.message
    token, new_code = v.recover(code.lower(), "new-password-1", "new-password-1")
    assert new_code != code
    assert v.session_ok(token)
    assert not v.session_ok(old_token)  # 예전 세션은 닫힌다
    assert v.get_secret("dart.api_key") == "dart-key-5678"  # 데이터 키는 그대로
    v.lock_now()
    with pytest.raises(VaultError):
        v.login(PW)
    v.login("new-password-1")
    v.lock_now()
    with pytest.raises(VaultError):  # 쓴 복구 코드는 다시 못 쓴다
        v.recover(code, "another-pass-2", "another-pass-2")
    v.recover(new_code, "another-pass-2", "another-pass-2")


def test_recovery_failures_count_toward_lock(tmp_path: Path) -> None:
    v = make(tmp_path)
    v.setup(PW, PW, adult=True, terms=True)
    for _ in range(4):
        with pytest.raises(VaultError):
            v.recover("0000-0000-0000-0000", "new-password-1", "new-password-1")
    with pytest.raises(VaultError) as e:
        v.login("nope-nope-nope")
    assert e.value.status == 429
