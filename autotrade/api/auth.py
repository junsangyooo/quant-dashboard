"""Login, lockout, logout and PIN changes (CONTRACT.md 쓰기, 세션과 보안).

The PIN is six digits (10^6 values), so the lockout is the guard. Every wrong PIN counts against:

- the address it came from — the IPv4 address, or the IPv6 /64 (one home or phone network owns a
  whole /64, so counting single IPv6 addresses handed any attacker unlimited fresh ones): 5 in a
  row lock that address for 30 minutes (scope 'ip');
- everyone, per hour: 20 within an hour lock new logins until that hour has passed (scope
  'global'; it slows an attacker who rotates addresses);
- everyone, per day: 10 within 24 hours raise 'PIN 실패 급증' — a red to-do on the header and the
  작동 screen, kept until the owner acts (the 'pin-failures' notification event once web push
  exists, phase 3); 30 within 24 hours close new logins until the owner runs
  `python -m autotrade.jobs unlock` on the server (scope 'hold'). `set-pin` clears all of it too.

Why a hold after 30 a day rather than one more timed lock: a timed cap is a rate, not a ceiling.
The hourly cap alone let anyone guess about 480 times a day forever (~1.4% a month against a
random PIN) while keeping the owner out, and pacing just under any hourly cap does the same. The
hold bounds an attacker to 30 guesses per unlock (0.003%). The owner's own mistakes cannot reach it
by accident: his address locks after 5 wrong PINs for 30 minutes, so he would have to lock himself
out six times in a day; if he forgot the PIN, set-pin (which he needs then anyway) reopens login.
The price: whoever keeps guessing can close new logins (it takes them at least an hour). The owner
sees the red to-do on the devices already logged in, which keep working, and unlocks.

Open sessions are never affected by any lock. A PIN change (POST /api/account/pin) needs a session:
the address lock applies to it, the hourly lock and the hold do not — the owner must be able to
change his PIN exactly while someone is guessing it. A wrong current PIN counts like a wrong login
(address and daily counts), and 5 in a row on one session close that session, so a stolen session
cookie cannot be used to guess the PIN from many addresses.
"""

from __future__ import annotations

import ipaddress
import logging
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
from autotrade.db.auth_repo import ALERT_KEY, HOLD_KEY, LockoutFlag
from autotrade.db.connection import transaction
from autotrade.timeutil import KST

log = logging.getLogger("autotrade.api")

SESSION_KEY_PREFIX = "session:"


@dataclass(frozen=True)
class Issued:
    token: str
    session_id: str
    expires_at: datetime


@dataclass(frozen=True)
class Unlocked:
    """What `unlock` (or `set-pin`) cleared."""

    failures: int  # wrong-PIN rows
    locks: int  # lock rows: addresses, sessions and the two flags
    held: bool  # new logins had been closed (scope 'hold')
    alerted: bool  # 'PIN 실패 급증' had been raised


@dataclass(frozen=True)
class PinReset:
    revoked: int  # sessions closed
    unlocked: Unlocked


@dataclass(frozen=True)
class PinAlert:
    """'PIN 실패 급증' for the 작동 screen and the header."""

    since: datetime  # when it was raised
    count: int  # wrong PINs counted for it
    last_at: datetime | None  # the latest wrong PIN on record (rows older than 24 hours are
    # pruned when the next one arrives, so this is None only once nothing is left)
    closed: bool  # new logins are closed until unlock


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


