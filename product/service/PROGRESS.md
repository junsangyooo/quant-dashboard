# 진행 기록

일감마다 바로 아래 표에 한 줄씩 더해요. 지우거나 고치지 않고 덧붙이기만 해요. 자세한 결과는 `TASKS.md`의 결과 줄과 `tests/baseline/reports/`에 있어요.

| 날짜 | 일감 | 결과 | 검토 판정 | 가정 · 남은 질문 |
|---|---|---|---|---|
| 2026-11-04 | P1-00 시작 점검 | `service-v5` 생성 · push · 훅 거절 확인 · 도구 7종 정확한 판 · 화면 1장 · pytest 1426 통과 / 21 실패(`tests/baseline/reports/P1-00.md`) | 증거 확인 · 통과(검토자 없음) | 기존 실패 18건(문서 ↔ 코드 어긋남 · 단언 · 기대값을 바꿔야 풀림) → Q-N18 · **1단계를 멈추고 물음** |

## 남은 것
1단계에서 고치지 않은 원래 있던 미달이에요(`QUALITY.md` 7절). 덧붙이기만 해요.

| 규칙 | 자리 | 무엇 | 고칠 단계 |
|---|---|---|---|
| 시험(QUALITY 6절 · 문서 ↔ 코드 대조) | `tests/test_catalog.py` 17건 · `tests/test_copytext.py::test_forbidden_list_is_the_glossary` | `f33e2a9`가 `DATA-CATALOG.md` 1절 표 · `GLOSSARY.md` 5절을 고쳤는데 `app/catalog.py` · `web/tests/forbiddenWords.json`은 그대로라 깨끗한 상태에서도 실패 | Q-N18의 답에 따라(1단계 P1-02 앞 또는 3단계) |
