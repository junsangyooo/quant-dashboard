# 개발 안내 (quant 서비스)

이 레포에서 quant 서비스를 이어서 개발하는 사람이 처음 읽는 문서예요.

## 1. 이 폴더가 무엇인가

| 자리 | 무엇 | 손대도 되나 |
|---|---|---|
| `product/service/` | quant 서비스(고객이 설치해 자기 토스 계좌로 실전 운용하는 앱)의 기획 · 규칙 · 그림 · 코드 | 예 · 여기서 일해요 |
| `product/service/app/` | 지금 코드 = **v2(끝남) → 1단계 바탕 공사 중**(`service/TASKS.md` · 구조는 `service/ARCHITECTURE.md`). 지난 v2 할 일은 `history/V2-TASKS.md` | 예 · 1단계는 구조만 바꿔요 |
| `product/lab/` | lab(공개 실험 사이트) 기획 · 그림. 코드 없음 | 기획 문서만 |
| `product/history/` | MVP v1 경과 · 지운 결정 보드 그림 | 읽기만 |
| 레포 뿌리의 `autotrade/` · `web/` 등 | **운영 중인 다른 앱(quant-dashboard)**. 실제 계좌로 돌고 있어요 | **손대지 않아요.** 부품 · 토큰 · 글꼴을 참고로 읽는 것만 |

## 2. 정답의 순서

**1단계(바탕 공사) 동안**은 동작을 바꾸지 않아요. 정답은 `service/PRODUCT.md`(왜 · 품질 기준 · 확장 지점) → `service/ARCHITECTURE.md`(자리 · 규칙) → `service/TASKS.md`(할 일 · 다 됐다 기준) → **지금 코드와 시험**(동작)이에요. 지금 코드가 SPEC과 달라도 1단계에서는 코드를 바꾸지 않아요(동작 변화 0). 아래 순서는 동작을 확인할 때 써요. SPEC은 2단계에 새 전략 구조(v5)로 새로 써요.

1. `service/SPEC.md`(끝의 부록 A · B 포함. 부록 A가 본문을 이겨요)
2. `service/ENGINE-RULES.md`
3. `service/design/frames/` 그림(`design/FIGMA.md`로 찾아요)
4. 지금 코드(`service/app/`)

- 위가 아래를 이겨요(2단계부터). 1단계에서는 코드가 SPEC과 달라도 바꾸지 않아요.
- 그림 속 숫자 · 종목 · 날짜는 **예시**예요(SPEC 부록 B). 화면은 실제 값을 보여요.
- 문구는 그림 · SPEC의 **글자 그대로** 써요(3단계부터 · 1단계는 지금 글 그대로). 그림 · SPEC에 없는 글만 `service/GLOSSARY.md` 규칙으로 지어요.
- 결정의 이유는 `service/DECISIONS.md`, 데이터 출처는 `service/DATA-CATALOG.md`.
- 그림은 2026-11-02에 Figma에서 다시 내보낸 최종본이에요. 그림과 SPEC이 다르면 SPEC을 따르고 `service/OPEN-QUESTIONS.md` 4절에 적어요. 그림은 제품 주인이 갱신해요.

## 3. 안전 규칙 (어기면 멈추고 사람에게 물어요)

| 규칙 | 내용 |
|---|---|
| 기본은 가짜 전송 | 토스 · DART · 텔레그램 · **AI 제공사** · 주문 전송은 **기본이 가짜**예요(AI 제공사 호출도 `transport.py` 한 문으로만 · 붙이는 건 4단계 · 1단계는 AI SDK 금지 검사 · P1-02). 실제 전송은 `QUANT_LIVE_TRANSPORT=1` **과** 설치기가 쓰는 설정 파일(실제 전송 켬)이 둘 다 있을 때만 열려요(지난 할 일 T-00). 개발 · 시험 · 설치 시험(T-56)은 이 둘을 만들지 않아요. `./start.sh`로 켜 볼 때도 가짜예요 |
| 실제 요청 0 | 개발 · 시험에서 **실제 토스 · 증권사 · 텔레그램 · DART · AI 제공사에 요청을 보내지 않아요.** 가짜 응답은 `service/vendor/`의 꼴(토스 OpenAPI 1.2.28 명세 · DART 견본)을 따라요. 앱은 기본이 가짜 전송이라 따로 끄는 설정이 없어요. 공개 문서(명세 파일)를 받는 것은 괜찮지만 토스 API(인증 · 시세 · 주문)는 부르지 않아요 |
| 실제 주문 0 | 실제 주문은 개발이 하지 않아요. 실제 주문 확인은 **사용자가 소액으로 직접** 해요 |
| 주문 시험 | 주문 코드는 '**가짜 전송에서만 주문**' 시험(`tests/test_no_orders.py` · 1단계 P1-02에서 하위 폴더까지 넓힘)을 늘 통과해야 해요 |
| 비밀 값 | 키 · 비밀 값 · 계좌번호를 코드 · 시험 · 기록 · 커밋에 넣지 않아요. 시험 값은 지어낸 값(예: `12345671234`)만. 키를 담은 환경 설정 파일을 만들거나 읽지 않아요(키는 앱 화면에서 입력해 앱 안에 잠가 둬요) |
| 묶는 주소 | 서버는 **127.0.0.1에만** 묶어요(Tailscale serve가 받아 넘겨요). `0.0.0.0` 금지 |
| 운영 앱 | 레포 뿌리의 운영 앱 코드 · 설정 · 데이터는 건드리지 않아요 |

