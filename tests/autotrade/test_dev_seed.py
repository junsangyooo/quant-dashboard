"""python -m autotrade.jobs dev-seed: the three worlds through the API at their own clock, the
refusals that keep it away from a real ledger, and the dev-only fake clock of the API app."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from autotrade.api.app import create_app, dev_clock
from autotrade.config import REPO_ROOT
from autotrade.jobs.cli import main

DATA = REPO_ROOT / "data"


def seed(db: Path, world: str, *extra: str, env: dict[str, str] | None = None) -> dict[str, Any]:
    lines: list[str] = []
    code = main(
        ["dev-seed", "--db", str(db), "--world", world, *extra], env=env or {}, out=lines.append
    )
    assert code == 0
    report: dict[str, Any] = json.loads(lines[0])
    return report


@pytest.fixture
def reader(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Open a seeded database the way the web app runs the stack (dev-seed's env line)."""
    clients: list[TestClient] = []

    def open_(report: dict[str, Any], pin: str = "123456") -> TestClient:
        for pair in report["env"].split():
            key, _, value = pair.partition("=")
            monkeypatch.setenv(key, value)
        client = TestClient(create_app(), base_url="https://testserver")
        client.__enter__()
        clients.append(client)
        assert client.post("/api/auth/pin", json={"pin": pin}).status_code == 204
        return client

    yield open_
    for client in clients:
        client.__exit__(None, None, None)


def test_the_first_day_reads_like_section_4(tmp_path: Path, reader: Any) -> None:
    report = seed(tmp_path / "dev" / "first.db", "first-day", "--pin", "654321")
    assert (report["result"], report["now"], report["pin"]) == (
        "ok",
        "2026-07-01T16:10:00+09:00",
        "654321",
    )
    client = reader(report, "654321")
    assert client.get("/api/shell").json()["now"] == "2026-07-01T16:10:00+09:00"  # its clock
    home = client.get("/api/home").json()
    # 예시-값표 §4: 10,005,258 = 156 KOSPI200 ETF at 32,050 + $3,568.24 waiting + 40,252 won.
    assert (home["total"], home["pnl"]) == (10005258, {"amount": 5258, "pct": 0.05})
    assert home["planChip"]["next"]["qty"] == 54  # the US buy of 22:30
    assert (tmp_path / "dev" / "autotrade.secret").exists()  # the PIN's pepper, next to it


def test_the_paper_world_runs_from_7_1_to_10_7(tmp_path: Path, reader: Any) -> None:
    report = seed(tmp_path / "paper.db", "paper")
    # The scripted outage of 9/9 is the only failure: the check and its retry.
    assert [(f["at"][:16], f["task"]) for f in report["failed"]] == [
        ("2026-09-09T08:30", "check"),
        ("2026-09-09T09:30", "retry"),
    ]
    client = reader(report)
    history = client.get("/api/history").json()
    events = {(e["date"], e["kind"]) for m in history["months"] for e in m["events"]}
    assert {
        ("2026-07-01", "start"),
        ("2026-08-21", "rebalance"),
        ("2026-09-09", "check-failed"),
        ("2026-09-30", "dividend"),
        ("2026-10-07", "in-progress"),
    } <= events
    home = client.get("/api/home").json()
    assert home["planChip"]["status"] == "in-progress"  # the US buy waits for 22:30
    assert home["planChip"]["next"]["at"] == "2026-10-07T22:30:00+09:00"
    assert client.get("/api/health").json()["summary"]["kind"] == "ok"  # 9/9 was closed
    day = client.get("/api/day/2026-09-09").json()
    assert day["check"]["failure"] == {"reason": "no-quote", "recoveredOn": "2026-09-10"}


