# 3단계 명세 — 토스 실주문(실전)

모드 화면에서 모의투자를 실전으로 바꿀 수 있게 한다. 엔진의 단계(매도 → 환전 → 매수)가 실전 장부에서는 유준상의 토스증권 계좌로 실제 주문을 낸다. 이 문서는 운영 노트의 규칙(안전·3.10·품질)을 그대로 따른다.

- 유준상(2026-10-12): "모드를 바꾸는 방법이 없다." → 토스 실주문 연결을 "지금 만든다"(D44). 고칠 때마다 "파생되는 새로운 문제들까지 고려"한다(3절).
- 돈이 움직이는 일이라 빠르기보다 맞고 안전한 것이 먼저다.

## 근거
- 토스증권 Open API 공식 문서 1.2.24(2026-10-12 받음, 인증 없이 공개 문서만 받았다. 토스 API는 부르지 않았다)
  - 개요 `https://openapi.tossinvest.com/openapi-docs/overview.md`
  - FAQ `https://openapi.tossinvest.com/openapi-docs/faq.md`
  - OpenAPI JSON `https://openapi.tossinvest.com/openapi-docs/latest/openapi.json` (정본)
  - 안내 `https://developers.tossinvest.com/llms.txt`
- 옛 클라이언트 `src/quant/broker/toss.py`·`src/quant/broker/__init__.py`와 루트 운영 노트 §9.5·§11 '자동매매'(옛 시스템이 서버에서 겪은 것)
- Vault `001_projects/quant-dashboard/7-웹기획/인계.md` 규칙 5·6·7·13·14·15, `기획.md` SCR-MODE, `예시-값표.md` §1.6·§2

## 1. 토스 Open API에서 확인한 것

### 1.1 환전
- **환전 API는 없다.** 엔드포인트 목록(개요 '기능 목록', OpenAPI paths 42개)에 환전·외화 매수가 없다. 있는 것은 환율 조회(`GET /api/v1/exchange-rate`)뿐이고, 이 값은 "참고용 표시 환율. 실제 주문 시 적용되는 거래 환율과 다를 수 있습니다"(1분 갱신, `rate` 살 때 환율·`midRate` 매매기준율·`basisPoint`).
- **자동 환전도 없다.** FAQ '주문': "미국 주식을 살 때 달러가 부족하면 자동으로 환전되나요? — 환전되지 않습니다. Open API 주문은 자동환전을 지원하지 않으므로 달러 주문 가능 금액이 부족하면 `422 insufficient-buying-power` 로 거부됩니다."
- 결론: 원화 → 달러는 유준상이 토스 앱에서 한다. 엔진은 금액을 정확히 알려 주고, 바뀐 잔고로 환전을 알아본다(2.4).

### 1.2 주문 종류와 시간
- `POST /api/v1/orders`: `orderType` LIMIT(지정가)·MARKET(시장가), `timeInForce` DAY(기본, 정규장 끝까지 미체결분 자동 취소)·CLS(미국 지정가만, LOC)·OPG(국내만, 시가단일가 사전접수).
- 국내 가격은 호가 단위에 맞아야 한다(틀리면 400, `data.tickSize`·`nearestPrices`). 미국은 $1 이상 소수 둘째, 미만 넷째 자리(그 아래는 버림).
- 1억 원 이상 주문은 `confirmHighValueOrder: true`가 없으면 400 `confirm-high-value-required`. 최대 주문 금액을 넘으면 422 `max-order-amount-exceeded`.
- 주문 가능 시간은 매매 시스템 그대로다(FAQ). 밖이면 422 `order-hours-closed`, `data.retryAfterAt`(언제 다시).
- 장 운영 시간(`GET /api/v1/market-calendar/KR|US`, 모두 KST, 휴장이면 KR `integrated` null, US 네 세션 null): 국내 통합(KRX+NXT) 프리 08:00~09:00(단일가 08:50~), 정규 09:00~15:30(종가 단일가 15:20~), 애프터 15:30~20:00. 미국(서머타임 예) 데이마켓 09:00~16:50, 프리 17:00~22:30, 정규 22:30~05:00, 애프터 05:00~07:00.
- Open API 주문은 통합(SOR)만 된다. 계좌의 거래소 설정이 SOR가 아니면 422 `investor-exchange-not-integrated`.
- 국내만: 같은 종목에 반대 방향 미체결 주문이 있으면 409 `opposite-pending-order-exists`.
- 짧은 시간에 소액 주문을 수백 건 내면 어뷰징으로 매매가 제한될 수 있다(FAQ).

### 1.3 소수점
- 소수점 수량은 미국 시장가 매도에만(6자리까지). 소수점 매수는 금액 주문(`orderAmount`, 미국 시장가만). 둘 다 정규장 시작부터 끝나기 1시간 전까지만. 국내는 정수만.
- 엔진은 정수 주만 쓴다(ops notes). 앱에서 산 소수점 주식이 규칙 종목에 섞이면 대조가 맞지 않아 직접 할 일이 된다(2.5).

