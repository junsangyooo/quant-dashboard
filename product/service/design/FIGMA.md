# quant 서비스 · Figma 지도

- 파일: [quant.jsyoo.dev](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev)
- 페이지 'quant 서비스': [331:169405](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169405) · 목차와 흐름 지도 섹션: [345:428013](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-428013) (그림: [V2-00__목차와_흐름_지도__map__345-428013.png](frames/V2-00__목차와_흐름_지도__map__345-428013.png))
- 부품 섹션 'v2': [345:177823](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-177823) · 옛 MVP v1 프레임 보관 섹션(탐색 페이지): [345:291070](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-291070) — 보관한 프레임은 이 문서와 `frames/`에 넣지 않았어요.
- 지도 json: [page_map.json](page_map.json) (섹션 · 프레임 · 흐름 · 부품 · 링크. 프레임 항목은 [노드 id, 프레임 이름, 그림 파일])
- 프레임 이름 꼴: 'V2-xx · 화면 이름 · 상태 · 폭'. 그림 파일 이름 꼴: `<화면번호>__<상태>__<폭>__<노드id>.png`
- 폭: 1440은 모든 화면, 390은 SPEC 7절 머리의 주요 화면만. 나머지 390은 개발이 반응형으로 맞춰요. 편집기는 1024 이상에서만 편집해요.
- 그림은 정답의 3순위예요(SPEC > ENGINE-RULES > 그림 > 지금 코드). 그림 속 숫자 · 종목 · 날짜는 예시예요(SPEC 부록 B).
- 그림은 2026-11-02에 Figma에서 다시 내보낸 최종본이에요(1440은 1배 · 390은 2배). **그림은 제품 주인이 갱신해요.** 3MB가 넘는 그림은 없어요.
- Figma 파일을 열 수 없어도 `frames/`의 그림이 정답이에요.

## 최종 내보내기에서 바뀐 것 (2026-11-02)

| 무엇 | 바뀐 것 | 그림 |
|---|---|---|
| 흐름 ② 전략 만들기 | 10/2 시점(버전 3 저장 → 버전 3 백테스트) | [저장 전](frames/V2-23__버전_3_저장_전-10-2__1440__345-428251.png) · [저장한 뒤](frames/V2-23__저장한_뒤-버전_3-10-2__1440__345-429666.png) |
| V2-10 자산 · 운용 전 | 두 장: 처음 실행 직후(9/24) · 준비 끝(10/5) | [처음 실행 직후](frames/V2-10__운용_전-마법사_직후__1440__345-431103.png) · [준비 끝](frames/V2-10__운용_전-준비_끝__1440__328-134287.png) |
| DART 주식 수 상태 | '다 받음 · 9/28' | V2-09 · V2-51 · V2-53 그림 |
| V2-40 모의투자 목록 | 대형주 돌파 버전 3 카드 | [있음](frames/V2-40__있음__1440__345-292339.png) |
| V2-02 복구 코드 | '이전' 단추 없음 | [기본](frames/V2-02__기본__1440__331-171544.png) |
| V2-14 할 일 상세 | 권리 변동 1장 추가 | [1440](frames/V2-14__열림-권리_변동__1440__345-431475.png) · [390](frames/V2-14__열림-권리_변동__390__345-431677.png) |

## 섹션(화면) 목록

화면마다 프레임과 그림 파일은 아래 '프레임 표'예요(섹션 35개 · 프레임 282장).

| 줄 | 섹션 |
|---|---|
| 처음 실행 · 로그인 | [331:169406](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169406) V2-01 · 비밀번호 만들기 |
| 처음 실행 · 로그인 | [331:169411](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169411) V2-02 · 복구 코드 |
| 처음 실행 · 로그인 | [345:255898](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-255898) V2-05 · 설치 위치 |
| 처음 실행 · 로그인 | [345:256078](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-256078) V2-06 · Tailscale |
| 처음 실행 · 로그인 | [345:256644](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-256644) V2-07 · 토스 연결 |
| 처음 실행 · 로그인 | [345:257776](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-257776) V2-08 · 텔레그램 |
| 처음 실행 · 로그인 | [345:258335](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-258335) V2-09 · DART |
| 처음 실행 · 로그인 | [331:169416](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169416) V2-03 · 로그인 |
| 처음 실행 · 로그인 | [331:169428](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169428) V2-04 · 비밀번호 다시 만들기 |
| 실전 | [345:187566](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-187566) V2-10 · 자산 |
| 실전 | [345:225729](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-225729) V2-11 · 계획 |
| 실전 | [345:239968](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-239968) V2-12 · 기록 |
| 실전 | [345:250313](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-250313) V2-13 · 할 일 · 알림 |
| 실전 | [345:254367](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-254367) V2-14 · 할 일 상세 |
| 운용 | [345:259529](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-259529) V2-30 · 실전 운용 시작 |
| 운용 | [345:265178](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-265178) V2-31 · 운용 설정 |
| 운용 | [345:270078](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-270078) V2-32 · 멈추기 시트 |
| 운용 | [345:287561](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-287561) V2-33 · 비밀번호 확인 창 |
| 전략 | [331:169471](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169471) V2-20 · 전략 목록 |
| 전략 | [331:169479](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169479) V2-21 · 새 전략 시트 |
| 전략 | [331:169485](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169485) V2-22 · 붙여 넣기 |
| 전략 | [331:169495](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169495) V2-23 · 편집기 |
| 전략 | [345:292064](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292064) V2-24 · 좁은 창 |
| 전략 | [331:169530](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169530) V2-25 · 전략 상세 |
| 전략 | [331:169543](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169543) V2-26 · 백테스트 |
| 모의투자 | [345:292338](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292338) V2-40 · 모의투자 |
| 모의투자 | [345:292547](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292547) V2-41 · 모의투자 상세 |
| 모의투자 | [345:294900](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-294900) V2-42 · 모의투자 시작 창 |
| 설정 | [331:169445](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169445) V2-50 · 설정 |
| 설정 | [331:169450](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-169450) V2-51 · 연결 |
| 설정 | [345:291228](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-291228) V2-52 · 알림 |
| 설정 | [345:292095](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292095) V2-53 · 데이터 |
| 설정 | [345:292880](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292880) V2-54 · 비밀번호 변경 |
| 설정 | [345:293059](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-293059) V2-55 · 사용 조건 · 앱 정보 |
| 설정 | [345:293144](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-293144) V2-56 · 접속 |

## 흐름 여섯 (프로토타입 연결)

시작 프레임에서 단추를 누르면 다음 프레임으로 가요. 머리 탭 · 뒤로 링크는 아래 '모든 화면 공통 링크'예요.

### ① 처음 실행 · 시작 [331:171447](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-171447) V2-01 · 비밀번호 만들기 · 기본 · 1440

| 순서 | 어디서 | 누르는 것 | 어디로 |
|---|---|---|---|
| 1 | V2-01 · 비밀번호 만들기 · 기본 · 1440 | 체크 · 만 19세 이상이에요 | V2-01 · 비밀번호 만들기 · 모두 체크함 · 1440 |
| 2 | V2-01 · 비밀번호 만들기 · 모두 체크함 · 1440 | 버튼 · 다음 | V2-02 · 복구 코드 · 기본 · 1440 |
| 3 | V2-02 · 복구 코드 · 기본 · 1440 | 체크 · 적어 뒀어요 | V2-02 · 복구 코드 · 적어 둠 · 1440 |
| 4 | V2-02 · 복구 코드 · 적어 둠 · 1440 | 버튼 · 다음 | V2-05 · 설치 위치 · 고르기 전 · 1440 |
| 5 | V2-05 · 설치 위치 · 고르기 전 · 1440 | 설치 위치 카드 | V2-05 · 설치 위치 · 고름 · 1440 |
| 6 | V2-05 · 설치 위치 · 고름 · 1440 | 버튼 · 다음 | V2-06 · Tailscale · 서버 · 연결됨 · 1440 |
| 7 | V2-06 · Tailscale · 서버 · 연결됨 · 1440 | 버튼 · 다음 | V2-07 · 토스 연결 · 키 없음 · 1440 |
| 8 | V2-07 · 토스 연결 · 키 없음 · 1440 | 버튼 · 연결 확인 | V2-07 · 토스 연결 · 확인 중 · 1440 |
| 9 | V2-07 · 토스 연결 · 확인 중 · 1440 | (1.5초) | V2-07 · 토스 연결 · 연결됨 · 1440 |
| 10 | V2-07 · 토스 연결 · 연결됨 · 1440 | 버튼 · 다음 | V2-08 · 텔레그램 · 토큰 없음 · 1440 |
| 11 | V2-08 · 텔레그램 · 토큰 없음 · 1440 | 버튼 · 대화방 찾기 | V2-08 · 텔레그램 · 대화방 찾는 중 · 1440 |
| 12 | V2-08 · 텔레그램 · 대화방 찾는 중 · 1440 | (1.5초) | V2-08 · 텔레그램 · 연결됨 · 메시지 받음 · 1440 |
| 13 | V2-08 · 텔레그램 · 연결됨 · 메시지 받음 · 1440 | 버튼 · 다음 | V2-09 · DART · 없음 · 1440 |
| 14 | V2-09 · DART · 없음 · 1440 | 버튼 · 연결 확인 | V2-09 · DART · 확인 중 · 1440 |
| 15 | V2-09 · DART · 확인 중 · 1440 | (1.5초) | V2-09 · DART · 받기 시작 · 1440 |
| 16 | V2-09 · DART · 받기 시작 · 1440 | 버튼 · 마치기 | V2-10 · 자산 · 운용 전 · 마법사 직후 · 1440 |

### ② 전략 만들기 · 시작 [327:132945](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=327-132945) V2-25 · 전략 상세 · 운용 전 · 1440

| 순서 | 어디서 | 누르는 것 | 어디로 |
|---|---|---|---|
| 1 | V2-25 · 전략 상세 · 운용 전 · 1440 | 버튼 · 편집 | V2-23 · 편집기 · 버전 3 저장 전 · 10/2 · 1440 |
| 2 | V2-23 · 편집기 · 버전 3 저장 전 · 10/2 · 1440 | 버튼 · 버전 3으로 저장 | V2-23 · 편집기 · 저장한 뒤 · 버전 3 · 10/2 · 1440 |
| 3 | V2-23 · 편집기 · 저장한 뒤 · 버전 3 · 10/2 · 1440 | 버튼 · 백테스트 | V2-26 · 백테스트 · 입력 · 1440 |
| 4 | V2-26 · 백테스트 · 입력 · 1440 | 버튼 · 백테스트 실행 | V2-26 · 백테스트 · 결과 · 1440 |

### ③ 실전 운용 시작 · 시작 [311:95007](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=311-95007) V2-26 · 백테스트 · 결과 · 1440

