"""저장 층(P1-07 · ARCHITECTURE 2절 '저장' · 7절 'SQL 위치'): SQL과 sqlite3 연결은 `app/store/`에만 있고, 트랜잭션 경계는
옮기기 전과 같아요(`DB`는 자동 커밋 · `tx()` · `many()`만 BEGIN … COMMIT). SQL 글의 자리 셈은 `tests/test_structure.py`
(허용 목록 `tests/allow/sql.txt` · 0줄)가 보고, 여기는 그 셈이 보지 않는 꼴(연결 · 커서를 직접 쓰기 · 시각 읽기)과 경계를 봐요.
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.store import market as market_store
from app.store import runs as run_store
from app.store import strategies as strategy_store
from app.store.db import DB

ROOT = Path(__file__).resolve().parent.parent
APP = ROOT / "app"
STORE = APP / "store"
EXECUTE = {"execute", "executemany", "executescript"}
CLOCK_CALLS = {("datetime", "now"), ("datetime", "utcnow"), ("date", "today"), ("time", "time"),
               ("time", "monotonic"), ("time", "perf_counter")}


def connection_hits(paths: list[Path]) -> list[str]:
    """sqlite3 import · `.conn`(DB 연결) · `.execute*()` 호출 자리."""
    hits = []
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import) and any(a.name.split(".")[0] == "sqlite3" for a in node.names):
                hits.append(f"{path.name}:{node.lineno}: import sqlite3")
            elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "sqlite3":
                hits.append(f"{path.name}:{node.lineno}: from sqlite3")
            elif isinstance(node, ast.Attribute) and node.attr == "conn":
                hits.append(f"{path.name}:{node.lineno}: .conn")
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in EXECUTE:
                hits.append(f"{path.name}:{node.lineno}: .{node.func.attr}()")
    return hits


def clock_hits(paths: list[Path]) -> list[str]:
    """`datetime.now()` · `date.today()` · `time.time()` 같은 지금 시각 읽기."""
    hits = []
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                    isinstance(node.func.value, ast.Name) and (node.func.value.id, node.func.attr) in CLOCK_CALLS:
                hits.append(f"{path.name}:{node.lineno}: {node.func.value.id}.{node.func.attr}()")
    return hits


def test_sqlite_connection_only_in_store() -> None:
    outside = [p for p in sorted(APP.rglob("*.py")) if not p.is_relative_to(STORE)]
    inside = sorted(STORE.rglob("*.py"))
    assert outside and connection_hits(outside) == []
    assert connection_hits(inside)  # 저장 층은 써요(장치가 살아 있는지)


def test_connection_scan_catches_planted_access(tmp_path: Path) -> None:
    planted = tmp_path / "planted.py"
    planted.write_text("import sqlite3 as sq\nfrom sqlite3 import Row\n\ndef f(db, con):\n"
                       "    db.conn.execute('x')\n    con.executemany('y', [])\n    con.executescript('z')\n",
                       encoding="utf-8")
    assert sorted(h.split(": ", 1)[1] for h in connection_hits([planted])) == sorted(
        ["import sqlite3", "from sqlite3", ".conn", ".execute()", ".executemany()", ".executescript()"])


def test_store_never_reads_the_clock() -> None:
    """시각은 부르는 쪽이 값으로 넘겨요(기준선 시계 고정 자리 · Q-N24의 직접 읽는 곳은 옮기지 않음)."""
    inside = sorted(STORE.rglob("*.py"))
    assert inside and clock_hits(inside) == []
    assert clock_hits([APP / "market.py"])  # 장치가 살아 있는지(`market.now_kst`의 `datetime.now`)


def _traced(db: DB) -> list[str]:
    seen: list[str] = []
    db.conn.set_trace_callback(seen.append)
    return seen


def _words(seen: list[str]) -> list[str]:
    return [s.split()[0].upper() for s in seen]


def test_transaction_boundaries_are_the_old_ones(tmp_path: Path) -> None:
    """한 트랜잭션이던 묶음만 BEGIN … COMMIT · 나머지는 문장마다 자동 커밋(옮기기 전 `api_v2` · `market` · `live`와 같음)."""
    db = DB(tmp_path / "t.db")
    at = "2025-06-02T08:00:00+00:00"
    sid = strategy_store.add_strategy(db, "a", "", None, at)
    seen = _traced(db)
    vid, no = strategy_store.add_version(db, sid, "{}", 0, at, name="a", template="")
    assert (vid, no) == (1, 1)
    assert _words(seen) == ["BEGIN", "SELECT", "INSERT", "UPDATE", "COMMIT"]  # 전 `api_v2.save`의 `with db.tx()`
    seen.clear()
    strategy_store.delete_strategy(db, sid)
    assert _words(seen) == ["BEGIN", "DELETE", "DELETE", "COMMIT"]  # 전 `api_v2.delete`의 `with db.tx()`
    seen.clear()
    market_store.put_bars(db, "005930", [{"d": "2025-06-02", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}] * 2)
    words = _words(seen)
    assert words[0] == "BEGIN" and words[-1] == "COMMIT" and set(words[1:-1]) == {"INSERT"}  # 전 `DB.many`
    seen.clear()
    run_store.save_state(db, 1, "{}", at, {"A": {"qty": 1, "avg": 1.0}, "B": {"qty": 2, "avg": 2.0}})
    assert _words(seen) == ["INSERT", "DELETE", "INSERT", "INSERT"]  # 전 `Live.save`: 묶지 않음(문장마다 커밋)
    seen.clear()
    oid = run_store.add_order(db, 1, "2025-06-02", "005930", "buy", 1, "q1", None, "open_buy", 1, 100.0, "DAY",
                              "sending", "{}", at)
    assert _words(seen) == ["INSERT"] and run_store.order(db, oid)["status"] == "sending"