### 1.4 체결·수수료·세금 보고
- 체결은 주문 단위로 합쳐서 온다(`GET /api/v1/orders/{orderId}`의 `execution`): `filledQuantity`, `averageFilledPrice`, `filledAmount`, `commission`, `tax`, `filledAt`(마지막 체결), `settlementDate`(결제 예정일). FAQ: "주문 1건이 1행입니다. 여러 번 나누어 체결된 주문은 평균 체결가·총 체결 수량으로 합산". 건별 체결은 웹소켓 `personal:order`에만 있다.
- 상태: PENDING · PENDING_CANCEL · PENDING_REPLACE · PARTIAL_FILLED · FILLED · CANCELED · REJECTED · CANCEL_REJECTED · REPLACE_REJECTED · REPLACED. 일부 체결 뒤 취소된 주문은 체결 수량을 가진 채 CLOSED에 남는다.
- 주문 목록(`GET /api/v1/orders?status=OPEN|CLOSED`)에는 앱·WTS 주문도 들어 있다(장전·장후 시간외 종가만 빠진다). CLOSED는 100건씩 커서로 넘긴다. **목록에는 `clientOrderId`가 없다**(생성 응답에만 있다).
- 수수료율은 `GET /api/v1/commissions`(시장별 `commissionRate`, `startDate`, `endDate`). 2026-09-28 서버에서 읽은 값: 국내 0.015%, 미국 0.10%(종료일 2026-09-29, 그 뒤 값은 모름, 문서 예시는 0.25%).

### 1.5 현금·입출금·미결제
- **예수금·출금 가능 금액·입출금 내역 API는 없다.** 현금은 `GET /api/v1/buying-power?currency=KRW|USD`의 `cashBuyingPower`(미수 없이 현금으로 살 수 있는 금액) 하나다. 보유(`GET /api/v1/holdings`)에는 현금이 없다.
- 그래서 입금·출금·배당·이자·앱에서 한 환전은 **어떤 체결로도 설명되지 않는 매수 가능 금액의 변화**로만 보인다.
- 앱에서 판 주문은 주문 목록에 `settlementDate`와 함께 나온다. 인계 규칙 5의 '결제일 + 2영업일'을 이 날짜로 센다.

### 1.6 토큰과 '연결 만료'
- `POST /oauth2/token`(client credentials, form 본문) → `expires_in` 86400(24시간), refresh token 없음. **클라이언트당 유효한 토큰은 1개**: 새로 받으면 앞의 토큰이 바로 무효(401 `token-revoked`). FAQ: 프로세스마다 따로 받으면 서로를 무효화한다.
- 허용 IP(WTS 설정 > Open API > 허용 IP 관리)에 없는 곳에서 부르면 토큰은 403 `access_denied`("IP address not allowed"), API는 403 `ip-not-allowed`.
- **'90일마다 갱신'은 문서에 없다.** 디자인의 토스 연결 만료(10/19·12일 남음, 주기 '90d')는 가정이었다. 문서에 있는 만료는 24시간 토큰뿐이고 엔진이 알아서 다시 받는다. client 키 자체의 만료일은 문서에도 API에도 없다 → WTS 화면에 보이면 유준상이 설정으로 넣는다(`AUTOTRADE_TOSS_KEY_EXPIRES`), 없으면 만료 줄을 그리지 않는다.

### 1.7 멱등
- `clientOrderId`(36자 이하, 영숫자·`-`·`_`): 같은 값·같은 내용으로 **10분 안에** 다시 보내면 새 주문 없이 처음 결과를 돌려준다. 처리 중이면 409 `request-in-progress`, 내용이 다르면 422 `idempotency-key-conflict`. **10분이 지나면 같은 값도 새 주문이다.**

### 1.8 오류 코드(개요 '에러 응답'에서 엔진이 쓰는 것)
- 다시 해도 되는 것: 401 `expired-token`·`invalid-token`(토큰 다시 받기), 401 `token-revoked`, 429 `rate-limit-exceeded`(`Retry-After`), 500 `internal-error`·`maintenance`, 409 `request-in-progress`, 422 `order-hours-closed`.
- 브로커가 거부한 것(다시 내지 않고 직접 할 일, 인계 11): 400 `invalid-request`·`confirm-high-value-required`, 422 `insufficient-buying-power`·`stock-restricted`·`price-out-of-range`·`order-type-not-allowed`·`prerequisite-required`·`market-not-supported-for-stock`·`investor-exchange-not-integrated`·`insufficient-sellable-quantity`·`order-limit-exceeded`·`max-order-amount-exceeded`·`account-restricted`·`idempotency-key-conflict`, 409 `opposite-pending-order-exists`.
- 연결이 막힌 것(사람이 서버·WTS에서 고친다): 403 `ip-not-allowed`·`access_denied`, 401 `invalid_client`, 404 `account-not-found`.
- 오류 본문은 `{"error": {"requestId", "code", "message", "data"}}`, 토큰은 OAuth2 평평한 모양 `{"error": "...", "error_description": "..."}`(옛 클라이언트가 이 차이로 IP 거부를 4일 못 읽었다).

### 1.9 호출 한도
- 클라이언트 × API 그룹 단위(초당): ORDER 10, ORDER_HISTORY 5, ORDER_INFO 6(09:00~09:10 KST 3), ASSET 5, ACCOUNT 1, MARKET_DATA 15, MARKET_INFO 3, STOCK 5, AUTH 5. 429면 `Retry-After`.

