# 구조 (quant 서비스 · 목표와 규칙)

이 문서는 코드를 **어디에 두고, 무엇이 무엇을 가져와도 되는지**를 정해요. 목표는 중복 없이 느슨한 결합 · 높은 응집(low coupling · high cohesion)이고, 제품 기준(`PRODUCT.md`)의 품질 기준과 확장 지점을 코드 구조로 옮긴 것이에요. 규칙은 시험으로 지켜요(7절). 이 문서와 코드가 다르면 코드를 이 문서에 맞춰요.

- 1단계(바탕 공사 · `TASKS.md`)는 **동작을 바꾸지 않고** 자리만 옮기고 겹친 것을 합쳐요. 1단계에서 지키지 못하는 규칙은 6절의 '1단계 예외'에 이름을 적어 둬요.

## 1. 원칙
1. **한 가지 일은 한 곳에서.** 같은 계산 · 같은 글 · 같은 스타일 · 같은 부품이 두 곳에 있으면 하나로 합쳐요.
2. **돈의 규칙은 순수 함수로.** 도메인은 시각 · 네트워크 · 저장 · 화면 글을 모르고, 같은 입력이면 늘 같은 답을 내요.
3. **바깥은 약속(포트) 뒤로.** 토스 · DART · AI 제공사 · 텔레그램은 포트 약속을 맞춘 어댑터로만 불러요. 기본은 가짜예요(`../DEVELOPING.md` 3절).
4. **화면은 서버 규칙을 다시 계산하지 않아요**(3단계에서 마무리 · 1단계는 지금 동작 그대로).
5. **기능끼리 서로 가져오지 않아요.** 같이 쓰는 것은 아래 층으로 내려요.
6. **넓힐 자리는 약속으로.** `PRODUCT.md` 5절의 확장 지점마다 포트 또는 등록부 하나(4절).

## 2. 서버 층
| 층 | 폴더 | 담는 것 | 가져와도 됨 | 안 됨 |
|---|---|---|---|---|
| 입구 | `app/serve.py` · `app/install.py`(제자리 · 5절 바깥 약속) | 서버 켜기 · 설치 명령 | 조립 · 설정 | — |
| 조립 | `app/app.py` | `create_app`(어댑터 고르기 · 기본은 가짜 · 라우터 등록 · 설정 한 번 읽기) · 앱 루프(`_auto_loop`) | 아래 층 전부 | — |
| API | `app/api/` | 기능별 라우터 · pydantic 응답 모델 · 오류 번호 → HTTP 상태 | `services` · `run` · `store`(읽기 쿼리) · `domain` · `security` · `copy` | 어댑터 직접 · SQL |
| 쓰기 일 | `app/services/` | 사용자가 바꾸는 일(전략 저장 · 설정 · 키 · 연결 · 백업 · 복원 · 업데이트(updates) · 자료 관리(datamgmt) · 텔레그램 명령 받기) — 검사 → 저장 → 기록을 한 곳에서. 실전 운용 조작은 여기가 아니라 실행 흐름의 주인 | `domain` · `orders` · `store` · `ports` · `security` · `copy` | fastapi · 어댑터 구현 |
| 실행 흐름 | `app/run/` | 회차 하나(자료 → 판정 → 주문 처리 규칙 → Broker). 백테스트 · 모의투자 · 실전은 **Broker만 다르고 같은 엔진** · 실전 상태의 주인(`run/live.py` · 사용자 실전 조작은 이 주인의 공개 메서드) · 읽어 오며 저장하기(`run/data.py` · 포트와 store를 받음) · 일 시각 표 하나(`run/scheduler.py`) · 할 일 · 텔레그램 글은 `copy`에서 | `domain` · `orders` · `ports` · `store` · `copy` | 어댑터 구현 · fastapi |
| 주문 처리 규칙 | `app/orders/` | 1단계: 지금 코드의 주문 바꾸기 규칙을 순수 함수로(가격 · 수량 · 미체결 처리). 2단계: 규칙 등록부(O-xx 데이터 + 처리기) | `domain` | 어댑터 · 저장 · 실행 · API |
| 저장 | `app/store/` | 저장소 · 구조 버전 · **SQL은 여기에만** | `domain` 타입 · sqlite3 | 실행 · API · 어댑터 · 쓰기 일 |
| 보안 | `app/security/` | 금고(키 잠그기) · 세션 · 비밀번호 다시 받기 · CSRF · 호스트 허용 | `store` · `domain` 타입 | 실행 · 어댑터 |
| 바깥 연결 | `app/adapters/` | toss · dart · ai(제공사별) · telegram · publicip · fake · `transport.py`(실제 전송의 문 하나 · 두 열쇠) | `ports` · `domain` 타입 · 설정 | 실행 · API · 저장 |
| 포트 | `app/ports.py` | `Broker` · `MarketFeed` · `Disclosures` · `Notifier` · `Clock` 약속(Protocol · 이름은 지금 클래스와 겹치지 않게 · `AiProvider`는 4단계) | `domain` 타입 | 구현 |
| 도메인 | `app/domain/` | 전략 모델 · 검사 · 계산(지표 · 순위 · 배분 · 수량 · 호가 · 비용) · 엔진 판정 · 형식 변환 · 오류 종류 · 조사 | 표준 라이브러리 · `domain` 안 | fastapi · sqlite3 · 전송 · 지금 시각 읽기 · 다른 층 |
| 글 | `app/copy/` | 글 목록에서 만든 파이썬 쪽 글 | 없음 | 전부 |
| 설정 | `app/settings.py` | 환경 변수 · 설정 파일을 **한 번만** 읽어 값 묶음으로(조립이 넘겨 줌) | 표준 라이브러리 | 다른 층(설정은 받아서 씀) |