## 4. 실행 · 시험 (1단계 기준)

필요한 도구: **Python 3.12**, **Node.js 24**(화면 빌드 · 시험).

```bash
cd product/service/app

# 파이썬
python3.12 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest            # 네트워크 없이 돌아요(가짜 토스 · 가짜 일봉 · 가짜 공인 IP)

# 화면
cd web && npm ci && npm run typecheck && npm run lint && npm test && npm run build && cd ..

# 켜기 · 끄기 (127.0.0.1:8765)
./start.sh                            # 켜기(기본 가짜 전송 · macOS) · 리눅스 · 클라우드는 python -m tests.e2e_server
./stop.sh
```

- `start.sh`는 macOS Homebrew 파이썬 경로(`/opt/homebrew/bin/python3.12`)를 가정해요. 다른 환경이면 위처럼 venv를 먼저 만들면 그 단계를 건너뛰어요.
- 데이터는 `service/app/data/`(레포에 올리지 않음 · `service/app/.gitignore`). 지우면 처음 실행부터예요.
- 시험은 고정한 가짜 일봉을 써요(바깥으로 나가지 않음).

## 5. 일하는 방식

1. `service/TASKS.md`를 **위에서부터** 해요. 일은 `service-v5` 브랜치(안 되면 작업 환경이 정한 브랜치)에서만 하고, 끝나면 `quant-service`로 가는 PR 초안을 열어요(합치기는 사람이 해요).
2. 항목 하나가 끝나면 체크(`- [x]`)하고, 그 항목의 '결과' 줄을 `service/TASKS.md`의 **결과 줄 틀**로 적어요.
3. 항목마다 커밋해요. 커밋 메시지는 **영어 conventional · 짧게**(예: `feat(engine): block match all/any`, `test(live): fake-only order path`).
   - 커밋 작성자 · 커미터는 정확히 `Junsang Yoo <70479629+junsangyooo@users.noreply.github.com>`로 해요(`git config` · 로컬 commit-msg 훅 · TASKS P1-00). 공개 레포라서 커밋 메시지와 PR 본문에 꼬리 줄(trailer · `Co-authored-by:` · 세션 주소 같은 줄)을 넣지 않아요. 도구가 기본으로 붙이라고 해도 이 규칙이 이겨요.
4. 화면을 만들면 그림(`design/frames/`)과 **나란히 비교한 결과**(찍은 화면 경로나 비교 표)를 남겨요.
5. 모르는 것은 `service/OPEN-QUESTIONS.md` 4절에 적고 **가정으로 진행**해요(`service/TASKS.md`의 '멈추고 물을 것'은 빼고 · 그건 멈춰요). 가정은 TASKS 결과 줄에도 적어요.
6. SPEC을 바꿔야 할 것 같으면 바꾸지 말고 OPEN-QUESTIONS에 적어요(SPEC은 사람이 정해요).

## 6. 낱말 검사

화면 글과 빌드 결과(`web/dist`)에서 `service/GLOSSARY.md` 5절 **금지어 0건**이어야 해요. 서버가 돌려주는 오류 글도 화면 글이에요. 시험: `tests/test_copytext.py`(금지어 부분은 1단계 P1-03에서 새 파일로 옮김) · `web/tests/words.test.ts`.

## 7. 회귀 문턱

- **1단계(바탕 공사)**: 기준선 대조가 문턱이에요(`service/TASKS.md` P1-01 · P1-14). 화면 그림 · 화면 글 · API 모양 · 엔진 거래(사유 포함) · 하루 흐름 기록이 바꾸기 전과 같아야 다음 항목으로 가요.
- **2단계(엔진 v5)**: v3 → v5 변환 일치가 문턱이에요. 1단계에서 얼린 v3 사례 326개(`tests/baseline/`)를 v3 엔진과 v5 엔진으로 같은 일봉에 돌려 거래 하나하나가 같아야 해요(같은 날 매도 대금으로 갈아타는 전략은 SPEC v5에 따로 정함).
- 지난 v1 → v3 문턱(T-02 · T-24)은 통과했고(사례 326개 · 어긋남 0), v1 엔진은 1단계에서 지워요(옛 전략 호환은 v3부터).