### 1.10 실제 호출 없이는 알 수 없는 것(서버 확인 단계, 5절)
1. 이 계좌에서 069500(KODEX 200)과 SPYM이 거래되는지: `stocks`의 상장 상태·정리매매·거래정지(읽기로 확인 가능). SPYM 매수에 사전 요건(`prerequisite-required`)이 걸리는지는 **첫 실주문**에서만 안다.
2. 달러 `cashBuyingPower`가 순수 달러인지(앱의 '원화 주문'이 섞이는지): 앱의 달러 예수금과 맞춰 본다.
3. 판 돈이 바로 매수 가능 금액에 들어오는지, 미체결 매수가 매수 가능 금액을 얼마나 묶는지.
4. 지금 미국 수수료율(9/29 뒤).
5. client 키 만료일(WTS 화면), 서버 IP가 허용 목록에 있는지.

## 2. 설계

### 2.1 두 열쇠와 프로세스 경계
- 웹 서비스는 샌드박스라(밖으로 못 나감, 비밀 파일 못 읽음) **토스를 부를 수 없다.** 토스를 부르는 것은 cron의 tick 하나다. 웹은 tick이 DB에 남긴 기록(토스 연결 상태 `broker_status`, 계좌 사진 `broker_snapshots`, 주문 기록 `broker_orders`)만 읽는다.
- 주문은 **두 열쇠가 모두 있을 때만** 나간다(ops notes 안전).
  1. tick의 cron 줄에 `AUTOTRADE_LIVE_ORDERS=1`
  2. DB의 모드 '실전'(웹에서 PIN과 확인으로 켬)
- `AUTOTRADE_LIVE_ORDERS=1`이 없으면 tick은 **토스를 아예 부르지 않는다**(읽기도 안 함). 옛 quant가 같은 client로 토큰을 쓰고 있어서, 새 엔진이 토큰을 받는 순간 서로를 무효화하기 때문이다(1.6). 열쇠 1을 넣는 것이 '토스에 연결해도 된다'는 뜻이고, 열쇠 2 없이는 주문이 0건이다.
- 보낼 때마다 두 열쇠를 다시 본다: 주문 기록을 쓰는 같은 거래 안에서 모드를 읽고, 프로세스 환경을 읽는다(`broker/toss.py` `LivePermit`). 테스트와 노트북에는 열쇠 1이 없다(`tests/autotrade/conftest.py`).
- 비밀: tick만 `AUTOTRADE_SECRETS_ENV` 파일에서 `TOSS_CLIENT_ID`·`TOSS_CLIENT_SECRET`·`TOSS_ACCOUNT_NO`를 한 줄씩 읽는다(`config.read_env_key`). 토큰은 `data/autotrade-toss/token.json`(폴더 0700, 파일 0600, 원자적 쓰기, git 제외, 웹 서비스에서는 InaccessiblePaths).

### 2.2 토스 클라이언트(`broker/toss_api.py`)
- 옛 `src/quant/broker/toss.py`에서 옮겼고(D14, 머리 주석에 출처), 새 테스트로 다시 검증한다. 바꾼 것:
  - 전송을 주입한다(표준 라이브러리 urllib 기본, 테스트는 가짜 토스). 새 의존성 없음.
  - 토큰은 form 본문(문서 그대로). 만료 10분 전에만 새로 받는다. `token-revoked`면 파일을 다시 읽어 다른 토큰이 있으면 그것을 쓰고, 없을 때만 새로 받는다. 무효화를 센다(`revoked`) → 다른 프로세스가 같은 client를 쓰면 작동 화면에 보인다.
  - 계좌는 `TOSS_ACCOUNT_NO`와 번호가 같은 BROKERAGE 계좌(옛 코드는 첫 번째). 하나뿐이면 그것.
  - 그룹별 토큰 버킷(ORDER_INFO는 하루 종일 3/초), 429는 `Retry-After`(최대 5초) 뒤 한 번.
  - 금액은 모두 Decimal 문자열 그대로.
  - 오류 메시지에 비밀값·토큰·헤더를 넣지 않는다.

### 2.3 주문 보내기와 체결 받기(`broker/toss.py`, `jobs/live_tasks.py`)
- 네트워크는 거래 밖에서, 장부는 거래 안에서(기존 잡과 같은 원칙). tick의 실전 차례:
  1. **토스 동기화**(네트워크): 우리 주문 상태 읽기 → 끊긴 전송 정리 → 취소 요청 처리 → 때가 된 주문 보내기 → 계좌 사진.
  2. **단계 실행**(거래 하나): 기존 단계 실행기가 `TossExecutor`로 `broker_orders` 기록만 읽어 체결·실패를 장부에 적는다. 실행기 안에서는 토스를 부르지 않는다.
- 보내기 한 건:
  1. 지금 가격(토스 현재가), 매수면 매수 가능 금액(그 통화), 매도면 판매 가능 수량을 읽는다.
  2. 지정가: 매수 = 현재가 × 1.005를 호가 단위로 올림, 매도 = × 0.995를 내림(`live_limit_slippage`, 기본 0.5%). 체결은 시장 가격이고 이 값은 상한이다.
  3. 수량: 매수 = min(계획, ⌊매수 가능 금액 ÷ (지정가 × (1 + 수수료율))⌋)(낮게 틀리는 쪽, 옛 §11), 매도 = min(계획, 장부 보유, 판매 가능 수량). 0이면 보내지 않고 기록('not-sent', 다음 날 다시).
  4. 1억 원 이상(원화로 어림)이면 보내지 않고 직접 할 일(`live_max_order_krw`). 엔진은 `confirmHighValueOrder`를 켜지 않는다.
  5. **보내기 전에 의도를 먼저 커밋**한다(`state='sending'`, `clientOrderId`, 요청 내용, 시각). 그 거래 안에서 두 열쇠를 다시 본다.
  6. 보낸다. 결과를 커밋한다(성공 'sent', 거부 'rejected', 시간 밖 'not-sent'+`retryAfterAt`, 응답 없음·5xx·409 처리 중 'unknown').
