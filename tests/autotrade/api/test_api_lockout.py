"""PIN lockout (audit A1): IPv6 by /64, 'PIN 실패 급증', the hold until unlock, PIN changes while
someone is guessing, and the CLI that reopens login (autotrade/api/auth.py)."""

from __future__ import annotations

import io
import json
import sqlite3
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from autotrade.api.auth import address_key, pin_alert, session_key, set_pin
from autotrade.api.settings import ApiSettings
from autotrade.config import Config
from autotrade.db import auth_repo
from autotrade.jobs.cli import main as jobs_main

from ..helpers import kst
from .support import PIN, Clock, owner_pin

NGINX = ("127.0.0.1", 40000)
WRONG = "000000"


@pytest.fixture
def proxied(app: FastAPI, db: sqlite3.Connection, settings: ApiSettings) -> Iterator[TestClient]:
    """Requests that arrive through nginx, each naming its address in X-Forwarded-For."""
    owner_pin(db, settings)
    with TestClient(app, base_url="https://testserver", client=NGINX) as c:
        yield c


def attempt(c: TestClient, ip: str, pin: str = WRONG) -> Any:
    return c.post("/api/auth/pin", json={"pin": pin}, headers={"x-forwarded-for": ip})


def wrong_from(c: TestClient, prefix: str, count: int) -> None:
    """`count` wrong PINs, five per address (an address locks at its fifth)."""
    for i in range(count):
        response = attempt(c, f"{prefix}.{i // 5}")
        assert response.status_code == 403


def unlock_cli(db_path: Path) -> tuple[int, dict[str, Any]]:
    lines: list[str] = []
    code = jobs_main(["unlock", "--db", str(db_path)], env={}, out=lines.append)
    return code, json.loads(lines[0])


def test_address_keys() -> None:
    assert address_key("203.0.113.7") == "203.0.113.7"
    # One home or phone network is one /64: its addresses share a key.
    assert address_key("2001:db8:1:2::1") == "2001:db8:1:2::/64"
    assert address_key("2001:db8:1:2:aaaa:bbbb:cccc:dddd") == "2001:db8:1:2::/64"
    assert address_key("2001:db8:1:3::1") == "2001:db8:1:3::/64"
    assert address_key("::ffff:203.0.113.7") == "203.0.113.7"  # IPv4-mapped
    assert address_key("fe80::1%eth0") == "fe80::/64"
    assert address_key("2001:db8::1", ipv6_prefix=48) == "2001:db8::/48"
    assert address_key("testclient") == "testclient"  # not an address: the text itself
    assert session_key("abcdefghijklmnopqrstuvwxyz") == "session:abcdefghijklmnop"


def test_ipv6_addresses_of_one_network_share_a_lock(proxied: TestClient) -> None:
    for host in range(1, 5):
        assert attempt(proxied, f"2001:db8:1:2::{host}").json()["error"] == "pin"
    fifth = attempt(proxied, "2001:db8:1:2:ffff::9")  # another address of the same /64
    assert (fifth.json()["error"], fifth.json()["scope"]) == ("locked", "ip")
    assert attempt(proxied, "2001:db8:1:2::77", PIN).json()["error"] == "locked"
    assert attempt(proxied, "2001:db8:1:3::1", PIN).status_code == 204  # the next /64 is free


def test_ten_wrong_pins_a_day_raise_the_alert_but_leave_login_open(
    proxied: TestClient, db: sqlite3.Connection, clock: Clock
) -> None:
    wrong_from(proxied, "10.0.0", 9)
    assert pin_alert(db) is None
    clock.now += timedelta(hours=2)  # the hourly cap is not what raises it
    wrong_from(proxied, "10.0.1", 1)
    alert = pin_alert(db)
    assert alert is not None
    assert (alert.count, alert.closed, alert.since) == (10, False, clock.now)
    wrong_from(proxied, "10.0.2", 2)  # counted on the raised alert
    assert (pin_alert(db) or alert).count == 12
    assert attempt(proxied, "10.0.9.9", PIN).status_code == 204  # login still open

    shell = proxied.get("/api/shell").json()
    assert shell["status"] == {"kind": "todo", "count": 1}  # outranks '첫 확인 전'
    health = proxied.get("/api/health").json()
    todo = health["todos"][0]
    assert todo == {
        "id": "pin-failures",
        "severity": "red",
        "kind": "pin-failures",
        "facts": {
            "since": "2026-07-01T18:10:00+09:00",
            "count": 12,
            "closed": 0,
            "lastAt": "2026-07-01T18:10:00+09:00",
        },
        "action": {"kind": "manual"},
        "effect": "other",
    }
    assert health["summary"]["todoCount"] == 1


