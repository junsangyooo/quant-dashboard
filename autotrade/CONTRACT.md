# API 계약 — autotrade ↔ web

엔진(`autotrade/api`)과 화면(`web/src/api/types.ts`)이 같이 지키는 약속이다. 바꿀 때는 이 문서를 먼저 고치고, 맨 아래 '바뀐 것'에 한 줄을 남긴다.

## 원칙
- **서버는 숫자·날짜·enum을 준다. 문구는 화면이 만든다**(`web/src/copy.ts`). 서버 응답에는 사람이 읽는 문장을 넣지 않는다. 예외는 데이터 자체가 이름인 경우뿐이다: 종목·규칙 이름(과 이니셜), 회사가 쓰는 부문·항목 이름(`MetricRef.param`), 규칙 정의가 가진 흐름 카드 글(`FlowDisplay` 노드의 title·subtitle·fields). 단위·낱말·판정 이름은 보내지 않는다.
- **표시 반올림은 서버가 맞춰서 준다.** 명세에 '합이 맞아야 한다'는 완료 조건이 많아서다. 예: 묶음 % = 행 %의 합, 월 변동의 합 = 손익.
  - `krw`: 원 단위 정수
  - `usd`: 센트까지 소수 2자리 숫자
  - `rate`: 환율, 소수 1자리(1382.4)
  - `pct1`: 비중 %, 소수 1자리(40.7)
  - `pp1`: %p, 소수 1자리이고 부호 있음(−0.2 → `-0.2`)
  - `ret2`: 수익률 %, 소수 2자리(2.44)
- **시각은 ISO 8601이고 시간대를 붙인다**(KST는 `+09:00`). 종가 기준일은 `YYYY-MM-DD`와 시장(`KR`/`US`)으로 준다. 미국 종가는 화면이 '(ET)'를 붙인다.
- **장부는 `paper`(모의투자)와 `live`(실전) 둘이다.** 읽기 API는 `?ledger=`를 받는다. 없으면 지금 모드의 장부다. 다른 장부를 열면 화면은 '장부 칩'을 보인다(SCR-HISTORY.paper-ledger).
- 모든 `/api/*`는 세션 쿠키가 필요하다(`/api/auth/*`·`/api/healthz` 제외). 인가 실패는 403 JSON이다. 401은 쓰지 않는다(브라우저 인증 창과 충돌).
- 오류 응답: `{"error": "<code>", "detail"?: {...}}`. 404도 JSON이다. 코드는 '오류 코드' 표에 있다.

## 공통 타입
```ts
type Ledger = 'paper' | 'live'
type Market = 'KR' | 'US' | 'COIN'
type Currency = 'KRW' | 'USD'
type Side = 'buy' | 'sell' | 'fx'

interface Instrument {
  id: string            // 'KR:069500', 'US:SPYM'
  name: string          // 'KOSPI200 ETF', 'S&P 500 ETF'
  kind: 'etf' | 'stock' | 'coin'
  market: Market
  currency: Currency
  initials: string      // 로고 자리 이니셜(Figma 기준): 지수 ETF는 지정값(069500 'K2', SPYM 'SP'), 한글 이름은 첫 글자('삼'), 로마자로 시작하는 한국 종목 이름은 앞 로마자 두 글자까지('HD'·'SK'), 코인은 티커 첫 글자('B'), 그 밖은 티커 앞 두 글자('NV'). 현금 행은 화면이 ₩·$를 그린다
  outsideToss?: boolean // 토스 밖 계좌(코인)
}

interface RuleRef {
  id: string            // 'index_half', 'discovery_3y'
  name: string          // '지수 반반', '3년 발굴'
  ai: boolean           // 'AI 판단 포함' / 'AI 없음'
  colorIndex: number    // 규칙 색(구성 막대·벗어남 선): 0, 1, 2…
  example?: boolean     // 이름 앞 '[예시]'
}

// 상태 칩 일곱 가지(SCR-PLAN 완료 조건). AI 규칙은 같은 칩에 다른 낱말을 쓴다(화면-맞춤.md ②, 'hold' = '유지').
type RuleStatus =
  | 'in-range' | 'scheduled' | 'in-progress' | 'partial-failed'
  | 'holiday' | 'quote-wait' | 'withdraw-wait'
  | 'hold' | 'sell-scheduled' | 'buy-scheduled'   // AI 규칙 전용

interface Basis {                 // '기준' 칩과 시트
  valuedAt: string                // 평가 시각(16:00)
  krClose: string | null          // 한국 종가 기준일
  usClose: string | null          // 미국 종가 기준일(ET)
  fxRate: number | null           // rate
  fxAt: string | null
  coinAt?: string | null
}

interface Order {
  id: string
  market: Market                  // 환전(fx)은 'KR'(원화 계좌에서 09:10에 한다)
  side: Side
  instrument?: Instrument         // fx면 없음
  qty?: number                    // 주(코인은 소수)
  price?: number                  // 체결가 또는 예상가(종목 통화)
  approx?: boolean                // '약 $124.80'
  amountKrw?: number
  amountUsd?: number
  fee?: { krw?: number; usd?: number }
  fx?: { krw: number; usd: number; rate: number }   // 환전
  direction?: 'krw-usd' | 'usd-krw'                 // 환전의 방향('원 → 달러')
  at: string                      // 체결 시각 또는 예정 시각. 실패한 주문은 실패한 시각
  status: 'filled' | 'pending' | 'failed'
  fill?: 'paper' | 'live'         // '모의 체결' / '실제 체결'
  failure?: { reason: 'no-quote' | 'broker-rejected' | 'cancel-failed' | 'other'; retryAt?: string; manual?: boolean }
  retried?: { at: string; status: 'filled' | 'failed' }
  // 다시 낸 결과('9/15 다시 · 체결'). 실패한 주문은 실패한 날의 기록으로 status 'failed'·failure를 그대로 두고,
  // 다시 낸 주문의 결과가 나오면 retried를 붙인다. retried.status가 'filled'면 더 기다릴 것이 없다(다시 시도 예정 항목도 없다)
}

interface Stage {
  kind: 'sell' | 'fx' | 'buy'     // 매도 → 환전 → 매수. 주문 0건 단계는 보내지 않는다(화면이 숨김).
  status: 'done' | 'pending' | 'failed'
  at: string                      // 대표 시각(09:05 / 09:10 / 22:30)
  orders: Order[]
}

type NextAction =
  | { kind: 'order'; at: string; market: Market; side: Side; instrumentName: string; qty: number }   // '오늘 22:30 미국 매수 2주'
  | { kind: 'first-check'; at: string }                    // '첫 확인 7/1(수) 08:30 · 목표대로 매수'
  | { kind: 'first-order'; at: string; market: Market; side: Side; count: number }  // '오늘 09:05 첫 주문 · 한국 매수 2건'
  | { kind: 'retry'; at: string; market: Market; side: Side }
  | { kind: 'todo'; market: Market; side: Side }           // '직접 할 일 · 토스 앱에서 주문 확인'
  | { kind: 'withdraw-wait'; until: string }               // '10/12까지 · 리밸런싱 쉼'
  | { kind: 'holiday'; markets: Market[]; nextCheckAt: string }
  | { kind: 'quote-wait'; market: Market | 'FX'; basisDate: string }   // 'FX' = 환율이 낡음
  | { kind: 'next-check'; at: string; reviewAt?: string }   // AI 규칙: '다음 확인 10/8 08:30 · 점검 11/1'(다음 월 점검, 1일 08:30)

type RebalanceCause = 'band' | 'new-cash' | 'withdraw-expired'
// 지수 반반이 계획을 세운 까닭: band = 비중이 띠를 벗어남('2.3%p 벗어남'), new-cash = 새 현금(시작·입금·배당)을
// 산다('새 현금 투자', 벗어남은 띠 안일 수 있다), withdraw-expired = 출금 대기로 묶였던 현금이 기한이 지나 풀려서 산다(인계 14)

type EventKind =
  | 'start' | 'rebalance' | 'partial-failed' | 'in-progress' | 'check-failed'
  | 'dividend' | 'deposit' | 'withdrawal' | 'live-on' | 'live-off'
  | 'discovery' | 'ai-buy' | 'ai-sell' | 'ai-check' | 'monthly-review'   // AI 규칙(2단계)

type CalendarState =
  | 'normal' | 'rebalance' | 'in-progress' | 'partial-failed' | 'failed'
  | 'no-run' | 'holiday-one' | 'holiday-both' | 'quote-wait' | 'future' | 'before-record'
```

## 읽기

### `GET /api/shell` — 모든 화면의 헤더(60초마다 다시 읽음)
```ts
interface ShellResponse {
  now: string
  mode: Ledger
  modeChangedAt: string | null      // 화면이 기억한 모드와 다르면 '다른 기기에서 바뀜' 칩 + 스켈레톤
  liveSince: string | null
  status:
    | { kind: 'ok'; lastCheckAt: string }
    | { kind: 'before-first'; firstCheckAt: string }
    | { kind: 'check'; count: number }          // 원인 단위로 센다
    // AI 규칙의 자료(공시 DART·EDGAR 하나씩, AI 호출)는 마지막 성공 뒤로 그 시장의 거래일이 하루를 넘게 지나야
    // 원인으로 센다(밤사이 DART 점검으로 헤더가 바뀌지 않게). 작동 화면은 첫 실패부터 보인다. 한 번도 성공하지 못한
    // 자료는 첫 시도(감시 작업·첫 AI 호출)부터 센다
    | { kind: 'check-failed'; at: string }
    | { kind: 'todo'; count: number }
    | { kind: 'cancel-failed'; count: number }
    // '확인 불가'·'연결 안 됨'은 이 응답을 못 받았을 때 화면이 정한다
  banner: Banner | null              // 한 번에 하나, 서버가 우선순위를 정함
}
type Banner =
  | { kind: 'stale'; market: Market | 'FX'; basisDate: string; tradingDays: number; link: 'health' }
  | { kind: 'partial-retry'; date: string; market: Market; side: Side; retryAt: string; link: 'plan' }
  | { kind: 'partial-todo'; date: string; market: Market; side: Side; reason: 'broker-rejected' | 'retry-failed'; link: 'health' }   // retry-failed = 다시 시도까지 실패(모의투자는 이것뿐)
  | { kind: 'check-failed'; at: string; retryAt: string | null; link: 'health' }
  | { kind: 'cancel-failed'; market: Market; side: Side; link: 'mode' }
  | { kind: 'push-undelivered'; days: number; link: 'account' }
```

