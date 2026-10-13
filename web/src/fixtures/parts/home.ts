// SCR-HOME responses of each 예시-값표 world. Bundles pick one and add the shell around it.
// Row %, group % and totals are the table's; where the table is silent (spec-only states:
// 휴장, 확인 실패) the numbers are derived from it and the assumption is written down.
import type {
  Breakdown,
  CompRow,
  Composition,
  HomePeriod,
  HomeResponse,
  NextAction,
  PlanCard,
  Trend,
} from '../../api/types';
import { paperDaily3m, paperDailySinceStart, untouchedDaily3m } from '../charts';
import {
  BTC,
  INDEX_HALF,
  KOSPI200,
  MOMENTUM,
  NVDA,
  SAMSUNG,
  SP500,
  START_CAPITAL,
  kst,
  ret2,
} from '../world';
import {
  BASIS_1007,
  BASIS_1008,
  BASIS_STALE,
  LIVE_BUY_1007,
  LIVE_BUY_1007_REJECTED,
  LIVE_FIRST_BUY,
  NEXT_QUOTE_WAIT_US,
  NEXT_RETRY_1008,
  NEXT_TODO_US_BUY,
  NEXT_US_BUY_1007,
  PAPER_BUY_1007,
  PAPER_BUY_1007_FAILED,
  PAPER_FX_1007,
  PAPER_SELL_1007,
  liveStages1007,
  nextCheck,
  stages1007,
} from './common';
import { liveDaily, liveUntouchedDaily } from './series';
import { paperAccounts } from './accounts';

type Series = Trend['series'];
interface Point {
  date: string;
  value: number | null;
}

/** Join a value line and its untouched line into trend points (ret against `base`). */
export function trendSeries(
  mine: readonly Point[],
  untouched: readonly Point[],
  base: number = START_CAPITAL,
): Series {
  const byDate = new Map(untouched.map((p) => [p.date, p.value]));
  return mine.flatMap((p) => {
    if (p.value === null) return [];
    const b = byDate.get(p.date) ?? null;
    return [
      {
        date: p.date,
        value: p.value,
        ret: ret2(p.value, base),
        baseline: b,
        baselineRet: b === null ? null : ret2(b, base),
      },
    ];
  });
}

/** Replace the values of some dates (variants that end on another total). */
function patch(points: readonly Point[], values: Record<string, number>): Point[] {
  return points.map((p) => (p.date in values ? { ...p, value: values[p.date] ?? null } : p));
}

// ── 모의투자 world (값표 §1) ─────────────────────────────────────────────────

/** §1.1 지금 (10/7 16:00 평가) — the 구성 list. */
export const PAPER_COMPOSITION: Composition = {
  groupBy: ['instrument', 'kind', 'country', 'currency', 'rule'],
  groups: [
    {
      key: INDEX_HALF.id,
      rule: INDEX_HALF,
      pct: 81.1,
      target: 80,
      rows: [
        {
          kind: 'holding',
          instrument: KOSPI200,
          pct: 40.7,
          krw: 4_168_750,
          pnlPct: 13.3,
          qty: 115,
          avgCost: { amount: 32_005, currency: 'KRW' },
        },
        {
          kind: 'holding',
          instrument: SP500,
          pct: 38.7,
          krw: 3_968_041,
          usd: 2_870.4,
          pnlPct: -6.0,
          qty: 46,
          avgCost: { amount: 65.94, currency: 'USD' },
        },
        {
          kind: 'cash',
          cash: { currency: 'USD', country: 'US' },
          pct: 1.7,
          krw: 175_510,
          usd: 126.96,
          chip: { kind: 'buy-wait', instrumentName: 'S&P 500 ETF', qty: 2 },
        },
      ],
    },
    {
      key: MOMENTUM.id,
      rule: MOMENTUM,
      pct: 18.3,
      target: 20,
      rows: [
        {
          kind: 'holding',
          instrument: SAMSUNG,
          pct: 7.7,
          krw: 788_200,
          pnlPct: 1.4,
          qty: 14,
          avgCost: { amount: 55_508, currency: 'KRW' },
        },
        {
          kind: 'holding',
          instrument: NVDA,
          pct: 7.1,
          krw: 731_566,
          usd: 529.2,
          pnlPct: 1.7,
          qty: 3,
          avgCost: { amount: 172.17, currency: 'USD' },
        },
        {
          kind: 'holding',
          instrument: BTC,
          pct: 3.5,
          krw: 355_185,
          pnlPct: -15.1,
          qty: 0.0027,
          avgCost: { amount: 154_930_000, currency: 'KRW' },
        },
      ],
    },
    {
      key: 'cash',
      label: 'cash',
      pct: 0.6,
      target: null,
      rows: [
        {
          kind: 'cash',
          cash: { currency: 'KRW', country: 'KR' },
          pct: 0.6,
          krw: 56_548,
          chip: { kind: 'sub-share' },
        },
      ],
    },
  ],
  pendingBar: null,
  outsideRules: null,
};

