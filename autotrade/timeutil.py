"""Time zones and timestamp formatting.

Records are stored as UTC ISO 8601 strings ('2026-10-06T23:30:00+00:00'); every datetime in the
engine is timezone-aware. Screens show KST, and US closes carry their ET session date.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")


def require_aware(dt: datetime) -> datetime:
    """Return dt unchanged, or raise if it has no time zone."""
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"naive datetime: {dt!r}")
    return dt


def to_iso(dt: datetime) -> str:
    """UTC ISO string with seconds, the storage format."""
    return require_aware(dt).astimezone(UTC).isoformat(timespec="seconds")


def from_iso(text: str) -> datetime:
    """Parse a stored ISO timestamp (must carry an offset). A trailing 'Z' is read as UTC: this
    code writes '+00:00', but Python 3.10's fromisoformat refuses 'Z' outright, and one stray
    writer would otherwise turn every read of that row into a crash."""
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return require_aware(datetime.fromisoformat(text))


def kst_date(dt: datetime) -> date:
    return require_aware(dt).astimezone(KST).date()


def et_date(dt: datetime) -> date:
    return require_aware(dt).astimezone(ET).date()


def at_kst(d: date, t: time) -> datetime:
    """The aware datetime for wall-clock time t on date d in Seoul."""
    return datetime.combine(d, t, tzinfo=KST)


def at_zone(d: date, t: time, zone: ZoneInfo) -> datetime:
    return datetime.combine(d, t, tzinfo=zone)


def parse_cli_time(text: str) -> datetime:
    """ISO time from the command line; a value without an offset is read as KST."""
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=KST)
    return dt


def ceil_minute(dt: datetime) -> datetime:
    """Round up to the next whole minute (unchanged when already whole)."""
    if dt.second == 0 and dt.microsecond == 0:
        return dt
    return (dt + timedelta(minutes=1)).replace(second=0, microsecond=0)


def is_weekday(d: date) -> bool:
    return d.weekday() < 5
