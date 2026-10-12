// The 예시 값표 world for the operations screens (작동 · 모의투자·실전 · 설정 · 입장): shells,
// data sources, the 14-day check grid, the paper performance, the turn-on preview and the
// two-ledger series. Bundles health.* · mode.* · account.* · pin.* import from here so the
// numbers stay the table's (§0, §1.5, §1.6, §2.2, §3).
import type {
  AccountResponse,
  CalendarState,
  HealthResponse,
  ModeResponse,
  NotifyEvent,
  Order,
  ShellResponse,
} from '../api/types';
import { paperDailySinceStart } from './charts';
import { BTC, INDEX_HALF, KOSPI200, MOMENTUM, NVDA, SAMSUNG, SP500, kst, ret2 } from './world';

/** 화면 시각 (예시-값표 §0). */
export const NOW = kst('2026-10-07', '16:10');
export const LAST_CHECK = kst('2026-10-07', '08:30');
export const NEXT_CHECK = kst('2026-10-08', '08:30');
/** The tick's last look at Toss (3단계, every 5 minutes). */
export const TOSS_CHECKED = kst('2026-10-07', '16:05');
const TOSS_LINK_FACTS = {
  checkedAt: TOSS_CHECKED,
  account: '8901',
  expiresAt: '2026-10-19',
  daysLeft: 12,
};

// ── /api/shell ───────────────────────────────────────────────────────────────

export function shell(overrides: Partial<ShellResponse> = {}): ShellResponse {
  return {
    now: NOW,
    mode: 'paper',
    modeChangedAt: null,
    liveSince: null,
    status: { kind: 'ok', lastCheckAt: LAST_CHECK },
    banner: null,
    ...overrides,
  };
}

/** 실전 켬 8/31(월) 21:10 (예시-값표 §2). */
export const LIVE_ON_AT = kst('2026-08-31', '21:10');

export const liveShell = (overrides: Partial<ShellResponse> = {}): ShellResponse =>
  shell({ mode: 'live', liveSince: LIVE_ON_AT, ...overrides });

/** 미국 시세 10/02 기준 · 2거래일째 (예시-값표 §3 시세 대기 · 작동 점검 1). */
export const staleShell = (overrides: Partial<ShellResponse> = {}): ShellResponse =>
  shell({
    status: { kind: 'check', count: 1 },
    banner: {
      kind: 'stale',
      market: 'US',
      basisDate: '2026-10-02',
      tradingDays: 2,
      link: 'health',
    },
    ...overrides,
  });

/** 403 session (no cookie): the client sends the page to /pin?next=. */
export const NO_SESSION = { $status: 403, $body: { error: 'session' } } as const;

// ── /api/health ──────────────────────────────────────────────────────────────

type Source = HealthResponse['sources'][number];
type Todo = HealthResponse['todos'][number];
type Day = HealthResponse['recent14'][number];

// Age is 'age relative to the cadence'; the screen draws the bar over 0–2 cadences (fresh zone
// up to 1, late up to 1.5). The values below put each fill where the Figma bars end
// (1:62685: 8% · 20% · 8% · 62% · 12% · 5% of the bar; the stale US bar 93.5%), except the Toss
// link: its age is the contract's days since connecting ÷ 90 (10/19 expiry, 12 days left on 10/7:
// 78 ÷ 90 = 0.87), which the screen draws with expiry at the late/stale edge (65%).
export const sources = {
  kr: {
    id: 'kr-quotes',
    state: 'fresh',
    basis: '2026-10-07',
    receivedAt: kst('2026-10-07', '16:00'),
    cadence: 'daily',
    age: 0.16,
    extra: { market: 'KR' },
  },
  us: {
    id: 'us-quotes',
    state: 'fresh',
    basis: '2026-10-06',
    receivedAt: kst('2026-10-07', '06:20'),
    cadence: 'daily',
    age: 0.4,
    extra: { market: 'US' },
  },
  fx: {
    id: 'fx',
    state: 'fresh',
    basis: '1382.4',
    receivedAt: kst('2026-10-07', '16:00'),
    cadence: 'daily',
    age: 0.16,
  },
  // 3단계: the tick's last good look at Toss (every 5 minutes); the key expiry is the one the
  // owner gave (AUTOTRADE_TOSS_KEY_EXPIRES), 12 days away, so the row reads 'late'.
  tossLink: {
    id: 'toss-link',
    state: 'late',
    basis: '2026-10-19',
    receivedAt: TOSS_CHECKED,
    cadence: 'per-check',
    age: 0.33,
    extra: { daysLeft: 12, account: '8901' },
  },
  tossBalance: {
    id: 'toss-balance',
    state: 'fresh',
    basis: 'match',
    receivedAt: LAST_CHECK,
    cadence: 'per-check',
    age: 0.24,
  },
  push: {
    id: 'push-devices',
    state: 'fresh',
    basis: null,
    receivedAt: kst('2026-10-07', '08:31'),
    cadence: 'event',
    age: 0.1,
    extra: { devices: 2 },
  },
} satisfies Record<string, Source>;