def test_thirty_a_day_close_new_logins_until_unlock(
    proxied: TestClient, app: FastAPI, db: sqlite3.Connection, clock: Clock, api_cfg: Config
) -> None:
    owner = TestClient(app, base_url="https://testserver", client=NGINX)
    with owner:
        assert attempt(owner, "198.51.100.1", PIN).status_code == 204  # the owner's own device
        wrong_from(proxied, "10.0.0", 20)  # the hourly cap closes for an hour ...
        assert attempt(proxied, "10.0.9.9", PIN).json()["scope"] == "global"
        clock.now += timedelta(hours=1, minutes=1)
        wrong_from(proxied, "10.0.5", 9)
        last = attempt(proxied, "10.0.7.0")  # ... and the 30th of the day closes until unlock
        since = "2026-07-01T17:11:00+09:00"
        assert last.json() == {"error": "locked", "scope": "hold", "since": since}
        # Refused before the PIN is checked: the right PIN, a fresh address, a day later.
        clock.now += timedelta(hours=25)
        refused = attempt(proxied, "192.0.2.50", PIN)
        assert (refused.status_code, refused.json()["scope"]) == (403, "hold")
        assert auth_repo.count_failures_since(db, clock.now - timedelta(days=3)) == 30  # no more
        # The open session keeps working and sees why.
        assert owner.get("/api/shell").json()["status"] == {"kind": "todo", "count": 1}
        todo = owner.get("/api/health").json()["todos"][0]
        assert (todo["kind"], todo["facts"]["closed"], todo["facts"]["count"]) == (
            "pin-failures",
            1,
            30,
        )
        # Rows are pruned only when a new wrong PIN arrives; under the hold none is counted.
        assert todo["facts"]["lastAt"] == "2026-07-01T17:11:00+09:00"

        code, out = unlock_cli(api_cfg.db_path)
        assert (code, out) == (
            0,
            {
                "job": "unlock",
                "result": "ok",
                "clearedFailures": 30,
                "clearedLocks": 9,  # seven addresses, the alert and the hold
                "wasClosed": True,
                "wasAlerted": True,
            },
        )
        assert attempt(proxied, "192.0.2.50", PIN).status_code == 204
        assert owner.get("/api/health").json()["todos"] == []
        assert owner.get("/api/shell").json()["status"]["kind"] == "before-first"


def test_pacing_under_the_hourly_cap_still_ends_in_the_hold(
    proxied: TestClient, clock: Clock
) -> None:
    """19 an hour never trips the hourly cap (that allowed ~480 a day); the daily count stops it."""
    for hour in range(2):
        for i in range(19):
            response = attempt(proxied, f"10.{hour}.{i}.1")
            if hour == 1 and i == 10:
                assert response.json()["scope"] == "hold"  # the 30th
                return
            assert response.json()["error"] == "pin"
        clock.now += timedelta(hours=1, minutes=1)
    pytest.fail("the hold never came")


def test_set_pin_clears_the_lockout(
    proxied: TestClient, db: sqlite3.Connection, api_cfg: Config, clock: Clock
) -> None:
    wrong_from(proxied, "10.0.0", 20)
    clock.now += timedelta(hours=1, minutes=1)
    wrong_from(proxied, "10.0.5", 10)
    assert attempt(proxied, "10.1.0.1", PIN).json()["scope"] == "hold"
    lines: list[str] = []
    stdin = io.StringIO("222222\n222222\n")
    code = jobs_main(
        ["set-pin", "--db", str(api_cfg.db_path)], env={}, out=lines.append, stdin=stdin
    )
    out = json.loads(lines[0])
    cleared = (out["wasClosed"], out["wasAlerted"], out["clearedFailures"])
    assert (code, *cleared) == (0, True, True, 30)
    assert pin_alert(db) is None
    assert attempt(proxied, "10.1.0.1", "222222").status_code == 204


def test_unlock_with_nothing_locked(api_cfg: Config, db: sqlite3.Connection) -> None:
    assert unlock_cli(api_cfg.db_path) == (
        0,
        {
            "job": "unlock",
            "result": "ok",
            "clearedFailures": 0,
            "clearedLocks": 0,
            "wasClosed": False,
            "wasAlerted": False,
        },
    )


