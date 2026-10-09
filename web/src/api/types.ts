// Transcription of autotrade/CONTRACT.md (the API contract with the engine).
// Generated from the contract's ```ts blocks with `export` added; comments are the contract's.
// Re-transcribe when the contract changes (its '바뀐 것' section records each change).
// The types at the bottom transcribe the contract's '쓰기' and '오류 코드' tables.
// Contract snapshot: sha256 597a6a5a3e3f (2026-10-09, after the API session's change).
/* eslint-disable @typescript-eslint/array-type -- kept exactly as the contract writes it */

// ── 공통 타입 ──
export type Ledger = 'paper' | 'live';
export type Market = 'KR' | 'US' | 'COIN';
export type Currency = 'KRW' | 'USD';
export type Side = 'buy' | 'sell' | 'fx';

export interface Instrument {
  id: string; // 'KR:069500', 'US:SPLG'
  name: string; // 'KOSPI200 ETF', 'S&P 500 ETF'
  kind: 'etf' | 'stock' | 'coin';
  market: Market;
  currency: Currency;
  initials: string; // 로고 자리 이니셜(로고 없음). 이름의 글자·숫자 앞 두 개, 대문자('KO', 'SP', '삼성')
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
export type RuleStatus =
  | 'in-range'
  | 'scheduled'
  | 'in-progress'
  | 'partial-failed'
  | 'holiday'
  | 'quote-wait'
  | 'withdraw-wait'
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
  at: string; // 체결 시각 또는 예정 시각
  status: 'filled' | 'pending' | 'failed';
  fill?: 'paper' | 'live'; // '모의 체결' / '실제 체결'
  failure?: {
    reason: 'no-quote' | 'broker-rejected' | 'cancel-failed' | 'other';
    retryAt?: string;
    manual?: boolean;
  };
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
  | { kind: 'next-check'; at: string };

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
  planCard: PlanCard | null; // null이면 첫 확인 전 칩 줄만
  composition: Composition;
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
  }>;
  events: Array<{ date: string; kind: EventKind; count?: number }>; // 겹치면 count로 묶음 표식(kind는 그날 첫 사건)
  empty: null | 'before-first-check' | 'before-first-fill' | 'first-day';
}