### 2-1. 지금 파일이 갈 자리(1단계)
| 지금 | 새 자리 |
|---|---|
| `serve` · `install` | 제자리(입구 · 5절 바깥 약속) |
| `updates` · `datamgmt` | `services/updates.py` · `services/data_admin.py`(저장 부분은 `store/`) |
| `api_v2.py`(라우트 14개) | `api/strategies.py` + `services/strategies.py` |
| `main.py`(라우트 72개 · `create_app` 1,155줄) | `app.py`(조립 · 앱 루프) + `api/*`(기능별 라우터) + `services/*`(쓰기 일) |
| `catalog` · `indicators` · `fundamentals` · `rules` · `live.py`의 호가 규칙(`lower_limit` · `ticks_below`) · 조사 함수 | `domain/` |
| `blocks` · `engine`(v3) · `copytext`(v3) | `domain/`(그대로 옮김 · 2단계에 v5로 바꾸며 `tests/reference/v3/`로) |
| `live.py`(1,267줄 · 52개 메서드) | `run/live.py`(흐름) · `orders/`(주문 바꾸기) · `adapters/toss` · `store/runs.py` · `api/live.py`(화면 모양) |
| `paper_v2` · `backtest_v2` · `schedule` · 일 시각(장 시간 · 휴장일 · 한국 시간은 `domain/markets/kr.py`) | `run/paper.py` · `run/backtest.py` · `run/scheduler.py` |
| `toss` · `dart`(클라이언트) · `telegram`(보내기) · `transport` · `publicip` | `adapters/` |
| `market` | 장 시간 · 휴장일 → `domain/markets/kr.py` · 캐시 판단 · 받기 → `run/data.py` · 저장 → `store/market.py` |
| `dart`(저장) · `db` · 흩어진 SQL | `store/` |
| `telegram`의 명령 받기(`/상태` · `/멈춤`) | `services/telegram_commands.py`(보내기는 어댑터) |
| `vault` · `connect`(세션 · 키 고리) | `security/` · 연결 확인 흐름은 `services/connect.py` |
| 모듈마다 따로인 오류 종류(DataError · LiveError · PaperError …) | `domain/errors.py`(오류 번호 · HTTP 상태는 API가 붙임) |