- `clientOrderId` = `at-` + sha256(엔진의 idempotency key) 앞 32자: 같은 주문은 언제나 같은 값. 다시 시도(attempt 2)는 key가 달라 값도 다르다.
- 끊긴 전송('sending'·'unknown'): 처음 보낸 지 **9분 안**이면 같은 값·같은 내용으로 다시 보낸다(토스가 처음 주문을 돌려줌). 9분이 지났으면 다시 보내지 않고 그 종목의 그날 주문 목록(OPEN·CLOSED)에서 방향·수량·가격·주문 시각이 맞고 아직 우리 기록에 없는 주문을 찾는다: 하나면 그것으로 잇고, 없으면 '안 보냄'(새로 보내도 됨), 둘 이상이면 'unknown'으로 두고 직접 할 일.
- 체결: 'sent'인 주문은 tick마다 `GET /orders/{id}` 하나로 읽는다(보낸 직후 한 번 더). 기록하는 값은 브로커가 준 것: 수량 `filledQuantity`, 금액 `filledAmount`, 수수료 = `commission` + `tax`, 시각 `filledAt`, 평균가 = 금액 ÷ 수량. 장부의 `TradeFill`은 이제 총액을 직접 받는다(평균가 × 수량의 반올림 차이로 현금이 어긋나지 않게).
- 결과 → 실행기의 결과:
  - FILLED → 체결.
  - 일부 체결 뒤 끝남(취소·만료) → **체결된 만큼만 체결**로 적고 나머지는 버린다. 다음 확인이 띠를 보고 다시 계획한다(모의 체결의 '살 수 있는 만큼'과 같은 결과).
  - 체결 0으로 끝남(DAY 만료·취소) → 실패(다음 날 같은 시각에 다시, 인계 11).
  - 거부(REJECTED 또는 4xx 업무 오류) → 실패 `broker-rejected` → 다시 내지 않고 직접 할 일 `order-rejected`.
  - `order-hours-closed` → `retryAfterAt`이 그 장 안이면 그때 다시 보내고, 아니면 실패(다음 날).
  - 'sending'·'unknown'·'sent'(아직 열림) → 기다림. 브로커에서 끝났는지 모르는 주문은 실패로 치지 않는다(실패로 치면 다시 시도가 같은 주문을 또 낸다).
- 장이 끝났는데 열려 있는 주문(DAY인데 남음)은 취소를 요청한다.
- 장부에 적은 체결은 주문당 한 번(`fills.order_id` UNIQUE). 계획이 닫힌 뒤(실전 끄기, `resolve`) 들어온 체결도 버리지 않고 적는다(늦은 체결, 2.5).

### 2.4 환전(손으로, `fx` 단계)
- 실전 계획의 환전 단계는 **유준상이 토스 앱에서 하는 일**이다. 단계 시각(09:10)이 되면 작동 화면에 직접 할 일 `fx-manual`이 생긴다: 방향, 원화 금액, 달러 어림, 계획 환율, '이 시각까지'(그 돈을 쓸 매수 단계 시각).
- 미국 매수 단계는 환전 단계가 끝나야 돈다(기존 단계 의존). 그래서 **달러가 들어오기 전에는 미국 매수가 나가지 않는다.** 보낼 때도 매수 가능 달러로 수량을 자른다(2.3).
- 끝나는 것은 대조가 환전을 알아볼 때다(2.5): 원화 매수 가능 금액이 줄고 달러가 늘었는데 체결로 설명되지 않고, 그 비율이 그때 환율의 ±3% 안이면 환전이다. 기다리던 환전 주문에 그 금액(낸 원화 그대로, 받은 달러 그대로, 비율)을 **모의와 같은 fx 체결**로 적는다. 주문의 `executed_at`은 그 환전을 보여 준 계좌 사진의 시각이다 → 단계 끝 → 미국 매수가 다음 자리(22:30, 장중이면 5분 뒤)에 나간다. 덜 바꿨으면 산 만큼만, 더 바꿨으면 남는 달러는 다음에 쓴다.
- 실전의 계획은 이미 있는 달러를 먼저 쓴다(`PlanInput.net_free_cash`): 바꿔야 하는 금액만 환전으로 묻는다. 모의투자는 그대로다(예시 값표).
- 바꾸지 않을 거면 `python -m autotrade.jobs resolve fx-manual:<주문 id> --note …`: 환전 단계를 닫고, 있는 달러만큼만 산다.
- 달러 → 원화도 같다(미국 매도가 한국 매수를 대는 계획).

