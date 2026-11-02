"""DART(TASKS T-12): 가짜 DART로 첫 받기 · 이어 받기 · 한도 넘음 · 키 오류 · 자료 없음 · 접수일 다음 거래일(R-J9).

가짜 응답은 `vendor/dart-samples/`의 꼴(필드 이름)을 그대로 따라요: 견본 행을 복사해 값만 바꿔요.
"""

from __future__ import annotations

import copy
import io
import json
import urllib.parse
import zipfile
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.dart import DartClient, DartError, DartStore, disclosure_kind, rcept_date
from app.db import DB
from app.transport import HttpRequest, HttpResponse, TransportError

SAMPLES = Path(__file__).resolve().parents[2] / "vendor" / "dart-samples"
KEY = "fake-dart-key-0000"


def sample(name: str) -> dict[str, Any]:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


@dataclass
class FakeDart:
    """견본 꼴의 가짜 DART. 회사 2개(삼성전자 · SK하이닉스)."""

    calls: list[tuple[str, dict[str, str]]] = field(default_factory=list)
    key_ok: bool = True
    limit_after: int | None = None  # n번째 요청부터 020
    down: bool = False
    empty: set[str] = field(default_factory=set)  # 이 API는 013(자료 없음)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        url = urllib.parse.urlsplit(request.url)
        name = url.path.rsplit("/", 1)[-1]
        q = dict(urllib.parse.parse_qsl(url.query))
        self.calls.append((name, q))
        if self.down:
            raise TransportError("ConnectionError")
        if not self.key_ok or q.get("crtfc_key") != KEY:
            return self._json(sample("error-key.json"))
        if self.limit_after is not None and len(self.calls) > self.limit_after:
            return self._json(sample("error-limit.json"))
        if name in self.empty:
            return self._json(sample("error-nodata.json"))
        if name == "corpCode.xml":
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as zf:
                zf.writestr("CORPCODE.xml", (SAMPLES / "CORPCODE.sample.xml").read_bytes())
            return HttpResponse(200, {}, buf.getvalue())
        if name == "fnlttMultiAcnt.json":
            return self._json(self._fin(q))
        if name == "list.json":
            return self._json(self._list(q))
        if name == "stockTotqySttus.json":
            data = sample("stockTotqySttus.json")
            for r in data["list"]:
                r["corp_code"] = q["corp_code"]
                r["rcept_no"] = f"{q['bsns_year']}0815000001"
            return self._json(data)
        if name == "alotMatter.json":
            data = sample("alotMatter.json")
            for r in data["list"]:
                r["corp_code"] = q["corp_code"]
                r["rcept_no"] = f"{int(q['bsns_year']) + 1}0310000789"
            return self._json(data)
        return self._json({"status": "100", "message": "필드의 부적절한 값"})

    def _fin(self, q: dict[str, str]) -> dict[str, Any]:
        base = sample("fnlttMultiAcnt.json")
        year, reprt = q["bsns_year"], q["reprt_code"]
        stocks = {"00126380": "005930", "00164779": "000660"}
        rows = []
        for corp in q["corp_code"].split(","):
            for tmpl in base["list"]:
                for fs in ("CFS", "OFS"):
                    r = copy.deepcopy(tmpl)
                    r.update({"stock_code": stocks[corp], "bsns_year": year, "reprt_code": reprt, "fs_div": fs,
                              "rcept_no": f"{year}1030000456"})
                    if fs == "OFS":
                        r["thstrm_amount"] = "1"  # 별도는 다른 값(연결 우선인지 보려고)
                    rows.append(r)
        return {**base, "list": rows}

    def _list(self, q: dict[str, str]) -> dict[str, Any]:
        base = sample("list.json")
        rows = [dict(r, corp_code=q["corp_code"]) for r in base["list"]]
        if q["corp_code"] == "00164779":
            for r in rows:
                r["stock_code"] = "000660"
                r["rcept_no"] = r["rcept_no"][:-1] + "9"
        page = int(q.get("page_no", 1))
        # 2쪽: 첫 쪽에 하나, 둘째 쪽에 하나
        return {**base, "page_no": page, "total_page": 2, "total_count": 2, "list": [rows[page - 1]]}

    @staticmethod
    def _json(data: Any) -> HttpResponse:
        return HttpResponse(200, {"content-type": "application/json"}, json.dumps(data, ensure_ascii=False).encode())


