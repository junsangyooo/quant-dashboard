"""Filing lists and filing texts of the watched companies: DART (Korea) and EDGAR (US).

- DART open API (needs DART_API_KEY)
  - corpCode.xml: a zip of every listed company's corp_code. Anything else is an error page, for
    example status 800 '시스템 점검으로 인한 서비스 중지' (T28 met it all evening on 2026-10-08).
  - list.json: one company's filings, status '000' = ok, '013' = none in the range.
  - document.xml: the original text of one filing (a zip of XML-like markup).
- EDGAR (SEC asks for a User-Agent with a contact; the repository's value is used)
  - company_tickers.json: ticker -> CIK
  - data.sec.gov/submissions/CIK##########.json: 'filings.recent' columns (form, items,
    filingDate, accessionNumber, primaryDocument ...)
  - Archives/edgar/data/<cik>/<accession>.txt: the whole submission; the press release is the
    EX-99.1 document of an 8-K (T27: read the official text, not news articles).

Every request goes through one `http_get(url, params, headers)` function, so tests pass a fake
(no network). Failures become FilingSourceError with the state the health screen shows:
'maintenance' (DART said so), 'stale' (no answer, a connection cut mid-answer), 'no-key',
'failed' (an answer we cannot use: a refusal, a corrupt zip). A company the source does not know
(an ETF has no DART corp_code) is CompanyNotFoundError: that company's fault, not the source's.
"""

from __future__ import annotations

import html
import http.client
import io
import json
import re
import time as _time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
import zlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol
from xml.etree import ElementTree

from autotrade.domain.instruments import Instrument
from autotrade.market.sources import SourceError

HttpGet = Callable[[str, Mapping[str, str], Mapping[str, str]], bytes]

DART_BASE = "https://opendart.fss.or.kr/api"
DART_VIEW = "https://dart.fss.or.kr/dsaf001/main.do?rcpNo={}"
EDGAR_TICKERS = "https://www.sec.gov/files/company_tickers.json"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{:010d}.json"
EDGAR_ARCHIVE = "https://www.sec.gov/Archives/edgar/data/{}/{}"
REQUEST_TIMEOUT_S = 30.0

# DART statuses (opendart 개발가이드): 000 ok, 013 no data, 020 too many requests,
# 800 maintenance; 010/011/012/901 the key or the address is refused.
DART_OK = ("000", "013")
DART_STALE = ("020",)
DART_MAINTENANCE = ("800",)


class FilingSourceError(SourceError):
    state = "failed"


class SourceMaintenanceError(FilingSourceError):
    state = "maintenance"


class SourceUnreachableError(FilingSourceError):
    state = "stale"


class SourceNoKeyError(FilingSourceError):
    state = "no-key"


class CompanyNotFoundError(FilingSourceError):
    """The source answers but does not know this company (no DART corp_code, no EDGAR CIK)."""


# A zip that arrived broken: a bad archive, a broken deflate stream, a cut-off member, an
# unsupported or encrypted member.
_CORRUPT = (
    zipfile.BadZipFile,
    zlib.error,
    EOFError,
    IndexError,
    KeyError,
    NotImplementedError,
    RuntimeError,
)


@dataclass(frozen=True)
class FilingInfo:
    source: str  # 'dart' | 'edgar'
    source_ref: str  # DART rcept_no, EDGAR accession number
    form: str  # EDGAR form type; DART the report name without the [기재정정]-style prefix
    items: str | None  # EDGAR 8-K items ('2.02,9.01')
    title: str
    filed_on: date
    url: str | None


class FilingSource(Protocol):
    name: str

    def fetch_filings(self, instrument: Instrument, start: date, end: date) -> list[FilingInfo]: ...

    def fetch_text(self, filing: FilingInfo) -> str: ...