### 2.5 실전 장부의 진실은 브로커다(대조, `engine/live.py`)
- 실전 장부 = 규칙 종목의 보유 + 원화·달러 현금(매수 가능 금액). 규칙 밖 종목은 장부 밖이다('규칙 밖 n개 · 손익 제외', 계좌 사진에만).
- 대조는 tick마다(조용할 때) 하고, 08:30 확인은 **계획 전에 반드시** 한다. 계좌 사진이 15분보다 오래됐거나, 브로커에 열린 주문이 있거나(어느 채널이든), 우리 주문 중 아직 끝을 모르는 것이 있거나, 받은 체결을 아직 장부에 적지 않았으면 대조하지 않는다(확인은 실패 → 09:30 다시 → 직접 할 일).
- 사진의 잔고를 읽은 뒤에 끝난 체결이 목록에 있으면 그 사진은 쓰지 않는다(다음 tick).
- 순서:
  1. **늦은 체결**: 우리 주문의 체결 중 장부에 없는 것을 적는다.
  2. **우리 것이 아닌 체결**(앱·WTS, 실전 시작 뒤): 
     - 규칙 종목(장부에 있는 종목) 매수·매도 → 장부의 거래로 적는다(`external_fills`). **매도 대금은 출금 대기**(결제일 + 2영업일, 인계 5).
     - 규칙 밖 종목: 매수 = 그 돈이 장부를 떠남(출금 사건), 매도 = 들어옴(입금 사건) + 출금 대기.
     - 소수점 수량이 규칙 종목에 걸리면 적을 수 없다 → 맞지 않음.
  3. 남는 현금 차이(원화·달러):
     - 원화 −·달러 +(또는 반대)이고 비율이 환율 ±3% 안 → **환전**. 기다리던 환전 주문이 있으면 그 fx 체결(2.4). 없으면(주인이 계획 밖에서 바꿈) 'conversion' 표시가 붙은 출금(낸 통화)·입금(받은 통화) 사건 둘을 만든 환율로 적는다: 장부 손익은 fx 체결과 같고, 계좌별 보기는 계좌 사이의 이동으로 읽는다. fx 체결은 계획의 주문에 매달려야 해서, 계획 밖 환전에 가짜 계획을 만들면 그날 리밸런싱이 하나 더 보인다. 토스 API는 우리 주문을 위해 몰래 환전하지 않는다(1.1, 달러가 모자라면 422).
     - 남은 + → 받을 배당이 있으면(지급일 앞뒤, 실전 장부가 배당락 전에 들고 있던 주식) 그만큼 **배당**, 나머지는 **입금**.
     - 남은 − → **출금**(그 통화의 출금 대기부터 줄인다). 현금보다 많이 빠졌으면 맞지 않음.
  4. **보유 대조**: 규칙 종목의 수량이 브로커와 다르면 '맞지 않음'.
- '맞지 않음'은 장부를 고치지 않는다. 작동 화면 빨간 직접 할 일 `broker-mismatch`(종목·장부·브로커 수량, 현금 차이), 확인은 실패(주문 0건). 원인을 앱에서 고치면 다음 대조가 저절로 풀고, 브로커가 맞으면(분할, 시간외 종가 매매, 입고) 서버에서 `python -m autotrade.jobs adopt-broker --note …`로 장부를 브로커에 맞춘다(차이는 입·출금으로 적는다).
- 입금·출금·배당은 기존 사건(`deposit`·`withdrawal`·`dividend`, `payload.source='broker'`)이다: 금액은 양수, 통화는 그 돈의 통화(달러 입금은 USD, 원화 값은 `amount_krw`·`krw_rate`), `occurred_at`은 가장 잘 아는 도착 시각(앱 체결이면 그 체결 시각, 아니면 그 돈을 처음 보여 준 계좌 사진의 시각). 장부를 사건과 체결에서 다시 계산하면 원 단위까지 같다(`rebuild`가 `external_fills`와 시작 사진도 접는다).
- 실전 체결 주문의 `executed_at`은 브로커가 준 체결 시각이다(모의는 단계 실행기가 적은 시각 그대로). 계좌별 보기(`api/views/accounts.py`)가 이 시각으로 돈의 이동을 센다.
- 모의투자 장부는 실계좌 입출금을 따라 받지 않는다(인계 6).

