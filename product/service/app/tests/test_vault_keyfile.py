"""T-50: 컴퓨터 키 파일 · 재부팅 흉내 · 비밀번호 없이 돈이 움직이는 길 0개(SPEC 7-4).

키 파일은 늘 운영체제 임시 폴더(conftest `keyfile_path`)에만 만들어요. 토스는 가짜 서버(tests/fake_toss.py)예요.
"""

from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app import vault as vault_mod
from app.db import DB
from app.main import create_app
from app.market import KST, MarketDataError
from app.vault import MONEY_ACTIONS, Vault, VaultError
from tests.conftest import CsrfClient, PASSWORD, confirm, make_bars, setup_owner
from tests.test_paper_v2 import body, save
from tests.fake_toss import ACCOUNT_NO, CLIENT_ID, CLIENT_SECRET, FakeTossServer

NOW = datetime(2026, 11, 2, 21, 0, tzinfo=KST)


def toss_server() -> FakeTossServer:
    s = FakeTossServer()
    s.bars = {"005930": make_bars([70000 + 10 * i for i in range(80)], start=date(2026, 8, 3))}
    s.index_bars = {"KOSPI": make_bars([2500.0 + i for i in range(80)], start=date(2026, 8, 3))}
    return s


def boot(data: Path, server: FakeTossServer, keyfile: Path | bool = True) -> TestClient:
    """앱 프로세스 하나를 켠 것처럼: 같은 데이터 폴더 · 같은 키 파일로 새로 만들어요."""
    app = create_app(data, toss_transport=lambda: server, scrypt_n=2**12, scheduler=False,
                     now=lambda: NOW, keyfile=keyfile)
    c = CsrfClient(app, base_url="http://testserver")
    c.app_ref = app  # type: ignore[attr-defined]
    return c


def first_boot(data: Path, server: FakeTossServer) -> None:
    c = boot(data, server)
    setup_owner(c)
    r = c.put("/api/connect/toss", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
                                         "account_no": ACCOUNT_NO})
    assert r.status_code == 200, r.text


# ── 재부팅 흉내 ─────────────────────────────────────────────────────────────


def test_restart_runs_without_login(tmp_path: Path, keyfile_path: Path) -> None:
    server = toss_server()
    first_boot(tmp_path / "data", server)
    assert keyfile_path.exists() and (keyfile_path.stat().st_mode & 0o777) == 0o600
    # 키 파일은 레포 · 데이터 폴더 밖
    assert not keyfile_path.resolve().is_relative_to((tmp_path / "data").resolve())
    assert not keyfile_path.resolve().is_relative_to(Path(__file__).resolve().parents[4])

    # 프로세스 다시 시작(새 앱 · 메모리 비움). 로그인하지 않아요.
    c = boot(tmp_path / "data", server)
    v = c.app_ref.state.vault  # type: ignore[attr-defined]
    assert v.runner_ready and not v.unlocked
    # 화면은 잠겨 있어요: 비밀번호 없이는 API가 막혀요
    assert c.get("/api/connect").status_code == 401
    assert c.get("/api/state").json()["logged_in"] is False
    # 실행기(자동 확인)는 키 파일로 토스 시세를 받아요
    bars = c.app_ref.state.market.bars("005930", date(2026, 9, 1), date(2026, 9, 30))  # type: ignore[attr-defined]
    assert bars and bars[0]["d"] >= "2026-09-01"
    assert ("POST", "/oauth2/token") in server.calls
    # 잠그기도 실행기 키는 지우지 않아요('잠가도 실전 운용은 계속돼요')
    v.lock_now()
    assert v.runner_ready
    c.app_ref.state.market.bars("005930", date(2026, 9, 1), date(2026, 9, 30))  # type: ignore[attr-defined]