def urllib_get(
    url: str,
    params: Mapping[str, str],
    headers: Mapping[str, str],
    timeout: float = REQUEST_TIMEOUT_S,
) -> bytes:
    full = url + ("?" + urllib.parse.urlencode(params) if params else "")
    request = urllib.request.Request(full, headers=dict(headers))
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body: bytes = response.read()
    return body


def _get(
    http_get: HttpGet, url: str, params: Mapping[str, str], headers: Mapping[str, str]
) -> bytes:
    """One request; transport failures become SourceUnreachableError, refusals FilingSourceError."""
    try:
        return http_get(url, params, headers)
    except urllib.error.HTTPError as exc:
        if exc.code >= 500 or exc.code == 429:
            raise SourceUnreachableError(f"HTTP {exc.code} from {url}") from exc
        raise FilingSourceError(f"HTTP {exc.code} from {url}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        # http.client.IncompleteRead (the connection closed mid-answer) is not an OSError.
        raise SourceUnreachableError(f"{type(exc).__name__}: {exc}") from exc


# ── text of a filing ─────────────────────────────────────────────────────────────────────────

_TAGS = re.compile(r"<[^>]+>")
_SPACES = re.compile(r"[ \t\r\f\v\xa0]+")
_BLANK_LINES = re.compile(r"\n\s*\n+")
_BLOCKS = re.compile(r"(?i)<\s*(br|/p|/div|/tr|/li|/h[1-6]|/title|p|tr|div)\b[^>]*>")
_CELLS = re.compile(r"(?i)<\s*/\s*(td|th|te|tu)\s*>")  # a closing cell tag
_SCRIPTS = re.compile(r"(?is)<\s*(script|style)\b.*?<\s*/\s*\1\s*>")


def plain_text(markup: str) -> str:
    """Markup (HTML, DART's XML) -> plain lines: blocks and table rows end lines, cells are
    separated by ' | ', entities decoded, runs of spaces and blank lines collapsed."""
    text = _SCRIPTS.sub(" ", markup)
    text = _BLOCKS.sub("\n", text)
    text = _CELLS.sub(" | ", text)
    text = html.unescape(_TAGS.sub(" ", text))
    lines = [_SPACES.sub(" ", line).strip(" |") for line in text.split("\n")]
    return _BLANK_LINES.sub("\n", "\n".join(line for line in lines if line)).strip()


# ── DART ─────────────────────────────────────────────────────────────────────────────────────


def _dart_status(body: bytes) -> tuple[str, str]:
    """(status, message) of a DART error page (XML or JSON); ('', text) when unreadable."""
    text = body.decode("utf-8", "replace").strip()
    if text.startswith("{"):
        try:
            data = json.loads(text)
        except ValueError:
            return "", text[:200]
        return str(data.get("status", "")), str(data.get("message", ""))
    try:
        root = ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return "", text[:200]
    return (root.findtext("status") or "").strip(), (root.findtext("message") or "").strip()


def _dart_raise(status: str, message: str) -> None:
    detail = f"DART {status or '?'}: {message}".strip()
    if status in DART_MAINTENANCE:
        raise SourceMaintenanceError(detail)
    if status in DART_STALE:
        raise SourceUnreachableError(detail)
    raise FilingSourceError(detail)


_DART_PREFIX = re.compile(r"^\s*\[[^\]]*\]\s*")


def _yyyymmdd(text: str) -> date:
    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


class DartFilingSource:
    name = "dart"

    def __init__(
        self,
        api_key: str | None,
        http_get: HttpGet | None = None,
        pause_s: float = 0.2,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.api_key = api_key
        self.http_get = http_get or urllib_get
        self.pause_s = pause_s
        self.sleep = sleep or _time.sleep
        self._corp_codes: dict[str, str] | None = None

    def _key(self) -> str:
        if not self.api_key:
            raise SourceNoKeyError("DART_API_KEY is not set")
        return self.api_key

    def corp_codes(self) -> dict[str, str]:
        """Stock code -> DART corp_code (downloaded once per process)."""
        if self._corp_codes is not None:
            return self._corp_codes
        body = _get(self.http_get, f"{DART_BASE}/corpCode.xml", {"crtfc_key": self._key()}, {})
        if not body.startswith(b"PK"):
            _dart_raise(*_dart_status(body))
        try:
            archive = zipfile.ZipFile(io.BytesIO(body))
            root = ElementTree.fromstring(archive.read(archive.namelist()[0]))
        except (*_CORRUPT, ElementTree.ParseError) as exc:
            raise FilingSourceError(f"DART corpCode.xml: {type(exc).__name__}: {exc}") from exc
        codes: dict[str, str] = {}
        for item in root.iter("list"):
            stock = (item.findtext("stock_code") or "").strip()
            corp = (item.findtext("corp_code") or "").strip()
            if stock and corp:
                codes[stock] = corp
        if not codes:
            raise FilingSourceError("DART corpCode.xml listed no company")
        self._corp_codes = codes
        return codes

    def fetch_filings(self, instrument: Instrument, start: date, end: date) -> list[FilingInfo]:
        key = self._key()
        corp = self.corp_codes().get(instrument.ticker)
        if corp is None:
            raise CompanyNotFoundError(f"DART has no corp_code for {instrument.ticker}")
        out: list[FilingInfo] = []
        page = 1
        while True:
            body = _get(
                self.http_get,
                f"{DART_BASE}/list.json",
                {
                    "crtfc_key": key,
                    "corp_code": corp,
                    "bgn_de": start.strftime("%Y%m%d"),
                    "end_de": end.strftime("%Y%m%d"),
                    "page_no": str(page),
                    "page_count": "100",
                },
                {},
            )
            status, message = _dart_status(body)
            if status not in DART_OK:
                _dart_raise(status, message)
            if status == "013":
                return out
            data: dict[str, Any] = json.loads(body)
            for item in data.get("list") or []:
                name = " ".join(str(item.get("report_nm", "")).split())
                rcept_no = str(item["rcept_no"])
                out.append(
                    FilingInfo(
                        source=self.name,
                        source_ref=rcept_no,
                        form=_DART_PREFIX.sub("", name)[:120] or name,
                        items=None,
                        title=name,
                        filed_on=_yyyymmdd(str(item["rcept_dt"])),
                        url=DART_VIEW.format(rcept_no),
                    )
                )
            if page >= int(data.get("total_page") or 1):
                return out
            page += 1
            self.sleep(self.pause_s)

    def fetch_text(self, filing: FilingInfo) -> str:
        body = _get(
            self.http_get,
            f"{DART_BASE}/document.xml",
            {"crtfc_key": self._key(), "rcept_no": filing.source_ref},
            {},
        )
        if not body.startswith(b"PK"):
            _dart_raise(*_dart_status(body))
        try:
            archive = zipfile.ZipFile(io.BytesIO(body))
            # The main document is the largest member; attachments come with it.
            names = sorted(archive.namelist(), key=lambda n: archive.getinfo(n).file_size)
            raw = archive.read(names[-1])
        except _CORRUPT as exc:  # a corrupt download (audit E2: zlib.error escaped before)
            raise FilingSourceError(
                f"DART document {filing.source_ref}: {type(exc).__name__}: {exc}"
            ) from exc
        for encoding in ("utf-8", "euc-kr"):
            try:
                return plain_text(raw.decode(encoding))
            except UnicodeDecodeError:
                continue
        return plain_text(raw.decode("utf-8", "replace"))


# ── EDGAR ────────────────────────────────────────────────────────────────────────────────────

_DOCUMENT = re.compile(r"(?is)<DOCUMENT>(.*?)</DOCUMENT>")
_DOC_TYPE = re.compile(r"(?im)^\s*<TYPE>\s*([^\s<]+)")
_DOC_TEXT = re.compile(r"(?is)<TEXT>(.*?)</TEXT>")
EDGAR_FORMS = ("8-K", "8-K/A", "6-K", "6-K/A")
_EDGAR_FOLDER = re.compile(r"^(https://www\.sec\.gov/Archives/edgar/data/\d+/\d+)")


class EdgarFilingSource:
    name = "edgar"

    def __init__(
        self,
        user_agent: str,
        http_get: HttpGet | None = None,
        pause_s: float = 0.15,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self.headers = {"User-Agent": user_agent, "Accept-Encoding": "identity"}
        self.http_get = http_get or urllib_get
        self.pause_s = pause_s
        self.sleep = sleep or _time.sleep
        self._ciks: dict[str, int] | None = None

    def _json(self, url: str) -> Any:
        body = _get(self.http_get, url, {}, self.headers)
        try:
            return json.loads(body)
        except ValueError as exc:
            raise FilingSourceError(f"EDGAR: not JSON from {url}") from exc

    def ciks(self) -> dict[str, int]:
        if self._ciks is None:
            data = self._json(EDGAR_TICKERS)
            self._ciks = {
                str(v["ticker"]).upper(): int(v["cik_str"])
                for v in (data.values() if isinstance(data, dict) else [])
            }
        return self._ciks

    def fetch_filings(self, instrument: Instrument, start: date, end: date) -> list[FilingInfo]:
        cik = self.ciks().get(instrument.ticker.upper())
        if cik is None:
            raise CompanyNotFoundError(f"EDGAR has no CIK for {instrument.ticker}")
        self.sleep(self.pause_s)
        data = self._json(EDGAR_SUBMISSIONS.format(cik))
        try:
            recent: dict[str, list[Any]] = data["filings"]["recent"]
            rows = list(
                zip(
                    recent["form"],
                    recent["filingDate"],
                    recent["accessionNumber"],
                    recent.get("items") or [""] * len(recent["form"]),
                    recent.get("primaryDocument") or [""] * len(recent["form"]),
                    recent.get("primaryDocDescription") or [""] * len(recent["form"]),
                    strict=True,
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FilingSourceError(f"EDGAR submissions of {instrument.ticker}: {exc}") from exc
        out: list[FilingInfo] = []
        for form, filed, accession, items, primary, description in rows:
            filed_on = date.fromisoformat(str(filed))
            if form not in EDGAR_FORMS or not start <= filed_on <= end:
                continue
            folder = EDGAR_ARCHIVE.format(cik, str(accession).replace("-", ""))
            out.append(
                FilingInfo(
                    source=self.name,
                    source_ref=str(accession),
                    form=str(form),
                    items=str(items) or None,
                    title=str(description or f"{form} {items}").strip()[:200],
                    filed_on=filed_on,
                    url=f"{folder}/{primary}" if primary else folder,
                )
            )
        return out

    def fetch_text(self, filing: FilingInfo) -> str:
        """The press release (EX-99.x) of the submission when there is one, else the main
        document, as plain text."""
        if not filing.url:
            raise FilingSourceError(f"EDGAR filing {filing.source_ref} has no address")
        folder = _EDGAR_FOLDER.match(filing.url)
        if folder is None:
            raise FilingSourceError(f"EDGAR filing {filing.source_ref}: odd address {filing.url}")
        body = _get(self.http_get, f"{folder.group(1)}/{filing.source_ref}.txt", {}, self.headers)
        documents = _DOCUMENT.findall(body.decode("utf-8", "replace"))
        if not documents:
            raise FilingSourceError(f"EDGAR submission {filing.source_ref} has no documents")
        typed: list[tuple[str, str]] = []
        for doc in documents:
            kind = _DOC_TYPE.search(doc)
            text = _DOC_TEXT.search(doc)
            typed.append(((kind.group(1) if kind else "").upper(), text.group(1) if text else doc))
        releases = [t for k, t in typed if k.startswith("EX-99")]
        chosen = releases if releases else [typed[0][1]]
        return "\n\n".join(plain_text(t) for t in chosen)