/** 3개월 (7/7–10/7) with the 1.4 events on the band. */
export function paperTrend(period: HomePeriod = '3m'): Trend {
  const events: Trend['events'] = [
    { date: '2026-08-21', kind: 'rebalance', kinds: ['rebalance'] },
    { date: '2026-09-14', kind: 'partial-failed', kinds: ['partial-failed'] },
    { date: '2026-09-30', kind: 'dividend', kinds: ['dividend'] },
    { date: '2026-10-07', kind: 'in-progress', kinds: ['in-progress'] },
  ];
  const three = trendSeries(paperDaily3m, untouchedDaily3m);
  if (period === '1m') {
    // 9/7–10/7: 10,243,800 − 10,105,400 (9/7) = +138,400 (+1.37%).
    return {
      periods: ['1m', '3m', '1y', 'all'],
      period,
      periodPnl: { amount: 138_400, pct: 1.37 },
      series: three.filter((p) => p.date >= '2026-09-07'),
      events: events.filter((e) => e.date >= '2026-09-07'),
      empty: null,
    };
  }
  if (period === '1y' || period === 'all') {
    // Since the start (7/1): the record is shorter than a year, so 1년 = 전체. The untouched
    // line before 7/7 is not in Figma; 7/1 starts at the start amount and joins the 3m line.
    const untouched: Point[] = [
      { date: '2026-07-01', value: START_CAPITAL },
      { date: '2026-07-02', value: 9_992_600 },
      { date: '2026-07-03', value: 9_985_300 },
      { date: '2026-07-06', value: 9_971_900 },
      ...untouchedDaily3m,
    ];
    return {
      periods: ['1m', '3m', '1y', 'all'],
      period,
      periodPnl: period === 'all' ? null : { amount: 243_800, pct: 2.44 },
      series: trendSeries(paperDailySinceStart, untouched),
      events: [{ date: '2026-07-01', kind: 'start', kinds: ['start'] }, ...events],
      empty: null,
    };
  }
  return {
    periods: ['1m', '3m', '1y', 'all'],
    period: '3m',
    periodPnl: { amount: 222_800, pct: 2.22 },
    series: three,
    events,
    empty: null,
  };
}

/** 변동 분해 of the 모의투자 world per period (sum of the bars = end − start). */
export function paperBreakdown(period: HomePeriod): Breakdown {
  if (period === '1m') {
    // Fees after 9/7: 9/14 8 · 9/15 27 · 10/7 27.
    return {
      from: '2026-09-07',
      to: '2026-10-07',
      start: 10_105_400,
      deposit: 0,
      withdrawal: 0,
      market: 122_219,
      dividend: 16_243,
      fees: -62,
      end: 10_243_800,
    };
  }
  if (period === '1y' || period === 'all') {
    // Since the start: fees 5,935 (§1.2 수수료 누계), dividend 16,243.
    return {
      from: '2026-07-01',
      to: '2026-10-07',
      start: START_CAPITAL,
      deposit: 0,
      withdrawal: 0,
      market: 233_492,
      dividend: 16_243,
      fees: -5_935,
      end: 10_243_800,
    };
  }
  // 3개월 (7/7–10/7). 값표 splits only the since-start PnL, so this split is derived:
  // dividend 9/30 16,243, fees after 7/7 206 + 8 + 27 + 27 = 268, market = the rest.
  return {
    from: '2026-07-07',
    to: '2026-10-07',
    start: 10_021_000,
    deposit: 0,
    withdrawal: 0,
    market: 206_825,
    dividend: 16_243,
    fees: -268,
    end: 10_243_800,
  };
}

const PAPER_PLAN_CARD: PlanCard = {
  rule: INDEX_HALF,
  share: { pct: 81.1, target: 80 },
  status: 'in-progress',
  next: NEXT_US_BUY_1007,
  gauge: {
    kind: 'drift',
    threshold: 2,
    needle: { instrument: KOSPI200, deviation: 0.2, toThreshold: 1.8 },
  },
  stages: stages1007(PAPER_SELL_1007, PAPER_FX_1007, PAPER_BUY_1007),
  nextCheckAt: kst('2026-10-08', '08:30'),
  others: { count: 1, status: 'in-range' },
};

/** SCR-HOME · 모의투자 기본 (10/7 16:10). */
export function homePaper(period: HomePeriod = '3m'): HomeResponse {
  return {
    ledger: 'paper',
    example: true,
    startDate: '2026-07-01',
    basis: BASIS_1007,
    stale: [],
    total: 10_243_800,
    pnl: { amount: 243_800, pct: 2.44 },
    baseline: { pct: 3.59 },
    planChip: { ruleId: INDEX_HALF.id, status: 'in-progress', next: NEXT_US_BUY_1007 },
    trend: paperTrend(period),
    planCard: PAPER_PLAN_CARD,
    composition: PAPER_COMPOSITION,
    accounts: paperAccounts(period),
  };
}

