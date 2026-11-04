"""P1-01a 기준선: 얼린 시험 입력 · 정답(`tests/baseline/frozen/`)이 지금 값과 같고, v3 엔진만으로 다시 돌아요.

`app.engine` · `app.copytext` · `app.blocks`와 얼린 파일만 써요(P1-03 뒤 · 지운 v1 · MVP 모듈은 가져오지 않음).
- 얼린 326개를 v3 엔진으로 다시 돌려 거래 · 건너뜀 · 값 없음 기록 · 끝 자산 · 남은 보유가 모두 같음(다 됐다 A).
- 재생 코드 경로가 지운 모듈을 가져오지 않음(새 프로세스에서 `sys.modules` 검사).
- v1에서 나온 시험 입력(얼린 것)이 v3 변환으로 얼린 정답을 내줌(다 됐다 B의 v3 쪽).
- `test_frozen_legacy_body_through_api`는 본문을 DB에 직접 넣고 v2 라우트로 읽어요(P1-03 전에는 지운 MVP 라우트
  `/api/strategies`로 넣었음 · 정답은 얼린 값 그대로).
P1-03 전에는 2부(`test_v1_*` 6건)가 지울 v1 코드가 지금 만드는 값이 얼린 값과 같음을 보였고(다 됐다 B의 v1 쪽 · P1-01a 5절),
v1 코드와 함께 지웠어요(얼린 파일은 `f232bdf`에서 만든 것이 기준).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app import blocks as bk
from app import copytext as ct
from app.engine import run_backtest
from tests.baseline import replay

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = ("app.v1", "app.engine_v1", "app.strategy", "app.engine_mvp", "app.paper", "app.graph", "app.pieces",
             "tests.regression", "tests.helpers")

CASES = replay.load_cases()
BARS = replay.load_bars()
FX = replay.load_v1_fixtures()


def test_frozen_counts() -> None:
    assert len(CASES) == 252 + 10 + 4 + 60
    by = {}
    for c in CASES:
        by[c["source"]] = by.get(c["source"], 0) + 1
    assert by == {"regression": 252, "paper": 10, "example": 4, "random": 60}
    assert len({c["id"] for c in CASES}) == len(CASES)
    assert set(BARS) == {"seed-11", "seed-23", "seed-47", "example-big10"}
    assert {c["bars"] for c in CASES} <= set(BARS)
    assert all(c["v3_body"]["converted"] == "v1" for c in CASES)
    assert sum(len(c["trades"]) for c in CASES) == 23602


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_replay_frozen_case_with_v3_engine_only(case: dict) -> None:  # type: ignore[type-arg]
    """얼린 v3 본문 + 일봉 → v3 엔진 → 얼린 거래(사유 · 판단일 · 종류) · 건너뜀(까닭) · 값 없음 · 끝 자산 · 보유."""
    got = replay.run_case(case, BARS)
    assert replay.diff_case(case, got) == []
    assert got["trades"] == case["trades"]


def test_replay_module_imports_nothing_slated_for_deletion() -> None:
    """재생 코드 경로(`tests/baseline/replay.py` + `app.engine`)는 지울 모듈을 가져오지 않아요.

    같은 프로세스에서는 다른 시험 파일이 이미 가져왔을 수 있어서 새 프로세스에서 `sys.modules`를 봐요."""
    src = (ROOT / "tests" / "baseline" / "replay.py").read_text(encoding="utf-8")
    imports = [line for line in src.splitlines() if line.startswith(("import ", "from "))]
    assert imports and not any(name in line for line in imports for name in FORBIDDEN), imports
    code = (
        "import sys, json\n"
        "from tests.baseline import replay\n"
        "cases = replay.load_cases()\n"
        "pick = {c['source']: c for c in cases}\n"  # 출처마다 하나(코드 경로는 같아요)
        "bad = replay.replay_all(list(pick.values()))\n"
        f"loaded = sorted(m for m in sys.modules if m.startswith({FORBIDDEN!r}))\n"
        "print(json.dumps({'bad': bad, 'loaded': loaded, 'ran': sorted(pick)}))\n"
    )
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout.strip().splitlines()[-1])
    assert out["ran"] == ["example", "paper", "random", "regression"]
    assert out["bad"] == {}
    assert out["loaded"] == []


def test_frozen_v1_bodies_convert_to_frozen_v3() -> None:
    """회귀 본문 84개(얼린 입력) → `copytext.read_body` · `convert_v1`(v3 안의 변환) → 얼린 v3 · 방식(R-C9의 v3 쪽)."""
    assert len(FX["bodies"]) == 84
    for row in FX["bodies"]:
        assert ct.read_body(row["slots"]) == row["v3_from_slots"]
        assert ct.convert_v1(row["normalized"]) == row["v3_from_normalized"]
        for key in ("v3_from_slots", "v3_from_normalized"):
            body = row[key]
            assert body["converted"] == "v1" and bk.analyze(body["graph"])["problems"] == []
            assert bk.mode_of(body["graph"]) == row["mode"]
            assert all(b["match"] == "all" for b in body["graph"]["blocks"])
        nodes = row["normalized"]["graph"]["nodes"]
        weights = sum(1 for n in nodes if n["piece"] in ("equal", "max_per_stock", "rebalance_every"))
        assert len(row["v3_from_normalized"]["graph"]["blocks"]) == len(nodes) - (weights - 1)
    # 문턱 사례의 v3 본문은 같은 본문에서 나와요
    for case in CASES:
        if case["source"] in ("regression", "paper"):
            row = FX["bodies"][case["case"]]
            assert case["v1_body"] == row["slots"] and case["v3_body"] == row["v3_from_normalized"]


def test_frozen_examples_convert_and_copy_text_parse() -> None:
    """옛 예시 4개(얼린 본문) → `convert_v1` = 얼린 v3(R-C8 · R-C9) · v2 복사 글(얼린 글) → 새 전략으로 읽힘."""
    ex = {e["id"]: e for e in FX["examples"]}
    assert list(ex) == ["breakout", "either", "equal", "trend"]  # 옛 v1 예시(EXAMPLES) 순서
    for e in FX["examples"]:
        body = ct.convert_v1(e["body"])
        assert body == e["v3"] and body["converted"] == "v1"
        assert bk.mode_of(body["graph"]) == e["mode"] and bk.analyze(body["graph"])["problems"] == []
        assert e["copy_text"].startswith("quant-strategy/2 ")
    # test_copytext_v3.py test_R_C8_aliases_and_v1_cooldown_zero의 정답
    by_item = {r["item"]: r for b in ex["breakout"]["v3"]["graph"]["blocks"] for r in b["rows"]}
    assert by_item["high_n"]["params"] == {"n": 20}
    assert by_item["turnover"]["value"] == 100 and by_item["turnover"]["op"] == "gte"
    assert by_item["next_open"]["value"] == 0
    assert by_item["stop_loss"]["exec"] == "close" and by_item["stop_loss"]["value"] == 7
    assert by_item["top_n"]["value"] == 5 and by_item["top_n"]["params"] == {"by": "strength", "order": "desc"}
    # test_copytext_v3.py test_v1_and_v2_texts_become_v3의 v2 글 부분
    body2, _ = ct.parse_copy_text(ex["either"]["copy_text"])
    assert [b["stage"] for b in body2["graph"]["blocks"]].count("signal") == 2
    assert "converted" not in body2
    assert next(b for b in body2["graph"]["blocks"] if b["stage"] == "buy")["rows"][0]["value"] == 1
    for case in CASES:
        if case["source"] == "example":
            assert case["v1_body"] == ex[case["id"].removeprefix("example-")]["body"]
            assert case["v3_body"] == ex[case["id"].removeprefix("example-")]["v3"]


def test_frozen_legacy_bodies_read_as_v3() -> None:
    """`helpers.legacy`가 만들던 옛 빈 본문(얼린 것) → `read_body` = 얼린 v3(test_api_v2 test_old_body_reads_as_v3)."""
    assert len(FX["legacy"]) == 16
    for row in FX["legacy"]:
        body = ct.read_body(row["body"])
        assert body == row["v3"] and body["converted"] == "v1"
        stages = [b["stage"] for b in body["graph"]["blocks"]]
        if row["template"] == "event":
            assert stages[:2] == ["universe", "select"]
    old = next(r for r in FX["legacy"] if (r["template"], r["name"]) == ("event", "옛 전략"))
    assert old["body"]["name"] == "옛 전략" and old["body"]["template"] == "event"


def test_frozen_legacy_body_through_api(app_client) -> None:  # type: ignore[no-untyped-def]
    """test_api_v2.py test_old_body_reads_as_v3와 같은 길(본문을 DB에 직접 넣고 v2 라우트로 읽음)을 얼린 입력으로."""
    from tests.conftest import setup_owner
    from tests.helpers import store_v1_body

    setup_owner(app_client)
    old = next(r for r in FX["legacy"] if (r["template"], r["name"]) == ("event", "옛 전략"))
    sid = store_v1_body(app_client.app_ref.state.db, old["body"])  # P1-03: 지운 MVP 라우트 대신 DB에 직접
    got = app_client.get(f"/api/v2/strategies/{sid}").json()
    assert [b["stage"] for b in got["body"]["graph"]["blocks"]][:2] == ["universe", "select"]
    assert got["body"]["converted"] == "v1"
    assert got["body"] == old["v3"]


def test_frozen_R_B3_v1_trades_match_v3_engine() -> None:
    """test_engine_v2.py test_R_B3: 얼린 `run_v1` 거래(7열) = v3 엔진으로 돌린 변환 본문의 거래."""
    rb = FX["R_B3"]
    body = FX["bodies"][rb["body_index"]]["slots"]
    r2 = run_backtest(ct.convert_v1(body), BARS[rb["bars"]], None, rb["start"], rb["end"], rb["cash"], check=False)
    assert [[t[k] for k in rb["keys"]] for t in r2["trades"]] == rb["v1_trades"]
    assert rb["v1_trades"]  # 거래가 있어요
