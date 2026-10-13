// Transcription of autotrade/CONTRACT.md (the API contract with the engine).
// Generated from the contract's ```ts blocks with `export` added; comments are the contract's.
// Re-transcribe when the contract changes (its '바뀐 것' section records each change).
// The types at the bottom transcribe the contract's '쓰기' and '오류 코드' tables.
// Contract snapshot: sha256 de1f5ef1efe4 (2026-10-09, final, after the screens' gaps were folded in).
/* eslint-disable @typescript-eslint/array-type -- kept exactly as the contract writes it */

// ── 공통 타입 ──
export type Ledger = 'paper' | 'live';
export type Market = 'KR' | 'US' | 'COIN';
export type Currency = 'KRW' | 'USD';
export type Side = 'buy' | 'sell' | 'fx';

export interface Instrument {
  id: string; // 'KR:069500', 'US:SPYM'
  name: string; // 'KOSPI200 ETF', 'S&P 500 ETF'
  kind: 'etf' | 'stock' | 'coin';
  market: Market;
  currency: Currency;
  initials: string; // 로고 자리 이니셜(Figma 기준): 지수 ETF는 지정값(069500 'K2', SPYM 'SP'), 한글 이름은 첫 글자('삼'), 로마자로 시작하는 한국 종목 이름은 앞 로마자 두 글자까지('HD'·'SK'), 코인은 티커 첫 글자('B'), 그 밖은 티커 앞 두 글자('NV'). 현금 행은 화면이 ₩·$를 그린다
  outsideToss?: boolean; // 토스 밖 계좌(코인)
}

export interface RuleRef {
  id: string; // 'index_half', 'discovery_3y'
  name: string; // '지수 반반', '3년 발굴'
  ai: boolean; // 'AI 판단 포함' / 'AI 없음'
  colorIndex: number; // 규칙 색(구성 막대·벗어남 선): 0, 1, 2…
  example?: boolean; // 이름 앞 '[예시]'
}

// 상태 칩 일곱 가지(SCR-PLAN 완료 조건). AI 규칙은 같은 칩에 다른 낱말을 쓴다(화면-맞춤.md ②, 'hold' = '유지').
// 'fx-suggest'('환전 제안')는 실전 장부의 지수 반반만(D47): 원화·달러가 목표에서 띠보다 멀다. 정보일 뿐 막는 것 없음
export type RuleStatus =
  | 'in-range'
  | 'scheduled'
  | 'in-progress'
  | 'partial-failed'
  | 'holiday'
  | 'quote-wait'
  | 'withdraw-wait'
  | 'fx-suggest' // 실전 장부 전용(D47)
  | 'hold'
  | 'sell-scheduled'
  | 'buy-scheduled'; // AI 규칙 전용

export interface Basis {
  // '기준' 칩과 시트
  valuedAt: string; // 평가 시각(16:00)
  krClose: string | null; // 한국 종가 기준일
  usClose: string | null; // 미국 종가 기준일(ET)
  fxRate: number | null; // rate
  fxAt: string | null;
  coinAt?: string | null;
}

export interface Order {
  id: string;
  market: Market; // 환전(fx)은 'KR'(원화 계좌에서 09:10에 한다)
  side: Side;
  instrument?: Instrument; // fx면 없음
  qty?: number; // 주(코인은 소수)
  price?: number; // 체결가 또는 예상가(종목 통화)
  approx?: boolean; // '약 $124.80'
  amountKrw?: number;
  amountUsd?: number;
  fee?: { krw?: number; usd?: number };
  fx?: { krw: number; usd: number; rate: number }; // 환전
  direction?: 'krw-usd' | 'usd-krw'; // 환전의 방향('원 → 달러')
  at: string; // 체결 시각 또는 예정 시각. 실패한 주문은 실패한 시각
  status: 'filled' | 'pending' | 'failed';
  fill?: 'paper' | 'live'; // '모의 체결' / '실제 체결'
  failure?: {
    reason: 'no-quote' | 'broker-rejected' | 'cancel-failed' | 'other';
    retryAt?: string;
    manual?: boolean;
  };
  retried?: { at: string; status: 'filled' | 'failed' };
  // 다시 낸 결과('9/15 다시 · 체결'). 실패한 주문은 실패한 날의 기록으로 status 'failed'·failure를 그대로 두고,
  // 다시 낸 주문의 결과가 나오면 retried를 붙인다. retried.status가 'filled'면 더 기다릴 것이 없다(다시 시도 예정 항목도 없다)
}

export interface Stage {
  kind: 'sell' | 'fx' | 'buy'; // 매도 → 환전 → 매수. 주문 0건 단계는 보내지 않는다(화면이 숨김).
  status: 'done' | 'pending' | 'failed';
  at: string; // 대표 시각(09:05 / 09:10 / 22:30)
  orders: Order[];
}

export type NextAction =
  | { kind: 'order'; at: string; market: Market; side: Side; instrumentName: string; qty: number } // '오늘 22:30 미국 매수 2주'
  | { kind: 'first-check'; at: string } // '첫 확인 7/1(수) 08:30 · 목표대로 매수'
  | { kind: 'first-order'; at: string; market: Market; side: Side; count: number } // '오늘 09:05 첫 주문 · 한국 매수 2건'
  | { kind: 'retry'; at: string; market: Market; side: Side }
  | { kind: 'todo'; market: Market; side: Side } // '직접 할 일 · 토스 앱에서 주문 확인'
  | { kind: 'withdraw-wait'; until: string } // '10/12까지 · 리밸런싱 쉼'
  | { kind: 'holiday'; markets: Market[]; nextCheckAt: string }
  | { kind: 'quote-wait'; market: Market | 'FX'; basisDate: string } // 'FX' = 환율이 낡음
  | { kind: 'next-check'; at: string; reviewAt?: string }; // AI 규칙: '다음 확인 10/8 08:30 · 점검 11/1'(다음 월 점검, 1일 08:30)

export type EventKind =
  | 'start'
  | 'rebalance'
  | 'partial-failed'
  | 'in-progress'
  | 'check-failed'
  | 'dividend'
  | 'deposit'
  | 'withdrawal'
  | 'live-on'
  | 'live-off'
  | 'discovery'
  | 'ai-buy'
  | 'ai-sell'
  | 'ai-check'
  | 'monthly-review'; // AI 규칙(2단계)

export type CalendarState =
  | 'normal'
  | 'rebalance'
  | 'in-progress'
  | 'partial-failed'
  | 'failed'
  | 'no-run'
  | 'holiday-one'
  | 'holiday-both'
  | 'quote-wait'
  | 'future'
  | 'before-record';

