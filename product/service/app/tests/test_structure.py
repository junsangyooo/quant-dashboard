"""구조 장치 · 서버(ARCHITECTURE 7절 · TASKS P1-04): 중복(파이썬) · 같은 글 · SQL 위치 · 시각 숫자 + 허용 목록 규칙.

셈은 `tests/baseline/counts.py`(P1-01b 셈 규칙 그대로), 허용 목록과 견주기는 `tests/structure_guards.py`예요. 층은
`tests/test_layers.py`, 웹은 `tests/test_structure_web.py`.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from tests import structure_guards as sg

SERVER = ("sql", "time-literals", "same-text", "py-duplicates")


@pytest.mark.parametrize("name", SERVER)
def test_server_guard_only_decreases(name: str) -> None:
    g = sg.BY_NAME[name]
    found, problems = sg.check(g)
    assert problems == [], "\n".join(problems)
    assert sg.units(dict(found), g.unit) <= g.start


def test_python_duplicates_are_zero() -> None:
    """같은 본문 0 · 모듈 사이 같은 이름 0(5줄 이상 맨 위 공개 함수 · 허용 목록 없음)."""
    assert sg.BY_NAME["py-duplicates"].found() == Counter()


# P1-04 시작 숫자(지운 뒤 · 서버는 P1-03a 보고 · 웹은 P1-03b 보고 5절 '지운 뒤' 열 · 빌드 결과 같은 글만 토큰 셈 20 ·
# 이 일감 보고 `tests/baseline/reports/P1-04.md`)
P1_04_START = {"layers": 12, "sql": 203, "time-literals": 25, "same-text": 38, "py-duplicates": 0,
               "web-boundaries": 33, "web-duplication": 33, "web-same-css": 22, "web-same-text": 20,
               "web-server-same-text": 28, "web-dist-same-text": 20, "web-raw-tokens": 447, "web-px": 9}


def test_start_numbers_only_go_down() -> None:
    """`structure_guards.GUARDS`의 시작 숫자는 뒤 일감이 줄일 수는 있어도 P1-04 기록보다 올릴 수 없어요."""
    start = {g.name: g.start for g in sg.GUARDS}
    assert set(start) == set(P1_04_START)
    assert all(start[k] <= P1_04_START[k] for k in start), start


def test_every_allow_list_parses_with_a_tagged_reason_per_line() -> None:
    names = [g.name for g in sg.GUARDS if g.has_list]
    assert sorted(p.stem for p in sg.ALLOW.glob("*.txt") if p.stem in sg.BY_NAME) == sorted(names)
    for g in sg.GUARDS:
        if g.has_list:
            entries = sg.load(g)  # 꼴이 틀리면 ValueError
            assert sg.units({k: e.count for k, e in entries.items()}, g.unit) <= g.start, g.name


# ── 허용 목록 규칙(일부러 넣은 어긋남 · 가짜 자료) ─────────────────────────────


GUARD = sg.Guard("demo", "시험", 5, lambda: Counter())


def _allowed(text: str, *, text_key: bool = False) -> dict[sg.Key, sg.Entry]:
    return sg.parse(text, text_key=text_key)


def test_compare_passes_only_when_every_key_is_exactly_the_list() -> None:
    allowed = _allowed("a.py x 2  # [P1-07] 까닭\nb.py y 1  # [1단계 예외] 까닭\n")
    assert sg.compare(GUARD, Counter({("a.py", "x"): 2, ("b.py", "y"): 1}), allowed) == []
    assert sg.compare(GUARD, Counter({("a.py", "x"): 3, ("b.py", "y"): 1}), allowed) == ["demo: 새 어긋남 a.py x: 2 → 3"]
    assert sg.compare(GUARD, Counter({("a.py", "x"): 2, ("b.py", "y"): 1, ("c.py", "z"): 1}), allowed) == \
        ["demo: 새 어긋남 c.py z: 1"]
    p = sg.compare(GUARD, Counter({("a.py", "x"): 1, ("b.py", "y"): 1}), allowed)
    assert len(p) == 1 and p[0].startswith("demo: 줄었어요 a.py x: 2 → 1")


def test_compare_caps_the_total_at_the_start_number_even_when_keys_split() -> None:
    """파일을 나눠 키가 갈라져도 전체 수(시작 숫자 5)를 넘으면 실패."""
    allowed = _allowed("a.py x 3  # [P1-07] 까닭\nb.py x 3  # [P1-07] 까닭\n")
    found = Counter({("a.py", "x"): 3, ("b.py", "x"): 3})
    assert sg.compare(GUARD, found, allowed) == ["demo: 허용 목록 6 > P1-04 시작 숫자 5(줄어들기만)",
                                                 "demo: 지금 6 > P1-04 시작 숫자 5(줄어들기만)"]
    g = sg.Guard("demo", "글", 1, lambda: Counter(), text_key=True, unit="keys")
    allowed = _allowed('"가나다라마바사아" 2  # [P1-11] 까닭\n"하나 둘 셋 넷 다섯" 2  # [P1-11] 까닭\n', text_key=True)
    assert sg.compare(g, Counter({("가나다라마바사아",): 2, ("하나 둘 셋 넷 다섯",): 2}), allowed) == \
        ["demo: 허용 목록 2 > P1-04 시작 숫자 1(줄어들기만)", "demo: 지금 2 > P1-04 시작 숫자 1(줄어들기만)"]


@pytest.mark.parametrize("line", [
    "a.py x 2",  # 까닭 없음
    "a.py x 2  #",  # 빈 까닭
    "a.py x 2  # 꼬리표 없음",
    "a.py x 0  # [P1-07] 0이면 지움",
    "a.py x  # [P1-07] 수 없음",
    "a.py x 2  # [P1-04] 이 일감은 꼬리표가 아님",
])
def test_parse_rejects_bad_lines(line: str) -> None:
    with pytest.raises(ValueError):
        sg.parse(line + "\n", text_key=False)


def test_parse_rejects_duplicate_keys_and_reads_json_text_keys() -> None:
    with pytest.raises(ValueError):
        sg.parse("a.py x 1  # [P1-07] 하나\na.py x 1  # [P1-07] 둘\n", text_key=False)
    got = sg.parse('# 머리\n"글 # 안의 샵 · \\"따옴표\\"" 3  # [P1-11] 까닭\n', text_key=True)
    assert list(got) == [('글 # 안의 샵 · "따옴표"',)] and got[('글 # 안의 샵 · "따옴표"',)].count == 3
    line = sg.format_line(('글 # 안의 샵 · "따옴표"',), 3, "[P1-11] 까닭", text_key=True)
    assert sg.parse(line, text_key=True) == {('글 # 안의 샵 · "따옴표"',): sg.Entry(3, "[P1-11] 까닭", 1)}


def test_shrink_only_lowers_counts_and_never_adds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sg, "ALLOW", tmp_path)
    (tmp_path / "demo.txt").write_text("# 머리\na.py x 3  # [P1-07] 하나\nb.py x 1  # [P1-07] 둘\n", encoding="utf-8")
    g = sg.Guard("demo", "시험", 5, lambda: Counter({("a.py", "x"): 2, ("c.py", "x"): 1}))
    notes = sg.shrink(g)
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == "# 머리\na.py x 2  # [P1-07] 하나\n"
    assert any("새 어긋남은 목록에 더하지 않아요" in n for n in notes)
    assert sg.check(g)[1] == ["demo: 새 어긋남 c.py x: 1"]


def test_retake_rewrites_keys_only_when_the_total_goes_down(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """다른 일감을 합친 뒤(예: P1-12) 묶음이 다른 파일 쌍으로 갈라져도 전체가 줄면 다시 재고, 늘면 거절해요."""
    monkeypatch.setattr(sg, "ALLOW", tmp_path)
    (tmp_path / "demo.txt").write_text("# 머리\na.css b.css 3  # [1단계 예외] 있던 까닭\n", encoding="utf-8")
    found = Counter({("a.css", "b.css"): 1, ("a.css", "c.css"): 1})
    g = sg.Guard("demo", "시험", 5, lambda: found, new_reason=lambda k: "[1단계 예외] 새 키")
    assert sg.retake(g)[0].startswith("demo: 다시 잼 3 → 2")
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8") == (
        "# 머리\na.css b.css 1  # [1단계 예외] 있던 까닭\na.css c.css 1  # [1단계 예외] 새 키\n")
    assert sg.check(g)[1] == []
    found[("d.css", "e.css")] = 1  # 전체 3 > 목록 2
    assert "다시 재지 않아요" in sg.retake(g)[0]
    assert (tmp_path / "demo.txt").read_text(encoding="utf-8").count("\n") == 3  # 그대로
    no_reason = sg.Guard("demo", "시험", 5, lambda: Counter({("x.css", "y.css"): 1}))
    assert "까닭이 정해지지 않은" in sg.retake(no_reason)[0]
