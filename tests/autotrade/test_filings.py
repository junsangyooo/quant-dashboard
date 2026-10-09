"""DART and EDGAR adapters and the Yahoo research sources, with stand-in HTTP and yfinance
(no network): parsing, paging, error pages and the states the health screen shows."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
import zipfile
from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from email.message import Message
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from autotrade.domain.instruments import Currency, Instrument, Kind, Market
from autotrade.market import filings as fl
from autotrade.market.filings import (
    DartFilingSource,
    EdgarFilingSource,
    FilingInfo,
    FilingSourceError,
    SourceMaintenanceError,
    SourceNoKeyError,
    SourceUnreachableError,
    plain_text,
)
from autotrade.market.research import YahooAdjustedSource, YahooValuationSource

D = Decimal
HANWHA = Instrument(
    "KR:012450", Market.KR, Currency.KRW, Kind.STOCK, "012450", "한화에어로스페이스", "012450.KS"
)
AVGO = Instrument("US:AVGO", Market.US, Currency.USD, Kind.STOCK, "AVGO", "Broadcom", "AVGO")


class FakeHttp:
    """Answers by URL path; records every request."""

    def __init__(self, routes: Mapping[str, Any]) -> None:
        self.routes = dict(routes)
        self.calls: list[tuple[str, dict[str, str], dict[str, str]]] = []

    def __call__(self, url: str, params: Mapping[str, str], headers: Mapping[str, str]) -> bytes:
        self.calls.append((url, dict(params), dict(headers)))
        answer = self.routes[url]
        if callable(answer):
            answer = answer(dict(params))
        if isinstance(answer, BaseException):
            raise answer
        return answer if isinstance(answer, bytes) else json.dumps(answer).encode()


def zipped(name: str, data: bytes, extra: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(name, data)
        for k, v in (extra or {}).items():
            z.writestr(k, v)
    return buf.getvalue()


CORP_XML = """<?xml version="1.0" encoding="UTF-8"?><result>
<list><corp_code>00126566</corp_code><corp_name>한화에어로스페이스</corp_name>
<stock_code>012450</stock_code><modify_date>20260101</modify_date></list>
<list><corp_code>00999999</corp_code><corp_name>비상장사</corp_name>
<stock_code> </stock_code></list>
</result>""".encode()
DART = fl.DART_BASE


def dart_list(params: dict[str, str]) -> dict[str, Any]:
    page = int(params["page_no"])
    item = {
        "corp_code": "00126566",
        "report_nm": "[기재정정]반기보고서 (2026.06) " if page == 1 else "단일판매ㆍ공급계약체결",
        "rcept_no": f"2026081400000{page}",
        "rcept_dt": "20260814" if page == 1 else "20261012",
    }
    return {"status": "000", "message": "정상", "total_page": 2, "list": [item]}


def test_dart_lists_filings_page_by_page() -> None:
    http = FakeHttp(
        {f"{DART}/corpCode.xml": zipped("CORPCODE.xml", CORP_XML), f"{DART}/list.json": dart_list}
    )
    pauses: list[float] = []
    source = DartFilingSource("key", http, sleep=pauses.append)
    found = source.fetch_filings(HANWHA, date(2026, 6, 9), date(2026, 10, 13))
    assert [(f.source_ref, f.form, f.title, f.filed_on) for f in found] == [
        (
            "20260814000001",
            "반기보고서 (2026.06)",
            "[기재정정]반기보고서 (2026.06)",
            date(2026, 8, 14),
        ),
        ("20260814000002", "단일판매ㆍ공급계약체결", "단일판매ㆍ공급계약체결", date(2026, 10, 12)),
    ]
    assert found[0].url == "https://dart.fss.or.kr/dsaf001/main.do?rcpNo=20260814000001"
    _, params, _ = http.calls[1]
    assert params == {
        "crtfc_key": "key",
        "corp_code": "00126566",
        "bgn_de": "20260609",
        "end_de": "20261013",
        "page_no": "1",
        "page_count": "100",
    }
    assert pauses == [0.2]
    source.fetch_filings(HANWHA, date(2026, 6, 9), date(2026, 10, 13))
    assert [c[0].rsplit("/", 1)[1] for c in http.calls].count("corpCode.xml") == 1  # cached
    other = Instrument(
        "KR:000001", Market.KR, Currency.KRW, Kind.STOCK, "000001", "없음", "000001.KS"
    )
    with pytest.raises(FilingSourceError, match="no corp_code"):
        source.fetch_filings(other, date(2026, 6, 9), date(2026, 10, 13))


def test_dart_states_maintenance_no_data_and_refusals() -> None:
    maintenance = "<result><status>800</status><message>시스템 점검</message></result>".encode()
    http = FakeHttp({f"{DART}/corpCode.xml": maintenance})
    with pytest.raises(SourceMaintenanceError, match="DART 800") as caught:
        DartFilingSource("key", http).fetch_filings(HANWHA, date(2026, 10, 1), date(2026, 10, 2))
    assert caught.value.state == "maintenance"
    with pytest.raises(SourceNoKeyError) as no_key:
        DartFilingSource(None, http).fetch_filings(HANWHA, date(2026, 10, 1), date(2026, 10, 2))
    assert no_key.value.state == "no-key"
    corp = zipped("CORPCODE.xml", CORP_XML)
    cases: list[tuple[Any, type[Exception] | None, str]] = [
        ({"status": "013", "message": "조회된 데이타가 없습니다."}, None, ""),
        (
            {"status": "020", "message": "요청 제한을 초과하였습니다."},
            SourceUnreachableError,
            "stale",
        ),
        ({"status": "010", "message": "등록되지 않은 키입니다."}, FilingSourceError, "failed"),
        ({"status": "800", "message": "점검"}, SourceMaintenanceError, "maintenance"),
        (b"<html>gateway</html>", FilingSourceError, "failed"),
        (urllib.error.URLError("down"), SourceUnreachableError, "stale"),
        (
            urllib.error.HTTPError("u", 503, "busy", Message(), None),
            SourceUnreachableError,
            "stale",
        ),
        (urllib.error.HTTPError("u", 404, "gone", Message(), None), FilingSourceError, "failed"),
        (TimeoutError("timed out"), SourceUnreachableError, "stale"),
    ]
    for answer, error, state in cases:
        source = DartFilingSource(
            "key", FakeHttp({f"{DART}/corpCode.xml": corp, f"{DART}/list.json": answer})
        )
        if error is None:
            assert source.fetch_filings(HANWHA, date(2026, 10, 1), date(2026, 10, 2)) == []
            continue
        with pytest.raises(error) as raised:
            source.fetch_filings(HANWHA, date(2026, 10, 1), date(2026, 10, 2))
        assert getattr(raised.value, "state", None) == state
    broken = DartFilingSource("key", FakeHttp({f"{DART}/corpCode.xml": b"PK not a zip"}))
    with pytest.raises(FilingSourceError, match="corpCode"):
        broken.corp_codes()
    empty = DartFilingSource(
        "key", FakeHttp({f"{DART}/corpCode.xml": zipped("C.xml", b"<result/>")})
    )
    with pytest.raises(FilingSourceError, match="no company"):
        empty.corp_codes()


def test_dart_reads_the_main_document_as_text() -> None:
    main = (
        "<DOCUMENT><TITLE>반기보고서</TITLE><P>지상방산 부문 수주잔고는 38.3조원이다.</P>"
        "<TABLE><TR><TD>매출</TD><TD>1,000</TD></TR></TABLE></DOCUMENT>"
    )
    http = FakeHttp(
        {
            f"{DART}/document.xml": zipped(
                "main.xml", main.encode("euc-kr"), {"att.xml": b"<P>x</P>"}
            )
        }
    )
    info = FilingInfo(
        "dart", "20260814000001", "반기보고서", None, "반기보고서", date(2026, 8, 14), None
    )
    text = DartFilingSource("key", http).fetch_text(info)
    assert text == "반기보고서\n지상방산 부문 수주잔고는 38.3조원이다.\n매출 | 1,000"
    missing = {"status": "014", "message": "파일이 존재하지 않습니다."}
    bad = DartFilingSource("key", FakeHttp({f"{DART}/document.xml": missing}))
    with pytest.raises(FilingSourceError, match="014"):
        bad.fetch_text(info)
    with pytest.raises(FilingSourceError, match="document"):
        DartFilingSource("key", FakeHttp({f"{DART}/document.xml": b"PK broken"})).fetch_text(info)


SUBMISSIONS = {
    "cik": "1730168",
    "filings": {
        "recent": {
            "form": ["8-K", "4", "8-K", "10-Q", "6-K"],
            "filingDate": ["2026-10-09", "2026-10-08", "2026-09-04", "2026-09-10", "2026-01-02"],
            "accessionNumber": [
                "0001730168-26-000102",
                "0001730168-26-000099",
                "0001730168-26-000100",
                "0001730168-26-000101",
                "0001730168-26-000001",
            ],
            "items": ["8.01,9.01", "", "2.02,9.01", "", ""],
            "primaryDocument": ["avgo-8k.htm", "x.xml", "avgo-8k2.htm", "q.htm", "f.htm"],
            "primaryDocDescription": ["8-K", "", "", "10-Q", "6-K"],
        }
    },
}
SUBMISSION_TEXT = b"""<SEC-DOCUMENT>
<DOCUMENT>
<TYPE>8-K
<TEXT><html><body>Item 2.02 Results of Operations</body></html></TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>EX-99.1
<TEXT><html><body><p>Broadcom Inc. Announces Third Quarter Fiscal Year 2026 Results</p>
<table><tr><td>AI revenue</td><td>$6.2 billion</td></tr></table>
<script>ignored()</script></body></html></TEXT>
</DOCUMENT>
</SEC-DOCUMENT>"""


def test_edgar_lists_8k_and_6k_filings_and_reads_the_press_release() -> None:
    folder = "https://www.sec.gov/Archives/edgar/data/1730168/000173016826000100"
    http = FakeHttp(
        {
            fl.EDGAR_TICKERS: {"0": {"cik_str": 1730168, "ticker": "AVGO", "title": "Broadcom"}},
            fl.EDGAR_SUBMISSIONS.format(1730168): SUBMISSIONS,
            f"{folder}/0001730168-26-000100.txt": SUBMISSION_TEXT,
        }
    )
    source = EdgarFilingSource(
        "portfolio-dashboard/1.0 (contact: admin@jsyoo.dev)", http, sleep=lambda s: None
    )
    found = source.fetch_filings(AVGO, date(2026, 6, 9), date(2026, 10, 13))
    assert [(f.source_ref, f.form, f.items, f.title) for f in found] == [
        ("0001730168-26-000102", "8-K", "8.01,9.01", "8-K"),
        ("0001730168-26-000100", "8-K", "2.02,9.01", "8-K 2.02,9.01"),
    ]
    assert found[1].url == f"{folder}/avgo-8k2.htm"
    assert http.calls[0][2]["User-Agent"] == "portfolio-dashboard/1.0 (contact: admin@jsyoo.dev)"
    text = source.fetch_text(found[1])
    title = "Broadcom Inc. Announces Third Quarter Fiscal Year 2026 Results"
    assert text == f"{title}\nAI revenue | $6.2 billion"
    nyse = Instrument("US:ZZZZ", Market.US, Currency.USD, Kind.STOCK, "ZZZZ", "?", "ZZZZ")
    with pytest.raises(FilingSourceError, match="no CIK"):
        source.fetch_filings(nyse, date(2026, 6, 9), date(2026, 10, 13))
    odd = FilingInfo("edgar", "x", "8-K", None, "8-K", date(2026, 9, 4), "https://elsewhere/x")
    with pytest.raises(FilingSourceError, match="odd address"):
        source.fetch_text(odd)
    with pytest.raises(FilingSourceError, match="no address"):
        source.fetch_text(FilingInfo("edgar", "x", "8-K", None, "8-K", date(2026, 9, 4), None))


def test_edgar_answers_we_cannot_use() -> None:
    folder = "https://www.sec.gov/Archives/edgar/data/1730168/000173016826000100"
    tickers = {"0": {"cik_str": 1730168, "ticker": "AVGO", "title": "Broadcom"}}
    bad = EdgarFilingSource(
        "ua",
        FakeHttp(
            {fl.EDGAR_TICKERS: tickers, fl.EDGAR_SUBMISSIONS.format(1730168): {"filings": {}}}
        ),
        sleep=lambda s: None,
    )
    with pytest.raises(FilingSourceError, match="submissions"):
        bad.fetch_filings(AVGO, date(2026, 6, 9), date(2026, 10, 13))
    ragged = {"filings": {"recent": {**SUBMISSIONS["filings"]["recent"], "form": ["8-K"]}}}  # type: ignore[index]
    with pytest.raises(FilingSourceError, match="submissions"):
        EdgarFilingSource(
            "ua",
            FakeHttp({fl.EDGAR_TICKERS: tickers, fl.EDGAR_SUBMISSIONS.format(1730168): ragged}),
            sleep=lambda s: None,
        ).fetch_filings(AVGO, date(2026, 6, 9), date(2026, 10, 13))
    with pytest.raises(FilingSourceError, match="not JSON"):
        EdgarFilingSource("ua", FakeHttp({fl.EDGAR_TICKERS: b"<html>"})).ciks()
    info = FilingInfo(
        "edgar", "0001730168-26-000100", "8-K", None, "8-K", date(2026, 9, 4), f"{folder}/a.htm"
    )
    empty = EdgarFilingSource("ua", FakeHttp({f"{folder}/0001730168-26-000100.txt": b"nothing"}))
    with pytest.raises(FilingSourceError, match="no documents"):
        empty.fetch_text(info)
    plain = b"<DOCUMENT><TYPE>6-K\n<TEXT><p>Monthly revenue September 2026</p></TEXT></DOCUMENT>"
    only_main = EdgarFilingSource("ua", FakeHttp({f"{folder}/0001730168-26-000100.txt": plain}))
    assert only_main.fetch_text(info) == "Monthly revenue September 2026"


def test_plain_text_keeps_lines_and_cells() -> None:
    assert plain_text(
        "<p>a&amp;b</p><br/>c  &nbsp; d<table><tr><th>x</th><td>1</td></tr></table>"
    ) == ("a&b\nc d\nx | 1")
    assert plain_text("<style>p{}</style>\n\n\n<div>one</div>\n\n<div>two</div>") == "one\ntwo"


def test_urllib_get_sends_the_query_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class Response(io.BytesIO):
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            self.close()

    def urlopen(request: Any, timeout: float) -> Response:
        seen["url"], seen["ua"], seen["timeout"] = (
            request.full_url,
            request.get_header("User-agent"),
            timeout,
        )
        return Response(b"body")

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert fl.urllib_get("https://x.test/a", {"q": "한 글"}, {"User-Agent": "me"}) == b"body"
    assert seen == {"url": "https://x.test/a?q=%ED%95%9C+%EA%B8%80", "ua": "me", "timeout": 30.0}
    fl.urllib_get("https://x.test/b", {}, {})
    assert seen["url"] == "https://x.test/b"


def test_yahoo_adjusted_closes_and_ratios() -> None:
    frame = pd.DataFrame(
        {"Close": [100.5, float("nan"), 101.25]},
        index=pd.to_datetime(["2026-10-08", "2026-10-09", "2026-10-12"]).tz_localize(
            "America/New_York"
        ),
    )
    asked: list[dict[str, Any]] = []

    class Ticker:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol
            self.info = {"forwardPE": 18.5, "trailingPE": None, "priceToBook": "x", "other": 1}

        def history(self, **kw: Any) -> pd.DataFrame:
            asked.append({"symbol": self.symbol, **kw})
            return frame if self.symbol == "SPY" else frame.iloc[:0]

    module = SimpleNamespace(Ticker=Ticker)
    series = YahooAdjustedSource(module).fetch_adjusted(
        "SPY", date(2026, 10, 8), date(2026, 10, 12)
    )
    assert series == [(date(2026, 10, 8), D("100.5")), (date(2026, 10, 12), D("101.25"))]
    assert asked[0]["auto_adjust"] is True
    assert asked[0]["end"] == "2026-10-13"
    assert (
        YahooAdjustedSource(module).fetch_adjusted("X", date(2026, 10, 8), date(2026, 10, 12)) == []
    )
    assert YahooValuationSource(module).fetch_valuation("SPY") == {"per_fwd": D("18.5")}
