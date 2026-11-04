# 개발 할 일 · 1단계 바탕 공사

1단계는 **동작을 바꾸지 않고** 구조만 바꿔요. 지키는 장치를 먼저 걸고, 옛 코드를 지우고, 층을 나누고, 같은 일을 하는 것을 한 곳으로 모아요. 왜 · 무엇을 위해서는 `PRODUCT.md`, 자리와 규칙은 `ARCHITECTURE.md`, 일하는 방식 · 안전은 `../DEVELOPING.md`예요. 지난 v2 할 일은 `../history/V2-TASKS.md`(기록 · 아래 '지난 할 일의 자리' 표).

**지금 할 범위(2026-11-04 결정):** **P1-00 ~ P1-12와 P1-14**를 해요. P1-13(옛 화면 부품 합치기)은 하지 않아요. 3단계에서 새 디자인 시스템 부품으로 바뀌기 때문이에요. P1-12가 끝나면 P1-14로 대조 · 보고하고 PR 초안을 열어요. 그다음은 `ROADMAP.md`를 따라요. 일하는 방식(일감 · 검토 · 묶음 검토 · 단계 감사 · 진행 기록)은 `../DEVELOPING.md` 5절, 검토 기준은 `QUALITY.md`예요.

## 일하는 법
- 위에서부터 순서대로, 하나씩 해요.
- 코드 줄 번호는 `8b67df6` 기준이에요. 앞 항목이 그 파일을 바꾼 뒤에는 내용으로 찾아요.
- 항목 하나가 끝나면 체크하고 '결과' 줄을 **아래 틀**로 채우고 커밋해요(영어 conventional · 짧게). 표가 필요하면 `tests/baseline/reports/P1-xx.md`에 두고 경로를 적어요.
  - 결과 줄 틀: `통과 n건 · 허용 목록 어긋남 n→m · 화면 차 최대 x% · API 모양 차 0 · 엔진 거래 차 0 · 하루 흐름 차 0 · 시간 +y% · 바꾼 시험 n개(목록 경로) · 가정: … · 보고: 경로`
- 공통 기준(P1-02가 끝난 뒤부터): `product/service/app/scripts/check.sh`가 통과하고, 실제 토스 · DART · 텔레그램 · 증권사 · AI 제공사로 나가는 요청이 0건.
- **동작 변화 0의 뜻**: 화면 그림 · 화면 글 · API 경로와 응답 모양(키 · 타입) · 엔진 거래(사유 · 건너뜀 · 경고 글 포함) · 주문 흐름 · 하루 흐름 기록이 P1-01 기준선의 **'남는 것' 부분**과 같아요. 1단계에서는 API 응답을 바꾸지 않아요(번호로 보내기 · 서버 합계는 3단계).
- **시험을 고칠 때**: 준비 코드(만들기 · 인자 · 가짜 끼우기 · 가져오는 경로)는 바꿔도 돼요. **단언 · 기대값 · 시험 자료는 그대로이고, 있던 시험을 지우거나 합쳐 줄이지 않아요**(P1-02 ① · P1-03에서 정한 예외만 · 새 시험을 더하는 것은 괜찮아요). 바꾼 시험은 목록으로 남겨요. 단언이나 기대값을 바꿔야 하면 멈추고 물어요.
- **멈추고 물을 것**(OPEN-QUESTIONS 4절에 적고 단계를 멈춘 뒤 보고): 단언 · 기대값을 바꿔야 함 · 지울 대상에 목록 밖 참조가 있음 · DB 구조 버전을 바꿔야 함 · 기준선과 다른데 까닭을 설명 못 함 · Playwright나 새 개발 도구(정확한 버전)를 받을 수 없음(브라우저는 받지 않음) · 화면 찍기 브라우저(`../DEVELOPING.md` 4절)가 열리지 않음 · 바깥 약속(ARCHITECTURE 5절)을 바꿔야 함. 그 밖에 모르는 것은 가정으로 진행하고 결과 줄에 적어요.
- 하지 않는 것: 새 전략 구조 v5 · 새 화면 · AI 기능(포트 포함) · 화면 글 고치기(지금 글 그대로) · `web/src/screens/BlockEditor/*` 손질(3단계에 새 편집기로 바뀜) · 옛 화면 부품 합치기(P1-13 · 3단계).