export const SIX_SOURCES: Source[] = [
  sources.kr,
  sources.us,
  sources.fx,
  sources.tossLink,
  sources.tossBalance,
  sources.push,
];

export const tossExpiringTodo: Todo = {
  id: 'toss-expiring',
  severity: 'yellow',
  kind: 'toss-expiring',
  facts: { expiresAt: '2026-10-19', daysLeft: 12 },
  action: { kind: 'manual' },
  effect: 'orders-and-reconcile-stop',
};

/** 9/24(목)~10/07(수), weekdays only (예시-값표 §1.5). Seconds are fixture values except 42. */
export function recent14(last: Partial<Record<string, Day>> = {}): Day[] {
  const day = (date: string, state: CalendarState, result: string, seconds: number): Day => ({
    date,
    state,
    run: { at: kst(date, '08:30'), result, seconds },
  });
  const days: Day[] = [
    day('2026-09-24', 'holiday-one', 'holiday', 9),
    day('2026-09-25', 'holiday-one', 'holiday', 8),
    day('2026-09-28', 'normal', 'in-range', 11),
    day('2026-09-29', 'normal', 'in-range', 12),
    day('2026-09-30', 'normal', 'in-range', 10),
    day('2026-10-01', 'normal', 'in-range', 11),
    day('2026-10-02', 'normal', 'in-range', 13),
    day('2026-10-05', 'holiday-one', 'holiday', 9),
    day('2026-10-06', 'normal', 'in-range', 12),
    day('2026-10-07', 'in-progress', 'rebalance', 42),
  ];
  return days.map((d) => last[d.date] ?? d);
}

export const LAST_RUN: NonNullable<HealthResponse['lastRun']> = {
  at: LAST_CHECK,
  result: 'rebalance',
  seconds: 42,
};

/** SCR-HEALTH.todo: 정상 · 할 일 1 (토스 연결 만료 예정). */
export function healthTodo(): HealthResponse {
  return {
    summary: {
      kind: 'ok',
      sourcesTotal: 6,
      staleCount: 0,
      todoCount: 1,
      failCount: 0,
      lastCheckAt: LAST_CHECK,
      nextCheckAt: NEXT_CHECK,
      lastSuccessAt: LAST_CHECK,
    },
    todos: [tossExpiringTodo],
    sources: SIX_SOURCES,
    recent14: recent14(),
    lastRun: LAST_RUN,
    devices: PUSH_DEVICES,
  };
}

// ── /api/account ─────────────────────────────────────────────────────────────

const DEFAULT_EVENTS: { id: NotifyEvent; on: boolean; locked?: boolean }[] = [
  { id: 'check-failed', on: true, locked: true },
  { id: 'stale', on: true },
  { id: 'weekly-ok', on: true },
  { id: 'live-fill', on: true },
  { id: 'pin-failures', on: true },
  { id: 'toss-expiring', on: true },
  { id: 'check-missed', on: false },
  { id: 'rebalance-notice', on: false },
  { id: 'cash-moves', on: false },
];

export function events(): { id: NotifyEvent; on: boolean; locked?: boolean }[] {
  return DEFAULT_EVENTS.map((e) => ({ ...e }));
}

