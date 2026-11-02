# 개발 안내 (quant 서비스)

이 레포에서 quant 서비스를 이어서 개발하는 사람이 처음 읽는 문서예요.

## 1. 이 폴더가 무엇인가

| 자리 | 무엇 | 손대도 되나 |
|---|---|---|
| `product/service/` | quant 서비스(고객이 설치해 자기 토스 계좌로 실전 운용하는 앱)의 기획 · 규칙 · 그림 · 코드 | 예 · 여기서 일해요 |
| `product/service/app/` | 지금 코드 = **v2 개발 중**(엔진 · 데이터 · 실전 흐름은 가짜 토스로 끝, 화면 일부 진행 중 · `service/TASKS.md` 결과 줄). 옛 MVP v1 엔진은 시험용으로 `app/engine_v1.py`에 고정 | 예 · v2로 바꿔 가요 |
| `product/lab/` | lab(공개 실험 사이트) 기획 · 그림. 코드 없음 | 기획 문서만 |
| `product/history/` | MVP v1 경과 · 지운 결정 보드 그림 | 읽기만 |
| 레포 뿌리의 `autotrade/` · `web/` 등 | **운영 중인 다른 앱(quant-dashboard)**. 실제 계좌로 돌고 있어요 | **손대지 않아요.** 부품 · 토큰 · 글꼴을 참고로 읽는 것만 |

## 2. 정답의 순서

1. `service/SPEC.md`(끝의 부록 A · B 포함. 부록 A가 본문을 이겨요)
2. `service/ENGINE-RULES.md`
3. `service/design/frames/` 그림(`design/FIGMA.md`로 찾아요)
4. 지금 코드(`service/app/`)

- 위가 아래를 이겨요. 지금 코드가 SPEC과 다르면 코드를 바꿔요.
- 그림 속 숫자 · 종목 · 날짜는 **예시**예요(SPEC 부록 B). 화면은 실제 값을 보여요.
- 문구는 그림 · SPEC의 **글자 그대로** 써요. 그림 · SPEC에 없는 글만 `service/GLOSSARY.md` 규칙으로 지어요.
- 결정의 이유는 `service/DECISIONS.md`, 데이터 출처는 `service/DATA-CATALOG.md`.
- 그림은 2026-11-02에 Figma에서 다시 내보낸 최종본이에요. 그림과 SPEC이 다르면 SPEC을 따르고 `service/OPEN-QUESTIONS.md` 4절에 적어요. 그림은 제품 주인이 갱신해요.

## 3. 안전 규칙 (어기면 멈추고 사람에게 물어요)

| 규칙 | 내용 |
|---|---|
| 기본은 가짜 전송 | 토스 · DART · 텔레그램 · 주문 전송은 **기본이 가짜**예요. 실제 전송은 `QUANT_LIVE_TRANSPORT=1` **과** 설치기가 쓰는 설정 파일(실제 전송 켬)이 둘 다 있을 때만 열려요(TASKS T-00). 개발 · 시험 · 설치 시험(T-56)은 이 둘을 만들지 않아요. `./start.sh`로 켜 볼 때도 가짜예요 |
| 실제 요청 0 | 개발 · 시험에서 **실제 토스 · 증권사 · 텔레그램 · DART에 요청을 보내지 않아요.** 가짜 응답은 `service/vendor/`의 꼴(토스 OpenAPI 1.2.28 명세 · DART 견본)을 따라요. 지금 MVP는 `MVP_TOSS_OFFLINE=1`로 토스 · 공인 IP 서비스에 나가지 않게 켜요(v2에서는 위 기본 가짜로 바뀌어요). 공개 문서(명세 파일)를 받는 것은 괜찮지만 토스 API(인증 · 시세 · 주문)는 부르지 않아요 |
| 실제 주문 0 | 실제 주문은 개발이 하지 않아요. 실제 주문 확인은 **사용자가 소액으로 직접** 해요 |
| 주문 시험 | 주문 코드는 '**가짜 전송에서만 주문**' 시험(`tests/test_no_orders.py`를 바꾼 것, TASKS T-00)을 늘 통과해야 해요 |
| 비밀 값 | 키 · 비밀 값 · 계좌번호를 코드 · 시험 · 기록 · 커밋에 넣지 않아요. 시험 값은 지어낸 값(예: `12345671234`)만. 키를 담은 환경 설정 파일을 만들거나 읽지 않아요(키는 앱 화면에서 입력해 앱 안에 잠가 둬요) |
| 묶는 주소 | 서버는 **127.0.0.1에만** 묶어요(Tailscale serve가 받아 넘겨요). `0.0.0.0` 금지 |
| 운영 앱 | 레포 뿌리의 운영 앱 코드 · 설정 · 데이터는 건드리지 않아요 |