### `GET /api/home?ledger=&period=` — SCR-HOME
```ts
interface HomeResponse {
  ledger: Ledger
  example: boolean                   // '예시' 칩(고정 자료만 true)
  startDate: string                  // '[장부] 자산 · 7/1부터'
  basis: Basis
  stale: Array<'hero' | 'plan' | 'composition'>    // 섹션마다 '낡음' 태그 1개
  total: number                      // krw
  pnl: { amount: number; pct: number | null } | null   // null이면 '손익 · 첫 체결 뒤'. pct null이면 % 숨김(분모 0 이하)
  baseline: { pct: number } | null   // '손대지 않았을 때'
  planChip: { ruleId: string; status: RuleStatus; next: NextAction }
  trend: Trend
  planCard: PlanCard                 // 첫 확인 전에도 준다(바늘·단계 없음)
  composition: Composition
  accounts: HomeAccounts | null      // 계좌별 보기('전체 · 한국 ₩ · 미국 $'). pnl이 null이면(첫 체결 전) null
}

// 계좌는 통화로 가른다: 한국 계좌 = 원화 종목(원화 가격) + 원화 현금, 미국 계좌 = 달러 종목(달러 가격) + 달러 현금.
// 계좌에 들어온 돈(그 통화): 시작 금액·입금(+)·출금(−)은 그 통화의 계좌(지금은 모두 원화라 한국 계좌), 환전은 두 계좌
// 사이를 옮기는 돈이다(원→달러: 한국 계좌에서 낸 원만큼 빠지고 미국 계좌에 산 달러만큼 들어옴). 환전은 손익이 아니다.
// 배당(세후)·수수료·세금은 들어온 돈이 아니라 그 통화 계좌의 손익이다. 환전은 장부가 받아들인 때(주문 실행 시각)부터 센다.
// 계좌 손익 = 계좌 값 − 들어온 돈(그 통화), pct = 손익 ÷ 들어온 돈(0 이하면 null).
interface HomeAccounts {
  list: HomeAccount[]                // 한국 계좌('kr'), 미국 계좌('us') 순. 둘 다 늘 있다
  split: { kr: number; us: number; fx: number }
  // krw. 전체 손익 = kr + us + fx(원 단위까지 정확히, HomeResponse.pnl.amount).
  // kr = 한국 계좌 손익. us = 미국 계좌 손익(달러) × basis.fxRate를 원 단위 반올림.
  // fx = '환율 효과' = 나머지: 환전으로 산 달러가 지금 환율로 얼마인지 − 그 달러에 낸 원(+ 달러 행의 원 단위 반올림)
}
interface HomeAccount {
  id: 'kr' | 'us'
  currency: Currency                 // kr 'KRW' · us 'USD'
  total: number                      // 그 통화(krw 정수 · usd 센트)
  pnl: { amount: number; pct: number | null } | null   // 그 통화. null = 돈이 들어온 적 없는 빈 계좌(화면은 빈 상태)
  stale: boolean                     // 그 계좌 시세가 낡음(한국은 kr-quotes, 미국은 us-quotes. 환율은 달러 값에 들어가지 않는다)
  trend: Trend
  // 그 통화. ret = (값 − 그날까지 들어온 돈) ÷ 들어온 돈. 선은 돈이 처음 들어온 스냅숏부터다.
  // series[].netIn(계좌만): 그날까지 들어온 돈('원금', 그 통화). 환전 날 값과 같이 움직여서 둘의 차가 그 계좌 손익이다.
  // 30거래일 규칙은 그 계좌 기록(점 수)으로 정한다: 짧으면 periods null·period 'all'. 길면 요청한 period.
  // baseline·baselineRet는 늘 null: '손대지 않았을 때'는 전체만이다(규칙이 두 계좌 사이로 돈을 옮겨서, 한 계좌만 견주면
  // 차이가 대부분 옮긴 돈이 된다). events: 시작·실전 켬/끔은 두 계좌 모두, 리밸런싱(일부 실패·진행 중 포함)은 그 계획의
  // 주문이 닿은 계좌(거래는 그 통화, 환전은 둘 다), 입출금·배당은 그 통화 계좌만.
  // empty: 'first-day'(점이 하나 이하, 돈은 들어옴) | null
  composition: Composition
  // 그 계좌의 행. pct = 계좌 대비(합 100.0), 묶음 target은 null(목표는 장부 전체의 것).
  // 미국 계좌는 모든 행에 usd(금액)를 싣고 krw는 원화 환산이다. pnlPct·avgCost는 그 통화(달러 손익률에는 환율이 없다)
}

interface Trend {
  periods: Array<'1m' | '3m' | '1y' | 'all'> | null   // 기록 30거래일 미만이면 null(기간 칩 숨김)
  period: '1m' | '3m' | '1y' | 'all'
  periodPnl: { amount: number; pct: number } | null    // '전체'거나 기록이 짧으면 null
  series: Array<{ date: string; value: number; ret: number; baseline: number | null; baselineRet: number | null }>
  events: Array<{ date: string; kind: EventKind; kinds: EventKind[]; count?: number }>
  // 하루에 표식 하나. kind는 그날 첫 사건, kinds는 그날 사건 전부(순서대로), 둘 이상이면 count(묶음 표식).
  // check-failed는 넣지 않는다(홈 표식 범례에 없다). 기록 화면의 사건 목록에는 그대로 있다('✕ 확인 실패')
  empty: null | 'before-first-check' | 'before-first-fill' | 'first-day'
}

interface PlanCard {
  rule: RuleRef
  share: { pct: number; target: number | null }      // '자산의 81.1% · 목표 80%'
  status: RuleStatus
  next: NextAction
  gauge: Gauge
  stages: Stage[] | null             // 진행 중일 때만(첫 확인 전에는 null)
  nextCheckAt: string
  others: { count: number; status: RuleStatus | 'before-first' } | null
  // '외 n개 규칙 · [상태]'. 2단계: 3년 발굴의 몫이 0보다 크면 { count: 1, status: AI 규칙 상태 }, 첫 확인 전이면 'before-first'('첫 확인 전')
}
// HomeResponse.planCard는 첫 확인 전에도 있다: 규칙 이름·목표를 보이고, 게이지 바늘(needle)과 단계는 비운다.

type Gauge =
  | { kind: 'drift'; threshold: number; needle: null | {      // null = 바늘 숨김(시세 대기·첫 확인 전)
      instrument: Instrument; deviation: number; toThreshold: number } }   // pp1
  | { kind: 'sell-condition'; needle: null | {                // AI 규칙(D34)
      instrument: Instrument; progress: number; metric: MetricRef; margin: Margin } }

interface MetricRef {               // 지표 사전(autotrade/domain/metrics.py)의 키와 회사가 쓰는 말. 이름은 화면이 짓는다
  key: 'revenue' | 'operating_income' | 'net_income' | 'op_margin' | 'eps' | 'fcf' | 'ebitda_margin'
     | 'net_debt_to_ebitda' | 'backlog' | 'new_orders' | 'book_to_bill' | 'monthly_revenue_yoy'
     | 'segment_revenue' | 'segment_operating_income' | 'segment_op_margin' | 'segment_backlog' | 'guidance'
  param?: string                    // segment_*·guidance만: 회사의 부문·항목 이름('지상방산' → '지상방산 수주잔고')
}
interface Margin {                  // 선까지 남은 것. 화면이 단위에 맞춰 쓴다('2.3%p', '3.1조', '$350M', '0.12x', '2분기', '2.1%')
  unit: 'pp' | 'pct' | 'KRW' | 'USD' | 'x' | 'count' | 'quarter' | 'month' | 'year'
  value: number                     // pp는 pp1, pct는 소수 1자리, KRW는 원, USD는 달러, 기간은 남은 수
}

interface Composition {
  groupBy: Array<'instrument' | 'kind' | 'country' | 'currency' | 'rule'>   // 묶음이 2개 이상 생기는 기준만
  groups: Array<{
    key: string
    rule?: RuleRef                    // '● 지수 반반'
    label?: 'cash'                    // '현금'
    pct: number                       // pct1 = 행 %의 합
    target: number | null
    rows: CompRow[]
  }>
  pendingBar: { withdraw?: { krw: number; until: string } } | null   // 빗금 칸
  outsideRules: { count: number; krw: number } | null               // '규칙 밖 [n]개 [금액] · 손익 제외'
}
interface CompRow {
  kind: 'holding' | 'cash'
  instrument?: Instrument
  cash?: { currency: Currency; country: 'KR' | 'US' }   // 묶어 보기 '나라': 원화 현금은 한국, 달러 현금은 미국
  pct: number                         // pct1, 전체 자산 대비
  krw: number
  usd?: number
  pnlPct?: number                     // ret 1자리
  qty?: number
  avgCost?: { amount: number; currency: Currency }
  chip?:
    | { kind: 'buy-wait'; instrumentName: string; qty: number }   // '매수 대기 · S&P 500 ETF 2주'
    | { kind: 'sub-share' }                                        // '1주 미만 대기'
    | { kind: 'withdraw-wait'; until: string }
    | { kind: 'first-buy' }                                        // '첫 확인 때 매수'
    | { kind: 'buy-from'; at: string }                             // '09:05부터 매수'
}
```