def change(c: TestClient, current: str, new: str = "654321", ip: str = "198.51.100.1") -> Any:
    return c.post(
        "/api/account/pin",
        json={"current": current, "next": new},
        headers={"x-forwarded-for": ip},
    )


def test_a_session_can_change_the_pin_while_logins_are_closed(
    proxied: TestClient, app: FastAPI, clock: Clock
) -> None:
    with TestClient(app, base_url="https://testserver", client=NGINX) as owner:
        assert attempt(owner, "198.51.100.1", PIN).status_code == 204
        wrong_from(proxied, "10.0.0", 20)
        assert attempt(proxied, "10.0.9.9", PIN).json()["scope"] == "global"
        assert change(owner, PIN).status_code == 204  # under the hourly lock
        clock.now += timedelta(hours=1, minutes=1)
        wrong_from(proxied, "10.0.5", 10)
        assert attempt(proxied, "10.0.9.9", "654321").json()["scope"] == "hold"
        assert change(owner, "654321", "111111").status_code == 204  # under the hold
        # The new PIN does not reopen login: only unlock or set-pin do.
        assert attempt(proxied, "10.0.9.9", "111111").json()["scope"] == "hold"


def test_the_address_lock_still_applies_to_a_pin_change(proxied: TestClient, app: FastAPI) -> None:
    with TestClient(app, base_url="https://testserver", client=NGINX) as owner:
        assert attempt(owner, "198.51.100.1", PIN).status_code == 204
        for _ in range(5):  # the owner's address locks (someone else on his network)
            assert attempt(proxied, "198.51.100.1").status_code == 403
        refused = change(owner, PIN)
        assert (refused.json()["error"], refused.json()["scope"]) == ("locked", "ip")
        assert change(owner, PIN, ip="198.51.101.1").status_code == 204  # elsewhere it works


def test_five_wrong_current_pins_close_the_session(
    proxied: TestClient, app: FastAPI, db: sqlite3.Connection, clock: Clock
) -> None:
    """A stolen cookie cannot guess the PIN from many addresses: the session ends at the fifth."""
    with TestClient(app, base_url="https://testserver", client=NGINX) as thief:
        assert attempt(thief, "198.51.100.1", PIN).status_code == 204
        for i in range(4):
            wrong = change(thief, "111111", ip=f"203.0.113.{i}")
            assert wrong.json() == {"error": "current-pin"}
        fifth = change(thief, "111111", ip="203.0.113.99")
        assert fifth.json() == {"error": "session"}
        assert thief.get("/api/shell").json() == {"error": "session"}
        assert change(thief, PIN).json() == {"error": "session"}
    assert auth_repo.count_failures_since(db, clock.now - timedelta(days=1)) == 5  # counted
    revoked = db.execute("SELECT revoked_why FROM sessions").fetchall()
    assert [r["revoked_why"] for r in revoked] == ["pin-failures"]


def test_a_right_pin_change_clears_the_session_count(proxied: TestClient, app: FastAPI) -> None:
    with TestClient(app, base_url="https://testserver", client=NGINX) as owner:
        assert attempt(owner, "198.51.100.1", PIN).status_code == 204
        for i in range(4):
            assert change(owner, "111111", ip=f"203.0.113.{i}").json() == {"error": "current-pin"}
        assert change(owner, PIN, "222222").status_code == 204
        for i in range(4):  # four more wrong ones: the count started again
            assert change(owner, "111111", ip=f"203.0.114.{i}").json() == {"error": "current-pin"}
        assert owner.get("/api/shell").status_code == 200


def test_a_wrong_current_pin_can_lock_the_address(proxied: TestClient, app: FastAPI) -> None:
    with TestClient(app, base_url="https://testserver", client=NGINX) as owner:
        assert attempt(owner, "198.51.100.1", PIN).status_code == 204
        for _ in range(4):  # someone else on the owner's network
            assert attempt(proxied, "198.51.100.1").json()["error"] == "pin"
        locked = change(owner, "111111")  # the fifth wrong PIN of this address
        assert (locked.json()["error"], locked.json()["scope"]) == ("locked", "ip")
        assert owner.get("/api/shell").status_code == 200  # the session itself stays open


def test_set_pin_refuses_a_bad_pin(db: sqlite3.Connection) -> None:
    with pytest.raises(ValueError, match="six digits"):
        set_pin(db, b"x" * 32, "12345", 2**10, kst("2026-07-01 16:10"))