## 0. 시작
- [x] **P1-00 시작 점검** — ① `origin/quant-service`에서 `service-v5` 브랜치를 만들어 push(push는 이 브랜치로만 · 커밋할 때마다) ② `git config user.name "Junsang Yoo"` · `git config user.email "70479629+junsangyooo@users.noreply.github.com"` · git 훅(commit-msg: 꼬리 줄 · 다른 작성자 거절 · pre-push: `service-v5` 밖 push · 삭제 · 강제 push 거절): `git config --show-origin core.hooksPath`에 이미 훅이 걸려 있으면 그 훅이 거절하는 것을 한 번 보이고, 없으면 커밋하지 않는 로컬 `.git/hooks/commit-msg` · `pre-push`를 만듦 ③ Python 3.12 · Node 24 확인(`node -v`) · 화면 찍기 브라우저의 경로와 판(`../DEVELOPING.md` 4절)을 결과 줄에 · 새 개발 도구를 **정확한 버전으로** 받을 수 있는지(ruff · mypy · pip-audit · 해시 lock 도구 · jscpd · OpenAPI → TS 생성기 · Playwright npm 패키지 · 화면 찍기 브라우저는 내려받지 않고 `PW_CHROMIUM` 경로와 판을 적음) · 안 되면 멈추고 물음 ④ Playwright로 화면 한 장을 찍어 봄 ⑤ 이 문서와 `PRODUCT.md` · `ARCHITECTURE.md` · `QUALITY.md` · `ROADMAP.md` · `PROGRESS.md` · `design/tokens-export.json` · `../history/V2-TASKS.md`가 브랜치에 있는지 ⑥ 깨끗하게 받은 상태의 `pytest` 결과(`tests/fixtures/v1_app.db`가 없어 실패하는 `test_db.py`의 3건은 P1-02 맨 앞에서 지움).
  - 결과: 통과 1426건(실패 21 · 63.97초: `test_db.py` 3건은 P1-02 ①에서 지움 · `test_catalog.py` 17건 · `test_copytext.py::test_forbidden_list_is_the_glossary` 1건은 `origin/quant-service`에 이미 있던 문서 ↔ 코드 어긋남 → Q-N18 · 단계 멈춤) · 허용 목록 어긋남 — · 화면 차 — · API 모양 차 — · 엔진 거래 차 — · 하루 흐름 차 — · 시간 —(pytest 64초는 참고값 · 정식은 P1-01) · 바꾼 시험 0개 · ① `service-v5` = `125685d`에서 갈라져 원격에 있음 ② 작성자 · 커미터 정확히 일치 · 전역 훅 `/opt/githooks`(commit-msg: 꼬리 줄 거절 · pre-push: `service-v5` 밖 거절을 한 번씩 확인 · 로컬 훅은 만들지 않음) ③ Python 3.12.3 · Node v24.22.1 · 브라우저 `PW_CHROMIUM=/opt/pw-browsers/chromium`(chromium-1243 · Chrome for Testing 153.0.8010.12 · 내려받지 않음) · 정확한 판으로 받아짐: ruff 0.17.3 · mypy 2.4.1 · pip-audit 2.10.1 · pip-tools 7.6.2(해시 lock) · jscpd 5.4.2 · openapi-typescript 7.13.0 · @playwright/test 1.64.0 ④ 화면 1장(`tests/baseline/reports/P1-00-screen.png` · V2-01 1440) ⑤ 문서 8개 모두 브랜치에 있음 ⑥ 위 pytest 수 · 가정: 설치된 브라우저(1243)가 Playwright 1.64.0 기본 판(1248)보다 낮지만 `executablePath`로 정상 · 보고: `tests/baseline/reports/P1-00.md`