export const PUSH_DEVICES: AccountResponse['notifications']['devices'] = [
  { name: 'iPhone · 홈 화면 앱', lastDelivery: kst('2026-10-07', '08:31'), ok: true },
  { name: 'MacBook · Chrome', lastDelivery: kst('2026-10-06', '16:01'), ok: true },
];

/** SCR-ACCOUNT 기본 (1:39291): this iPhone home-screen app, 2 subscribed devices. */
export function account(): AccountResponse {
  return {
    // The server names the device from the User-Agent; a home-screen app has no browser token.
    thisDevice: { name: 'iPhone', kind: 'iphone-app', enteredAt: kst('2026-10-01', '08:12') },
    notifications: {
      available: true,
      vapidPublicKey: 'BFixtureVapidPublicKey',
      thisDevice: { supported: true, subscribed: true },
      events: events(),
      hideAmounts: false,
      savedAt: kst('2026-10-07', '15:38'),
      devices: PUSH_DEVICES,
      testResults: [
        { device: 'iPhone', ok: true, at: kst('2026-10-07', '15:40') },
        { device: 'MacBook · Chrome', ok: true, at: kst('2026-10-07', '15:40') },
      ],
    },
  };
}

// ── /api/mode ────────────────────────────────────────────────────────────────

/** 모의투자 성적 (예시-값표 §1.4 끝): 71 · 3 · 1 · 13, +2.44% · +243,800원, 기준선 +3.59%. */
export const PERFORMANCE: ModeResponse['performance'] = {
  since: '2026-07-01',
  checks: 71,
  rebalances: 3,
  failures: 1,
  paperFills: 13,
  ret: { pct: 2.44, amount: 243_800 },
  baselinePct: 3.59,
};

/** 기록 30거래일 미만 변형(7/16 가정): 12 · 0 · 0 · 6, 수익률 없음. */
export const PERFORMANCE_SHORT: ModeResponse['performance'] = {
  since: '2026-07-01',
  checks: 12,
  rebalances: 0,
  failures: 0,
  paperFills: 6,
  ret: null,
  baselinePct: null,
};

export const PREFLIGHT_OK: NonNullable<ModeResponse['preflight']> = [
  { id: 'health', ok: true, facts: { lastCheckAt: LAST_CHECK } },
  { id: 'toss-link', ok: true, facts: TOSS_LINK_FACTS },
  {
    id: 'freshness',
    ok: true,
    facts: {
      balanceAt: LAST_CHECK,
      priceAt: kst('2026-10-07', '16:00'),
      fxAt: kst('2026-10-07', '16:00'),
    },
  },
  { id: 'push', ok: true, facts: { devices: 2, lastDelivery: kst('2026-10-07', '08:31') } },
];

/** SCR-MODE.blocked (1:38336): one cause, US quotes stale since 10/02. */
export const PREFLIGHT_BLOCKED: NonNullable<ModeResponse['preflight']> = [
  { id: 'health', ok: false, facts: { count: 1, source: 'us-quotes' } },
  { id: 'toss-link', ok: true, facts: TOSS_LINK_FACTS },
  {
    id: 'freshness',
    ok: false,
    facts: { source: 'us-quotes', basisDate: '2026-10-02' },
    sameCauseAs: 'health',
  },
  { id: 'push', ok: true, facts: { devices: 2, lastDelivery: kst('2026-10-07', '08:31') } },
];

const tomorrow = (time: string) => kst('2026-10-08', time);

function previewBuy(id: string, inst: typeof KOSPI200, qty: number, price: number): Order {
  const kr = inst.currency === 'KRW';
  return {
    id,
    market: inst.market,
    side: 'buy',
    instrument: inst,
    qty,
    price,
    approx: true,
    ...(kr
      ? { amountKrw: Math.round(qty * price) }
      : { amountUsd: Math.round(qty * price * 100) / 100 }),
    at: tomorrow(kr ? '09:05' : '22:30'),
    status: 'pending',
  };
}