| 순서 | 어디서 | 누르는 것 | 어디로 |
|---|---|---|---|
| 1 | V2-26 · 백테스트 · 결과 · 1440 | 저장된 버전으로 운용 준비 › | V2-30 · 실전 운용 시작 · 기본 · 모두 통과 · 1440 |
| 2 | V2-30 · 실전 운용 시작 · 기본 · 모두 통과 · 1440 | 비밀번호 입력하고 시작 | V2-30 · 실전 운용 시작 · 비밀번호 창 · 1440 |
| 3 | V2-30 · 실전 운용 시작 · 비밀번호 창 · 1440 | 실전 운용 시작 | V2-10 · 자산 · 첫 확인 전 · 1440 |

### ④ 매일 운용 · 시작 [331:166011](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-166011) V2-10 · 자산 · 운용 중 · 1440

| 순서 | 어디서 | 누르는 것 | 어디로 |
|---|---|---|---|
| 1 | V2-10 · 자산 · 운용 중 · 1440 | 계획 보기 › | V2-11 · 계획 · 계획 있음 · 1440 |
| 2 | V2-11 · 계획 · 계획 있음 · 1440 | 머리 탭 · 기록(부품 머리 v2 1440) | V2-12 · 기록 · 거래 있음 · 1440 |
| 3 | V2-12 · 기록 · 거래 있음 · 1440 | 머리 · 할 일 아이콘(부품) | V2-13 · 할 일 · 알림 · 있음 · 1440 |
| 4 | V2-13 · 할 일 · 알림 · 있음 · 1440 | 할 일 행 · 결과 모르는 주문 · 기아 | V2-14 · 할 일 상세 · 열림 · 결과 모르는 주문 · 1440 |

### ⑤ 멈추기 · 시작 [345:271033](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-271033) V2-32 · 멈추기 시트 · 기본 · 1440

| 순서 | 어디서 | 누르는 것 | 어디로 |
|---|---|---|---|
| 1 | V2-10 · 자산 · 운용 중 · 1440 | 멈추기 ›(재생 시작 전 단계 · 시작점은 시트) | V2-32 · 멈추기 시트 · 기본 · 1440 |
| 2 | V2-32 · 멈추기 시트 · 기본 · 1440 | 새 매수 멈춤 카드 | V2-32 · 멈추기 시트 · 새 매수 멈춤 · 1440 |
| 3 | V2-32 · 멈추기 시트 · 새 매수 멈춤 · 1440 | 새 매수 멈춤 | V2-10 · 자산 · 새 매수 멈춤 · 1440 |
| 4 | V2-32 · 멈추기 시트 · 기본 · 1440 | 토스에서 멈추기 · 펼쳐요 | V2-32 · 멈추기 시트 · 토스에서 멈추기 펼침 · 1440 |

### ⑥ 모의투자 · 시작 [345:264645](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-264645) V2-25 · 전략 상세 · 실전 운용 중 · 1440

| 순서 | 어디서 | 누르는 것 | 어디로 |
|---|---|---|---|
| 1 | V2-25 · 전략 상세 · 실전 운용 중 · 1440 | 버튼 · 버전 3으로 모의투자 시작 | V2-42 · 모의투자 시작 창 · 기본 · 1440 |
| 2 | V2-42 · 모의투자 시작 창 · 기본 · 1440 | 모의투자 시작 | V2-40 · 모의투자 · 있음 · 1440 |
| 3 | V2-40 · 모의투자 · 있음 · 1440 | 링크 · 보기 › | V2-41 · 모의투자 상세 · 첫 확인 전 · 1440 |

## 모든 화면 공통 링크

| 링크 | 가는 곳 |
|---|---|
| 머리 부품 | 345:182452 (6 변형 모두) |
| 머리 1440 · 탭 · 자산 | V2-10 · 자산 · 운용 중 · 1440 |
| 머리 1440 · 탭 · 계획 | V2-11 · 계획 · 계획 있음 · 1440 |
| 머리 1440 · 탭 · 기록 | V2-12 · 기록 · 거래 있음 · 1440 |
| 머리 1440 · 탭 · 전략 | V2-20 · 전략 목록 · 전략 있음 · 1440 |
| 머리 1440 · 탭 · 모의투자 | V2-40 · 모의투자 · 있음 · 1440 |
| 머리 1440 · 할 일 | V2-13 · 할 일 · 알림 · 있음 · 1440 |
| 머리 1440 · 설정 | V2-50 · 설정 · 기본 · 1440 |
| 머리 1440 · 운용 상태 칩 | V2-10 · 자산 · 운용 중 · 1440 |
| 머리 1440 · 워드마크 | V2-10 · 자산 · 운용 중 · 1440 |
| 뒤로 링크 수 | 140개 |
| 뒤로 · 이전 | 마법사 앞 화면(02→01 기본 · 05→02 기본 · 06→05 고름 · 07→06 서버 연결됨 · 08→07 연결됨 · 09→08 연결됨) |
| 뒤로 · 로그인 | V2-03 · 로그인 · 기본 · 1440 |
| 뒤로 · 설정 | V2-50 · 설정 · 기본 · 1440 |
| 뒤로 · 새 전략 | V2-21 · 새 전략 시트 · 기본 · 1440 |
| 뒤로 · 전략 | V2-20 · 전략 목록 · 전략 있음 · 1440 |
| 뒤로 · 대형주 돌파 | V2-25 · 전략 상세 · 실전 운용 중 · 1440 |
| 뒤로 · 할 일 · 알림 | V2-13 · 할 일 · 알림 · 있음 · 1440 |
| 뒤로 · 배당 성장 | V2-25 · 전략 상세 · 모의투자 중 · 1440 |
| 뒤로 · 자산 | V2-10 · 자산 · 운용 중 · 1440 |
| 뒤로 · 모의투자 | V2-40 · 모의투자 · 있음 · 1440 |
| 뒤로 · V2-02 이전 | 숨김 · 이동 없음(지적 11) |
| 뒤로 · V2-26 대형주 돌파 | 327:132945 (10/2 시점) |

## 부품 목록(섹션 '부품 · v2')

| 부품 | 노드 | 쓴 곳 수 | 쓰지 않은 변형 |
|---|---|---|---|
| 운용 상태 칩 | [345:177854](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-177854) | 373 | 상태=업데이트 중 |
| 할 일 버튼 | [345:177880](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-177880) | 285 | — |
| 머리 v2 1440 | [345:182452](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-182452) | 189 | — |
| 머리 v2 390 | [345:182489](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-182489) | 88 | — |
| 하단 탭 v2 | [345:182635](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-182635) | 51 | 현재=모의투자 |
| 매수 매도 표시 | [345:182916](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-182916) | 355 | — |
| 주문 상태 칩 | [345:182935](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-182935) | 105 | 상태=조건주문 체결 |
| 실행 방식 칩 | [345:182957](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-182957) | 1121 | — |
| 가상 표시 | [345:182958](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-182958) | 26 | — |
| 가상 금액 카드 | [345:182960](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-182960) | 5 | — |
| 주문 표 행 | [345:183012](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-183012) | 57 | 종류=매도 |
| 할 일 행 v2 | [345:183499](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-183499) | 8 | 심각도=정보 |
| 할 일 배너 | [345:183524](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-183524) | 12 | — |
| 비밀번호 확인 창 | [345:183687](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-183687) | 16 | — |
| v2/꼬리 칩 | [345:177697](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-177697) | 2032 | 종류=지금 섹터 기준 |
| v2/블록 토글 | [345:177714](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-177714) | 253 | 값=하나라도, 상태=열림 |
| v2/조건 줄 | [345:177822](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-177822) | 1012 | — |
| v2/단계 블록 | [345:181961](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-181961) | 225 | 단계=① 유니버스, 상태=고름 · 단계=① 유니버스, 상태=문제 · 단계=① 유니버스, 상태=옮기는 중 · 단계=② 신호, 상태=옮기는 중 · 단계=③ 필터, 상태=옮기는 중 · 단계=④ 종목 선정, 상태=고름 · 단계=④ 종목 선정, 상태=옮기는 중 · 단계=⑤ 매수, 상태=문제 · 단계=⑤ 매수, 상태=옮기는 중 · 단계=⑦ 비중, 상태=문제 · 단계=⑦ 비중, 상태=옮기는 중 |
| v2/조건 추가 메뉴 | [345:183388](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-183388) | 3 | — |
| v2/단계 목록 행 | [345:183432](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-183432) | 224 | — |
| v2/문장으로 보기 | [345:183433](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-183433) | 1 | — |
| v2/줄 편집 패널 | [345:184012](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-184012) | 5 | — |
| v2/단계 요약 | [345:255678](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-255678) | 71 | — |
| 라디오 | [345:376038](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-376038) | 46 | — |
| 처음 실행 단계 막대 | [345:241830](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-241830) | 32 | — |
| 알림 상자 | [345:241854](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-241854) | 107 | — |
| 값 줄 | [345:241855](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-241855) | 137 | — |
| 안내 단계 | [345:241863](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-241863) | 171 | — |
| 설치 위치 카드 | [345:241910](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-241910) | 4 | 위치=PC, 상태=고름 |

- 실행 방식 칩은 '실행 방식 칩'(345:182957) 하나만 써요. 옛 캔버스 부품(연결점 · 이름표 · 경로 행 · 문제 행 · 매매 방식 칩 · 경로 한 줄 · 도구 막대 · 알림)은 v1 부품을 다시 썼어요(`page_map.json`에는 없음): 322:116726 · 330:136352 · 322:116934 · 322:116957 · 322:116875 · 322:116876 · 322:116882 · 322:116958.

## 프레임 표 (화면 → 상태 → 그림)