/** 값표 §3 일부 실패 (10/8 08:40): numbers as §1.1, the 10/7 buy failed, retry 10/8 22:30. */
export function homePartial(): HomeResponse {
  const base = homePaper();
  return {
    ...base,
    basis: BASIS_1008,
    planChip: { ruleId: INDEX_HALF.id, status: 'partial-failed', next: NEXT_RETRY_1008 },
    trend: {
      ...base.trend,
      events: base.trend.events.map((e) =>
        e.date === '2026-10-07' ? { ...e, kind: 'partial-failed', kinds: ['partial-failed'] } : e,
      ),
    },
    planCard: {
      ...PAPER_PLAN_CARD,
      status: 'partial-failed',
      next: NEXT_RETRY_1008,
      stages: stages1007(PAPER_SELL_1007, PAPER_FX_1007, PAPER_BUY_1007_FAILED),
      nextCheckAt: kst('2026-10-09', '08:30'),
    },
  };
}

// ── 시세 대기 (값표 §3, 10/7 16:10): US close stuck at 10/2, no 10/7 rebalance ──

export const STALE_COMPOSITION: Composition = {
  groupBy: ['instrument', 'kind', 'country', 'currency', 'rule'],
  groups: [
    {
      key: INDEX_HALF.id,
      rule: INDEX_HALF,
      pct: 81.2,
      target: 80,
      rows: [
        {
          kind: 'holding',
          instrument: KOSPI200,
          pct: 42.6,
          krw: 4_350_000,
          pnlPct: 13.3,
          qty: 120,
          avgCost: { amount: 32_005, currency: 'KRW' },
        },
        {
          kind: 'holding',
          instrument: SP500,
          pct: 38.6,
          krw: 3_948_964,
          usd: 2_856.6,
          pnlPct: -6.5,
          qty: 46,
          avgCost: { amount: 65.94, currency: 'USD' },
        },
      ],
    },
    {
      key: MOMENTUM.id,
      rule: MOMENTUM,
      pct: 18.3,
      target: 20,
      rows: [
        {
          kind: 'holding',
          instrument: SAMSUNG,
          pct: 7.7,
          krw: 788_200,
          pnlPct: 1.4,
          qty: 14,
          avgCost: { amount: 55_508, currency: 'KRW' },
        },
        {
          kind: 'holding',
          instrument: NVDA,
          pct: 7.1,
          krw: 725_345,
          usd: 524.7,
          pnlPct: 0.9,
          qty: 3,
          avgCost: { amount: 172.17, currency: 'USD' },
        },
        {
          kind: 'holding',
          instrument: BTC,
          pct: 3.5,
          krw: 355_185,
          pnlPct: -15.1,
          qty: 0.0027,
          avgCost: { amount: 154_930_000, currency: 'KRW' },
        },
      ],
    },
    {
      key: 'cash',
      label: 'cash',
      pct: 0.5,
      target: null,
      rows: [
        {
          kind: 'cash',
          cash: { currency: 'KRW', country: 'KR' },
          pct: 0.5,
          krw: 47_675,
          chip: { kind: 'sub-share' },
        },
        { kind: 'cash', cash: { currency: 'USD', country: 'US' }, pct: 0.0, krw: 2_295, usd: 1.66 },
      ],
    },
  ],
  pendingBar: null,
  outsideRules: null,
};

export function homeStale(): HomeResponse {
  // Line: the 3개월 line until the last good US close, then KR-only moves to 10,217,664.
  const mine = [
    ...paperDaily3m.filter((p) => p.date <= '2026-10-05'),
    { date: '2026-10-06', value: 10_221_000 },
    { date: '2026-10-07', value: 10_217_664 },
  ];
  // Figma 1:52732: the untouched line follows 3개월 until 10/5, then the stale US close holds
  // it down (10/7 = +3.36%).
  const untouched = patch(untouchedDaily3m, {
    '2026-10-06': 10_330_000,
    '2026-10-07': 10_336_000,
  });
  return {
    ledger: 'paper',
    example: true,
    startDate: '2026-07-01',
    basis: BASIS_STALE,
    stale: ['hero', 'plan', 'composition'],
    total: 10_217_664,
    pnl: { amount: 217_664, pct: 2.18 },
    baseline: { pct: 3.36 },
    planChip: { ruleId: INDEX_HALF.id, status: 'quote-wait', next: NEXT_QUOTE_WAIT_US },
    trend: {
      periods: ['1m', '3m', '1y', 'all'],
      period: '3m',
      periodPnl: { amount: 196_664, pct: 1.96 },
      series: trendSeries(mine, untouched),
      events: [
        { date: '2026-08-21', kind: 'rebalance', kinds: ['rebalance'] },
        { date: '2026-09-14', kind: 'partial-failed', kinds: ['partial-failed'] },
        { date: '2026-09-30', kind: 'dividend', kinds: ['dividend'] },
      ],
      empty: null,
    },
    planCard: {
      rule: INDEX_HALF,
      share: { pct: 81.2, target: 80 },
      status: 'quote-wait',
      next: NEXT_QUOTE_WAIT_US,
      gauge: { kind: 'drift', threshold: 2, needle: null },
      stages: null,
      nextCheckAt: kst('2026-10-08', '08:30'),
      others: { count: 1, status: 'quote-wait' },
    },
    composition: STALE_COMPOSITION,
    // 계좌별 보기 is drawn in home.paper · home.account-* · home.us-* (the states with the split).
    accounts: null,
  };
}