### `GET /api/home/breakdown?ledger=&period=&account=` — 변동 분해 시트
```ts
interface Breakdown { from: string; to: string; start: number; deposit: number; withdrawal: number; market: number; dividend: number; fees: number; end: number
  currency?: Currency                // account가 있을 때만: 그 계좌 통화. 없으면 원화(전체)
  transfer?: number                  // account가 있을 때만: 환전으로 들어오고(+) 나간(−) 돈, 그 통화
}
// krw. 부호 있음: withdrawal·fees는 0 이하. deposit + withdrawal + market + dividend + fees = end - start(market이 반올림 나머지를 받는다).
// 'all'(기록 30거래일 미만이면 항상 'all')은 from = 시작일, start = 시작 금액이다. 시작 금액은 deposit에 넣지 않는다.
// account('kr' | 'us'): 그 계좌의 변동을 그 통화로(달러는 센트). deposit + withdrawal + transfer + market + dividend + fees
// = end − start. 'all'의 start는 한국 계좌가 시작 금액, 미국 계좌가 0. 30거래일 규칙은 그 계좌 기록으로 센다(HomeAccount.trend).
// market은 그 계좌 시세 변동(환율은 없다)이고 나머지를 받는다
```

### `GET /api/plan?ledger=&drift=` — SCR-PLAN
```ts
interface PlanResponse {
  ledger: Ledger
  example: boolean
  ruleShares: Array<{ rule: RuleRef; pct: number }> | null   // 0이 아닌 규칙이 2개 이상일 때
  rules: RuleCard[]
  schedule: {
    now: { ruleId: string; status: RuleStatus; stages: Stage[] } | null
    items: ScheduleItem[]
  }
  drift: {
    periods: Array<'3m' | '1y' | 'all'> | null        // 30거래일 미만이면 null('[시작일]부터')
    period: '3m' | '1y' | 'all'
    since: string
    lines: Array<{ ruleId: string; points: Array<{ date: string; value: number | null }> }>   // pp1, null = 시세 대기 구간
    staleFrom: string | null                           // '10/05부터 시세 대기'
    events: Array<{ date: string; kind: EventKind; ruleId: string | null }>
    // 규칙의 리밸런싱은 그 규칙 선 위에(ruleId), 시작·실전 켬·끔은 장부 전체의 사건이라 ruleId null. AI 규칙은 선이 없어 여기 없다
    empty: null | 'second-day'
  }
}
interface RuleCard {
  rule: RuleRef
  share: { pct: number; target: number | null }
  status: RuleStatus
  next: NextAction
  gauge: Gauge
  rows: Array<{
    instrument: Instrument
    weight: number | null            // pct1, null = '—'(시세 대기)
    target: number                   // pct1
    toThreshold: number | null       // pp1
    // AI 규칙(sell-condition 게이지): 팔 조건까지
    progress?: number; metric?: MetricRef; margin?: Margin
  }>
  basisLine: {
    pendingBuyIncluded: boolean      // '매수 대기 달러 포함'
    fxRate: number | null; fxAt: string | null
    withdrawExcluded: boolean        // '출금 대기 현금 제외'
    staleMarket: Market | null; staleBasisDate: string | null   // '미국 시세 10/02 기준이라 계산 안 함'
    metricTableAt?: string | null    // AI 규칙: '지표 표 10/8'(지표 표가 마지막으로 바뀐 날, YYYY-MM-DD)
  }
  vsIndex?: { since: string; points: Array<{ date: string; value: number | null }> } | null
  // AI 규칙: '지수 대비 · [since]부터'(pp1). 종목마다 고른 날부터 같은 시장 지수 대비 초과 수익의 평균(채점과 같은 계산, 판 종목은 판 날에 고정)
}
type ScheduleItem =                  // ruleId는 한 규칙의 항목에만 있다. 확인·휴장·현금 항목은 장부 전체의 것이다
  | { kind: 'next-check'; at: string }
  | { kind: 'holiday'; date: string; markets: Market[] }
  | { kind: 'retry'; at: string; market: Market; side: Side; ruleId: string }   // 다시 낼 주문의 규칙
  | { kind: 'sub-share-cash'; krw: number }
  | { kind: 'withdraw-wait'; krw: number; until: string }
  | { kind: 'new-cash'; krw: number }
  | { kind: 'first-check'; at: string }
  | { kind: 'monthly-review'; at: string; ruleId: string }      // AI 규칙: 매달 1일 08:30(점검은 전날 22:00부터 돌아 그 확인 전에 끝난다)
  | { kind: 'discovery'; at: string; ruleId: string }           // AI 규칙: 4·6·9·12월 1일 08:30
  | { kind: 'earnings'; date: string; instrument: Instrument; ruleId: string }   // AI 규칙. 실적 발표일 자료원이 없어 아직 보내지 않는다
```

### `GET /api/history?ledger=&year=` — SCR-HISTORY
```ts
interface HistoryResponse {
  ledger: Ledger
  example: boolean
  year: number
  years: number[]
  trend: { since: string; basis: Basis; total: number; pnl: { amount: number; pct: number | null } | null;
           series: Array<{ date: string; value: number }>; events: Array<{ date: string; kind: EventKind }> }
  tiles: {
    rebalances: { count: number; partialFailed: number; inProgress: number }
    fees: { krw: number }             // '세금 미포함'
    checks: { count: number; failed: number }
  }
  calendar: Array<{ date: string; state: CalendarState }>   // 평일만
  filters: {
    total: number
    rules: Array<{ rule: RuleRef; count: number }>   // 규칙의 리밸런싱 + 그 규칙 종목의 배당. AI 규칙은 그 규칙의 계획 + AI 판단 사건
    kinds: Array<{ kind: 'rebalance' | 'deposit' | 'withdrawal' | 'dividend' | 'failed' | 'ai'; count: number }>   // 'ai'는 AI 규칙이 있을 때만
  }
  months: Array<{ month: string; change: number; events: HistoryEvent[] }>   // 최신순, 월 변동의 합 = 손익
  offPeriods: Array<{ from: string; to: string }>
}
interface HistoryEvent {
  date: string
  kind: EventKind
  rule?: RuleRef                      // 리밸런싱, 그리고 규칙 종목의 배당('지수 반반 (KOSPI200 ETF)'). AI 판단 사건은 AI 규칙
  stagesMini?: Array<'done' | 'pending' | 'failed'>   // 리밸런싱, 그리고 시작(첫 매수). fill·fees도 같다
  weightsMini?: { before: number[]; after: number[]; target: number[] }   // target = 목표 눈금(pct1). AI 규칙은 빈 배열
  pending?: { side: Side; at: string }   // 리밸런싱 중: 기다리는 단계와 그 시각('매수 22:30')
  fill?: 'paper' | 'live'
  deviation?: number                  // '2.3%p 벗어남'
  cause?: RebalanceCause              // 지수 반반의 리밸런싱 사건만(AI 규칙의 계획은 없음)
  fees?: number
  amount?: number                     // 시작·입출금·배당(krw. 달러 배당은 받은 날 환율로 원화)
  instrument?: Instrument             // 배당
  retry?: { date: string; filled: boolean }   // '9/15 다시 · 체결'
  failureReason?: 'no-quote' | 'broker-rejected' | 'other'
  recoveredOn?: string                // 확인 실패 → '9/10 정상'
  resolvedOn?: string                 // 직접 할 일을 처리했다고 닫은 날(일부 실패·확인 실패) → '10/9 직접 처리'
  treatment?: 'pnl-excluded' | 'income' | 'invest-next-check' | 'withdraw-wait'
  dayChange: number | null
  dayTotal: number
}
```

