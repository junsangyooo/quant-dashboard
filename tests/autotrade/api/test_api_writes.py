"""Write endpoints of phase 1: notification preferences, mode, push (not built yet)."""

from __future__ import annotations

from fastapi.testclient import TestClient

DEFAULTS = {
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


def events_of(account: dict[str, object]) -> dict[str, bool]:
    notifications = account["notifications"]
    assert isinstance(notifications, dict)
    return {e["id"]: e["on"] for e in notifications["events"]}


def test_account_and_notification_preferences(logged_in: TestClient) -> None:
    account = logged_in.get("/api/account", headers={"user-agent": "x"}).json()
    assert account["thisDevice"]["kind"] in ("iphone-app", "iphone-safari", "mac", "other")
    assert account["thisDevice"]["enteredAt"] == "2026-07-01T16:10:00+09:00"
    notifications = account["notifications"]
    assert notifications["thisDevice"] == {
        "supported": False,
        "reason": "unsupported",
        "subscribed": False,
    }
    assert events_of(account) == DEFAULTS
    assert next(e for e in notifications["events"] if e["id"] == "check-failed")["locked"] is True
    assert (notifications["hideAmounts"], notifications["savedAt"]) == (False, None)
    assert (notifications["devices"], notifications["testResults"]) == ([], None)

    saved = logged_in.put(
        "/api/account/notifications",
        json={"events": {"rebalance-notice": True}, "hideAmounts": True},
    )
    assert saved.status_code == 200
    assert saved.json() == {"savedAt": "2026-07-01T16:10:00+09:00"}
    account = logged_in.get("/api/account").json()
    assert events_of(account)["rebalance-notice"] is True
    assert account["notifications"]["hideAmounts"] is True
    assert account["notifications"]["savedAt"] == "2026-07-01T16:10:00+09:00"
    # Only what is sent changes.
    logged_in.put("/api/account/notifications", json={"events": {"stale": False}})
    account = logged_in.get("/api/account").json()
    assert events_of(account)["rebalance-notice"] is True
    assert events_of(account)["stale"] is False
    assert account["notifications"]["hideAmounts"] is True

    locked = logged_in.put("/api/account/notifications", json={"events": {"check-failed": False}})
    assert (locked.status_code, locked.json()) == (
        400,
        {"error": "locked-event", "detail": {"event": "check-failed"}},
    )
    unknown = logged_in.put("/api/account/notifications", json={"events": {"ai-sell": True}})
    assert unknown.json() == {"error": "unknown-event", "detail": {"event": "ai-sell"}}
    assert logged_in.put("/api/account/notifications", json={"bogus": 1}).status_code == 400


def test_mode_switches(logged_in: TestClient) -> None:
    live = logged_in.post(
        "/api/mode/live", json={"pin": "123456", "confirm": True, "previewHash": "x"}
    )
    assert (live.status_code, live.json()) == (
        409,
        {"error": "blocked", "detail": {"cause": "live-not-available"}},
    )
    paper = logged_in.post("/api/mode/paper")
    assert (paper.status_code, paper.json()) == (200, {"mode": "paper", "cancelFailed": []})
    assert logged_in.post("/api/mode/paper").json() == {"mode": "paper", "cancelFailed": []}
    assert logged_in.post("/api/mode/cancel-retry").json() == {"cancelFailed": []}
    mode = logged_in.get("/api/mode").json()
    assert mode["mode"] == "paper"
    assert mode["canTurnOn"] == {"ok": False, "cause": "live-not-available"}
    assert (mode["live"], mode["liveOff"], mode["twoLedgers"]) == (None, None, None)
    assert (mode["preflight"], mode["preview"], mode["cancelFailed"]) == (None, None, None)
    shell = logged_in.get("/api/shell").json()
    assert (shell["mode"], shell["modeChangedAt"], shell["liveSince"]) == ("paper", None, None)


def test_push_is_not_built_yet(logged_in: TestClient) -> None:
    for path in ("/api/account/push", "/api/account/push/test"):
        response = logged_in.post(path, json={"subscription": {}})
        assert (response.status_code, response.json()) == (
            501,
            {"error": "not-implemented", "detail": {"feature": "push"}},
        )
