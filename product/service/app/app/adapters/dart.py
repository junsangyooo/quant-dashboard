"""DART OpenAPI 클라이언트(TASKS T-12 · SPEC 11-1 순서 3 · DATA-CATALOG 2-2): 요청 하나 · 응답 꼴 읽기 · DART 상태 코드 → 오류.

- 꼴의 근거: `vendor/dart-samples/`(공개 개발 가이드의 필드 이름 · 값은 지어냄). 앱은 실행 중에 읽지 않아요.
- 전송: `transport.py`의 문을 지나요(기본 가짜 · 응답 없음 · T-00). 키는 요청 주소에만 넣고 기록하지 않아요.
- 받은 것을 담아 두는 큐 · 하루 한도 · 읽기는 `run/dart.py`(`DartStore` · 표 읽고 쓰기는 `store/dart.py`)예요. 큐는 이 클라이언트를
  `DisclosureSource` 포트로 받아요(`ports.py`).
"""

from __future__ import annotations

import io
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from collections.abc import Callable
from datetime import date
from typing import Any

from ..ports import DisclosureSourceError
from .fake import FakeTransport
from .transport import HttpRequest, Transport, TransportError

BASE = "https://opendart.fss.or.kr/api"
MULTI_MAX = 100  # fnlttMultiAcnt 한 번에 100개 회사
LIST_PAGE = 100

KEY_ERRORS = {"010", "011", "012", "901"}  # 등록 안 된 키 · 사용할 수 없는 키 · 접근할 수 없는 IP · 키 만료
LIMIT_ERROR = "020"
NO_DATA = "013"
# 오류 글(한 곳에 · 어댑터 층은 글 목록 `app/copy/`를 가져오지 않아요 · ARCHITECTURE 2절 · TASKS P1-11)
NO_ANSWER = "DART가 응답하지 않아요"
BAD_SHAPE = "DART 응답 형식이 맞지 않아요"


class DartError(DisclosureSourceError):
    """DART 오류(글 · 종류 key · limit · network · bad). 큐는 포트 쪽 이름(`DisclosureSourceError`)으로 잡아요."""


# ── 클라이언트 ──────────────────────────────────────────────────────────────


class DartClient:
    multi_max = MULTI_MAX  # `DisclosureSource` 약속(큐가 재무 요청을 이 수로 나눠요)

    def __init__(self, api_key: str, *, transport: Transport | None = None, base: str = BASE,
                 on_request: Callable[[], None] | None = None) -> None:
        self._key = api_key
        self.transport: Transport = transport if transport is not None else FakeTransport("dart")
        self.base = base
        self.on_request = on_request or (lambda: None)

    def __repr__(self) -> str:
        return "DartClient(<key hidden>)"

    def _get(self, name: str, params: dict[str, Any]) -> bytes:
        self.on_request()
        query = urllib.parse.urlencode({"crtfc_key": self._key, **{k: v for k, v in params.items() if v is not None}})
        try:
            resp = self.transport(HttpRequest("GET", f"{self.base}/{name}?{query}", {"accept": "*/*"}, None))
        except TransportError:
            raise DartError(NO_ANSWER, "network") from None
        if resp.status != 200:
            raise DartError(NO_ANSWER, "network")
        return resp.body

    def _json(self, name: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        raw = self._get(name, params)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise DartError(BAD_SHAPE, "bad") from None
        return _rows(data, name)

    def corp_codes(self) -> dict[str, tuple[str, str]]:
        """상장 회사: 종목 코드 → (DART 고유번호, 회사 이름)."""
        raw = self._get("corpCode.xml", {})
        if raw[:2] != b"PK":  # 오류는 zip이 아니라 JSON · XML로 와요
            try:
                _rows(json.loads(raw.decode("utf-8")), "corpCode.xml")
            except (UnicodeDecodeError, ValueError):
                _xml_status(raw)
            raise DartError(BAD_SHAPE, "bad")
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as zf:
                xml = zf.read(zf.namelist()[0])
            root = ET.fromstring(xml)
        except (zipfile.BadZipFile, IndexError, ET.ParseError, KeyError):
            raise DartError(BAD_SHAPE, "bad") from None
        out: dict[str, tuple[str, str]] = {}
        for item in root.iter("list"):
            stock = (item.findtext("stock_code") or "").strip()
            corp = (item.findtext("corp_code") or "").strip()
            if re.fullmatch(r"\d{6}", stock) and corp:
                out[stock] = (corp, (item.findtext("corp_name") or "").strip())
        return out

    def financials(self, corp_codes: list[str], year: int, reprt: str) -> list[dict[str, Any]]:
        return self._json("fnlttMultiAcnt.json",
                          {"corp_code": ",".join(corp_codes[:MULTI_MAX]), "bsns_year": str(year), "reprt_code": reprt})

    def disclosures(self, corp_code: str, start: date, end: date, page: int = 1) -> tuple[list[dict[str, Any]], int]:
        raw = self._get("list.json", {"corp_code": corp_code, "bgn_de": start.strftime("%Y%m%d"),
                                      "end_de": end.strftime("%Y%m%d"), "page_no": page, "page_count": LIST_PAGE})
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            raise DartError(BAD_SHAPE, "bad") from None
        rows = _rows(data, "list.json")
        try:
            pages = int(data.get("total_page") or 1) if rows else 0
        except (TypeError, ValueError):
            pages = 1
        return rows, pages

    def share_count(self, corp_code: str, year: int, reprt: str) -> list[dict[str, Any]]:
        return self._json("stockTotqySttus.json", {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": reprt})

    def dividends(self, corp_code: str, year: int) -> list[dict[str, Any]]:
        return self._json("alotMatter.json", {"corp_code": corp_code, "bsns_year": str(year), "reprt_code": "11011"})


def _rows(data: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(data, dict) or "status" not in data:
        raise DartError(BAD_SHAPE, "bad")
    status = str(data["status"])
    if status == "000":
        rows = data.get("list")
        if not isinstance(rows, list):
            raise DartError(BAD_SHAPE, "bad")
        return [r for r in rows if isinstance(r, dict)]
    if status == NO_DATA:
        return []
    if status in KEY_ERRORS:
        raise DartError("DART 인증키가 맞지 않아요 · 인증키를 확인하고 다시 입력해요", "key")
    if status == LIMIT_ERROR:
        raise DartError("하루 20,000건을 넘었어요 · 내일 이어서 받아요", "limit")
    raise DartError("DART에서 데이터를 받지 못했어요", "bad")


def _xml_status(raw: bytes) -> None:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        raise DartError(BAD_SHAPE, "bad") from None
    _rows({"status": root.findtext("status"), "list": []}, "corpCode.xml")