### `GET /api/day/{date}?ledger=` — SCR-DAY
```ts
interface DayResponse {
  date: string
  ledger: Ledger
  example: boolean
  prev: string | null; next: string | null      // 이전·다음 사건 날짜
  total: number; change: { amount: number; pct: number } | null
  events: DayEvent[]
  check: {
    at: string | null                             // null = 주말·확인 없음
    result: 'rebalance' | 'in-range' | 'partial-failed' | 'failed' | 'holiday' | 'quote-wait' | 'weekend'
          | 'in-progress' | 'withdraw-wait' | 'no-run'   // no-run = 평일인데 확인 기록이 없음(기록 전·작업 안 돎)
    holidayMarkets?: Market[]
    band: { threshold: number; before: number | null; after: number | null } | null   // pp1
    ruleId?: string; rule?: RuleRef                 // 확인한 규칙(이름은 rule)
    instrument?: Instrument; weight?: number; toThreshold?: number; over?: number
    failure?: { reason: 'no-quote' | 'other'; recoveredOn?: string }   // result 'failed': 코드와 날짜('시세 응답 없음 · 9/10 정상')
    cause?: RebalanceCause                          // 그날 확인이 계획을 세웠으면 그 까닭
  }
  basis: Basis   // total과 같은 값의 기준: 그날 16:00 평가. 평가가 없는 날(주말·놓친 날)은 그 전 마지막 평가, 오늘 16:00 전은 지금 값
}
type DayEvent =
  | { kind: 'rebalance' | 'partial-failed' | 'in-progress'; rule: RuleRef; stagesMini: Array<'done' | 'pending' | 'failed'>;
      weights: { instruments: Instrument[]; before: number[]; after: number[]; target: number[]; threshold: number };
      stages: Stage[]; feesKrw: number }
  | { kind: 'deposit' | 'withdrawal' | 'dividend' | 'start'; krw: number; treatment: 'pnl-excluded' | 'income' | 'invest-next-check' | 'withdraw-wait'; until?: string; instrument?: Instrument;
      stages?: Stage[]; feesKrw?: number }   // start는 첫 매수의 단계·수수료를 같이 싣는다
  | { kind: 'live-on' | 'live-off'; at: string }
  | { kind: 'ai-check' | 'ai-sell' | 'ai-buy' | 'monthly-review' | 'discovery'; rule: RuleRef; judgment: AiJudgment }   // 2단계
interface AiJudgment {
  at: string; trigger: 'shock' | 'filing' | 'condition' | 'monthly' | 'discovery' | 'buy-price'
  instrument?: Instrument            // 판단한 종목(바꾸기는 살 종목)
  model: 'haiku' | 'sonnet' | 'opus'; tokens: number
  verdict: 'hold' | 'weaken' | 'invalidated' | 'buy' | 'skip'
  votes?: Array<'hold' | 'weaken' | 'invalidated' | 'buy' | 'skip' | 'switch' | 'keep'>   // 두 번 묻는 판단의 두 답(팔기 확인, 사기 확인, 바꾸기)
  action: 'none' | 'sell' | 'buy' | 'switch'
  input: JudgmentItem[]              // '입력' 줄: 화면이 항목마다 말을 짓고 순서대로 ' · '로 잇는다
  output: JudgmentItem[]             // '출력' 줄. verdict·votes·action은 위 칸에 있어 되풀이하지 않는다(비면 줄을 숨긴다)
}
type JudgmentItem =
  | { key: 'instrument' | 'sold' | 'bought'; instrument: Instrument }   // 판단한 종목 · 바꾸기의 팔 종목 · 살 종목
  | { key: 'shock'; date: string; value: number }    // 급락한 날, 그날 지수 대비 수익률(%, 소수 1자리)
  | { key: 'condition'; value: number }              // 걸린 반증 조건 번호(1부터)
  | { key: 'filing'; date: string }                  // 걸린 공시의 접수일
  | { key: 'review'; value: 'weaken' | 'invalidated'; months?: number }   // 월 점검이 넘긴 판정(약화면 몇 달째)
  | { key: 'month'; value: string }                  // 'YYYY-MM'
  | { key: 'cost'; value: number }                   // 바꾸기 비용(바꾸는 금액 대비 %, 소수 2자리)
  | { key: 'filings' | 'news' | 'picks' | 'held' | 'candidates' | 'checks' | 'hold' | 'weaken' | 'invalidated'
        | 'rewritten' | 'new-picks' | 'expired'; value: number }   // 수
  | { key: 'slot-full' }                             // 사기 확인: 자리가 없어 바꾸기 확인으로 넘김
// 2단계 구현: 사건 하나에 판단 하나. 문장은 보내지 않는다(모델이 쓴 근거와 찾은 뉴스는 기록에만 남는다).
// - 팔기 확인(ai-sell: 두 번 다 '반증', action 'sell' / ai-check: 그대로): input = instrument, 계기(shock·condition·filing·review),
//   filings(꾸러미에 넣은 최근 공시 수). output = news(급락이라 웹을 켰을 때 찾은 뉴스 수), 웹이 꺼져 있으면 빈 줄
// - 사기 확인(ai-buy 'buy' / ai-check 'skip', 두 번 다 '근거 있음'이어야 산다): input = instrument, checks(충족한 살 조건 수)
//   또는 month(분기 발굴이 새로 고른 종목, trigger 'discovery'), filings(꾸러미의 최근 공시 수). votes = 'buy' | 'skip' 두 번.
//   output = slot-full(자리 없음)이거나 빈 줄
// - 바꾸기(ai-buy 'switch' / ai-check): input = sold, bought, cost. votes = 'switch' | 'keep' 두 번
// - monthly-review(그달 점검 전체, verdict는 가장 나쁜 판정): input = month, picks. output = hold·weaken·invalidated 수,
//   rewritten(새로 쓰거나 바꾼 팔 조건 수)
// - discovery(분기 발굴): input = month, held(발굴 전 보유 수), candidates(발굴 전 후보 수). output = new-picks(사기 확인으로 보낸 새 종목 수),
//   candidates(새 후보 수), expired. action은 늘 'none'이다: 새 종목은 사기 확인 두 번을 거쳐서만 산다
// trigger는 일감에서 온다(지난 실적 공시를 처음 읽는 'backfill'은 'filing'). tokens는 그 판단의 호출들을 더한 값이다
```

### `GET /api/rules` · `GET /api/rules/{id}?lane=` — SCR-RULES
```ts
interface RulesListResponse {
  rules: Array<{ rule: RuleRef; share: { pct: number; target: number | null }; status: RuleStatus; example: boolean }>   // example = 목록 머리의 '예시' 칩
}
interface RuleDetailResponse {
  rule: RuleRef
  share: { pct: number; target: number | null }
  status: RuleStatus
  example: boolean
  stale: Array<'kr-quotes' | 'us-quotes' | 'fx'>   // 마지막 확인 때 낡았던 자료(작동 화면의 출처 id). 비어 있으면 '낡음' 없음
  display: TilesDisplay | FlowDisplay
}
interface TilesDisplay {                       // 고정 규칙: 타일 6칸
  kind: 'tiles'
  what: { instruments: Instrument[]; weights: number[]; basis: 'krw' }
  when: { time: string; days: 'weekdays'; tz: 'KST' }
  condition: {
    threshold: number; targetEach: number[]
    deviation: { now: number | null; atCheck: number | null }
    // pp1. now = 지금 가장 큰 벗어남(빈 점, 시세 대기면 null), atCheck = 오늘 08:30 확인 때 값(주황 점, 오늘 확인이 없거나 보유가 없으면 null)
  }
  action: { stages: Array<'sell' | 'fx' | 'buy'> }
  measured: { median: number; worst: number; badYear: number; period: string; afterTax: boolean; source: string } | null   // 측정되지 않으면 null(그리지 않음)
  now: { status: RuleStatus; stages: Stage[] | null; nextCheckAt: string }
}
interface FlowDisplay {                        // AI 규칙: 흐름 카드(D34)
  kind: 'flow'
  lanes: Array<{ id: string; label: { kind: 'daily' | 'earnings' | 'monthly' | 'quarterly'; time?: string } }>
  lane: string                                 // 고른 흐름
  nodes: Array<{
    id: string
    type: 'start' | 'stock' | 'data' | 'ai' | 'weight' | 'condition' | 'action' | 'exception' | 'result'
    col: number; row: number                   // 3열 격자
    title: string; subtitle?: string           // 규칙 정의의 이름(데이터)
    fields?: Array<{ key: 'input' | 'ai' | 'output'; value: string }>
    more?: number                              // '외 N': 지금 칸이 보인 종목(최대 3) 밖의 수
    targets?: Array<{ instrument: Instrument; weight: number }>
    // 비중 카드의 종목별 목표(pct1). 목표가 모두 같은 비중이면 보내지 않고 지금 칸의 kv targetEach로 준다(3년 발굴)
    now: NowBlock
  }>
  edges: Array<{ from: string; to: string; label?: 'yes' | 'no-keep' | 'no' | 'no-wait'; style: 'taken' | 'not-taken' | 'exception' }>   // no-wait = '아니오 · 후보로 대기'(분기 발굴)
}
interface NowBlock {
  headKey: 'now' | 'now-check' | 'now-last-judgment' | 'now-month' | 'now-last'   // '지금', '지금 · 확인 08:30' …
  at?: string             // 머리의 시각·날짜. 시작 카드는 다음 실행 시각('다음 10/12 08:30'), 실적 흐름의 시작 카드는 마지막 실적 공시 날
  until?: string          // 'now-last'가 여러 날에 걸치면 끝 날('마지막 9/14~9/15', at = 첫날)
  // 머리 메모(자유 문장)는 없다. '8종목 중 상위 3', '15종목' 같은 말은 kv 행의 수로 주고 화면이 문장을 만든다
  rows: Array<
    | { kind: 'instrument'; instrument: Instrument; weight?: number; ret?: number; progress?: number; margin?: Margin; period?: string }
    // progress 0~100: 보유는 팔 조건까지(margin = 팔 조건까지 남은 것), 후보는 살 값까지(고른 날 가격 0 → 살 값 100,
    // margin { unit: 'pct' } = 살 값보다 몇 % 위). period = 실적 기간('2026Q3')
    | { kind: 'rank'; rank: number; instrument: Instrument; ret: number }
    | { kind: 'band'; value: number; threshold: number; instrument?: Instrument }
    | { kind: 'order'; side: Side; text: string; status?: 'filled' | 'pending' | 'failed'; at?: string; retried?: boolean }
    // text = 종목 이름, 환전이면 방향 코드('krw-usd' | 'usd-krw'). 한 번 실패하고 다시 낸 주문은 retried true이고
    // status·at이 다시 낸 결과다('9/15 다시 · 체결'). 주문(Order) 자체는 실패한 날의 기록으로 남는다
    | { kind: 'status'; status: RuleStatus; at?: string }
    | { kind: 'kv'; key: string; value: string; note?: string }   // 셋째 칸 note도 데이터(코드·수)다. 문장은 보내지 않는다
    | { kind: 'exceptions'; items: Array<'holiday' | 'quote-wait' | 'withdraw-wait'>; active: boolean }
  >
}
// AI 규칙(3년 발굴)의 kv 키. value와 note는 날짜(YYYY-MM-DD)·수·이름·코드이고, 값이 없으면 '-'다:
//   krClose·usClose(value 종가일, note 출처 상태 'fresh'…), filings(value 마지막 공시 회사, note 새 공시 수),
//   metricTable(value 지표 표 날짜, note 지표가 있는 회사 수), hits(조건에 걸린 수), verdict(value 판정, note 계기),
//   judgments·sells·buys(이번 달 판단·팔기·사기 수), votes(마지막 두 번 확인, 'hold,invalidated'), metrics(뽑은 지표 수),
//   tokens, companies(지표 표의 회사 수), picks(보유 수), newFilings(30일 새 공시 수), hold·weaken·invalidated(그달 판정 수),
//   daysToNext(다음 발굴까지 날 수), lastDiscovery(마지막 발굴 날), candidates(후보 대기 수, '후보 대기 · 6'), targetEach(종목당 목표 pct1)
```

