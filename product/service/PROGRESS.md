# 진행 기록

일감마다 바로 아래 표에 한 줄씩 더해요. 지우거나 고치지 않고 덧붙이기만 해요. 자세한 결과는 `TASKS.md`의 결과 줄과 `tests/baseline/reports/`에 있어요.

| 날짜 | 일감 | 결과 | 검토 판정 | 가정 · 남은 질문 |
|---|---|---|---|---|
| 2026-11-04 | P1-00 시작 점검 | `service-v5` 생성 · push · 훅 거절 확인 · 도구 7종 정확한 판 · 화면 1장 · pytest 1426 통과 / 21 실패(`tests/baseline/reports/P1-00.md`) | 증거 확인 · 통과(검토자 없음) | 기존 실패 18건(문서 ↔ 코드 어긋남 · 단언 · 기대값을 바꿔야 풀림) → Q-N18 · **1단계를 멈추고 물음** |
| 2026-11-04 | P1-01a 얼리기(P1-01의 1/3) | v3 사례 326(회귀 252 · 모의 10 · 예시 4 · 무작위 60 · 일봉 자체) · v1 기대값 5건을 `tests/baseline/frozen/`에 얼림 · v3 엔진만으로 재생 차이 0 · 두 번 sha 동일 · 새 시험 339건 · pytest 1765 통과 / 21 실패(목록 P1-00과 같음) · `tests/baseline/reports/P1-01a.md` | 고친 뒤 통과(심각도 2: 분류 표에 새 파일 자신의 P1-03 참조 누락 → `7a6335c` · `538e454`로 고침 · 재검토 통과) | 가정: 일봉 묶음 4개를 이름으로 가리킴 · `tests/fixtures/yahoo_bars.json`은 지울 시험만 써서 고아가 됨(P1-03에서 처리) · `freeze.py` · `docs_compare.py`는 v1 · 나눌 시험을 가져오므로 P1-03에서 지움 · 덤: `f33e2a9^` 문서 표 == 지금 `app/catalog.py` · `forbiddenWords.json`(Q-N18 (가)의 근거) |
| 2026-11-04 | P1-01b 서버 관측(P1-01의 2/3) | 시계 고정(`tests/baseline/clock.py` 한 곳 · 5곳 + `now_kst` + 복구 코드 씨앗) · API 모양 라우트 87(남는 66 · 지울 21 · 관측 없음 3은 모두 지울 것) · 엔진 사례 33(경고 글 6 · paper 흐름 7) · 하루 흐름 6일 · `_auto_loop` · 주문 'sending' 선행 순서 시험 · 숫자(줄 14,995 · 모듈 38/남는 27 · 층 어긋남 12 · 중복 0 · SQL 밖 224 · 시각 숫자 26 · 같은 글 41) · 설치된 판 · `python -m tests.baseline.capture` 두 번 바이트 동일 · `compare` 차이 0 · 새 시험 13 · pytest 1778 통과 / 21 실패(목록 같음) · `tests/baseline/reports/P1-01b.md` | 고친 뒤 통과(심각도 2: 시각 숫자 셈이 `.at(h, m)` · `(h, m)` 상수 12곳을 빼먹음 → `b3f667f`로 고침 · 재검토 통과) | 가정: 고정 시각 = conftest `FIXED_NOW`(2025-06-02 17:00 KST) · 층 어긋남은 ARCHITECTURE 2절 표의 '새 자리'로 모듈을 붙여 셈 · 같은 글 규칙 = 길이 8자 이상 + 한글 하나 이상 · 시간은 본체 밖 파일(대조는 `--timing`일 때만) · capture · compare는 Node 24 아니면 실패 · 남는 라우트를 부르는 새 시험을 더하면 API 모양 `optional` 표시가 바뀌므로 기준선을 다시 만들어야 함 |

## 남은 것
1단계에서 고치지 않은 원래 있던 미달이에요(`QUALITY.md` 7절). 덧붙이기만 해요.

| 규칙 | 자리 | 무엇 | 고칠 단계 |
|---|---|---|---|
| 시험(QUALITY 6절 · 문서 ↔ 코드 대조) | `tests/test_catalog.py` 17건 · `tests/test_copytext.py::test_forbidden_list_is_the_glossary` | `f33e2a9`가 `DATA-CATALOG.md` 1절 표 · `GLOSSARY.md` 5절을 고쳤는데 `app/catalog.py` · `web/tests/forbiddenWords.json`은 그대로라 깨끗한 상태에서도 실패 | Q-N18의 답에 따라(1단계 P1-02 앞 또는 3단계) |
| 시험(T6 · 엔진 관측 범위) | `tests/baseline/frozen/v3_cases.json` 326개 | 경고 글(`notes`)이 326개 모두 0건이라 이 재생만으로는 경고 글 변화를 못 잡음 · 모의 10건도 `threshold.py` 그대로 백테스트 기간으로 돌린 것이라 `paper_v2` 흐름 관측이 아님 → 경고 글이 나오는 사례와 `paper_v2` 흐름은 P1-01b의 엔진 관측에서 따로 기록 | 1단계 P1-01b |
| X(ARCHITECTURE 7절 숫자 · 시작값) | `tests/baseline/server/counts.json` | 층 어긋남 12(`install` · `live` · `telegram` · `backtest_v2` · `connect` · `dart` · `market`) · SQL `db.py` 밖 224 · 시각 숫자 26 · 같은 글 41(자리 54) · 중복 0 | 1단계 P1-04(허용 목록 · 줄어들기만) · P1-05 ~ P1-11 |
| U(화면 글 · 보이는 것이 일어나는 것) | `app/live.py:359` · `app/telegram.py:71` | '08:35 주문'이 글에 박혀 있어 늦게 여는 날에도 점검 글이 '08:35 주문 1건'으로 나감(실제 주문은 09:35) · 기준선에 그대로 기록됨 | 3단계(글 고치기 · 1단계는 지금 글 그대로) |
| 시계(ARCHITECTURE 6절 `Clock`) | `app/dart.py:231` · `app/install.py:114` · `151` | 고정 시계 밖(TASKS가 적은 5곳 밖 · CLI 또는 가릴 필드라 기준선에 영향 없음) | `dart.py:231`은 1단계 예외(2단계) · `install.py`는 5단계 |
