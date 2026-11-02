"""변환 일치 문턱(TASKS T-24 · ENGINE-RULES R-C10). 이 시험이 통과해야 화면 · 모의투자 · 실전 단계로 가요.

대상: 회귀 사례(일곱 칸 본문 백테스트 252건 · 모의투자 10건) + 옛 예시 4개 + 무작위 그래프 60개.
표: `tests/regression/conversion_table.md`(전략마다 완전 일치 / 첫 차이 날짜 · 종목).
"""

from __future__ import annotations

import pytest

from tests.regression import threshold as th

ROWS = th.run_all()


def test_counts() -> None:
    assert len(ROWS) == 252 + 10 + 4 + 60


@pytest.mark.parametrize("row", ROWS, ids=[r["name"] for r in ROWS])
def test_conversion_matches_v1(row: dict) -> None:  # type: ignore[type-arg]
    assert row["ok"], row
    if not row["switching"]:
        assert row["kind"] == "same"  # 같은 날 갈아타기가 없으면 거래가 모두 같아야 해요


def test_table_file_is_current() -> None:
    assert th.TABLE.read_text(encoding="utf-8") == th.table(ROWS)


def test_compare_catches_real_differences() -> None:
    cal = ["2026-01-05", "2026-01-06", "2026-01-07"]
    sell = ["2026-01-05", "111111", "sell", 10, "100.0"]
    buy = ["2026-01-05", "222222", "buy", 5, "200.0"]
    late = ["2026-01-06", "222222", "buy", 5, "210.0"]
    assert th.compare([sell, buy], [sell, late], cal)["kind"] == "late_buy"
    # 갈아타기가 없는데 다르면 어긋남
    assert th.compare([buy], [late], cal)["ok"] is False
    # 수량이 다르면 어긋남
    assert th.compare([sell, buy], [sell, ["2026-01-05", "222222", "buy", 4, "200.0"]], cal)["ok"] is False
    # 빠진 매수가 다음 거래일에 없으면 어긋남
    assert th.compare([sell, buy], [sell, ["2026-01-07", "222222", "buy", 5, "220.0"]], cal)["ok"] is False
    # 매도가 빠지면 어긋남
    assert th.compare([sell, buy], [late], cal)["ok"] is False