/**
 * 첫 주문 미리보기 (예시-값표 §1.6, 10/07 16:00): 원화 현금 10,000,000원 → 환전 약 4,705,000원 →
 * 약 $3,403 (1,382.4원) · 매수 KOSPI200 ETF 110주 · 삼성전자 14주 (4,775,700원) / S&P 500 ETF 46주
 * · NVDA 3주 ($3,399.60 → 약 $3,400). $3,403 = the US buys plus their 0.1% fee. BTC is outside Toss.
 */
export const PREVIEW_OK: Extract<NonNullable<ModeResponse['preview']>, { kind: 'ok' }> = {
  kind: 'ok',
  computedAt: kst('2026-10-07', '16:00'),
  hash: 'preview-20261007-1600',
  basis: {
    balanceAt: LAST_CHECK,
    priceAt: kst('2026-10-07', '16:00'),
    fxRate: 1382.4,
    fxAt: kst('2026-10-07', '16:00'),
  },
  current: [{ label: 'krw-cash', krw: 10_000_000 }],
  target: [
    { ruleId: INDEX_HALF.id, instrument: KOSPI200, pct: 40 },
    { ruleId: INDEX_HALF.id, instrument: SP500, pct: 40 },
    { ruleId: MOMENTUM.id, instrument: SAMSUNG, pct: 8.4 },
    { ruleId: MOMENTUM.id, instrument: NVDA, pct: 8 },
    { ruleId: MOMENTUM.id, instrument: BTC, pct: 3.6 },
  ],
  stages: [
    {
      kind: 'fx',
      status: 'pending',
      at: tomorrow('09:10'),
      orders: [
        {
          id: 'preview-fx-1',
          market: 'KR',
          side: 'fx',
          direction: 'krw-usd',
          fx: { krw: 4_705_000, usd: 3403, rate: 1382.4 },
          approx: true,
          at: tomorrow('09:10'),
          status: 'pending',
        },
      ],
    },
    {
      kind: 'buy',
      status: 'pending',
      at: tomorrow('09:05'),
      orders: [
        previewBuy('preview-buy-1', KOSPI200, 110, 36_250),
        previewBuy('preview-buy-2', SAMSUNG, 14, 56_300),
        previewBuy('preview-buy-3', SP500, 46, 62.4),
        previewBuy('preview-buy-4', NVDA, 3, 176.4),
      ],
    },
  ],
  outside: [{ instrument: BTC, qty: 0.0027, approxKrw: 355_000 }],
};

/** SCR-MODE paper (1:37871 · 1:38094): checks pass, preview computed, ready to turn on. */
export function modePaper(overrides: Partial<ModeResponse> = {}): ModeResponse {
  return {
    mode: 'paper',
    live: null,
    liveOff: null,
    twoLedgers: null,
    performance: PERFORMANCE,
    preflight: PREFLIGHT_OK,
    preview: PREVIEW_OK,
    cancelFailed: null,
    cancelPending: null,
    canTurnOn: { ok: true },
    offPreview: null,
    ...overrides,
  };
}

