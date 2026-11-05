"""조사 견본 · 서버 쪽(TASKS P1-11: 조사는 견본만 얼리고 합치지 않음 · 합치는 것은 3단계).

서버의 조사 함수는 v3 모듈 `app/domain/blocks.py`의 `josa`(받침 판정 `_has_batchim`)뿐이에요(ARCHITECTURE 6절 '1단계 예외' ·
v3 모듈의 한글 글). 지금 내는 글을 글자 그대로 얼려 둬요. 화면 쪽 견본은 `web/tests/particles-samples.test.ts`(P1-03)예요.
두 쪽은 숫자 끝 '로/으로'가 달라요(서버 `josa('버전 1', '로/으로')` = '버전 1으로' · 화면 `josaRo(1)` = '로') · 고치거나
합치지 않고 지금 그대로 얼려요(3단계 조사 한 벌에서 정함 · 보고 `tests/baseline/reports/P1-11.md`).
"""

from __future__ import annotations

import pytest

from app.domain.blocks import _has_batchim, josa

SAMPLES = [
    ("PER", "은/는", "PER은"),
    ("RSI", "은/는", "RSI는"),
    ("ROE", "이/가", "ROE가"),
    ("이동평균", "을/를", "이동평균을"),
    ("거래대금", "이/가", "거래대금이"),
    ("시가총액", "과/와", "시가총액과"),
    ("종목 선정", "과/와", "종목 선정과"),
    ("매수", "을/를", "매수를"),
    ("유니버스", "은/는", "유니버스는"),
    ("10%", "로/으로", "10%로"),
    ("3일", "로/으로", "3일로"),
    ("1 ~ 5", "로/으로", "1 ~ 5로"),
    ("버전 1", "은/는", "버전 1은"),
    ("버전 2", "은/는", "버전 2는"),
    ("버전 3", "은/는", "버전 3은"),
    ("버전 10", "은/는", "버전 10은"),
    ("버전 1", "로/으로", "버전 1으로"),
    ("버전 3", "로/으로", "버전 3으로"),
    ("버전 6", "로/으로", "버전 6으로"),
    ("버전 10", "로/으로", "버전 10으로"),
]


@pytest.mark.parametrize(("word", "pair", "expected"), SAMPLES)
def test_server_josa_samples(word: str, pair: str, expected: str) -> None:
    assert josa(word, pair) == expected


def test_server_batchim_samples() -> None:
    got = {w: _has_batchim(w) for w in ("매수", "신호", "필터", "유니버스", "종목 선정", "매도", "비중", "PER", "RSI", "3", "5")}
    assert got == {"매수": False, "신호": False, "필터": False, "유니버스": False, "종목 선정": True, "매도": False,
                   "비중": True, "PER": True, "RSI": False, "3": True, "5": False}
