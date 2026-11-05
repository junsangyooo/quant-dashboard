"""FastAPI 앱. 127.0.0.1에만 묶어 켠다(start.sh).

uvicorn --factory app.main:create_app

환경 값(모두 선택 · `settings.py`가 한 번 읽어 `create_app`이 받아요):
- MVP_DATA_DIR: 데이터 폴더(기본 mvp/data)
- MVP_PORT: 포트(기본 8765, Host 검사에 쓴다)
- MVP_WEB_DIST: 화면 파일 폴더(기본 web/dist)
- QUANT_TS_NAME: 등록한 Tailscale 이름(쉼표로 여럿)
- QUANT_LIVE_TRANSPORT=1: 실제 전송을 켜는 두 열쇠 가운데 하나. 설치기 설정 파일도 있어야
  열린다(adapters/transport.py). 없으면 토스 · DART · 텔레그램 · 공인 IP · 시세 전송은 모두 가짜다.

화면은 web/dist(npm run build 결과)를 '/'에서 내준다.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import re
import secrets
import traceback
from collections.abc import Callable
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import APP_VERSION_TEXT
from . import settings
from .domain import copytext as ct
from . import backtest_v2 as bt2
from .api_v2 import ApiError, make_router
from . import datamgmt as dm
from . import updates
from .live import Live, LiveError
from .live import tick as live_tick
from .schedule import Scheduler
from .dart import DartStore
from .paper_v2 import PaperError, PaperV2
from .ports import Clock, MarketFeed
from .connect import Connections
from .store.db import DB
from .domain.engine import BacktestError as BacktestErrorV2
from .domain.markets.kr import KST, weekday_open
from .market import Market, MarketDataError, TossSource, now_kst
from .adapters.publicip import IpFetch, PublicIpError, public_ip
from .domain.stock_names import stock_name
from .adapters.telegram import TelegramError
from .telegram import Telegram
from .adapters.transport import Transport, Transports, build_transports
from . import vault as vault_mod
from .vault import SCRYPT_N, SESSION_S, Vault, VaultError

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent.parent.parent  # 레포 뿌리(product/service/app → 레포)
DIST = ROOT / "web" / "dist"
COOKIE = "qm_session"
CSRF_COOKIE = "qm_csrf"  # 화면 스크립트가 읽어 X-CSRF-Token 머리글로 되돌려 보내요(두 번 보내기)
CSRF_HEADER = "x-csrf-token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
TS_NAME = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.ts\.net$")


def ts_names_from(text: str | None) -> list[str]:
    """등록한 Tailscale 이름(설치기가 QUANT_TS_NAME으로 넘겨요 · 쉼표로 여럿). 꼴이 맞지 않으면 버려요."""
    out = []
    for part in (text or "").split(","):
        name = part.strip().lower().rstrip(".")
        if name and TS_NAME.match(name):
            out.append(name)
    return out
CONFIRM_HEADER = "x-confirm-token"  # 비밀번호 다시 받기로 받은 1회용 토큰
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
    bars_source: MarketFeed | None = None,
    toss_transport: Callable[[], Transport] | None = None,
    telegram_transport: Transport | None = None,
    ip_fetch: IpFetch | None = None,
    transports: Transports | None = None,
    scrypt_n: int | None = None,
    scheduler: bool = True,
    port: int | None = None,
    now: Clock = now_kst,
    keyfile: Path | str | None | bool = True,
    ts_names: list[str] | None = None,
) -> FastAPI:
    cfg = settings.load()  # 환경 변수 · 실제 전송 설정 파일 자리를 한 번만 읽어요(아래는 이 값만 씀)
    data = Path(data_dir or cfg.data_dir or ROOT / "data")
    port = port or cfg.port
    db = DB(data / "app.db")
    # 컴퓨터 키 파일(T-50): 기본은 고정 경로(vault.KEYFILE_PATH), False면 안 써요. 레포 · 데이터 폴더 안은 거절.
    kf = vault_mod.KEYFILE_PATH if keyfile is True else (None if keyfile is False else keyfile)
    vault = Vault(db, scrypt_n=scrypt_n or SCRYPT_N, keyfile=kf, forbidden_dirs=(data, REPO))
    # 전송은 기본 가짜(T-00). 실제 전송은 transport.build_transports의 두 열쇠가 다 있을 때만.
    if transports is None:
        transports = build_transports(cfg.live_env, cfg.live_config_paths)
    if toss_transport is None:
        toss_transport = transports.toss_factory()
    if ip_fetch is None:
        ip_fetch = transports.ip_fetch
    dist = Path(cfg.web_dist or DIST)
    conns = Connections(db, vault, toss_transport)
    market = Market(db, bars_source or TossSource(conns.client))

    allowed_hosts = {
        f"127.0.0.1:{port}",
        f"localhost:{port}",
        "testserver",
    }
    allowed_origins = {f"http://{h}" for h in allowed_hosts}
    # Tailscale serve가 https로 받아 127.0.0.1로 넘겨요: 등록한 ts.net 이름만(T-51 · SPEC 10 main)
    names = ts_names if ts_names is not None else ts_names_from(cfg.ts_name)
    ts_ok = ts_names_from(",".join(names))
    for name in ts_ok:
        allowed_hosts |= {name, f"{name}:443"}
        allowed_origins.add(f"https://{name}")

    # 텔레그램(T-52): 전송은 기본 가짜. `/멈춤`은 새 매수 멈춤을 켜기만 해요(끄는 길은 앱 화면 · 비밀번호).
    def latest_dps(sym: str) -> float | None:
        row = db.one("SELECT dps FROM dart_div WHERE stock_code=? ORDER BY rcept_dt DESC LIMIT 1", (sym,))
        return float(row["dps"]) if row and row["dps"] else None

    def notify(event: str, text: str) -> bool:  # Notifier 포트(텔레그램 · 알림함) · telegram은 아래에서 만들어요
        return telegram.notify(event, text)

    # 실전 운용(T-60 ~ T-63): 증권사는 Broker 포트 · conns.client가 토스 어댑터를 줘요(기본 가짜 · 두 열쇠 · T-00)
    live = Live(db, market, conns.client, now=now, notify=notify,
                info=lambda: {r["symbol"]: dict(r) for r in db.all("SELECT * FROM stock_info")}, dps=latest_dps)

    def pause_new_buys(source: str) -> bool:
        return live.pause_new_buys(source)

    def tg_status() -> dict[str, Any]:
        todos = db.one("SELECT COUNT(*) AS n FROM todos WHERE status='open'")
        label = ("새 매수 멈춤" if db.get_meta("live.new_buys_paused") == "1"
                 else "운용 중" if live.run() is not None else "운용 전")
        return {"label": label, "todos": int(todos["n"]) if todos else 0}

    telegram = Telegram(
        db, vault, telegram_transport or transports.telegram, now=now, status=tg_status, pause=pause_new_buys,
        link=lambda: f"https://{ts_ok[0]}" if ts_ok else None,
    )
    csrf_key = secrets.token_bytes(32)  # 프로세스마다 새로(세션도 메모리에만 있어요)

    def csrf_for(session: str) -> str:
        return hmac.new(csrf_key, session.encode(), hashlib.sha256).hexdigest()

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
    app.state.telegram = telegram
    app.state.live = live

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
            session = request.cookies.get(COOKIE)
            if not vault.session_ok(session):
                return _err("다시 로그인해 주세요", 401, need_login=True)
            # 바꾸는 요청은 CSRF 값이 세션과 맞아야 해요(쿠키는 SameSite=Strict · 두 겹)
            if request.method not in SAFE_METHODS:
                sent = request.headers.get(CSRF_HEADER) or ""
                if not session or not hmac.compare_digest(sent, csrf_for(session)):
                    return _err("요청 확인 값이 맞지 않아요 · 화면을 다시 열어 주세요", 403, csrf=True)
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

    @app.exception_handler(ApiError)
    async def on_api(_: Request, exc: ApiError) -> JSONResponse:
        return _err(exc.message, exc.status, **exc.extra)

    @app.exception_handler(ct.FormatError)
    async def on_format_v3(_: Request, exc: ct.FormatError) -> JSONResponse:
        if exc.kind == "graph":
            return _err(exc.message, 400, kind="graph", title=ct.BAD_LINKS, detail=exc.detail)
        return _err(exc.message, 400, kind=exc.kind)

    @app.exception_handler(dm.DataError)
    async def on_data(_: Request, exc: dm.DataError) -> JSONResponse:
        return _err(exc.message, exc.status)

    @app.exception_handler(LiveError)
    async def on_live(_: Request, exc: LiveError) -> JSONResponse:
        return _err(exc.message, exc.status)

    @app.exception_handler(TelegramError)
    async def on_telegram(_: Request, exc: TelegramError) -> JSONResponse:
        return _err(exc.message, exc.status, kind=exc.kind)

    @app.exception_handler(VaultError)
    async def on_vault(_: Request, exc: VaultError) -> JSONResponse:
        return _err(exc.message, exc.status, **exc.extra)

    @app.exception_handler(MarketDataError)
    async def on_market(_: Request, exc: MarketDataError) -> JSONResponse:
        if exc.kind == "symbol":
            return _err(exc.message, 400, kind="symbol", symbols=exc.symbols)
        return _err(exc.message, 502, kind="market")

    @app.exception_handler(BacktestErrorV2)
    async def on_bt2(_: Request, exc: BacktestErrorV2) -> JSONResponse:
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
        resp.set_cookie(
            CSRF_COOKIE, csrf_for(token), max_age=SESSION_S, httponly=False, samesite="strict", path="/"
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
            "update_chip": updates.status(data)["chip"],  # 머리 칩 '업데이트 중'(5-10)
            "auto": vault.runner_ready,  # 키 파일로 로그인 없이 운용 이어짐(T-50)
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
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp

    # ── 설정 › 연결 ────────────────────────────────────────────────────────

    @app.get("/api/connect")
    def connect_view() -> dict[str, Any]:
        return conns.view()

    # ── 비밀번호 다시 받기(SPEC 7-4 · V2-33) ─────────────────────────────

    @app.post("/api/confirm")
    async def confirm(request: Request) -> dict[str, Any]:
        b = await _body(request)
        action = str(b.get("action") or "")
        token = await asyncio.to_thread(vault.confirm, str(b.get("password") or ""), action)
        return {"token": token, "expires_in": vault_mod.CONFIRM_S}

    def need_confirm(request: Request, action: str) -> None:
        vault.use_confirm(request.headers.get(CONFIRM_HEADER), action)

    app.state.need_confirm = need_confirm

    @app.put("/api/connect/toss")
    async def toss_save(request: Request) -> dict[str, Any]:
        if conns.view()["toss"]["saved"]:
            need_confirm(request, "toss_key_change")  # 처음 넣기는 로그인만, 바꾸기는 비밀번호
        b = await _body(request)
        live.check_account_change(str(b.get("account_no") or "") or None)  # 운용 중 계좌번호 변경 거절(R-L10)
        conns.save_toss(
            str(b.get("client_id") or ""),
            str(b.get("client_secret") or ""),
            str(b.get("account_no") or "") or None,
        )
        return conns.view()

    @app.delete("/api/connect/toss")
    def toss_delete(request: Request) -> dict[str, Any]:
        need_confirm(request, "toss_key_delete")
        conns.delete_toss()
        return conns.view()

    @app.post("/api/connect/toss/check")
    async def toss_check() -> dict[str, Any]:
        return {"result": await asyncio.to_thread(conns.check), **conns.view()}

    @app.put("/api/connect/dart")
    async def dart_save(request: Request) -> dict[str, Any]:
        if conns.view()["dart"]["saved"]:
            need_confirm(request, "dart_key_change")
        b = await _body(request)
        conns.save_dart(str(b.get("key") or ""))
        return conns.view()

    @app.delete("/api/connect/dart")
    def dart_delete(request: Request) -> dict[str, Any]:
        need_confirm(request, "dart_key_delete")
        conns.delete_dart()
        return conns.view()

    # ── 설정 › 접속(V2-05 · V2-06 · V2-56) ────────────────────────────────

    PLACES = {"server": "서버(클라우드 · 고정 IP)", "pc": "늘 켜 둔 PC"}

    def access_view() -> dict[str, Any]:
        place = db.get_meta("access.place")
        return {
            "place": place if place in PLACES else None,
            "place_name": PLACES.get(place or ""),
            # Tailscale: 설치기가 serve를 설정하고 이름을 넘겨 줬으면 연결됨(Q-N10)
            "tailscale": {"ok": bool(ts_ok), "name": ts_ok[0] if ts_ok else None,
                          "address": f"https://{ts_ok[0]}" if ts_ok else None},
            "local": f"127.0.0.1:{port}",
        }

    @app.get("/api/access")
    def access_get() -> dict[str, Any]:
        return access_view()

    @app.put("/api/access/place")
    async def access_place(request: Request) -> dict[str, Any]:
        b = await _body(request)
        place = str(b.get("place") or "")
        if place not in PLACES:
            raise VaultError("서버 또는 PC를 골라 주세요")
        if db.get_meta("access.place") and db.get_meta("access.place") != place:
            need_confirm(request, "install_place")  # 처음 고르기는 로그인만, 변경은 비밀번호(SPEC 7-4)
        db.set_meta("access.place", place)
        return access_view()

    # ── 실전 운용(T-60 ~ T-63 · SPEC 7-2 · 7-4) ────────────────────────────

    def _rid() -> int:
        r = live.run()
        if r is None:
            raise LiveError("실전 운용 중이 아니에요", 409)
        return int(r["id"])

    @app.get("/api/live")
    def live_view() -> dict[str, Any]:
        return live.view()

    @app.get("/api/live/screen")
    async def live_screen() -> dict[str, Any]:
        return await asyncio.to_thread(live.screen)

    @app.get("/api/live/preview")
    def live_preview(version_id: int) -> dict[str, Any]:
        """V2-30 ① 확인할 것: 토스 연결 · 백테스트 함 · 다른 운용 없음 · 텔레그램 · 설치 위치 · 손절 없음(R-X10)."""
        from .domain import blocks as bkm

        v = db.one("SELECT v.*, s.name FROM versions v JOIN strategies s ON s.id=v.strategy_id WHERE v.id=?",
                   (version_id,))
        if v is None:
            raise LiveError("그 버전이 없어요", 404)
        body = json.loads(v["body"])
        from .domain.copytext import read_body

        g = read_body(body)["graph"]
        stop = any(r["item"] in ("stop_loss", "trailing_stop") and bkm.exec_of(g, b["id"], i) in ("intraday", "broker")
                   for b in g["blocks"] if b["stage"] == "sell" for i, r in enumerate(b["rows"]))
        view = conns.view()["toss"]
        tg = telegram.view()
        checks = [
            {"key": "toss", "ok": bool(view["saved"] and (view.get("last_check") or {}).get("ok"))},
            {"key": "account", "ok": bool(view.get("account_tail")), "tail": view.get("account_tail")},
            {"key": "backtest", "ok": db.one("SELECT 1 FROM backtest_runs WHERE version_id=?", (version_id,)) is not None},
            {"key": "single", "ok": live.run() is None},
            {"key": "telegram", "ok": bool(tg["saved"] and tg["chat"])},
            {"key": "place", "ok": bool(db.get_meta("access.place")), "place": db.get_meta("access.place")},
        ]
        return {"name": v["name"], "version_no": v["no"], "checks": checks, "has_stop": stop,
                "ok": all(c["ok"] for c in checks)}

    @app.post("/api/live/start")
    async def live_start(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_start")
        b = await _body(request)
        try:
            vid, amount = int(b.get("version_id")), float(b.get("amount"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise LiveError("버전과 운용 금액을 정해 주세요") from None
        await asyncio.to_thread(live.start, vid, amount)
        return live.view()

    @app.post("/api/live/pause")
    def live_pause() -> dict[str, Any]:
        live.pause_new_buys("app")  # 로그인만(SPEC 7-4)
        return live.view()

    @app.post("/api/live/resume")
    def live_resume(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_resume_buys")
        live.resume_new_buys()
        return live.view()

    @app.post("/api/live/end")
    def live_end(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_end")
        live.end(_rid())
        return live.view()

    @app.post("/api/live/sell-all")
    def live_sell_all(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_sell_all_end")
        return {"orders": live.sell_all_and_end(_rid()), **live.view()}

    @app.put("/api/live/amount")
    async def live_amount(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_amount")
        b = await _body(request)
        live.set_amount(_rid(), float(b.get("amount") or 0))
        return live.view()

    @app.put("/api/live/limits")
    async def live_limits(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_limits")
        b = await _body(request)
        live.set_limits(_rid(), b)
        return live.view()

    @app.put("/api/live/strategy")
    async def live_strategy(request: Request) -> dict[str, Any]:
        need_confirm(request, "live_strategy")
        b = await _body(request)
        from_d = live.change_strategy(_rid(), int(b.get("version_id") or 0))
        return {"from": from_d, **live.view()}

    @app.post("/api/todos/{tid}/unknown")
    async def todo_unknown(tid: int, request: Request) -> dict[str, Any]:
        need_confirm(request, "unknown_order_record")
        b = await _body(request)
        t = db.one("SELECT data FROM todos WHERE id=? AND kind='unknown'", (tid,))
        if t is None:
            raise LiveError("그 할 일이 없어요", 404)
        live.resolve_unknown(_rid(), int(json.loads(t["data"])["order"]), filled_qty=int(b.get("filled_qty") or 0),
                             price=float(b.get("price") or 0))
        return live.view()

    @app.post("/api/todos/{tid}/corp")
    def todo_corp(tid: int, request: Request) -> dict[str, Any]:
        need_confirm(request, "todo_corp_action")
        t = db.one("SELECT symbol FROM todos WHERE id=? AND kind='corp'", (tid,))
        if t is None:
            raise LiveError("그 할 일이 없어요", 404)
        live.apply_corp(_rid(), t["symbol"])
        return live.view()

    @app.post("/api/todos/{tid}/match")
    def todo_match(tid: int, request: Request) -> dict[str, Any]:
        need_confirm(request, "todo_match_account")
        t = db.one("SELECT symbol FROM todos WHERE id=? AND kind='mismatch'", (tid,))
        if t is None:
            raise LiveError("그 할 일이 없어요", 404)
        live.match_account(_rid(), t["symbol"])
        return live.view()

    @app.post("/api/todos/{tid}/big-order")
    def todo_big(tid: int, request: Request) -> dict[str, Any]:
        need_confirm(request, "todo_big_order")
        return {"order": live.send_big(_rid(), tid), **live.view()}

    # ── 설정 › 데이터(V2-53 · T-53) ───────────────────────────────────────

    @app.get("/api/data")
    def data_view() -> dict[str, Any]:
        return dm.overview(db)

    @app.get("/api/data/backup")
    async def data_backup() -> Response:
        raw = await asyncio.to_thread(dm.backup_bytes, db)
        name = dm.backup_name(now().astimezone(KST).date().isoformat())
        return Response(raw, media_type="application/octet-stream",
                        headers={"content-disposition": f'attachment; filename="{name}"'})

    @app.post("/api/data/restore")
    async def data_restore(request: Request) -> Response:
        need_confirm(request, "restore")
        raw = await request.body()
        await asyncio.to_thread(dm.restore, db, raw, now_iso=_now())
        vault.reload()  # 계정 · 비밀번호가 백업 것으로 바뀌어요: 다시 로그인
        conns.drop()
        resp = JSONResponse({"ok": True, "line": dm.RESTORE_LINE})
        resp.delete_cookie(COOKIE, path="/")
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp

    @app.delete("/api/data")
    def data_delete(request: Request) -> Response:
        if dm.live_running(db):
            raise dm.DataError(dm.RUNNING_LIVE, 409)  # 비밀번호 창보다 먼저 알려요
        need_confirm(request, "data_delete")
        vault.forget_keyfile()
        dm.delete_all(db)
        vault.reload()
        conns.drop()
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/")
        resp.delete_cookie(CSRF_COOKIE, path="/")
        return resp

    @app.get("/api/history/csv")
    def history_csv(run_id: int | None = None) -> Response:
        name = f"quant-history-{now().astimezone(KST).date().isoformat().replace('-', '')}.csv"
        return Response(dm.history_csv(db, run_id), media_type="text/csv; charset=utf-8",
                        headers={"content-disposition": f'attachment; filename="{name}"'})

    @app.get("/api/update")
    def update_status() -> dict[str, Any]:
        return updates.status(data)

    # ── 설정 › 알림 · 텔레그램(V2-08 · V2-52) ─────────────────────────────

    @app.get("/api/telegram")
    def telegram_view() -> dict[str, Any]:
        return telegram.view()

    @app.put("/api/telegram")
    async def telegram_save(request: Request) -> dict[str, Any]:
        if telegram.view()["saved"]:
            need_confirm(request, "telegram_key_change")  # 토큰 변경은 비밀번호(V2-52)
        b = await _body(request)
        return await asyncio.to_thread(telegram.save_token, str(b.get("token") or ""))

    @app.delete("/api/telegram")
    def telegram_delete(request: Request) -> dict[str, Any]:
        need_confirm(request, "telegram_key_delete")
        return telegram.delete()

    @app.post("/api/telegram/find-chat")
    async def telegram_find_chat() -> dict[str, Any]:
        return await asyncio.to_thread(telegram.find_chat)

    @app.post("/api/telegram/test")
    async def telegram_test() -> dict[str, Any]:
        return await asyncio.to_thread(telegram.test_send)

    @app.put("/api/telegram/events")
    async def telegram_events(request: Request) -> dict[str, Any]:
        b = await _body(request)
        return telegram.set_event(str(b.get("key") or ""), b.get("on") is True)

    # ── 전략 이름(v2 라우터가 써요 · 옛 MVP 전략 · 백테스트 · 모의투자 라우트는 P1-03에서 지움) ──────────────

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

    # ── 화면(web/dist) ──────────────────────────────────────────────────────

    def _index() -> Response:
        index = dist / "index.html"
        if not index.is_file():
            return _err("화면 파일이 없어요 · start.sh로 다시 켜 주세요", 503)
        return FileResponse(index, headers={"cache-control": "no-store"})

    dart_store = DartStore(db)
    paper2 = PaperV2(db, market, now=now,
                     info=lambda: {r["symbol"]: dict(r) for r in db.all("SELECT * FROM stock_info")})
    app.state.paper2 = paper2

    @app.exception_handler(PaperError)
    async def on_paper2(_: Request, exc: PaperError) -> JSONResponse:
        return _err(exc.message, exc.status)

    @app.get("/api/v2/paper")
    def paper2_list() -> dict[str, Any]:
        return {"runs": paper2.list()}

    @app.post("/api/v2/paper/start")
    async def paper2_start(request: Request) -> dict[str, Any]:
        b = await _body(request)
        try:
            vid = int(b.get("version_id"))  # type: ignore[arg-type]
        except (TypeError, ValueError):
            raise VaultError("전략 버전을 골라 주세요") from None
        return await asyncio.to_thread(paper2.start, vid, b.get("cash"))

    @app.get("/api/v2/paper/preview")
    def paper2_preview(version_id: int) -> dict[str, Any]:
        return paper2.preview(version_id)

    @app.get("/api/v2/paper/{rid}")
    def paper2_view(rid: int) -> dict[str, Any]:
        return paper2.view(rid)

    @app.post("/api/v2/paper/{rid}/stop")
    def paper2_stop(rid: int) -> dict[str, Any]:
        return paper2.stop(rid)

    @app.post("/api/v2/paper/check")
    async def paper2_check() -> dict[str, Any]:
        return {"advanced": await asyncio.to_thread(paper2.tick)}

    def _backtest_v2(body: dict[str, Any], start: date, end: date, cash: float) -> dict[str, Any]:
        info = {r["symbol"]: dict(r) for r in db.all("SELECT * FROM stock_info")}
        return bt2.run(body, market=market, db=db, dart=dart_store,
                       has_dart=bool(conns.view()["dart"]["saved"]),
                       toss_ready=conns.client() is not None or bars_source is not None,
                       start=start, end=end, cash=cash, info=info, names=stock_name)

    def _running_v2(sid: int) -> dict[str, Any] | None:
        r2 = paper2.running_for(sid)
        if r2 is not None:
            no = db.one("SELECT no FROM versions WHERE id=?", (r2["version_id"],))
            return {"kind": "paper", "version_no": int(no["no"]) if no else 0, "run_id": int(r2["id"])}
        return None

    app.include_router(make_router(
        db, dart=lambda: bool(conns.view()["dart"]["saved"]), unique_name=lambda n: _unique_name(n)[0],
        now=_now, running=_running_v2,
        used=lambda sid: db.one(
            "SELECT r.id FROM paper_runs r JOIN versions v ON v.id=r.version_id WHERE v.strategy_id=? "
            "UNION SELECT id FROM runs WHERE strategy_id=? LIMIT 1", (sid, sid)) is not None,
        backtester=_backtest_v2,
    ))

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

    # ── 평일 16:30 자동으로 한 번(auto_tick · app.state.auto_tick은 바깥 약속 · ARCHITECTURE 5절) ──────────────────────────────────────────

    # 스케줄러(T-51): 거래일 · 장 시작은 토스 market-calendar로. 실전 일(08:30 점검 · 08:35 주문)은 T-6x에서 더해요.
    sched = Scheduler(db, market.calendar, now)
    sched.add("paper_check", 20, 10, paper2.tick)  # 모의투자 v2: 거래일 20:10 확인(T-40)

    def live_check() -> None:
        r = live.run()
        if r is not None:
            live.check(int(r["id"]))  # 실패하면 스케줄러가 10분 뒤 다시(R-L4)

    sched.add("live_check", 20, 10, live_check)
    app.state.scheduler = sched

    async def _auto_loop() -> None:
        first = True
        while True:
            try:
                # 세션이 만료됐으면 요청이 없어도 30초 안에 데이터 키와 연결 객체를 지운다
                _ = vault.unlocked
                await asyncio.to_thread(auto_tick)
                if first:  # 켜질 때 한 번: 꺼져 있던 날을 이어서 채워요(R-V4) · 업데이트 끝 알림(5-10)
                    first = False
                    await asyncio.to_thread(paper2.tick)
                    updates.announce(data, db, lambda text: telegram.notify("info", text))
                await asyncio.to_thread(sched.run_due)
                await asyncio.to_thread(live_tick, live)  # 08:30 점검 · 08:35 주문 · 장중 감시(R-O1)
                await asyncio.to_thread(telegram.poll)  # `/상태` · `/멈춤`(등록 대화방만)
            except Exception as exc:  # 루프는 멈추지 않는다
                log.error("auto tick failed: %s", type(exc).__name__)
            await asyncio.sleep(30)

    def auto_tick() -> str | None:
        local = now().astimezone(KST)
        if not weekday_open(local.date()) or (local.hour, local.minute) < AUTO_AT:
            return None
        today = local.date().isoformat()
        if db.get_meta("auto.last") == today:
            return None
        db.set_meta("auto.last", today)
        # 자동 확인이 돈 날(앱이 켜져 있던 날). '앱이 꺼져 있던 날도 채웠어요' 안내를 가르는 데 쓴다.
        ran_days: list[str] = json.loads(db.get_meta("auto.ran_days") or "[]")
        db.set_meta("auto.ran_days", json.dumps((ran_days + [today])[-60:]))
        # 옛 MVP 모의투자(status 'running' · P1-03에서 지움)는 더 만들 수 없어 늘 건너뛰어요 · 모의투자 v2는 20:10 paper_check
        db.set_meta("auto.last_result", "실행 중인 모의투자가 없어 건너뛰었어요")
        return "skip"

    app.state.auto_tick = auto_tick
    return app


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