### `GET /api/health` — SCR-HEALTH
```ts
interface HealthResponse {
  summary: {
    kind: 'ok' | 'check' | 'check-failed' | 'unknown' | 'before-first'
    // 'check' = 낡은 자료나 빨간 카드가 있음. 노란 카드만 있으면 'ok'('정상 · 할 일 1')
    sourcesTotal: number; staleCount: number; failCount: number
    todoCount: number                           // 직접 할 일 카드(action 'manual') 수: 노란 카드 전부와, 다시 시도가 끝나 사람을 기다리는 빨간 카드. 자동으로 다시 하는 카드는 세지 않는다
    lastCheckAt: string | null; nextCheckAt: string | null
    lastSuccessAt?: string; retryAt?: string; firstCheckAt?: string
  }
  todos: Array<{
    id: string
    severity: 'red' | 'yellow'
    kind: 'stale' | 'check-failed' | 'toss-expiring' | 'order-rejected' | 'order-failed' | 'cancel-failed' | 'push-undelivered' | 'ai-cli' | 'filings' | 'pin-failures'
        | 'toss-link' | 'broker-mismatch' | 'fx-manual'   // 3단계 실전 연결(autotrade/PHASE3.md 2.7)
    // order-failed = 다시 시도까지 실패한 주문. order-rejected는 실전 브로커 거절(3단계)
    facts: Record<string, string | number>      // 화면 문구에 끼울 값. 종류마다 키가 정해져 있다(아래). 모르는 값은 키를 빼고 null을 넣지 않는다
    action: { kind: 'auto-retry'; at: string } | { kind: 'manual' }
    effect: 'orders-zero-live-blocked' | 'orders-and-reconcile-stop' | 'no-order-sent' | 'other'
  }>
  sources: Array<{                              // 1단계는 kr-quotes·us-quotes·fx 셋만(없는 연결은 줄을 만들지 않는다)
    // 2단계: 3년 발굴의 몫이 0보다 크면 filings·ai-cli·metric-table을 더한다.
    //  filings: state는 DART·EDGAR 중 나쁜 쪽(점검 중이면 'maintenance', 응답 없음·키 없음·실패면 'stale'),
    //           basis는 마지막으로 둘이 받은 날, extra { dart, edgar }: 'ok' | 'maintenance' | 'stale' | 'failed' | 'no-key' | 'unknown'
    //  ai-cli: state는 마지막 호출의 성공 여부(실행기가 CLI를 못 찾으면 'stale'), basis는 마지막 성공 호출의 모델, cadence 'event',
    //          extra { monthTokens, budget, enabled(0·1, 실행기가 마지막에 본 AUTOTRADE_AI_CALLS), due(기다리는 일감 수),
    //                  cli('ok' | 'missing' | 'unknown'), lastRunAt?(실행기가 마지막으로 돈 시각), running?·runningSince?(지금 묻는 일감 종류와 시작 시각) }
    //          실행기는 따로 도는 cron 줄이라 웹 서비스의 환경으로는 알 수 없다: 실행기가 남긴 심장 박동(ai_runner)을 읽는다
    //  metric-table: basis는 마지막으로 뽑은 날, cadence 'event'
    //  summary.staleCount는 'maintenance'도 센다
    id: 'kr-quotes' | 'us-quotes' | 'fx' | 'toss-link' | 'toss-balance' | 'push-devices' | 'filings' | 'ai-cli' | 'metric-table'
    state: 'fresh' | 'late' | 'stale' | 'maintenance' | 'unknown'
    basis: string | null                        // 종가일·환율 값·만료일 …
    receivedAt: string | null
    cadence: 'daily' | 'per-check' | '90d' | 'event'
    age: number                                 // 주기 대비 나이(0~1 이상)
    extra?: Record<string, string | number>     // 기기 수, 남은 날 …, 시세는 { market: 'KR' | 'US' }
  }>
  recent14: Array<{ date: string; state: CalendarState; run?: { at: string; result: string; seconds: number; reason?: 'no-quote' | 'other' } }>   // 최근 14일 중 평일만(10칸). reason은 result 'failed'·'todo'일 때
  lastRun: { at: string; result: string; seconds: number; reason?: 'no-quote' | 'other' } | null   // reason은 코드다(문장 아님)
  devices: Array<{ name: string; lastDelivery: string | null; ok: boolean }>   // '알림 기기'를 펼친 목록(AccountResponse와 같은 모양). 3단계 전에는 빈 배열
}
// todos[].facts 키(값은 날짜·시각·수·코드):
//   stale: market('KR' | 'US' | 'FX'), basisDate, tradingDays, missingDates?(못 받은 거래일 'YYYY-MM-DD,YYYY-MM-DD', 환율은 없음)
//   check-failed: at, reason('no-quote' | 'other')
//   order-failed: date, market, side, reason
//   toss-expiring(3단계): expiresAt, daysLeft
//   ai-cli: 노랑 { reason: 'over-budget', tokens, budget }(한 달 토큰이 예산을 넘음, 멈추지는 않음)
//           빨강 { reason: 'task-failed', count, taskKind, since }(세 번 실패한 일감이 사람을 기다림, since = 그중 가장 오래된 일감이 생긴 시각)
//           빨강 { reason: 'cli-missing', since? }(AI 실행기가 Claude CLI를 찾지 못함: 일감은 시도로 세지 않고 기다림, since = 처음 못 찾은 시각)
//           노랑 { reason: 'call-running', taskKind, since }(호출 하나가 1시간 넘게 이어짐. 시간 상한은 없어서 멈추지 않음)
//           노랑 { reason: 'queue-waiting', count, since, cause }(일감이 2시간 넘게 차례를 못 받거나 3일 넘게 열려 있음, since = 가장 오래된 일감이 생긴 시각.
//                 cause 'off'(AUTOTRADE_AI_CALLS 꺼짐) | 'stopped'(실행기가 돌지 않음) | 'busy'(긴 호출이 실행기를 잡음) | 'cli-missing' | 'deferred'(출처·키·자료를 기다림))
//   filings: 빨강 { source: 'dart' | 'edgar', market: 'KR' | 'US', state, since? }(공시 감시가 멈춤, 다음 확인 때 다시. since = 마지막으로 받은 시각)
//            state 'no-key'는 AI 실행기에 DART 키가 없음(action 'manual': 서버 cron 줄을 고쳐야 함)
//   pin-failures: 빨강, 직접 할 일, 목록 맨 앞 { since, count, lastAt?, closed: 0 | 1 }('PIN 실패 급증': 24시간에 틀린 PIN
//           10회부터 서버의 unlock·set-pin까지. since = 생긴 시각, count = 그때부터 센 틀린 PIN 수, lastAt = 기록에 남은
//           마지막 틀린 PIN, closed 1 = 새 로그인이 닫힘(30회)). 헤더 status는 이것도 'todo' 수로 세고, '첫 확인 전'보다 앞선다
//   toss-link(3단계): { cause: TossLinkCause }. 실전이면 빨강, 아니면 노랑. 사람이 고칠 원인(env-off·no-key·auth·ip·account·
//           not-tradable·conflict·never·expired)은 직접 할 일, 나머지(unreachable·maintenance·error·old)는 다음 확인(5분 뒤) 자동.
//           effect 'orders-zero-live-blocked'. 실전이 아니고 켜려는 기미도 없으면(env-off·never) 카드를 만들지 않는다.
//           mismatch는 이 카드 대신 broker-mismatch가 말한다
//   broker-mismatch(3단계, 빨강·직접): { reason, instrument?(이름), ledgerQty?, brokerQty?, count?(다른 종목 수), currency? }
//           reason 'positions' | 'cash'(설명 안 되는 현금 변화, currency) | 'external-fill' | 'fractional' | 'sleeves' | 'other'.
//           id 'broker-mismatch:order:<id>'는 결과를 가를 수 없는 우리 주문 { reason: 'order-unknown', market, side }.
//           effect 'orders-zero-live-blocked'(대조가 맞을 때까지 실전 주문 0건)
//   fx-manual(3단계, 노랑·직접): { direction: 'krw-usd' | 'usd-krw', krw, usd, rate, orderId, by? }(토스 API는 환전을 못 한다:
//           주인이 토스 앱에서 바꾸면 다음 대조가 그 금액을 환전 주문의 체결로 적고 미국 매수가 이어진다. by = 기다리는 매수 시각)
//   cancel-failed(3단계 facts): { at(대기 시각), market, side }
// sources[].age(주기 대비 나이): 토스 연결(cadence '90d')은 지난 날 ÷ 90일(새로 연결한 날 0, 만료일에 1)
//   3단계 실제 연결은 cadence 'per-check'다(토스 API에 키 만료가 없다, PHASE3.md 1.6):
//   toss-link: state는 tick이 마지막으로 본 토스(fresh | 15분 넘게 못 봄 'late' | 원인이 있으면 'stale' | 아직 모르면 'unknown'),
//              주인이 알려 준 키 만료일(`AUTOTRADE_TOSS_KEY_EXPIRES`)이 14일 안이면 'late'. basis = 그 만료일(없으면 null),
//              receivedAt = 마지막 성공, age = 마지막 확인 뒤 ÷ 15분, extra { cause?: TossLinkCause, account?(끝 4자리), daysLeft? }
//   toss-balance: basis 'match' | 'mismatch' | null(대조 결과), receivedAt = 마지막 대조, age = ÷ 15분
// type TossLinkCause = 'never' | 'env-off'(주문 실행기에 AUTOTRADE_LIVE_ORDERS 없음) | 'no-key' | 'auth' | 'ip' | 'account'
//   | 'unreachable' | 'maintenance' | 'error' | 'old'(마지막 확인 15분 넘음) | 'conflict'(다른 프로그램이 같은 키로 토큰을 받음)
//   | 'not-tradable'(규칙 종목이 거래 안 됨) | 'mismatch'(잔고가 장부와 다름) | 'expired'(알려 준 키 만료일 지남)
```