- [ ] **P1-01 기준선** — 바꾸기 전 상태를 `tests/baseline/`에 남겨요(`.gitignore`에 걸리지 않게 · `data/` · `docs/` · `tmp/` · `static/` · `*.csv` · `*.log` · `*.db` 이름을 쓰지 않음). 기준선은 **'남는 것'과 '지울 것'으로 나눠** 기록해요(P1-03이 지우는 MVP 라우트 · MVP 엔진 · 지울 시험의 관측은 '지울 것').
  - 시계 고정: 서버 `now` · 직접 시계를 읽는 5곳(`api_v2.py:237` · `connect.py:79` · `vault.py:91` · `main.py:1267` · `backtest_v2.py:120`) · Playwright `page.clock`을 같은 고정 시각으로 · 복구 코드(`vault.py:109`)는 씨앗으로 고정.
  - 화면: `web/e2e/compare.mjs`의 화면 목록 × 1440 · 390 · 그림과 화면 글.
  - API 모양: pytest 전체를 돌리며 오간 응답의 키 · 타입을 라우트마다 · 가릴 필드 목록(시각 · 복구 코드 · 세션 · 쿠키 · 토큰).
  - 엔진: 시험의 백테스트 · 모의투자 사례의 거래 목록(날짜 · 종목 · 수량 · 가격 · **사유 · 건너뜀 · 경고 글**).
  - v3 사례 얼리기: v1 → v3 문턱의 사례 326개를 **'v3 본문 + 일봉(옛 예시 4개는 씨앗이 아니라 일봉 자체 · `st1.BIG10` 종목 목록이 있어야 만들어져서) + v3 거래(사유 포함)'로 자기완결**로 남김.
  - v1에서 나온 기대값 · 입력 얼리기: 지울 `app.v1` · `engine_v1` · `app.strategy`가 만드는 **시험 입력과 정답 전부** — v1 변환 시험 4건(`test_copytext_v3.py:77 · 157 · 175 · 176` · `test_engine_v2.py:520`)의 예시 본문 · `mode_of` 값 · `run_v1` 거래 · 복사 글 · `st1.normalize(bodies())` 결과, `helpers.legacy`가 `st.PIECES`로 만드는 본문(`test_api_v2.py:65`가 씀)을 파일로.
  - 하루 흐름 기록 시험: 실전 tick과 스케줄러를 **30초 간격으로 하루 돌려** 일어난 일의 순서를 기록 — 정상 날 · 08:30 점검 실패 뒤 08:40 회복 · 늦게 여는 날 · 08:55에 켬 · 장중에 다시 켬.
  - `_auto_loop` 한 바퀴를 실제로 도는 시험 · 주문 기록 순서 시험(가짜 토스가 주문을 받는 순간 DB에 'sending' 행이 이미 있음).
  - 시간: pytest 전체 · 백테스트 사례 · 화면 API의 걸린 시간.
  - 숫자: 줄 수 · 모듈 수 · 층 어긋남 · 중복 · SQL 위치 · 원시 토큰 · 같은 글 · 시각 숫자(ARCHITECTURE 7절 셈 규칙) · 설치된 판(`pip freeze --all` · `node -v` · `npm ls --depth=0`)을 `tests/baseline/`에.
  - 다 됐다: 기준선을 **두 번 만들어 같음** · 얼린 326개를 v3 엔진만으로 다시 돌려 차이 0 · 얼린 v1 기대값으로 4건이 통과.
  - 결과:
- [ ] **P1-02 안전 장치(지우기 전)** — ① 맨 앞: `test_db.py`의 `v1_app.db` 시험 3건(49 · 76 · 106행)과 `db.py`의 `_migrate_v1` 지움(설치본이 없어 v1 자료가 없음 · 지난 T-80 해결 · 213행 자리는 '알 수 없는 구조 버전' 오류로) ② `test_no_orders.py` · `test_copytext.py`의 소스 검사를 하위 폴더까지 · 금지 목록에 AI 제공사 SDK · urllib3 · websockets · subprocess 더함 ③ ruff 설정(정의 안 된 이름 F821 포함) · mypy 설정 ④ 옛 경로 다시 내보내기 금지 시험 · '시험 중 키 파일은 임시 폴더' 시험 · 자식 프로세스는 HOME을 임시 폴더로 ⑤ 금고 흐름 화면 시험(돈이 움직이는 요청 403 → 비밀번호 → 토큰으로 다시 보냄) ⑥ `product/service/app/scripts/check.sh`(어느 폴더에서 불러도 같게 돎 · Node 판이 24가 아니면 까닭을 적고 실패) · 커밋 위생 확인(ARCHITECTURE 7절 식) · 비밀 검사(QUALITY S11) ⑦ 의존성 고정(QUALITY S7): 파이썬은 기준선을 만들 때 설치된 판 그대로 해시까지 고정한 lock 파일 · 웹은 지금 `package-lock.json` · `check.sh`에 pip-audit · npm audit(1단계에서 나온 취약점은 판을 올리지 않고 허용 목록(까닭 한 줄)과 OPEN-QUESTIONS로).
  - 다 됐다: 일부러 넣은 위반(하위 폴더의 실제 전송 · 정의 안 된 이름 · 다시 내보내기 · 다른 커밋 작성자 · 키 꼴 문자열)을 각각 잡는 것을 한 번씩 보임 · lock 파일로 새로 설치한 환경에서도 pytest 통과 · `check.sh` 통과.
  - 결과:

## 1. 지우기
- [ ] **P1-03 옛 MVP · v1 코드 지움** — 지우기 전 **남는 코드 · 시험 · 도우미 · 시험 자료**에서 부르는 곳 0을 `grep`으로 셈(결과 줄에).
  - 먼저 옮길 것: 금지어 시험 3건(`test_copytext.py`에서 새 파일로) · 남길 검사(돈 · 주문 · 금지어 · **금고 · 세션 · 키 · 접속 · 화면 파일 내주기 · 바깥 전송**)를 지울 시험 파일에서 v2 시험으로(시험 함수마다 남김 / 옮김 / 지움 표 · `test_mvp_api.py` 13건 중 8건 · `test_fix1.py` 18건 중 5건 · `test_mvp_api.py:66`처럼 지울 라우트만 부르는 부분은 지움) · 조사 견본(`web/tests/particles.test.ts`의 버전 1 · 2 · 3 · 10)을 새 조사 시험으로.
  - 나눌 파일(지울 모듈을 가져오는 남는 파일 · v1 · MVP 부분만 떼고 나머지는 남김): `tests/helpers.py:7` · `test_copytext.py:11` · `test_copytext_v3.py:13` · `test_engine_v2.py:522`.
  - MVP 라우트를 부르는 남는 시험: `test_api_v2.py:65` · `test_copytext.py:196-218` → v2 라우트나 DB 직접 넣기로 · 보안 시험(`test_api_secrets.py:25 · 113`)은 남는 길(`/api/live` 등)로.
  - 서버: `app/engine_mvp.py` · `paper.py` · `strategy.py` · `graph.py` · `pieces.py` · `main.py`의 37 · 51 · 53 · 80 · 140 · **199**(`app.state.paper`) · 261-265 · 273-275 · 699-775(**747행 `_unique_name`은 v2 라우터가 쓰니 남김**) · 777-1107 · 1211 · 1223-1262행. **1167-1168행**(`_running_v2` 안의 MVP 갈래)은 `return None`으로(함수는 1172행 v2 라우터가 쓰니 남김). `main.py:1160`의 `st.stock_name`은 `pieces.py:219`의 종목 이름 사전과 함수를 그대로 옮겨 씀. 지운 뒤 안 쓰게 된 import(`timedelta` · `body_format` · `INDEX` 등)는 같이 정리.
  - 옛 전략 호환: `app/v1/*` · `engine_v1.py` · v1 → v3 일치 시험만 지움. **v3 안의 v1 변환(`copytext.convert_v1` · `V1_ALIASES` · 엔진의 v1 동점 규칙 · `/1` 복사 글 받기)은 그대로**. 그 시험 4건은 **기대값의 출처만 P1-01에서 얼린 파일로 바꿈(값은 같음 · 이 항목에서 허용하는 유일한 기대값 변경)**.
  - 저장: 표는 지우지 않음(paper_* 표는 v2 모의투자가 같이 씀) · 구조 버전 2 그대로.
  - 지울 시험 · 도구: `test_engine_paper.py` · `test_fix1.py` · `test_graph.py` · `test_graph_engine.py` · `test_graph_mirror.py` · `test_mvp_api.py` · `test_regression.py` · `test_engine_v1.py` · `test_threshold.py` · `regression/graph_cases.py` · `regression/threshold.py` · `regression/v1_inputs.py` · `regression/make_v1_trades.py` · `regression/conversion_table.md` · `regression/make_baseline.py` · `regression/replay.py` · `fixtures/regression_baseline.json` · `fixtures/v1_trades.json` — 위 '먼저 옮길 것'과 P1-01의 얼리기를 끝낸 뒤.
  - 웹: 화면에서 닿지 않는 23개(`src/graph/*` · `components/graph/*` · `copy/editor` · `copy/graph` · `copy/particles` · `components/Badges` · `Chips` · `Dots` · `StageIcon` · `Text` · `Toast` · `lib/money` · `lib/runDates` · `screens/LoadError` · 그 시험 · `public/flags/*` · `web/tests/fixtures/graph_cases.json` · `public/licenses/flag-icons-MIT.txt` · `licenses/README.txt`의 해당 줄) · `api/mvp.ts`(화면이 직접 쓰는 **8개** `useAppState` · `useConnect` · `keys` · `createQueryClient` · `usePost` · 타입 `CheckResult` · `CheckStep` · `ConnectView`와 같이 옮길 2개 `useRefreshAll` · `AppState`를 동작 그대로(재시도 규칙 · staleTime 5초 포함) 새 `api/`로 옮긴 뒤).
  - 다 됐다: 기준선 '남는 것'과 같음(화면 · API 모양 · 엔진 · 하루 흐름) · 남은 시험 통과 · 지운 줄 수 표 · 바꾼 시험 목록.
  - 결과:
- [ ] **P1-04 구조 장치(지운 뒤)** — `tests/test_layers.py`(ARCHITECTURE 2절 · 하위 폴더) · ESLint 경계(3절 · 1단계는 지금 폴더에 맞춰 셈 · ARCHITECTURE 6절) · 중복 · 같은 글 · SQL 위치 · 시각 숫자 · 토큰 규칙 시험(7절 셈 규칙). 지금 어긋나는 곳은 허용 목록(`tests/allow/*.txt` · 줄마다 까닭)에 넣고 **어긋남 수가 줄어들기만** 하게 해요(파일을 나눠 줄이 갈라져도 수로 셈). 1단계 끝에 허용 목록은 ARCHITECTURE 6절 '1단계 예외'만 남아요.
  - 다 됐다: 허용 목록 밖의 새 어긋남을 넣으면 실패하는 것을 한 번씩 보임 · 시작 숫자를 결과 줄에.
  - 결과:

## 2. 서버 층 나누기(ARCHITECTURE 2절)
- [ ] **P1-05 설정 · 오류 · 도메인** — `app/settings.py`(환경 변수 · 설정 파일을 한 번만 · `main.py:124-137` · `serve.py:55` · `transport.py:137` 등) · `domain/errors.py`(오류 번호 · HTTP 상태 없음) · 순수 계산을 `domain/`으로(1단계 예외: v3 모듈의 한글 글은 그대로) · 장 시간 · 휴장일 · 호가 단위 · 상하한가 · 한국 시간 정의(5벌 → 1벌)를 `domain/markets/kr.py`로.
  - 다 됐다: 도메인 층 어긋남 0 · 엔진 기준선 같음 · `os.environ`은 settings에만.
  - 결과:
- [ ] **P1-06 포트 · 어댑터** — `app/ports.py`(`Broker` · `MarketFeed` · `Disclosures` · `Notifier` · `Clock` · AI 포트는 4단계) · `app/adapters/`(toss · dart · telegram 보내기 · transport · publicip · fake). 실행 흐름이 구체 클래스 대신 포트를 받게(조립이 넣어 줌). **앱의 기본 가짜는 지금처럼 '응답 없음'** · 응답이 있는 가짜 토스(`tests/fake_toss.py`)는 시험에만. 시계는 `Clock`으로(1단계 예외: 일봉 캐시 판단 · `dart.py:231` 하루 한도 날짜 · `api_v2.py:237` 백테스트 기본 기간은 지금 시계 그대로 · 값이 바뀌어서).
  - 다 됐다: 바깥 소켓 0 · 하위 폴더 소스 검사 통과 · 기준선 같음.
  - 결과:
- [ ] **P1-07 저장 층** — SQL을 `app/store/`로(실행 · API · 어댑터 · 쓰기 일에 SQL 0). 트랜잭션 경계는 지금과 같게(`_send`가 'sending' 행을 먼저 쓰고 토스를 부르는 순서 유지).
  - 다 됐다: `store/` 밖 SQL 0 · 주문 기록 순서 시험 · 기준선 같음.
  - 결과:
- [ ] **P1-08 실행 흐름 · 시각 표** — `live.py`를 흐름 · 실전 상태의 주인(`run/live.py` · 사용자 실전 조작 12개(시작 · 끝 · 금액 · 한도 · 전략 바꾸기 · 할 일)는 주인의 공개 메서드) · 주문 바꾸기(`orders/` · 순수 함수) · 화면 모양(`api/live.py`)으로. `paper_v2` · `backtest_v2`를 `run/`으로. `market`의 '읽어 오며 저장하기'(캐시 판단 · 토스 받기 · 저장)는 `run/data.py`(포트와 store를 받음)로. 일 시각(20:10 · 08:20 ~ 15:20 · 16:00 ~ 20:00 · live.py 안 9곳 · `paper_v2.py:30` · `main.py` 1195 · 1202)을 `run/scheduler.py`의 시각 표 하나로. 앱 루프(`_auto_loop`)는 조립(`app.py`)으로. **실전 tick의 '창' 방식**(08:30 ~ 08:50 5분마다 점검 · 장중 1분마다)과 '점검 실패 = False(다시 시도)'의 뜻을 그대로 둠.
  - 다 됐다: 하루 흐름 기록이 기준선과 같음(5가지 날) · 시각 숫자 시험 · `test_live` · `test_todos` · `test_no_orders` 통과.
  - 결과:
- [ ] **P1-09 API · 쓰기 일 · 타입 생성** — `main.py`를 `app.py`(조립 · `create_app` 인자 12개 유지) + `api/*`(기능별 라우터 · `api_v2.py`는 `api/strategies.py`로) + `services/*`(쓰기 일 · `updates` · `datamgmt` 포함)로. 모든 라우트에 pydantic 응답 모델(지금 모양 그대로 · 상태에 따라 나오는 키는 선택 필드 · `response_model_exclude_unset=True`). **실행 때는 모르는 키를 남기고(`extra="allow"`), 시험 때만 엄격하게(`forbid`)**. 돈이 움직이는 라우트(주문 · 매도 · 멈추기)는 응답 검사 실패가 500이 되지 않게(기록하고 원래 응답). OpenAPI에서 `web/src/api/types.gen.ts`를 만들고, 손으로 쓴 API 타입을 생성 타입으로.
  - 다 됐다: API 모양 기준선과 같음 · 생성 타입 최신 시험 · 손으로 쓴 API 타입 0.
  - 결과:
- [ ] **P1-10 거래 비용 한 표** — 수수료 · 매도 세금 · 배당 원천징수(0.154 · `live.py:910`)를 날짜별 표 하나(`domain/costs.py`)로. 값은 지금 코드 값 그대로 · 그림(백테스트 '0.20%')과 다른 점 · 날짜별 세율은 OPEN-QUESTIONS에(지난 T-87).
  - 다 됐다: 비용 상수 정의 1곳 · 엔진 기준선 같음.
  - 결과:

## 3. 글 · 토큰 · 부품(ARCHITECTURE 3절)
- [ ] **P1-11 화면 글 한 출처** — `copy/texts.json`(id → **지금 글 그대로** · 변수는 `{name}` 꼴 · 조건 사전 `app/catalog.py`와 이름이 겹치지 않게)에서 파이썬 · TS 글을 만들어요. 서버가 보내는 글은 지금처럼 보내되 출처를 글 목록으로 · 같은 글이 두 곳에 있는 것을 0으로(지운 뒤 다시 셈 · 대략 16 · 27 · 20). 조사는 **견본만 얼리고 합치지 않음**(3단계).
  - 다 됐다: 같은 글 0(`BlockEditor/*` 빼고) · 금지어 0 · 화면 글 기준선과 같음 · API 모양 같음.
  - 결과:
- [ ] **P1-12 토큰 파이프라인** — `design/tokens-export.json`(Figma 정답 3묶음) → `web/design/tokens.json` → `web/src/styles/tokens.css`(지금 자리 · `web/scripts/gen-tokens.ts`가 만듦 · `ds/tokens/`로 옮기는 것은 3단계)를 스크립트로. 글꼴 이름 바꿈 규칙('Pretendard Variable' → 'Pretendard')으로 지금과 같게 · 1단계 범위는 지금 쓰는 180개(나머지 43개는 목록으로 남김). 원시 토큰 직접 사용을 같은 값의 의미 토큰으로 · 화면 안 임의 변수를 토큰으로(`BlockEditor/*`는 뺌 · 1단계 셈 범위는 지금 폴더 `screens/` · `components/` · `charts/` · ARCHITECTURE 6절).
  - 다 됐다: 원시 토큰 직접 사용 0(`BlockEditor/*` 빼고) · 토큰 대조 시험 · 화면 그림 기준선 0.5% 이하 · 화면 글 같음.
  - 결과:
- [ ] **P1-13 부품 합치기 · 경계(1단계에서 하지 않음 · 3단계로 옮김 · 아래는 기록)** — `web/src/`를 ARCHITECTURE 3절 꼴로 옮기고 겹친 부품을 하나로: SideTag 2벌 → SideMark · HowTo 2벌 → HowToSteps · Kv ↔ KeyValue → KeyValue · 창(덮개 + 창)은 `BlockEditor/*` 밖 2벌 → Dialog · Sheet · 칩 클래스 → Chip 부품 · Layout · Page 틀은 `ds/composites`. 부품이 API를 부르는 곳(Header · ConfirmHost)은 props로(P1-02의 금고 흐름 화면 시험 통과 유지). 기능끼리 가져오는 5쌍(Setup → Auth 포함) · 기능 → shell 15곳 · shell → api · lib → copy · lib ↔ charts 순환을 없앰(`main.tsx`는 웹 조립이라 무엇이든 가져와도 됨). **페이지 제목 굵기는 지금 700 그대로**.
  - 다 됐다: ESLint 경계 0 · 웹 중복 1% 미만 · 같은 CSS 본문 0(셋 다 `BlockEditor/*` 빼고) · 화면 그림 기준선 0.5% 이하 · 화면 글 같음.
  - 결과:

## 4. 마무리
- [ ] **P1-14 대조 · 보고** — 기준선(P1-01 '남는 것')과 대조: 화면 그림 · 화면 글 · API 모양 · 엔진 거래 · 하루 흐름 · pytest 수(지운 · 옮긴 시험 표와 함께) · 시간(20% 넘게 느려지지 않음). 허용 목록은 '1단계 예외'만. 전후 숫자 표. 이 대조 뒤에 단계 감사(`../DEVELOPING.md` 5절)를 하고, 통과하면 PR 초안을 열어요. **PR 본문은 이 표 · 가정 · 남은 질문만**(꼬리 줄 0).
  - 다 됐다: 동작 변화 0 · ARCHITECTURE 7절 문턱 모두(화면 경계 · 웹 중복 · 같은 CSS는 1단계 예외 · 허용 목록이 줄어들기만) · 커밋 위생 확인 통과.
  - 결과:

## 지난 할 일의 자리(`../history/V2-TASKS.md`의 열린 23개)
| 어디서 | 항목 |
|---|---|
| 1단계에서 끝냄 | T-80(P1-02) · T-87의 표 한 곳(P1-10 · 날짜별 세율은 OPEN-QUESTIONS) |
| 2단계(엔진 v5) | T-81 결과 모르는 주문 · T-82 남은 매도 그만두기 · T-84 지금 지켜지는 것 · T-85 텔레그램 고정 메시지 · T-86 DART 키 오류 · T-88 복사 글 잠긴 조건 · T-90 접속 · 계정 · T-56 설치기 |
| 3단계(새 화면)에서 새로 · 이 항목은 닫음 | T-30 · T-31 · T-32 · T-41 · T-55 · T-64 · T-83 · T-89 · T-91 ~ T-96 · T-97 · T-98(블록 편집기 · 옛 화면 · 그 문구 · 그림 짝 · UX 마무리는 새 전략 구조와 디자인 시스템 v1로 바뀜) |

## 정한 것(2026-11-04 제품 주인 확인)
| 무엇 | 정함 |
|---|---|
| 진행 범위 | 1단계는 P1-00 ~ P1-12 · P1-14(P1-13은 3단계) · 그 뒤는 `ROADMAP.md` |
| 증권사 | 토스만 · 다른 증권사는 하지 않음(나중에 넓힐 자리로 `Broker` 포트 하나만) |
| 옛 전략 호환 | `app/v1/*` · `engine_v1.py` · v1 → v3 일치 시험만 지움 · v3 안의 v1 변환은 1단계 동안 그대로 · 2단계에서 v3 → v5 문턱만 둠 |
| 동작 변화 0의 범위 | API 응답 모양까지 · 번호로 보내기 · 서버 합계는 3단계 |
| 화면 글 기준 | 지금 글 그대로(SPEC과 다른 글은 3단계에 고침) |
| 설치본 | 없음(2026-11-04 확인) · 바깥 약속은 1단계 동안 고정 |
| 디자인 토큰 정답 | Figma 기본 3묶음(원시 · 의미 · 컴포넌트) · 옛 시안 묶음(B · C · D)은 쓰지 않음 |
| 일하는 곳 | `service-v5` 브랜치 · PR 초안(합치기는 제품 주인이) |