// ── `GET /api/shell` — 모든 화면의 헤더(60초마다 다시 읽음) ──
export interface ShellResponse {
  now: string;
  mode: Ledger;
  modeChangedAt: string | null; // 화면이 기억한 모드와 다르면 '다른 기기에서 바뀜' 칩 + 스켈레톤
  liveSince: string | null;
  status:
    | { kind: 'ok'; lastCheckAt: string }
    | { kind: 'before-first'; firstCheckAt: string }
    | { kind: 'check'; count: number } // 원인 단위로 센다
    // AI 규칙의 자료(공시 DART·EDGAR 하나씩, AI 호출)는 마지막 성공 뒤로 그 시장의 거래일이 하루를 넘게 지나야
    // 원인으로 센다(밤사이 DART 점검으로 헤더가 바뀌지 않게). 작동 화면은 첫 실패부터 보인다. 한 번도 성공하지 못한
    // 자료는 첫 시도(감시 작업·첫 AI 호출)부터 센다
    | { kind: 'check-failed'; at: string }
    | { kind: 'todo'; count: number }
    | { kind: 'cancel-failed'; count: number };
  // '확인 불가'·'연결 안 됨'은 이 응답을 못 받았을 때 화면이 정한다
  banner: Banner | null; // 한 번에 하나, 서버가 우선순위를 정함
}
export type Banner =
  | { kind: 'stale'; market: Market | 'FX'; basisDate: string; tradingDays: number; link: 'health' }
  | {
      kind: 'partial-retry';
      date: string;
      market: Market;
      side: Side;
      retryAt: string;
      link: 'plan';
    }
  | {
      kind: 'partial-todo';
      date: string;
      market: Market;
      side: Side;
      reason: 'broker-rejected' | 'retry-failed';
      link: 'health';
    } // retry-failed = 다시 시도까지 실패(모의투자는 이것뿐)
  | { kind: 'check-failed'; at: string; retryAt: string | null; link: 'health' }
  | { kind: 'cancel-failed'; market: Market; side: Side; link: 'mode' }
  | { kind: 'push-undelivered'; days: number; link: 'account' };

// ── `GET /api/home?ledger=&period=` — SCR-HOME ──
export interface HomeResponse {
  ledger: Ledger;
  example: boolean; // '예시' 칩(고정 자료만 true)
  startDate: string; // '[장부] 자산 · 7/1부터'
  basis: Basis;
  stale: Array<'hero' | 'plan' | 'composition'>; // 섹션마다 '낡음' 태그 1개
  total: number; // krw
  pnl: { amount: number; pct: number | null } | null; // null이면 '손익 · 첫 체결 뒤'. pct null이면 % 숨김(분모 0 이하)
  baseline: { pct: number } | null; // '손대지 않았을 때'
  planChip: { ruleId: string; status: RuleStatus; next: NextAction };
  trend: Trend;
  planCard: PlanCard; // 첫 확인 전에도 준다(바늘·단계 없음)
  composition: Composition;
  accounts: HomeAccounts | null; // 계좌별 보기('전체 · 한국 ₩ · 미국 $'). pnl이 null이면(첫 체결 전) null
}

// 계좌는 통화로 가른다: 한국 계좌 = 원화 종목 + 원화 현금, 미국 계좌 = 달러 종목 + 달러 현금. 환전은 두 계좌 사이를 옮기는
// 돈이고 손익이 아니다. 배당·수수료·세금은 그 통화 계좌의 손익. 계좌 손익 = 계좌 값 − 들어온 돈(그 통화).
export type AccountId = 'kr' | 'us';
export interface HomeAccounts {
  list: HomeAccount[]; // 한국 계좌('kr'), 미국 계좌('us') 순. 둘 다 늘 있다
  split: { kr: number; us: number; fx: number };
  // krw. 전체 손익 = kr + us + fx. us = 미국 손익(달러) × basis.fxRate(원 단위 반올림), fx = '환율 효과'(나머지)
}
export interface HomeAccount {
  id: AccountId;
  currency: Currency; // kr 'KRW' · us 'USD'
  total: number; // 그 통화(krw 정수 · usd 센트)
  pnl: { amount: number; pct: number | null } | null; // 그 통화. null = 돈이 들어온 적 없는 빈 계좌
  stale: boolean; // 그 계좌 시세가 낡음(한국 kr-quotes · 미국 us-quotes)
  trend: Trend; // 그 통화. 30거래일 규칙은 그 계좌 기록으로. baseline·baselineRet는 늘 null(손대지 않았을 때는 전체만).
  // events: 시작·실전 켬/끔은 두 계좌, 리밸런싱은 그 계획의 주문이 닿은 계좌, 입출금·배당은 그 통화 계좌
  composition: Composition; // pct = 계좌 대비, target null. 미국 계좌는 모든 행에 usd(금액), krw는 원화 환산
}

export interface Trend {
  periods: Array<'1m' | '3m' | '1y' | 'all'> | null; // 기록 30거래일 미만이면 null(기간 칩 숨김)
  period: '1m' | '3m' | '1y' | 'all';
  periodPnl: { amount: number; pct: number } | null; // '전체'거나 기록이 짧으면 null
  series: Array<{
    date: string;
    value: number;
    ret: number;
    baseline: number | null;
    baselineRet: number | null;
    netIn?: number; // HomeAccount.trend만: 그날까지 들어온 돈(그 통화)
  }>;
  events: Array<{ date: string; kind: EventKind; kinds: EventKind[]; count?: number }>;
  // 하루에 표식 하나. kind는 그날 첫 사건, kinds는 그날 사건 전부(순서대로), 둘 이상이면 count(묶음 표식)
  empty: null | 'before-first-check' | 'before-first-fill' | 'first-day';
}

export interface PlanCard {
  rule: RuleRef;
  share: { pct: number; target: number | null }; // '자산의 81.1% · 목표 80%'
  status: RuleStatus;
  next: NextAction;
  gauge: Gauge;
  stages: Stage[] | null; // 진행 중일 때만(첫 확인 전에는 null)
  nextCheckAt: string;
  others: { count: number; status: RuleStatus | 'before-first' } | null;
  // '외 n개 규칙 · [상태]'. 2단계: 3년 발굴의 몫이 0보다 크면 { count: 1, status: AI 규칙 상태 }, 첫 확인 전이면 'before-first'('첫 확인 전')
}
// HomeResponse.planCard는 첫 확인 전에도 있다: 규칙 이름·목표를 보이고, 게이지 바늘(needle)과 단계는 비운다.

export type Gauge =
  | {
      kind: 'drift';
      threshold: number;
      needle: null | {
        // null = 바늘 숨김(시세 대기·첫 확인 전)
        instrument: Instrument;
        deviation: number;
        toThreshold: number;
      };
    } // pp1
  | {
      // 실전 장부의 지수 반반(D47): 원화·달러 비율. 띠는 '환전 제안'의 문턱이고 리밸런싱하지 않는다
      kind: 'mix';
      threshold: number;
      needle: null | {
        // null = 바늘 숨김(시세 대기·첫 확인 전·자료가 낡음·규칙 돈 없음)
        now: { kr: number; us: number }; // pct1, 합 100.0 (FxSuggestion.now와 같은 셈)
        deviation: number; // pp1, 한국 − 한국 목표(+ = 원화가 많음)
        toThreshold: number; // pp1, 환전 제안까지(띠 밖이면 0)
      };
    }
  | {
      kind: 'sell-condition';
      needle: null | {
        // AI 규칙(D34)
        instrument: Instrument;
        progress: number;
        metric: MetricRef;
        margin: Margin;
      };
    };