// 두 장부 (9/1부터): the paper line is the paper ledger (charts.ts) against its 8/31 close; the
// live and baseline lines are read from the Figma two-ledger chart (1:64317), rounded to 100원
// (the same line SCR-HOME · 실전 draws), and end on the table's values (실전 10,112,670원 +1.13% ·
// 손대지 않았을 때 10,175,000원 +1.75%).
const LIVE_START = 10_000_000;
const PAPER_AT_LIVE_START = 10_114_800; // paper ledger, 8/31 close (예시-값표 §1.2 월말 값)
const LIVE_AND_BASELINE: readonly (readonly [string, number, number])[] = [
  ['2026-09-01', 9_994_400, 10_000_000],
  ['2026-09-02', 10_006_500, 10_013_300],
  ['2026-09-03', 10_005_400, 10_013_200],
  ['2026-09-04', 10_012_000, 10_021_000],
  ['2026-09-07', 9_998_100, 10_009_500],
  ['2026-09-08', 9_987_600, 9_999_900],
  ['2026-09-09', 9_985_000, 9_998_000],
  ['2026-09-10', 9_984_900, 9_999_100],
  ['2026-09-11', 9_984_100, 9_999_500],
  ['2026-09-14', 9_976_000, 9_995_000],
  ['2026-09-15', 9_986_100, 10_006_800],
  ['2026-09-16', 9_995_200, 10_017_700],
  ['2026-09-17', 9_994_200, 10_018_400],
  ['2026-09-18', 10_004_000, 10_030_000],
  ['2026-09-21', 10_019_000, 10_047_000],
  ['2026-09-22', 10_018_900, 10_047_600],
  ['2026-09-23', 10_022_200, 10_051_500],
  ['2026-09-24', 10_031_000, 10_061_000],
  ['2026-09-25', 10_039_400, 10_070_700],
  ['2026-09-28', 10_048_800, 10_084_100],
  ['2026-09-29', 10_058_000, 10_094_600],
  ['2026-09-30', 10_060_000, 10_098_000],
  ['2026-10-01', 10_064_600, 10_104_600],
  ['2026-10-02', 10_079_000, 10_121_000],
  ['2026-10-05', 10_095_100, 10_150_600],
  ['2026-10-06', 10_098_000, 10_158_000],
  ['2026-10-07', 10_112_670, 10_175_000],
];

export const TWO_LEDGERS: NonNullable<ModeResponse['twoLedgers']> = {
  since: '2026-09-01',
  series: LIVE_AND_BASELINE.map(([date, live, baseline]) => {
    const paper = paperDailySinceStart.find((p) => p.date === date)?.value ?? null;
    if (paper === null) throw new Error(`paper ledger has no value on ${date}`);
    return {
      date,
      live,
      paper,
      baseline,
      liveRet: ret2(live, LIVE_START),
      paperRet: ret2(paper, PAPER_AT_LIVE_START),
      baselineRet: ret2(baseline, LIVE_START),
    };
  }),
  endRet: { live: 1.13, paper: 1.28, baseline: 1.75 },
  // 체결가 −0.02 · 실제 수수료 −0.06 · 기타 −0.07 → 합 −0.15%p = 1.13 − 1.28 (예시-값표 §2.2).
  breakdown: {
    fills: -0.02,
    fees: -0.06,
    other: -0.07,
    total: -0.15,
    valuedAt: kst('2026-10-07', '16:00'),
  },
};

/** SCR-MODE.live (1:38520): 실전 9/1부터 · 27일째. */
export function modeLive(overrides: Partial<ModeResponse> = {}): ModeResponse {
  return {
    mode: 'live',
    live: { since: '2026-09-01', days: 27 },
    liveOff: null,
    twoLedgers: TWO_LEDGERS,
    performance: PERFORMANCE,
    preflight: null,
    preview: null,
    cancelFailed: null,
    cancelPending: null,
    canTurnOn: { ok: true },
    offPreview: LIVE_OFF_PREVIEW,
    ...overrides,
  };
}

/** 10/7 실전 매수·미국 22:30 대기 S&P 500 ETF 2주 · 약 $124.80 (예시-값표 §2.2). */
export const LIVE_PENDING_BUY: Order = {
  id: 'live-20261007-buy-1',
  market: 'US',
  side: 'buy',
  instrument: SP500,
  qty: 2,
  price: 62.4,
  approx: true,
  amountUsd: 124.8,
  fee: { usd: 0.12 },
  at: kst('2026-10-07', '22:30'),
  status: 'pending',
};

/**
 * 실전 끄기 미리보기 (CONTRACT ModeResponse.offPreview): the 22:30 buy that gets cancelled and the
 * live account's cash (예시-값표 §2.2, 10/7 16:00: 원화 현금 85,964원 · 달러 현금 $125.67 =
 * 173,726원). The modal shows the 달러 line, the currency of the cancelled buy.
 */
export const LIVE_OFF_PREVIEW: NonNullable<ModeResponse['offPreview']> = {
  cancel: [LIVE_PENDING_BUY],
  cash: [
    { currency: 'KRW', krw: 85_964 },
    { currency: 'USD', usd: 125.67, krw: 173_726 },
  ],
};
