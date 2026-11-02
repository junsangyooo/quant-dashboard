"""주문은 가짜 전송에서만(TASKS T-00 · DEVELOPING 3절).

- 실제 전송 객체(urllib · http.client · socket · 바깥 라이브러리)는 `app/transport.py` 한 곳에서만,
  `QUANT_LIVE_TRANSPORT=1` **과** 설치기 설정 파일이 둘 다 있을 때만 만들어요.
- 아무 설정 없이 켠 앱의 토스 · DART · 텔레그램 · 공인 IP · 시세 전송은 모두 가짜예요.
- 주문은 토스 전송을 지나가요. 기본 전송으로 주문을 보내면 가짜 전송에 적히고 바깥으로 0건이에요.
- 시험 전체에서 바깥 소켓 시도는 0개예요(`conftest.py`가 세고, 0이 아니면 시험 전체가 실패해요).
"""

from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from app import transport as tp
from app.main import create_app
from app.toss import TossClient, TossCredentials, TossUnreachableError
from app.transport import FakeTransport, HttpRequest, Transports, build_transports, live_enabled
from tests import conftest

ROOT = Path(__file__).resolve().parent.parent
APP_SOURCES = sorted(ROOT.glob("app/*.py"))
GATE = ROOT / "app" / "transport.py"

# 바깥으로 나가는 수단. transport.py 밖의 앱 코드에서는 0건이어야 해요.
NETWORK_MODULES = {"urllib.request", "http.client", "socket", "ssl", "requests", "httpx", "aiohttp"}
NETWORK_CALLS = re.compile(r"urlopen|create_connection|_urllib_transport|_urllib_fetch")


def _imports(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names}
    return out


def network_hits(paths: list[Path]) -> list[str]:
    """transport.py 밖에서 실제 전송을 만드는 코드를 찾아요."""
    hits = []
    for path in paths:
        if path == GATE:
            continue
        text = path.read_text(encoding="utf-8")
        mods = _imports(ast.parse(text))
        for mod in sorted(mods & NETWORK_MODULES):
            hits.append(f"{path.name}: import {mod}")
        if "yfinance" in mods or "yfinance" in text:
            hits.append(f"{path.name}: yfinance")
        for m in NETWORK_CALLS.finditer(text):
            hits.append(f"{path.name}:{text[: m.start()].count(chr(10)) + 1}: {m.group()}")
        if path.name != "main.py" and re.search(r"\bbuild_transports\s*\(", text):
            hits.append(f"{path.name}: build_transports")
    return hits


# ── ① 아무 설정 없이 켠 앱 · 시험에서 실제 전송 객체가 없어요 ─────────────────


def test_app_without_settings_has_only_fake_transports(tmp_path: Path) -> None:
    app = create_app(tmp_path / "data", scheduler=False)
    t: Transports = app.state.transports
    assert t.is_live is False
    for name in ("toss", "dart", "telegram", "ip_fetch"):
        assert tp.is_fake(getattr(t, name)), name
    assert type(app.state.market.source).__name__ == "TossSource"  # 시세도 토스 전송(가짜)으로만
    # 앱이 쓰는 토스 전송도 가짜
    assert tp.is_fake(app.state.connections.transport_factory())


def test_toss_client_default_transport_is_fake() -> None:
    client = TossClient(TossCredentials("cid", "sec"))
    assert tp.is_fake(client.transport)
    with pytest.raises(TossUnreachableError):
        client.token()
    assert [r.url for r in client.transport.calls] == ["https://openapi.tossinvest.com/oauth2/token"]  # type: ignore[attr-defined]