export interface MetricRef {
  // 지표 사전(autotrade/domain/metrics.py)의 키와 회사가 쓰는 말. 이름은 화면이 짓는다
  key:
    | 'revenue'
    | 'operating_income'
    | 'net_income'
    | 'op_margin'
    | 'eps'
    | 'fcf'
    | 'ebitda_margin'
    | 'net_debt_to_ebitda'
    | 'backlog'
    | 'new_orders'
    | 'book_to_bill'
    | 'monthly_revenue_yoy'
    | 'segment_revenue'
    | 'segment_operating_income'
    | 'segment_op_margin'
    | 'segment_backlog'
    | 'guidance';
  param?: string; // segment_*·guidance만: 회사의 부문·항목 이름('지상방산' → '지상방산 수주잔고')
}
export interface Margin {
  // 선까지 남은 것. 화면이 단위에 맞춰 쓴다('2.3%p', '3.1조', '$350M', '0.12x', '2분기', '2.1%')
  unit: 'pp' | 'pct' | 'KRW' | 'USD' | 'x' | 'count' | 'quarter' | 'month' | 'year';
  value: number; // pp는 pp1, pct는 소수 1자리, KRW는 원, USD는 달러, 기간은 남은 수
}

export interface Composition {
  groupBy: Array<'instrument' | 'kind' | 'country' | 'currency' | 'rule'>; // 묶음이 2개 이상 생기는 기준만
  groups: Array<{
    key: string;
    rule?: RuleRef; // '● 지수 반반'
    label?: 'cash'; // '현금'
    pct: number; // pct1 = 행 %의 합
    target: number | null;
    rows: CompRow[];
  }>;
  pendingBar: { withdraw?: { krw: number; until: string } } | null; // 빗금 칸
  outsideRules: { count: number; krw: number } | null; // '규칙 밖 [n]개 [금액] · 손익 제외'
}
export interface CompRow {
  kind: 'holding' | 'cash';
  instrument?: Instrument;
  cash?: { currency: Currency; country: 'KR' | 'US' }; // 묶어 보기 '나라': 원화 현금은 한국, 달러 현금은 미국
  pct: number; // pct1, 전체 자산 대비
  krw: number;
  usd?: number;
  pnlPct?: number; // ret 1자리
  qty?: number;
  avgCost?: { amount: number; currency: Currency };
  chip?:
    | { kind: 'buy-wait'; instrumentName: string; qty: number } // '매수 대기 · S&P 500 ETF 2주'
    | { kind: 'sub-share' } // '1주 미만 대기'
    | { kind: 'withdraw-wait'; until: string }
    | { kind: 'first-buy' } // '첫 확인 때 매수'
    | { kind: 'buy-from'; at: string }; // '09:05부터 매수'
}

// ── `GET /api/home/breakdown?ledger=&period=` — 변동 분해 시트 ──
export interface Breakdown {
  from: string;
  to: string;
  start: number;
  deposit: number;
  withdrawal: number;
  market: number;
  dividend: number;
  fees: number;
  end: number;
  currency?: Currency; // ?account=만: 그 계좌 통화. 없으면 원화(전체)
  transfer?: number; // ?account=만: 환전으로 들어오고(+) 나간(−) 돈, 그 통화
}
// krw. 부호 있음: withdrawal·fees는 0 이하. deposit + withdrawal + market + dividend + fees = end - start(market이 반올림 나머지를 받는다).
// 'all'(기록 30거래일 미만이면 항상 'all')은 from = 시작일, start = 시작 금액이다. 시작 금액은 deposit에 넣지 않는다.
// ?account=kr|us: 그 계좌를 그 통화로. deposit + withdrawal + transfer + market + dividend + fees = end − start.
// 'all'의 start는 한국 계좌가 시작 금액, 미국 계좌가 0. market은 그 계좌 시세 변동(환율 없음)

// ── `GET /api/plan?ledger=&drift=` — SCR-PLAN ──
export interface PlanResponse {
  ledger: Ledger;
  example: boolean;
  ruleShares: Array<{ rule: RuleRef; pct: number }> | null; // 0이 아닌 규칙이 2개 이상일 때
  rules: RuleCard[];
  schedule: {
    now: { ruleId: string; status: RuleStatus; stages: Stage[] } | null;
    items: ScheduleItem[];
  };
  drift: {
    periods: Array<'3m' | '1y' | 'all'> | null; // 30거래일 미만이면 null('[시작일]부터')
    period: '3m' | '1y' | 'all';
    since: string;
    lines: Array<{ ruleId: string; points: Array<{ date: string; value: number | null }> }>; // pp1, null = 시세 대기 구간
    staleFrom: string | null; // '10/05부터 시세 대기'
    events: Array<{ date: string; kind: EventKind; ruleId: string | null }>;
    // 규칙의 리밸런싱은 그 규칙 선 위에(ruleId), 시작·실전 켬·끔은 장부 전체의 사건이라 ruleId null. AI 규칙은 선이 없어 여기 없다
    empty: null | 'second-day';
    mix?: true; // 실전 장부만(D47): 선이 원화·달러 비율의 벗어남 |한국 − 목표|이고 띠는 환전 제안의 문턱
  };
}
export interface RuleCard {
  rule: RuleRef;
  share: { pct: number; target: number | null };
  status: RuleStatus;
  next: NextAction;
  gauge: Gauge;
  rows: Array<{
    instrument: Instrument;
    weight: number | null; // pct1, null = '—'(시세 대기)
    target: number; // pct1
    toThreshold: number | null; // pp1. 실전 장부는 null(D47: 통화 사이로 리밸런싱하지 않는다)
    // AI 규칙(sell-condition 게이지): 팔 조건까지
    progress?: number;
    metric?: MetricRef;
    margin?: Margin;
  }>;
  basisLine: {
    pendingBuyIncluded: boolean; // '매수 대기 달러 포함'
    fxRate: number | null;
    fxAt: string | null;
    withdrawExcluded: boolean; // '출금 대기 현금 제외'
    staleMarket: Market | null;
    staleBasisDate: string | null; // '미국 시세 10/02 기준이라 계산 안 함'
    metricTableAt?: string | null; // AI 규칙: '지표 표 10/8'(지표 표가 마지막으로 바뀐 날, YYYY-MM-DD)
  };
  vsIndex?: { since: string; points: Array<{ date: string; value: number | null }> } | null;
  // AI 규칙: '지수 대비 · [since]부터'(pp1). 종목마다 고른 날부터 같은 시장 지수 대비 초과 수익의 평균(채점과 같은 계산, 판 종목은 판 날에 고정)
  fxSuggestion?: FxSuggestion | null;
  // 실전 장부의 지수 반반 카드에만 키가 있다(D47). null = 띠 안(또는 시세·환율이 낡아 계산 안 함)
}