export interface PlanCard {
  rule: RuleRef;
  share: { pct: number; target: number | null }; // '자산의 81.1% · 목표 80%'
  status: RuleStatus;
  next: NextAction;
  gauge: Gauge;
  stages: Stage[] | null; // 진행 중일 때만
  nextCheckAt: string;
  others: { count: number; status: RuleStatus } | null; // '외 n개 규칙 · [상태]'
}

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
      kind: 'sell-condition';
      needle: null | {
        // AI 규칙(D34)
        instrument: Instrument;
        progress: number;
        metric: string;
        marginText: string;
      };
    };

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
  cash?: { currency: Currency };
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
}
// krw. 부호 있음: withdrawal·fees는 0 이하. deposit + withdrawal + market + dividend + fees = end - start(market이 반올림 나머지를 받는다).
// 'all'(기록 30거래일 미만이면 항상 'all')은 from = 시작일, start = 시작 금액이다. 시작 금액은 deposit에 넣지 않는다.

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
    events: Array<{ date: string; kind: EventKind; ruleId: string }>;
    empty: null | 'second-day';
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
    toThreshold: number | null; // pp1
    // AI 규칙(sell-condition 게이지): 팔 조건까지
    progress?: number;
    metric?: string;
    marginText?: string;
  }>;
  basisLine: {
    pendingBuyIncluded: boolean; // '매수 대기 달러 포함'
    fxRate: number | null;
    fxAt: string | null;
    withdrawExcluded: boolean; // '출금 대기 현금 제외'
    staleMarket: Market | null;
    staleBasisDate: string | null; // '미국 시세 10/02 기준이라 계산 안 함'
  };
}
export type ScheduleItem =
  | { kind: 'next-check'; at: string }
  | { kind: 'holiday'; date: string; markets: Market[] }
  | { kind: 'retry'; at: string; market: Market; side: Side }
  | { kind: 'sub-share-cash'; krw: number }
  | { kind: 'withdraw-wait'; krw: number; until: string }
  | { kind: 'new-cash'; krw: number }
  | { kind: 'first-check'; at: string }
  | { kind: 'monthly-review'; at: string } // AI 규칙
  | { kind: 'discovery'; at: string } // AI 규칙
  | { kind: 'earnings'; date: string; instrument: Instrument }; // AI 규칙

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
    rules: Array<{ rule: RuleRef; count: number }>;
    kinds: Array<{
      kind: 'rebalance' | 'deposit' | 'withdrawal' | 'dividend' | 'failed' | 'ai';
      count: number;
    }>;
  };
  months: Array<{ month: string; change: number; events: HistoryEvent[] }>; // 최신순, 월 변동의 합 = 손익
  offPeriods: Array<{ from: string; to: string }>;
}
export interface HistoryEvent {
  date: string;
  kind: EventKind;
  rule?: RuleRef;
  stagesMini?: Array<'done' | 'pending' | 'failed'>; // 리밸런싱, 그리고 시작(첫 매수). fill·fees도 같다
  weightsMini?: { before: number[]; after: number[] };
  fill?: 'paper' | 'live';
  deviation?: number; // '2.3%p 벗어남'
  fees?: number;
  amount?: number; // 시작·입출금·배당
  instrument?: Instrument; // 배당
  retry?: { date: string; filled: boolean }; // '9/15 다시 · 체결'
  failureReason?: 'no-quote' | 'broker-rejected' | 'other';
  recoveredOn?: string; // 확인 실패 → '9/10 정상'
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
    instrument?: Instrument;
    weight?: number;
    toThreshold?: number;
    over?: number;
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
  instrument?: Instrument;
  model: 'haiku' | 'sonnet' | 'opus';
  tokens: number;
  verdict: 'hold' | 'weaken' | 'invalidated' | 'buy' | 'skip';
  votes?: Array<'hold' | 'weaken' | 'invalidated'>; // 두 번 확인
  inputSummary: string[];
  outputSummary: string[]; // 데이터 그대로(종목명·지표), 문장 아님
  action: 'none' | 'sell' | 'buy' | 'switch';
}

// ── `GET /api/rules` · `GET /api/rules/{id}?lane=` — SCR-RULES ──
export interface RulesListResponse {
  rules: Array<{
    rule: RuleRef;
    share: { pct: number; target: number | null };
    status: RuleStatus;
  }>;
}
export interface RuleDetailResponse {
  rule: RuleRef;
  share: { pct: number; target: number | null };
  status: RuleStatus;
  example: boolean;
  display: TilesDisplay | FlowDisplay;
}
export interface TilesDisplay {
  // 고정 규칙: 타일 6칸
  kind: 'tiles';
  what: { instruments: Instrument[]; weights: number[]; basis: 'krw' };
  when: { time: string; days: 'weekdays'; tz: 'KST' };
  condition: { threshold: number; targetEach: number[] };
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
    now: NowBlock;
  }>;
  edges: Array<{
    from: string;
    to: string;
    label?: 'yes' | 'no-keep' | 'no';
    style: 'taken' | 'not-taken' | 'exception';
  }>;
}
export interface NowBlock {
  headKey: 'now' | 'now-check' | 'now-last-judgment' | 'now-month' | 'now-last'; // '지금', '지금 · 확인 08:30' …
  at?: string;
  rows: Array<
    | {
        kind: 'instrument';
        instrument: Instrument;
        weight?: number;
        ret?: number;
        progress?: number;
        marginText?: string;
      }
    | { kind: 'rank'; rank: number; instrument: Instrument; ret: number }
    | { kind: 'band'; value: number; threshold: number; instrument?: Instrument }
    | {
        kind: 'order';
        side: Side;
        text: string;
        status?: 'filled' | 'pending' | 'failed';
        at?: string;
      }
    | { kind: 'status'; status: RuleStatus; at?: string }
    | { kind: 'kv'; key: string; value: string }
    | {
        kind: 'exceptions';
        items: Array<'holiday' | 'quote-wait' | 'withdraw-wait'>;
        active: boolean;
      }
  >;
}

