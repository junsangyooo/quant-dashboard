"""주문 코드가 0개인지 소스를 훑는다.

주문 · 정정 · 취소 · 조건주문 함수와 엔드포인트가 없어야 한다. 실전 모드도 없다.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 화면은 web/src(손으로 쓴 화면 코드 전부)와 web/index.html. 빌드 결과(dist)는 React 같은
# 바깥 묶음이 섞여 있어 소스 쪽을 본다.
WEB_SOURCES = [
    p for p in (ROOT / "web" / "src").rglob("*") if p.is_file() and p.suffix in {".ts", ".tsx", ".css"}
]
SOURCES = sorted(
    [*ROOT.glob("app/*.py"), *WEB_SOURCES, ROOT / "web" / "index.html", ROOT / "start.sh", ROOT / "stop.sh"]
)

FORBIDDEN = [
    r"create_order",
    r"place_order",
    r"submit_order",
    r"cancel_order",
    r"modify_order",
    r"replace_order",
    r"amend",
    r"/orders",
    r"/api/v1/order",
    r"conditional[-_ ]?order",
    r"LivePermit",
    r"LIVE_ORDERS",
    r"live[_-]?mode",
    r"buy_order|sell_order",
    r"def\s+\w*order\w*\s*\(",
    r"정정",
    r"조건주문",
    r"실전\s*모드",
]
# 'cancel'은 asyncio 작업 정리에만 쓴다
CANCEL_OK = {"task.cancel()", "asyncio.CancelledError"}


def test_sources_exist() -> None:
    names = {p.name for p in SOURCES}
    assert {"toss.py", "main.py", "engine.py", "main.tsx", "index.html", "start.sh"} <= names
    assert len(WEB_SOURCES) > 20  # 화면 코드를 실제로 훑는지
    assert not (ROOT / "static").exists()  # 옛 화면은 삭제했다


def test_no_order_words() -> None:
    hits = []
    for path in SOURCES:
        text = path.read_text(encoding="utf-8")
        for pat in FORBIDDEN:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                line = text[: m.start()].count("\n") + 1
                hits.append(f"{path.relative_to(ROOT)}:{line}: {pat}")
        for i, line in enumerate(text.splitlines(), 1):
            if "cancel" in line.lower() and not any(ok in line for ok in CANCEL_OK):
                hits.append(f"{path.relative_to(ROOT)}:{i}: cancel")
    assert hits == []


def test_toss_client_sends_get_only() -> None:
    """토스로 나가는 요청: POST는 토큰 받기 하나, 나머지는 GET."""
    tree = ast.parse((ROOT / "app" / "toss.py").read_text(encoding="utf-8"))
    methods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "HttpRequest":
            first = node.args[0]
            assert isinstance(first, ast.Constant)
            url = ast.unparse(node.args[1])
            methods.append((first.value, url))
    assert methods == [("POST", "f'{self.base}/oauth2/token'"), ("GET", "url")]
    # 공개 메서드는 조회뿐
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "TossClient")
    public = sorted(f.name for f in cls.body if isinstance(f, ast.FunctionDef) and not f.name.startswith("_"))
    assert public == ["account", "buying_power", "call", "holdings", "prices", "token"]


def test_api_routes_have_no_trading() -> None:
    from app.main import create_app

    app = create_app(ROOT / "tests" / ".tmp" / "routes", scheduler=False)
    paths = []
    for r in app.routes:
        path = getattr(r, "path", "")
        methods = getattr(r, "methods", set()) or set()
        paths.append((path, sorted(methods)))
        assert "order" not in path.lower()
        assert "live" not in path.lower()
    posts = sorted(p for p, m in paths if "POST" in m)
    assert posts == sorted(
        [
            "/api/setup",
            "/api/login",
            "/api/recover",
            "/api/password",
            "/api/public-ip",
            "/api/logout",
            "/api/connect/toss/check",
            "/api/strategies",
            "/api/strategies/{sid}/versions",
            "/api/strategies/{sid}/check",
            "/api/import/preview",
            "/api/import/accept",
            "/api/backtest",
            "/api/paper/start",
            "/api/paper/judge",
            "/api/paper/stop",
        ]
    )


def test_server_binds_localhost_only() -> None:
    text = (ROOT / "start.sh").read_text(encoding="utf-8")
    hosts = re.findall(r"--host\s+(\S+)", text)
    assert hosts and set(hosts) == {"127.0.0.1"}
