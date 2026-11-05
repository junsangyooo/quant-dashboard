"""계정 · 키 파일 감싸기 · 비밀 값(owner · owner_keyfile · secrets). 금고(`vault.py` · 보안 층)가 써요.

여기는 감싼 바이트를 그대로 읽고 써요(잠그기 · 풀기는 금고). 계정은 한 줄(`id = 1`)이에요.
"""

from __future__ import annotations

import sqlite3

from .db import DB

# ── 계정 ────────────────────────────────────────────────────────────────────


def owner(db: DB) -> sqlite3.Row | None:
    return db.one("SELECT * FROM owner WHERE id=1")


def has_owner(db: DB) -> bool:
    return db.one("SELECT 1 FROM owner WHERE id=1") is not None


def owner_lock(db: DB) -> sqlite3.Row | None:
    """잠금이 풀리는 때(`locked_until`)."""
    return db.one("SELECT locked_until FROM owner WHERE id=1")


def owner_dates(db: DB) -> sqlite3.Row | None:
    """사용 조건 동의 · 계정 만든 때."""
    return db.one("SELECT terms_at, created_at FROM owner WHERE id=1")


def add_owner(db: DB, scrypt_n: int, pw_salt: bytes, pw_wrap: bytes, rc_salt: bytes, rc_wrap: bytes, terms_at: str,
              created_at: str) -> None:
    db.run("INSERT INTO owner(id,scrypt_n,pw_salt,pw_wrap,rc_salt,rc_wrap,fails,locked_until,"
           "adult,terms_at,created_at) VALUES(1,?,?,?,?,?,0,0,1,?,?)",
           (scrypt_n, pw_salt, pw_wrap, rc_salt, rc_wrap, terms_at, created_at))


def lock_owner(db: DB, until: float) -> None:
    """틀린 횟수를 0으로 하고 그때까지 잠가요."""
    db.run("UPDATE owner SET fails=0, locked_until=? WHERE id=1", (until,))


def set_fails(db: DB, fails: int) -> None:
    db.run("UPDATE owner SET fails=? WHERE id=1", (fails,))


def clear_fails(db: DB) -> None:
    db.run("UPDATE owner SET fails=0, locked_until=0 WHERE id=1")


def rewrap_both(db: DB, pw_salt: bytes, pw_wrap: bytes, rc_salt: bytes, rc_wrap: bytes) -> None:
    """복구 코드로 새 비밀번호: 두 감싸기를 바꾸고 틀린 횟수 · 잠금을 풀어요."""
    db.run("UPDATE owner SET pw_salt=?, pw_wrap=?, rc_salt=?, rc_wrap=?, fails=0, locked_until=0 WHERE id=1",
           (pw_salt, pw_wrap, rc_salt, rc_wrap))


def rewrap_password(db: DB, pw_salt: bytes, pw_wrap: bytes) -> None:
    db.run("UPDATE owner SET pw_salt=?, pw_wrap=?, fails=0, locked_until=0 WHERE id=1", (pw_salt, pw_wrap))


# ── 키 파일 감싸기 ──────────────────────────────────────────────────────────


def keyfile_wrap(db: DB) -> sqlite3.Row | None:
    return db.one("SELECT wrap FROM owner_keyfile WHERE id=1")


def put_keyfile_wrap(db: DB, wrap: bytes, at: str) -> None:
    db.run("INSERT INTO owner_keyfile(id,wrap,at) VALUES(1,?,?) "
           "ON CONFLICT(id) DO UPDATE SET wrap=excluded.wrap, at=excluded.at", (wrap, at))


def delete_keyfile_wrap(db: DB) -> None:
    db.run("DELETE FROM owner_keyfile")


# ── 비밀 값 ─────────────────────────────────────────────────────────────────


def put_secret_blob(db: DB, name: str, blob: bytes, at: str) -> None:
    db.run("INSERT INTO secrets(name,blob,updated_at) VALUES(?,?,?) "
           "ON CONFLICT(name) DO UPDATE SET blob=excluded.blob, updated_at=excluded.updated_at", (name, blob, at))


def secret_blob(db: DB, name: str) -> sqlite3.Row | None:
    return db.one("SELECT blob FROM secrets WHERE name=?", (name,))


def has_secret_blob(db: DB, name: str) -> bool:
    return db.one("SELECT 1 FROM secrets WHERE name=?", (name,)) is not None


def delete_secret_blob(db: DB, name: str) -> None:
    db.run("DELETE FROM secrets WHERE name=?", (name,))