export const STALE_BREAKDOWN: Breakdown = {
  // 3개월 +196,664: dividend 16,243, fees 8/21 206 · 9/14 8 · 9/15 27 (no 10/7 rebalance).
  from: '2026-07-07',
  to: '2026-10-07',
  start: 10_021_000,
  deposit: 0,
  withdrawal: 0,
  market: 180_662,
  dividend: 16_243,
  fees: -241,
  end: 10_217_664,
};

// ── 실전 world (값표 §2, D47: 넣은 돈 그대로) ─────────────────────────────────────

/**
 * §2.2 평상 (10/7 16:00), as the live ledger runs since D47: only 지수 반반 (실전 몫 100 · 3년
 * 발굴 0), won in the Korean ETF and the dollars the owner converted in the US one, about half
 * each. KOSPI200 ETF 140주 × 36,250원; S&P 500 ETF 56주 × $62.40 × 1,382.4원; $125.67 wait for
 * the 22:30 buy of 2주; 33,285원 is less than one share. Total and P&L stay the table's
 * (10,112,670원).
 */
export const LIVE_COMPOSITION: Composition = {
  groupBy: ['instrument', 'country', 'currency'],
  groups: [
    {
      key: INDEX_HALF.id,
      rule: INDEX_HALF,
      pct: 99.7,
      target: 100,
      rows: [
        {
          kind: 'holding',
          instrument: KOSPI200,
          pct: 50.2,
          krw: 5_075_000,
          pnlPct: 5.3,
          qty: 140,
          avgCost: { amount: 34_425, currency: 'KRW' },
        },
        {
          kind: 'holding',
          instrument: SP500,
          pct: 47.8,
          krw: 4_830_659,
          usd: 3_494.4,
          pnlPct: -2.1,
          qty: 56,
          avgCost: { amount: 63.4, currency: 'USD' },
        },
        {
          kind: 'cash',
          cash: { currency: 'USD', country: 'US' },
          pct: 1.7,
          krw: 173_726,
          usd: 125.67,
          chip: { kind: 'buy-wait', instrumentName: 'S&P 500 ETF', qty: 2 },
        },
      ],
    },
    {
      key: 'cash',
      label: 'cash',
      pct: 0.3,
      target: null,
      rows: [
        {
          kind: 'cash',
          cash: { currency: 'KRW', country: 'KR' },
          pct: 0.3,
          krw: 33_285,
          chip: { kind: 'sub-share' },
        },
      ],
    },
  ],
  pendingBar: null,
  outsideRules: null,
};

/**
 * The live gauge (D47, CONTRACT Gauge 'mix'): 한국 5,108,285원 : 미국 5,004,385원 of the rule's
 * money, so 50.5 : 49.5, +0.5%p and 1.5%p to the conversion suggestion.
 */
const LIVE_MIX_GAUGE: PlanCard['gauge'] = {
  kind: 'mix',
  threshold: 2,
  needle: { now: { kr: 50.5, us: 49.5 }, deviation: 0.5, toThreshold: 1.5 },
};

const LIVE_PLAN_CARD: PlanCard = {
  rule: INDEX_HALF,
  share: { pct: 99.7, target: 100 },
  status: 'in-progress',
  next: NEXT_US_BUY_1007,
  gauge: LIVE_MIX_GAUGE,
  stages: liveStages1007(LIVE_BUY_1007),
  nextCheckAt: kst('2026-10-08', '08:30'),
  // 실전 has no AI rule (3년 발굴 0).
  others: null,
};

/** SCR-HOME · 실전 평상 (10/7 16:10, 9/1부터 27거래일: no period chips). */
export function homeLive(): HomeResponse {
  return {
    ledger: 'live',
    example: true,
    startDate: '2026-09-01',
    basis: BASIS_1007,
    stale: [],
    total: 10_112_670,
    pnl: { amount: 112_670, pct: 1.13 },
    baseline: { pct: 1.75 },
    planChip: { ruleId: INDEX_HALF.id, status: 'in-progress', next: NEXT_US_BUY_1007 },
    trend: {
      periods: null,
      period: 'all',
      periodPnl: null,
      series: trendSeries(liveDaily, liveUntouchedDaily),
      events: [
        { date: '2026-09-01', kind: 'live-on', kinds: ['live-on'] },
        { date: '2026-10-07', kind: 'in-progress', kinds: ['in-progress'] },
      ],
      empty: null,
    },
    planCard: LIVE_PLAN_CARD,
    composition: LIVE_COMPOSITION,
    // 계좌별 보기 is drawn in home.paper · home.account-* · home.us-* (the states with the split).
    accounts: null,
  };
}