def test_scheduler_check_runs_after_restart(tmp_path: Path) -> None:
    """앱 스케줄러가 부르는 v2 모의투자 확인(거래일 20:10)이 재시작 뒤 로그인 없이 토스 시세로 돌아요."""
    server = toss_server()
    data = tmp_path / "data"
    first_boot(data, server)
    c1 = boot(data, server)
    c1.post("/api/login", json={"password": PASSWORD})
    vid = save(c1.app_ref.state.db, body(["005930"]))  # type: ignore[attr-defined]
    rid = c1.app_ref.state.paper2.start(vid, 10_000_000)["id"]  # type: ignore[attr-defined]
    c1.post("/api/logout")

    later = datetime(2026, 11, 4, 21, 0, tzinfo=KST)
    app = create_app(data, toss_transport=lambda: server, scrypt_n=2**12, scheduler=False, now=lambda: later)
    assert not app.state.vault.unlocked
    done = app.state.paper2.tick()
    assert done, "확인이 돌지 않았어요"
    view = app.state.paper2.view(rid)
    assert view["status"] == "running"


def test_no_keyfile_means_locked_after_restart(tmp_path: Path, keyfile_path: Path) -> None:
    server = toss_server()
    first_boot(tmp_path / "data", server)
    keyfile_path.unlink()
    c = boot(tmp_path / "data", server)
    assert not c.app_ref.state.vault.runner_ready  # type: ignore[attr-defined]
    with pytest.raises(MarketDataError):
        c.app_ref.state.market.bars("005930", date(2026, 9, 1), date(2026, 9, 30))  # type: ignore[attr-defined]
    # 비밀번호로 들어오면 키 파일을 새로 만들고 다시 감싸요 → 다음 재시작부터 다시 자동
    c.post("/api/login", json={"password": PASSWORD})
    assert keyfile_path.exists()
    c2 = boot(tmp_path / "data", server)
    assert c2.app_ref.state.vault.runner_ready  # type: ignore[attr-defined]


def test_keyfile_readable_by_others_is_ignored(tmp_path: Path, keyfile_path: Path) -> None:
    server = toss_server()
    first_boot(tmp_path / "data", server)
    os.chmod(keyfile_path, 0o644)
    c = boot(tmp_path / "data", server)
    assert not c.app_ref.state.vault.runner_ready  # type: ignore[attr-defined]


def test_other_keyfile_does_not_open(tmp_path: Path, keyfile_path: Path) -> None:
    server = toss_server()
    first_boot(tmp_path / "data", server)
    keyfile_path.unlink()
    fd = os.open(keyfile_path, os.O_WRONLY | os.O_CREAT, 0o600)
    os.write(fd, os.urandom(32).hex().encode())
    os.close(fd)
    c = boot(tmp_path / "data", server)
    assert not c.app_ref.state.vault.runner_ready  # type: ignore[attr-defined]


def test_keyfile_inside_data_or_repo_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        create_app(tmp_path / "data", scheduler=False, keyfile=tmp_path / "data" / "keyfile")
    repo = Path(__file__).resolve().parents[4]
    with pytest.raises(ValueError):
        create_app(tmp_path / "data", scheduler=False, keyfile=repo / "keyfile")
    assert not (repo / "keyfile").exists()


def test_keyfile_off(tmp_path: Path, keyfile_path: Path) -> None:
    server = toss_server()
    c = boot(tmp_path / "data", server, keyfile=False)
    setup_owner(c)
    assert not keyfile_path.exists()
    assert not c.app_ref.state.vault.runner_ready  # type: ignore[attr-defined]


def test_default_path_is_outside_repo() -> None:
    # conftest가 바꾸기 전 기본값: 홈의 설정 폴더(레포 · 데이터 폴더 밖 고정 경로)
    assert vault_mod.DEFAULT_KEYFILE_PATH == Path.home() / ".config" / "quant-service" / "keyfile"
    assert not vault_mod.DEFAULT_KEYFILE_PATH.is_relative_to(Path(__file__).resolve().parents[4])


# ── 1회용 토큰 ──────────────────────────────────────────────────────────────


def _vault(tmp_path: Path, clock: list[float]) -> Vault:
    v = Vault(DB(tmp_path / "v.db"), scrypt_n=2**12, clock=lambda: clock[0])
    v.setup(PASSWORD, PASSWORD, adult=True, terms=True)
    return v


