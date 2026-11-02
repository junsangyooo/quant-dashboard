"""FastAPI 앱. 127.0.0.1에만 묶어 켠다(start.sh).

uvicorn --factory app.main:create_app

환경 값(모두 선택):
- MVP_DATA_DIR: 데이터 폴더(기본 mvp/data)
- MVP_PORT: 포트(기본 8765, Host 검사에 쓴다)
- QUANT_LIVE_TRANSPORT=1: 실제 전송을 켜는 두 열쇠 가운데 하나. 설치기 설정 파일도 있어야
  열린다(transport.py). 없으면 토스 · DART · 텔레그램 · 공인 IP · 시세 전송은 모두 가짜다.

화면은 web/dist(npm run build 결과)를 '/'에서 내준다.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import traceback
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import APP_VERSION_TEXT
from . import strategy as st
from .connect import Connections
from .db import DB, body_format
from .engine_mvp import BacktestError, run_backtest, universe_of, warmup_calendar_days
from .market import INDEX, KST, BarSource, Market, MarketDataError, TossSource, now_kst
from .paper import Paper
from .publicip import IpFetch, PublicIpError, public_ip
from .toss import Transport
from .transport import Transports, build_transports
from .vault import SCRYPT_N, SESSION_S, Vault, VaultError

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"
COOKIE = "qm_session"
AUTO_AT = (16, 30)
log = logging.getLogger("quant-mvp")

PUBLIC_API = {"/api/health", "/api/state", "/api/setup", "/api/login", "/api/recover"}


def _err(message: str, status: int = 400, **extra: Any) -> JSONResponse:
    return JSONResponse({"error": message, **extra}, status_code=status)


async def _body(request: Request) -> dict[str, Any]:
    if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
        raise VaultError("JSON으로 보내 주세요", 415)
    try:
        data = await request.json()
    except ValueError:
        raise VaultError("요청 형식이 맞지 않아요") from None
    if not isinstance(data, dict):
        raise VaultError("요청 형식이 맞지 않아요")
    return data


def _date(text: Any, what: str) -> date:
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        raise VaultError(f"{what} 날짜를 2024-01-31 형식으로 입력해 주세요") from None


def create_app(
    data_dir: Path | str | None = None,
    *,
    bars_source: BarSource | None = None,
    toss_transport: Callable[[], Transport] | None = None,
    ip_fetch: IpFetch | None = None,
    transports: Transports | None = None,
    scrypt_n: int | None = None,
    scheduler: bool = True,
    port: int | None = None,
    now: Callable[[], datetime] = now_kst,
) -> FastAPI:
    data = Path(data_dir or os.environ.get("MVP_DATA_DIR") or ROOT / "data")
    port = port or int(os.environ.get("MVP_PORT") or 8765)
    db = DB(data / "app.db")
    vault = Vault(db, scrypt_n=scrypt_n or SCRYPT_N)
    # 전송은 기본 가짜(T-00). 실제 전송은 transport.build_transports의 두 열쇠가 다 있을 때만.
    if transports is None:
        transports = build_transports()
    if toss_transport is None:
        toss_transport = transports.toss_factory()
    if ip_fetch is None:
        ip_fetch = transports.ip_fetch
    dist = Path(os.environ.get("MVP_WEB_DIST") or DIST)
    conns = Connections(db, vault, toss_transport)
    market = Market(db, bars_source or TossSource(conns.client))
    paper = Paper(db, market, conns, now=now)

    allowed_hosts = {
        f"127.0.0.1:{port}",
        f"localhost:{port}",
        "testserver",
    }
    allowed_origins = {f"http://{h}" for h in allowed_hosts}

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        task = asyncio.create_task(_auto_loop()) if scheduler else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="quant-mvp", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.db = db
    app.state.transports = transports
    app.state.vault = vault
    app.state.connections = conns
    app.state.market = market
    app.state.paper = paper

    # ── 바깥 문 ────────────────────────────────────────────────────────────

    @app.middleware("http")
    async def guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        host = request.headers.get("host", "")
        if host not in allowed_hosts:
            return _err("이 주소로는 열 수 없어요", 403)
        origin = request.headers.get("origin")
        if request.method not in ("GET", "HEAD") and origin and origin not in allowed_origins:
            return _err("다른 사이트에서 온 요청은 받지 않아요", 403)
        path = request.url.path
        if path.startswith("/api/") and path not in PUBLIC_API:
            if not vault.session_ok(request.cookies.get(COOKIE)):
                return _err("다시 로그인해 주세요", 401, need_login=True)
        response = await call_next(request)
        if path.startswith("/api/"):
            response.headers["cache-control"] = "no-store"
        response.headers["x-content-type-options"] = "nosniff"
        response.headers["x-frame-options"] = "DENY"
        response.headers["referrer-policy"] = "no-referrer"
        response.headers["content-security-policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.exception_handler(VaultError)
    async def on_vault(_: Request, exc: VaultError) -> JSONResponse:
        return _err(exc.message, exc.status, **exc.extra)

    @app.exception_handler(st.FormatError)
    async def on_format(_: Request, exc: st.FormatError) -> JSONResponse:
        if exc.kind == "graph":
            return _err(str(exc), 400, kind="graph", title=st.BAD_GRAPH, detail=exc.detail)
        return _err(str(exc), 400, kind=exc.kind)

    @app.exception_handler(MarketDataError)
    async def on_market(_: Request, exc: MarketDataError) -> JSONResponse:
        if exc.kind == "symbol":
            return _err(exc.message, 400, kind="symbol", symbols=exc.symbols)
        return _err(exc.message, 502, kind="market")

    @app.exception_handler(BacktestError)
    async def on_bt(_: Request, exc: BacktestError) -> JSONResponse:
        return _err(exc.message, 400)

    @app.exception_handler(RequestValidationError)
    async def on_validation(_: Request, __: RequestValidationError) -> JSONResponse:
        return _err("요청 형식이 맞지 않아요", 400)  # 받은 값을 되돌려 보내지 않는다

    @app.exception_handler(StarletteHTTPException)
    async def on_http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _err("없는 주소예요" if exc.status_code == 404 else "요청을 받지 못했어요", exc.status_code)

    @app.exception_handler(Exception)
    async def on_any(_: Request, exc: Exception) -> JSONResponse:
        # 예외 글에는 무엇이 들었는지 모르니 종류와 위치만 남긴다
        where = traceback.extract_tb(exc.__traceback__)[-1:] if exc.__traceback__ else []
        log.error("unhandled %s at %s", type(exc).__name__, [f"{f.filename}:{f.lineno}" for f in where])
        return _err("앱 안에서 문제가 생겼어요 · 다시 해 주세요", 500)

    def _set_cookie(resp: Response, token: str) -> None:
        resp.set_cookie(
            COOKIE, token, max_age=SESSION_S, httponly=True, samesite="strict", path="/"
        )

    # ── 처음 열기 · 로그인 ───────────────────────────────────────────────────

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"app": "quant-mvp", "version": APP_VERSION_TEXT}

    @app.get("/api/state")
    def state(request: Request) -> dict[str, Any]:
        return {
            "setup": vault.is_setup(),
            "logged_in": vault.session_ok(request.cookies.get(COOKIE)),
            "unlocked": vault.unlocked,
            "locked_for": vault.locked_for(),
            "restarted": vault.is_setup() and not vault.opened_since_start,
            "version": APP_VERSION_TEXT,
        }

    @app.post("/api/setup")
    async def setup(request: Request) -> Response:
        b = await _body(request)
        token, code = vault.setup(
            str(b.get("password") or ""),
            str(b.get("password2") or ""),
            adult=b.get("adult") is True,
            terms=b.get("terms") is True,
        )
        resp = JSONResponse({"ok": True, "recovery_code": code})
        _set_cookie(resp, token)
        return resp

    @app.post("/api/login")
    async def login(request: Request) -> Response:
        b = await _body(request)
        token = await asyncio.to_thread(vault.login, str(b.get("password") or ""))
        resp = JSONResponse({"ok": True})
        _set_cookie(resp, token)
        return resp

    @app.post("/api/recover")
    async def recover(request: Request) -> Response:
        b = await _body(request)
        token, code = await asyncio.to_thread(
            vault.recover,
            str(b.get("recovery_code") or ""),
            str(b.get("password") or ""),
            str(b.get("password2") or ""),
        )
        resp = JSONResponse({"ok": True, "recovery_code": code})
        _set_cookie(resp, token)
        return resp

    @app.get("/api/about")
    def about() -> dict[str, Any]:
        row = db.one("SELECT terms_at, created_at FROM owner WHERE id=1")
        return {
            "version": APP_VERSION_TEXT,
            "terms_at": row["terms_at"] if row else None,
            "created_at": row["created_at"] if row else None,
            "address": f"127.0.0.1:{port}",
        }

    @app.post("/api/password")
    async def password_change(request: Request) -> dict[str, Any]:
        b = await _body(request)
        await asyncio.to_thread(
            vault.change_password,
            str(b.get("current") or ""),
            str(b.get("password") or ""),
            str(b.get("password2") or ""),
        )
        return {"ok": True}

    @app.post("/api/public-ip")
    async def public_ip_view() -> dict[str, Any]:
        # 누를 때만 부른다. 저장하지 않는다.
        try:
            ip = await asyncio.to_thread(public_ip, ip_fetch)
        except PublicIpError as exc:
            raise VaultError(exc.message, 502) from None
        return {"ip": ip}

    @app.post("/api/logout")
    def logout(request: Request) -> Response:
        # 잠그기 = 앱 전체 잠금: 모든 세션을 끝내고 데이터 키를 메모리에서 지운다.
        # 자동 확인은 데이터 키가 풀려 있을 때 토스에서 일봉을 받는다.
        vault.lock_now()
        conns.drop()
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        return resp

    # ── 설정 › 연결 ────────────────────────────────────────────────────────

    @app.get("/api/connect")
    def connect_view() -> dict[str, Any]:
        return conns.view()

    @app.put("/api/connect/toss")
    async def toss_save(request: Request) -> dict[str, Any]:
        b = await _body(request)
        conns.save_toss(
            str(b.get("client_id") or ""),
            str(b.get("client_secret") or ""),
            str(b.get("account_no") or "") or None,
        )
        return conns.view()

    @app.delete("/api/connect/toss")
    def toss_delete() -> dict[str, Any]:
        conns.delete_toss()
        return conns.view()

    @app.post("/api/connect/toss/check")
    async def toss_check() -> dict[str, Any]:
        return {"result": await asyncio.to_thread(conns.check), **conns.view()}

    @app.put("/api/connect/dart")
    async def dart_save(request: Request) -> dict[str, Any]:
        b = await _body(request)
        conns.save_dart(str(b.get("key") or ""))
        return conns.view()

    @app.delete("/api/connect/dart")
    def dart_delete() -> dict[str, Any]:
        conns.delete_dart()
        return conns.view()

    # ── 전략 ────────────────────────────────────────────────────────────────

    def _strategy(sid: int) -> Any:
        row = db.one("SELECT * FROM strategies WHERE id=?", (sid,))
        if row is None:
            raise VaultError("그 전략이 없어요", 404)
        return row

    def _running_version() -> tuple[int, int] | None:
        """(전략 id, 버전 번호) — 실행 중인 모의투자가 있으면."""
        running = paper.active()
        if running is None:
            return None
        rv = db.one("SELECT strategy_id, no FROM versions WHERE id=?", (running["version_id"],))
        return (int(rv["strategy_id"]), int(rv["no"])) if rv else None

    def _version_row(v: Any, running: tuple[int, int] | None) -> dict[str, Any]:
        body = json.loads(v["body"])
        return {
            "id": v["id"],
            "no": v["no"],
            "problems": v["problems"],
            "blanks": st.count_blanks(body),
            "created_at": v["created_at"],
            "paper": running is not None and running == (int(v["strategy_id"]), int(v["no"])),
        }

    def _versions(sid: int) -> list[dict[str, Any]]:
        running = _running_version()
        return [
            _version_row(r, running)
            for r in db.all("SELECT * FROM versions WHERE strategy_id=? ORDER BY no DESC", (sid,))
        ]

    def _save_version(sid: int, body: dict[str, Any]) -> dict[str, Any]:
        problems = st.validate(body)
        with db.tx():
            row = db.one("SELECT COALESCE(MAX(no),0)+1 AS n FROM versions WHERE strategy_id=?", (sid,))
            no = int(row["n"])
            text = json.dumps(body, ensure_ascii=False)
            vid = db.run(
                "INSERT INTO versions(strategy_id,no,body,problems,created_at,format) VALUES(?,?,?,?,?,?)",
                (sid, no, text, len(problems), _now(), body_format(text)),
            )
            db.run(
                "UPDATE strategies SET name=?, template=? WHERE id=?",
                (body["name"], st.mode_of(body) or "", sid),
            )
        return {"version_id": vid, "no": no, "problems": problems}

    def _unique_name(name: str, skip: int | None = None) -> tuple[str, bool]:
        """이름이 겹치면 끝에 ' (2)'처럼 숫자를 더한다(붙여 넣기 · 예시 복사 · 새 전략 모두)."""
        taken = {r["name"] for r in db.all("SELECT id, name FROM strategies") if r["id"] != skip}
        if name not in taken:
            return name, False
        n = 2
        while True:
            tail = f" ({n})"
            cand = name[: 60 - len(tail)] + tail
            if cand not in taken:
                return cand, True
            n += 1

    def _steps() -> dict[str, Any]:
        """시작하기 4단계: API 키 연결(선택) · 전략 만들기 · 백테스트 · 모의투자 시작."""
        toss = conns.view()["toss"]
        last = toss.get("last_check") or {}
        return {
            "connected": bool(toss.get("saved")) and bool(last.get("ok")),
            "strategies": int(db.one("SELECT COUNT(*) AS n FROM strategies")["n"]),
            "backtested": db.get_meta("steps.backtested") == "1",
            "papered": db.one("SELECT 1 FROM paper_runs LIMIT 1") is not None,
            "latest_strategy": (db.one("SELECT id FROM strategies ORDER BY id DESC LIMIT 1") or {"id": None})["id"],
        }

    def _body_view(body: dict[str, Any]) -> dict[str, Any]:
        a = st.analyze(body)
        return {"body": body, "analysis": a, "mode": a["mode"], "mode_name": st.mode_name(a["mode"]),
                "summary": st.summary(body)}

    @app.get("/api/catalog")
    def catalog() -> dict[str, Any]:
        return st.catalog()

    @app.get("/api/examples")
    def examples() -> dict[str, Any]:
        return {"examples": [st.example_view(e["id"]) for e in st.EXAMPLES]}

    @app.get("/api/examples/{eid}")
    def example(eid: str) -> dict[str, Any]:
        if eid not in st.EXAMPLE_BY_ID:
            raise VaultError("그 예시가 없어요", 404)
        return st.example_view(eid)

    @app.get("/api/strategies")
    def strategies() -> dict[str, Any]:
        out = []
        running = _running_version()
        for r in db.all("SELECT * FROM strategies ORDER BY id DESC"):
            v = db.one(
                "SELECT * FROM versions WHERE strategy_id=? ORDER BY no DESC LIMIT 1", (r["id"],)
            )
            body = json.loads(v["body"]) if v else None
            paper_here = running is not None and running[0] == r["id"]
            summ = st.summary(body) if body else None
            out.append(
                {
                    "id": r["id"],
                    "name": r["name"],
                    "mode": summ["mode"] if summ else None,
                    "mode_name": summ["mode_name"] if summ else "",
                    "source": json.loads(r["source"]) if r["source"] else None,
                    "latest": _version_row(v, running) if v else None,
                    "summary": summ,
                    "paper": {"version_no": running[1]} if paper_here and running else None,
                }
            )
        return {"strategies": out, "steps": _steps()}

    @app.post("/api/strategies")
    async def strategy_new(request: Request) -> dict[str, Any]:
        """새 전략: 편집에서 처음 저장할 때 만든다(저장 전에는 전략도 버전도 없다). 이름이 겹치면 ' (2)'."""
        b = await _body(request)
        body = st.normalize(b.get("body"))
        body.pop("source", None)
        body["name"] = _unique_name(body["name"])[0]
        sid = db.run(
            "INSERT INTO strategies(name,template,source,created_at) VALUES(?,?,?,?)",
            (body["name"], st.mode_of(body) or "", None, _now()),
        )
        saved = _save_version(sid, body)
        return {"id": sid, "name": body["name"], **saved}

    @app.get("/api/strategies/{sid}")
    def strategy_get(sid: int) -> dict[str, Any]:
        r = _strategy(sid)
        v = db.one(
            "SELECT * FROM versions WHERE strategy_id=? ORDER BY no DESC LIMIT 1", (sid,)
        )
        body = json.loads(v["body"])
        if "graph" not in body:
            body = {"name": body.get("name") or r["name"], "graph": st.as_graph(body)}
        running = _running_version()
        run_here = None
        if running is not None and running[0] == sid:
            active = paper.active()
            home_now = paper.home()
            run_here = {
                "id": active["id"],
                "version_no": running[1],
                "started_at": active["started_at"],
                "first_d": home_now["curve"][0][0] if home_now.get("curve") else None,
                "cash0": home_now["cash0"],
                "total": home_now["total"],
                "pnl": home_now["pnl"],
                "pnl_pct": home_now["pnl_pct"],
                "last_d": home_now["curve"][-1][0] if home_now.get("curve") else None,
                "held": len(home_now["holdings"]),
            }
        past = [x for x in paper.runs(sid) if x["status"] == "ended"]
        used = db.one(
            "SELECT 1 FROM paper_runs r JOIN versions v ON v.id=r.version_id WHERE v.strategy_id=?",
            (sid,),
        )
        view = _body_view(body)
        return {
            "id": sid,
            "name": r["name"],
            **{k: view[k] for k in ("mode", "mode_name", "analysis", "summary")},
            "source": json.loads(r["source"]) if r["source"] else None,
            "version": {
                **_version_row(v, running),
                "problems": view["analysis"]["problems"],
                "blanks_by_slot": st.blanks_by_slot(body),
            },
            "body": body,
            "versions": _versions(sid),
            "paper": run_here,
            "past_runs": past,
            "deletable": used is None,
        }

    @app.post("/api/strategies/{sid}/versions")
    async def strategy_save(sid: int, request: Request) -> dict[str, Any]:
        _strategy(sid)
        b = await _body(request)
        body = st.normalize(b.get("body"))
        body.pop("source", None)
        body["name"] = _unique_name(body["name"], skip=sid)[0]
        saved = _save_version(sid, body)
        return {**saved, "name": body["name"], "versions": _versions(sid)}

    @app.post("/api/strategies/{sid}/check")
    async def strategy_check(sid: int, request: Request) -> dict[str, Any]:
        """저장하지 않고 검사만(편집 화면의 상태 · 문제 목록 · 경로). sid=0은 아직 저장하지 않은 새 전략."""
        if sid != 0:
            _strategy(sid)
        b = await _body(request)
        body = st.normalize(b.get("body"))
        view = _body_view(body)
        return {"analysis": view["analysis"], "mode": view["mode"], "mode_name": view["mode_name"],
                "problems": view["analysis"]["problems"], "blanks_by_slot": st.blanks_by_slot(body)}

    @app.get("/api/versions/{vid}")
    def version_get(vid: int) -> dict[str, Any]:
        v = db.one("SELECT * FROM versions WHERE id=?", (vid,))
        if v is None:
            raise VaultError("그 버전이 없어요", 404)
        body = json.loads(v["body"])
        view = _body_view(body)
        return {
            "id": vid,
            "strategy_id": v["strategy_id"],
            "no": v["no"],
            "body": body,
            "problems": view["analysis"]["problems"],
            "analysis": view["analysis"],
            "mode_name": view["mode_name"],
        }

    @app.get("/api/strategies/{sid}/copytext")
    def strategy_copy(sid: int) -> dict[str, Any]:
        r = _strategy(sid)
        v = db.one("SELECT no, body FROM versions WHERE strategy_id=? ORDER BY no DESC LIMIT 1", (sid,))
        body = json.loads(v["body"])
        body["name"] = r["name"]
        source = {"from": "이 앱", "id": f"strategy-{sid}", "title": r["name"], "version": str(v["no"])}
        return {"text": st.to_copy_text(body, source)}

    def _source_line(source: dict[str, Any]) -> str:
        title = source.get("title") or ""
        ver = source.get("version")
        where = source.get("from") or "알 수 없음"
        if title and ver:
            return f"{title} · 버전 {ver}에서 복사"
        if title:
            return f"{title} · {where}에서 복사"
        return f"{where}에서 복사"

    @app.post("/api/import/preview")
    async def import_preview(request: Request) -> dict[str, Any]:
        b = await _body(request)
        body, notes = st.parse_copy_text(str(b.get("text") or ""))
        source = body.get("source") or {"from": "알 수 없음"}
        name, renamed = _unique_name(body["name"])
        view = _body_view({"name": body["name"], "graph": body["graph"]})
        return {
            "name": name,
            "renamed": renamed,
            "original_name": body["name"],
            "mode": view["mode"],
            "mode_name": view["mode_name"],
            "source": source,
            "source_line": _source_line(source),
            "body": {"name": name, "graph": body["graph"]},
            "analysis": view["analysis"],
            "summary": view["summary"],
            "blanks": st.count_blanks(body),
            "notes": notes,
        }

    @app.post("/api/import/accept")
    async def import_accept(request: Request) -> dict[str, Any]:
        b = await _body(request)
        body, _ = st.parse_copy_text(str(b.get("text") or ""))
        source = body.pop("source", None) or {"from": "알 수 없음"}
        wanted = str(b.get("name") or "").strip()[:60]
        body["name"] = _unique_name(wanted or body["name"])[0]
        sid = db.run(
            "INSERT INTO strategies(name,template,source,created_at) VALUES(?,?,?,?)",
            (body["name"], st.mode_of(body) or "", json.dumps(source, ensure_ascii=False), _now()),
        )
        saved = _save_version(sid, body)
        return {"id": sid, "name": body["name"], **saved}

    @app.delete("/api/strategies/{sid}")
    def strategy_delete(sid: int) -> dict[str, Any]:
        _strategy(sid)
        running = _running_version()
        if running is not None and running[0] == sid:
            raise VaultError("모의투자 중인 전략은 삭제할 수 없어요 · 먼저 모의투자를 끝내 주세요")
        used = db.one(
            "SELECT 1 FROM paper_runs r JOIN versions v ON v.id=r.version_id WHERE v.strategy_id=?",
            (sid,),
        )
        if used:
            raise VaultError("모의투자 기록이 있는 전략은 삭제할 수 없어요")
        with db.tx():
            db.run("DELETE FROM versions WHERE strategy_id=?", (sid,))
            db.run("DELETE FROM strategies WHERE id=?", (sid,))
        return {"ok": True}

    # ── 백테스트 ────────────────────────────────────────────────────────────

    @app.post("/api/backtest")
    async def backtest(request: Request) -> dict[str, Any]:
        b = await _body(request)
        return await asyncio.to_thread(_backtest, b)

    def _backtest(b: dict[str, Any]) -> dict[str, Any]:
        """버전(version_id) 또는 예시(example)로 백테스트. 결과는 남기지 않는다."""
        example = b.get("example")
        v = None
        if example is not None:
            if example not in st.EXAMPLE_BY_ID:
                raise VaultError("그 예시가 없어요", 404)
            body = st.example_body(str(example))
        else:
            try:
                vid = int(b.get("version_id"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                raise VaultError("전략 버전을 골라 주세요") from None
            v = db.one("SELECT * FROM versions WHERE id=?", (vid,))
            if v is None:
                raise VaultError("그 버전이 없어요", 404)
            body = json.loads(v["body"])
        problems = st.validate(body)
        if problems:
            raise VaultError(
                f"문제가 {len(problems)}개 있어요 · 편집에서 먼저 수정해 주세요",
                400,
                problems=problems,
            )
        start = _date(b.get("start"), "시작")
        end = _date(b.get("end"), "끝")
        today = now().date()
        if end > today:
            end = today
        if start >= end:
            raise VaultError("시작 날짜가 끝 날짜보다 앞이어야 해요")
        if start < date(2000, 1, 1):
            raise VaultError("2000년부터 볼 수 있어요")
        try:
            cash = float(b.get("cash"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise VaultError("시작 금액을 숫자로 입력해 주세요") from None
        if not (100_000 <= cash <= 10_000_000_000):
            raise VaultError("시작 금액은 10만 원 ~ 100억 원 사이로 입력해 주세요")
        warm = start - timedelta(days=warmup_calendar_days(body))
        bars = market.many(universe_of(body), warm, end)
        try:
            bench = market.bars(INDEX, start - timedelta(days=10), end)
        except MarketDataError:
            bench = []
        result = run_backtest(body, bars, bench, start.isoformat(), end.isoformat(), cash)
        names = {s: st.stock_name(s) for s in universe_of(body)}
        for t in result["trades"]:
            t["name"] = names.get(t["sym"], t["sym"])
        for o in result["open"]:
            o["name"] = names.get(o["sym"], o["sym"])
        if v is not None:
            result["version"] = {"id": v["id"], "no": v["no"], "strategy_id": v["strategy_id"]}
            db.set_meta("steps.backtested", "1")
        else:
            result["version"] = None
            result["example"] = {"id": example, "name": st.EXAMPLE_BY_ID[str(example)]["name"]}
        result["costs_rule"] = "수수료 0.015% · 매도 세금 0.18% 반영"
        result["data_source"] = "토스 일봉(수정주가)"
        result["ran_at"] = _now()
        result["bench_name"] = "코스피" if bench else None
        return result

    # ── 모의투자 ────────────────────────────────────────────────────────────

    @app.post("/api/paper/start")
    async def paper_start(request: Request) -> dict[str, Any]:
        b = await _body(request)
        try:
            vid = int(b.get("version_id"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise VaultError("전략 버전을 골라 주세요") from None
        return await asyncio.to_thread(paper.start, vid, b.get("cash"))

    @app.get("/api/paper/preview")
    async def paper_preview(version_id: int) -> dict[str, Any]:
        return await asyncio.to_thread(paper.preview, version_id)

    @app.post("/api/paper/judge")
    async def paper_judge() -> dict[str, Any]:
        res = await asyncio.to_thread(paper.judge, "button")
        res["at"] = now().astimezone(timezone.utc).isoformat(timespec="seconds")
        return res

    @app.post("/api/paper/stop")
    def paper_stop() -> dict[str, Any]:
        return {"ok": True, "run": paper.stop()}

    def _auto() -> dict[str, Any]:
        fill = db.get_meta("auto.last_fill")
        return {
            "at": "평일 16:30",
            "last": db.get_meta("auto.last"),
            "last_result": db.get_meta("auto.last_result"),
            "last_fill": json.loads(fill) if fill else None,
            "now": now().astimezone(KST).isoformat(timespec="seconds"),
        }

    @app.get("/api/home")
    async def home() -> dict[str, Any]:
        out = await asyncio.to_thread(paper.home)
        out["auto"] = _auto()
        out["steps"] = _steps()
        return out

    @app.get("/api/plan")
    def plan() -> dict[str, Any]:
        out = paper.plan()
        out["auto"] = _auto()
        return out

    @app.get("/api/paper/runs")
    def paper_runs(strategy_id: int | None = None) -> dict[str, Any]:
        return {"runs": paper.runs(strategy_id), "auto": _auto()}

    @app.get("/api/paper/runs/{rid}")
    def paper_run(rid: int) -> dict[str, Any]:
        return paper.run_view(rid)

    @app.get("/api/history")
    def history() -> dict[str, Any]:
        return paper.history()

    # ── 화면(web/dist) ──────────────────────────────────────────────────────

    def _index() -> Response:
        index = dist / "index.html"
        if not index.is_file():
            return _err("화면 파일이 없어요 · start.sh로 다시 켜 주세요", 503)
        return FileResponse(index, headers={"cache-control": "no-store"})

    @app.get("/{path:path}")
    def web(path: str) -> Response:
        if path.startswith("api/") or path == "api":
            return _err("없는 주소예요", 404)
        if path:
            base = dist.resolve()
            target = (base / path).resolve()
            if target.is_file() and target.is_relative_to(base):
                cache = "public, max-age=31536000, immutable" if path.startswith("assets/") else "no-cache"
                return FileResponse(target, headers={"cache-control": cache})
        return _index()

    # ── 평일 16:30 자동으로 한 번 ──────────────────────────────────────────

    async def _auto_loop() -> None:
        while True:
            try:
                # 세션이 만료됐으면 요청이 없어도 30초 안에 데이터 키와 연결 객체를 지운다
                _ = vault.unlocked
                await asyncio.to_thread(auto_tick)
            except Exception as exc:  # 루프는 멈추지 않는다
                log.error("auto tick failed: %s", type(exc).__name__)
            await asyncio.sleep(30)

    def auto_tick() -> str | None:
        local = now().astimezone(KST)
        if local.weekday() >= 5 or (local.hour, local.minute) < AUTO_AT:
            return None
        today = local.date().isoformat()
        if db.get_meta("auto.last") == today:
            return None
        db.set_meta("auto.last", today)
        # 자동 확인이 돈 날(앱이 켜져 있던 날). '앱이 꺼져 있던 날도 채웠어요' 안내를 가르는 데 쓴다.
        ran_days: list[str] = json.loads(db.get_meta("auto.ran_days") or "[]")
        db.set_meta("auto.ran_days", json.dumps((ran_days + [today])[-60:]))
        if paper.active() is None:
            db.set_meta("auto.last_result", "실행 중인 모의투자가 없어 건너뛰었어요")
            return "skip"
        run_id = int(paper.active()["id"])
        try:
            res = paper.judge("auto")
            db.set_meta("auto.last_result", res["message"])
            db.set_meta(
                "auto.last_fill",
                json.dumps(
                    {
                        "run_id": run_id,
                        "new_days": res["new_days"],
                        "from": res["first"],
                        "to": res["judged"],
                        # 이어 채운 날 가운데 앱이 꺼져 있던 날(그날 16:30 자동 확인이 돌지 않은 날)
                        "off_days": [d for d in res.get("days", []) if d < today and d not in ran_days],
                        "at": now().astimezone(timezone.utc).isoformat(timespec="seconds"),
                    },
                    ensure_ascii=False,
                ),
            )
        except MarketDataError as exc:
            db.set_meta("auto.last_result", exc.message)
        except VaultError as exc:
            db.set_meta("auto.last_result", exc.message)
        return "ran"

    app.state.auto_tick = auto_tick
    return app


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

