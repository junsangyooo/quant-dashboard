"""Login, lockout, logout and PIN changes (CONTRACT.md 쓰기, 세션과 보안).

Lockout: 5 consecutive wrong PINs from one address lock that address for 30 minutes; and
20 wrong PINs within an hour from anywhere lock new logins until the hour has passed (the
global cap stops an attacker who rotates addresses). Open sessions are never affected.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from autotrade.api.errors import ApiError
from autotrade.api.security import (
    hash_pin,
    is_valid_pin,
    make_token,
    new_session_id,
    verify_pin,
)
from autotrade.api.settings import ApiSettings
from autotrade.db import auth_repo
from autotrade.db.connection import transaction
from autotrade.timeutil import KST


@dataclass(frozen=True)
class Issued:
    token: str
    session_id: str
    expires_at: datetime


def device_from_user_agent(user_agent: str | None) -> tuple[str, str]:
    """(kind, name) for SCR-ACCOUNT '이 기기'. An iPhone home-screen app has no 'Safari/' token."""
    ua = (user_agent or "").lower()
    if "iphone" in ua:
        kind, system = ("iphone-safari" if "safari/" in ua else "iphone-app"), "iPhone"
    elif "ipad" in ua:
        kind, system = "other", "iPad"
    elif "macintosh" in ua or "mac os x" in ua:
        kind, system = "mac", "Mac"
    elif "android" in ua:
        kind, system = "other", "Android"
    elif "windows" in ua:
        kind, system = "other", "Windows"
    else:
        kind, system = "other", ""
    if "edg/" in ua:
        browser = "Edge"
    elif "firefox/" in ua or "fxios/" in ua:
        browser = "Firefox"
    elif "chrome/" in ua or "crios/" in ua:
        browser = "Chrome"
    elif "safari/" in ua:
        browser = "Safari"
    else:
        browser = ""
    name = " · ".join(p for p in (system, browser) if p)
    return kind, name


def _locked(until: datetime, scope: str) -> ApiError:
    return ApiError(
        403,
        "locked",
        extra={"until": until.astimezone(KST).isoformat(timespec="seconds"), "scope": scope},
    )


def _check_locks(conn: sqlite3.Connection, settings: ApiSettings, ip: str, at: datetime) -> None:
    lock = auth_repo.get_lock(conn, ip)
    if lock.locked_until is not None and lock.locked_until > at:
        raise _locked(lock.locked_until, "ip")
    recent = auth_repo.failures_since(conn, at - settings.global_window)
    if len(recent) >= settings.global_max_failures:
        oldest_that_counts = recent[len(recent) - settings.global_max_failures]
        raise _locked(oldest_that_counts + settings.global_window, "global")


def _register_failure(
    conn: sqlite3.Connection, settings: ApiSettings, ip: str, at: datetime
) -> ApiError | None:
    """Record a wrong PIN. Returns the lock it caused, if any."""
    auth_repo.add_failure(conn, ip, at)
    auth_repo.prune_failures(conn, at - settings.global_window * 24)
    lock = auth_repo.get_lock(conn, ip)
    failures = lock.failures + 1
    if failures >= settings.ip_max_failures:
        until = at + settings.ip_lock
        auth_repo.set_lock(conn, ip, 0, until, at)
        return _locked(until, "ip")
    auth_repo.set_lock(conn, ip, failures, None, at)
    try:
        _check_locks(conn, settings, ip, at)
    except ApiError as global_lock:
        return global_lock
    return ApiError(403, "pin", extra={"remaining": settings.ip_max_failures - failures})


def login(
    conn: sqlite3.Connection,
    settings: ApiSettings,
    secret: bytes,
    pin: str,
    ip: str,
    user_agent: str | None,
    at: datetime,
) -> Issued:
    refusal: ApiError | None = None
    issued: Issued | None = None
    with transaction(conn):
        _check_locks(conn, settings, ip, at)
        stored = auth_repo.get_pin_hash(conn)
        if stored is None:
            raise ApiError(403, "no-pin")
        if not verify_pin(pin, stored, secret):
            refusal = _register_failure(conn, settings, ip, at)
        else:
            auth_repo.clear_lock(conn, ip)
            session_id = new_session_id()
            expires = at + settings.session_ttl
            kind, name = device_from_user_agent(user_agent)
            auth_repo.insert_session(
                conn,
                session_id=session_id,
                created_at=at,
                expires_at=expires,
                ip=ip,
                user_agent=(user_agent or "")[:300],
                device_kind=kind,
                device_name=name,
            )
            issued = Issued(
                make_token(session_id, int(expires.timestamp()), secret), session_id, expires
            )
    if refusal is not None:
        raise refusal  # raised after the commit, so the failure is counted
    if issued is None:  # pragma: no cover — one of the two branches always ran
        raise ApiError(500, "internal")
    return issued


def logout(conn: sqlite3.Connection, session_id: str, at: datetime) -> None:
    with transaction(conn):
        auth_repo.revoke_session(conn, session_id, at, "logout")


def logout_others(conn: sqlite3.Connection, keep_session_id: str, at: datetime) -> int:
    with transaction(conn):
        return auth_repo.revoke_all_but(conn, keep_session_id, at, "logout-others")


def change_pin(
    conn: sqlite3.Connection,
    settings: ApiSettings,
    secret: bytes,
    current: str,
    new: str,
    keep_session_id: str,
    ip: str,
    at: datetime,
) -> None:
    refusal: ApiError | None = None
    with transaction(conn):
        _check_locks(conn, settings, ip, at)
        if not verify_pin(current, auth_repo.get_pin_hash(conn), secret):
            lock = _register_failure(conn, settings, ip, at)
            refusal = (
                lock if lock is not None and lock.code == "locked" else ApiError(403, "current-pin")
            )
        elif not is_valid_pin(new):
            raise ApiError(400, "invalid-pin")
        else:
            auth_repo.clear_lock(conn, ip)
            auth_repo.set_pin_hash(conn, hash_pin(new, secret, settings.scrypt_n), at)
            auth_repo.revoke_all_but(conn, keep_session_id, at, "pin-changed")
    if refusal is not None:
        raise refusal


def set_pin(conn: sqlite3.Connection, secret: bytes, pin: str, n: int, at: datetime) -> int:
    """First PIN or a reset (CLI only). Every open session is closed. Returns how many."""
    if not is_valid_pin(pin):
        raise ValueError("a PIN is six digits")
    with transaction(conn):
        auth_repo.set_pin_hash(conn, hash_pin(pin, secret, n), at)
        return auth_repo.revoke_all_but(conn, None, at, "pin-reset")