def test_order_request_on_default_transport_stays_in_fake(tmp_path: Path) -> None:
    """주문 요청(POST /api/v1/orders 꼴)을 기본 전송으로 보내면 가짜에 적히고 끝나요."""
    t = build_transports(env={}, config_paths=[])
    order = HttpRequest(
        "POST",
        "https://openapi.tossinvest.com/api/v1/orders",
        {"content-type": "application/json"},
        json.dumps({"symbol": "005930", "side": "BUY", "quantity": "1"}).encode(),
    )
    with pytest.raises(tp.TransportError):
        t.toss(order)
    assert isinstance(t.toss, FakeTransport) and t.toss.calls == [order]


# ── ② 환경 변수만 · 설정 파일만 있을 때도 가짜 ────────────────────────────────


def _config(tmp_path: Path, value: object) -> Path:
    path = tmp_path / "live-transport.json"
    path.write_text(json.dumps({"live_transport": value}), encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("env", "file_value", "live"),
    [
        ({}, None, False),  # 아무것도 없음
        ({"QUANT_LIVE_TRANSPORT": "1"}, None, False),  # 환경 변수만
        ({}, True, False),  # 설정 파일만
        ({"QUANT_LIVE_TRANSPORT": "0"}, True, False),  # 환경 변수가 1이 아님
        ({"QUANT_LIVE_TRANSPORT": "true"}, True, False),
        ({"QUANT_LIVE_TRANSPORT": "1"}, False, False),  # 파일이 '끔'
        ({"QUANT_LIVE_TRANSPORT": "1"}, "true", False),  # 글자 'true'는 켬이 아님
        ({"QUANT_LIVE_TRANSPORT": "1"}, True, True),  # 둘 다 있을 때만
    ],
)
def test_live_needs_both_keys(tmp_path: Path, env: dict[str, str], file_value: object, live: bool) -> None:
    paths = [] if file_value is None else [_config(tmp_path, file_value)]
    assert live_enabled(env, paths) is live
    if not live:
        t = build_transports(env, paths)
        assert t.is_live is False and all(tp.is_fake(x) for x in (t.toss, t.dart, t.telegram, t.ip_fetch))


def test_broken_config_file_is_fake(tmp_path: Path) -> None:
    bad = tmp_path / "live-transport.json"
    bad.write_text("{live_transport: true", encoding="utf-8")
    assert live_enabled({"QUANT_LIVE_TRANSPORT": "1"}, [bad, tmp_path / "none.json"]) is False


def test_both_keys_build_real_objects_without_sending(tmp_path: Path) -> None:
    """두 열쇠가 다 있으면 실제 전송 객체가 생겨요(만들기만 하고 부르지 않아요)."""
    t = build_transports({"QUANT_LIVE_TRANSPORT": "1"}, [_config(tmp_path, True)])
    assert t.is_live is True
    assert not any(tp.is_fake(x) for x in (t.toss, t.dart, t.telegram, t.ip_fetch))


def test_env_alone_on_app_is_fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUANT_LIVE_TRANSPORT", "1")
    app = create_app(tmp_path / "data", scheduler=False)
    assert app.state.transports.is_live is False  # 시험은 설정 파일 자리를 비워 둬요(conftest)


# ── ③ 시험 전체에서 바깥 소켓 0개 ──────────────────────────────────────────────


def test_outbound_guard_catches_and_counts() -> None:
    import socket

    before = len(conftest.OUTBOUND_ATTEMPTS)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(RuntimeError, match="network blocked"):
            s.connect(("203.0.113.1", 443))  # 문서용 주소(TEST-NET-3)
    finally:
        s.close()
    assert len(conftest.OUTBOUND_ATTEMPTS) == before + 1
    del conftest.OUTBOUND_ATTEMPTS[before:]  # 일부러 낸 한 건은 지워요


def test_no_outbound_so_far() -> None:
    assert conftest.OUTBOUND_ATTEMPTS == []


# ── 소스 검사: 실제 전송은 transport.py에서만 ─────────────────────────────────


def test_sources_exist() -> None:
    names = {p.name for p in APP_SOURCES}
    assert {"toss.py", "main.py", "transport.py", "publicip.py", "market.py"} <= names