/** 실전 일부 실패 (직접 할 일), 10/8 08:40: Toss rejected the 10/7 22:30 buy. */
export function homeLiveTodo(): HomeResponse {
  const base = homeLive();
  return {
    ...base,
    basis: BASIS_1008,
    planChip: { ruleId: INDEX_HALF.id, status: 'partial-failed', next: NEXT_TODO_US_BUY },
    trend: {
      ...base.trend,
      events: base.trend.events.map((e) =>
        e.date === '2026-10-07' ? { ...e, kind: 'partial-failed', kinds: ['partial-failed'] } : e,
      ),
    },
    planCard: {
      ...LIVE_PLAN_CARD,
      status: 'partial-failed',
      next: NEXT_TODO_US_BUY,
      stages: liveStages1007(LIVE_BUY_1007_REJECTED),
      nextCheckAt: kst('2026-10-09', '08:30'),
    },
  };
}

/**
 * §2.3 출금 대기 (10/7 16:00): 10/2 hand sale of KOSPI200 ETF 14주 in the Toss app (140 → 126),
 * waiting until 10/12; the won left waits with it (orders 0). 실전 runs 지수 반반 alone (D47).
 */
export const WITHDRAW_COMPOSITION: Composition = {
  groupBy: ['instrument', 'country', 'currency'],
  groups: [
    {
      key: INDEX_HALF.id,
      rule: INDEX_HALF,
      pct: 93.0,
      target: 100,
      rows: [
        {
          kind: 'holding',
          instrument: KOSPI200,
          pct: 45.2,
          krw: 4_567_500,
          pnlPct: 5.3,
          qty: 126,
          avgCost: { amount: 34_425, currency: 'KRW' },
        },
        {
          kind: 'holding',
          instrument: SP500,
          pct: 47.8,
          krw: 4_830_659,
          usd: 3_494.4,
          pnlPct: -2.1,
          qty: 56,
          avgCost: { amount: 63.4, currency: 'USD' },
        },
      ],
    },
    {
      key: 'cash',
      label: 'cash',
      pct: 7.0,
      target: null,
      rows: [
        { kind: 'cash', cash: { currency: 'KRW', country: 'KR' }, pct: 2.0, krw: 205_712 },
        { kind: 'cash', cash: { currency: 'USD', country: 'US' }, pct: 0.0, krw: 622, usd: 0.45 },
        {
          kind: 'cash',
          cash: { currency: 'KRW', country: 'KR' },
          pct: 5.0,
          krw: 500_425,
          chip: { kind: 'withdraw-wait', until: '2026-10-12' },
        },
      ],
    },
  ],
  pendingBar: { withdraw: { krw: 500_425, until: '2026-10-12' } },
  outsideRules: null,
};

export function homeWithdraw(): HomeResponse {
  const next = { kind: 'withdraw-wait', until: '2026-10-12' } as const;
  return {
    ledger: 'live',
    example: true,
    startDate: '2026-09-01',
    basis: BASIS_1007,
    stale: [],
    total: 10_104_918,
    pnl: { amount: 104_918, pct: 1.05 },
    baseline: { pct: 1.75 },
    planChip: { ruleId: INDEX_HALF.id, status: 'withdraw-wait', next },
    trend: {
      periods: null,
      period: 'all',
      periodPnl: null,
      series: trendSeries(patch(liveDaily, { '2026-10-07': 10_104_918 }), liveUntouchedDaily),
      events: [{ date: '2026-09-01', kind: 'live-on', kinds: ['live-on'] }],
      empty: null,
    },
    planCard: {
      rule: INDEX_HALF,
      share: { pct: 93.0, target: 100 },
      status: 'withdraw-wait',
      next,
      // 한국 4,773,212원 (the waiting cash leaves) : 미국 4,831,281원.
      gauge: {
        kind: 'mix',
        threshold: 2,
        needle: { now: { kr: 49.7, us: 50.3 }, deviation: -0.3, toThreshold: 1.7 },
      },
      stages: null,
      nextCheckAt: kst('2026-10-08', '08:30'),
      others: null,
    },
    composition: WITHDRAW_COMPOSITION,
    // 계좌별 보기 is drawn in home.paper · home.account-* · home.us-* (the states with the split).
    accounts: null,
  };
}