### 2.6 실전 시작·켜기·끄기
- **켜기**(`POST /api/mode/live`, 웹): 세션 → 확인 체크 → PIN(틀린 수는 PIN 바꾸기와 같은 잠금, 한 세션 5회면 끊음) → 켜기 전 점검 → 미리보기를 다시 계산해 받은 hash와 비교(합계가 1% 이상 다르거나 주문이 다르면 409 `preview-changed`와 새 미리보기) → 한 거래에서: 모드 '실전', `live-on` 사건, (처음이면) 실전 장부 시작.
- **실전 장부 시작 = 켜는 순간 미리보기에 보인 계좌**: 그 계좌 사진의 원화·달러 매수 가능 금액과 규칙 종목(069500·SPYM) 보유. 원가는 그때 가격(사진의 현재가)으로 두어 시작 손익이 0이다. 시작 금액 = 그 합(원화, `start` 사건의 통화는 KRW). 달러나 미국 종목이 있으면 사건이 통화별 몫(`by_currency`: 원화 몫, 달러 몫)을 함께 가져서 계좌별 보기에서 미국 계좌가 제 달러로 시작한다. 규칙 밖 종목은 손대지 않고 '규칙 밖'으로만 보인다. **넣고 싶은 돈만큼 계좌에 두면 된다.** 계좌에 있는 원화·달러는 모두 규칙의 돈이 된다(빼 둘 돈은 켜기 전에 출금).
- 규칙 몫은 실전 지수 반반 100 · 3년 발굴 0(설정 `AUTOTRADE_LIVE_SHARES`, 표가 진실).
- 첫 주문은 다음 평일 08:30 확인이 그날 자료로 다시 계획한다(미리보기는 어림).
- 다시 켜면 같은 실전 장부를 이어 간다(인계 15). 꺼진 동안의 입출금·앱 매매는 tick의 대조가 그때그때(열쇠 1이 있으면) 또는 다시 켤 때 적는다. 평가(16:00)는 꺼진 동안에도 돈다.
- **끄기**(`POST /api/mode/paper`, 세션만, PIN 잠김 중에도): 한 거래에서 모드 '모의투자', `live-off` 사건, 실전의 열린 계획을 닫고 아직 안 보낸 주문은 취소. 이미 브로커에 있는 열린 주문은 '취소 요청'으로 두고 **다음 tick(5분 안)이 취소한다**(웹은 토스를 못 부른다). 응답의 `cancelPending`이 그 주문들이다. 취소가 실패하면 `cancelFailed`(헤더 '취소 안 됨 n', 배너, 작동 화면 할 일)이고 tick은 끝날 때까지 다시 시도한다. 모드가 실전이 아닌데 열린 우리 주문은 무엇이든 취소한다(켜고 끄는 사이에 나간 주문까지).
- 모의투자는 실전 중에도 그대로 돈다(D33).

### 2.7 화면
- `GET /api/mode`: `preflight` 네 줄을 tick의 기록에서 만든다.
  - 작동: 모의투자 장부의 작동 화면 요약과 같은 판정.
  - 토스 연결: 열쇠 1, 토큰·계좌·잔고 읽기, 규칙 종목 거래 가능, 마지막 성공 15분 안, 다른 프로세스의 토큰 무효화 없음, 대조 맞음. facts는 `{checkedAt, account?}` 또는 `{cause}`(+ 키 만료를 알면 `expiresAt`·`daysLeft`).
  - 자료 최신: 잔고(계좌 사진), 현재가(종가), 환율.
  - 알림 받을 기기: 웹 푸시는 아직 없어 0대 경고(켜기를 막지 않음).
- `preview`: 계좌 사진 + 최근 종가 + 환율로 `plan_rule`을 돌린 첫 주문(단계·시각·어림 금액), 지금 막대, 목표, 규칙 밖 종목. hash와 합계를 저장해 켤 때 비교한다.
- `canTurnOn`: 지난 실전 주문의 취소가 안 끝남 → `cancel-pending`(그 열린 주문이 계좌를 바쁘게 해서 점검도 함께 ✕), 점검 ✕ → `checks`, 미리보기 없음 → `preview`.
- `live`·`liveOff`(기간 칩), `cancelFailed`, `cancelPending`, `offPreview`. `twoLedgers`는 아직 null(열린 것).
- 헤더·작동 화면: 토스 연결·토스 잔고 대조 줄(주기 '확인마다': 토스 연결은 마지막으로 본 시각과 계좌 끝 4자리, 막히면 원인), 할 일 `order-rejected`·`cancel-failed`·`fx-manual`·`broker-mismatch`·`toss-link`(연결이 막힘, 원인과 할 일 두 줄)·`toss-expiring`(키 만료를 알 때). 실전 장부의 할 일은 모드와 상관없이 보인다(끈 뒤 취소 실패). 잔고가 맞지 않으면 `broker-mismatch` 카드 하나만(연결 카드는 같은 원인을 다시 말하지 않는다).
- 웹(`web/`): 모드 화면의 토스 연결 점검 줄이 원인과 할 일(또는 계좌 끝 4자리·마지막 확인)을, '취소 요청한 주문' 카드가 다음 확인이 취소할 주문을 보인다. 계약 바뀐 것은 `CONTRACT.md` '바뀐 것' 2026-10-13.

### 2.8 tick
- 한 프로세스가 모의투자 → 실전 순서로 돈다(cron 줄 그대로). 실전 차례: 토스 동기화 → 단계 → 대조 → 확인·다시 → 평가. 배당 받기(Yahoo)는 모의투자만(실전 배당은 대조가 브로커 현금으로 적는다). 백업은 마지막에 한 번.
- 할 일이 없으면 로그를 쓰지 않는다(토스 동기화가 아무것도 바꾸지 않은 tick, 기다리기만 한 실전 단계).

### 2.9 저장(스키마 6)
- `broker_status`(한 줄: tick이 본 토스 연결), `broker_snapshots`(계좌 사진), `broker_orders`(우리 주문의 브로커 쪽: clientOrderId·주문 id·상태·체결·취소), `external_fills`(우리 것이 아닌 체결·환전), `live_previews`(켜기 미리보기 hash).