def test_real_transport_only_in_gate() -> None:
    assert network_hits(APP_SOURCES) == []


def test_no_yahoo_dependency() -> None:
    """T-11: 야후(yfinance)는 requirements와 앱 코드에서 0(회귀 시험 자료는 그대로 · Q-L7)."""
    for req in ROOT.glob("requirements*.txt"):
        assert "yfinance" not in req.read_text(encoding="utf-8"), req.name
    for path in [*APP_SOURCES, ROOT / "start.sh"]:
        assert "yfinance" not in path.read_text(encoding="utf-8").lower(), path.name


def test_gate_builds_real_objects_only_behind_live_check() -> None:
    tree = ast.parse(GATE.read_text(encoding="utf-8"))
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "build_transports")
    first = fn.body[0]
    # 첫 문장이 'if not live_enabled(...): return fake_transports()'
    assert isinstance(first, ast.If)
    assert "live_enabled" in ast.unparse(first.test) and ast.unparse(first.test).startswith("not ")
    assert ast.unparse(first.body[0]) == "return fake_transports()"
    # 실제 전송 함수 이름은 build_transports 안(검사 뒤)과 정의에만 나와요
    names = [
        (n.id, getattr(n, "lineno", 0))
        for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id in {"_urllib_transport", "_urllib_fetch", "YahooSource"}
    ]
    assert names and all(fn.lineno <= line <= (fn.end_lineno or 0) for _, line in names)


# ── ④ 일부러 실제 전송을 부르는 코드를 넣으면 시험이 실패해요 ──────────────────


def test_planted_real_call_is_caught_by_source_scan(tmp_path: Path) -> None:
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import urllib.request\n\n"
        "def send_order():\n"
        "    return urllib.request.urlopen('https://openapi.tossinvest.com/api/v1/orders')\n",
        encoding="utf-8",
    )
    hits = network_hits([*APP_SOURCES, planted])
    assert hits == ["planted.py: import urllib.request", "planted.py:4: urlopen"]


def test_planted_real_call_fails_a_test_run() -> None:
    """실제 전송(transport.py의 실제 함수)을 부르는 시험 파일을 넣고 pytest를 돌리면 실패해요."""
    planted_dir = ROOT / "tests" / ".tmp" / "planted"
    planted_dir.mkdir(parents=True, exist_ok=True)
    planted = planted_dir / "test_planted_live_call.py"
    planted.write_text(
        textwrap.dedent(
            """
            from app.transport import HttpRequest, _urllib_transport

            def test_sends_real_order():
                req = HttpRequest("POST", "https://openapi.tossinvest.com/api/v1/orders", {}, b"{}")
                try:
                    _urllib_transport(req)
                except Exception:
                    pass  # 예외를 삼켜도 바깥 시도는 적혀서 시험 전체가 실패해요
            """
        ),
        encoding="utf-8",
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "-p", "no:warnings", "--basetemp", str(planted_dir / "bt"),
             "--rootdir", str(ROOT), "-c", str(ROOT / "pytest.ini"), str(planted)],
            cwd=ROOT, capture_output=True, text=True, timeout=120,
            env={k: v for k, v in os.environ.items() if "proxy" not in k.lower()},
        )
    finally:
        planted.unlink(missing_ok=True)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 1, out
    assert "바깥으로 나가려 한 시도" in out and "openapi.tossinvest.com" in out


# ── 그대로 두는 것 ────────────────────────────────────────────────────────────


def test_server_binds_localhost_only() -> None:
    text = (ROOT / "start.sh").read_text(encoding="utf-8")
    hosts = re.findall(r"--host\s+(\S+)", text)
    assert hosts and set(hosts) == {"127.0.0.1"}
    assert "0.0.0.0" not in text
    assert "QUANT_LIVE_TRANSPORT" not in text  # 켜 볼 때도 가짜