/** §2.1 첫 체결 전 (9/1 08:40): all cash (won only), the first order at 09:05. */
export function homeLiveFirst(): HomeResponse {
  return {
    ledger: 'live',
    example: true,
    startDate: '2026-09-01',
    basis: {
      valuedAt: kst('2026-09-01', '08:30'),
      krClose: '2026-08-31',
      usClose: '2026-08-31',
      // Not in 값표: the rate §2.1's first plan implied (it then converted; D47 does not).
      fxRate: 1389.8,
      fxAt: kst('2026-09-01', '08:30'),
      coinAt: null,
    },
    stale: [],
    total: START_CAPITAL,
    pnl: null,
    baseline: null,
    planChip: {
      ruleId: INDEX_HALF.id,
      status: 'scheduled',
      next: {
        kind: 'first-order',
        at: kst('2026-09-01', '09:05'),
        market: 'KR',
        side: 'buy',
        count: 1,
      },
    },
    trend: {
      periods: null,
      period: 'all',
      periodPnl: null,
      series: [
        { date: '2026-09-01', value: START_CAPITAL, ret: 0, baseline: null, baselineRet: null },
      ],
      events: [{ date: '2026-09-01', kind: 'live-on', kinds: ['live-on'] }],
      empty: 'before-first-fill',
    },
    planCard: {
      rule: INDEX_HALF,
      share: { pct: 0, target: 100 },
      status: 'scheduled',
      next: {
        kind: 'first-order',
        at: kst('2026-09-01', '09:05'),
        market: 'KR',
        side: 'buy',
        count: 1,
      },
      // Won only (D47): all of it in Korea, so the live gauge stands at 100 : 0 from the first
      // check, where the plan screen suggests converting half ('환전 제안').
      gauge: {
        kind: 'mix',
        threshold: 2,
        needle: { now: { kr: 100, us: 0 }, deviation: 50, toThreshold: 0 },
      },
      // One stage: the won buys the Korean ETF at 09:05; nothing is converted.
      stages: [
        {
          kind: 'buy',
          status: 'pending',
          at: kst('2026-09-01', '09:05'),
          orders: [LIVE_FIRST_BUY],
        },
      ],
      nextCheckAt: kst('2026-09-02', '08:30'),
      others: null,
    },
    composition: {
      groupBy: [],
      groups: [
        { key: INDEX_HALF.id, rule: INDEX_HALF, pct: 0, target: 100, rows: [] },
        {
          key: 'cash',
          label: 'cash',
          pct: 100,
          target: null,
          rows: [
            {
              kind: 'cash',
              cash: { currency: 'KRW', country: 'KR' },
              pct: 100,
              krw: START_CAPITAL,
              chip: { kind: 'buy-from', at: kst('2026-09-01', '09:05') },
            },
          ],
        },
      ],
      pendingBar: null,
      outsideRules: null,
    },
    // No fill yet: no P&L, so no account view (CONTRACT HomeResponse.accounts).
    accounts: null,
  };
}

/** SCR-HOME empty: 모의투자 before its first check (6/30 18:00), start amount only. */
export function homeEmpty(): HomeResponse {
  const firstCheck = { kind: 'first-check', at: kst('2026-07-01', '08:30') } as const;
  return {
    ledger: 'paper',
    example: true,
    startDate: '2026-07-01',
    basis: {
      valuedAt: kst('2026-06-30', '16:00'),
      krClose: null,
      usClose: null,
      fxRate: null,
      fxAt: null,
      coinAt: null,
    },
    stale: [],
    total: START_CAPITAL,
    pnl: null,
    baseline: null,
    planChip: { ruleId: INDEX_HALF.id, status: 'scheduled', next: firstCheck },
    trend: {
      periods: null,
      period: 'all',
      periodPnl: null,
      series: [],
      events: [],
      empty: 'before-first-check',
    },
    planCard: {
      rule: INDEX_HALF,
      share: { pct: 0, target: 80 },
      status: 'scheduled',
      next: firstCheck,
      gauge: { kind: 'drift', threshold: 2, needle: null },
      stages: null,
      nextCheckAt: kst('2026-07-01', '08:30'),
      // CONTRACT PlanCard.others: before the first check the other rule reads 'before-first'.
      others: { count: 1, status: 'before-first' },
    },
    composition: {
      groupBy: [],
      groups: [
        { key: INDEX_HALF.id, rule: INDEX_HALF, pct: 0, target: 80, rows: [] },
        { key: MOMENTUM.id, rule: MOMENTUM, pct: 0, target: 20, rows: [] },
        {
          key: 'cash',
          label: 'cash',
          pct: 100,
          target: null,
          rows: [
            {
              kind: 'cash',
              cash: { currency: 'KRW', country: 'KR' },
              pct: 100,
              krw: START_CAPITAL,
              chip: { kind: 'first-buy' },
            },
          ],
        },
      ],
      pendingBar: null,
      outsideRules: null,
    },
    accounts: null,
  };
}

