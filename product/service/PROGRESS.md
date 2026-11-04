# 진행 기록

일감마다 바로 아래 표에 한 줄씩 더해요. 지우거나 고치지 않고 덧붙이기만 해요. 자세한 결과는 `TASKS.md`의 결과 줄과 `tests/baseline/reports/`에 있어요.

| 날짜 | 일감 | 결과 | 검토 판정 | 가정 · 남은 질문 |
|---|---|---|---|---|
| 2026-11-04 | P1-00 시작 점검 | `service-v5` 생성 · push · 훅 거절 확인 · 도구 7종 정확한 판 · 화면 1장 · pytest 1426 통과 / 21 실패(`tests/baseline/reports/P1-00.md`) | 증거 확인 · 통과(검토자 없음) | 기존 실패 18건(문서 ↔ 코드 어긋남 · 단언 · 기대값을 바꿔야 풀림) → Q-N18 · **1단계를 멈추고 물음** |
| 2026-11-04 | P1-01a 얼리기(P1-01의 1/3) | v3 사례 326(회귀 252 · 모의 10 · 예시 4 · 무작위 60 · 일봉 자체) · v1 기대값 5건을 `tests/baseline/frozen/`에 얼림 · v3 엔진만으로 재생 차이 0 · 두 번 sha 동일 · 새 시험 339건 · pytest 1765 통과 / 21 실패(목록 P1-00과 같음) · `tests/baseline/reports/P1-01a.md` | 고친 뒤 통과(심각도 2: 분류 표에 새 파일 자신의 P1-03 참조 누락 → `7a6335c` · `538e454`로 고침 · 재검토 통과) | 가정: 일봉 묶음 4개를 이름으로 가리킴 · `tests/fixtures/yahoo_bars.json`은 지울 시험만 써서 고아가 됨(P1-03에서 처리) · `freeze.py` · `docs_compare.py`는 v1 · 나눌 시험을 가져오므로 P1-03에서 지움 · 덤: `f33e2a9^` 문서 표 == 지금 `app/catalog.py` · `forbiddenWords.json`(Q-N18 (가)의 근거) |

## 남은 것
1단계에서 고치지 않은 원래 있던 미달이에요(`QUALITY.md` 7절). 덧붙이기만 해요.

| 규칙 | 자리 | 무엇 | 고칠 단계 |
|---|---|---|---|
| 시험(QUALITY 6절 · 문서 ↔ 코드 대조) | `tests/test_catalog.py` 17건 · `tests/test_copytext.py::test_forbidden_list_is_the_glossary` | `f33e2a9`가 `DATA-CATALOG.md` 1절 표 · `GLOSSARY.md` 5절을 고쳤는데 `app/catalog.py` · `web/tests/forbiddenWords.json`은 그대로라 깨끗한 상태에서도 실패 | Q-N18의 답에 따라(1단계 P1-02 앞 또는 3단계) |
| 시험(T6 · 엔진 관측 범위) | `tests/baseline/frozen/v3_cases.json` 326개 | 경고 글(`notes`)이 326개 모두 0건이라 이 재생만으로는 경고 글 변화를 못 잡음 · 모의 10건도 `threshold.py` 그대로 백테스트 기간으로 돌린 것이라 `paper_v2` 흐름 관측이 아님 → 경고 글이 나오는 사례와 `paper_v2` 흐름은 P1-01b의 엔진 관측에서 따로 기록 | 1단계 P1-01b |