## 4. 실행 · 시험 (지금 MVP 기준)

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
MVP_TOSS_OFFLINE=1 ./start.sh         # 토스 · 공인 IP 서비스에 나가지 않고 켜기
./stop.sh
```

- `start.sh`는 macOS Homebrew 파이썬 경로(`/opt/homebrew/bin/python3.12`)를 가정해요. 다른 환경이면 위처럼 venv를 먼저 만들면 그 단계를 건너뛰어요.
- 데이터는 `service/app/data/`(레포에 올리지 않음 · `service/app/.gitignore`). 지우면 처음 실행부터예요.
- 지금 MVP는 일봉을 야후 금융에서 받아요(v2에서 토스로 바꿈 · TASKS T-11). 시험은 고정한 가짜 일봉을 써요.

## 5. 일하는 방식

1. `service/TASKS.md`를 **위에서부터** 해요.
2. 항목 하나가 끝나면 체크(`- [x]`)하고, 그 항목의 '결과' 줄에 **'다 됐다' 기준을 어떻게 확인했는지와 시험 결과를 한 줄로** 적어요.
3. 항목마다 커밋해요. 커밋 메시지는 **영어 conventional · 짧게**(예: `feat(engine): block match all/any`, `test(live): fake-only order path`).
   - 커밋 작성자는 `Junsang Yoo <70479629+junsangyooo@users.noreply.github.com>`로 해요. 공개 레포라서 커밋 메시지에 꼬리 줄(trailer · `Co-authored-by:` 같은 줄)을 넣지 않아요.
4. 화면을 만들면 그림(`design/frames/`)과 **나란히 비교한 결과**(찍은 화면 경로나 비교 표)를 남겨요.
5. 모르는 것은 `service/OPEN-QUESTIONS.md` 4절에 적고 **가정으로 진행**해요. 가정은 TASKS 결과 줄에도 적어요.
6. SPEC을 바꿔야 할 것 같으면 바꾸지 말고 OPEN-QUESTIONS에 적어요(SPEC은 사람이 정해요).

## 6. 낱말 검사

화면 글과 빌드 결과(`web/dist`)에서 `service/GLOSSARY.md` 5절 **금지어 0건**이어야 해요. 서버가 돌려주는 오류 글도 화면 글이에요. 시험: `tests/test_copytext.py` · `web/tests/words.test.ts`(TASKS T-01 · T-71).

## 7. 회귀 문턱

**v1 → v3 변환 일치**(SPEC 4-8 · ENGINE-RULES R-C10 · TASKS T-02 · T-24)가 다음 단계로 가는 문턱이에요. v1 엔진을 `app/engine_v1.py`로 고정한 뒤, 레포 안 `tests/regression` 사례 · 옛 예시 4개 · 무작위 그래프를 v1 엔진과 v3 엔진으로 같은 일봉에 돌려 거래 하나하나(날짜 · 종목 · 수량 · 가격)가 같아야 해요. 같은 날 매도 대금으로 갈아타는 전략은 첫 차이가 나는 날까지 같고 그 첫 차이가 '하루 늦은 매수'여야 해요. 이 시험이 통과하기 전에는 화면 · 모의투자 · 실전 단계로 넘어가지 않아요.
