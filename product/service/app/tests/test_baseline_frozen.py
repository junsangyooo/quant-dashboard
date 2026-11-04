"""P1-01a 기준선: 얼린 시험 입력 · 정답(`tests/baseline/frozen/`)이 지금 값과 같고, v3 엔진만으로 다시 돌아요.

이 파일은 두 부분이에요(P1-03이 지울 때 헷갈리지 않게 머리 글로 나눠요).

1부 **v3만 쓰는 시험**(P1-03 뒤에도 그대로 남음 · 예외 하나: `test_frozen_legacy_body_through_api`가 본문을 넣는 길
   `/api/strategies`는 P1-03이 지우는 MVP 라우트라 그때 v2 라우트나 DB 직접 넣기로 **넣는 길만** 바뀜 · 정답은 얼린 값 그대로):
   `app.engine` · `app.copytext` · `app.blocks`와 얼린 파일만 써요.
   - 얼린 326개를 v3 엔진으로 다시 돌려 거래 · 건너뜀 · 값 없음 기록 · 끝 자산 · 남은 보유가 모두 같음(다 됐다 A).
   - 재생 코드 경로가 지울 모듈을 가져오지 않음(새 프로세스에서 `sys.modules` 검사).
   - v1에서 나온 시험 입력(얼린 것)이 v3 변환으로 얼린 정답을 내줌(다 됐다 B의 v3 쪽).
2부 **v1 코드와 대조하는 시험**(P1-03이 이 부분만 지움): 지울 모듈(`app.v1` · `app.engine_v1` · `app.strategy` ·
   `tests.regression` · `tests.helpers.legacy`)이 지금 만드는 값이 얼린 값과 같음을 보여요(다 됐다 B의 v1 쪽).
   함수 이름이 `test_v1_`로 시작하고 import는 함수 안에서만 해요.
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


# ═══════════════════════════════════════════════════════════════════════════════
# 1부. v3만 쓰는 시험 — P1-03 뒤에도 남아요
# ═══════════════════════════════════════════════════════════════════════════════


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
    assert list(ex) == ["breakout", "either", "equal", "trend"]  # app/v1/strategy.py EXAMPLES 순서
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
    """test_api_v2.py test_old_body_reads_as_v3와 같은 길(옛 라우트로 넣고 v2 라우트로 읽음)을 얼린 입력으로."""
    from tests.conftest import setup_owner

    setup_owner(app_client)
    old = next(r for r in FX["legacy"] if (r["template"], r["name"]) == ("event", "옛 전략"))
    sid = app_client.post("/api/strategies", json={"body": old["body"]}).json()["id"]
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


# ═══════════════════════════════════════════════════════════════════════════════
# 2부. v1 코드와 대조하는 시험 — P1-03이 지울 모듈과 함께 이 부분만 지워요
# ═══════════════════════════════════════════════════════════════════════════════


def test_v1_bars_match_frozen() -> None:
    from tests.regression.cases import SEEDS, bar_set
    from tests.regression.v1_inputs import example_bars, random_bars

    assert SEEDS == [11, 23, 47]
    for s in SEEDS:
        assert bar_set(s) == BARS[f"seed-{s}"]
    assert example_bars() == BARS["example-big10"]
    for case in CASES:
        if case["source"] == "random":
            assert random_bars(case["seed"]) == BARS[case["bars"]]


def test_v1_bodies_match_frozen() -> None:
    from app.v1 import strategy as st1
    from tests.regression.cases import bodies

    slots = bodies()
    assert len(slots) == len(FX["bodies"])
    for b, row in zip(slots, FX["bodies"], strict=True):
        assert b == row["slots"]
        norm = st1.normalize(b)
        assert norm == row["normalized"]
        assert st1.mode_of(norm) == row["mode"]


def test_v1_examples_match_frozen() -> None:
    from app.v1 import strategy as st1

    assert [e["id"] for e in st1.EXAMPLES] == [e["id"] for e in FX["examples"]]
    for e in FX["examples"]:
        body = st1.example_body(e["id"])
        assert body == e["body"]
        assert st1.mode_of(body) == e["mode"]
        assert st1.to_copy_text(body) == e["copy_text"]


def test_v1_legacy_helper_matches_frozen() -> None:
    from tests.helpers import legacy

    for row in FX["legacy"]:
        assert legacy(row["template"], row["name"]) == row["body"]


def test_v1_threshold_inputs_match_frozen() -> None:
    """문턱 사례의 v1 본문 · 기간 · v1 거래는 `v1_trades.json`과 같고, v3 본문은 `convert_v1(st1.normalize(v1))`이에요."""
    from app.v1 import strategy as st1
    from tests.regression import threshold as th
    from tests.regression.cases import bodies

    v1 = th.V1
    slots = bodies()
    fixed = [*v1["backtests"], *v1["papers"], *v1["examples"], *v1["randoms"]]
    assert len(fixed) == len(CASES)
    cal = th._calendar(BARS["seed-11"])
    for f, case in zip(fixed, CASES, strict=True):
        body = f["body"] if "body" in f else slots[f["case"]]
        assert case["v1_body"] == body
        assert case["v1_trades"] == f["trades"] and case["v1_final"] == f["final"]
        assert case["cash"] == float(v1["cash"])
        start, end = (cal[f["first"]], cal[f["last"]]) if "first" in f else (f["start"], f["end"])
        assert (case["start"], case["end"]) == (start, end)
        assert case["v3_body"] == ct.convert_v1(st1.normalize(body))
        assert th.compare(case["v1_trades"], [th.trade_key(t) for t in case["trades"]],
                          th._calendar(BARS[case["bars"]]))["kind"] == case["threshold"]["kind"]


def test_v1_run_v1_matches_frozen_R_B3() -> None:
    from app.engine_v1 import run_v1
    from tests.regression.cases import bar_set, bodies

    rb = FX["R_B3"]
    data = bar_set(11)
    r1 = run_v1(bodies()[rb["body_index"]], data, rb["start"], rb["end"], rb["cash"])
    assert [[t[k] for k in rb["keys"]] for t in r1["trades"]] == rb["v1_trades"]