def test_the_discovery_world_has_every_3y_screen_element(tmp_path: Path, reader: Any) -> None:
    report = seed(tmp_path / "discovery.db", "discovery")
    assert (report["now"], report["ai_calls"], report["failed"]) == (
        "2026-11-03T16:10:00+09:00",
        37,  # 15 + 2 earnings reads, a screen, two checks asked twice, 15 reviews
        [],
    )
    client = reader(report)
    plan = client.get("/api/plan").json()
    index, ai = plan["rules"]
    # The index rule counts only its own shares of the ETF the AI rule parks money in.
    assert index["status"] == "in-range"
    assert ai["gauge"]["needle"]["progress"] == 64.0  # land-systems backlog 38.3조 -> 33조, line 30
    bought = [r["instrument"]["name"] for r in ai["rows"] if r["weight"] is not None]
    waiting = [r["instrument"]["name"] for r in ai["rows"] if r["weight"] is None]
    assert (len(bought), sorted(waiting)) == (
        11,
        ["Eli Lilly", "TSMC", "삼양식품", "한화에어로스페이스"],
    )
    shock = client.get("/api/day/2026-10-21").json()["events"][0]["judgment"]
    assert (shock["trigger"], shock["votes"], shock["output"]) == (
        "shock",
        ["hold", "hold"],
        [{"key": "news", "value": 1}],
    )
    filing = client.get("/api/day/2026-10-23").json()["events"][0]["judgment"]
    assert (filing["trigger"], filing["verdict"], filing["votes"]) == (
        "filing",
        "weaken",
        ["invalidated", "hold"],
    )
    review = client.get("/api/day/2026-10-31").json()["events"][0]["judgment"]
    assert review["output"][:3] == [
        {"key": "hold", "value": 14},
        {"key": "weaken", "value": 1},
        {"key": "invalidated", "value": 0},
    ]
    history = client.get("/api/history").json()
    ai_plans = [
        e["date"]
        for m in history["months"]
        for e in m["events"]
        if e.get("rule", {}).get("id") == "discovery_3y" and "weightsMini" in e
    ]
    assert sorted(ai_plans) == ["2026-10-08", "2026-11-02"]  # the seed bought, the equal weight
    for lane in ("daily", "earnings", "monthly", "quarterly"):
        nodes = client.get(f"/api/rules/discovery_3y?lane={lane}").json()["display"]["nodes"]
        assert any(n["now"]["rows"] for n in nodes)
    health = client.get("/api/health").json()
    assert {s["id"]: s["state"] for s in health["sources"]} == {
        "kr-quotes": "fresh",
        "us-quotes": "fresh",
        "fx": "fresh",
        "filings": "fresh",
        "ai-cli": "fresh",
        "metric-table": "fresh",
    }
    # Only data names are Korean in what the screens read (CONTRACT.md 원칙).
    han = re.compile(r"[가-힣]")
    urls = ["/api/home", "/api/plan", "/api/history", "/api/health", "/api/day/2026-10-21"]
    for url in urls:
        text = json.dumps(client.get(url).json(), ensure_ascii=False)
        for value in re.findall(
            r'"(?:name|initials|param|title|subtitle|text|value)": "([^"]*)"', text
        ):
            text = text.replace(f'"{value}"', '""')
        assert not han.search(text), url


@pytest.mark.parametrize(
    "where",
    [
        "data/autotrade.db",  # the real ledger
        "data/dev/seed.db",  # anything under data/
        "data/../data/autotrade.db",
        "data",
    ],
)
def test_it_never_writes_under_data(
    where: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(REPO_ROOT)
    before = sorted(p.name for p in DATA.iterdir()) if DATA.exists() else []
    code = main(["dev-seed", "--db", where, "--world", "paper"], env={})
    assert code == 2
    refused = json.loads(capsys.readouterr().err)
    assert (refused["result"], "never touches a real ledger" in refused["error"]) == (
        "refused",
        True,
    )
    after = sorted(p.name for p in DATA.iterdir()) if DATA.exists() else []
    assert after == before  # nothing created


def test_it_refuses_a_link_into_data_the_configured_ledger_and_an_existing_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    link = tmp_path / "link"
    link.symlink_to(DATA, target_is_directory=True)
    assert main(["dev-seed", "--db", str(link / "x.db"), "--world", "paper"], env={}) == 2
    configured = tmp_path / "ledger.db"
    env = {"AUTOTRADE_DB": str(configured)}
    assert main(["dev-seed", "--db", str(configured), "--world", "paper"], env=env) == 2
    existing = tmp_path / "old.db"
    existing.write_text("keep me")
    assert main(["dev-seed", "--db", str(existing), "--world", "paper"], env={}) == 2
    assert existing.read_text() == "keep me"
    assert main(["dev-seed", "--world", "paper"], env={}) == 2  # no --db
    errors = [json.loads(line)["error"] for line in capsys.readouterr().err.splitlines()]
    assert ["under" in errors[0], "configured" in errors[1], "exists" in errors[2]] == [True] * 3
    bad_pin = tmp_path / "pin.db"
    assert main(["dev-seed", "--db", str(bad_pin), "--world", "paper", "--pin", "12"], env={}) == 2
    assert not bad_pin.exists()


def test_pin_and_world_belong_to_dev_seed_only(tmp_path: Path) -> None:
    for argv in (["set-pin", "--pin", "123456"], ["status", "--world", "paper"], ["dev-seed"]):
        with pytest.raises(SystemExit):
            main([*argv, "--db", str(tmp_path / "x.db")], env={})


def test_the_fake_clock_needs_the_dev_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reader: Any
) -> None:
    assert dev_clock({"AUTOTRADE_FAKE_NOW": "2026-10-07T16:10"}) is None  # ignored
    assert dev_clock({"AUTOTRADE_DEV": "1"}) is None
    fixed = dev_clock({"AUTOTRADE_DEV": "1", "AUTOTRADE_FAKE_NOW": "2026-10-07T16:10"})
    assert fixed is not None
    assert fixed().isoformat() == "2026-10-07T16:10:00+09:00"
    # The app the server runs: without AUTOTRADE_DEV the variable changes nothing.
    report = seed(tmp_path / "clock.db", "first-day")
    report["env"] = report["env"].replace("AUTOTRADE_DEV=1 ", "")
    monkeypatch.delenv("AUTOTRADE_DEV", raising=False)
    client = reader(report)
    assert client.get("/api/shell").json()["now"] != "2026-07-01T16:10:00+09:00"
