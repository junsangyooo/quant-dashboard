"""화면의 그래프 검사(web/src/graph/rules.ts)와 서버(app/graph.py)가 같은 결과를 내도록 묶는 대조 파일이
지금 서버 결과와 같은지 본다(화면 쪽은 web/tests/graphMirror.test.ts가 같은 파일과 대조한다)."""

from __future__ import annotations

from tests.regression.graph_cases import OUT, build, dumps


def test_mirror_fixture_matches_the_server() -> None:
    assert OUT.read_text(encoding="utf-8") == dumps(build()), (
        "app/graph.py 결과가 바뀌었어요 · python -m tests.regression.graph_cases --write 로 다시 만들고 "
        "web 시험(npm test)도 돌려 주세요"
    )
