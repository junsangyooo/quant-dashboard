# product · quant 서비스와 lab

이 폴더는 두 제품의 기획 · 규칙 · 그림 · 코드를 담아요. **기획과 그림은 v2 완성본(2026-11-01 · UX 평가 반영 2026-11-02)이고, 코드는 v2 개발 중이에요**(엔진 · 데이터 · 실전 흐름은 가짜 토스로 끝, 화면은 일부). 이어서 할 일은 `service/TASKS.md`의 열린 항목이에요.

> 레포 뿌리의 `autotrade/` · `web/` 등은 운영 중인 다른 앱이에요. 이 폴더의 개발은 그쪽을 건드리지 않아요(`DEVELOPING.md` 1절).

## 1. 제품 둘

| | quant 서비스 | lab(실험실) |
|---|---|---|
| 무엇 | 고객이 설치해 자기 토스 계좌로 **실전 운용**하는 앱 | 누구나 전략을 실험해 보는 **공개 웹사이트** |
| 누가 · 어디에 | 고객이 자기 서버(고정 IP 클라우드)나 늘 켜 둔 PC에 설치. 화면은 Tailscale 사설망으로만. 사용자 본인도 자기 것을 따로 설치 | 사용자(운영자)가 배포 |
| 데이터 | 고객의 토스 Open API 키 + DART 키(선택) | 운영자 자료(상장폐지 종목 포함) |
| 하는 일 | 단계 블록 편집 · 백테스트 · 모의투자 · 실전 주문 · 할 일 · 텔레그램 알림 · 기록 | 블록 편집 · 백테스트 · 매일 추적 · 전략 복사 글 만들기 |
| 서로 | lab의 **전략 복사 글 하나**(`quant-strategy/3`, 숫자 · 종목 · 섹터 비움)만 받아요. 운영자에게 아무것도 보내지 않아요 | 복사 글을 내보내기만. 앱에 접속하지 않고 키 · 계좌 · 결과를 받지 않아요 |
| 문서 | [service/SPEC.md](service/SPEC.md) | [lab/SPEC.md](lab/SPEC.md) |

```mermaid
flowchart LR
  subgraph C["고객 서버 또는 늘 켜 둔 PC"]
    A["quant 서비스<br/>확인 · 주문 · 장중 감시"]
  end
  L["lab · 공개 사이트"] -- "전략 복사 글(숫자 비움)" --> A
  A <-- "고객 키 · 허용 IP" --> T[(토스증권 Open API)]
  D[(DART · 선택)] --> A
  A -- "알림 · 08:30 점검" --> G[고객 텔레그램 봇]
  P[휴대폰 · 노트북] -- "Tailscale" --> A
```

## 2. 지금 상태 (2026-11-02)

| 무엇 | 상태 | 남은 것 |
|---|---|---|
| quant 서비스 기획 v2 | 완성 · 검토 반영(기획 1회 · 다른 길 1회 · 디자인 2회 · 문서 1회) + **UX 평가 반영**(처음 쓰는 사람 기준 전문가 검토(그림 검토 · 사용자 시험 아님) · 전후 비교 · `service/SPEC.md` 부록 D) | 토스 · DART · 법령을 확인해야 정해지는 것 11개 · 법률 확인 7개 · 열린 결정 14개(2개는 답함) · 개발 중 질문 17개(1개는 답함) · `service/OPEN-QUESTIONS.md` |
| quant 서비스 그림 v2 | Figma 'quant 서비스' 페이지 · 화면 섹션 35개 · **1440 206장 + 390 96장**(UX 반영 새 프레임 20장 포함) + 흐름 지도 1장 | 레포의 그림 파일 · 프레임 표는 반영됨. 그림은 제품 주인이 갱신해요(`service/design/FIGMA.md`) |
| quant 서비스 코드 | **v2 개발 중**: `service/TASKS.md` 51항목 중 25 끝 · 26 열림(앞선 7개는 진행 중(일부) · UX 반영 19개 새로). 끝난 것: 안전(가짜 전송) · 데이터(토스 · DART) · 블록 모델 · v2 엔진 · 변환 일치 문턱 · 모의투자 엔진 · 키 · 접속 · 텔레그램 · 실전 흐름(가짜 토스) · 할 일 | 화면(편집기 · 전략 · 백테스트 · 모의 · 처음 실행 · 설정 · 실전)과 설치기 마무리, UX 반영 엔진 규칙(접수만 · 남은 매도 그만두기 · 잠긴 조건으로 받기 · 날짜별 매도 세금 · 텔레그램 고정 · 세션 등), 이미 있는 문제(깨끗한 체크아웃의 시험 자료 · 멈추기 · 자산 화면 차이 · 그림 비교 짝) |
| lab 기획 · 그림 | v2와 맞춤 + UX 반영(쓸모 한 줄 · '앱에서 쓸 수 있는 것만' 기본 · 구간 정의 하나로) · Figma 'lab' 페이지 화면 9개 · 그림 12장(목차 포함) | 코드 없음 · 데이터셋 출처 · 공개 권리 · 법률 확인 · 서명 · 받는 쪽 결정 |
| 실제 주문 확인 | 하지 않음 | 개발이 끝난 뒤 **사용자가 소액으로 직접** |

