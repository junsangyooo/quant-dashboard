"""GET /api/account (SCR-ACCOUNT) and the notification preferences."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from autotrade.api.views import fmt
from autotrade.db.auth_repo import NotificationPrefs, SessionRow

# CONTRACT.md NotifyEvent. Six are on from the start ('check-failed' cannot be turned off),
# three start off (D-notify-webpush). The AI events come with the AI rule (phase 2).
NOTIFY_DEFAULTS: dict[str, bool] = {
    "check-failed": True,
    "stale": True,
    "weekly-ok": True,
    "live-fill": True,
    "pin-failures": True,
    "toss-expiring": True,
    "check-missed": False,
    "rebalance-notice": False,
    "cash-moves": False,
}
LOCKED_EVENTS = frozenset({"check-failed"})


def effective_events(prefs: NotificationPrefs | None) -> dict[str, bool]:
    events = dict(NOTIFY_DEFAULTS)
    if prefs is not None:
        events.update({k: v for k, v in prefs.events.items() if k in events})
    for k in LOCKED_EVENTS:
        events[k] = True
    return events


def account(session: SessionRow, prefs: NotificationPrefs | None) -> dict[str, Any]:
    events = effective_events(prefs)
    saved_at: datetime | None = None if prefs is None else prefs.saved_at
    return {
        "thisDevice": {
            "name": session.device_name,
            "kind": session.device_kind,
            "enteredAt": fmt.iso(session.created_at),
        },
        "notifications": {
            # Web push is not built yet (phase 3): no device can subscribe, and the screen says
            # '알림은 준비 중' from `available` (the VAPID key and unsubscribing come with it).
            "available": False,
            "thisDevice": {"supported": False, "reason": "unsupported", "subscribed": False},
            "events": [
                {"id": k, "on": v, **({"locked": True} if k in LOCKED_EVENTS else {})}
                for k, v in events.items()
            ],
            "hideAmounts": False if prefs is None else prefs.hide_amounts,
            "savedAt": None if saved_at is None else fmt.iso(saved_at),
            "devices": [],
            "testResults": None,
        },
    }