## 3. 파생 문제와 처리
| 고친 것 | 새로 생길 수 있는 문제 | 처리 |
|---|---|---|
| 새 엔진이 토스 토큰을 받는다 | 옛 quant(keeper·cycle, 아직 cron에 있음)와 서로 토큰을 무효화 | 열쇠 1 전에는 토스를 부르지 않음. 켜기 전 할 일: 옛 quant의 토스 cron 줄을 뺀다(4절). `token-revoked`를 세어 토스 연결 ✕ |
| 같은 계좌를 옛 quant가 매매할 수 있다 | 대조가 앱 매매로 보고 출금 대기를 만든다 | 옛 quant 줄 제거가 켜기 전 조건. 우리 것 아닌 체결은 기록에 남는다 |
| 보내다 프로세스가 죽음 | 다음 tick이 같은 주문을 또 냄 | 의도를 먼저 커밋, 9분 안 같은 clientOrderId, 9분 뒤엔 목록에서 찾기 |
| 응답 없음·5xx | 실패로 치고 다음 날 다시 내면 두 번 | 끝을 모르는 주문은 실패로 치지 않음('unknown' → 다시 확인) |
| 일부 체결 | 나머지를 다시 내면 가격이 바뀐 뒤 과매수·과매도 | 체결분만 적고 나머지는 다음 확인이 다시 계획 |
| 실전 끄기 | 웹은 취소를 못 함 | 취소 요청 → 다음 tick. 모드가 실전이 아닌데 열린 우리 주문은 모두 취소 |
| 끄는 사이에 체결 | 체결이 버려지고 장부가 브로커와 어긋남 | 늦은 체결을 대조 첫 단계에서 적음 |
| 대조가 입출금을 만든다 | 배당·이자·앱 환전이 입금으로 잡힘 | 환전(반대 부호·환율 ±3%), 배당(받을 배당) 먼저 가린다 |
| 미체결 매수가 매수 가능 금액을 묶음 | 대조가 출금으로 오해 | 열린 주문이 있으면 대조하지 않음 |
| 잔고와 목록을 다른 시각에 읽음 | 그 사이 체결이 출금·입금으로 보임 | 잔고 뒤 체결이 있으면 그 사진 버림 |
| 수동 환전 | 미국 매수가 달러 없이 나감 | 환전 단계가 끝나야 미국 매수, 보낼 때 달러로 수량 자름 |
| 지정가 상한 | 현금이 빠듯하면 1주 덜 삼 | 남은 현금은 다음 확인이 '1주 미만'·새 현금으로 봄 |
| 1억 원 이상 | 토스가 거부 | 보내기 전에 직접 할 일 |
| 켜는 순간과 계좌 사진 사이 입금 | 시작 금액이 다름 | 시작은 미리보기의 사진, 그 뒤 차이는 다음 대조가 입금으로 |
| 실전 장부가 브로커와 다름 | 틀린 장부로 매매 | 맞지 않으면 주문 0건, 직접 할 일, `adopt-broker` |
| 토스 연결 90일 만료 표시 | 가짜 숫자 | 만료를 모르면 그리지 않음(계약 바꿈) |
| 계좌별 보기(10/12, 한국 ₩ · 미국 $) | 실전의 환전·입금·달러 시작이 한쪽 계좌의 이익, 다른 쪽의 손실로 보임 | 환전은 fx 체결, 입출금은 그 통화의 사건, 시작·adopt는 `by_currency`. 테스트가 한국 + 미국 × 환율 + 환율 효과 = 장부 손익과 계좌마다 '값 − 들어온 돈'을 확인 |
| 계획 밖 환전 | fx 체결은 계획의 주문이 있어야 해서 가짜 계획이 리밸런싱으로 보임 | 'conversion' 출금·입금 둘(만든 환율), 계좌별 보기는 이동으로 |
| 달러 입금 사건 | '손대지 않았을 때'가 달러 금액을 원으로 읽어 틀어짐 | 원화 값(`amount_krw`)으로 읽고, 'conversion' 사건은 건너뜀 |
| 끄고 곧바로 다시 켜기 | 지난 실전 주문이 새 시작 뒤에 체결되어 섞임 | 취소가 끝날 때까지 `cancel-pending`이 켜기를 막음(점검보다 먼저) |
| 잔고 불일치를 두 카드가 말함 | 같은 원인이 할 일 둘로 셈 | 불일치는 `broker-mismatch` 하나, 연결 카드는 빼고 |
| 웹 서비스 | 공개 프로세스에 토스 키 | 단위가 `TOSS_*`를 지우고 토큰 폴더를 가림, 웹은 기록만 읽음 |

## 4. 실전 전에 유준상이 할 일
1. **넣을 돈을 정한다.** 켜는 순간 토스 종합매매 계좌의 원화·달러·규칙 종목이 모두 실전 장부가 된다. 넣고 싶은 만큼만 두고, 넣지 않을 돈은 먼저 출금한다. 규칙 밖 종목은 그대로 둔다(팔지 않음).
2. **옛 quant의 토스 사용을 멈춘다**(서버 crontab에서 `quant.keeper`·`quant.cycle_job` 줄 삭제, 백업 후). 같은 client의 토큰을 서로 무효화하고, 같은 계좌에 주문을 낼 수 있다.
3. WTS 설정 > Open API: 서버 IP(146.56.118.65)가 허용 목록에 있는지, 키 만료일이 보이는지(있으면 알려 주면 `AUTOTRADE_TOSS_KEY_EXPIRES`로 넣는다). 계좌의 거래소 설정이 통합(SOR)인지.
4. 서버 확인 단계(5절)를 허락한다(읽기만).
5. tick 줄에 열쇠 1을 넣는다(crontab, AI 줄의 `AUTOTRADE_AI_CALLS=1`과 같은 방식):
   ```
   */5 * * * * cd /home/ubuntu/portfolio-dashboard && AUTOTRADE_LIVE_ORDERS=1 AUTOTRADE_SECRETS_ENV=/home/ubuntu/dotclaude/secrets/.env flock -n data/autotrade.db-cron.lock timeout 10m .venv/bin/python -m autotrade.jobs tick >> data/logs/autotrade-jobs.log 2>&1
   ```
   이것만으로는 주문이 나가지 않는다(모드가 모의투자). 5분 안에 모드 화면의 '토스 연결'이 ✓가 된다.
