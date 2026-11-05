"""DART OpenAPI: 재무 · 공시 · 주식 총수 · 배당을 받아 담아 둬요(TASKS T-12 · SPEC 11-1 순서 3 · DATA-CATALOG 2-2).

- 요청 · 응답 꼴은 어댑터 `adapters/dart.py`(`DartClient` · 전송은 `transport.py`의 문 · 기본 가짜 · T-00)예요. 이 파일은 받은 것을
  담아 두는 큐 · 하루 한도 · 읽기(`Disclosures` 포트 · `ports.py`)예요(저장은 P1-07에서 `store/`로).
- 받는 순서(큐): ① corpCode(종목 ↔ 회사 번호) → ② 재무 주요계정 `fnlttMultiAcnt`(100개 회사씩 · 2015년~ ·
  1분기 · 반기 · 3분기 · 사업) → ③ 공시 목록 `list.json`(회사마다) → ④ 주식 총수 `stockTotqySttus`(사업 · 반기) ·
  배당 `alotMatter`(사업). ①~③은 첫날 안에, ④는 회사 × 연도 × 보고서라 약 4일 걸려요(SPEC 3 · V2-09).
- 하루 20,000건(개인 키 · 83종 합산): 오늘 쓴 수를 세어 넘기 전에 멈추고 '내일 이어서 받아요'. DART가 020을
  돌려줘도 같아요. 다음 날 같은 큐를 이어서 받아요.
- 재무 값 · 공시는 **접수일 다음 거래일**부터 써요(R-J9). 재무는 연결(CFS) 우선, 없으면 별도(OFS).
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from .adapters.dart import MULTI_MAX, DartClient, DartError
from .db import DB
from .domain.markets.kr import KST

DAILY_LIMIT = 20_000
FIRST_YEAR = 2015  # DART 재무는 2015년 보고서부터
REPORTS = ("11013", "11012", "11014", "11011")  # 1분기 · 반기 · 3분기 · 사업
SHARE_REPORTS = ("11012", "11011")  # 주식 총수는 반기 · 사업만(SPEC 3 · 약 4일)
ACCOUNTS = ("매출액", "영업이익", "당기순이익", "자본총계", "부채총계", "자산총계")
log = logging.getLogger("quant-dart")

# 공시 목록 보고서명 → 공시 종류(ENGINE-RULES 11-3 `disclosure` · kind)
DISCLOSURE_KINDS: list[tuple[str, str]] = [
    ("buyback", r"자기주식\s*취득\s*결정"),
    ("treasury_sale", r"자기주식\s*처분\s*결정"),
    ("rights_issue", r"유상\s*증자\s*결정"),
    ("bonus_issue", r"무상\s*증자\s*결정"),
    ("capital_reduction", r"감자\s*결정"),
    ("cb", r"전환사채권?\s*발행\s*결정"),
    ("bw", r"신주인수권부사채권?\s*발행\s*결정"),
    ("merger", r"합병\s*결정"),
    ("split", r"(?<!주식)분할\s*결정"),
    ("business_transfer", r"영업\s*양(수|도)\s*결정"),
    ("lawsuit", r"소송\s*등의\s*제기"),
    ("default", r"부도\s*발생"),
    ("rehabilitation", r"회생\s*절차"),
    ("dissolution", r"해산\s*사유"),
    ("earnings", r"^(\[[^\]]*\])?\s*(사업|반기|분기)보고서"),
]


def disclosure_kind(report_nm: str) -> str | None:
    for kind, pattern in DISCLOSURE_KINDS:
        if re.search(pattern, report_nm):
            return kind
    return None


def rcept_date(rcept_no: str) -> date:
    """접수번호 앞 8자리 = 접수일."""
    return datetime.strptime(rcept_no[:8], "%Y%m%d").date()


def usable_from(received: date, next_open: Callable[[date], date]) -> date:
    """R-J9: 접수일 다음 거래일부터 써요."""
    return next_open(received)


def _amount(text: Any) -> float | None:
    if text is None:
        return None
    s = str(text).replace(",", "").strip()
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ── 저장 · 큐 ────────────────────────────────────────────────────────────────

# 표는 db.py SCHEMA_V2(dart_corp · dart_jobs · dart_quota · dart_fin · dart_disc · dart_shares · dart_div)

PHASE_CORP, PHASE_FIN, PHASE_LIST, PHASE_SLOW = 1, 2, 3, 4


@dataclass(frozen=True)
class Progress:
    state: str  # idle · running · limit · key · done · network
    done: int
    total: int
    fast_done: bool  # 재무 · 공시까지 다 받음(수익성 · 성장성 · 안정성 · 공시를 쓸 수 있음)
    message: str

    @property
    def pct(self) -> int:
        return 0 if self.total == 0 else int(self.done * 100 / self.total)


class DartStore:
    def __init__(self, db: DB, *, today: Callable[[], date] | None = None, daily_limit: int = DAILY_LIMIT) -> None:
        self.db = db
        self.today = today or (lambda: datetime.now(KST).date())
        self.daily_limit = daily_limit

    # 하루 한도 ─────────────────────────────────────────────────────────

    def used_today(self) -> int:
        row = self.db.one("SELECT used FROM dart_quota WHERE day=?", (self.today().isoformat(),))
        return int(row["used"]) if row else 0

    def _count(self) -> None:
        if self.used_today() >= self.daily_limit:
            raise DartError("하루 20,000건을 넘었어요 · 내일 이어서 받아요", "limit")
        self.db.run("INSERT INTO dart_quota(day, used) VALUES(?, 1) ON CONFLICT(day) DO UPDATE SET used=used+1",
                    (self.today().isoformat(),))

    def _limit_reached(self) -> None:
        self.db.run("INSERT INTO dart_quota(day, used) VALUES(?, ?) ON CONFLICT(day) DO UPDATE SET used=?",
                    (self.today().isoformat(), self.daily_limit, self.daily_limit))

    # 큐 ────────────────────────────────────────────────────────────────

    def _add(self, phase: int, kind: str, arg: dict[str, Any]) -> None:
        self.db.run("INSERT OR IGNORE INTO dart_jobs(phase, kind, arg) VALUES(?,?,?)",
                    (phase, kind, json.dumps(arg, sort_keys=True)))

    def _plan(self) -> None:
        """회사 목록을 받은 뒤 나머지 일을 큐에 넣어요(이미 있는 일은 그대로)."""
        corps = [r["corp_code"] for r in self.db.all("SELECT corp_code FROM dart_corp ORDER BY stock_code")]
        last_year = self.today().year
        rows: list[tuple[int, str, str]] = []
        for year in range(FIRST_YEAR, last_year + 1):
            for reprt in REPORTS:
                for i in range(0, len(corps), MULTI_MAX):
                    rows.append((PHASE_FIN, "fin", json.dumps({"corps": corps[i:i + MULTI_MAX], "reprt": reprt,
                                                               "year": year}, sort_keys=True)))
        for corp in corps:
            rows.append((PHASE_LIST, "list", json.dumps({"corp": corp}, sort_keys=True)))
        for year in range(FIRST_YEAR, last_year + 1):
            for corp in corps:
                for reprt in SHARE_REPORTS:
                    rows.append((PHASE_SLOW, "shares", json.dumps({"corp": corp, "reprt": reprt, "year": year},
                                                                   sort_keys=True)))
                rows.append((PHASE_SLOW, "div", json.dumps({"corp": corp, "year": year}, sort_keys=True)))
        self.db.many("INSERT OR IGNORE INTO dart_jobs(phase, kind, arg) VALUES(?,?,?)", rows)

    def start(self) -> None:
        self._add(PHASE_CORP, "corp", {})

    def progress(self) -> Progress:
        total = int(self.db.one("SELECT COUNT(*) n FROM dart_jobs")["n"])
        done = int(self.db.one("SELECT COUNT(*) n FROM dart_jobs WHERE done=1")["n"])
        fast_left = int(self.db.one("SELECT COUNT(*) n FROM dart_jobs WHERE done=0 AND phase<?", (PHASE_SLOW,))["n"])
        state = self.db.get_meta("dart.state") or "idle"
        msg = self.db.get_meta("dart.message") or ""
        return Progress(state, done, total, total > 0 and fast_left == 0, msg)

    def _state(self, state: str, message: str = "") -> None:
        self.db.set_meta("dart.state", state)
        self.db.set_meta("dart.message", message)

    def run(self, client: DartClient, *, budget: int | None = None) -> Progress:
        """큐를 앞에서부터 받아요. 한도 · 키 오류면 멈추고, 다음에 부르면 이어서 받아요."""
        client.on_request = self._count
        sent = 0
        try:
            while budget is None or sent < budget:
                job = self.db.one("SELECT * FROM dart_jobs WHERE done=0 ORDER BY phase, id LIMIT 1")
                if job is None:
                    break
                self._do(client, job["kind"], json.loads(job["arg"]))
                self.db.run("UPDATE dart_jobs SET done=1 WHERE id=?", (job["id"],))
                sent += 1
        except DartError as exc:
            if exc.kind == "limit":
                self._limit_reached()
                self._state("limit", "하루 20,000건을 넘었어요 · 내일 이어서 받아요")
            elif exc.kind == "key":
                self._state("key", exc.message)
            else:
                self._state("network", exc.message)
            return self.progress()
        p = self.progress()
        if p.total and p.done == p.total:
            self._state("done", "다 받음")
        elif p.fast_done:
            self._state("running", "가치 조건(시가총액 · PER · PBR · PSR · 배당수익률)은 주식 수를 받는 약 4일 뒤부터 "
                                   "써요 · 수익성 · 성장성 · 안정성 · 공시는 오늘 안에")
        else:
            self._state("running", "")
        return self.progress()

    # 일 하나 ───────────────────────────────────────────────────────────

    def _stock_of(self, corp: str) -> str | None:
        row = self.db.one("SELECT stock_code FROM dart_corp WHERE corp_code=?", (corp,))
        return str(row["stock_code"]) if row else None

    def _do(self, client: DartClient, kind: str, arg: dict[str, Any]) -> None:
        if kind == "corp":
            codes = client.corp_codes()
            self.db.many("INSERT INTO dart_corp(stock_code, corp_code, name) VALUES(?,?,?) "
                         "ON CONFLICT(stock_code) DO UPDATE SET corp_code=excluded.corp_code, name=excluded.name",
                         [(s, c, n) for s, (c, n) in codes.items()])
            self._plan()
        elif kind == "fin":
            self._save_fin(client.financials(arg["corps"], arg["year"], arg["reprt"]), arg["year"], arg["reprt"])
        elif kind == "list":
            self._save_list(client, arg["corp"])
        elif kind == "shares":
            stock = self._stock_of(arg["corp"])
            rows = client.share_count(arg["corp"], arg["year"], arg["reprt"])
            for r in rows:
                if stock and str(r.get("se", "")).startswith(("보통주", "합계")) and r.get("rcept_no"):
                    self.db.run(
                        "INSERT OR REPLACE INTO dart_shares VALUES(?,?,?,?,?,?,?)",
                        (stock, arg["year"], arg["reprt"], _amount(r.get("istc_totqy")), _amount(r.get("tesstk_co")),
                         r["rcept_no"], rcept_date(r["rcept_no"]).isoformat()),
                    )
                    break
        elif kind == "div":
            stock = self._stock_of(arg["corp"])
            for r in client.dividends(arg["corp"], arg["year"]):
                # 행 이름은 확인 전(OPEN-QUESTIONS Q-T5): '주당 현금배당금' + 보통주
                if stock and "주당" in str(r.get("se", "")) and "현금" in str(r.get("se", "")) \
                        and str(r.get("stock_knd", "보통주")).startswith("보통") and r.get("rcept_no"):
                    self.db.run("INSERT OR REPLACE INTO dart_div VALUES(?,?,?,?,?)",
                                (stock, arg["year"], _amount(r.get("thstrm")), r["rcept_no"],
                                 rcept_date(r["rcept_no"]).isoformat()))
                    break

    def _save_fin(self, rows: Iterable[dict[str, Any]], year: int, reprt: str) -> None:
        out = []
        for r in rows:
            stock = str(r.get("stock_code") or "").strip()
            account = str(r.get("account_nm") or "").strip()
            fs = str(r.get("fs_div") or "")
            rno = str(r.get("rcept_no") or "")
            if not stock or account not in ACCOUNTS or fs not in ("CFS", "OFS") or len(rno) < 8:
                continue
            out.append((stock, year, reprt, fs, account, _amount(r.get("thstrm_amount")),
                        _amount(r.get("thstrm_add_amount")), rno, rcept_date(rno).isoformat()))
        if out:
            self.db.many("INSERT OR REPLACE INTO dart_fin VALUES(?,?,?,?,?,?,?,?,?)", out)

    def _save_list(self, client: DartClient, corp: str) -> None:
        stock = self._stock_of(corp)
        start = date(FIRST_YEAR, 1, 1)
        end = self.today()
        page, pages = 1, 1
        while page <= pages:
            rows, pages = client.disclosures(corp, start, end, page)
            out = []
            for r in rows:
                rno = str(r.get("rcept_no") or "")
                if not stock or len(rno) < 8:
                    continue
                name = str(r.get("report_nm") or "")
                rdt = str(r.get("rcept_dt") or rno[:8])
                out.append((rno, stock, f"{rdt[:4]}-{rdt[4:6]}-{rdt[6:8]}", name, disclosure_kind(name)))
            if out:
                self.db.many("INSERT OR REPLACE INTO dart_disc VALUES(?,?,?,?,?)", out)
            page += 1

    # 읽기 (R-J9: 접수일 다음 거래일부터) ───────────────────────────────

    def financial_rows(self, stock: str, on: date, next_open: Callable[[date], date]) -> list[dict[str, Any]]:
        """on 날 확인에 쓸 수 있는 재무 행(연결 우선 · 접수일 다음 거래일부터)."""
        rows = self.db.all("SELECT * FROM dart_fin WHERE stock_code=? ORDER BY year, reprt", (stock,))
        best: dict[tuple[int, str, str], dict[str, Any]] = {}
        for r in rows:
            if usable_from(date.fromisoformat(r["rcept_dt"]), next_open) > on:
                continue
            key = (int(r["year"]), str(r["reprt"]), str(r["account"]))
            if key not in best or (r["fs_div"] == "CFS" and best[key]["fs_div"] != "CFS"):
                best[key] = dict(r)
        return list(best.values())

    def disclosures_on(self, stock: str, on: date, next_open: Callable[[date], date]) -> list[dict[str, Any]]:
        rows = self.db.all("SELECT * FROM dart_disc WHERE stock_code=? ORDER BY rcept_dt", (stock,))
        out = []
        for r in rows:
            frm = usable_from(date.fromisoformat(r["rcept_dt"]), next_open)
            if frm <= on:
                out.append({**dict(r), "usable_from": frm.isoformat()})
        return out
