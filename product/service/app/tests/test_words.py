"""금지어: 서버가 돌려주는 글(GLOSSARY 5절 + SPEC 8-1 · TASKS T-01 · T-71 · P1-03에서 `test_copytext.py`에서 옮김 · 단언 그대로)."""

from __future__ import annotations

import json

import pytest

from tests import words_rules as wr

# 지금 MVP 서버 글에서 걸리는 건수(T-01에서 센 값). 늘어나면 실패하고, T-71에서 0으로 내려요.
SERVER_HITS_LIMIT = 0


def _server_hits() -> list[str]:
    """서버 글 금지어: `app/**/*.py` 하위 폴더까지(P1-02 ② · 뒤 일감이 만들 `domain/` · `api/` 등도 저절로 들어와요)."""
    rules = wr.load_rules()
    out = []
    for path in sorted((wr.APP / "app").rglob("*.py")):
        for line, text in wr.server_strings(path):
            out += [f"{path.relative_to(wr.APP).as_posix()}:{line}: {h}" for h in wr.hits(text, rules)]
    return out


def test_forbidden_list_is_the_glossary() -> None:
    """화면 시험이 읽는 JSON이 GLOSSARY 5절 · SPEC 8-1 표와 같아요(문서를 바꾸면 --write로 다시 만들어요)."""
    rules = wr.load_rules()
    on_disk = json.loads(wr.JSON_PATH.read_text(encoding="utf-8"))
    assert on_disk == rules
    words = {w["word"]: w["except"] for w in rules["words"]}
    # GLOSSARY 5절 표의 낱말과 예외 꼴
    for word in ["고쳐", "넣어요", "넣은 값", "한 줄", "템플릿", "(가져옴)", "(내 전략)", "블록", "전략 바꾸기",
                 "증권사에 걸", "설치 없이 체험", "숫자를 채워 둔", "우리 수량", "장부", "clientOrderId", "OPG"]:
        assert words[word] == [], word
    assert words["넣기"] == ["붙여 넣기"]
    assert words["포트"] == ["리포트", "서포트"]
    assert words["시험"] == ["시험 보내기"]
    assert words["테스트"] == ["백테스트"]
    assert words["칸"] == ["빈칸", "숫자 칸", "입력 칸"]
    assert words["판단"] == ["투자 판단"]
    assert rules["chips"] == ["예시"] and rules["headerChips"] == ["모의투자"]
    # SPEC 8-1 왼쪽 열(‘…’로 끊긴 문구는 조각마다)
    spec = [w["word"] for w in rules["words"] if w["source"] == "SPEC 8-1"]
    assert len(spec) == 37
    assert {"지금 신호 확인", "다른 모의투자 실행 중", "상장폐지 종목 미포함", "평일 16:30 자동 확인", "MVP-xx"} <= set(spec)
    glossary = [w for w in rules["words"] if w["source"] == "GLOSSARY 5"]
    assert len(glossary) == 40


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("조건을 고쳐요 · 블록 추가 · 전략 코드 복사", ["고쳐", "블록", "전략 코드"]),
        ("붙여 넣기 · 백테스트 · 빈칸 · 숫자 칸 · 입력 칸 · 투자 판단 · 시험 보내기 · 리포트", []),
        ("값 넣기 · 시험 결과 · 테스트 · 칸 · 판단", ["넣기", "시험", "테스트", "칸", "판단"]),
        ("11/3(화) 16:30 확인 · 11/4(수) 시가에 모의 체결해요", ["10/29(목) 16:30 확인 · 10/30(금) 시가에 모의 체결해요"]),
        ("실전 운용이나 모의투자 기록이 있는 전략은 삭제할 수 없어요", []),
        ("모의투자 기록이 있는 전략은 삭제할 수 없어요", ["모의투자 기록이 있는 전략은 삭제할 수 없어요"]),
        ("clientOrderId · OPG 주문", ["clientOrderId", "OPG"]),
    ],
)
def test_forbidden_rule_catches_and_allows(text: str, found: list[str]) -> None:
    assert sorted(h.split(": …")[0] for h in wr.hits(text)) == sorted(found)


def test_server_text_forbidden_words() -> None:
    hits = _server_hits()
    print(f"\n서버 글 금지어 {len(hits)}건", *hits, sep="\n  ")
    assert len(hits) <= SERVER_HITS_LIMIT, hits
