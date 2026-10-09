"""PIN hashing, the server secret and signed session tokens.

Adapted from src/core/security.py (old quant app; copied, not imported — decision D14):
- the secret file idea (created once, 0600, outside git) is the same; the file is now
  data/autotrade.secret;
- the PIN hash is NOT the old one. The old hash was one SHA-256 over (secret, account, pin),
  which a leaked database + secret turns into a million cheap guesses. Here the PIN is peppered
  with the secret (HMAC-SHA256) and stretched with scrypt (N=2^15, r=8, p=1, random 16-byte
  salt); parameters are stored with the hash so they can be raised later;
- tokens no longer carry an account id: a token names a row in the sessions table, so a session
  can be revoked (logout, logout-others, PIN change). Format '<session_id>.<expires>.<hmac>'.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from pathlib import Path

PIN_LENGTH = 6
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


def is_valid_pin(pin: object) -> bool:
    return isinstance(pin, str) and len(pin) == PIN_LENGTH and pin.isascii() and pin.isdigit()


def load_or_create_secret(path: Path) -> bytes:
    """32 random bytes kept in a 0600 file next to the database."""
    if path.exists():
        data = path.read_bytes()
        if len(data) >= 32:
            return data
    path.parent.mkdir(parents=True, exist_ok=True)
    data = secrets.token_bytes(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, data)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
    return data


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _stretch(pin: str, pepper: bytes, salt: bytes, n: int, r: int, p: int) -> bytes:
    peppered = hmac.new(pepper, pin.encode(), hashlib.sha256).digest()
    return hashlib.scrypt(
        peppered, salt=salt, n=n, r=r, p=p, maxmem=256 * n * r + 1024 * 1024, dklen=SCRYPT_DKLEN
    )


def hash_pin(pin: str, pepper: bytes, n: int = 2**15) -> str:
    if not is_valid_pin(pin):
        raise ValueError("a PIN is six digits")
    salt = secrets.token_bytes(16)
    key = _stretch(pin, pepper, salt, n, SCRYPT_R, SCRYPT_P)
    return f"scrypt${n}${SCRYPT_R}${SCRYPT_P}${_b64(salt)}${_b64(key)}"


def verify_pin(pin: str, stored: str | None, pepper: bytes) -> bool:
    if not stored or not is_valid_pin(pin):
        return False
    try:
        scheme, n, r, p, salt, key = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = _unb64(key)
        actual = _stretch(pin, pepper, _unb64(salt), int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def _sign(payload: str, secret: bytes) -> str:
    return hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()


def make_token(session_id: str, expires_unix: int, secret: bytes) -> str:
    payload = f"{session_id}.{expires_unix}"
    return f"{payload}.{_sign(payload, secret)}"


def read_token(token: str | None, secret: bytes, now_unix: float | None = None) -> str | None:
    """The session id inside a valid, unexpired token; None otherwise."""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    session_id, expires, sig = parts
    if not hmac.compare_digest(sig, _sign(f"{session_id}.{expires}", secret)):
        return None
    try:
        if int(expires) <= (time.time() if now_unix is None else now_unix):
            return None
    except ValueError:
        return None
    return session_id
