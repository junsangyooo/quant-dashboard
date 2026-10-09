"""예시-값표 §4 '출시 첫날' built through the engine and read through the API at 7/1 16:10."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient

from autotrade.jobs.tasks import JobContext

from ..fakes import World
from .support import first_day

KOSPI = "KR:069500"
SNP = "US:SPYM"


def rows_of(home: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for group in home["composition"]["groups"] for row in group["rows"]]


def test_home(logged_in: TestClient, world: World, jobs: JobContext) -> None:
    first_day(world, jobs)
    home = logged_in.get("/api/home").json()
    assert home["total"] == 10005258  # §4 합
    assert home["pnl"] == {"amount": 5258, "pct": 0.05}  # '▲ +5,258원 · +0.05%'
    assert home["baseline"] == {"pct": 0.05}  # '손대지 않았을 때 +0.05%' (첫날은 같은 매수)
    assert home["startDate"] == "2026-07-01"
    assert home["stale"] == []
    assert home["basis"] == {
        "valuedAt": "2026-07-01T16:00:00+09:00",
        "krClose": "2026-07-01",
        "usClose": "2026-06-30",
        "fxRate": 1391.5,
        "fxAt": "2026-07-01T16:00:00+09:00",
    }

    card = home["planCard"]
    assert card["share"] == {"pct": 99.6, "target": 100.0}  # '자산의 99.6% · 목표 100%'
    assert card["status"] == "in-progress"
    assert card["next"] == {  # '리밸런싱 중 · 오늘 22:30 미국 매수 54주'
        "kind": "order",
        "at": "2026-07-01T22:30:00+09:00",
        "market": "US",
        "side": "buy",
        "instrumentName": "S&P 500 ETF",
        "qty": 54,
    }
    assert home["planChip"] == {
        "ruleId": "index_half",
        "status": "in-progress",
        "next": card["next"],
    }
    needle = card["gauge"]["needle"]
    assert (needle["instrument"]["id"], needle["deviation"], needle["toThreshold"]) == (
        KOSPI,
        0.2,
        1.8,
    )
    assert card["gauge"]["threshold"] == 2.0
    assert card["nextCheckAt"] == "2026-07-02T08:30:00+09:00"  # '다음 확인 7/2 08:30'
    assert card["others"] is None

    fx_stage, buy_stage = card["stages"]
    assert (fx_stage["kind"], fx_stage["status"], fx_stage["at"]) == (
        "fx",
        "done",
        "2026-07-01T09:10:00+09:00",
    )
    assert fx_stage["orders"][0]["fx"] == {"krw": 4967000, "usd": 3568.24, "rate": 1392.0}
    assert fx_stage["orders"][0]["fill"] == "paper"
    assert (buy_stage["kind"], buy_stage["status"], buy_stage["at"]) == (
        "buy",
        "pending",
        "2026-07-01T22:30:00+09:00",
    )
    kr_buy, us_buy = buy_stage["orders"]
    assert (
        kr_buy["qty"],
        kr_buy["price"],
        kr_buy["amountKrw"],
        kr_buy["fee"],
        kr_buy["status"],
    ) == (156, 32000, 4992000, {"krw": 748}, "filled")
    assert (
        us_buy["qty"],
        us_buy["price"],
        us_buy["amountUsd"],
        us_buy["approx"],
        us_buy["status"],
    ) == (54, 66.0, 3564.0, True, "pending")
    assert us_buy["fee"] == {"usd": 3.56}

    rule_group, cash_group = home["composition"]["groups"]
    kospi, dollars = rule_group["rows"]
    assert (kospi["instrument"]["id"], kospi["krw"], kospi["pct"], kospi["qty"]) == (
        KOSPI,
        4999800,
        50.0,
        156,
    )
    assert kospi["avgCost"] == {"amount": 32005, "currency": "KRW"}
    assert (dollars["krw"], dollars["usd"], dollars["pct"]) == (4965206, 3568.24, 49.6)
    assert dollars["chip"] == {"kind": "buy-wait", "instrumentName": "S&P 500 ETF", "qty": 54}
    assert (rule_group["pct"], rule_group["target"]) == (99.6, 100.0)
    [leftover] = cash_group["rows"]
    assert (leftover["krw"], leftover["chip"], leftover["pct"]) == (
        40252,
        {"kind": "sub-share"},
        0.4,
    )
    assert cash_group["label"] == "cash"
    # The rows add up: to the total in won and to 100.0%, and each group is the sum of its rows.
    rows = rows_of(home)
    assert sum(r["krw"] for r in rows) == home["total"]
    assert sum(Decimal(str(r["pct"])) for r in rows) == Decimal("100.0")
    for group in home["composition"]["groups"]:
        assert Decimal(str(group["pct"])) == sum(Decimal(str(r["pct"])) for r in group["rows"])
    assert home["composition"]["groupBy"] == ["country", "currency"]  # '나라·통화만'
    assert home["composition"]["pendingBar"] is None
    assert home["trend"]["empty"] == "first-day"
    assert home["trend"]["periods"] is None
    assert home["trend"]["events"] == [{"date": "2026-07-01", "kind": "start"}]


def test_plan(logged_in: TestClient, world: World, jobs: JobContext) -> None:
    first_day(world, jobs)
    plan = logged_in.get("/api/plan").json()
    assert plan["ruleShares"] is None
    [card] = plan["rules"]
    assert card["share"] == {"pct": 99.6, "target": 100.0}
    weights = {
        row["instrument"]["id"]: (row["weight"], row["target"], row["toThreshold"])
        for row in card["rows"]
    }
    assert weights == {
        KOSPI: (50.2, 50.0, 1.8),
        SNP: (49.8, 50.0, 1.8),
    }  # '50.2% · 49.8%(매수 대기)'
    assert card["basisLine"] == {
        "pendingBuyIncluded": True,
        "fxRate": 1391.5,
        "fxAt": "2026-07-01T16:00:00+09:00",
        "withdrawExcluded": False,
        "staleMarket": None,
        "staleBasisDate": None,
    }
    items = plan["schedule"]["items"]
    assert {"kind": "next-check", "at": "2026-07-02T08:30:00+09:00"} in items
    assert {"kind": "holiday", "date": "2026-07-03", "markets": ["US"]} in items  # '7/3 미국 휴장'
    assert {"kind": "sub-share-cash", "krw": 40252} in items  # '1주 미만 대기 40,252원'
    now = plan["schedule"]["now"]
    assert (now["ruleId"], now["status"]) == ("index_half", "in-progress")
    assert [s["kind"] for s in now["stages"]] == ["fx", "buy"]
    assert plan["drift"]["empty"] == "second-day"  # '벗어남 흐름은 둘째 날부터'
    assert plan["drift"]["lines"][0]["points"] == [{"date": "2026-07-01", "value": 0.2}]


def test_rules(logged_in: TestClient, world: World, jobs: JobContext) -> None:
    first_day(world, jobs)
    listing = logged_in.get("/api/rules").json()
    assert listing == {
        "rules": [
            {
                "rule": {"id": "index_half", "name": "지수 반반", "ai": False, "colorIndex": 0},
                "share": {"pct": 99.6, "target": 100.0},
                "status": "in-progress",
            }
        ]
    }
    detail = logged_in.get("/api/rules/index_half?lane=daily").json()
    display = detail["display"]
    assert detail["share"] == {"pct": 99.6, "target": 100.0}
    assert detail["example"] is False
    assert display["kind"] == "tiles"
    assert [i["id"] for i in display["what"]["instruments"]] == [KOSPI, SNP]
    assert display["what"]["weights"] == [50.0, 50.0]
    assert display["when"] == {"time": "08:30", "days": "weekdays", "tz": "KST"}
    assert display["condition"] == {"threshold": 2.0, "targetEach": [50.0, 50.0]}
    assert display["action"] == {"stages": ["sell", "fx", "buy"]}
    assert display["measured"] == {
        "median": 9.5,
        "worst": -33.5,
        "badYear": -13.6,
        "period": "2015–25",
        "afterTax": True,
        "source": "T09",
    }
    assert display["now"]["status"] == "in-progress"
    assert display["now"]["nextCheckAt"] == "2026-07-02T08:30:00+09:00"
    assert [s["kind"] for s in display["now"]["stages"]] == ["fx", "buy"]
    missing = logged_in.get("/api/rules/discovery_3y")
    assert (missing.status_code, missing.json()["error"]) == (404, "not-found")


def test_day_and_history_of_the_first_day(
    logged_in: TestClient, world: World, jobs: JobContext
) -> None:
    first_day(world, jobs)
    day = logged_in.get("/api/day/2026-07-01").json()
    assert day["total"] == 10005258
    assert day["change"] is None
    [start] = day["events"]
    assert (start["kind"], start["krw"], start["treatment"]) == ("start", 10000000, "pnl-excluded")
    assert [s["kind"] for s in start["stages"]] == ["fx", "buy"]  # the first purchase
    assert start["feesKrw"] == 748
    assert day["check"]["result"] == "rebalance"
    assert day["check"]["at"] == "2026-07-01T08:30:00+09:00"
    history = logged_in.get("/api/history").json()
    assert history["tiles"]["fees"] == {"krw": 748}
    assert history["tiles"]["checks"] == {"count": 1, "failed": 0}
    [month] = history["months"]
    assert (month["month"], month["change"]) == ("2026-07", 5258)
    [row] = month["events"]
    assert (row["kind"], row["amount"], row["treatment"], row["dayTotal"]) == (
        "start",
        10000000,
        "pnl-excluded",
        10005258,
    )
    assert row["stagesMini"] == ["done", "pending"]
    states = {c["date"]: c["state"] for c in history["calendar"]}
    assert (states["2026-06-30"], states["2026-07-01"], states["2026-07-02"]) == (
        "before-record",
        "in-progress",
        "future",
    )