## 3. 문서 지도

| 문서 | 무엇 | 언제 읽나 |
|---|---|---|
| [DEVELOPING.md](DEVELOPING.md) | 개발 안내 · 정답의 순서 · 안전 규칙 · 실행 · 시험 · 일하는 방식 | 개발을 시작할 때 맨 먼저 |
| [service/SPEC.md](service/SPEC.md) | quant 서비스 v2 기획서 완성본(정답) · 부록 A 규칙 · 부록 B 예시 시간표 · 부록 D UX 평가 반영 | 모든 일의 기준 |
| [service/ENGINE-RULES.md](service/ENGINE-RULES.md) | 엔진 규칙만(경로 · 블록 · 판정 · 실행 방식 · 매매 방식 · 신호 강도 · 매도 대금 · 보호 매도 · 변환 · 복사 글 v3) + 강도 식 · 목표 금액 · 백테스트 적용 규칙 · 복사 글 v3 항목 id 사전 + 시험 예 | 엔진 · 시험을 짤 때 |
| [service/DATA-CATALOG.md](service/DATA-CATALOG.md) | 조건 카탈로그 + 토스 · DART 자료 출처 조사(Sources 포함) | 조건 · 데이터를 다룰 때 |
| [service/GLOSSARY.md](service/GLOSSARY.md) | 낱말 규칙 · 쓰는 말 · 쓰지 않는 말 · 금지어 · 말투 | 화면 글을 쓸 때 |
| [service/TASKS.md](service/TASKS.md) | 개발 할 일(순서 · 체크 · '다 됐다' 기준 · 시험) | 매일 |
| [service/OPEN-QUESTIONS.md](service/OPEN-QUESTIONS.md) | 토스 · DART 확인 · 법률 · 열린 결정 | 막힐 때 |
| [service/INSTALL.md](service/INSTALL.md) | 설치 안내(서버 · 늘 켜 둔 PC · Tailscale · 허용 IP) | 설치기 · 설치 문서를 다룰 때 |
| [service/TERMS-DRAFT.md](service/TERMS-DRAFT.md) | 사용 조건 초안(법률 확인 전) | 사용 조건 화면(V2-55)을 다룰 때 |
| [service/DECISIONS.md](service/DECISIONS.md) | 결정 기록(날짜 · 무엇 · 이유 · 바꾼 것) | '왜'가 궁금할 때 |
| [service/vendor/README.md](service/vendor/README.md) · [service/examples/](service/examples/copy-v3-example.txt) | 토스 OpenAPI 1.2.28 명세 · DART 응답 견본(가짜 응답의 꼴) · 복사 글 v3 예시 | 가짜 응답 · 복사 글 시험을 만들 때 |
| [service/design/FIGMA.md](service/design/FIGMA.md) | Figma 링크 · 화면 → 상태 → 그림 표 · 흐름 여섯 · 부품 | 화면을 만들 때 |
| [service/app/README.md](service/app/README.md) | 지금 코드 설명 | 코드를 읽을 때 |
| [lab/SPEC.md](lab/SPEC.md) · [lab/design/FIGMA.md](lab/design/FIGMA.md) | lab 기획 · 그림 | lab 쪽 일 |
| [history/MVP-V1.md](history/MVP-V1.md) | MVP v1 경과 · 검증 결과 · v2로 바뀐 것 · 지운 결정 보드 | 배경이 궁금할 때 |

## 4. Figma

- 파일: [quant.jsyoo.dev](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev)
- 페이지 [quant 서비스](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169405) · 목차와 흐름 지도 섹션 [345:428013](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-428013)
- 페이지 [lab](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=343-172871)
- 그림 파일은 `service/design/frames/` · `lab/design/frames/`(12장 · 목차 1장 포함). 서비스 그림은 UX 반영 뒤 1440 206장 · 390 96장 + 흐름 지도 1장이에요. 이름 꼴 `<화면번호>__<상태>__<폭>__<노드id>.png`

## 5. 개발을 이어서 하는 법

1. [DEVELOPING.md](DEVELOPING.md)를 읽어요(특히 3절 안전 규칙).
2. `service/app/`에서 시험을 돌려 모두 통과하는지 봐요(DEVELOPING 4절 · 깨끗한 체크아웃에서 실패하는 시험 3개는 TASKS T-80).
3. [service/TASKS.md](service/TASKS.md)의 열린 항목을 위에서부터 해요(UX 반영은 8절 · 돈에 닿는 것 먼저). 항목마다 체크 · 결과 한 줄 · 커밋.
4. 정답은 SPEC > ENGINE-RULES > 그림 > 지금 코드. 모르는 것은 OPEN-QUESTIONS에 적고 가정으로 진행.
5. **변환 일치 시험(TASKS T-24)이 통과하기 전에는 화면 · 모의투자 · 실전으로 넘어가지 않아요.**