## 3. 화면 층(`web/src/`)
| 층 | 폴더 | 가져와도 됨 | 안 됨 |
|---|---|---|---|
| 토큰 | `ds/tokens/`(내보내기 → `tokens.json` → `tokens.css` 생성) | — | — |
| 기본 부품 | `ds/primitives/` | tokens · clsx · lucide | features · api · copy(글은 props로) · 원시 토큰 |
| 합친 부품 | `ds/composites/`(Layout · Page 틀 포함) | primitives · tokens | features · api · copy |
| API 클라이언트 | `api/`(OpenAPI에서 만든 타입 + fetch 한 겹 + 쿼리 키) | lib | ds · features |
| 화면 글 | `copy/`(글 목록 한 출처에서 생성) | — | 전부 |
| 공용 | `lib/`(형식 · 날짜 · 숫자 꼴 · 차트 계산 한 벌) | — | 위 층 전부 |
| 기능 | `features/<기능>/`(로그인 · 처음 실행 · 설정 · 자산 · 계획 · 기록 · 할 일 · 실전 운용 시작 · 멈추기 · 전략 목록 · 편집기 · 백테스트 · 모의투자) · 차트는 `features/charts`가 아니라 `ds/composites/charts` | ds · api · copy · lib | **다른 features** · shell |
| 틀 | `shell/`(routes · AppShell · 머리 · 내비) | features · ds · copy | api 직접 |
| 조립 | `main.tsx`(앱 뿌리 · API 설정) | 무엇이든 | — |

## 4. 확장 지점 → 약속(`PRODUCT.md` 5절)
| 확장 지점 | 약속 | 1단계에서 할 것 | 새 것을 더할 때 고치는 곳 |
|---|---|---|---|
| 증권사 | `Broker` 포트(토스 어댑터 하나 · 증권사별 기능표는 두 번째 증권사를 붙일 때) | 토스 어댑터를 포트 뒤로 | 어댑터 파일 하나 + 기능표 |
| 시장 | 시장 정보(장 시간 · 휴장일 · 호가 단위 · 상하한가 · 통화 · 한국 시간)를 `domain/markets/` 한 곳에 · 세금 · 수수료는 `domain/costs.py` · 종목 코드에 시장 포함은 2단계 스키마 | 국내만 · 흩어진 장 시간 · 호가 · 한국 시간 정의를 한 곳으로 | 시장 파일 하나 |
| 자료 | `MarketFeed` · `Disclosures` 포트 · 자료마다 '알 수 있었던 시각'(2단계) | 토스 시세 · DART를 포트 뒤로 | 어댑터 하나 |
| 전략 항목 | 항목 등록부(정의 · 검사 · 계산 · 화면 글 id) + 전략 스키마 버전 + 옮기기 | 손대지 않음(2단계에 v5 항목 등록부) | 항목 파일 하나 + 등록 한 줄 |
| 주문 처리 규칙 | 규칙 등록부(O-xx 데이터 + 처리기) | 순수 함수로 빼기만(2단계에 등록부) | 규칙 한 줄 + 처리기 |
| AI 제공사 | `AiProvider` 포트 + 기능표 | AI SDK 금지 검사만(포트 · 어댑터는 4단계 · 전송은 `transport.py` 문) | 어댑터 하나 + 기능표 한 줄 |
| 알림 | `Notifier` 포트 · 글은 글 목록 id | 텔레그램 보내기를 포트 뒤로 | 어댑터 하나 |
| 계좌 | 자료에 계좌 id | 새 표 · 새 열은 만들지 않음(1단계 구조 버전 그대로) · 2단계 스키마에 넣음 | — |
| 화면 | API만 씀 · 토큰 | API 타입 생성 | — |
| 전략 주고받기 | 복사 글 형식 버전 + 변환 | 지금 `/3` 그대로 | 변환 하나 |