// 실전 장부는 넣은 돈 그대로 굴린다(D47): 원화는 한국 종목, 달러는 미국 종목, 환전하지 않음.
// 원화·달러가 목표에서 띠보다 멀면 '약 X원을 달러로 바꾸면 50:50'. 할 일이 아니고 아무것도 막지 않는다.
export interface FxSuggestion {
  direction: 'krw-usd' | 'usd-krw'; // krw-usd = 한국이 많음: 원을 달러로
  krw: number; // krw. 바꿀 원(krw-usd) 또는 받을 원(usd-krw), 1,000원 단위
  usd: number; // usd. 받을 달러 또는 바꿀 달러
  rate: number; // rate. 계산에 쓴 환율
  now: { kr: number; us: number }; // pct1, 합 100.0: 규칙 돈의 지금 비율(현금 포함, 출금 대기 제외)
  target: { kr: number; us: number }; // pct1: 규칙 목표(50 · 50)
}
// 새로 들어온 돈은 다음 거래일부터(D48): 주인이 오늘(KST) 넣은 돈·주인이 한 환전으로 들어온 돈
export interface NewMoneyWait {
  krw: number; // krw. 0 = 없음
  usd: number; // usd. 0 = 없음
  from: string; // 쓰기 시작하는 확인(다음 평일 08:30)
}
export interface LiveCash {
  // 실전이 켜져 있을 때 모드·작동 화면에(할 일이 아님)
  newMoney: NewMoneyWait | null;
  fxSuggestion: FxSuggestion | null;
}
export type ScheduleItem =
  // ruleId는 한 규칙의 항목에만 있다. 확인·휴장·현금 항목은 장부 전체의 것이다
  | { kind: 'next-check'; at: string }
  | { kind: 'holiday'; date: string; markets: Market[] }
  | { kind: 'retry'; at: string; market: Market; side: Side; ruleId: string } // 다시 낼 주문의 규칙
  | { kind: 'sub-share-cash'; krw: number }
  | { kind: 'withdraw-wait'; krw: number; until: string }
  | { kind: 'new-cash'; krw: number } // 다음 확인이 쓸 새 현금('새로 들어온 돈'은 빼고)
  | ({ kind: 'new-money-wait' } & NewMoneyWait) // 실전(D48): '새로 들어온 돈 · 다음 거래일 08:30부터 써요'
  | { kind: 'first-check'; at: string }
  | { kind: 'monthly-review'; at: string; ruleId: string } // AI 규칙: 매달 1일 08:30(점검은 전날 22:00부터 돌아 그 확인 전에 끝난다)
  | { kind: 'discovery'; at: string; ruleId: string } // AI 규칙: 4·6·9·12월 1일 08:30
  | { kind: 'earnings'; date: string; instrument: Instrument; ruleId: string }; // AI 규칙. 실적 발표일 자료원이 없어 아직 보내지 않는다

// ── `GET /api/history?ledger=&year=` — SCR-HISTORY ──
export interface HistoryResponse {
  ledger: Ledger;
  example: boolean;
  year: number;
  years: number[];
  trend: {
    since: string;
    basis: Basis;
    total: number;
    pnl: { amount: number; pct: number | null } | null;
    series: Array<{ date: string; value: number }>;
    events: Array<{ date: string; kind: EventKind }>;
  };
  tiles: {
    rebalances: { count: number; partialFailed: number; inProgress: number };
    fees: { krw: number }; // '세금 미포함'
    checks: { count: number; failed: number };
  };
  calendar: Array<{ date: string; state: CalendarState }>; // 평일만
  filters: {
    total: number;
    rules: Array<{ rule: RuleRef; count: number }>; // 규칙의 리밸런싱 + 그 규칙 종목의 배당. AI 규칙은 그 규칙의 계획 + AI 판단 사건
    kinds: Array<{
      kind: 'rebalance' | 'deposit' | 'withdrawal' | 'dividend' | 'failed' | 'ai';
      count: number;
    }>; // 'ai'는 AI 규칙이 있을 때만
  };
  months: Array<{ month: string; change: number; events: HistoryEvent[] }>; // 최신순, 월 변동의 합 = 손익
  offPeriods: Array<{ from: string; to: string }>;
}
export interface HistoryEvent {
  date: string;
  kind: EventKind;
  rule?: RuleRef; // 리밸런싱, 그리고 규칙 종목의 배당('지수 반반 (KOSPI200 ETF)'). AI 판단 사건은 AI 규칙
  stagesMini?: Array<'done' | 'pending' | 'failed'>; // 리밸런싱, 그리고 시작(첫 매수). fill·fees도 같다
  weightsMini?: { before: number[]; after: number[]; target: number[] }; // target = 목표 눈금(pct1). AI 규칙은 빈 배열
  pending?: { side: Side; at: string }; // 리밸런싱 중: 기다리는 단계와 그 시각('매수 22:30')
  fill?: 'paper' | 'live';
  deviation?: number; // '2.3%p 벗어남'
  fees?: number;
  amount?: number; // 시작·입출금·배당(krw. 달러 배당은 받은 날 환율로 원화)
  instrument?: Instrument; // 배당
  retry?: { date: string; filled: boolean }; // '9/15 다시 · 체결'
  failureReason?: 'no-quote' | 'broker-rejected' | 'other';
  recoveredOn?: string; // 확인 실패 → '9/10 정상'
  resolvedOn?: string; // 직접 할 일을 처리했다고 닫은 날(일부 실패·확인 실패) → '10/9 직접 처리'
  treatment?: 'pnl-excluded' | 'income' | 'invest-next-check' | 'withdraw-wait';
  dayChange: number | null;
  dayTotal: number;
}

// ── `GET /api/day/{date}?ledger=` — SCR-DAY ──
export interface DayResponse {
  date: string;
  ledger: Ledger;
  example: boolean;
  prev: string | null;
  next: string | null; // 이전·다음 사건 날짜
  total: number;
  change: { amount: number; pct: number } | null;
  events: DayEvent[];
  check: {
    at: string | null; // null = 주말·확인 없음
    result:
      | 'rebalance'
      | 'in-range'
      | 'partial-failed'
      | 'failed'
      | 'holiday'
      | 'quote-wait'
      | 'weekend'
      | 'in-progress'
      | 'withdraw-wait'
      | 'no-run'; // no-run = 평일인데 확인 기록이 없음(기록 전·작업 안 돎)
    holidayMarkets?: Market[];
    band: { threshold: number; before: number | null; after: number | null } | null; // pp1
    ruleId?: string;
    rule?: RuleRef; // 확인한 규칙(이름은 rule)
    instrument?: Instrument;
    weight?: number;
    toThreshold?: number;
    over?: number;
    failure?: { reason: 'no-quote' | 'other'; recoveredOn?: string }; // result 'failed': 코드와 날짜('시세 응답 없음 · 9/10 정상')
  };
  basis: Basis;
}
export type DayEvent =
  | {
      kind: 'rebalance' | 'partial-failed' | 'in-progress';
      rule: RuleRef;
      stagesMini: Array<'done' | 'pending' | 'failed'>;
      weights: {
        instruments: Instrument[];
        before: number[];
        after: number[];
        target: number[];
        threshold: number;
      };
      stages: Stage[];
      feesKrw: number;
    }
  | {
      kind: 'deposit' | 'withdrawal' | 'dividend' | 'start';
      krw: number;
      treatment: 'pnl-excluded' | 'income' | 'invest-next-check' | 'withdraw-wait';
      until?: string;
      instrument?: Instrument;
      stages?: Stage[];
      feesKrw?: number;
    } // start는 첫 매수의 단계·수수료를 같이 싣는다
  | { kind: 'live-on' | 'live-off'; at: string }
  | {
      kind: 'ai-check' | 'ai-sell' | 'ai-buy' | 'monthly-review' | 'discovery';
      rule: RuleRef;
      judgment: AiJudgment;
    }; // 2단계