### `GET /api/mode` — SCR-MODE
```ts
interface ModeResponse {
  mode: Ledger
  live: { since: string; days: number } | null
  liveOff: { from: string; to: string; offAt: string } | null    // '실전 9/1~10/7 · 16:12에 끔'
  twoLedgers: null | {
    since: string
    series: Array<{ date: string; live: number; paper: number; baseline: number; liveRet: number; paperRet: number; baselineRet: number }>
    endRet: { live: number; paper: number; baseline: number }
    breakdown: { fills: number; fees: number; other: number; total: number; valuedAt: string }    // pp, 합 = live - paper. valuedAt = 평가 시각('· 16:00')
  }
  performance: {
    since: string
    checks: number; rebalances: number; failures: number; paperFills: number
    ret: { pct: number; amount: number } | null     // 30거래일 미만이면 null('기간 짧음 · 30거래일부터 수익률')
    baselinePct: number | null
  }
  preflight: null | Array<{ id: 'health' | 'toss-link' | 'freshness' | 'push'; ok: boolean; warn?: boolean; facts: Record<string, string | number>; sameCauseAs?: string }>
  // facts 키: health ok면 { lastCheckAt }, 아니면 { count, source }(원인 수와 첫 원인의 출처 id)
  //          toss-link ok면 { checkedAt, account }(tick이 마지막으로 본 시각, 계좌 끝 4자리), 아니면 { cause: TossLinkCause };
  //          주인이 키 만료일을 알려 줬으면 둘 다 { expiresAt, daysLeft }를 더한다. 웹은 서버 cron에 열쇠가 있고(env-off 아님)
  //          15분 안에 본 결과로만 켤 수 있다: 웹 서비스는 토스를 부르지 않는다
  //          freshness ok면 { balanceAt, priceAt, fxAt }, 아니면 { source, basisDate } · push { devices, lastDelivery }
  preview: null
    | { kind: 'ok'; computedAt: string; hash: string; basis: { balanceAt: string; priceAt: string; fxRate: number; fxAt: string };
        current: Array<{ label: 'krw-cash' | 'usd-cash' | 'holding'; instrument?: Instrument; krw: number }>;
        target: Array<{ ruleId: string; instrument: Instrument; pct: number }>;
        stages: Stage[]; outside: Array<{ instrument: Instrument; qty: number; approxKrw: number }> }
    | { kind: 'not-computable'; at: string; cause: 'stale' | 'other' }
  cancelFailed: Order[] | null
  cancelPending: Order[] | null          // 3단계: 끄기·계획 종료로 토스에 취소를 요청했고 다음 확인(5분 안)이 처리할 주문(실패하면 cancelFailed로)
  canTurnOn: { ok: true } | { ok: false; cause: 'checks' | 'preview' | 'live-not-available' | 'cancel-pending' }
  // 1단계는 항상 live-not-available. 3단계: 지난 실전 주문의 취소가 안 끝났으면 'cancel-pending'(점검보다 먼저), 점검 ✕면 'checks',
  // 첫 주문을 계산할 수 없으면 'preview'
  offPreview: null | {                   // 실전이 켜져 있을 때만: 끄면 취소될 주문과 계좌에 남는 현금(실전 끄기 모달)
    cancel: Order[]                      // 실전 장부의 열린 계획에서 아직 대기 중인 주문
    cash: Array<{ currency: 'KRW'; krw: number } | { currency: 'USD'; usd: number; krw: number }>   // 0보다 큰 현금만. 달러의 krw는 지금 환율로
  }
}
// twoLedgers·preflight·preview는 실전이 생기는 3단계부터 채운다. 1·2단계는 null이다
```

### `GET /api/account` — SCR-ACCOUNT
```ts
interface AccountResponse {
  thisDevice: { name: string; kind: 'iphone-app' | 'iphone-safari' | 'mac' | 'other'; enteredAt: string }
  // name·kind는 로그인 때의 User-Agent로 정한다. name은 '[시스템] · [브라우저]'('Mac · Chrome', 'iPhone · Safari').
  // UA에 'Safari/'가 없는 iPhone을 홈 화면 앱으로 보고 name은 'iPhone'만 준다(화면이 '· 홈 화면 앱'을 붙인다)
  notifications: {
    available: boolean            // 웹 푸시가 있나. 1·2단계는 false: 화면은 알림을 한 줄('3단계에서 켤 수 있어요')로 접는다
    vapidPublicKey?: string       // 3단계: 이 기기를 구독할 때 쓰는 공개키(available일 때만)
    thisDevice: { supported: boolean; reason?: 'safari-tab' | 'denied' | 'unsupported'; subscribed: boolean }
    events: Array<{ id: NotifyEvent; on: boolean; locked?: boolean }>
    hideAmounts: boolean
    savedAt: string | null
    devices: Array<{ name: string; lastDelivery: string | null; ok: boolean }>
    testResults: Array<{ device: string; ok: boolean; at: string }> | null
  }
}
type NotifyEvent =
  | 'check-failed'      // 잠김(끌 수 없음), 일부 실패 포함
  | 'stale' | 'weekly-ok' | 'live-fill' | 'pin-failures' | 'toss-expiring'   // 처음부터 켜짐(6개 중 나머지 5)
  | 'check-missed' | 'rebalance-notice' | 'cash-moves'                         // 처음부터 꺼짐
  | 'ai-sell' | 'ai-buy' | 'ai-review'                                         // 2단계(화면-맞춤.md 3절)
```

## 쓰기
| 요청 | 본문 | 결과 |
|---|---|---|
| `POST /api/auth/pin` | `{pin}` | 204와 세션 쿠키. 틀리면 403 `{error:'pin', remaining}`, 잠기면 403 `{error:'locked', until, scope:'ip'|'global'}`, 새 로그인이 서버의 unlock까지 닫혔으면 403 `{error:'locked', scope:'hold', since}`(끝나는 시각 없음). 6자리 숫자가 아니면 400 `{error:'invalid-pin'}`(실패로 세지 않음). PIN이 아직 없으면 403 `{error:'no-pin'}` |
| `POST /api/auth/logout` | — | 204, 쿠키 지움 |
| `POST /api/auth/logout-others` | — | 204, 이 세션만 남김 |
| `POST /api/account/pin` | `{current, next}` | 204, 다른 세션 모두 끊김. 403 `{error:'current-pin'}`(틀린 PIN으로 셈). 이 접속 위치가 잠기면 403 `{error:'locked', until, scope:'ip'}`(1시간 상한과 'hold'는 PIN 바꾸기에 걸지 않는다). 한 세션에서 5회 연속 틀리면 그 세션을 끊고 403 `{error:'session'}`. `next`가 6자리 숫자가 아니면 400 `{error:'invalid-pin'}` |
| `POST /api/mode/live` | `{pin, confirm:true, previewHash}` | 200 `{mode:'live'}`. 다시 계산한 미리보기 금액이 1% 이상 다르면 409 `{error:'preview-changed', preview}`. 켤 수 없으면 409 `{error:'blocked', detail:{cause}}`(cause는 `canTurnOn.cause`: 3단계는 'cancel-pending' · 'checks' · 'preview'). 이미 실전이면 200(멱등). **1단계는 항상 409 `{error:'blocked', detail:{cause:'live-not-available'}}`** |
| `POST /api/mode/paper` | — | 200 `{mode:'paper', cancelFailed: Order[], cancelPending: Order[]}` (PIN 없음, 세션만). 토스에 가지 않은 주문은 바로 취소, 토스에 있는 주문은 취소 요청(다음 확인이 처리: `cancelPending`) |
| `POST /api/mode/cancel-retry` | — | 200 `{cancelFailed: Order[], cancelPending: Order[]}`(실패한 취소를 다시 요청, 다음 확인이 처리) |
| `PUT /api/account/notifications` | `{events?: {[id]: boolean}, hideAmounts?}` | 200 `{savedAt}`. 보낸 것만 바뀐다. 없는 id는 400 `{error:'unknown-event', detail:{event}}`, 잠긴 id(check-failed)를 끄면 400 `{error:'locked-event', detail:{event}}` |
| `POST /api/account/push` | `{subscription}` | 204. **1·2단계는 501 `{error:'not-implemented', detail:{feature:'push'}}`** |
| `DELETE /api/account/push` | — | 204, 이 기기의 구독을 끊음. **1·2단계는 501(위와 같음)** |
| `POST /api/account/push/test` | — | 200 `{results}`. **1·2단계는 501(위와 같음)** |

- 중복 요청은 멱등이다. `POST /api/mode/live`는 진행 중이면 409 `{error:'in-progress'}`를 준다.
- PIN 잠금(`autotrade/api/auth.py` 머리 주석에 이유). 틀린 PIN은 모두 다음에 센다.
  - 접속 위치: IPv4 주소, IPv6는 /64 묶음(한 집·한 휴대폰 망이 /64 하나를 통째로 갖는다). 5회 연속이면 그 위치를 30분 잠근다(`scope:'ip'`).
  - 전체 1시간: 어디서든 1시간에 20회면 그 1시간이 지날 때까지 새 로그인을 막는다(`scope:'global'`).
  - 전체 24시간: 10회면 'PIN 실패 급증'(작동 화면 빨간 직접 할 일 `pin-failures`, 헤더 '할 일'에 셈, 알림 사건 `pin-failures`의 기록), 30회면 서버에서 `python -m autotrade.jobs unlock`을 할 때까지 새 로그인을 닫는다(`scope:'hold'`). 1시간 상한만으로는 그 바로 아래 속도로 하루 480회씩 끝없이 맞혀 볼 수 있었다.
  - 이미 열린 세션은 어떤 잠금에도 그대로다. PIN 바꾸기는 세션이 있어야 하므로 접속 위치 잠금만 건다(누군가 PIN을 맞혀 보는 동안에도 주인이 바꿀 수 있게). 틀리면 똑같이 세고, 한 세션에서 5회 연속이면 그 세션을 끊는다(훔친 쿠키로 여러 주소에서 맞혀 보지 못하게).
- 첫 PIN은 웹에서 만들지 않는다. 서버 CLI로만 만든다(`python -m autotrade.jobs set-pin`, PIN은 표준 입력으로 두 번). CLI로 PIN을 다시 정하면 열린 세션이 모두 끊기고, `unlock`처럼 잠금·실패 기록도 모두 지운다. `unlock`은 세션을 건드리지 않는다.
- `GET /api/healthz`는 세션 없이, DB가 코드의 스키마 판일 때만 200 `{ok: true, schema: number}`를 준다. 다르면(배포 중 이전 전후, 실패한 이전, 이전된 DB 위의 옛 코드) 503 `{error:'schema', detail:{stored, code}}`, DB를 못 읽으면 503 `{error:'db'}`. 배포 헬스체크용이다.