def test_confirm_token_is_one_shot_and_bound(tmp_path: Path) -> None:
    clock = [1000.0]
    v = _vault(tmp_path, clock)
    t = v.confirm(PASSWORD, "live_start")
    with pytest.raises(VaultError) as e:
        v.use_confirm(t, "live_end")  # 다른 일
    assert e.value.status == 403 and e.value.extra["need_confirm"] is True
    t = v.confirm(PASSWORD, "live_start")
    v.use_confirm(t, "live_start")
    with pytest.raises(VaultError):
        v.use_confirm(t, "live_start")  # 두 번째
    t = v.confirm(PASSWORD, "live_start")
    clock[0] += vault_mod.CONFIRM_S + 1
    with pytest.raises(VaultError):
        v.use_confirm(t, "live_start")  # 지남
    with pytest.raises(VaultError):
        v.use_confirm(None, "live_start")
    with pytest.raises(VaultError):
        v.confirm(PASSWORD, "nothing")


def test_confirm_shares_fail_count_with_login(tmp_path: Path) -> None:
    clock = [1000.0]
    v = _vault(tmp_path, clock)
    for _ in range(2):
        with pytest.raises(VaultError):
            v.login("wrong password")
    for _ in range(2):
        with pytest.raises(VaultError):
            v.confirm("wrong password", "live_start")
    with pytest.raises(VaultError) as e:
        v.confirm("wrong password", "live_start")
    assert e.value.status == 429  # 다섯 번째에 잠금(로그인 둘 + 확인 셋)
    with pytest.raises(VaultError) as e:
        v.login(PASSWORD)
    assert e.value.status == 429


# ── 비밀번호 없이 돈이 움직이는 길 0개 ───────────────────────────────────────

# 바꾸는 요청(POST · PUT · DELETE) 가운데 돈이 움직이지 않는 것과 그 까닭. 새 길은 여기나 MONEY_ROUTES에 넣어야 시험이 지나요.
NOT_MONEY: dict[tuple[str, str], str] = {
    ("POST", "/api/setup"): "처음 계정",
    ("POST", "/api/login"): "입장",
    ("POST", "/api/recover"): "복구 코드로 새 비밀번호",
    ("POST", "/api/password"): "지금 비밀번호를 받아요",
    ("POST", "/api/public-ip"): "조회",
    ("POST", "/api/logout"): "나가기",
    ("POST", "/api/confirm"): "비밀번호 다시 받기 자체",
    ("POST", "/api/connect/toss/check"): "조회",
    ("POST", "/api/strategies"): "전략(돈 없음)",
    ("POST", "/api/strategies/{sid}/versions"): "전략(돈 없음)",
    ("POST", "/api/strategies/{sid}/check"): "전략(돈 없음)",
    ("POST", "/api/import/preview"): "전략(돈 없음)",
    ("POST", "/api/import/accept"): "전략(돈 없음)",
    ("DELETE", "/api/strategies/{sid}"): "전략(운용 기록이 있으면 거절)",
    ("POST", "/api/backtest"): "백테스트",
    ("POST", "/api/paper/start"): "MVP 모의투자(가상 돈)",
    ("POST", "/api/paper/judge"): "MVP 모의투자(가상 돈)",
    ("POST", "/api/paper/stop"): "MVP 모의투자(가상 돈)",
    ("POST", "/api/v2/import/preview"): "전략(돈 없음)",
    ("POST", "/api/v2/import/accept"): "전략(돈 없음)",
    ("POST", "/api/v2/import/file"): "전략(돈 없음)",
    ("DELETE", "/api/v2/strategies/{sid}"): "전략(운용 기록이 있으면 거절)",
    ("POST", "/api/v2/backtest"): "백테스트",
    ("POST", "/api/v2/analyze"): "전략 분석",
    ("POST", "/api/v2/strategies"): "전략(돈 없음)",
    ("POST", "/api/v2/strategies/{sid}/versions"): "전략(돈 없음)",
    ("POST", "/api/v2/paper/start"): "모의투자(가상 돈 · R-V5)",
    ("POST", "/api/v2/paper/{rid}/stop"): "모의투자(가상 돈)",
    ("POST", "/api/v2/paper/check"): "모의투자 확인",
}