class Today:
    def __init__(self, d: date) -> None:
        self.d = d

    def __call__(self) -> date:
        return self.d


def weekday_next_open(d: date) -> date:
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


@pytest.fixture
def setup(tmp_path: Path) -> tuple[DartStore, DartClient, FakeDart, Today]:
    today = Today(date(2026, 11, 2))
    fake = FakeDart()
    store = DartStore(DB(tmp_path / "d.db"), today=today)
    return store, DartClient(KEY, transport=fake), fake, today


EXPECTED_JOBS = 1 + 12 * 4 + 2 + 12 * 2 * 2 + 12 * 2  # corp + 재무(1묶음) + 목록 + 주식 수 + 배당 = 123


def test_fake_follows_sample_fields() -> None:
    for name in ("fnlttMultiAcnt.json", "list.json", "stockTotqySttus.json", "alotMatter.json"):
        keys = set(sample(name)["list"][0])
        assert keys, name
    f = FakeDart()
    resp = f(HttpRequest("GET", f"https://x/api/fnlttMultiAcnt.json?crtfc_key={KEY}&corp_code=00126380"
                                "&bsns_year=2026&reprt_code=11014", {}, None))
    rows = json.loads(resp.body)["list"]
    assert set(rows[0]) == set(sample("fnlttMultiAcnt.json")["list"][0])


def test_first_download(setup) -> None:  # type: ignore[no-untyped-def]
    store, client, fake, _ = setup
    store.start()
    p = store.run(client)
    assert (p.state, p.done, p.total, p.pct) == ("done", EXPECTED_JOBS, EXPECTED_JOBS, 100)
    assert p.message == "다 받음"
    db = store.db
    assert {r["stock_code"]: r["corp_code"] for r in db.all("SELECT * FROM dart_corp")} == {
        "005930": "00126380", "000660": "00164779"}
    assert db.one("SELECT COUNT(*) n FROM dart_disc")["n"] == 4  # 회사마다 2쪽 × 1건
    kinds = {r["report_nm"]: r["kind"] for r in db.all("SELECT * FROM dart_disc")}
    assert kinds == {"주요사항보고서(자기주식취득결정)": "buyback", "분기보고서 (2026.09)": "earnings"}
    sh = db.one("SELECT * FROM dart_shares WHERE stock_code='005930' AND year=2026 AND reprt='11011'")
    assert sh["shares"] == 7_000_000_000 and sh["treasury"] == 100_000_000
    dv = db.one("SELECT * FROM dart_div WHERE stock_code='005930' AND year=2025")
    assert dv["dps"] == 1500 and dv["rcept_dt"] == "2026-03-10"
    # 요청 수 = 일 수 + 목록의 둘째 쪽(회사 2) · 키는 요청 주소에만
    assert len(fake.calls) == EXPECTED_JOBS + 2 == store.used_today()
    assert "fake-dart-key" not in repr(client)


def test_resume_continues_where_it_stopped(setup) -> None:  # type: ignore[no-untyped-def]
    store, client, fake, _ = setup
    store.start()
    p = store.run(client, budget=10)
    assert p.state == "running" and p.done == 10 and not p.fast_done
    before = len(fake.calls)
    p = store.run(client, budget=45)
    assert p.done == 55 and p.fast_done  # 재무 · 공시를 다 받음
    assert p.message.startswith("가치 조건(시가총액 · PER · PBR · PSR · 배당수익률)은 주식 수를 받는 약 4일 뒤부터 써요")
    p = store.run(client)
    assert p.state == "done"
    # 다 받은 일은 다시 받지 않아요: 첫 받기와 같은 요청 수
    assert len(fake.calls) == EXPECTED_JOBS + 2
    assert before == 10