<!-- frames:start -->
| 화면 | 상태 | 폭 | 노드 | 그림 파일 |
|---|---|---|---|---|
| V2-00 목차와 흐름 지도 | 목차와 흐름 지도 | map | [345:428013](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-428013) | [V2-00__목차와_흐름_지도__map__345-428013.png](frames/V2-00__목차와_흐름_지도__map__345-428013.png) |
| V2-01 비밀번호 만들기 | 기본 | 1440 | [331:171447](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-171447) | [V2-01__기본__1440__331-171447.png](frames/V2-01__기본__1440__331-171447.png) |
| V2-01 비밀번호 만들기 | 두 비밀번호 다름 | 1440 | [345:242001](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-242001) | [V2-01__두_비밀번호_다름__1440__345-242001.png](frames/V2-01__두_비밀번호_다름__1440__345-242001.png) |
| V2-01 비밀번호 만들기 | 모두 체크함 | 1440 | [345:340290](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-340290) | [V2-01__모두_체크함__1440__345-340290.png](frames/V2-01__모두_체크함__1440__345-340290.png) |
| V2-01 비밀번호 만들기 | 기본 | 390 | [303:87237](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=303-87237) | [V2-01__기본__390__303-87237.png](frames/V2-01__기본__390__303-87237.png) |
| V2-01 비밀번호 만들기 | 두 비밀번호 다름 | 390 | [303:87301](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=303-87301) | [V2-01__두_비밀번호_다름__390__303-87301.png](frames/V2-01__두_비밀번호_다름__390__303-87301.png) |
| V2-01 비밀번호 만들기 | 모두 체크함 | 390 | [345:343498](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-343498) | [V2-01__모두_체크함__390__345-343498.png](frames/V2-01__모두_체크함__390__345-343498.png) |
| V2-02 복구 코드 | 기본 | 1440 | [331:171544](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-171544) | [V2-02__기본__1440__331-171544.png](frames/V2-02__기본__1440__331-171544.png) |
| V2-02 복구 코드 | 적어 둠 | 1440 | [331:171615](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-171615) | [V2-02__적어_둠__1440__331-171615.png](frames/V2-02__적어_둠__1440__331-171615.png) |
| V2-02 복구 코드 | 기본 | 390 | [303:87365](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=303-87365) | [V2-02__기본__390__303-87365.png](frames/V2-02__기본__390__303-87365.png) |
| V2-02 복구 코드 | 적어 둠 | 390 | [303:87403](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=303-87403) | [V2-02__적어_둠__390__303-87403.png](frames/V2-02__적어_둠__390__303-87403.png) |
| V2-03 로그인 | 기본 | 1440 | [313:95664](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=313-95664) | [V2-03__기본__1440__313-95664.png](frames/V2-03__기본__1440__313-95664.png) |
| V2-03 로그인 | 다시 켠 뒤 | 1440 | [313:95822](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=313-95822) | [V2-03__다시_켠_뒤__1440__313-95822.png](frames/V2-03__다시_켠_뒤__1440__313-95822.png) |
| V2-03 로그인 | 맞지 않음 | 1440 | [313:95715](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=313-95715) | [V2-03__맞지_않음__1440__313-95715.png](frames/V2-03__맞지_않음__1440__313-95715.png) |
| V2-03 로그인 | 잠금 | 1440 | [313:95767](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=313-95767) | [V2-03__잠금__1440__313-95767.png](frames/V2-03__잠금__1440__313-95767.png) |
| V2-03 로그인 | 기본 | 390 | [303:87443](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=303-87443) | [V2-03__기본__390__303-87443.png](frames/V2-03__기본__390__303-87443.png) |
| V2-03 로그인 | 다시 켠 뒤 | 390 | [303:87559](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=303-87559) | [V2-03__다시_켠_뒤__390__303-87559.png](frames/V2-03__다시_켠_뒤__390__303-87559.png) |
| V2-03 로그인 | 맞지 않음 | 390 | [303:87479](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=303-87479) | [V2-03__맞지_않음__390__303-87479.png](frames/V2-03__맞지_않음__390__303-87479.png) |
| V2-03 로그인 | 잠금 | 390 | [303:87516](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=303-87516) | [V2-03__잠금__390__303-87516.png](frames/V2-03__잠금__390__303-87516.png) |
| V2-04 비밀번호 다시 만들기 | 기본 | 1440 | [345:260567](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-260567) | [V2-04__기본__1440__345-260567.png](frames/V2-04__기본__1440__345-260567.png) |
| V2-04 비밀번호 다시 만들기 | 복구 코드 맞지 않음 | 1440 | [345:365428](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-365428) | [V2-04__복구_코드_맞지_않음__1440__345-365428.png](frames/V2-04__복구_코드_맞지_않음__1440__345-365428.png) |
| V2-04 비밀번호 다시 만들기 | 새 복구 코드 | 1440 | [345:260632](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-260632) | [V2-04__새_복구_코드__1440__345-260632.png](frames/V2-04__새_복구_코드__1440__345-260632.png) |
| V2-04 비밀번호 다시 만들기 | 기본 | 390 | [303:87602](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=303-87602) | [V2-04__기본__390__303-87602.png](frames/V2-04__기본__390__303-87602.png) |
| V2-04 비밀번호 다시 만들기 | 복구 코드 맞지 않음 | 390 | [345:365494](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-365494) | [V2-04__복구_코드_맞지_않음__390__345-365494.png](frames/V2-04__복구_코드_맞지_않음__390__345-365494.png) |
| V2-04 비밀번호 다시 만들기 | 새 복구 코드 | 390 | [303:87654](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=303-87654) | [V2-04__새_복구_코드__390__303-87654.png](frames/V2-04__새_복구_코드__390__303-87654.png) |
| V2-05 설치 위치 | 고르기 전 | 1440 | [345:255899](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-255899) | [V2-05__고르기_전__1440__345-255899.png](frames/V2-05__고르기_전__1440__345-255899.png) |
| V2-05 설치 위치 | 고름 | 1440 | [345:255987](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-255987) | [V2-05__고름__1440__345-255987.png](frames/V2-05__고름__1440__345-255987.png) |
| V2-06 Tailscale | PC · 건너뛰기 | 1440 | [345:256393](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-256393) | [V2-06__PC-건너뛰기__1440__345-256393.png](frames/V2-06__PC-건너뛰기__1440__345-256393.png) |
| V2-06 Tailscale | PC · 연결됨 | 1440 | [345:256289](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-256289) | [V2-06__PC-연결됨__1440__345-256289.png](frames/V2-06__PC-연결됨__1440__345-256289.png) |
| V2-06 Tailscale | 서버 · 안 보임 | 1440 | [345:256183](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-256183) | [V2-06__서버-안_보임__1440__345-256183.png](frames/V2-06__서버-안_보임__1440__345-256183.png) |
| V2-06 Tailscale | 서버 · 연결됨 | 1440 | [345:256079](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-256079) | [V2-06__서버-연결됨__1440__345-256079.png](frames/V2-06__서버-연결됨__1440__345-256079.png) |
| V2-07 토스 연결 | 실패 · 응답 없음 | 1440 | [345:257375](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-257375) | [V2-07__실패-응답_없음__1440__345-257375.png](frames/V2-07__실패-응답_없음__1440__345-257375.png) |
| V2-07 토스 연결 | 실패 · 키 | 1440 | [345:257137](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-257137) | [V2-07__실패-키__1440__345-257137.png](frames/V2-07__실패-키__1440__345-257137.png) |
| V2-07 토스 연결 | 실패 · 허용 IP | 1440 | [345:257256](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-257256) | [V2-07__실패-허용_IP__1440__345-257256.png](frames/V2-07__실패-허용_IP__1440__345-257256.png) |
| V2-07 토스 연결 | 연결됨 | 1440 | [345:257024](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-257024) | [V2-07__연결됨__1440__345-257024.png](frames/V2-07__연결됨__1440__345-257024.png) |
| V2-07 토스 연결 | 입력함 · PC | 1440 | [345:256763](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-256763) | [V2-07__입력함-PC__1440__345-256763.png](frames/V2-07__입력함-PC__1440__345-256763.png) |
| V2-07 토스 연결 | 키 없음 | 1440 | [345:256645](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-256645) | [V2-07__키_없음__1440__345-256645.png](frames/V2-07__키_없음__1440__345-256645.png) |
| V2-07 토스 연결 | 확인 중 | 1440 | [345:256881](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-256881) | [V2-07__확인_중__1440__345-256881.png](frames/V2-07__확인_중__1440__345-256881.png) |
| V2-08 텔레그램 | 대화방 못 찾음 | 1440 | [345:258217](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-258217) | [V2-08__대화방_못_찾음__1440__345-258217.png](frames/V2-08__대화방_못_찾음__1440__345-258217.png) |
| V2-08 텔레그램 | 대화방 찾는 중 | 1440 | [345:257886](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-257886) | [V2-08__대화방_찾는_중__1440__345-257886.png](frames/V2-08__대화방_찾는_중__1440__345-257886.png) |
| V2-08 텔레그램 | 연결됨 · 메시지 받음 | 1440 | [345:257997](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-257997) | [V2-08__연결됨-메시지_받음__1440__345-257997.png](frames/V2-08__연결됨-메시지_받음__1440__345-257997.png) |
| V2-08 텔레그램 | 토큰 없음 | 1440 | [345:257777](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-257777) | [V2-08__토큰_없음__1440__345-257777.png](frames/V2-08__토큰_없음__1440__345-257777.png) |
| V2-08 텔레그램 | 토큰 틀림 | 1440 | [345:258107](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-258107) | [V2-08__토큰_틀림__1440__345-258107.png](frames/V2-08__토큰_틀림__1440__345-258107.png) |
| V2-09 DART | 받기 시작 | 1440 | [345:258524](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-258524) | [V2-09__받기_시작__1440__345-258524.png](frames/V2-09__받기_시작__1440__345-258524.png) |
| V2-09 DART | 없음 | 1440 | [345:258336](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-258336) | [V2-09__없음__1440__345-258336.png](frames/V2-09__없음__1440__345-258336.png) |
| V2-09 DART | 오류 | 1440 | [345:258625](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-258625) | [V2-09__오류__1440__345-258625.png](frames/V2-09__오류__1440__345-258625.png) |
| V2-09 DART | 확인 중 | 1440 | [345:258430](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-258430) | [V2-09__확인_중__1440__345-258430.png](frames/V2-09__확인_중__1440__345-258430.png) |
| V2-10 자산 | 로딩 | 1440 | [345:193610](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-193610) | [V2-10__로딩__1440__345-193610.png](frames/V2-10__로딩__1440__345-193610.png) |
| V2-10 자산 | 새 매수 멈춤 | 1440 | [345:191097](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-191097) | [V2-10__새_매수_멈춤__1440__345-191097.png](frames/V2-10__새_매수_멈춤__1440__345-191097.png) |
| V2-10 자산 | 운용 끝낸 뒤 | 1440 | [331:167708](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-167708) | [V2-10__운용_끝낸_뒤__1440__331-167708.png](frames/V2-10__운용_끝낸_뒤__1440__331-167708.png) |
| V2-10 자산 | 운용 전 · 마법사 직후 | 1440 | [345:431103](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-431103) | [V2-10__운용_전-마법사_직후__1440__345-431103.png](frames/V2-10__운용_전-마법사_직후__1440__345-431103.png) |
| V2-10 자산 | 운용 전 · 준비 끝 | 1440 | [328:134287](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=328-134287) | [V2-10__운용_전-준비_끝__1440__328-134287.png](frames/V2-10__운용_전-준비_끝__1440__328-134287.png) |
| V2-10 자산 | 운용 중 | 1440 | [331:166011](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-166011) | [V2-10__운용_중__1440__331-166011.png](frames/V2-10__운용_중__1440__331-166011.png) |
| V2-10 자산 | 주문 멈춤 · 연결 끊김 | 1440 | [345:191472](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-191472) | [V2-10__주문_멈춤-연결_끊김__1440__345-191472.png](frames/V2-10__주문_멈춤-연결_끊김__1440__345-191472.png) |
| V2-10 자산 | 주문 멈춤 · 응답 이상 | 1440 | [345:192697](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-192697) | [V2-10__주문_멈춤-응답_이상__1440__345-192697.png](frames/V2-10__주문_멈춤-응답_이상__1440__345-192697.png) |
| V2-10 자산 | 주문 멈춤 · 점검 실패 | 1440 | [345:191890](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-191890) | [V2-10__주문_멈춤-점검_실패__1440__345-191890.png](frames/V2-10__주문_멈춤-점검_실패__1440__345-191890.png) |
| V2-10 자산 | 주문 멈춤 · 확인 실패 | 1440 | [345:192308](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-192308) | [V2-10__주문_멈춤-확인_실패__1440__345-192308.png](frames/V2-10__주문_멈춤-확인_실패__1440__345-192308.png) |
| V2-10 자산 | 첫 확인 전 | 1440 | [331:171918](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-171918) | [V2-10__첫_확인_전__1440__331-171918.png](frames/V2-10__첫_확인_전__1440__331-171918.png) |
| V2-10 자산 | 토스 연결 전 | 1440 | [345:193525](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-193525) | [V2-10__토스_연결_전__1440__345-193525.png](frames/V2-10__토스_연결_전__1440__345-193525.png) |
| V2-10 자산 | 할 일 빨강 | 1440 | [345:193115](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-193115) | [V2-10__할_일_빨강__1440__345-193115.png](frames/V2-10__할_일_빨강__1440__345-193115.png) |
| V2-10 자산 | 로딩 | 390 | [345:201074](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-201074) | [V2-10__로딩__390__345-201074.png](frames/V2-10__로딩__390__345-201074.png) |
| V2-10 자산 | 새 매수 멈춤 | 390 | [345:198580](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-198580) | [V2-10__새_매수_멈춤__390__345-198580.png](frames/V2-10__새_매수_멈춤__390__345-198580.png) |
| V2-10 자산 | 운용 끝낸 뒤 | 390 | [331:167864](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-167864) | [V2-10__운용_끝낸_뒤__390__331-167864.png](frames/V2-10__운용_끝낸_뒤__390__331-167864.png) |
| V2-10 자산 | 운용 전 · 준비 끝 | 390 | [328:134445](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=328-134445) | [V2-10__운용_전-준비_끝__390__328-134445.png](frames/V2-10__운용_전-준비_끝__390__328-134445.png) |
| V2-10 자산 | 운용 중 | 390 | [331:166343](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-166343) | [V2-10__운용_중__390__331-166343.png](frames/V2-10__운용_중__390__331-166343.png) |
| V2-10 자산 | 주문 멈춤 · 연결 끊김 | 390 | [345:198950](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-198950) | [V2-10__주문_멈춤-연결_끊김__390__345-198950.png](frames/V2-10__주문_멈춤-연결_끊김__390__345-198950.png) |
| V2-10 자산 | 주문 멈춤 · 응답 이상 | 390 | [345:200160](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-200160) | [V2-10__주문_멈춤-응답_이상__390__345-200160.png](frames/V2-10__주문_멈춤-응답_이상__390__345-200160.png) |
| V2-10 자산 | 주문 멈춤 · 점검 실패 | 390 | [345:199363](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-199363) | [V2-10__주문_멈춤-점검_실패__390__345-199363.png](frames/V2-10__주문_멈춤-점검_실패__390__345-199363.png) |
| V2-10 자산 | 주문 멈춤 · 확인 실패 | 390 | [345:199776](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-199776) | [V2-10__주문_멈춤-확인_실패__390__345-199776.png](frames/V2-10__주문_멈춤-확인_실패__390__345-199776.png) |
| V2-10 자산 | 첫 확인 전 | 390 | [331:172117](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-172117) | [V2-10__첫_확인_전__390__331-172117.png](frames/V2-10__첫_확인_전__390__331-172117.png) |
| V2-10 자산 | 토스 연결 전 | 390 | [345:200978](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-200978) | [V2-10__토스_연결_전__390__345-200978.png](frames/V2-10__토스_연결_전__390__345-200978.png) |
| V2-10 자산 | 할 일 빨강 | 390 | [345:200573](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-200573) | [V2-10__할_일_빨강__390__345-200573.png](frames/V2-10__할_일_빨강__390__345-200573.png) |
| V2-11 계획 | 계획 없음 | 1440 | [314:98882](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-98882) | [V2-11__계획_없음__1440__314-98882.png](frames/V2-11__계획_없음__1440__314-98882.png) |
| V2-11 계획 | 계획 있음 | 1440 | [314:98796](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-98796) | [V2-11__계획_있음__1440__314-98796.png](frames/V2-11__계획_있음__1440__314-98796.png) |
| V2-11 계획 | 운용 없음 | 1440 | [345:233537](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-233537) | [V2-11__운용_없음__1440__345-233537.png](frames/V2-11__운용_없음__1440__345-233537.png) |
| V2-11 계획 | 점검 실패 | 1440 | [345:232658](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-232658) | [V2-11__점검_실패__1440__345-232658.png](frames/V2-11__점검_실패__1440__345-232658.png) |
| V2-11 계획 | 주문 보낸 뒤 | 1440 | [345:233108](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-233108) | [V2-11__주문_보낸_뒤__1440__345-233108.png](frames/V2-11__주문_보낸_뒤__1440__345-233108.png) |
| V2-11 계획 | 확인 실패 | 1440 | [345:232367](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-232367) | [V2-11__확인_실패__1440__345-232367.png](frames/V2-11__확인_실패__1440__345-232367.png) |
| V2-11 계획 | 확인 전 | 1440 | [314:98940](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-98940) | [V2-11__확인_전__1440__314-98940.png](frames/V2-11__확인_전__1440__314-98940.png) |
| V2-11 계획 | 확인 중 | 1440 | [314:99093](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-99093) | [V2-11__확인_중__1440__314-99093.png](frames/V2-11__확인_중__1440__314-99093.png) |
| V2-11 계획 | 계획 없음 | 390 | [306:89671](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=306-89671) | [V2-11__계획_없음__390__306-89671.png](frames/V2-11__계획_없음__390__306-89671.png) |
| V2-11 계획 | 계획 있음 | 390 | [306:89580](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=306-89580) | [V2-11__계획_있음__390__306-89580.png](frames/V2-11__계획_있음__390__306-89580.png) |
| V2-11 계획 | 운용 없음 | 390 | [345:233581](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-233581) | [V2-11__운용_없음__390__345-233581.png](frames/V2-11__운용_없음__390__345-233581.png) |
| V2-11 계획 | 점검 실패 | 390 | [345:232883](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-232883) | [V2-11__점검_실패__390__345-232883.png](frames/V2-11__점검_실패__390__345-232883.png) |
| V2-11 계획 | 주문 보낸 뒤 | 390 | [345:233325](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-233325) | [V2-11__주문_보낸_뒤__390__345-233325.png](frames/V2-11__주문_보낸_뒤__390__345-233325.png) |
| V2-11 계획 | 확인 실패 | 390 | [345:232507](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-232507) | [V2-11__확인_실패__390__345-232507.png](frames/V2-11__확인_실패__390__345-232507.png) |
| V2-11 계획 | 확인 전 | 390 | [306:89734](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=306-89734) | [V2-11__확인_전__390__306-89734.png](frames/V2-11__확인_전__390__306-89734.png) |
| V2-11 계획 | 확인 중 | 390 | [314:98558](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-98558) | [V2-11__확인_중__390__314-98558.png](frames/V2-11__확인_중__390__314-98558.png) |
| V2-12 기록 | 거래 0회 | 1440 | [314:100030](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-100030) | [V2-12__거래_0회__1440__314-100030.png](frames/V2-12__거래_0회__1440__314-100030.png) |
| V2-12 기록 | 거래 있음 | 1440 | [314:99712](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-99712) | [V2-12__거래_있음__1440__314-99712.png](frames/V2-12__거래_있음__1440__314-99712.png) |
| V2-12 기록 | 빈 | 1440 | [314:99887](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-99887) | [V2-12__빈__1440__314-99887.png](frames/V2-12__빈__1440__314-99887.png) |
| V2-12 기록 | 지난 운용 | 1440 | [314:99928](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-99928) | [V2-12__지난_운용__1440__314-99928.png](frames/V2-12__지난_운용__1440__314-99928.png) |
| V2-12 기록 | 필터 실패 | 1440 | [331:150964](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-150964) | [V2-12__필터_실패__1440__331-150964.png](frames/V2-12__필터_실패__1440__331-150964.png) |
| V2-12 기록 | 거래 0회 | 390 | [314:99646](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-99646) | [V2-12__거래_0회__390__314-99646.png](frames/V2-12__거래_0회__390__314-99646.png) |
| V2-12 기록 | 거래 있음 | 390 | [306:89797](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=306-89797) | [V2-12__거래_있음__390__306-89797.png](frames/V2-12__거래_있음__390__306-89797.png) |
| V2-12 기록 | 빈 | 390 | [306:89968](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=306-89968) | [V2-12__빈__390__306-89968.png](frames/V2-12__빈__390__306-89968.png) |
| V2-12 기록 | 지난 운용 | 390 | [314:99542](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-99542) | [V2-12__지난_운용__390__314-99542.png](frames/V2-12__지난_운용__390__314-99542.png) |
| V2-12 기록 | 필터 실패 | 390 | [345:241053](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-241053) | [V2-12__필터_실패__390__345-241053.png](frames/V2-12__필터_실패__390__345-241053.png) |
| V2-13 할 일 · 알림 | 알림 · 로딩 | 1440 | [345:250812](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-250812) | [V2-13__알림-로딩__1440__345-250812.png](frames/V2-13__알림-로딩__1440__345-250812.png) |
| V2-13 할 일 · 알림 | 알림 · 빈 | 1440 | [345:250644](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-250644) | [V2-13__알림-빈__1440__345-250644.png](frames/V2-13__알림-빈__1440__345-250644.png) |
| V2-13 할 일 · 알림 | 알림 · 있음 | 1440 | [345:250314](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-250314) | [V2-13__알림-있음__1440__345-250314.png](frames/V2-13__알림-있음__1440__345-250314.png) |
| V2-13 할 일 · 알림 | 알림 · 로딩 | 390 | [345:250867](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-250867) | [V2-13__알림-로딩__390__345-250867.png](frames/V2-13__알림-로딩__390__345-250867.png) |
| V2-13 할 일 · 알림 | 알림 · 빈 | 390 | [345:250737](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-250737) | [V2-13__알림-빈__390__345-250737.png](frames/V2-13__알림-빈__390__345-250737.png) |
| V2-13 할 일 · 알림 | 알림 · 있음 | 390 | [345:250488](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-250488) | [V2-13__알림-있음__390__345-250488.png](frames/V2-13__알림-있음__390__345-250488.png) |
| V2-14 할 일 상세 | 닫힘 | 1440 | [345:254788](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-254788) | [V2-14__닫힘__1440__345-254788.png](frames/V2-14__닫힘__1440__345-254788.png) |
| V2-14 할 일 상세 | 열림 | 1440 | [345:254368](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-254368) | [V2-14__열림__1440__345-254368.png](frames/V2-14__열림__1440__345-254368.png) |
| V2-14 할 일 상세 | 열림 · 결과 모르는 주문 | 1440 | [345:255212](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-255212) | [V2-14__열림-결과_모르는_주문__1440__345-255212.png](frames/V2-14__열림-결과_모르는_주문__1440__345-255212.png) |
| V2-14 할 일 상세 | 열림 · 계좌 불일치 | 1440 | [345:255456](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-255456) | [V2-14__열림-계좌_불일치__1440__345-255456.png](frames/V2-14__열림-계좌_불일치__1440__345-255456.png) |
| V2-14 할 일 상세 | 열림 · 권리 변동 | 1440 | [345:431475](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-431475) | [V2-14__열림-권리_변동__1440__345-431475.png](frames/V2-14__열림-권리_변동__1440__345-431475.png) |
| V2-14 할 일 상세 | 오류 | 1440 | [345:254990](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-254990) | [V2-14__오류__1440__345-254990.png](frames/V2-14__오류__1440__345-254990.png) |
| V2-14 할 일 상세 | 처리 중 | 1440 | [345:254572](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-254572) | [V2-14__처리_중__1440__345-254572.png](frames/V2-14__처리_중__1440__345-254572.png) |
| V2-14 할 일 상세 | 닫힘 | 390 | [345:254898](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-254898) | [V2-14__닫힘__390__345-254898.png](frames/V2-14__닫힘__390__345-254898.png) |
| V2-14 할 일 상세 | 열림 | 390 | [345:254479](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-254479) | [V2-14__열림__390__345-254479.png](frames/V2-14__열림__390__345-254479.png) |
| V2-14 할 일 상세 | 열림 · 결과 모르는 주문 | 390 | [345:255343](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-255343) | [V2-14__열림-결과_모르는_주문__390__345-255343.png](frames/V2-14__열림-결과_모르는_주문__390__345-255343.png) |
| V2-14 할 일 상세 | 열림 · 계좌 불일치 | 390 | [345:255562](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-255562) | [V2-14__열림-계좌_불일치__390__345-255562.png](frames/V2-14__열림-계좌_불일치__390__345-255562.png) |
| V2-14 할 일 상세 | 열림 · 권리 변동 | 390 | [345:431677](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-431677) | [V2-14__열림-권리_변동__390__345-431677.png](frames/V2-14__열림-권리_변동__390__345-431677.png) |
| V2-14 할 일 상세 | 오류 | 390 | [345:255110](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-255110) | [V2-14__오류__390__345-255110.png](frames/V2-14__오류__390__345-255110.png) |
| V2-14 할 일 상세 | 처리 중 | 390 | [345:254689](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-254689) | [V2-14__처리_중__390__345-254689.png](frames/V2-14__처리_중__390__345-254689.png) |
| V2-20 전략 목록 | 빈 | 1440 | [328:134606](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=328-134606) | [V2-20__빈__1440__328-134606.png](frames/V2-20__빈__1440__328-134606.png) |
| V2-20 전략 목록 | 전략 있음 | 1440 | [314:100364](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-100364) | [V2-20__전략_있음__1440__314-100364.png](frames/V2-20__전략_있음__1440__314-100364.png) |
| V2-21 새 전략 시트 | 기본 | 1440 | [328:135486](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=328-135486) | [V2-21__기본__1440__328-135486.png](frames/V2-21__기본__1440__328-135486.png) |
| V2-21 새 전략 시트 | 기본 | 390 | [328:135374](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=328-135374) | [V2-21__기본__390__328-135374.png](frames/V2-21__기본__390__328-135374.png) |
| V2-22 붙여 넣기 | 모르는 조건 | 1440 | [345:259108](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-259108) | [V2-22__모르는_조건__1440__345-259108.png](frames/V2-22__모르는_조건__1440__345-259108.png) |
| V2-22 붙여 넣기 | 붙여 넣기 | 1440 | [345:258918](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-258918) | [V2-22__붙여_넣기__1440__345-258918.png](frames/V2-22__붙여_넣기__1440__345-258918.png) |
| V2-22 붙여 넣기 | 앱 버전이 낮음 | 1440 | [345:259042](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-259042) | [V2-22__앱_버전이_낮음__1440__345-259042.png](frames/V2-22__앱_버전이_낮음__1440__345-259042.png) |
| V2-22 붙여 넣기 | 연결이 맞지 않아 거절 | 1440 | [331:150910](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-150910) | [V2-22__연결이_맞지_않아_거절__1440__331-150910.png](frames/V2-22__연결이_맞지_않아_거절__1440__331-150910.png) |
| V2-22 붙여 넣기 | 형식 아님 | 1440 | [345:258976](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-258976) | [V2-22__형식_아님__1440__345-258976.png](frames/V2-22__형식_아님__1440__345-258976.png) |
| V2-22 붙여 넣기 | 확인 | 1440 | [327:132753](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=327-132753) | [V2-22__확인__1440__327-132753.png](frames/V2-22__확인__1440__327-132753.png) |
| V2-22 붙여 넣기 | 붙여 넣기 | 390 | [310:93885](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=310-93885) | [V2-22__붙여_넣기__390__310-93885.png](frames/V2-22__붙여_넣기__390__310-93885.png) |
| V2-22 붙여 넣기 | 연결이 맞지 않아 거절 | 390 | [331:150870](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-150870) | [V2-22__연결이_맞지_않아_거절__390__331-150870.png](frames/V2-22__연결이_맞지_않아_거절__390__331-150870.png) |
| V2-22 붙여 넣기 | 형식 아님 | 390 | [310:93916](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=310-93916) | [V2-22__형식_아님__390__310-93916.png](frames/V2-22__형식_아님__390__310-93916.png) |
| V2-22 붙여 넣기 | 확인 | 390 | [327:133449](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=327-133449) | [V2-22__확인__390__327-133449.png](frames/V2-22__확인__390__327-133449.png) |
| V2-23 편집기 | ⑥ → ⑥ 확인 창 | 1440 | [331:144366](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-144366) | [V2-23__⑥_→_⑥_확인_창__1440__331-144366.png](frames/V2-23__⑥_→_⑥_확인_창__1440__331-144366.png) |
| V2-23 편집기 | 가운데 단계 삭제 뒤 | 1440 | [331:148222](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-148222) | [V2-23__가운데_단계_삭제_뒤__1440__331-148222.png](frames/V2-23__가운데_단계_삭제_뒤__1440__331-148222.png) |
| V2-23 편집기 | 경로가 많을 때 | 1440 | [331:148729](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-148729) | [V2-23__경로가_많을_때__1440__331-148729.png](frames/V2-23__경로가_많을_때__1440__331-148729.png) |
| V2-23 편집기 | 기본(문제 없음) | 1440 | [324:117378](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=324-117378) | [V2-23__기본(문제_없음)__1440__324-117378.png](frames/V2-23__기본%28문제_없음%29__1440__324-117378.png) |
| V2-23 편집기 | 나가기 확인 | 1440 | [326:127098](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=326-127098) | [V2-23__나가기_확인__1440__326-127098.png](frames/V2-23__나가기_확인__1440__326-127098.png) |
| V2-23 편집기 | 눌러서 추가 | 1440 | [326:129522](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=326-129522) | [V2-23__눌러서_추가__1440__326-129522.png](frames/V2-23__눌러서_추가__1440__326-129522.png) |
| V2-23 편집기 | 다음 단계 연결 | 1440 | [331:144889](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-144889) | [V2-23__다음_단계_연결__1440__331-144889.png](frames/V2-23__다음_단계_연결__1440__331-144889.png) |
| V2-23 편집기 | 단계 끌어 오는 중 | 1440 | [325:119011](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=325-119011) | [V2-23__단계_끌어_오는_중__1440__325-119011.png](frames/V2-23__단계_끌어_오는_중__1440__325-119011.png) |
| V2-23 편집기 | 단축키 | 1440 | [331:145440](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-145440) | [V2-23__단축키__1440__331-145440.png](frames/V2-23__단축키__1440__331-145440.png) |
| V2-23 편집기 | 데이터 받는 중 | 1440 | [345:224505](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-224505) | [V2-23__데이터_받는_중__1440__345-224505.png](frames/V2-23__데이터_받는_중__1440__345-224505.png) |
| V2-23 편집기 | 리밸런싱 방식 빈칸 | 1440 | [326:123215](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=326-123215) | [V2-23__리밸런싱_방식_빈칸__1440__326-123215.png](frames/V2-23__리밸런싱_방식_빈칸__1440__326-123215.png) |
| V2-23 편집기 | 리밸런싱 방식에서 신호 줄을 고름 | 1440 | [331:147766](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-147766) | [V2-23__리밸런싱_방식에서_신호_줄을_고름__1440__331-147766.png](frames/V2-23__리밸런싱_방식에서_신호_줄을_고름__1440__331-147766.png) |
| V2-23 편집기 | 머리 토글 바꿈 | 1440 | [345:214380](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-214380) | [V2-23__머리_토글_바꿈__1440__345-214380.png](frames/V2-23__머리_토글_바꿈__1440__345-214380.png) |
| V2-23 편집기 | 문장으로 보기 | 1440 | [345:186346](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-186346) | [V2-23__문장으로_보기__1440__345-186346.png](frames/V2-23__문장으로_보기__1440__345-186346.png) |
| V2-23 편집기 | 문제 있음 · 문제 목록 펼침 | 1440 | [325:117895](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=325-117895) | [V2-23__문제_있음-문제_목록_펼침__1440__325-117895.png](frames/V2-23__문제_있음-문제_목록_펼침__1440__325-117895.png) |
| V2-23 편집기 | 문제 있음 · 문제를 누른 뒤 | 1440 | [325:118490](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=325-118490) | [V2-23__문제_있음-문제를_누른_뒤__1440__325-118490.png](frames/V2-23__문제_있음-문제를_누른_뒤__1440__325-118490.png) |
| V2-23 편집기 | 방식 바뀜 알림 · 리밸런싱 주기 삭제 뒤 | 1440 | [331:146510](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-146510) | [V2-23__방식_바뀜_알림-리밸런싱_주기_삭제_뒤__1440__331-146510.png](frames/V2-23__방식_바뀜_알림-리밸런싱_주기_삭제_뒤__1440__331-146510.png) |
| V2-23 편집기 | 방식 바뀜 알림 · 순위 교체로 | 1440 | [326:123681](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=326-123681) | [V2-23__방식_바뀜_알림-순위_교체로__1440__326-123681.png](frames/V2-23__방식_바뀜_알림-순위_교체로__1440__326-123681.png) |
| V2-23 편집기 | 버전 3 저장 전 · 10/2 | 1440 | [345:428251](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-428251) | [V2-23__버전_3_저장_전-10-2__1440__345-428251.png](frames/V2-23__버전_3_저장_전-10-2__1440__345-428251.png) |
| V2-23 편집기 | 빈 캔버스 | 1440 | [324:116962](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=324-116962) | [V2-23__빈_캔버스__1440__324-116962.png](frames/V2-23__빈_캔버스__1440__324-116962.png) |
| V2-23 편집기 | 선 잇는 중 · 맞는 곳 | 1440 | [325:119551](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=325-119551) | [V2-23__선_잇는_중-맞는_곳__1440__325-119551.png](frames/V2-23__선_잇는_중-맞는_곳__1440__325-119551.png) |
| V2-23 편집기 | 선 잇는 중 · 안 되는 곳 | 1440 | [326:122208](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=326-122208) | [V2-23__선_잇는_중-안_되는_곳__1440__326-122208.png](frames/V2-23__선_잇는_중-안_되는_곳__1440__326-122208.png) |
| V2-23 편집기 | 선을 고름 | 1440 | [326:126110](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=326-126110) | [V2-23__선을_고름__1440__326-126110.png](frames/V2-23__선을_고름__1440__326-126110.png) |
| V2-23 편집기 | 실행 방식 · 고르기 | 1440 | [345:220695](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-220695) | [V2-23__실행_방식-고르기__1440__345-220695.png](frames/V2-23__실행_방식-고르기__1440__345-220695.png) |
| V2-23 편집기 | 실행 방식 · 종가 확인으로 바뀜 | 1440 | [345:221951](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-221951) | [V2-23__실행_방식-종가_확인으로_바뀜__1440__345-221951.png](frames/V2-23__실행_방식-종가_확인으로_바뀜__1440__345-221951.png) |
| V2-23 편집기 | 자동 정렬 결과 · 분기 있음 | 1440 | [331:143833](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-143833) | [V2-23__자동_정렬_결과-분기_있음__1440__331-143833.png](frames/V2-23__자동_정렬_결과-분기_있음__1440__331-143833.png) |
| V2-23 편집기 | 잠긴 줄 | 1440 | [345:223221](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-223221) | [V2-23__잠긴_줄__1440__345-223221.png](frames/V2-23__잠긴_줄__1440__345-223221.png) |
| V2-23 편집기 | 저장한 뒤 | 1440 | [331:145977](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-145977) | [V2-23__저장한_뒤__1440__331-145977.png](frames/V2-23__저장한_뒤__1440__331-145977.png) |
| V2-23 편집기 | 저장한 뒤 · 버전 3 · 10/2 | 1440 | [345:429666](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-429666) | [V2-23__저장한_뒤-버전_3-10-2__1440__345-429666.png](frames/V2-23__저장한_뒤-버전_3-10-2__1440__345-429666.png) |
| V2-23 편집기 | 조건 추가 메뉴 · 검색 | 1440 | [345:203739](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-203739) | [V2-23__조건_추가_메뉴-검색__1440__345-203739.png](frames/V2-23__조건_추가_메뉴-검색__1440__345-203739.png) |
| V2-23 편집기 | 조건 추가 메뉴 · 분류 | 1440 | [345:201134](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-201134) | [V2-23__조건_추가_메뉴-분류__1440__345-201134.png](frames/V2-23__조건_추가_메뉴-분류__1440__345-201134.png) |
| V2-23 편집기 | 조건 추가 메뉴 · 잠긴 분류 | 1440 | [345:202428](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-202428) | [V2-23__조건_추가_메뉴-잠긴_분류__1440__345-202428.png](frames/V2-23__조건_추가_메뉴-잠긴_분류__1440__345-202428.png) |
| V2-23 편집기 | 줄 삭제 뒤 | 1440 | [326:126602](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=326-126602) | [V2-23__줄_삭제_뒤__1440__326-126602.png](frames/V2-23__줄_삭제_뒤__1440__326-126602.png) |
| V2-23 편집기 | 줄 편집 | 1440 | [326:122715](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=326-122715) | [V2-23__줄_편집__1440__326-122715.png](frames/V2-23__줄_편집__1440__326-122715.png) |
| V2-24 좁은 창 | 보기만 | 390 | [329:136085](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=329-136085) | [V2-24__보기만__390__329-136085.png](frames/V2-24__보기만__390__329-136085.png) |
| V2-25 전략 상세 | 모의투자 중 | 1440 | [314:101169](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-101169) | [V2-25__모의투자_중__1440__314-101169.png](frames/V2-25__모의투자_중__1440__314-101169.png) |
| V2-25 전략 상세 | 문제 있음 | 1440 | [314:101543](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-101543) | [V2-25__문제_있음__1440__314-101543.png](frames/V2-25__문제_있음__1440__314-101543.png) |
| V2-25 전략 상세 | 백테스트 안 한 버전 | 1440 | [345:266189](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-266189) | [V2-25__백테스트_안_한_버전__1440__345-266189.png](frames/V2-25__백테스트_안_한_버전__1440__345-266189.png) |
| V2-25 전략 상세 | 실전 운용 중 | 1440 | [345:264645](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-264645) | [V2-25__실전_운용_중__1440__345-264645.png](frames/V2-25__실전_운용_중__1440__345-264645.png) |
| V2-25 전략 상세 | 운용 전 | 1440 | [327:132945](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=327-132945) | [V2-25__운용_전__1440__327-132945.png](frames/V2-25__운용_전__1440__327-132945.png) |
| V2-25 전략 상세 | 모의투자 중 | 390 | [310:93564](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=310-93564) | [V2-25__모의투자_중__390__310-93564.png](frames/V2-25__모의투자_중__390__310-93564.png) |
| V2-25 전략 상세 | 문제 있음 | 390 | [314:100827](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-100827) | [V2-25__문제_있음__390__314-100827.png](frames/V2-25__문제_있음__390__314-100827.png) |
| V2-25 전략 상세 | 운용 전 | 390 | [327:133207](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=327-133207) | [V2-25__운용_전__390__327-133207.png](frames/V2-25__운용_전__390__327-133207.png) |
| V2-26 백테스트 | DART 받는 중 | 1440 | [345:285169](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-285169) | [V2-26__DART_받는_중__1440__345-285169.png](frames/V2-26__DART_받는_중__1440__345-285169.png) |
| V2-26 백테스트 | 결과 | 1440 | [311:95007](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=311-95007) | [V2-26__결과__1440__311-95007.png](frames/V2-26__결과__1440__311-95007.png) |
| V2-26 백테스트 | 문제 있음 | 1440 | [345:286285](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-286285) | [V2-26__문제_있음__1440__345-286285.png](frames/V2-26__문제_있음__1440__345-286285.png) |
| V2-26 백테스트 | 시세 못 받음 | 1440 | [311:95189](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=311-95189) | [V2-26__시세_못_받음__1440__311-95189.png](frames/V2-26__시세_못_받음__1440__311-95189.png) |
| V2-26 백테스트 | 시세 받는 중 | 1440 | [345:285076](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-285076) | [V2-26__시세_받는_중__1440__345-285076.png](frames/V2-26__시세_받는_중__1440__345-285076.png) |
| V2-26 백테스트 | 실행 중 | 1440 | [311:94916](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=311-94916) | [V2-26__실행_중__1440__311-94916.png](frames/V2-26__실행_중__1440__311-94916.png) |
| V2-26 백테스트 | 입력 | 1440 | [311:94832](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=311-94832) | [V2-26__입력__1440__311-94832.png](frames/V2-26__입력__1440__311-94832.png) |
| V2-26 백테스트 | 토스 연결 전 | 1440 | [345:286377](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-286377) | [V2-26__토스_연결_전__1440__345-286377.png](frames/V2-26__토스_연결_전__1440__345-286377.png) |
| V2-26 백테스트 | 결과 | 390 | [311:94596](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=311-94596) | [V2-26__결과__390__311-94596.png](frames/V2-26__결과__390__311-94596.png) |
| V2-26 백테스트 | 시세 못 받음 | 390 | [311:94760](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=311-94760) | [V2-26__시세_못_받음__390__311-94760.png](frames/V2-26__시세_못_받음__390__311-94760.png) |
| V2-26 백테스트 | 실행 중 | 390 | [311:94523](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=311-94523) | [V2-26__실행_중__390__311-94523.png](frames/V2-26__실행_중__390__311-94523.png) |
| V2-26 백테스트 | 입력 | 390 | [311:94459](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=311-94459) | [V2-26__입력__390__311-94459.png](frames/V2-26__입력__390__311-94459.png) |
| V2-30 실전 운용 시작 | 기본 · 모두 통과 | 1440 | [345:259865](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-259865) | [V2-30__기본-모두_통과__1440__345-259865.png](frames/V2-30__기본-모두_통과__1440__345-259865.png) |
| V2-30 실전 운용 시작 | 미리 보기 계산 중 | 1440 | [345:261464](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-261464) | [V2-30__미리_보기_계산_중__1440__345-261464.png](frames/V2-30__미리_보기_계산_중__1440__345-261464.png) |
| V2-30 실전 운용 시작 | 미리 보기 못 함 | 1440 | [345:261706](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-261706) | [V2-30__미리_보기_못_함__1440__345-261706.png](frames/V2-30__미리_보기_못_함__1440__345-261706.png) |
| V2-30 실전 운용 시작 | 비밀번호 창 | 1440 | [345:262983](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-262983) | [V2-30__비밀번호_창__1440__345-262983.png](frames/V2-30__비밀번호_창__1440__345-262983.png) |
| V2-30 실전 운용 시작 | 손절 없음 | 1440 | [345:262289](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-262289) | [V2-30__손절_없음__1440__345-262289.png](frames/V2-30__손절_없음__1440__345-262289.png) |
| V2-30 실전 운용 시작 | 시작됨 | 1440 | [345:262985](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-262985) | [V2-30__시작됨__1440__345-262985.png](frames/V2-30__시작됨__1440__345-262985.png) |
| V2-30 실전 운용 시작 | 이미 운용 중 | 1440 | [345:261948](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-261948) | [V2-30__이미_운용_중__1440__345-261948.png](frames/V2-30__이미_운용_중__1440__345-261948.png) |
| V2-30 실전 운용 시작 | 입력 중 | 1440 | [345:261128](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-261128) | [V2-30__입력_중__1440__345-261128.png](frames/V2-30__입력_중__1440__345-261128.png) |
| V2-30 실전 운용 시작 | 확인 ✕ 있음 | 1440 | [345:259530](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-259530) | [V2-30__확인_✕_있음__1440__345-259530.png](frames/V2-30__확인_✕_있음__1440__345-259530.png) |
| V2-31 운용 설정 | 다음 확인부터 적용 예약됨 | 1440 | [345:265744](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-265744) | [V2-31__다음_확인부터_적용_예약됨__1440__345-265744.png](frames/V2-31__다음_확인부터_적용_예약됨__1440__345-265744.png) |
| V2-31 운용 설정 | 바꾸는 중 | 1440 | [345:265340](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-265340) | [V2-31__바꾸는_중__1440__345-265340.png](frames/V2-31__바꾸는_중__1440__345-265340.png) |
| V2-31 운용 설정 | 보기 | 1440 | [345:265179](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-265179) | [V2-31__보기__1440__345-265179.png](frames/V2-31__보기__1440__345-265179.png) |
| V2-31 운용 설정 | 비밀번호 창 | 1440 | [345:265742](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-265742) | [V2-31__비밀번호_창__1440__345-265742.png](frames/V2-31__비밀번호_창__1440__345-265742.png) |
| V2-32 멈추기 시트 | 기본 | 1440 | [345:271033](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-271033) | [V2-32__기본__1440__345-271033.png](frames/V2-32__기본__1440__345-271033.png) |
| V2-32 멈추기 시트 | 새 매수 멈춤 | 1440 | [345:270079](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-270079) | [V2-32__새_매수_멈춤__1440__345-270079.png](frames/V2-32__새_매수_멈춤__1440__345-270079.png) |
| V2-32 멈추기 시트 | 오류(취소 안 됨) | 1440 | [345:277130](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-277130) | [V2-32__오류(취소_안_됨)__1440__345-277130.png](frames/V2-32__오류%28취소_안_됨%29__1440__345-277130.png) |
| V2-32 멈추기 시트 | 운용 끝내기 | 1440 | [345:272944](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-272944) | [V2-32__운용_끝내기__1440__345-272944.png](frames/V2-32__운용_끝내기__1440__345-272944.png) |
| V2-32 멈추기 시트 | 장 밖 전부 팔기 | 1440 | [345:274966](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-274966) | [V2-32__장_밖_전부_팔기__1440__345-274966.png](frames/V2-32__장_밖_전부_팔기__1440__345-274966.png) |
| V2-32 멈추기 시트 | 장중 전부 팔기 | 1440 | [345:273941](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-273941) | [V2-32__장중_전부_팔기__1440__345-273941.png](frames/V2-32__장중_전부_팔기__1440__345-273941.png) |
| V2-32 멈추기 시트 | 처리 중 | 1440 | [345:276003](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-276003) | [V2-32__처리_중__1440__345-276003.png](frames/V2-32__처리_중__1440__345-276003.png) |
| V2-32 멈추기 시트 | 토스에서 멈추기 펼침 | 1440 | [345:420569](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-420569) | [V2-32__토스에서_멈추기_펼침__1440__345-420569.png](frames/V2-32__토스에서_멈추기_펼침__1440__345-420569.png) |
| V2-32 멈추기 시트 | 기본 | 390 | [345:271484](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-271484) | [V2-32__기본__390__345-271484.png](frames/V2-32__기본__390__345-271484.png) |
| V2-32 멈추기 시트 | 새 매수 멈춤 | 390 | [345:270541](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-270541) | [V2-32__새_매수_멈춤__390__345-270541.png](frames/V2-32__새_매수_멈춤__390__345-270541.png) |
| V2-32 멈추기 시트 | 오류(취소 안 됨) | 390 | [345:277601](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-277601) | [V2-32__오류(취소_안_됨)__390__345-277601.png](frames/V2-32__오류%28취소_안_됨%29__390__345-277601.png) |
| V2-32 멈추기 시트 | 운용 끝내기 | 390 | [345:273410](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-273410) | [V2-32__운용_끝내기__390__345-273410.png](frames/V2-32__운용_끝내기__390__345-273410.png) |
| V2-32 멈추기 시트 | 장 밖 전부 팔기 | 390 | [345:275460](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-275460) | [V2-32__장_밖_전부_팔기__390__345-275460.png](frames/V2-32__장_밖_전부_팔기__390__345-275460.png) |
| V2-32 멈추기 시트 | 장중 전부 팔기 | 390 | [345:274436](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-274436) | [V2-32__장중_전부_팔기__390__345-274436.png](frames/V2-32__장중_전부_팔기__390__345-274436.png) |
| V2-32 멈추기 시트 | 처리 중 | 390 | [345:276510](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-276510) | [V2-32__처리_중__390__345-276510.png](frames/V2-32__처리_중__390__345-276510.png) |
| V2-32 멈추기 시트 | 토스에서 멈추기 펼침 | 390 | [345:421271](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-421271) | [V2-32__토스에서_멈추기_펼침__390__345-421271.png](frames/V2-32__토스에서_멈추기_펼침__390__345-421271.png) |
| V2-33 비밀번호 확인 창 | 기본 | 1440 | [345:287562](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-287562) | [V2-33__기본__1440__345-287562.png](frames/V2-33__기본__1440__345-287562.png) |
| V2-33 비밀번호 확인 창 | 맞지 않음(남은 횟수) | 1440 | [345:288112](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-288112) | [V2-33__맞지_않음(남은_횟수)__1440__345-288112.png](frames/V2-33__맞지_않음%28남은_횟수%29__1440__345-288112.png) |
| V2-33 비밀번호 확인 창 | 잠금 5분 | 1440 | [345:288662](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-288662) | [V2-33__잠금_5분__1440__345-288662.png](frames/V2-33__잠금_5분__1440__345-288662.png) |
| V2-33 비밀번호 확인 창 | 할 일 해결 예 · 계좌에 맞추기 | 1440 | [345:288981](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-288981) | [V2-33__할_일_해결_예-계좌에_맞추기__1440__345-288981.png](frames/V2-33__할_일_해결_예-계좌에_맞추기__1440__345-288981.png) |
| V2-33 비밀번호 확인 창 | 기본 | 390 | [345:287747](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-287747) | [V2-33__기본__390__345-287747.png](frames/V2-33__기본__390__345-287747.png) |
| V2-33 비밀번호 확인 창 | 맞지 않음(남은 횟수) | 390 | [345:288297](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-288297) | [V2-33__맞지_않음(남은_횟수)__390__345-288297.png](frames/V2-33__맞지_않음%28남은_횟수%29__390__345-288297.png) |
| V2-33 비밀번호 확인 창 | 잠금 5분 | 390 | [345:288847](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-288847) | [V2-33__잠금_5분__390__345-288847.png](frames/V2-33__잠금_5분__390__345-288847.png) |
| V2-33 비밀번호 확인 창 | 할 일 해결 예 · 계좌에 맞추기 | 390 | [345:289099](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-289099) | [V2-33__할_일_해결_예-계좌에_맞추기__390__345-289099.png](frames/V2-33__할_일_해결_예-계좌에_맞추기__390__345-289099.png) |
| V2-40 모의투자 | 빈 | 1440 | [345:292494](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292494) | [V2-40__빈__1440__345-292494.png](frames/V2-40__빈__1440__345-292494.png) |
| V2-40 모의투자 | 있음 | 1440 | [345:292339](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292339) | [V2-40__있음__1440__345-292339.png](frames/V2-40__있음__1440__345-292339.png) |
| V2-41 모의투자 상세 | 끝내기 확인 | 1440 | [314:101147](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=314-101147) | [V2-41__끝내기_확인__1440__314-101147.png](frames/V2-41__끝내기_확인__1440__314-101147.png) |
| V2-41 모의투자 상세 | 끝낸 뒤 | 1440 | [345:294335](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-294335) | [V2-41__끝낸_뒤__1440__345-294335.png](frames/V2-41__끝낸_뒤__1440__345-294335.png) |
| V2-41 모의투자 상세 | 모의투자 중 | 1440 | [345:292548](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292548) | [V2-41__모의투자_중__1440__345-292548.png](frames/V2-41__모의투자_중__1440__345-292548.png) |
| V2-41 모의투자 상세 | 모의투자 중 · 계획 탭 | 1440 | [345:293827](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-293827) | [V2-41__모의투자_중-계획_탭__1440__345-293827.png](frames/V2-41__모의투자_중-계획_탭__1440__345-293827.png) |
| V2-41 모의투자 상세 | 모의투자 중 · 기록 탭 | 1440 | [345:293946](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-293946) | [V2-41__모의투자_중-기록_탭__1440__345-293946.png](frames/V2-41__모의투자_중-기록_탭__1440__345-293946.png) |
| V2-41 모의투자 상세 | 첫 확인 전 | 1440 | [345:294069](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-294069) | [V2-41__첫_확인_전__1440__345-294069.png](frames/V2-41__첫_확인_전__1440__345-294069.png) |
| V2-41 모의투자 상세 | 현금만 | 1440 | [331:167282](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-167282) | [V2-41__현금만__1440__331-167282.png](frames/V2-41__현금만__1440__331-167282.png) |
| V2-42 모의투자 시작 창 | 기본 | 1440 | [331:172322](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-172322) | [V2-42__기본__1440__331-172322.png](frames/V2-42__기본__1440__331-172322.png) |
| V2-42 모의투자 시작 창 | 이 전략은 이미 모의투자 중 | 1440 | [345:295144](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-295144) | [V2-42__이_전략은_이미_모의투자_중__1440__345-295144.png](frames/V2-42__이_전략은_이미_모의투자_중__1440__345-295144.png) |
| V2-42 모의투자 시작 창 | 기본 | 390 | [310:94233](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=310-94233) | [V2-42__기본__390__310-94233.png](frames/V2-42__기본__390__310-94233.png) |
| V2-42 모의투자 시작 창 | 이 전략은 이미 모의투자 중 | 390 | [310:94418](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=310-94418) | [V2-42__이_전략은_이미_모의투자_중__390__310-94418.png](frames/V2-42__이_전략은_이미_모의투자_중__390__310-94418.png) |
| V2-50 설정 | 기본 | 1440 | [331:171688](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-171688) | [V2-50__기본__1440__331-171688.png](frames/V2-50__기본__1440__331-171688.png) |
| V2-50 설정 | 기본 | 390 | [305:87696](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-87696) | [V2-50__기본__390__305-87696.png](frames/V2-50__기본__390__305-87696.png) |
| V2-51 연결 | 토스 변경 · DART 다 받음 | 1440 | [313:97570](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=313-97570) | [V2-51__토스_변경-DART_다_받음__1440__313-97570.png](frames/V2-51__토스_변경-DART_다_받음__1440__313-97570.png) |
| V2-51 연결 | 토스 삭제 확인 · DART 다 받음 | 1440 | [305:88451](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-88451) | [V2-51__토스_삭제_확인-DART_다_받음__1440__305-88451.png](frames/V2-51__토스_삭제_확인-DART_다_받음__1440__305-88451.png) |
| V2-51 연결 | 토스 실패 · 응답 없음 · DART 없음 | 1440 | [305:89008](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-89008) | [V2-51__토스_실패-응답_없음-DART_없음__1440__305-89008.png](frames/V2-51__토스_실패-응답_없음-DART_없음__1440__305-89008.png) |
| V2-51 연결 | 토스 실패 · 키 · DART 없음 | 1440 | [305:88744](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-88744) | [V2-51__토스_실패-키-DART_없음__1440__305-88744.png](frames/V2-51__토스_실패-키-DART_없음__1440__305-88744.png) |
| V2-51 연결 | 토스 실패 · 허용 IP · DART 없음 | 1440 | [305:88876](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-88876) | [V2-51__토스_실패-허용_IP-DART_없음__1440__305-88876.png](frames/V2-51__토스_실패-허용_IP-DART_없음__1440__305-88876.png) |
| V2-51 연결 | 토스 연결됨 · DART 다 받음 | 1440 | [305:88641](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-88641) | [V2-51__토스_연결됨-DART_다_받음__1440__305-88641.png](frames/V2-51__토스_연결됨-DART_다_받음__1440__305-88641.png) |
| V2-51 연결 | 토스 연결됨 · DART 받는 중 | 1440 | [345:278048](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-278048) | [V2-51__토스_연결됨-DART_받는_중__1440__345-278048.png](frames/V2-51__토스_연결됨-DART_받는_중__1440__345-278048.png) |
| V2-51 연결 | 토스 연결됨 · DART 삭제 확인 · 운용 중 · DART 다 받음 | 1440 | [345:367558](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-367558) | [V2-51__토스_연결됨-DART_삭제_확인-운용_중-DART_다_받음__1440__345-367558.png](frames/V2-51__토스_연결됨-DART_삭제_확인-운용_중-DART_다_받음__1440__345-367558.png) |
| V2-51 연결 | 토스 연결됨 · DART 오류 | 1440 | [345:278604](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-278604) | [V2-51__토스_연결됨-DART_오류__1440__345-278604.png](frames/V2-51__토스_연결됨-DART_오류__1440__345-278604.png) |
| V2-51 연결 | 토스 연결됨 · DART 한도 넘음 | 1440 | [345:278188](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-278188) | [V2-51__토스_연결됨-DART_한도_넘음__1440__345-278188.png](frames/V2-51__토스_연결됨-DART_한도_넘음__1440__345-278188.png) |
| V2-51 연결 | 토스 연결됨 · DART 확인 중 | 1440 | [345:277920](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-277920) | [V2-51__토스_연결됨-DART_확인_중__1440__345-277920.png](frames/V2-51__토스_연결됨-DART_확인_중__1440__345-277920.png) |
| V2-51 연결 | 토스 운용 중 계좌번호 잠김 · DART 다 받음 | 1440 | [345:277784](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-277784) | [V2-51__토스_운용_중_계좌번호_잠김-DART_다_받음__1440__345-277784.png](frames/V2-51__토스_운용_중_계좌번호_잠김-DART_다_받음__1440__345-277784.png) |
| V2-51 연결 | 토스 운용 중 삭제 막힘 · DART 다 받음 | 1440 | [345:277637](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-277637) | [V2-51__토스_운용_중_삭제_막힘-DART_다_받음__1440__345-277637.png](frames/V2-51__토스_운용_중_삭제_막힘-DART_다_받음__1440__345-277637.png) |
| V2-51 연결 | 토스 입력함 · DART 없음 | 1440 | [331:171802](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=331-171802) | [V2-51__토스_입력함-DART_없음__1440__331-171802.png](frames/V2-51__토스_입력함-DART_없음__1440__331-171802.png) |
| V2-51 연결 | 토스 키 없음 · DART 없음 | 1440 | [305:88347](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-88347) | [V2-51__토스_키_없음-DART_없음__1440__305-88347.png](frames/V2-51__토스_키_없음-DART_없음__1440__305-88347.png) |
| V2-51 연결 | 토스 확인 중 · DART 없음 | 1440 | [305:88535](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-88535) | [V2-51__토스_확인_중-DART_없음__1440__305-88535.png](frames/V2-51__토스_확인_중-DART_없음__1440__305-88535.png) |
| V2-51 연결 | 토스 변경 · DART 다 받음 | 390 | [313:96604](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=313-96604) | [V2-51__토스_변경-DART_다_받음__390__313-96604.png](frames/V2-51__토스_변경-DART_다_받음__390__313-96604.png) |
| V2-51 연결 | 토스 삭제 확인 · DART 다 받음 | 390 | [313:96732](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=313-96732) | [V2-51__토스_삭제_확인-DART_다_받음__390__313-96732.png](frames/V2-51__토스_삭제_확인-DART_다_받음__390__313-96732.png) |
| V2-51 연결 | 토스 실패 · 응답 없음 · DART 없음 | 390 | [305:88253](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-88253) | [V2-51__토스_실패-응답_없음-DART_없음__390__305-88253.png](frames/V2-51__토스_실패-응답_없음-DART_없음__390__305-88253.png) |
| V2-51 연결 | 토스 실패 · 키 · DART 없음 | 390 | [305:88065](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-88065) | [V2-51__토스_실패-키-DART_없음__390__305-88065.png](frames/V2-51__토스_실패-키-DART_없음__390__305-88065.png) |
| V2-51 연결 | 토스 실패 · 허용 IP · DART 없음 | 390 | [305:88159](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-88159) | [V2-51__토스_실패-허용_IP-DART_없음__390__305-88159.png](frames/V2-51__토스_실패-허용_IP-DART_없음__390__305-88159.png) |
| V2-51 연결 | 토스 연결됨 · DART 다 받음 | 390 | [305:87980](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-87980) | [V2-51__토스_연결됨-DART_다_받음__390__305-87980.png](frames/V2-51__토스_연결됨-DART_다_받음__390__305-87980.png) |
| V2-51 연결 | 토스 입력함 · DART 없음 | 390 | [305:87826](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-87826) | [V2-51__토스_입력함-DART_없음__390__305-87826.png](frames/V2-51__토스_입력함-DART_없음__390__305-87826.png) |
| V2-51 연결 | 토스 키 없음 · DART 없음 | 390 | [305:87740](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-87740) | [V2-51__토스_키_없음-DART_없음__390__305-87740.png](frames/V2-51__토스_키_없음-DART_없음__390__305-87740.png) |
| V2-51 연결 | 토스 확인 중 · DART 없음 | 390 | [305:87892](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=305-87892) | [V2-51__토스_확인_중-DART_없음__390__305-87892.png](frames/V2-51__토스_확인_중-DART_없음__390__305-87892.png) |
| V2-52 알림 | 보내기 실패 | 1440 | [345:291494](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-291494) | [V2-52__보내기_실패__1440__345-291494.png](frames/V2-52__보내기_실패__1440__345-291494.png) |
| V2-52 알림 | 연결 안 됨 | 1440 | [345:291229](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-291229) | [V2-52__연결_안_됨__1440__345-291229.png](frames/V2-52__연결_안_됨__1440__345-291229.png) |
| V2-52 알림 | 연결됨 | 1440 | [345:291360](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-291360) | [V2-52__연결됨__1440__345-291360.png](frames/V2-52__연결됨__1440__345-291360.png) |
| V2-52 알림 | 토큰 변경 · 비밀번호 | 1440 | [345:291629](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-291629) | [V2-52__토큰_변경-비밀번호__1440__345-291629.png](frames/V2-52__토큰_변경-비밀번호__1440__345-291629.png) |
| V2-52 알림 | 보내기 실패 | 390 | [345:291886](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-291886) | [V2-52__보내기_실패__390__345-291886.png](frames/V2-52__보내기_실패__390__345-291886.png) |
| V2-52 알림 | 연결됨 | 390 | [345:291772](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-291772) | [V2-52__연결됨__390__345-291772.png](frames/V2-52__연결됨__390__345-291772.png) |
| V2-53 데이터 | 기본 | 1440 | [345:292096](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292096) | [V2-53__기본__1440__345-292096.png](frames/V2-53__기본__1440__345-292096.png) |
| V2-53 데이터 | 받는 중 | 1440 | [345:292178](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292178) | [V2-53__받는_중__1440__345-292178.png](frames/V2-53__받는_중__1440__345-292178.png) |
| V2-53 데이터 | 복원 확인 | 1440 | [345:292263](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292263) | [V2-53__복원_확인__1440__345-292263.png](frames/V2-53__복원_확인__1440__345-292263.png) |
| V2-53 데이터 | 삭제 확인 · 운용 전 | 1440 | [345:292783](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292783) | [V2-53__삭제_확인-운용_전__1440__345-292783.png](frames/V2-53__삭제_확인-운용_전__1440__345-292783.png) |
| V2-54 비밀번호 변경 | 기본 | 1440 | [345:292881](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292881) | [V2-54__기본__1440__345-292881.png](frames/V2-54__기본__1440__345-292881.png) |
| V2-54 비밀번호 변경 | 맞지 않음 | 1440 | [345:292945](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-292945) | [V2-54__맞지_않음__1440__345-292945.png](frames/V2-54__맞지_않음__1440__345-292945.png) |
| V2-54 비밀번호 변경 | 기본 | 390 | [313:96023](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=313-96023) | [V2-54__기본__390__313-96023.png](frames/V2-54__기본__390__313-96023.png) |
| V2-55 사용 조건 · 앱 정보 | 앱 정보 · 기본 | 1440 | [345:293060](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-293060) | [V2-55__앱_정보-기본__1440__345-293060.png](frames/V2-55__앱_정보-기본__1440__345-293060.png) |
| V2-56 접속 | PC에서 Tailscale 없음 | 1440 | [345:293350](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-293350) | [V2-56__PC에서_Tailscale_없음__1440__345-293350.png](frames/V2-56__PC에서_Tailscale_없음__1440__345-293350.png) |
| V2-56 접속 | Tailscale 안 보임 | 1440 | [345:293245](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-293245) | [V2-56__Tailscale_안_보임__1440__345-293245.png](frames/V2-56__Tailscale_안_보임__1440__345-293245.png) |
| V2-56 접속 | 연결됨 | 1440 | [345:293145](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-293145) | [V2-56__연결됨__1440__345-293145.png](frames/V2-56__연결됨__1440__345-293145.png) |
| V2-56 접속 | Tailscale 안 보임 | 390 | [345:293530](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-293530) | [V2-56__Tailscale_안_보임__390__345-293530.png](frames/V2-56__Tailscale_안_보임__390__345-293530.png) |
| V2-56 접속 | 연결됨 | 390 | [345:293450](https://www.figma.com/design/ygAxFnxi4jeiw4vMxS1Xbm/quant.jsyoo.dev?node-id=345-293450) | [V2-56__연결됨__390__345-293450.png](frames/V2-56__연결됨__390__345-293450.png) |
<!-- frames:end -->