// ── `GET /api/health` — SCR-HEALTH ──
export interface HealthResponse {
  summary: {
    kind: 'ok' | 'check' | 'check-failed' | 'unknown' | 'before-first';
    sourcesTotal: number;
    staleCount: number;
    todoCount: number;
    failCount: number;
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
      | 'filings';
    // order-failed = 다시 시도까지 실패한 주문(facts: date, market, side, reason). order-rejected는 실전 브로커 거절(3단계)
    facts: Record<string, string | number>; // 화면 문구에 끼울 값(시장, 날짜, 남은 날 …)
    action: { kind: 'auto-retry'; at: string } | { kind: 'manual' };
    effect: 'orders-zero-live-blocked' | 'orders-and-reconcile-stop' | 'no-order-sent' | 'other';
  }>;
  sources: Array<{
    // 1단계는 kr-quotes·us-quotes·fx 셋만(없는 연결은 줄을 만들지 않는다)
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
    run?: { at: string; result: string; seconds: number };
  }>; // 최근 14일 중 평일만(10칸)
  lastRun: { at: string; result: string; seconds: number; reason?: string } | null;
}

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
    breakdown: { fills: number; fees: number; other: number; total: number }; // pp, 합 = live - paper
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
        stages: Stage[];
        outside: Array<{ instrument: Instrument; qty: number; approxKrw: number }>;
      }
    | { kind: 'not-computable'; at: string; cause: 'stale' | 'other' };
  cancelFailed: Order[] | null;
  canTurnOn: { ok: true } | { ok: false; cause: 'checks' | 'preview' | 'live-not-available' }; // 1단계는 항상 live-not-available
}

// ── `GET /api/account` — SCR-ACCOUNT ──
export interface AccountResponse {
  thisDevice: {
    name: string;
    kind: 'iphone-app' | 'iphone-safari' | 'mac' | 'other';
    enteredAt: string;
  };
  // name·kind는 로그인 때의 User-Agent로 정한다(name 예: 'Mac · Chrome'). UA에 'Safari/'가 없는 iPhone을 홈 화면 앱으로 본다
  notifications: {
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
  | 'no-pin' // 403 — PIN (table above)
  | 'pin' // 403 — + remaining
  | 'locked' // 403 — + until, scope
  | 'current-pin' // 403
  | 'not-found' // 404 {rule}(규칙일 때) — unknown /api path or rule id
  | 'no-ledger' // 404 {ledger} — ?ledger= of a ledger that never started
  | 'method-not-allowed' // 405
  | 'blocked' // 409 {cause} — turning live on
  | 'preview-changed' // 409 — turning live on
  | 'in-progress' // 409 — turning live on
  | 'internal' // 500
  | 'not-implemented' // 501 {feature} — not in stage 1 (push)
  | 'db'; // 503 — /api/healthz only

// POST /api/auth/pin {pin} → 204 and the session cookie
export interface PinLoginRequest {
  pin: string;
}
export type PinLoginError =
  | { error: 'pin'; remaining: number }
  | { error: 'locked'; until: string; scope: 'ip' | 'global' }
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
  | { error: 'locked'; until: string; scope: 'ip' | 'global' }
  | { error: 'invalid-pin' }; // 400: `next` is not six digits

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
}
// POST /api/mode/cancel-retry
export interface CancelRetryResponse {
  cancelFailed: Order[];
}

// PUT /api/account/notifications {events?: {[id]: boolean}, hideAmounts?} → 200 {savedAt}.
// Only what is sent changes; 400 unknown-event / locked-event (turning check-failed off).
export interface NotificationsRequest {
  events?: Partial<Record<NotifyEvent, boolean>>;
  hideAmounts?: boolean;
}
export interface NotificationsResponse {
  savedAt: string;
}
// POST /api/account/push {subscription} → 204. Stage 1: 501 {error:'not-implemented', detail:{feature:'push'}}
export interface PushSubscribeRequest {
  subscription: PushSubscriptionJSON;
}
// POST /api/account/push/test → 200 {results}; stage 1: 501 as above.
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
