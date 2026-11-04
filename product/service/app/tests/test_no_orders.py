"""주문은 가짜 전송에서만(TASKS T-00 · DEVELOPING 3절).

- 실제 전송 객체(urllib · http.client · socket · 바깥 라이브러리)는 `app/transport.py` 한 곳에서만,
  `QUANT_LIVE_TRANSPORT=1` **과** 설치기 설정 파일이 둘 다 있을 때만 만들어요.
- 아무 설정 없이 켠 앱의 토스 · DART · 텔레그램 · 공인 IP · 시세 전송은 모두 가짜예요.
- 주문은 토스 전송을 지나가요. 기본 전송으로 주문을 보내면 가짜 전송에 적히고 바깥으로 0건이에요.
- 시험 전체에서 바깥 소켓 시도는 0개예요(`conftest.py`가 세고, 0이 아니면 시험 전체가 실패해요).

소스 검사의 범위(P1-02 ②): 앱 코드 `app/**/*.py`(하위 폴더까지 · 뒤 일감이 만들 `domain/` · `adapters/` · `store/` ·
`run/` · `api/` · `services/` 포함). 금지 목록은 실제 전송 수단(`NETWORK_MODULES`)에 더해 AI 제공사 SDK(4단계 전에는 앱이
AI를 부르지 않고, 붙일 때도 `transport.py` 한 문으로만 · DEVELOPING 3절) · `urllib3` · `websockets`(전송 수단) ·
`subprocess`(앱이 다른 프로그램을 띄우지 않아요)예요. `tests/`와 `tests/baseline/` 도구는 대상이 아니에요: 시험 · 기준선
도구는 pytest · npm · node · 서버를 자식 프로세스로 띄워야 해서 `subprocess`를 쓰고, 앱 코드가 아니라 전송 문을 지나지
않아요(바깥 소켓은 conftest가 따로 0으로 막아요).
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


def app_sources(root: Path) -> list[Path]:
    """검사 대상: `root/app/**/*.py`(하위 폴더까지 · P1-02 ②)."""
    return sorted((root / "app").rglob("*.py"))


APP_SOURCES = app_sources(ROOT)
GATE = ROOT / "app" / "transport.py"

# 바깥으로 나가는 수단. transport.py 밖의 앱 코드에서는 0건이어야 해요.
NETWORK_MODULES = {"urllib.request", "http.client", "socket", "ssl", "requests", "httpx", "aiohttp"}
NETWORK_CALLS = re.compile(r"urlopen|create_connection|_urllib_transport|_urllib_fetch")
# 앱 코드 전체(transport.py 포함)에서 0건이어야 하는 것(P1-02 ②): AI 제공사 SDK(제품 기능인 금지 목록이라 이름을 적어요) ·
# 전송 수단 둘 · 다른 프로그램 띄우기.
AI_SDK_MODULES = {"anthropic", "openai", "google.generativeai", "google.genai", "mistralai", "cohere", "ollama",
                  "litellm", "xai_sdk", "vertexai", "boto3", "botocore", "groq", "together", "replicate",
                  "huggingface_hub", "transformers"}
FORBIDDEN_MODULES = AI_SDK_MODULES | {"urllib3", "websockets", "websocket", "subprocess", "asyncio.subprocess", "pty"}
FORBIDDEN_PREFIXES = ("langchain",)  # 첫 이름이 이걸로 시작하면 모두(langchain · langchain_openai · langchain_core …)
# import 문이 아닌 길로 모듈을 들이거나 다른 프로그램을 띄우는 꼴(글 검사 · AST가 못 보는 것 · QUALITY E1).
DYNAMIC_CALLS = re.compile(r"import_module\(|__import__\(|create_subprocess_|os\.(?:system|popen|exec\w*|spawn\w*)\("
                           r"|\bpty(?=\.)")  # `pty.` 꼴만 · pty import는 어떤 꼴이든 위 AST 목록(FORBIDDEN_MODULES)이 봐요


def _label(path: Path) -> str:
    """앱 안 파일은 `app/` 기준 상대 경로(하위 폴더가 보이게) · 밖(시험 임시 파일)은 이름만."""
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT / "app") else path.name


def _imports(tree: ast.AST) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names}
    return out


def _forbidden_in(mods: set[str]) -> list[str]:
    """금지 모듈과 그 하위 모듈(`openai.types` · `subprocess.run` 꼴) · 금지 머리말(`langchain*`)이 import됐는지."""
    out = {f for f in FORBIDDEN_MODULES for m in mods if m == f or m.startswith(f + ".")}
    out |= {m.split(".")[0] for m in mods if m.split(".")[0].startswith(FORBIDDEN_PREFIXES)}
    return sorted(out)


def network_hits(paths: list[Path]) -> list[str]:
    """transport.py 밖에서 실제 전송을 만드는 코드를 찾아요."""
    hits = []
    for path in paths:
        if path == GATE:
            continue
        text = path.read_text(encoding="utf-8")
        mods = _imports(ast.parse(text))
        for mod in sorted(mods & NETWORK_MODULES):
            hits.append(f"{_label(path)}: import {mod}")
        if "yfinance" in mods or "yfinance" in text:
            hits.append(f"{_label(path)}: yfinance")
        for m in NETWORK_CALLS.finditer(text):
            hits.append(f"{_label(path)}:{text[: m.start()].count(chr(10)) + 1}: {m.group()}")
        if path.name != "main.py" and re.search(r"\bbuild_transports\s*\(", text):
            hits.append(f"{_label(path)}: build_transports")
    return hits


def forbidden_hits(paths: list[Path]) -> list[str]:
    """앱 코드 전체(transport.py 포함)에서 AI 제공사 SDK · urllib3 · websocket(s) · subprocess import와
    동적 import · 셸 호출 꼴(`import_module(` · `__import__(` · `create_subprocess_*` · `os.system` 등 · `pty`)을 찾아요(P1-02 ②)."""
    hits = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        mods = _imports(ast.parse(text))
        hits += [f"{_label(path)}: import {mod}" for mod in _forbidden_in(mods)]
        for m in DYNAMIC_CALLS.finditer(text):
            hits.append(f"{_label(path)}:{text[: m.start()].count(chr(10)) + 1}: {m.group()}")
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


def test_sources_include_subfolders(tmp_path: Path) -> None:
    """검사 범위가 `app/` 하위 폴더까지예요(뒤 일감의 `domain/` · `adapters/` 등도 저절로 들어와요).

    P1-03 전에는 실제 하위 폴더 `app/v1/`로 봤어요. 그 폴더를 지워 지금 `app/`에는 하위 폴더가 없어서, 같은 셈 함수(`app_sources`)에
    하위 폴더를 심은 임시 뿌리를 주어 봐요."""
    (tmp_path / "app" / "sub").mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "sub" / "__init__.py").write_text("", encoding="utf-8")
    assert tmp_path / "app" / "sub" / "__init__.py" in app_sources(tmp_path)
    assert all(p.is_relative_to(ROOT / "app") for p in APP_SOURCES)


def test_real_transport_only_in_gate() -> None:
    assert network_hits(APP_SOURCES) == []


def test_no_ai_sdk_urllib3_websockets_subprocess_in_app() -> None:
    """AI 제공사 SDK · urllib3 · websockets · subprocess는 앱 코드(transport.py 포함) 어디에도 0건(P1-02 ②)."""
    assert forbidden_hits(APP_SOURCES) == []


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


def test_planted_sdk_in_subfolder_is_caught_by_source_scan(tmp_path: Path) -> None:
    """하위 폴더(`adapters_tmp/x.py` 꼴)에 AI SDK · urllib3 · websockets · subprocess · 실제 전송을 넣으면 두 검사가 잡아요."""
    sub = tmp_path / "app" / "adapters_tmp"
    sub.mkdir(parents=True)
    planted = sub / "x.py"
    planted.write_text(
        "import subprocess\nimport urllib3\nimport websockets\nfrom openai import OpenAI\n"
        "import google.generativeai as genai\nimport anthropic\nimport urllib.request\n",
        encoding="utf-8",
    )
    found = sorted((tmp_path / "app").rglob("*.py"))  # 실제 검사와 같은 방법(rglob)으로 하위 폴더가 보여요
    assert found == [planted]
    assert forbidden_hits(found) == [
        "x.py: import anthropic", "x.py: import google.generativeai", "x.py: import openai",
        "x.py: import subprocess", "x.py: import urllib3", "x.py: import websockets",
    ]
    assert network_hits(found) == ["x.py: import urllib.request"]


def test_planted_dynamic_import_and_shell_calls_are_caught(tmp_path: Path) -> None:
    """import 문 없이 들이는 꼴(`importlib.import_module` · `__import__`) · 셸 · 자식 프로세스(`asyncio.create_subprocess_exec` ·
    `os.system` · `os.popen` · `os.execv` · `os.spawnl` · `pty`) · `langchain*` · `xai_sdk` · `websocket`도 잡혀요."""
    planted = tmp_path / "y.py"
    planted.write_text(
        "import importlib\nimport os\nimport langchain_core.runnables\nimport xai_sdk\nimport websocket\n"
        "from asyncio import create_subprocess_exec\n\n"
        "def run():\n"
        "    importlib.import_module('anthropic')\n"
        "    __import__('openai')\n"
        "    os.system('ls')\n"
        "    os.popen('ls')\n"
        "    os.execv('/bin/ls', ['ls'])\n"
        "    os.spawnl(0, '/bin/ls')\n"
        "    pty.spawn('ls')\n",  # `pty.` 꼴(글 검사) · `import pty` 꼴은 AST 목록이 봐요(아래 시험)
        encoding="utf-8",
    )
    assert forbidden_hits([planted]) == [
        "y.py: import langchain_core", "y.py: import websocket", "y.py: import xai_sdk",
        "y.py:6: create_subprocess_", "y.py:9: import_module(", "y.py:10: __import__(", "y.py:11: os.system(",
        "y.py:12: os.popen(", "y.py:13: os.execv(", "y.py:14: os.spawnl(", "y.py:15: pty",
    ]


def test_planted_pty_import_in_any_form_is_caught(tmp_path: Path) -> None:
    """`pty`는 import 꼴이 무엇이든(`from pty import spawn` · `import os, pty` · 하위 폴더) AST 목록이 잡아요(P1-03a 검토 지적 · QUALITY E1)."""
    sub = tmp_path / "app" / "adapters"
    sub.mkdir(parents=True)
    (sub / "z1.py").write_text("from pty import spawn\n", encoding="utf-8")
    (sub / "z2.py").write_text("import os, pty\n", encoding="utf-8")
    (sub / "z3.py").write_text("x = 'pty'\n", encoding="utf-8")  # 글자만 · 잡히지 않아요
    (sub / "z4.py").write_text("import pty\n", encoding="utf-8")  # 맨 import 꼴
    found = sorted((tmp_path / "app").rglob("*.py"))
    assert forbidden_hits(found) == ["z1.py: import pty", "z2.py: import pty", "z4.py: import pty"]


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
    # 켜기는 app.serve로(127.0.0.1 고정 · T-51). --host를 따로 주면 127.0.0.1만.
    assert "-m app.serve" in text
    hosts = re.findall(r"--host\s+(\S+)", text)
    assert set(hosts) <= {"127.0.0.1"}
    assert "0.0.0.0" not in text
    assert "QUANT_LIVE_TRANSPORT" not in text  # 켜 볼 때도 가짜