# 비밀번호(1회용 토큰)를 받는 길 → 일. 처음 키 넣기는 로그인만(바꾸기 · 삭제가 비밀번호 · SPEC 7-4).
MONEY_ROUTES: dict[tuple[str, str], str] = {
    ("PUT", "/api/connect/toss"): "toss_key_change",
    ("DELETE", "/api/connect/toss"): "toss_key_delete",
    ("PUT", "/api/connect/dart"): "dart_key_change",
    ("DELETE", "/api/connect/dart"): "dart_key_delete",
}

# SPEC 7-4 목록 가운데 아직 길이 없는 일과 그 길을 만드는 항목(길이 생기면 MONEY_ROUTES로 옮겨요).
NOT_BUILT: dict[str, str] = {
    "live_start": "T-60", "live_amount": "T-63", "live_limits": "T-63", "live_strategy": "T-63",
    "live_resume_buys": "T-62", "live_end": "T-63", "live_sell_all_end": "T-63",
    "todo_match_account": "T-70", "todo_corp_action": "T-70", "todo_big_order": "T-70",
    "toss_key_view": "T-55", "dart_key_view": "T-55",
    "telegram_key_view": "T-52", "telegram_key_change": "T-52", "telegram_key_delete": "T-52",
    "restore": "T-53", "install_place": "T-55", "data_delete": "T-53", "unknown_order_record": "T-70",
}


def _routes(routes: list[Any]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for r in routes:
        inner = getattr(r, "original_router", None)
        if inner is not None:
            out += _routes(inner.routes)
            continue
        for m in sorted((getattr(r, "methods", None) or set()) & {"POST", "PUT", "DELETE", "PATCH"}):
            out.append((m, r.path))
    return out


def test_every_changing_route_is_classified(tmp_path: Path) -> None:
    app = create_app(tmp_path / "data", scheduler=False, keyfile=False)
    found = set(_routes(app.routes))
    unknown = found - set(NOT_MONEY) - set(MONEY_ROUTES)
    assert not unknown, f"분류 안 된 바꾸는 길: {sorted(unknown)}"
    assert set(MONEY_ROUTES) <= found
    # SPEC 7-4 목록 전부가 길(비밀번호) 또는 아직 없음으로 적혀 있어요
    assert set(MONEY_ROUTES.values()) | set(NOT_BUILT) == set(MONEY_ACTIONS)


@pytest.mark.parametrize(("method", "path"), list(MONEY_ROUTES))
def test_money_routes_need_password(tmp_path: Path, method: str, path: str) -> None:
    server = toss_server()
    c = boot(tmp_path / "data", server)
    setup_owner(c)
    c.put("/api/connect/toss", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET})
    c.put("/api/connect/dart", json={"key": "fake-dart-key-0000"})
    body = {"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, "key": "fake-dart-key-1111"}
    send = (lambda h=None: c.request(method, path, json=body, headers=h or {}))
    action = MONEY_ROUTES[(method, path)]
    r = send()
    assert r.status_code == 403 and r.json()["need_confirm"] is True and r.json()["action"] == action
    # 다른 일의 토큰도 안 돼요
    other = next(a for a in MONEY_ACTIONS if a != action)
    assert send(confirm(c, other)).status_code == 403
    h = confirm(c, action)
    assert send(h).status_code == 200
    # 같은 토큰 두 번째는 안 돼요(삭제 뒤라 처음 넣기가 된 PUT은 빼고)
    if method == "DELETE":
        assert send(h).status_code == 403


def test_first_key_needs_login_only(tmp_path: Path) -> None:
    c = boot(tmp_path / "data", toss_server())
    setup_owner(c)
    assert c.put("/api/connect/toss", json={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}).status_code == 200
    assert c.put("/api/connect/dart", json={"key": "fake-dart-key-0000"}).status_code == 200
    r = c.post("/api/confirm", json={"password": "wrong password", "action": "toss_key_change"})
    assert r.status_code == 401 and r.json()["tries_left"] == 4