export interface AiJudgment {
  at: string;
  trigger: 'shock' | 'filing' | 'condition' | 'monthly' | 'discovery' | 'buy-price';
  instrument?: Instrument; // 판단한 종목(바꾸기는 살 종목)
  model: 'haiku' | 'sonnet' | 'opus';
  tokens: number;
  verdict: 'hold' | 'weaken' | 'invalidated' | 'buy' | 'skip';
  votes?: Array<'hold' | 'weaken' | 'invalidated' | 'buy' | 'skip' | 'switch' | 'keep'>; // 두 번 묻는 판단의 두 답(팔기 확인, 사기 확인, 바꾸기)
  action: 'none' | 'sell' | 'buy' | 'switch';
  input: JudgmentItem[]; // '입력' 줄: 화면이 항목마다 말을 짓고 순서대로 ' · '로 잇는다
  output: JudgmentItem[]; // '출력' 줄. verdict·votes·action은 위 칸에 있어 되풀이하지 않는다(비면 줄을 숨긴다)
}
export type JudgmentItem =
  | { key: 'instrument' | 'sold' | 'bought'; instrument: Instrument } // 판단한 종목 · 바꾸기의 팔 종목 · 살 종목
  | { key: 'shock'; date: string; value: number } // 급락한 날, 그날 지수 대비 수익률(%, 소수 1자리)
  | { key: 'condition'; value: number } // 걸린 반증 조건 번호(1부터)
  | { key: 'filing'; date: string } // 걸린 공시의 접수일
  | { key: 'review'; value: 'weaken' | 'invalidated'; months?: number } // 월 점검이 넘긴 판정(약화면 몇 달째)
  | { key: 'month'; value: string } // 'YYYY-MM'
  | { key: 'cost'; value: number } // 바꾸기 비용(바꾸는 금액 대비 %, 소수 2자리)
  | {
      key:
        | 'filings'
        | 'news'
        | 'picks'
        | 'held'
        | 'candidates'
        | 'checks'
        | 'hold'
        | 'weaken'
        | 'invalidated'
        | 'rewritten'
        | 'new-picks'
        | 'expired';
      value: number;
    } // 수
  | { key: 'slot-full' }; // 사기 확인: 자리가 없어 바꾸기 확인으로 넘김
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

// ── `GET /api/rules` · `GET /api/rules/{id}?lane=` — SCR-RULES ──
export interface RulesListResponse {
  rules: Array<{
    rule: RuleRef;
    share: { pct: number; target: number | null };
    status: RuleStatus;
    example: boolean;
  }>; // example = 목록 머리의 '예시' 칩
}
export interface RuleDetailResponse {
  rule: RuleRef;
  share: { pct: number; target: number | null };
  status: RuleStatus;
  example: boolean;
  stale: Array<'kr-quotes' | 'us-quotes' | 'fx'>; // 마지막 확인 때 낡았던 자료(작동 화면의 출처 id). 비어 있으면 '낡음' 없음
  display: TilesDisplay | FlowDisplay;
}
export interface TilesDisplay {
  // 고정 규칙: 타일 6칸
  kind: 'tiles';
  what: { instruments: Instrument[]; weights: number[]; basis: 'krw' };
  when: { time: string; days: 'weekdays'; tz: 'KST' };
  condition: {
    threshold: number;
    targetEach: number[];
    deviation: { now: number | null; atCheck: number | null };
    // pp1. now = 지금 가장 큰 벗어남(빈 점, 시세 대기면 null), atCheck = 오늘 08:30 확인 때 값(주황 점, 오늘 확인이 없거나 보유가 없으면 null)
  };
  action: { stages: Array<'sell' | 'fx' | 'buy'> };
  measured: {
    median: number;
    worst: number;
    badYear: number;
    period: string;
    afterTax: boolean;
    source: string;
  } | null; // 측정되지 않으면 null(그리지 않음)
  now: { status: RuleStatus; stages: Stage[] | null; nextCheckAt: string };
  mix?: true;
  // 실전 장부만(D47 넣은 돈 그대로): condition.deviation은 원화·달러 비율(한국 − 목표, atCheck는 null)이고
  // 띠를 넘으면 '환전 제안'(정보). action은 통화마다 그 통화 종목을 산다(실전 stages ['buy'])
}
export interface FlowDisplay {
  // AI 규칙: 흐름 카드(D34)
  kind: 'flow';
  lanes: Array<{
    id: string;
    label: { kind: 'daily' | 'earnings' | 'monthly' | 'quarterly'; time?: string };
  }>;
  lane: string; // 고른 흐름
  nodes: Array<{
    id: string;
    type:
      | 'start'
      | 'stock'
      | 'data'
      | 'ai'
      | 'weight'
      | 'condition'
      | 'action'
      | 'exception'
      | 'result';
    col: number;
    row: number; // 3열 격자
    title: string;
    subtitle?: string; // 규칙 정의의 이름(데이터)
    fields?: Array<{ key: 'input' | 'ai' | 'output'; value: string }>;
    more?: number; // '외 N': 지금 칸이 보인 종목(최대 3) 밖의 수
    targets?: Array<{ instrument: Instrument; weight: number }>;
    // 비중 카드의 종목별 목표(pct1). 목표가 모두 같은 비중이면 보내지 않고 지금 칸의 kv targetEach로 준다(3년 발굴)
    now: NowBlock;
  }>;
  edges: Array<{
    from: string;
    to: string;
    label?: 'yes' | 'no-keep' | 'no' | 'no-wait';
    style: 'taken' | 'not-taken' | 'exception';
  }>; // no-wait = '아니오 · 후보로 대기'(분기 발굴)
}
export interface NowBlock {
  headKey: 'now' | 'now-check' | 'now-last-judgment' | 'now-month' | 'now-last'; // '지금', '지금 · 확인 08:30' …
  at?: string; // 머리의 시각·날짜. 시작 카드는 다음 실행 시각('다음 10/12 08:30'), 실적 흐름의 시작 카드는 마지막 실적 공시 날
  until?: string; // 'now-last'가 여러 날에 걸치면 끝 날('마지막 9/14~9/15', at = 첫날)
  // 머리 메모(자유 문장)는 없다. '8종목 중 상위 3', '15종목' 같은 말은 kv 행의 수로 주고 화면이 문장을 만든다
  rows: Array<
    | {
        kind: 'instrument';
        instrument: Instrument;
        weight?: number;
        ret?: number;
        progress?: number;
        margin?: Margin;
        period?: string;
      }
    // progress 0~100: 보유는 팔 조건까지(margin = 팔 조건까지 남은 것), 후보는 살 값까지(고른 날 가격 0 → 살 값 100,
    // margin { unit: 'pct' } = 살 값보다 몇 % 위). period = 실적 기간('2026Q3')
    | { kind: 'rank'; rank: number; instrument: Instrument; ret: number }
    | { kind: 'band'; value: number; threshold: number; instrument?: Instrument }
    | {
        kind: 'order';
        side: Side;
        text: string;
        status?: 'filled' | 'pending' | 'failed';
        at?: string;
        retried?: boolean;
      }
    // text = 종목 이름, 환전이면 방향 코드('krw-usd' | 'usd-krw'). 한 번 실패하고 다시 낸 주문은 retried true이고
    // status·at이 다시 낸 결과다('9/15 다시 · 체결'). 주문(Order) 자체는 실패한 날의 기록으로 남는다
    | { kind: 'status'; status: RuleStatus; at?: string }
    | { kind: 'kv'; key: string; value: string; note?: string } // 셋째 칸 note도 데이터(코드·수)다. 문장은 보내지 않는다
    | {
        kind: 'exceptions';
        items: Array<'holiday' | 'quote-wait' | 'withdraw-wait'>;
        active: boolean;
      }
  >;
}
// AI 규칙(3년 발굴)의 kv 키. value와 note는 날짜(YYYY-MM-DD)·수·이름·코드이고, 값이 없으면 '-'다:
//   krClose·usClose(value 종가일, note 출처 상태 'fresh'…), filings(value 마지막 공시 회사, note 새 공시 수),
//   metricTable(value 지표 표 날짜, note 지표가 있는 회사 수), hits(조건에 걸린 수), verdict(value 판정, note 계기),
//   judgments·sells·buys(이번 달 판단·팔기·사기 수), votes(마지막 두 번 확인, 'hold,invalidated'), metrics(뽑은 지표 수),
//   tokens, companies(지표 표의 회사 수), picks(보유 수), newFilings(30일 새 공시 수), hold·weaken·invalidated(그달 판정 수),
//   daysToNext(다음 발굴까지 날 수), lastDiscovery(마지막 발굴 날), candidates(후보 대기 수, '후보 대기 · 6'), targetEach(종목당 목표 pct1)

