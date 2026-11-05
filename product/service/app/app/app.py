"""조립(ARCHITECTURE 2절 조립 층 · TASKS P1-08 · P1-09): `create_app` · 앱 루프 · 설치기 몫.

`create_app`은 설정을 한 번 읽고(`settings.load`), 어댑터를 고르고(기본은 가짜 전송 · 두 열쇠 · T-00), 저장 · 금고 · 실행 흐름 ·
쓰기 일을 만들어 서로 이어 주고, 기능별 라우터(`api/*`)를 등록해요. 인자 12개 · `app.state`의 이름 · 상태 응답 `"quant-mvp"`는
바깥 약속이에요(ARCHITECTURE 5절 · `python -m app.serve`가 불러요).

앱 루프: 조립이 만든 일을 30초마다(`run/scheduler.py`의 시각 표 `LOOP_EVERY_S`) 차례로 돌려요: 세션 만료 확인 → 평일 16:30
자동 확인 → (켤 때 한 번) 꺼져 있던 날 모의투자 채우기 · 업데이트 끝 알림 → 스케줄러(20:10 확인) → 실전 tick(08:30 점검 ·
08:35 주문 · 장중 감시) → 텔레그램 받기. 한 일이 실패해도 루프는 멈추지 않아요(종류만 기록). 일은 부를 때마다 이름을 찾는
함수로 넘겨요(앱 상태의 객체를 시험이 바꿔 끼워도 루프가 그것을 불러요 · 옮기기 전 `main._auto_loop`와 같음).

기준선 시계 고정 자리(Q-N24)의 기록 시각 함수 셋(`main._now` · `connect._now` · `api_v2.backtest_today`)은 그 모듈 이름에
정의가 남아 있고, 여기서 받아 넘겨요.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI

from . import api_v2 as api_v2_clock
from . import backtest_v2 as bt2
from . import connect as connect_clock
from . import main as main_clock
from . import settings
from .adapters.publicip import IpFetch, PublicIpError, public_ip
from .adapters.telegram import Bot
from .adapters.toss import TossClient, TossCredentials, TossSource, link_state
from .adapters.transport import Transport, Transports, build_transports
from .api import access as access_api
from .api import account as account_api
from .api import connect as connect_api
from .api import data as data_api
from .api import live as live_api
from .api import paper as paper_api
from .api import strategies as strategies_api
from .api import telegram as telegram_api
from .api import web as web_api
from .api.errors import install_error_handlers, with_kind
from .api.guard import install_guard
from .api.http import confirmer
from .domain.markets.kr import KST, weekday_open
from .domain.stock_names import stock_name
from .market import now_kst
from .ports import Clock, MarketFeed, TelegramError
from .run.dart import DartStore
from .run.data import Calendar, Market
from .run.live import Live
from .run.live import tick as live_tick
from .run.paper import PaperV2
from .run.scheduler import AUTO_CHECK, DAILY_CHECK, LOOP_EVERY_S, UPDATE_FROM, UPDATE_UNTIL, Scheduler
from .security import vault as vault_mod
from .security.access import Csrf, allowed_hosts_and_origins, ts_names_from
from .security.vault import SCRYPT_N, Vault, VaultError
from .services import updates
from .services.connect import Connections
from .services.telegram_commands import TelegramCommands
from .store import dart as store_dart
from .store import market as market_store
from .store import strategies as strategy_store
from .store import todos as todo_store
from .store.db import DB

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT.parent.parent.parent  # 레포 뿌리(product/service/app → 레포)
DIST = ROOT / "web" / "dist"
log = logging.getLogger("quant-mvp")


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
    conns = Connections(db, vault, toss_transport,
                        client_for=lambda cid, sec, acc, t: TossClient(TossCredentials(cid, sec, acc), transport=t),
                        link_state=link_state, now=connect_clock._now)
    # 일봉 원천은 연결 객체가 만든 토스 클라이언트(쓰기 일은 `Broker` 포트로 알지만 조립은 토스 어댑터인 것을 알아요)
    market = Market(db, bars_source or TossSource(lambda: cast(TossClient | None, conns.client())))

    # Tailscale serve가 https로 받아 127.0.0.1로 넘겨요: 등록한 ts.net 이름만(T-51 · SPEC 10 main)
    names = ts_names if ts_names is not None else ts_names_from(cfg.ts_name)
    ts_ok = ts_names_from(",".join(names))
    allowed_hosts, allowed_origins = allowed_hosts_and_origins(port, ts_ok)

    # 텔레그램(T-52): 전송은 기본 가짜. `/멈춤`은 새 매수 멈춤을 켜기만 해요(끄는 길은 앱 화면 · 비밀번호).
    def latest_dps(sym: str) -> float | None:
        return store_dart.latest_dps(db, sym)

    def notify(event: str, text: str) -> bool:  # Notifier 포트(텔레그램 · 알림함) · telegram은 아래에서 만들어요
        return telegram.notify(event, text)

    # 실전 운용(T-60 ~ T-63): 증권사는 Broker 포트 · conns.client가 토스 어댑터를 줘요(기본 가짜 · 두 열쇠 · T-00)
    live = Live(db, market, conns.client, now=now, notify=notify,
                info=lambda: market_store.stock_info_map(db), dps=latest_dps)

    def pause_new_buys(source: str) -> bool:
        return live.pause_new_buys(source)

    def tg_status() -> dict[str, Any]:
        todos = todo_store.count_open_todos(db)
        label = ("새 매수 멈춤" if db.get_meta("live.new_buys_paused") == "1"
                 else "운용 중" if live.run() is not None else "운용 전")
        return {"label": label, "todos": todos}

    tg_transport = telegram_transport or transports.telegram
    telegram = TelegramCommands(
        db, vault, lambda token: Bot(token, tg_transport), now=now, status=tg_status, pause=pause_new_buys,
        link=lambda: f"https://{ts_ok[0]}" if ts_ok else None,
    )
    csrf = Csrf()  # 프로세스마다 새로(세션도 메모리에만 있어요)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        task = asyncio.create_task(auto_loop(loop_steps)) if scheduler else None
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

    # ── 바깥 문 · 오류 ─────────────────────────────────────────────────────
    install_guard(app, vault=vault, allowed_hosts=allowed_hosts, allowed_origins=allowed_origins, csrf=csrf)
    install_error_handlers(app)
    app.add_exception_handler(TelegramError, with_kind)  # 포트 오류라 조립이 등록(API 층은 포트를 몰라요)

    need_confirm = confirmer(vault)
    app.state.need_confirm = need_confirm

    def lookup_ip() -> str:
        # 누를 때만 부른다. 저장하지 않는다.
        try:
            return public_ip(ip_fetch)
        except PublicIpError as exc:
            raise VaultError(exc.message, 502) from None

    dart_store = DartStore(db)
    paper2 = PaperV2(db, market, now=now,
                     info=lambda: market_store.stock_info_map(db))
    app.state.paper2 = paper2

    def _backtest_v2(body: dict[str, Any], start: date, end: date, cash: float) -> dict[str, Any]:
        info = market_store.stock_info_map(db)
        return bt2.run(body, market=market, db=db, dart=dart_store,
                       has_dart=bool(conns.view()["dart"]["saved"]),
                       toss_ready=conns.client() is not None or bars_source is not None,
                       start=start, end=end, cash=cash, info=info, names=stock_name)

    def _running_v2(sid: int) -> dict[str, Any] | None:
        r2 = paper2.running_for(sid)
        if r2 is not None:
            no = strategy_store.version_no(db, r2["version_id"])
            return {"kind": "paper", "version_no": int(no["no"]) if no else 0, "run_id": int(r2["id"])}
        return None

    # ── 기능별 라우터(등록 차례 = 옮기기 전 `main.py`의 라우트 차례 · 화면 파일은 맨 끝) ──────────────
    app.include_router(account_api.account_router(db=db, vault=vault, conns=conns, csrf=csrf, data=data, port=port,
                                               lookup_ip=lookup_ip))
    app.include_router(connect_api.connect_router(conns=conns, live=live, need_confirm=need_confirm))
    app.include_router(access_api.access_router(db=db, ts_ok=ts_ok, port=port, need_confirm=need_confirm))
    app.include_router(live_api.live_router(db=db, live=live, conns=conns, telegram=telegram,
                                            need_confirm=need_confirm))
    app.include_router(data_api.data_router(db=db, data=data, vault=vault, conns=conns, need_confirm=need_confirm,
                                            now=now, now_iso=main_clock._now))
    app.include_router(telegram_api.telegram_router(telegram=telegram, need_confirm=need_confirm))
    app.include_router(paper_api.paper_router(paper2=paper2))
    app.include_router(strategies_api.strategies_router(
        db, dart=lambda: bool(conns.view()["dart"]["saved"]), now=main_clock._now,
        today=api_v2_clock.backtest_today, running=_running_v2,
        used=lambda sid: strategy_store.strategy_in_use(db, sid),
        backtester=_backtest_v2,
    ))
    app.include_router(web_api.web_router(dist=dist))

    # ── 평일 16:30 자동으로 한 번(auto_tick · app.state.auto_tick은 바깥 약속 · ARCHITECTURE 5절) ──────────────

    # 스케줄러(T-51): 거래일 · 장 시작은 토스 market-calendar로. 실전 일(08:30 점검 · 08:35 주문)은 T-6x에서 더해요.
    sched = Scheduler(db, market.calendar, now)
    sched.add("paper_check", *DAILY_CHECK, paper2.tick)  # 모의투자 v2: 거래일 20:10 확인(T-40)

    def live_check() -> None:
        r = live.run()
        if r is not None:
            live.check(int(r["id"]))  # 실패하면 스케줄러가 10분 뒤 다시(R-L4)

    sched.add("live_check", *DAILY_CHECK, live_check)
    app.state.scheduler = sched

    # 앱 루프(`auto_loop` · 30초마다): 일은 부를 때마다 이름을 찾아요(시험이 앱 상태의 객체를 바꿔 끼워도 같게)
    loop_steps = LoopSteps(
        touch=lambda: vault.unlocked,
        auto_tick=lambda: auto_tick(),
        catch_up=lambda: paper2.tick(),
        announce=lambda: updates.announce(data, db, lambda text: telegram.notify("info", text)),
        run_due=lambda: sched.run_due(),
        live_tick=lambda: live_tick(live),
        poll=lambda: telegram.poll(),
    )

    def auto_tick() -> str | None:
        local = now().astimezone(KST)
        if not weekday_open(local.date()) or (local.hour, local.minute) < AUTO_CHECK:
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


# ── 앱 루프 ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class LoopSteps:
    touch: Callable[[], object]  # 세션이 만료됐으면 요청이 없어도 30초 안에 데이터 키와 연결 객체를 지워요
    auto_tick: Callable[[], object]  # 평일 16:30 자동으로 한 번(`app.state.auto_tick`)
    catch_up: Callable[[], object]  # 켤 때 한 번: 꺼져 있던 날을 이어서 채워요(모의투자 · R-V4)
    announce: Callable[[], object]  # 켤 때 한 번: 업데이트 끝 알림(SPEC 5-10 · 루프 안에서 바로 불러요)
    run_due: Callable[[], object]  # 스케줄러: 때가 된 일(20:10 확인 · 실패하면 10분 뒤 다시)
    live_tick: Callable[[], object]  # 실전 tick: 08:20 대조 · 08:30 ~ 08:50 점검 창 · 08:35 주문 · 장중 1분마다(R-O1)
    poll: Callable[[], object]  # 텔레그램 `/상태` · `/멈춤`(등록 대화방만)


async def auto_loop(steps: LoopSteps) -> None:
    first = True
    while True:
        try:
            steps.touch()
            await asyncio.to_thread(steps.auto_tick)
            if first:
                first = False
                await asyncio.to_thread(steps.catch_up)
                steps.announce()
            await asyncio.to_thread(steps.run_due)
            await asyncio.to_thread(steps.live_tick)
            await asyncio.to_thread(steps.poll)
        except Exception as exc:  # 루프는 멈추지 않는다
            log.error("auto tick failed: %s", type(exc).__name__)
        await asyncio.sleep(LOOP_EVERY_S)


# ── 설치기(입구 `install.py` · `python -m app.install`)가 조립을 거쳐 쓰는 것 ─────────────────────────────


def stored_calendar(data: Path) -> Calendar | None:
    """`can-update`: 앱이 데이터 폴더 DB에 받아 둔 토스 장 달력(DB가 없으면 None · 그때는 평일 규칙)."""
    db_path = data / "app.db"
    return Calendar(DB(db_path), None) if db_path.exists() else None


def update_window_state(now: datetime, cal: Calendar | None = None) -> str | None:
    """SPEC 5-10 업데이트 창(거래일 16:00 ~ 20:00 · `run/scheduler.py` 시각 표): 안이면 None · 거래일이 아니면 'closed' ·
    시간 밖이면 'hours'(글은 설치기가 붙여요)."""
    local = now.astimezone(KST)
    is_open = cal.is_open(local.date()) if cal is not None else local.weekday() < 5
    if not is_open:
        return "closed"
    if not (UPDATE_FROM <= local.time() < UPDATE_UNTIL):
        return "hours"
    return None


def write_update_step(data: Path, step: str, state: str, version: str, now: datetime) -> None:
    """설치기 `step`: `update.json`에 한 단계를 적어요(꼴은 `services/updates.py` · 시각은 한국 시간 초 단위)."""
    updates.write_step(data, step, state, version, at=now.astimezone(KST).isoformat(timespec="seconds"))