### 오류 코드
| 상태 | `error` | `detail` | 언제 |
|---|---|---|---|
| 400 | `bad-request` | `{fields: string[]}` | 본문·쿼리·경로 값의 형식이 틀림(없는 `period`, 날짜 아님, JSON이 아닌 본문 …). 세션이 필요한 경로는 세션을 먼저 본다: 세션이 없으면 본문이 깨져 있어도 403 `session` |
| 400 | `invalid-pin` | — | PIN이 6자리 숫자가 아님 |
| 400 | `unknown-event` · `locked-event` | `{event}` | 알림 설정(위 표) |
| 403 | `session` | — | 세션 쿠키가 없거나 만료·끊김(서명이 안 맞거나 ASCII가 아닌 쿠키 값도 같다) |
| 403 | `origin` | — | 쓰기 요청(POST·PUT·PATCH·DELETE)이 이 사이트에서 오지 않음(아래 '세션과 보안') |
| 403 | `no-pin` · `pin` · `locked` · `current-pin` | — | PIN(위 표). `pin`·`locked`는 `remaining`·`until`·`scope`(`hold`면 `until` 대신 `since`)를 맨 위에 싣는다 |
| 404 | `not-found` | `{rule}`(규칙일 때) | 없는 `/api` 경로, 없는 규칙 id |
| 404 | `no-ledger` | `{ledger}` | `?ledger=`로 시작한 적 없는 장부를 열 때. 지금 모드의 장부는 404 대신 첫 확인 전 상태를 준다 |
| 405 | `method-not-allowed` | — | |
| 409 | `blocked` · `preview-changed` · `in-progress` | `{cause}`(blocked) | 실전 켜기(위 표) |
| 500 | `internal` | — | 서버 오류. 보안 헤더는 그대로 붙고, 서버 로그에 경로와 traceback이 남는다(헤더·쿠키·본문은 남기지 않음) |
| 501 | `not-implemented` | `{feature}` | 아직 없는 기능(`push`, 3단계) |
| 503 | `schema` | `{stored, code}` | 모든 `/api`(세션 확인보다 먼저): DB가 코드의 스키마 판이 아님. 배포의 이전과 재시작 사이에 잠깐 나고, 남아 있으면 배포가 실패한 것이다 |
| 503 | `db` | — | DB를 열거나 읽지 못함 |

## 세션과 보안
- 쿠키 `__Host-qsess`: HttpOnly, Secure, SameSite=Strict, Path=/, Domain 없이 둔다(host-only). `__Host-` 접두어라 브라우저가 이 조건을 강제하고, 다른 `*.jsyoo.dev` 사이트가 같은 이름으로 쿠키를 심거나 가리지 못한다. HMAC으로 서명하고 30일 동안 유효하다. 서버 비밀값은 `data/autotrade.secret`이다.
  - 개발용(`AUTOTRADE_DEV=1`이고 DB가 `data/` 밖, dev-seed 세계)만 http에서도 되도록 Secure 없는 `qsess`를 쓴다. `data/autotrade.db`에서는 `AUTOTRADE_DEV`·`AUTOTRADE_FAKE_NOW`를 무시한다.
- 쓰기(POST·PUT·PATCH·DELETE)는 이 사이트에서 온 것만 받는다. SameSite=Strict는 `*.jsyoo.dev`를 모두 같은 사이트로 보아서, 옛 portfolio 앱의 스크립트가 주인의 쿠키로 본문 없는 쓰기(`logout-others`, `mode/paper`)를 보낼 수 있었다.
  - 받는 것: `Sec-Fetch-Site`가 `same-origin`·`none`, 또는 `Origin`의 호스트(와 포트)가 요청의 `Host`와 같음. nginx 뒤에서 앱은 http로 받고 브라우저 origin은 https라서 scheme은 비교하지 않는다. nginx는 `Host $host`를 그대로 넘겨야 한다.
  - 두 헤더가 다 없는 요청(curl, 배포 확인)은 브라우저가 아니므로 받는다. 그 밖은 403 `{error:'origin'}`.
- 세션이 필요한 경로는 본문을 세션 확인 뒤에 읽는다(JSON이 아니거나 `application/json`이 아니면 400 `bad-request`).
- API는 DB를 이전하지 않는다(`python -m autotrade.jobs migrate`만 한다). 저장된 스키마(`schema_migrations`의 가장 큰 판, 표가 없으면 0)가 코드와 다르면 `/api/*`는 503 `schema`다. DB 파일이 없어도 만들지 않는다.
- CSP: `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'`.
- 모든 응답에 `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY`를 붙인다. `/api/*` 응답은 `Cache-Control: no-store`다.
- 세션은 서버 DB에 남는다(id·만료·끊김). 쿠키 값은 `<세션 id>.<만료 unix 초>.<HMAC>`이고, 끊긴 세션의 쿠키는 서명이 맞아도 403이다.
- 접속 위치(IP)는 요청이 127.0.0.1(nginx)에서 왔을 때만 `X-Forwarded-For`를 읽는다(nginx가 붙인 맨 오른쪽 값).
- `/docs`·`/redoc`·`/openapi.json`은 끈다. 정적 파일은 빌드 결과(`web/dist`)만 내준다. `index.html`은 no-cache, 해시 붙은 파일(`/assets/*`)은 immutable이다. 둘 다 `no-transform`을 붙인다: Cloudflare가 HTML에 Web Analytics 비컨을 끼워 넣지 못하게 한다(넣으면 CSP가 막아 페이지마다 콘솔 오류 둘, 2026-10-12 실서버에서 봄). `/api`가 아닌 다른 경로는 모두 `index.html`(화면 라우팅)이고, 빌드가 없으면 `/`는 503 안내 페이지다. 어떤 파일도 가질 수 없는 경로(제어 문자, 255바이트를 넘는 경로 조각, 1,024자 넘는 경로)는 파일 시스템에 묻지 않고 404 text다.
  - 서버의 `web/dist`는 지금 릴리스(`web/releases/<id>`)를 가리키는 심볼릭 링크다(배포가 원자적으로 바꾼다). 릴리스마다 이전 릴리스들의 해시 자산을 함께 두어, 배포 전에 연 화면도 청크를 찾는다.
- 앞단(nginx, `deploy/nginx-quant.conf`): Cloudflare에서 온 연결만 받는다. `Strict-Transport-Security: max-age=31536000`(quant.jsyoo.dev만, includeSubDomains 없음), 서버 판 번호는 숨긴다.

## 화면 상태와 고정 자료
- 화면은 `src/fixtures/bundles/<상태 id>.ts`(이 계약의 응답 묶음, 타입 검사를 받음)로 모든 상태를 띄운다. 개발 서버와 Playwright만 쓰고, 운영 빌드에는 넣지 않는다.
- 상태 id는 화면과 상태를 '.'으로 잇는다.
  - home.paper(모의투자 기본), home.live(실전 평상), home.live-first(실전 첫 체결 전), home.withdraw(출금 대기), home.stale(시세 대기), home.partial(일부 실패), home.offline, home.other-device, home.first-day(출시 첫날), home.empty(첫 확인 전)
  - 계좌별 보기(그림 없음): home.paper가 '전체'(계좌 칸·환율 효과), home.account-kr·home.account-us(같은 세계에서 스위치 '한국 ₩'·'미국 $', 주소 `?account=kr|us`), home.before-fill(첫 체결 전: 스위치 없음), home.us-cash(미국 계좌에 달러 현금만), home.us-empty(미국 계좌가 빔: 환전 전)
  - plan.paper, plan.live, plan.stale, plan.partial, plan.live-todo, plan.first-day
  - history.paper, history.paper-ledger
  - day.0821, day.0925
  - rules.index-half, rules.momentum, rules.first-day
  - health.todo, health.stale, health.unknown, health.failed
  - mode.paper, mode.live, mode.turning-on, mode.off-confirm, mode.off-failed, mode.blocked, mode.short
  - account.default, account.no-push
  - pin.entering, pin.error, pin.locked
- 위 목록은 Figma 디자인 페이지의 프레임 50장과 일대일이다. 그림이 없는 상태(명세에만 있는 것)는 같은 규칙으로 이름을 붙여 더한다.

