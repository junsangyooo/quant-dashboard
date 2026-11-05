"""포트 · 어댑터(P1-06 · ARCHITECTURE 2절 포트 · 어댑터 층 · 4절 확장 지점 · 6절 '바꿔 끼우기' · QUALITY E1).

- 약속(`app/ports.py`)은 Protocol과 그 약속의 오류 종류뿐이고, 이름이 지금 클래스와 겹치지 않아요.
- 실행 흐름(`live` · `paper_v2` · `backtest_v2` · `schedule`)은 어댑터를 가져오지 않고 포트만 받아요(조립이 넣어 줌).
- 어댑터 오류는 포트 오류 종류를 하나씩만 이어받아요(실행 흐름이 포트 이름으로 잡아도 잡히는 것이 전과 같게).
- 토스 어댑터의 메서드 모양(인자 이름 · 종류 · 기본값)이 `Broker` 약속과 같아요(타입은 mypy가 조립에서 봐요).
- 앱의 기본 가짜는 '응답 없음'이고, 응답이 있는 가짜(`tests/fake_toss.py` 등)는 시험에만 있어요.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any, Protocol

import pytest

from app import ports
from app.adapters import dart as dart_adapter
from app.adapters import telegram as tg_adapter
from app.adapters import toss
from app.adapters import transport as tp
from app.adapters.fake import FakeFetch, FakeTransport
from app.main import create_app

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
PORTS = APP / "ports.py"
RUN_FLOWS = ("live.py", "paper_v2.py", "backtest_v2.py", "schedule.py")
PROTOCOLS = ("Broker", "MarketFeed", "Disclosures", "Notifier", "Clock")
# 포트 오류 → 그 오류를 이어받는 어댑터 오류(하나씩)
ERROR_MAP: dict[type[BaseException], type[BaseException]] = {
    ports.NoAnswer: tp.TransportError,
    ports.BrokerError: toss.TossError,
    ports.BrokerUnreachable: toss.TossUnreachableError,
    ports.BrokerBadAnswer: toss.TossShapeError,
    ports.BrokerRejected: toss.TossApiError,
}


def _classes(path: Path) -> set[str]:
    return {n.name for n in ast.walk(ast.parse(path.read_text(encoding="utf-8"))) if isinstance(n, ast.ClassDef)}


def _imports(path: Path) -> set[str]:
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            base = ("app." if node.level else "") + (node.module or "")
            out.add(base)
            out |= {f"{base}.{a.name}" for a in node.names}
        elif isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
    return out


def _adapter_side(cls: type) -> bool:
    """앱 안 클래스 가운데 포트 파일 밖(포트 오류끼리의 이어받음은 뺌)."""
    return cls.__module__.startswith("app.") and cls.__module__ != ports.__name__


def _all_subclasses(cls: type) -> set[type]:
    out: set[type] = set()
    for sub in cls.__subclasses__():
        out |= {sub} | _all_subclasses(sub)
    return out


# ── 약속 ────────────────────────────────────────────────────────────────────


def test_five_ports_are_protocols() -> None:
    for name in PROTOCOLS:
        cls = getattr(ports, name)
        assert Protocol in cls.__mro__ and getattr(cls, "_is_protocol", False), name
    assert not hasattr(ports, "AiProvider")  # 4단계


def test_ports_hold_only_protocols_and_their_errors() -> None:
    for name, obj in vars(ports).items():
        if isinstance(obj, type) and obj.__module__ == ports.__name__:
            assert getattr(obj, "_is_protocol", False) or issubclass(obj, Exception), name


def test_port_names_do_not_clash_with_app_classes() -> None:
    mine = _classes(PORTS)
    others: set[str] = set()
    for p in sorted(APP.rglob("*.py")):
        if p != PORTS:
            others |= _classes(p)
    assert set(PROTOCOLS) <= mine
    assert mine & others == set()


def test_ports_import_only_the_standard_library() -> None:
    assert {m for m in _imports(PORTS) if m.startswith("app")} == set()


# ── 실행 흐름은 포트만 ──────────────────────────────────────────────────────


@pytest.mark.parametrize("name", RUN_FLOWS)
def test_run_flows_take_ports_not_adapters(name: str) -> None:
    mods = _imports(APP / name)
    adapters = {"app.adapters", "app.toss", "app.transport", "app.dart", "app.telegram", "app.publicip"}
    assert {m for m in mods if any(m == a or m.startswith(a + ".") for a in adapters)} == set()


# ── 오류 종류 ───────────────────────────────────────────────────────────────


def test_adapter_errors_subclass_port_errors_one_to_one() -> None:
    import app.main  # noqa: F401  (앱 모듈을 모두 들여 이어받는 클래스가 다 보이게)

    for port_error, adapter_error in ERROR_MAP.items():
        assert issubclass(adapter_error, port_error)
        app_subs = {c for c in _all_subclasses(port_error) if _adapter_side(c)}
        assert app_subs == {adapter_error} | {c for c in _all_subclasses(adapter_error) if _adapter_side(c)}, \
            port_error.__name__
    # 토스 오류 넷은 BrokerError 아래 · 전송 '응답 없음'은 증권사 오류가 아님(잡히는 범위가 전과 같게)
    assert not issubclass(tp.TransportError, ports.BrokerError)
    assert not issubclass(toss.TossError, ports.NoAnswer)


def test_adapter_errors_keep_their_shape() -> None:
    e = toss.TossApiError(409, "conflict")
    assert (e.status, e.code, str(e)) == (409, "conflict", "HTTP 409 conflict")
    s = toss.TossShapeError("/api/v1/prices", "result")
    assert (s.path, s.what, s.code) == ("/api/v1/prices", "result", "bad-shape")
    assert isinstance(dart_adapter.DartError("x", "network"), Exception)
    assert tg_adapter.TelegramError("x").status == 400


# ── 토스 어댑터 모양 == Broker 약속 ─────────────────────────────────────────


def _shape(fn: Any) -> list[tuple[str, Any, Any]]:
    sig = inspect.signature(fn)
    return [(p.name, p.kind, p.default) for p in sig.parameters.values() if p.name != "self"]


def test_toss_client_matches_broker_signatures() -> None:
    members = [n for n, v in vars(ports.Broker).items() if callable(v) and not n.startswith("_")]
    assert members  # 메서드가 있어요
    for name in members:
        assert _shape(getattr(toss.TossClient, name)) == _shape(getattr(ports.Broker, name)), name
    client = toss.TossClient(toss.TossCredentials("cid", "sec", "acct-7"))
    assert client.credentials.account_no == "acct-7"


def test_dart_store_matches_disclosures_signatures() -> None:
    from app.dart import DartStore

    for name in ("progress", "financial_rows", "disclosures_on"):
        assert _shape(getattr(DartStore, name)) == _shape(getattr(ports.Disclosures, name)), name


# ── 앱의 기본 가짜는 '응답 없음' ───────────────────────────────────────────


def test_app_default_fakes_answer_nothing(tmp_path: Path) -> None:
    app = create_app(tmp_path / "data", scheduler=False, keyfile=False)
    t: tp.Transports = app.state.transports
    for name in ("toss", "dart", "telegram"):
        fake = getattr(t, name)
        assert isinstance(fake, FakeTransport) and fake.responder is None, name
        with pytest.raises(ports.NoAnswer):
            fake(tp.HttpRequest("GET", "https://example.invalid/", {}))
    assert isinstance(t.ip_fetch, FakeFetch)
    with pytest.raises(OSError):
        t.ip_fetch("https://example.invalid/")
    # 실행 흐름이 받는 포트: 증권사는 토스 어댑터(키가 없으면 None) · 시계는 조립의 now
    assert app.state.live.client() is None
    assert app.state.live.now is app.state.scheduler.now is app.state.paper2.now


def test_app_code_never_imports_test_fakes() -> None:
    for p in sorted(APP.rglob("*.py")):
        assert {m for m in _imports(p) if m == "tests" or m.startswith("tests.")} == set(), p