// ── spec-only states (그림 없음) ─────────────────────────────────────────────

/**
 * 휴장 (10/9 금 16:10, 한글날 — 한국 휴장, 미국은 열림). Not in 값표: the 10/7 22:30 buy
 * filled at the planned $62.40 (+ fee $0.12) and every price is assumed unchanged since 10/7
 * 16:00 (as 값표 §3 does for 일부 실패), so the total is 10,243,800 − $0.12 = 10,243,633.
 */
export const HOLIDAY_COMPOSITION: Composition = {
  groupBy: ['instrument', 'kind', 'country', 'currency', 'rule'],
  groups: [
    {
      key: INDEX_HALF.id,
      rule: INDEX_HALF,
      pct: 81.1,
      target: 80,
      rows: [
        {
          kind: 'holding',
          instrument: KOSPI200,
          pct: 40.7,
          krw: 4_168_750,
          pnlPct: 13.3,
          qty: 115,
          avgCost: { amount: 32_005, currency: 'KRW' },
        },
        {
          kind: 'holding',
          instrument: SP500,
          pct: 40.4,
          krw: 4_140_564,
          usd: 2_995.2,
          pnlPct: -5.8,
          qty: 48,
          avgCost: { amount: 65.8, currency: 'USD' },
        },
      ],
    },
    PAPER_COMPOSITION.groups[1] ?? { key: MOMENTUM.id, pct: 0, target: 20, rows: [] },
    {
      key: 'cash',
      label: 'cash',
      pct: 0.6,
      target: null,
      rows: [
        {
          kind: 'cash',
          cash: { currency: 'KRW', country: 'KR' },
          pct: 0.6,
          krw: 56_548,
          chip: { kind: 'sub-share' },
        },
        { kind: 'cash', cash: { currency: 'USD', country: 'US' }, pct: 0.0, krw: 2_820, usd: 2.04 },
      ],
    },
  ],
  pendingBar: null,
  outsideRules: null,
};

export const NEXT_HOLIDAY_KR: NextAction = {
  kind: 'holiday',
  markets: ['KR'],
  nextCheckAt: kst('2026-10-12', '08:30'),
};

export function homeHoliday(): HomeResponse {
  const mine = [
    ...paperDaily3m,
    { date: '2026-10-08', value: 10_243_633 },
    { date: '2026-10-09', value: 10_243_633 },
  ];
  const untouched = [
    ...untouchedDaily3m,
    { date: '2026-10-08', value: 10_358_700 },
    { date: '2026-10-09', value: 10_358_700 },
  ];
  return {
    ledger: 'paper',
    example: true,
    startDate: '2026-07-01',
    basis: {
      valuedAt: kst('2026-10-09', '16:00'),
      krClose: '2026-10-08',
      usClose: '2026-10-08',
      fxRate: 1382.4,
      fxAt: kst('2026-10-09', '16:00'),
      coinAt: kst('2026-10-09', '16:00'),
    },
    stale: [],
    total: 10_243_633,
    pnl: { amount: 243_633, pct: 2.44 },
    baseline: { pct: 3.59 },
    planChip: { ruleId: INDEX_HALF.id, status: 'holiday', next: NEXT_HOLIDAY_KR },
    trend: {
      periods: ['1m', '3m', '1y', 'all'],
      period: '3m',
      // From 7/9: 10,243,633 − 10,013,600.
      periodPnl: { amount: 230_033, pct: 2.3 },
      series: trendSeries(
        mine.filter((p) => p.date >= '2026-07-09'),
        untouched,
      ),
      events: [
        { date: '2026-08-21', kind: 'rebalance', kinds: ['rebalance'] },
        { date: '2026-09-14', kind: 'partial-failed', kinds: ['partial-failed'] },
        { date: '2026-09-30', kind: 'dividend', kinds: ['dividend'] },
        { date: '2026-10-07', kind: 'rebalance', kinds: ['rebalance'] },
      ],
      empty: null,
    },
    planCard: {
      rule: INDEX_HALF,
      share: { pct: 81.1, target: 80 },
      status: 'holiday',
      next: NEXT_HOLIDAY_KR,
      gauge: {
        kind: 'drift',
        threshold: 2,
        needle: { instrument: KOSPI200, deviation: 0.2, toThreshold: 1.8 },
      },
      stages: null,
      nextCheckAt: kst('2026-10-12', '08:30'),
      others: { count: 1, status: 'holiday' },
    },
    composition: HOLIDAY_COMPOSITION,
    // 계좌별 보기 is drawn in home.paper · home.account-* · home.us-* (the states with the split).
    accounts: null,
  };
}

