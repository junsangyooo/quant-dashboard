"""Owner PIN, sessions, PIN lockout and notification preferences (tables of migration 2).

None of these commit; the caller owns the transaction.

Lockout rows (autotrade/api/auth.py decides what they mean):
- pin_failures: one row per wrong PIN, keyed by the caller's address (IPv4 address or IPv6 /64).
- pin_locks: keyed by text. An address key holds that address's consecutive failures and its
  lock; 'session:<id prefix>' holds one session's consecutive wrong current PINs (PIN change);
  the reserved keys ALERT_KEY and HOLD_KEY ('*…', never an address) are flags: the row exists
  from the moment 'PIN 실패 급증' was raised or new logins were closed, with `updated_at` = that
  moment and `failures` = the wrong PINs counted for it. Only `python -m autotrade.jobs unlock`
  and `set-pin` (clear_lockouts) remove them.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from autotrade.db.connection import dumps, loads
from autotrade.timeutil import from_iso, to_iso


@dataclass(frozen=True)
class SessionRow:
    session_id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    ip: str | None
    user_agent: str | None
    device_kind: str
    device_name: str

    def is_open(self, at: datetime) -> bool:
        return self.revoked_at is None and at < self.expires_at

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> SessionRow:
        revoked = row["revoked_at"]
        return cls(
            session_id=str(row["session_id"]),
            created_at=from_iso(str(row["created_at"])),
            last_seen_at=from_iso(str(row["last_seen_at"])),
            expires_at=from_iso(str(row["expires_at"])),
            revoked_at=None if revoked is None else from_iso(str(revoked)),
            ip=None if row["ip"] is None else str(row["ip"]),
            user_agent=None if row["user_agent"] is None else str(row["user_agent"]),
            device_kind=str(row["device_kind"]),
            device_name=str(row["device_name"]),
        )


ALERT_KEY = "*alert"
HOLD_KEY = "*hold"


@dataclass(frozen=True)
class PinLock:
    ip: str
    failures: int
    locked_until: datetime | None


@dataclass(frozen=True)
class LockoutFlag:
    raised_at: datetime
    count: int


@dataclass(frozen=True)
class NotificationPrefs:
    events: dict[str, bool]
    hide_amounts: bool
    saved_at: datetime


# ── PIN ──────────────────────────────────────────────────────────────────────────────────


def get_pin_hash(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT pin_hash FROM auth_pin WHERE id = 1").fetchone()
    return None if row is None else str(row["pin_hash"])


def set_pin_hash(conn: sqlite3.Connection, pin_hash: str, at: datetime) -> None:
    conn.execute(
        "INSERT INTO auth_pin (id, pin_hash, updated_at) VALUES (1, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET pin_hash = excluded.pin_hash,"
        " updated_at = excluded.updated_at",
        (pin_hash, to_iso(at)),
    )


# ── sessions ─────────────────────────────────────────────────────────────────────────────


def insert_session(
    conn: sqlite3.Connection,
    *,
    session_id: str,
    created_at: datetime,
    expires_at: datetime,
    ip: str | None,
    user_agent: str | None,
    device_kind: str,
    device_name: str,
) -> None:
    conn.execute(
        "INSERT INTO sessions (session_id, created_at, last_seen_at, expires_at, ip,"
        " user_agent, device_kind, device_name) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            session_id,
            to_iso(created_at),
            to_iso(created_at),
            to_iso(expires_at),
            ip,
            user_agent,
            device_kind,
            device_name,
        ),
    )


def get_session(conn: sqlite3.Connection, session_id: str) -> SessionRow | None:
    row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    return None if row is None else SessionRow.from_row(row)


def touch_session(conn: sqlite3.Connection, session_id: str, at: datetime) -> None:
    conn.execute(
        "UPDATE sessions SET last_seen_at = ? WHERE session_id = ?", (to_iso(at), session_id)
    )


def revoke_session(conn: sqlite3.Connection, session_id: str, at: datetime, why: str) -> None:
    conn.execute(
        "UPDATE sessions SET revoked_at = ?, revoked_why = ? WHERE session_id = ?"
        " AND revoked_at IS NULL",
        (to_iso(at), why, session_id),
    )


def revoke_all_but(
    conn: sqlite3.Connection, keep_session_id: str | None, at: datetime, why: str
) -> int:
    """Revoke every open session except `keep_session_id` (None revokes all)."""
    cur = conn.execute(
        "UPDATE sessions SET revoked_at = ?, revoked_why = ? WHERE revoked_at IS NULL"
        " AND session_id IS NOT ?",
        (to_iso(at), why, keep_session_id),
    )
    return int(cur.rowcount)


def open_sessions(conn: sqlite3.Connection, at: datetime) -> list[SessionRow]:
    rows = conn.execute(
        "SELECT * FROM sessions WHERE revoked_at IS NULL AND expires_at > ? ORDER BY created_at",
        (to_iso(at),),
    ).fetchall()
    return [SessionRow.from_row(r) for r in rows]


# ── lockout ──────────────────────────────────────────────────────────────────────────────


def get_lock(conn: sqlite3.Connection, ip: str) -> PinLock:
    row = conn.execute("SELECT * FROM pin_locks WHERE ip = ?", (ip,)).fetchone()
    if row is None:
        return PinLock(ip, 0, None)
    until = row["locked_until"]
    return PinLock(ip, int(row["failures"]), None if until is None else from_iso(str(until)))


def set_lock(
    conn: sqlite3.Connection, ip: str, failures: int, locked_until: datetime | None, at: datetime
) -> None:
    conn.execute(
        "INSERT INTO pin_locks (ip, failures, locked_until, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(ip) DO UPDATE SET failures = excluded.failures,"
        " locked_until = excluded.locked_until, updated_at = excluded.updated_at",
        (ip, failures, None if locked_until is None else to_iso(locked_until), to_iso(at)),
    )


def clear_lock(conn: sqlite3.Connection, ip: str) -> None:
    conn.execute("DELETE FROM pin_locks WHERE ip = ?", (ip,))


def add_failure(conn: sqlite3.Connection, ip: str, at: datetime) -> None:
    conn.execute("INSERT INTO pin_failures (ip, at) VALUES (?, ?)", (ip, to_iso(at)))


def failures_since(conn: sqlite3.Connection, since: datetime) -> list[datetime]:
    rows = conn.execute(
        "SELECT at FROM pin_failures WHERE at > ? ORDER BY at", (to_iso(since),)
    ).fetchall()
    return [from_iso(str(r["at"])) for r in rows]


def prune_failures(conn: sqlite3.Connection, before: datetime) -> None:
    conn.execute("DELETE FROM pin_failures WHERE at <= ?", (to_iso(before),))


def count_failures_since(conn: sqlite3.Connection, since: datetime) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM pin_failures WHERE at > ?", (to_iso(since),)
    ).fetchone()
    return int(row[0])


def last_failure_at(conn: sqlite3.Connection) -> datetime | None:
    row = conn.execute("SELECT MAX(at) FROM pin_failures").fetchone()
    return None if row is None or row[0] is None else from_iso(str(row[0]))


def get_flag(conn: sqlite3.Connection, key: str) -> LockoutFlag | None:
    row = conn.execute("SELECT failures, updated_at FROM pin_locks WHERE ip = ?", (key,)).fetchone()
    if row is None:
        return None
    return LockoutFlag(raised_at=from_iso(str(row["updated_at"])), count=int(row["failures"]))


def raise_flag(conn: sqlite3.Connection, key: str, count: int, at: datetime) -> None:
    """Set a flag once; a flag already raised keeps its moment."""
    conn.execute(
        "INSERT INTO pin_locks (ip, failures, locked_until, updated_at) VALUES (?, ?, NULL, ?)"
        " ON CONFLICT(ip) DO NOTHING",
        (key, count, to_iso(at)),
    )


def bump_flag(conn: sqlite3.Connection, key: str) -> None:
    """Count one more wrong PIN on a raised flag (its moment stays)."""
    conn.execute("UPDATE pin_locks SET failures = failures + 1 WHERE ip = ?", (key,))


def clear_lockouts(conn: sqlite3.Connection) -> tuple[int, int]:
    """Empty pin_failures and pin_locks (unlock, set-pin). Returns the rows removed of each."""
    failures = conn.execute("DELETE FROM pin_failures").rowcount
    locks = conn.execute("DELETE FROM pin_locks").rowcount
    return int(failures), int(locks)


# ── notification preferences ─────────────────────────────────────────────────────────────


def get_prefs(conn: sqlite3.Connection) -> NotificationPrefs | None:
    row = conn.execute("SELECT * FROM notification_prefs WHERE id = 1").fetchone()
    if row is None:
        return None
    events: Any = loads(str(row["events"])) or {}
    return NotificationPrefs(
        events={str(k): bool(v) for k, v in dict(events).items()},
        hide_amounts=bool(row["hide_amounts"]),
        saved_at=from_iso(str(row["saved_at"])),
    )


def save_prefs(
    conn: sqlite3.Connection, events: dict[str, bool], hide_amounts: bool, at: datetime
) -> None:
    conn.execute(
        "INSERT INTO notification_prefs (id, events, hide_amounts, saved_at) VALUES (1, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET events = excluded.events,"
        " hide_amounts = excluded.hide_amounts, saved_at = excluded.saved_at",
        (dumps(events), 1 if hide_amounts else 0, to_iso(at)),
    )