## 5. 바깥 약속(1단계 동안 이름 · 경로 · 모양을 바꾸지 않음)
`python -m app.serve` · `python -m app.install` · 환경 변수 `MVP_DATA_DIR` · `MVP_PORT` · `MVP_WEB_DIST` · `QUANT_LIVE_TRANSPORT` · `QUANT_TS_NAME`(설치기가 서비스 파일에 씀) · 실제 전송 설정 파일 경로 2곳 · 상태 응답의 `"quant-mvp"` · `create_app`의 인자 12개 · `app.state`의 이름(P1-03 뒤 남는 10개: db · transports · vault · connections · market · telegram · paper2 · scheduler · live · need_confirm · `auto_tick` · `paper`는 P1-03에서 지움) · DB 구조 버전 2 · 데이터 폴더 배치 · API 경로와 응답 모양(키 · 타입). 옮긴 모듈은 옛 경로에서 다시 내보내지 않아요(시험의 막기 경로가 진짜 모듈에 닿게 · 6절).

## 6. 함께 지키는 규칙
| 무엇 | 규칙 |
|---|---|
| 설정 | 환경 변수 · 설정 파일은 `settings.py`만 읽음 · 조립이 값을 넘김 · 다른 곳에서 `os.environ` 0 |
| 오류 | 도메인 오류는 번호 + 값(HTTP 모름) · API가 번호 → HTTP 상태 · 화면에는 원인 한 줄 + 다음 행동 |
| 기록 | 목표: 한 줄 JSON(사건 이름 · 규칙 번호 · 종목 · 회차 id)(2단계) · 언제나: 키 · 비밀번호 · 계좌번호 · 토큰은 남기지 않음 · 예외는 종류와 위치 |
| 바꿔 끼우기 | 어댑터 · 시계 · 저장소는 조립이 넣어 줌(모듈 안에서 직접 만들지 않음) · `create_app` 인자 12개 유지 |
| 동시성 | 실전 상태는 주인(`run/live.py`)만 바꿈 · API는 주인의 공개 메서드를 부름 · 잠금은 2단계 |
| 시각 | `Clock` 포트로 받음 · 장 시간 · 휴장일 · 한국 시간은 `domain/markets/kr.py` · 일 시각은 `run/scheduler.py` |
| 다시 내보내기 | 옮긴 모듈을 옛 경로에서 다시 내보내지 않음 · 시험은 새 경로를 씀 |
| 1단계 예외(이름으로 적음) | v3 모듈(`blocks` · `engine` · `copytext` · `catalog`)의 한글 글 · 실제 시계 3곳(일봉 캐시 판단 · `dart.py:231` 하루 한도 날짜 · `api_v2.py:237` 백테스트 기본 기간) · 한 줄 JSON 기록 · 실전 상태 잠금 · 전략 항목 등록부 · Broker 기능표 · '알 수 있었던 시각' · 백테스트 · 모의투자의 Broker(체결 흉내를 Broker 뒤로 옮기기 · 엔진 모듈은 지금도 하나) → 2단계 / 화면이 돈 숫자를 더하는 곳 · 화면이 글자로 상태를 판정하는 곳 · `web/src/screens/BlockEditor/*` · 화면 경계 · 웹 중복 · 같은 CSS의 0 문턱(옛 화면 부품 합치기 P1-13을 디자인 시스템 v1 부품과 함께 하므로 · 1단계에는 허용 목록이 줄어들기만) · `ds/` · `features/` 폴더(1단계 셈은 지금 폴더에 맞춤: `screens/` = features 자리 · `components/` · `charts/` = ds 자리 · `api/` · `copy/` · `lib/` · `shell/`은 이름이 같음) → 3단계 |