// ── `GET /api/health` — SCR-HEALTH ──
export interface HealthResponse {
  summary: {
    kind: 'ok' | 'check' | 'check-failed' | 'unknown' | 'before-first';
    // 'check' = 낡은 자료나 빨간 카드가 있음. 노란 카드만 있으면 'ok'('정상 · 할 일 1')
    sourcesTotal: number;
    staleCount: number;
    failCount: number;
    todoCount: number; // 직접 할 일 카드(action 'manual') 수: 노란 카드 전부와, 다시 시도가 끝나 사람을 기다리는 빨간 카드. 자동으로 다시 하는 카드는 세지 않는다
    lastCheckAt: string | null;
    nextCheckAt: string | null;
    lastSuccessAt?: string;
    retryAt?: string;
    firstCheckAt?: string;
  };
  todos: Array<{
    id: string;
    severity: 'red' | 'yellow';
    kind:
      | 'stale'
      | 'check-failed'
      | 'toss-expiring'
      | 'order-rejected'
      | 'order-failed'
      | 'cancel-failed'
      | 'push-undelivered'
      | 'ai-cli'
      | 'filings'
      | 'pin-failures'
      | 'toss-link'
      | 'broker-mismatch';
    // order-failed = 다시 시도까지 실패한 주문. order-rejected는 실전 브로커 거절(3단계)
    // toss-link·broker-mismatch: 실전 연결(3단계, autotrade/PHASE3.md 2.7)
    facts: Record<string, string | number>; // 화면 문구에 끼울 값. 종류마다 키가 정해져 있다(아래). 모르는 값은 키를 빼고 null을 넣지 않는다
    action: { kind: 'auto-retry'; at: string } | { kind: 'manual' };
    effect: 'orders-zero-live-blocked' | 'orders-and-reconcile-stop' | 'no-order-sent' | 'other';
  }>;
  sources: Array<{
    // 1단계는 kr-quotes·us-quotes·fx 셋만(없는 연결은 줄을 만들지 않는다)
    // 2단계: 3년 발굴의 몫이 0보다 크면 filings·ai-cli·metric-table을 더한다.
    //  filings: state는 DART·EDGAR 중 나쁜 쪽(점검 중이면 'maintenance', 응답 없음·키 없음·실패면 'stale'),
    //           basis는 마지막으로 둘이 받은 날, extra { dart, edgar }: 'ok' | 'maintenance' | 'stale' | 'failed' | 'no-key' | 'unknown'
    //  ai-cli: state는 마지막 호출의 성공 여부(실행기가 CLI를 못 찾으면 'stale'), basis는 마지막 성공 호출의 모델, cadence 'event',
    //          extra { monthTokens, budget, enabled(0·1, 실행기가 마지막에 본 AUTOTRADE_AI_CALLS), due(기다리는 일감 수),
    //                  cli('ok' | 'missing' | 'unknown'), lastRunAt?(실행기가 마지막으로 돈 시각), running?·runningSince?(지금 묻는 일감 종류와 시작 시각) }
    //  metric-table: basis는 마지막으로 뽑은 날, cadence 'event'
    //  summary.staleCount는 'maintenance'도 센다
    id:
      | 'kr-quotes'
      | 'us-quotes'
      | 'fx'
      | 'toss-link'
      | 'toss-balance'
      | 'push-devices'
      | 'filings'
      | 'ai-cli'
      | 'metric-table';
    state: 'fresh' | 'late' | 'stale' | 'maintenance' | 'unknown';
    basis: string | null; // 종가일·환율 값·만료일 …
    receivedAt: string | null;
    cadence: 'daily' | 'per-check' | '90d' | 'event';
    age: number; // 주기 대비 나이(0~1 이상)
    extra?: Record<string, string | number>; // 기기 수, 남은 날 …, 시세는 { market: 'KR' | 'US' }
  }>;
  recent14: Array<{
    date: string;
    state: CalendarState;
    run?: { at: string; result: string; seconds: number; reason?: 'no-quote' | 'other' };
  }>; // 최근 14일 중 평일만(10칸). reason은 result 'failed'·'todo'일 때
  lastRun: { at: string; result: string; seconds: number; reason?: 'no-quote' | 'other' } | null; // reason은 코드다(문장 아님)
  devices: Array<{ name: string; lastDelivery: string | null; ok: boolean }>; // '알림 기기'를 펼친 목록(AccountResponse와 같은 모양). 3단계 전에는 빈 배열
  liveCash: LiveCash | null; // 실전이 켜져 있을 때만(D47·D48). 할 일이 아니고 수에 들어가지 않는다
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
//   pin-failures: 빨강, 직접 할 일 { since, count, lastAt?, closed: 0 | 1 }('PIN 실패 급증': 24시간에 틀린 PIN 10회부터
//           서버 unlock까지. since = 생긴 시각, count = 그때부터 센 틀린 PIN 수, closed 1 = 새 로그인이 닫힘(30회))
//   toss-link(3단계): { cause }(TossLinkCause). 실전이면 빨강, 아니면 노랑. 사람이 고칠 원인이면 직접 할 일, 아니면 다음 확인에 자동
//   broker-mismatch(3단계, 빨강·직접): { reason, instrument?, ledgerQty?, brokerQty?, count?, currency? }
//           reason 'positions'(보유 수량이 다름, 첫 종목과 다른 종목 수) | 'cash'(설명 안 되는 현금 변화, currency)
//           | 'external-fill' | 'fractional' | 'sleeves' | 'other' · 'order-unknown'(보낸 주문의 결과를 가를 수 없음: { reason, market, side })
// sources[].age(주기 대비 나이): 토스 연결(cadence '90d')은 지난 날 ÷ 90일(새로 연결한 날 0, 만료일에 1)
// 3단계 실제 연결: toss-link는 cadence 'per-check', age = 마지막 확인 뒤 ÷ 15분, basis = 주인이 알려 준 키 만료일(없으면 null),
//   receivedAt = 마지막 성공, extra { cause?(TossLinkCause), account?(끝 4자리), daysLeft? }. 만료 14일 안이면 'late'.
//   toss-balance는 basis 'match' | 'mismatch' | null, receivedAt = 마지막 대조

// ── `GET /api/mode` — SCR-MODE ──
export interface ModeResponse {
  mode: Ledger;
  live: { since: string; days: number } | null;
  liveOff: { from: string; to: string; offAt: string } | null; // '실전 9/1~10/7 · 16:12에 끔'
  twoLedgers: null | {
    since: string;
    series: Array<{
      date: string;
      live: number;
      paper: number;
      baseline: number;
      liveRet: number;
      paperRet: number;
      baselineRet: number;
    }>;
    endRet: { live: number; paper: number; baseline: number };
    breakdown: { fills: number; fees: number; other: number; total: number; valuedAt: string }; // pp, 합 = live - paper. valuedAt = 평가 시각('· 16:00')
  };
  performance: {
    since: string;
    checks: number;
    rebalances: number;
    failures: number;
    paperFills: number;
    ret: { pct: number; amount: number } | null; // 30거래일 미만이면 null('기간 짧음 · 30거래일부터 수익률')
    baselinePct: number | null;
  };
  preflight: null | Array<{
    id: 'health' | 'toss-link' | 'freshness' | 'push';
    ok: boolean;
    warn?: boolean;
    facts: Record<string, string | number>;
    sameCauseAs?: string;
  }>;
  // facts 키: health ok면 { lastCheckAt }, 아니면 { count, source }(원인 수와 첫 원인의 출처 id)
  //          toss-link ok면 { checkedAt, account }(계좌 끝 4자리), 아니면 { cause }(TossLinkCause). 주인이 키 만료일을 알려 줬으면 + { expiresAt, daysLeft }
  //          freshness ok면 { balanceAt, priceAt, fxAt }, 아니면 { source, basisDate } · push { devices, lastDelivery }
  preview:
    | null
    | {
        kind: 'ok';
        computedAt: string;
        hash: string;
        basis: { balanceAt: string; priceAt: string; fxRate: number; fxAt: string };
        current: Array<{
          label: 'krw-cash' | 'usd-cash' | 'holding';
          instrument?: Instrument;
          krw: number;
        }>;
        target: Array<{ ruleId: string; instrument: Instrument; pct: number }>;
        stages: Stage[]; // 매도·매수뿐(실전은 환전하지 않음, D47)
        outside: Array<{ instrument: Instrument; qty: number; approxKrw: number }>;
        newMoney: NewMoneyWait | null; // 다시 켤 때: 다음 확인 날 들어온 돈(그 확인이 쓰지 않음)
        fxSuggestion: FxSuggestion | null;
      }
    | { kind: 'not-computable'; at: string; cause: 'stale' | 'other' };
  cancelFailed: Order[] | null;
  cancelPending: Order[] | null; // 3단계: 끄기·계획 종료로 토스에 취소를 요청했고 다음 확인(5분 안)이 처리할 주문
  canTurnOn:
    | { ok: true }
    | { ok: false; cause: 'checks' | 'preview' | 'live-not-available' | 'cancel-pending' }; // cancel-pending = 지난 실전 주문의 취소가 안 끝남
  offPreview: null | {
    // 실전이 켜져 있을 때만: 끄면 취소될 주문과 계좌에 남는 현금(실전 끄기 모달)
    cancel: Order[]; // 실전 장부의 열린 계획에서 아직 대기 중인 주문
    cash: Array<{ currency: 'KRW'; krw: number } | { currency: 'USD'; usd: number; krw: number }>; // 0보다 큰 현금만. 달러의 krw는 지금 환율로
  };
  liveCash: LiveCash | null; // 실전이 켜져 있을 때만(D47·D48): 새로 들어온 돈과 환전 제안
}
// twoLedgers·preflight·preview는 실전이 생기는 3단계부터 채운다. 1·2단계는 null이다

// ── `GET /api/account` — SCR-ACCOUNT ──
export interface AccountResponse {
  thisDevice: {
    name: string;
    kind: 'iphone-app' | 'iphone-safari' | 'mac' | 'other';
    enteredAt: string;
  };
  // name·kind는 로그인 때의 User-Agent로 정한다. name은 '[시스템] · [브라우저]'('Mac · Chrome', 'iPhone · Safari').
  // UA에 'Safari/'가 없는 iPhone을 홈 화면 앱으로 보고 name은 'iPhone'만 준다(화면이 '· 홈 화면 앱'을 붙인다)
  notifications: {
    available: boolean; // 웹 푸시가 있나. 1·2단계는 false: 화면은 알림을 한 줄로 접는다
    vapidPublicKey?: string; // 3단계: 이 기기를 구독할 때 쓰는 공개키(available일 때만)
    thisDevice: {
      supported: boolean;
      reason?: 'safari-tab' | 'denied' | 'unsupported';
      subscribed: boolean;
    };
    events: Array<{ id: NotifyEvent; on: boolean; locked?: boolean }>;
    hideAmounts: boolean;
    savedAt: string | null;
    devices: Array<{ name: string; lastDelivery: string | null; ok: boolean }>;
    testResults: Array<{ device: string; ok: boolean; at: string }> | null;
  };
}
export type NotifyEvent =
  | 'check-failed' // 잠김(끌 수 없음), 일부 실패 포함
  | 'stale'
  | 'weekly-ok'
  | 'live-fill'
  | 'pin-failures'
  | 'toss-expiring' // 처음부터 켜짐(6개 중 나머지 5)
  | 'check-missed'
  | 'rebalance-notice'
  | 'cash-moves' // 처음부터 꺼짐
  | 'ai-sell'
  | 'ai-buy'
  | 'ai-review'; // 2단계(화면-맞춤.md 3절)

// ── 쓰기 · 오류 코드 (the contract's tables, transcribed) ──
// '오류 응답: {"error": "<code>", "detail"?: {...}}'. `pin`·`locked` carry remaining·until·scope
// at the top level, `preview-changed` carries `preview`.
export interface ApiErrorBody {
  error: string;
  detail?: Record<string, unknown>;
}

// 오류 코드 표: status · detail · when.
export type ApiErrorCode =
  | 'bad-request' // 400 {fields: string[]} — malformed body, query or path value
  | 'invalid-pin' // 400 — the PIN is not six digits
  | 'unknown-event' // 400 {event} — notification settings
  | 'locked-event' // 400 {event} — notification settings
  | 'session' // 403 — no session cookie, or it expired or was ended
  | 'origin' // 403 — a write (POST/PUT/DELETE) that did not come from this site
  | 'no-pin' // 403 — PIN (table above)
  | 'pin' // 403 — + remaining
  | 'locked' // 403 — + until, scope ('ip' | 'global'); scope 'hold' has since instead of until
  | 'current-pin' // 403
  | 'not-found' // 404 {rule}(규칙일 때) — unknown /api path or rule id
  | 'no-ledger' // 404 {ledger} — ?ledger= of a ledger that never started
  | 'method-not-allowed' // 405
  | 'blocked' // 409 {cause} — turning live on
  | 'preview-changed' // 409 — turning live on
  | 'in-progress' // 409 — turning live on
  | 'internal' // 500
  | 'not-implemented' // 501 {feature} — not built yet (push, stage 3)
  | 'db' // 503 — the database cannot be read
  | 'schema'; // 503 {stored, code} — the database is not at the code's schema (during a deploy)

// POST /api/auth/pin {pin} → 204 and the session cookie
export interface PinLoginRequest {
  pin: string;
}
export type PinLoginError =
  | { error: 'pin'; remaining: number }
  | { error: 'locked'; until: string; scope: 'ip' | 'global' }
  // 30 wrong PINs in 24 h: new logins closed until `python -m autotrade.jobs unlock` (no end time)
  | { error: 'locked'; scope: 'hold'; since: string }
  | { error: 'invalid-pin' } // 400, not counted as a failure
  | { error: 'no-pin' }; // no PIN yet (the server CLI sets the first one)
// POST /api/auth/logout → 204 (cookie cleared) · POST /api/auth/logout-others → 204

// POST /api/account/pin {current, next} → 204, every other session ends
export interface ChangePinRequest {
  current: string;
  next: string;
}
export type ChangePinError =
  | { error: 'current-pin' } // counted as a wrong PIN
  // Only this address's lock applies to a PIN change (the hourly cap and the hold do not).
  | { error: 'locked'; until: string; scope: 'ip' }
  | { error: 'invalid-pin' } // 400: `next` is not six digits
  | { error: 'session' }; // the 5th wrong current PIN on one session closes that session

// POST /api/mode/live
export interface LiveOnRequest {
  pin: string;
  confirm: true;
  previewHash: string;
}
export interface LiveOnResponse {
  mode: 'live';
}
export type LiveOnError =
  | { error: 'preview-changed'; preview: ModeResponse['preview'] } // re-computed amount moved ≥1%
  | { error: 'blocked'; detail: { cause: TurnOnBlockedCause } } // stage 1: always live-not-available
  | { error: 'in-progress' }; // duplicate request
/** `detail.cause` of 409 blocked; taken to be canTurnOn's cause (the table names only live-not-available). */
export type TurnOnBlockedCause = Extract<ModeResponse['canTurnOn'], { ok: false }>['cause'];
// POST /api/mode/paper (no PIN, session only)
export interface LiveOffResponse {
  mode: 'paper';
  cancelFailed: Order[];
  cancelPending: Order[]; // 3단계: 토스에 있어 다음 확인이 취소할 주문
}
// POST /api/mode/cancel-retry
export interface CancelRetryResponse {
  cancelFailed: Order[];
  cancelPending: Order[]; // 3단계: 다시 요청한 취소(다음 확인이 처리)
}
/** Why the Toss link cannot carry live orders now (toss-link preflight·todo·source). */
export type TossLinkCause =
  | 'never' // 아직 한 번도 확인 안 함
  | 'env-off' // 주문 실행기의 AUTOTRADE_LIVE_ORDERS가 없음(서버 cron 줄)
  | 'no-key' // 서버에 토스 키가 없음
  | 'auth' // 토스가 키를 받지 않음
  | 'ip' // 서버 IP가 허용 목록에 없음
  | 'account' // 계좌를 못 찾음
  | 'unreachable' // 토스 응답 없음
  | 'maintenance' // 토스 점검 중
  | 'error' // 토스 오류
  | 'old' // 마지막 확인이 15분보다 오래됨
  | 'conflict' // 다른 프로그램이 같은 키로 토큰을 받음(옛 quant)
  | 'not-tradable' // 규칙 종목이 지금 거래 안 됨
  | 'mismatch' // 잔고가 장부와 다름
  | 'expired'; // 주인이 알려 준 키 만료일이 지남

// PUT /api/account/notifications {events?: {[id]: boolean}, hideAmounts?} → 200 {savedAt}.
// Only what is sent changes; 400 unknown-event / locked-event (turning check-failed off).
export interface NotificationsRequest {
  events?: Partial<Record<NotifyEvent, boolean>>;
  hideAmounts?: boolean;
}
export interface NotificationsResponse {
  savedAt: string;
}
// POST /api/account/push {subscription} → 204. Stages 1·2: 501 {error:'not-implemented', detail:{feature:'push'}}
export interface PushSubscribeRequest {
  subscription: PushSubscriptionJSON;
}
// DELETE /api/account/push → 204, ends this device's subscription. Stages 1·2: 501 as above.
// POST /api/account/push/test → 200 {results}; stages 1·2: 501 as above.
// The item shape is not in the contract; assumed to match notifications.testResults.
export interface PushTestResponse {
  results: Array<{ device: string; ok: boolean; at: string }>;
}

// GET /api/healthz (no session) → 200 {ok: true, schema} · 503 {error:'db'}. Deploy health check.
export interface HealthzResponse {
  ok: true;
  schema: number;
}

// Query parameters of the read endpoints.
export type HomePeriod = Trend['period'];
export type DriftPeriod = PlanResponse['drift']['period'];