6. 모드 화면에서 미리보기를 보고 체크 + PIN → 실전 켜기.
7. 첫 환전: 08:30 확인 뒤 09:10에 작동 화면에 '환전' 할 일이 뜨면 토스 앱에서 그 원화 금액을 달러로 바꾼다(그날 22:30 전).
8. 갱신한 `deploy/autotrade.service`를 설치한다(토스 키 이름을 지우고 토큰 폴더를 가림, 방어용). 설치 명령은 파일 머리 주석에 있다.
- 되돌리기: 모드 화면 '실전 끄기'(세션만, 열린 주문은 5분 안에 취소). 토스를 아예 멈추려면 tick 줄에서 `AUTOTRADE_LIVE_ORDERS=1`을 지운다(다음 tick부터 토스를 부르지 않는다).

## 5. 서버 확인 단계(읽기만, 유준상 허락 뒤)
```
cd ~/portfolio-dashboard
AUTOTRADE_SECRETS_ENV=/home/ubuntu/dotclaude/secrets/.env .venv/bin/python -m autotrade.jobs toss-check
```
- 주문·취소를 부르지 않는다(코드에 그 경로가 없다). 토큰을 하나 받으므로 옛 quant의 토큰이 무효가 된다(옛 quant가 다음 호출에서 다시 받는다). 옛 quant를 멈춘 뒤에 하면 깔끔하다.
- 앞선 조건: 이 커밋이 배포되어 DB가 스키마 6이다(`migrate`). 규칙 종목을 DB에서 읽는다. 열쇠 1(`AUTOTRADE_LIVE_ORDERS`)은 필요 없다.
- JSON 한 줄. 기대하는 출력(키 순서 그대로):
  - `"job": "toss-check"`, `"result": "ok"`, `"token": "ok"`
  - `"account": {"seq": <정수>, "tail": "<TOSS_ACCOUNT_NO 끝 4자리>", "type": "BROKERAGE"}`
  - `"cash": {"KRW": "<원>", "USD": "<달러>"}` — 앱의 원화·달러 주문 가능 금액과 같아야 한다(1.10-2)
  - `"holdings": [{"id": "KR:…", "name": "…", "qty": "…"}, …]`(앱의 보유와 같음), `"openOrders": 0`(옛 quant의 열린 주문이 있으면 그 수)
  - `"commissions": {"KR": "0.00015", "US": "…"}`(1.10-4)
  - `"instruments": {"KR:069500": {"name": "KODEX 200", "market": "…", "status": "ACTIVE", "securityType": "ETF", "currency": "KRW", "tradable": true, "price": "…"}, "US:SPYM": {… "currency": "USD", "tradable": true …}}` — `tradable`이 false거나 `{"found": false}`면 그 종목으로는 켤 수 없다(1.10-1)
  - `"calendar": {"KR": {…}, "US": {…}}`(오늘 세션), `"fx": {"rate": "…", "midRate": "…"}`
  - `"tokenRevoked": n`이 있으면 그 사이 다른 프로그램(옛 quant)이 같은 키로 토큰을 받았다.
- 실패하면 `"result": "failed"`, `"cause"`와 `"error"`: `ip`(403 `ip-not-allowed`·`access_denied`: WTS 허용 IP), `auth`(401 `invalid_client`: 키), `account`(404 `account-not-found` 또는 번호가 맞는 BROKERAGE 계좌 없음), `no-key`(파일에 키 없음), `unreachable`·`maintenance`·`error`. 비밀값·토큰은 출력하지 않는다.
- 1.10-1의 사전 요건과 1.10-3은 첫 실주문에서만 안다: 첫날 작동 화면을 같이 본다.

## 6. 열린 것
- 모드 화면 두 장부 그래프(`twoLedgers`)와 차이 분해는 아직 null이다.
- 계획 밖 환전은 입금·출금 사건 둘이라 전체 자산 그래프에 입금·출금 표식으로 보인다(계좌별 보기는 이동으로 읽는다). 표식을 '환전'으로 따로 그리려면 화면 계약이 바뀐다.
- 앱에서 한 규칙 종목 매매(`external_fills`)의 수수료는 계좌별 변동 분해에서 '수수료'가 아니라 '시장'에 들어간다(합은 맞다).
- 늦게 적힌 돈: 대조가 바쁜(열린 주문) 동안 들어온 입금은 조용해진 뒤 처음 보인 시각으로 적힌다. 그 사이의 평가 점은 그 돈 없이 남는다.
- 웹 푸시(알림)는 범위 밖이다.
- 한국 09:05 주문 시각: LP 호가 의무가 시가 뒤 5분부터라(연구 기록) 09:05는 그 끝이다. 시각은 바꾸지 않았다.
- 미국 개장 직후 주문: 지정가 상한(0.5%)을 넘게 열리면 기다리다 장 끝에 만료 → 다음 날 다시.