## 7. 지키는 장치(시험 · 문턱 · 셈 규칙)
| 장치 | 방법 | 문턱 | 셈 규칙 |
|---|---|---|---|
| 파이썬 층 | 표준 라이브러리 AST 시험 `tests/test_layers.py`(2절 표 · 하위 폴더까지) | 어긋남 0(1단계 예외 목록 밖) | 모듈 맨 위 · 함수 안 import 모두 |
| 화면 경계 | ESLint `no-restricted-imports` patterns(3절 표) | warnings 0(1단계는 허용 목록이 줄어들기만 · 6절) | 정적 import · 동적 import |
| 중복 · 웹 | jscpd(개발 의존성) | 1% 미만(1단계는 줄어들기만 · 6절) | 최소 50토큰 · 시험 · 생성 파일 뺌 |
| 중복 · 파이썬 | AST 본문 해시 | 같은 본문 0 · 모듈 사이 같은 이름 0 | 5줄 이상 함수 · 맨 위 공개 함수만(`main` · 포트 구현 · 시험 뺌) |
| 중복 · CSS | 규칙 본문 비교 | 0(1단계는 줄어들기만 · 6절) | 선언 3개 이상 |
| 같은 글 | 글 목록 밖 같은 글 | 0 | 8자 이상 한글 문자열 · 서버 · 웹 · 빌드 결과 |
| SQL 위치 | AST · 문자열 검사 | `store/` 밖 0 | sqlite3 호출 · SQL 낱말로 시작하는 문자열 |
| 시각 숫자 | 문자열 · 숫자 검사 | `domain/markets/kr.py` · `run/scheduler.py` 밖 0 | 서버(`app/`)만 · `HH:MM` 문자열 · 시각 생성자(독스트링 · 글 목록 · 시험 뺌 · 웹은 3단계) |
| 토큰 | 원시 토큰 사용 · 위치 · 모서리 px 리터럴 · 내보내기 대조 | 0 | features · composites의 CSS · TSX(1단계는 `screens/` · `components/` · `charts/` · 6절) |
| 화면 그림 | Playwright 기준선(1440 · 390 · 고정 시각) | 화면마다 0.5% 이하 + 화면 글이 같음 | 기준선 화면 목록 전부 |
| 금지어 | `GLOSSARY.md` 5절 | 0건 | 서버 · 화면 · 빌드 결과 · 글 목록 · 하위 폴더 |
| 가짜 전송에서만 주문 | `tests/test_no_orders.py`(하위 폴더 · AI 제공사 SDK · urllib3 · websockets · subprocess 금지) + 바깥 소켓 0 · 자식 프로세스는 HOME을 임시 폴더로 | 실제 전송 객체 0 · 바깥 소켓 0 | 시험 전체 |
| API 모양 | 시험 전체에서 오간 응답의 키 · 타입(가릴 필드 목록 따로) | 기준선과 같음 | 라우트마다 |
| API 타입 | 생성 타입 최신 시험 | 손으로 쓴 API 타입 0 | `web/src/api` |
| 커밋 위생 | `git log origin/quant-service..HEAD --format='%an <%ae> / %cn <%ce> / %(trailers)'` · commit-msg 훅 | 작성자 · 커미터가 정확히 `Junsang Yoo <70479629+junsangyooo@users.noreply.github.com>` · 꼬리 줄 0 · PR 본문은 정한 틀만(TASKS P1-14) | 브랜치의 모든 커밋 |
| 비밀 검사 | 문자열 검사(QUALITY S11) | 키 · 토큰 꼴 · 계좌번호 꼴 · 공인 IP 0(허용 목록 밖) | `product/` 아래 추적되는 파일(생성 파일 · `vendor/` · 시험 자료는 까닭과 함께 뺌) |
| 의존성 | lock 파일(해시) · pip-audit · npm audit(QUALITY S7) | 허용 목록 밖 취약점 0 | 파이썬 · 웹 의존성 |
| 한 번에 | `product/service/app/scripts/check.sh`(pytest · ruff · mypy · typecheck · lint · test · build · 위 전부) | 모두 통과 | — |