def address_key(ip: str, ipv6_prefix: int = 64) -> str:
    """The lockout key of a caller: the IPv4 address, or the IPv6 network of `ipv6_prefix` bits
    (an IPv4-mapped IPv6 address counts as its IPv4 address). Not an address: the text itself."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip[:64]
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped is not None:
            return str(addr.ipv4_mapped)
        host_bits = 128 - ipv6_prefix
        network = ipaddress.IPv6Network(((int(addr) >> host_bits) << host_bits, ipv6_prefix))
        return str(network)
    return str(addr)


def session_key(session_id: str) -> str:
    return SESSION_KEY_PREFIX + session_id[:16]


def _locked(until: datetime, scope: str) -> ApiError:
    return ApiError(
        403,
        "locked",
        extra={"until": until.astimezone(KST).isoformat(timespec="seconds"), "scope": scope},
    )


def _held(hold: LockoutFlag) -> ApiError:
    """New logins closed until unlock: no `until`, the moment it closed instead."""
    since = hold.raised_at.astimezone(KST).isoformat(timespec="seconds")
    return ApiError(403, "locked", extra={"scope": "hold", "since": since})


def _gate(
    conn: sqlite3.Connection, settings: ApiSettings, key: str, at: datetime, *, login: bool
) -> None:
    """Raise the lock that refuses this attempt, if any: the hold, then the address, then the
    hourly cap. A PIN change from a session (login=False) is held back by its address only."""
    if login:
        hold = auth_repo.get_flag(conn, HOLD_KEY)
        if hold is not None:
            raise _held(hold)
    lock = auth_repo.get_lock(conn, key)
    if lock.locked_until is not None and lock.locked_until > at:
        raise _locked(lock.locked_until, "ip")
    if login:
        recent = auth_repo.failures_since(conn, at - settings.global_window)
        if len(recent) >= settings.global_max_failures:
            oldest_that_counts = recent[len(recent) - settings.global_max_failures]
            raise _locked(oldest_that_counts + settings.global_window, "global")


def _raise_flags(conn: sqlite3.Connection, settings: ApiSettings, at: datetime) -> None:
    """'PIN 실패 급증' and the hold, from the wrong PINs of the last 24 hours (this one too)."""
    day = auth_repo.count_failures_since(conn, at - settings.daily_window)
    if auth_repo.get_flag(conn, ALERT_KEY) is not None:
        auth_repo.bump_flag(conn, ALERT_KEY)
    elif day >= settings.alert_failures:
        auth_repo.raise_flag(conn, ALERT_KEY, day, at)
        log.warning(
            "pin-failures alert: %d wrong PINs within %s; it stays on the health screen until"
            " `python -m autotrade.jobs unlock`",
            day,
            settings.daily_window,
        )
    if day >= settings.hold_failures and auth_repo.get_flag(conn, HOLD_KEY) is None:
        auth_repo.raise_flag(conn, HOLD_KEY, day, at)
        log.error(
            "pin-failures hold: %d wrong PINs within %s; new logins are closed until"
            " `python -m autotrade.jobs unlock` (open sessions keep working)",
            day,
            settings.daily_window,
        )


def _count_failure(conn: sqlite3.Connection, settings: ApiSettings, key: str, at: datetime) -> int:
    """Record a wrong PIN everywhere it counts. Returns the address's failures in a row (the lock
    is set, and the count starts again, at the fifth)."""
    auth_repo.add_failure(conn, key, at)
    auth_repo.prune_failures(conn, at - max(settings.daily_window, settings.global_window))
    _raise_flags(conn, settings, at)
    failures = auth_repo.get_lock(conn, key).failures + 1
    if failures >= settings.ip_max_failures:
        auth_repo.set_lock(conn, key, 0, at + settings.ip_lock, at)
    else:
        auth_repo.set_lock(conn, key, failures, None, at)
    return failures


def _login_refusal(
    conn: sqlite3.Connection, settings: ApiSettings, key: str, at: datetime, failures: int
) -> ApiError:
    """After a wrong PIN: the lock it caused or met, else the tries left at this address."""
    try:
        _gate(conn, settings, key, at, login=True)
    except ApiError as lock:
        return lock
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
    key = address_key(ip, settings.ipv6_prefix)
    refusal: ApiError | None = None
    issued: Issued | None = None
    with transaction(conn):
        _gate(conn, settings, key, at, login=True)
        stored = auth_repo.get_pin_hash(conn)
        if stored is None:
            raise ApiError(403, "no-pin")
        if not verify_pin(pin, stored, secret):
            failures = _count_failure(conn, settings, key, at)
            refusal = _login_refusal(conn, settings, key, at, failures)
        else:
            auth_repo.clear_lock(conn, key)
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
    """The caller has an open session (checked before this). See the module docstring for why
    only the address lock applies here."""
    key = address_key(ip, settings.ipv6_prefix)
    tries_key = session_key(keep_session_id)
    refusal: ApiError | None = None
    with transaction(conn):
        _gate(conn, settings, key, at, login=False)
        if not verify_pin(current, auth_repo.get_pin_hash(conn), secret):
            _count_failure(conn, settings, key, at)
            tries = auth_repo.get_lock(conn, tries_key).failures + 1
            if tries >= settings.session_max_failures:
                auth_repo.clear_lock(conn, tries_key)
                auth_repo.revoke_session(conn, keep_session_id, at, "pin-failures")
                refusal = ApiError(403, "session")
            else:
                auth_repo.set_lock(conn, tries_key, tries, None, at)
                try:
                    _gate(conn, settings, key, at, login=False)
                except ApiError as lock:
                    refusal = lock
                else:
                    refusal = ApiError(403, "current-pin")
        elif not is_valid_pin(new):
            raise ApiError(400, "invalid-pin")
        else:
            auth_repo.clear_lock(conn, key)
            auth_repo.clear_lock(conn, tries_key)
            auth_repo.set_pin_hash(conn, hash_pin(new, secret, settings.scrypt_n), at)
            auth_repo.revoke_all_but(conn, keep_session_id, at, "pin-changed")
    if refusal is not None:
        raise refusal  # after the commit, so the failure is counted


def _clear_lockouts(conn: sqlite3.Connection) -> Unlocked:
    held = auth_repo.get_flag(conn, HOLD_KEY) is not None
    alerted = auth_repo.get_flag(conn, ALERT_KEY) is not None
    failures, locks = auth_repo.clear_lockouts(conn)
    return Unlocked(failures=failures, locks=locks, held=held, alerted=alerted)


def unlock(conn: sqlite3.Connection) -> Unlocked:
    """`python -m autotrade.jobs unlock`: forget every wrong PIN and lock (CLI only). Reopens new
    logins after a hold and takes 'PIN 실패 급증' off the screens. Sessions are untouched."""
    with transaction(conn):
        cleared = _clear_lockouts(conn)
    log.info(
        "unlock: %d wrong PINs and %d locks cleared (hold %s, alert %s)",
        cleared.failures,
        cleared.locks,
        cleared.held,
        cleared.alerted,
    )
    return cleared


def set_pin(conn: sqlite3.Connection, secret: bytes, pin: str, n: int, at: datetime) -> PinReset:
    """First PIN or a reset (CLI only). Every open session is closed, and every wrong PIN and lock
    of the old PIN is forgotten (as `unlock` does)."""
    if not is_valid_pin(pin):
        raise ValueError("a PIN is six digits")
    with transaction(conn):
        auth_repo.set_pin_hash(conn, hash_pin(pin, secret, n), at)
        revoked = auth_repo.revoke_all_but(conn, None, at, "pin-reset")
        cleared = _clear_lockouts(conn)
    return PinReset(revoked=revoked, unlocked=cleared)


def pin_alert(conn: sqlite3.Connection) -> PinAlert | None:
    """'PIN 실패 급증' while raised (until unlock or set-pin)."""
    flags = [
        f for f in (auth_repo.get_flag(conn, ALERT_KEY), auth_repo.get_flag(conn, HOLD_KEY)) if f
    ]
    if not flags:
        return None
    return PinAlert(
        since=min(f.raised_at for f in flags),
        count=max(f.count for f in flags),
        last_at=auth_repo.last_failure_at(conn),
        closed=auth_repo.get_flag(conn, HOLD_KEY) is not None,
    )