/**
 * 확인 실패 (값표 §3, 10/7 09:00): the 10/7 08:30 check failed, retry 09:30. Numbers are the
 * 10/6 16:00 valuation (10,228,000 on the 3개월 line). The 10/6 prices are not in 값표:
 * KOSPI200 ETF 36,200원 · 삼성전자 56,000원 · 환율 1,380.6원 (= the 10/7 08:30 rate) and BTC is
 * the remainder; holdings are the pre-10/7 ones of the 시세 대기 world.
 */
export const CHECK_FAILED_COMPOSITION: Composition = {
  groupBy: ['instrument', 'kind', 'country', 'currency', 'rule'],
  groups: [
    {
      key: INDEX_HALF.id,
      rule: INDEX_HALF,
      pct: 81.2,
      target: 80,
      rows: [
        {
          kind: 'holding',
          instrument: KOSPI200,
          pct: 42.5,
          krw: 4_344_000,
          pnlPct: 13.1,
          qty: 120,
          avgCost: { amount: 32_005, currency: 'KRW' },
        },
        {
          kind: 'holding',
          instrument: SP500,
          pct: 38.7,
          krw: 3_962_874,
          usd: 2_870.4,
          pnlPct: -6.1,
          qty: 46,
          avgCost: { amount: 65.94, currency: 'USD' },
        },
      ],
    },
    {
      key: MOMENTUM.id,
      rule: MOMENTUM,
      pct: 18.3,
      target: 20,
      rows: [
        {
          kind: 'holding',
          instrument: SAMSUNG,
          pct: 7.7,
          krw: 784_000,
          pnlPct: 0.9,
          qty: 14,
          avgCost: { amount: 55_508, currency: 'KRW' },
        },
        {
          kind: 'holding',
          instrument: NVDA,
          pct: 7.1,
          krw: 730_614,
          usd: 529.2,
          pnlPct: 1.6,
          qty: 3,
          avgCost: { amount: 172.17, currency: 'USD' },
        },
        {
          kind: 'holding',
          instrument: BTC,
          pct: 3.5,
          krw: 356_545,
          pnlPct: -14.8,
          qty: 0.0027,
          avgCost: { amount: 154_930_000, currency: 'KRW' },
        },
      ],
    },
    {
      key: 'cash',
      label: 'cash',
      pct: 0.5,
      target: null,
      rows: [
        {
          kind: 'cash',
          cash: { currency: 'KRW', country: 'KR' },
          pct: 0.5,
          krw: 47_675,
          chip: { kind: 'sub-share' },
        },
        { kind: 'cash', cash: { currency: 'USD', country: 'US' }, pct: 0.0, krw: 2_292, usd: 1.66 },
      ],
    },
  ],
  pendingBar: null,
  outsideRules: null,
};

export function homeCheckFailed(): HomeResponse {
  const mine = paperDaily3m.filter((p) => p.date <= '2026-10-06');
  return {
    ledger: 'paper',
    example: true,
    startDate: '2026-07-01',
    basis: {
      valuedAt: kst('2026-10-06', '16:00'),
      krClose: '2026-10-06',
      usClose: '2026-10-05',
      fxRate: 1380.6,
      fxAt: kst('2026-10-06', '16:00'),
      coinAt: kst('2026-10-06', '16:00'),
    },
    stale: [],
    total: 10_228_000,
    pnl: { amount: 228_000, pct: 2.28 },
    baseline: { pct: 3.71 },
    // The plan chip and card keep the last good check (10/6 08:30): in range.
    planChip: {
      ruleId: INDEX_HALF.id,
      status: 'in-range',
      next: nextCheck('2026-10-07', '09:30'),
    },
    trend: {
      periods: ['1m', '3m', '1y', 'all'],
      period: '3m',
      // From 7/7: 10,228,000 − 10,021,000.
      periodPnl: { amount: 207_000, pct: 2.07 },
      series: trendSeries(mine, untouchedDaily3m),
      events: [
        { date: '2026-08-21', kind: 'rebalance', kinds: ['rebalance'] },
        { date: '2026-09-14', kind: 'partial-failed', kinds: ['partial-failed'] },
        { date: '2026-09-30', kind: 'dividend', kinds: ['dividend'] },
      ],
      empty: null,
    },
    planCard: {
      rule: INDEX_HALF,
      share: { pct: 81.2, target: 80 },
      status: 'in-range',
      next: nextCheck('2026-10-07', '09:30'),
      gauge: {
        kind: 'drift',
        threshold: 2,
        needle: { instrument: KOSPI200, deviation: 1.9, toThreshold: 0.1 },
      },
      stages: null,
      nextCheckAt: kst('2026-10-07', '09:30'),
      others: { count: 1, status: 'in-range' },
    },
    composition: CHECK_FAILED_COMPOSITION,
    // 계좌별 보기 is drawn in home.paper · home.account-* · home.us-* (the states with the split).
    accounts: null,
  };
}

/** Rows of a composition, in order (tests and the gauge/row tone order). */
export function compositionRows(c: Composition): CompRow[] {
  return c.groups.flatMap((g) => g.rows);
}