## 바뀐 것
- 2026-10-09: 처음 씀(메인 세션).
- 2026-10-09: API 구현에 맞춤(API 세션). 오류 코드 표, `/api/healthz`, 1단계 실전 켜기 409 `live-not-available`(+ `canTurnOn.cause`), 푸시 501, partial-todo `retry-failed`, 할 일 `order-failed`, 시세 대기 다음 할 일 `market: 'FX'`, 그날 확인 결과 `in-progress`·`withdraw-wait`·`no-run`, 변동 분해의 부호와 'all' 기준, 시작 사건의 단계·수수료, 환전 주문 `market: 'KR'`, recent14 평일만, 1단계 출처 3개(`extra.market`), 이니셜 규칙, 이 기기 판별, 보안 헤더·`no-store`를 더했다.
- 2026-10-09: 이니셜 규칙을 Figma에 맞춤(K2·SP·삼·NV·B), 종목 id 예시 SPYM, 고정 자료 위치를 bundles/*.ts로(메인 세션).
- 2026-10-09: 서버 무인 운영(엔진 세션). HistoryEvent에 `resolvedOn`(직접 할 일을 닫은 날)을 더했다. 배당 줄은 규칙(`rule`)을 싣고 규칙 칩 수에 들어간다(예시 '지수 반반 3'). 달러 배당의 `amount`·`krw`와 변동 분해의 `dividend`는 원화다. 직접 처리로 닫힌 리밸런싱은 `partial-failed`로 남는다. 사건이 있는 달은 스냅숏이 없어도 월 목록에 나온다(변동 0).
- 2026-10-09: 2단계 '3년 발굴'(엔진 세션). 계획 탭에 AI 규칙 카드(게이지 `sell-condition`, 종목 줄 `progress`·`metric`·`marginText`, `vsIndex`, `basisLine.metricTableAt`)와 `ruleShares`(두 규칙의 지금 몫)를 더했다. 계약 공백의 제안 1·2·5(`vsIndex`, `metricTableAt`, 예정 항목 `ruleId`는 AI 규칙 항목에만)를 받았다. 지수 반반의 `share.target`은 규칙 몫 설정(모의 80)이다. 구성은 규칙별로 나뉜다: 3년 발굴 묶음에 그 규칙의 종목·그 규칙 몫의 지수 ETF·그 규칙 현금(칩 없음)이 들어간다. 홈 계획 카드 `others`, 규칙 목록·`/api/rules/discovery_3y?lane=`(FlowDisplay, 선 `no-wait` 더함, '지금' kv 키 목록), 그날 화면 AI 판단 사건(`judgment`), AI 규칙 계획의 리밸런싱 사건(`weights.target` 빈 배열·`threshold` 0), 기록의 `filters.kinds` 'ai'와 AI 규칙 칩, 작동 화면의 출처 filings·ai-cli·metric-table과 할 일 ai-cli·filings의 facts를 정했다. 몫이 0인 장부(실전)에는 AI 규칙이 나오지 않는다. 이니셜: 한국 종목 이름이 로마자로 시작하면 이름의 앞 로마자 두 글자까지다(HD현대일렉트릭 'HD', SK바이오팜 'SK').
- 2026-10-09: 계약 공백 정리 · 자산·계획(API 세션). 자산 그래프 표식에 `kinds`(그날 사건 전부)를 더했다. 첫 확인 전에도 `planCard`를 준다(바늘·단계 없음, `others.status` 'before-first'). 현금 행에 `cash.country`, 벗어남 사건의 `ruleId` null(시작·실전 켬·끔), 다음 할 일 `next-check.reviewAt`(다음 월 점검), 예정 항목 `retry`의 `ruleId`를 더했다. 월 점검·분기 발굴의 예정 시각은 1일 08:30, `metricTableAt`은 날짜다. `vsIndex`는 2단계에서 받은 그대로다.
- 2026-10-09: 계약 공백 정리 · 작동·모드·설정·입장(API 세션). 할 일과 켜기 전 점검의 `facts` 키를 고정했다(낡음 `missingDates`, ai-cli 빨강 `since`, filings `market`, filings는 빨강). `summary.todoCount`는 직접 할 일 카드(action 'manual') 수이고, 노란 카드만 있으면 `summary.kind`는 'ok'다. `recent14[].run.reason`·`lastRun.reason`은 코드다. `/api/health`에 `devices`를 더했고, 토스 연결 `age`는 지난 날 ÷ 90일이다. `/api/mode`에 `offPreview`(취소될 주문·남는 현금), 두 장부 분해에 `valuedAt`(3단계)을 더했다. `notifications.available`(1·2단계 false), `vapidPublicKey`(3단계), `DELETE /api/account/push`(지금은 501)를 더하고 기기 이름 형식을 적었다.
- 2026-10-09: 계약 공백 정리 · 기록·그날·규칙(API 세션). 기록 사건에 `pending`(기다리는 단계·시각)과 `weightsMini.target`, 주문에 `retried`(다시 낸 결과, 실패한 주문은 실패한 날의 기록으로 남음)와 환전 `direction`, 그날 확인에 `failure`(코드·회복한 날)와 `rule`을 더했다. 규칙 목록 `example`, 규칙 상세 `stale`, 조건 타일 `deviation`, 흐름 카드 `more`·`targets`, '지금' 칸 `until`·kv `note`(데이터만)·주문 행 `retried`를 더하고, 주문 행 `text`(종목 이름 또는 환전 방향 코드)와 AI 규칙 kv 키 목록을 다시 정했다. '대기 6'은 상태가 아니라 kv `candidates`이고, 살 값까지 막대는 종목 줄의 `progress`·`marginText`다. 급락 확인 판단의 `outputSummary`에 뉴스 출처·날짜가 붙는다.
- 2026-10-09: 서버 문구 걷어냄(API 세션). AI 판단의 `inputSummary`·`outputSummary`를 `input`·`output`(JudgmentItem: 코드·수·날짜·종목)으로 바꿨고, 모델이 쓴 근거와 뉴스는 기록에만 남긴다. `votes`에 바꾸기의 'switch'·'keep'을 더했다. 게이지·종목 줄의 `metric`은 지표 사전 키와 회사의 말(`MetricRef`), `marginText`는 수와 단위(`Margin`)로 바꿨고, '지금' 종목 행은 `margin`·`period`를 쓴다. 응답의 한국어는 이제 데이터 이름(종목·규칙 이름, 회사의 부문 이름, 규칙 정의의 흐름 카드 글)뿐이다. 헤더 '점검 n'은 1거래일 넘게 멈춘 AI 규칙 자료(공시 DART·EDGAR, AI 호출)를 원인으로 센다.
- 2026-10-09: 웹 통합 실행에서 나온 것(API 세션). 그날 화면의 `basis`는 `total`과 같은 평가의 기준이다(주말·평가 없는 날은 그 전 마지막 평가, 휴장일은 그날 16:00 평가). 그날 확인과 기록의 리밸런싱 사건에 `cause`(`RebalanceCause`: band·new-cash·withdraw-expired)를 더했다. 홈 자산 그래프 표식(`Trend.events`)에서 check-failed를 뺐다(기록에는 남는다).
- 2026-10-10: 점검 고침(엔진 세션). 사는 판단도 두 번 묻는다: 사기 확인의 `votes`에 'buy'·'skip'(두 답)을 더했고, 입력 줄에 `filings`(꾸러미의 최근 공시 수)와 분기 발굴이 새로 고른 종목이면 `checks` 대신 `month`가 온다. 분기 발굴 판단의 `action`은 늘 'none'이다(새 종목은 사기 확인 두 번 뒤에 산다). 작동 화면의 ai-cli 줄은 웹 서비스의 환경이 아니라 AI 실행기의 심장 박동을 읽는다: `extra.enabled`는 실행기가 본 값이고 `cli`·`lastRunAt`·`running`·`runningSince`를 더했으며, CLI를 못 찾으면 줄이 'stale'이다. ai-cli 할 일에 빨강 'cli-missing', 노랑 'call-running'·'queue-waiting'(`cause`)을, filings 할 일에 실행기에 DART 키가 없을 때의 state 'no-key'(action 'manual')를 더했다. 헤더 '점검 n'은 실행기가 CLI를 1거래일 넘게 못 찾을 때도 센다.
- 2026-10-10: 보안 감사 수정(API 세션). 쿠키 이름 `__Host-qsess`(개발용만 Secure 없는 `qsess`). 쓰기 요청의 출처 검사와 403 `origin`. 세션이 필요한 경로는 본문보다 세션을 먼저 본다. 스키마 판이 코드와 다르면 모든 `/api`가 503 `schema {stored, code}`(API는 이전하지 않음, `/api/healthz` 포함), DB를 못 읽으면 어디서나 503 `db`. PIN 잠금: IPv6는 /64로 묶고, 24시간에 10회면 할 일 `pin-failures`('PIN 실패 급증'), 30회면 `scope:'hold'`(서버 `unlock`까지, `since`). PIN 바꾸기에는 접속 위치 잠금만 걸고, 한 세션에서 5회 연속 틀리면 그 세션을 끊는다(403 `session`). 고정 자료 `pin.hold`(그림 없음)를 더했다. 제어 문자·너무 긴 경로는 404 text, 깨진 쿠키는 403 `session`.
- 2026-10-12: 계좌별 보기와 설정 정리(웹 세션, 주인 요청 '국장과 미장은 엄연히 다른 화폐단위'). `HomeResponse.accounts`(한국 계좌·미국 계좌를 각 통화로: 값·손익·선·구성, 선의 점마다 원금 `netIn`, 30거래일 규칙은 계좌 기록으로, 리밸런싱 표식은 그 계획이 닿은 계좌에만)와 `split`(전체 손익 = 한국 + 미국 원화 환산 + 환율 효과, 원 단위까지 맞음)을 더했다. 환전은 계좌 사이를 옮기는 돈이고 손익이 아니다. '손대지 않았을 때'는 전체에만 둔다. `/api/home/breakdown?account=`(`Breakdown.currency`·`transfer`)를 더했다. 설정의 알림은 `notifications.available`이 false인 동안(1·2단계) 화면이 한 줄로 접는다(API는 그대로). 고정 자료 home.account-kr·home.account-us·home.before-fill·home.us-cash·home.us-empty를 더했다.
- 2026-10-13: 3단계 실전 연결(토스 세션, autotrade/PHASE3.md). 작동 화면 할 일에 `toss-link`(원인 `TossLinkCause`, 실전이면 빨강, 사람이 고칠 원인만 직접 할 일)·`broker-mismatch`(대조가 맞지 않음: 보유 수량·현금·결과를 모르는 주문, 그동안 실전 주문 0건)·`fx-manual`(토스 앱에서 할 환전: 방향·원화·달러·환율·기다리는 매수 시각)을 더하고 `cancel-failed`의 facts를 정했다. 토스 연결 줄은 'per-check'다(토스 API에 키 만료가 없다): tick이 마지막으로 본 결과, `extra.cause`·`account`, 주인이 알려 준 키 만료일이 있을 때만 basis·`daysLeft`(14일 안이면 'late'). '90d'는 1·2단계 그림의 값으로 남는다. `/api/mode`에 `cancelPending`(토스에 요청한 취소, 다음 확인이 처리)과 `canTurnOn.cause` 'cancel-pending'을, 켜기 전 점검 toss-link의 facts(`checkedAt`·`account` 또는 `cause`)를 더했다. `POST /api/mode/paper`·`/cancel-retry`가 `cancelPending`을 준다. 실전 장부는 계좌별 보기가 읽는 대로 적는다: 계획의 환전은 그 환전 주문의 fx 체결(주문의 `executed_at`은 계좌가 보여 준 시각), 실전 체결 주문의 `executed_at`은 브로커 시각, 대조가 찾은 입·출금·배당은 그 통화의 사건(`occurred_at` = 계좌에서 처음 보인 시각). 달러가 있는 시작과 adopt-broker는 payload `by_currency`(통화마다 들어온 돈, 부호 있음)를, 계획에 없던 환전(주인이 앱에서)은 'conversion' 표시가 붙은 출금·입금 사건 둘을 남기고 계좌별 보기는 이를 계좌 사이의 이동으로 읽는다.