def test_daily_limit_then_tomorrow(setup, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    _, client, fake, today = setup
    store = DartStore(DB(tmp_path / "lim.db"), today=today, daily_limit=30)
    store.start()
    p = store.run(client)
    assert p.state == "limit" and p.message == "하루 20,000건을 넘었어요 · 내일 이어서 받아요"
    assert store.used_today() == 30 and len(fake.calls) == 30
    p = store.run(client)  # 같은 날 다시: 요청 0
    assert len(fake.calls) == 30 and p.state == "limit"
    today.d = date(2026, 11, 3)
    for _ in range(5):
        p = store.run(client)
        today.d += timedelta(days=1)
    assert p.state == "done" and p.done == p.total


def test_server_limit_020(setup) -> None:  # type: ignore[no-untyped-def]
    store, client, fake, today = setup
    fake.limit_after = 20
    store.start()
    p = store.run(client)
    assert p.state == "limit" and store.used_today() == store.daily_limit
    fake.limit_after = None
    today.d = date(2026, 11, 3)
    assert store.run(client).state == "done"


def test_key_error(setup) -> None:  # type: ignore[no-untyped-def]
    store, client, fake, _ = setup
    fake.key_ok = False
    store.start()
    p = store.run(client)
    assert p.state == "key" and p.message == "DART 인증키가 맞지 않아요 · 인증키를 확인하고 다시 입력해요"
    assert p.done == 0
    with pytest.raises(DartError) as e:
        client.financials(["00126380"], 2026, "11011")
    assert e.value.kind == "key"


def test_no_data_is_empty_not_error(setup) -> None:  # type: ignore[no-untyped-def]
    store, client, fake, _ = setup
    fake.empty = {"alotMatter.json", "stockTotqySttus.json"}
    store.start()
    p = store.run(client)
    assert p.state == "done"
    assert store.db.one("SELECT COUNT(*) n FROM dart_div")["n"] == 0
    assert store.db.one("SELECT COUNT(*) n FROM dart_shares")["n"] == 0


def test_network_down(setup) -> None:  # type: ignore[no-untyped-def]
    store, client, fake, _ = setup
    fake.down = True
    store.start()
    assert store.run(client).state == "network"


def test_usable_from_next_trading_day(setup) -> None:  # type: ignore[no-untyped-def]
    """R-J9: 11/2(월) 접수 공시 → 11/3(화) 판단부터. 금요일 접수 → 월요일부터. 재무는 연결 우선."""
    store, client, _, _ = setup
    store.start()
    store.run(client)
    disc = store.disclosures_on("005930", date(2026, 11, 2), weekday_next_open)
    assert [d["report_nm"] for d in disc] == ["분기보고서 (2026.09)"]  # 10/30(금) 접수 → 11/2(월)부터
    assert disc[0]["usable_from"] == "2026-11-02"
    disc = store.disclosures_on("005930", date(2026, 11, 3), weekday_next_open)
    assert [d["kind"] for d in disc] == ["earnings", "buyback"]
    fin = store.financial_rows("005930", date(2026, 10, 30), weekday_next_open)
    assert all(r["year"] < 2026 for r in fin)  # 2026 보고서는 10/30 접수 → 11/2부터
    fin = store.financial_rows("005930", date(2026, 11, 2), weekday_next_open)
    equity = [r for r in fin if r["year"] == 2026 and r["reprt"] == "11014" and r["account"] == "자본총계"]
    assert len(equity) == 1 and equity[0]["fs_div"] == "CFS" and equity[0]["amount"] == 100_000_000_000


def test_disclosure_kinds_and_receipt_date() -> None:
    assert rcept_date("20261102000123") == date(2026, 11, 2)
    cases = {
        "주요사항보고서(자기주식처분결정)": "treasury_sale",
        "주요사항보고서(유상증자결정)": "rights_issue",
        "주요사항보고서(무상증자결정)": "bonus_issue",
        "주요사항보고서(감자결정)": "capital_reduction",
        "주요사항보고서(전환사채권발행결정)": "cb",
        "주요사항보고서(신주인수권부사채권발행결정)": "bw",
        "주요사항보고서(회사합병결정)": "merger",
        "주요사항보고서(회사분할결정)": "split",
        "주요사항보고서(영업양수결정)": "business_transfer",
        "주요사항보고서(소송등의제기)": "lawsuit",
        "주요사항보고서(부도발생)": "default",
        "주요사항보고서(회생절차개시신청)": "rehabilitation",
        "주요사항보고서(해산사유발생)": "dissolution",
        "[기재정정]사업보고서 (2025.12)": "earnings",
        "임원ㆍ주요주주특정증권등소유상황보고서": None,
    }
    for name, kind in cases.items():
        assert disclosure_kind(name) == kind, name
