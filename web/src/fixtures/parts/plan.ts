// SCR-PLAN responses of each 예시-값표 world (§1.3 규칙 안 비중, §1.4/§2.2 단계, §3 변형, §4).
import type {
  DriftPeriod,
  Instrument,
  NextAction,
  PlanResponse,
  RuleCard,
  ScheduleItem,
} from '../../api/types';
import type { LinePoint } from '../../charts/geometry/lineChart';
import { driftIndex, driftMomentum } from '../charts';
import { BTC, INDEX_HALF, KOSPI200, MOMENTUM, NVDA, SAMSUNG, SP500, kst } from '../world';
import {
  LIVE_BUY_1007,
  LIVE_BUY_1007_REJECTED,
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
import { LIVE_CASH } from '../ops';
import { NEXT_HOLIDAY_KR } from './home';
import {
  discoveryVsIndex,
  liveDriftIndex,
  staleDriftIndex,
  staleDriftMomentum,
  withdrawDriftIndex,
} from './series';

type Rows = RuleCard['rows'];
type BasisLine = RuleCard['basisLine'];
type Drift = PlanResponse['drift'];

// ── rule cards ───────────────────────────────────────────────────────────────

/** §1.3 지금 (16:00): 지수 반반 50.2 : 49.8 (매수 대기 달러는 S&P 500 ETF에 더함). */
const INDEX_ROWS: Rows = [
  { instrument: KOSPI200, weight: 50.2, target: 50, toThreshold: 1.8 },
  { instrument: SP500, weight: 49.8, target: 50, toThreshold: 1.8 },
];

/** §1.3: 모멘텀 42.0 · 39.0 · 18.9, NVDA is the most deviated (−1.0%p). */
const MOMENTUM_ROWS: Rows = [
  { instrument: SAMSUNG, weight: 42.0, target: 42, toThreshold: 2.0 },
  { instrument: NVDA, weight: 39.0, target: 40, toThreshold: 1.0 },
  { instrument: BTC, weight: 18.9, target: 18, toThreshold: 1.1 },
];

const FX_1600 = { fxRate: 1382.4, fxAt: kst('2026-10-07', '16:00') };

const BASIS_INDEX: BasisLine = {
  pendingBuyIncluded: true,
  ...FX_1600,
  withdrawExcluded: false,
  staleMarket: null,
  staleBasisDate: null,
};

const BASIS_MOMENTUM: BasisLine = { ...BASIS_INDEX, pendingBuyIncluded: false };

function indexCard(
  over: Partial<RuleCard> & Pick<RuleCard, 'share' | 'status' | 'next'>,
): RuleCard {
  return {
    rule: INDEX_HALF,
    gauge: {
      kind: 'drift',
      threshold: 2,
      needle: { instrument: KOSPI200, deviation: 0.2, toThreshold: 1.8 },
    },
    rows: INDEX_ROWS,
    basisLine: BASIS_INDEX,
    ...over,
  };
}

function momentumCard(
  over: Partial<RuleCard> & Pick<RuleCard, 'share' | 'status' | 'next'>,
): RuleCard {
  return {
    rule: MOMENTUM,
    gauge: {
      kind: 'drift',
      threshold: 2,
      needle: { instrument: NVDA, deviation: -1.0, toThreshold: 1.0 },
    },
    rows: MOMENTUM_ROWS,
    basisLine: BASIS_MOMENTUM,
    ...over,
  };
}

/**
 * 실전 (D47): the rule's weights stay, but nothing rebalances between won and dollars, so the rows
 * carry no '리밸런싱까지' and the gauge is the mix of the two against the targets.
 */
const LIVE_ROWS: Rows = [
  { instrument: KOSPI200, weight: 50.4, target: 50, toThreshold: null },
  { instrument: SP500, weight: 49.6, target: 50, toThreshold: null },
];

function liveCard(over: Partial<RuleCard> & Pick<RuleCard, 'share' | 'status' | 'next'>): RuleCard {
  return indexCard({
    gauge: {
      kind: 'mix',
      threshold: 2,
      needle: { now: { kr: 50.5, us: 49.5 }, deviation: 0.5, toThreshold: 1.5 },
    },
    rows: LIVE_ROWS,
    ...over,
  });
}

const NEXT_CHECK_1008 = nextCheck('2026-10-08');

// ── 벗어남 흐름 ──────────────────────────────────────────────────────────────

function lines(index: readonly LinePoint[], momentum: readonly LinePoint[]): Drift['lines'] {
  return [
    { ruleId: INDEX_HALF.id, points: [...index] },
    { ruleId: MOMENTUM.id, points: [...momentum] },
  ];
}

const PAPER_DRIFT_EVENTS: Drift['events'] = [
  { date: '2026-08-21', kind: 'rebalance', ruleId: INDEX_HALF.id },
  { date: '2026-09-14', kind: 'partial-failed', ruleId: MOMENTUM.id },
  { date: '2026-10-07', kind: 'in-progress', ruleId: INDEX_HALF.id },
];

/** 모의투자: 3개월 (7/7–10/7); 1년 = 전체 = since 7/1 (the record is 3 months long). */
export function paperDrift(period: DriftPeriod = '3m'): Drift {
  if (period === '3m') {
    return {
      periods: ['3m', '1y', 'all'],
      period,
      since: '2026-07-07',
      lines: lines(driftIndex, driftMomentum),
      staleFrom: null,
      events: PAPER_DRIFT_EVENTS,
      empty: null,
    };
  }
  // 7/1 (first buy) is not in Figma: 지수 반반 +0.2%p as on 출시 첫날, 모멘텀 0.4%p.
  return {
    periods: ['3m', '1y', 'all'],
    period,
    since: '2026-07-01',
    lines: lines(
      [{ date: '2026-07-01', value: 0.2 }, ...driftIndex],
      [{ date: '2026-07-01', value: 0.4 }, ...driftMomentum],
    ),
    staleFrom: null,
    events: PAPER_DRIFT_EVENTS,
    empty: null,
  };
}

/**
 * 실전: 27거래일 since 9/1, no period chips; ⏻ 실전 켬 is the ledger's event (ruleId null). One line,
 * 지수 반반's mix of won and dollars (D47: `mix`); 실전 has no AI rule.
 */
function liveDrift(
  index: readonly LinePoint[],
  last: Drift['events'][number]['kind'] | null,
): Drift {
  return {
    periods: null,
    period: 'all',
    since: '2026-09-01',
    lines: [{ ruleId: INDEX_HALF.id, points: [...index] }],
    staleFrom: null,
    events: [
      { date: '2026-09-01', kind: 'live-on', ruleId: null },
      ...(last ? [{ date: '2026-10-07', kind: last, ruleId: INDEX_HALF.id }] : []),
    ],
    empty: null,
    mix: true,
  };
}

// ── 예정 ─────────────────────────────────────────────────────────────────────

const HOLIDAY_1009: ScheduleItem = { kind: 'holiday', date: '2026-10-09', markets: ['KR'] };

// ── worlds ───────────────────────────────────────────────────────────────────

/** SCR-PLAN · 모의투자 기본 (10/7 16:10). */
export function planPaper(drift: DriftPeriod = '3m'): PlanResponse {
  return {
    ledger: 'paper',
    example: true,
    ruleShares: [
      { rule: INDEX_HALF, pct: 81.1 },
      { rule: MOMENTUM, pct: 18.3 },
    ],
    rules: [
      indexCard({
        share: { pct: 81.1, target: 80 },
        status: 'in-progress',
        next: NEXT_US_BUY_1007,
      }),
      momentumCard({ share: { pct: 18.3, target: 20 }, status: 'in-range', next: NEXT_CHECK_1008 }),
    ],
    schedule: {
      now: {
        ruleId: INDEX_HALF.id,
        status: 'in-progress',
        stages: stages1007(PAPER_SELL_1007, PAPER_FX_1007, PAPER_BUY_1007),
      },
      items: [
        { kind: 'next-check', at: kst('2026-10-08', '08:30') },
        HOLIDAY_1009,
        { kind: 'sub-share-cash', krw: 56_548 },
      ],
    },
    drift: paperDrift(drift),
  };
}

/** 값표 §3 일부 실패 (10/8 08:40): buy ✕, again 10/8 22:30. */
export function planPartial(): PlanResponse {
  const base = planPaper();
  return {
    ...base,
    rules: [
      indexCard({
        share: { pct: 81.1, target: 80 },
        status: 'partial-failed',
        next: NEXT_RETRY_1008,
      }),
      momentumCard({
        share: { pct: 18.3, target: 20 },
        status: 'in-range',
        next: nextCheck('2026-10-09'),
      }),
    ],
    schedule: {
      now: {
        ruleId: INDEX_HALF.id,
        status: 'partial-failed',
        stages: stages1007(PAPER_SELL_1007, PAPER_FX_1007, PAPER_BUY_1007_FAILED),
      },
      items: [
        {
          kind: 'retry',
          at: kst('2026-10-08', '22:30'),
          market: 'US',
          side: 'buy',
          ruleId: INDEX_HALF.id,
        },
        HOLIDAY_1009,
        { kind: 'sub-share-cash', krw: 56_548 },
      ],
    },
    drift: {
      ...base.drift,
      events: base.drift.events.map((e) =>
        e.date === '2026-10-07' ? { ...e, kind: 'partial-failed' } : e,
      ),
    },
  };
}

/** 값표 §3 시세 대기: every weight '—', both rules 시세 대기, lines break from 10/5. */
export function planStale(): PlanResponse {
  const staleBasis: BasisLine = {
    ...BASIS_INDEX,
    pendingBuyIncluded: false,
    staleMarket: 'US',
    staleBasisDate: '2026-10-02',
  };
  const blank = (rows: Rows): Rows =>
    rows.map((r) => ({
      instrument: r.instrument,
      weight: null,
      target: r.target,
      toThreshold: null,
    }));
  return {
    ledger: 'paper',
    example: true,
    ruleShares: [
      { rule: INDEX_HALF, pct: 81.2 },
      { rule: MOMENTUM, pct: 18.3 },
    ],
    rules: [
      indexCard({
        share: { pct: 81.2, target: 80 },
        status: 'quote-wait',
        next: NEXT_QUOTE_WAIT_US,
        gauge: { kind: 'drift', threshold: 2, needle: null },
        rows: blank(INDEX_ROWS),
        basisLine: staleBasis,
      }),
      momentumCard({
        share: { pct: 18.3, target: 20 },
        status: 'quote-wait',
        next: NEXT_QUOTE_WAIT_US,
        gauge: { kind: 'drift', threshold: 2, needle: null },
        rows: blank(MOMENTUM_ROWS),
        basisLine: staleBasis,
      }),
    ],
    schedule: {
      now: { ruleId: INDEX_HALF.id, status: 'quote-wait', stages: [] },
      items: [
        { kind: 'next-check', at: kst('2026-10-08', '08:30') },
        HOLIDAY_1009,
        { kind: 'sub-share-cash', krw: 47_675 },
      ],
    },
    drift: {
      periods: ['3m', '1y', 'all'],
      period: '3m',
      since: '2026-07-07',
      lines: lines(staleDriftIndex, staleDriftMomentum),
      staleFrom: '2026-10-05',
      events: PAPER_DRIFT_EVENTS.filter((e) => e.date !== '2026-10-07'),
      empty: null,
    },
  };
}

/**
 * SCR-PLAN · 실전 평상 (10/7 16:10, D47): 지수 반반 alone; the 08:30 check buys S&P 500 ETF at
 * 22:30 with the dollars the owner converted. 1주 미만 대기 33,285원.
 */
export function planLive(): PlanResponse {
  return {
    ledger: 'live',
    example: true,
    ruleShares: null,
    rules: [
      liveCard({
        share: { pct: 99.7, target: 100 },
        status: 'in-progress',
        next: NEXT_US_BUY_1007,
      }),
    ],
    schedule: {
      now: {
        ruleId: INDEX_HALF.id,
        status: 'in-progress',
        stages: liveStages1007(LIVE_BUY_1007),
      },
      items: [
        { kind: 'next-check', at: kst('2026-10-08', '08:30') },
        HOLIDAY_1009,
        { kind: 'sub-share-cash', krw: 33_285 },
      ],
    },
    drift: liveDrift(liveDriftIndex, 'in-progress'),
  };
}

/**
 * 실전 · 넣은 돈 그대로 (D47·D48, 그림 없음), 10/7 16:10: no plan open, and the owner deposited
 * 3,000,000원 at 14:20. The rule's weights (its holdings) are inside the band, but with that won
 * 한국 is 61.8% of the rule's money: '환전 제안 · 약 1,552,000원을 달러로 바꾸면 50:50', and the gauge
 * stands 11.8%p over (its 10/7 16:00 point too). The deposit waits for 10/8 08:30 (예정 '새로 들어온
 * 돈'), as new cash outside the rule's share (10,079,385원 of 13,112,670원). No plan is open, and
 * nothing waits on the suggestion.
 */
export function planLiveMix(): PlanResponse {
  const base = planLive();
  return {
    ...base,
    rules: [
      liveCard({
        share: { pct: 76.8, target: 100 },
        status: 'fx-suggest',
        next: NEXT_CHECK_1008,
        gauge: {
          kind: 'mix',
          threshold: 2,
          needle: { now: { kr: 61.8, us: 38.2 }, deviation: 11.8, toThreshold: 0 },
        },
        fxSuggestion: LIVE_CASH.fxSuggestion,
      }),
    ],
    schedule: {
      now: null,
      items: [
        { kind: 'next-check', at: kst('2026-10-08', '08:30') },
        HOLIDAY_1009,
        { kind: 'new-money-wait', krw: 3_000_000, usd: 0, from: kst('2026-10-08', '08:30') },
        { kind: 'sub-share-cash', krw: 33_285 },
      ],
    },
    drift: liveDrift(
      liveDriftIndex.map((p) => (p.date === '2026-10-07' ? { ...p, value: 11.8 } : p)),
      null,
    ),
  };
}

/** 실전 일부 실패 (10/8 08:40): Toss rejected the buy → 직접 할 일. */
export function planLiveTodo(): PlanResponse {
  const base = planLive();
  return {
    ...base,
    rules: [
      liveCard({
        share: { pct: 99.7, target: 100 },
        status: 'partial-failed',
        next: NEXT_TODO_US_BUY,
      }),
    ],
    schedule: {
      now: {
        ruleId: INDEX_HALF.id,
        status: 'partial-failed',
        stages: liveStages1007(LIVE_BUY_1007_REJECTED),
      },
      items: [
        { kind: 'next-check', at: kst('2026-10-09', '08:30') },
        HOLIDAY_1009,
        { kind: 'sub-share-cash', krw: 33_285 },
      ],
    },
    drift: liveDrift(liveDriftIndex, 'partial-failed'),
  };
}

/**
 * 값표 §2.3 출금 대기 (실전, D47): weights without the waiting cash (48.6 · 51.4), orders 0; the
 * gauge is 한국 49.7 : 미국 50.3 of the rule's money (the waiting cash leaves it).
 */
export function planWithdraw(): PlanResponse {
  const next: NextAction = { kind: 'withdraw-wait', until: '2026-10-12' };
  const basis: BasisLine = { ...BASIS_INDEX, pendingBuyIncluded: false, withdrawExcluded: true };
  return {
    ledger: 'live',
    example: true,
    ruleShares: null,
    rules: [
      liveCard({
        share: { pct: 93.0, target: 100 },
        status: 'withdraw-wait',
        next,
        gauge: {
          kind: 'mix',
          threshold: 2,
          needle: { now: { kr: 49.7, us: 50.3 }, deviation: -0.3, toThreshold: 1.7 },
        },
        rows: [
          { instrument: KOSPI200, weight: 48.6, target: 50, toThreshold: null },
          { instrument: SP500, weight: 51.4, target: 50, toThreshold: null },
        ],
        basisLine: basis,
      }),
    ],
    schedule: {
      now: null,
      items: [
        { kind: 'withdraw-wait', krw: 500_425, until: '2026-10-12' },
        { kind: 'next-check', at: kst('2026-10-08', '08:30') },
        HOLIDAY_1009,
      ],
    },
    drift: { ...liveDrift(withdrawDriftIndex, null) },
  };
}

/** 휴장 (10/9 16:10, 한국 휴장): the state of home.holiday. */
export function planHoliday(): PlanResponse {
  const fx = { fxRate: 1382.4, fxAt: kst('2026-10-09', '16:00') };
  return {
    ledger: 'paper',
    example: true,
    ruleShares: [
      { rule: INDEX_HALF, pct: 81.1 },
      { rule: MOMENTUM, pct: 18.3 },
    ],
    rules: [
      indexCard({
        share: { pct: 81.1, target: 80 },
        status: 'holiday',
        next: NEXT_HOLIDAY_KR,
        basisLine: { ...BASIS_INDEX, ...fx, pendingBuyIncluded: false },
      }),
      momentumCard({
        share: { pct: 18.3, target: 20 },
        status: 'holiday',
        next: NEXT_HOLIDAY_KR,
        basisLine: { ...BASIS_MOMENTUM, ...fx },
      }),
    ],
    schedule: {
      now: null,
      items: [
        { kind: 'next-check', at: kst('2026-10-12', '08:30') },
        { kind: 'sub-share-cash', krw: 56_548 },
      ],
    },
    drift: {
      periods: ['3m', '1y', 'all'],
      period: '3m',
      since: '2026-07-09',
      lines: lines(
        [...driftIndex.filter((p) => p.date >= '2026-07-09'), { date: '2026-10-09', value: 0.2 }],
        [
          ...driftMomentum.filter((p) => p.date >= '2026-07-09'),
          { date: '2026-10-09', value: 1.0 },
        ],
      ),
      staleFrom: null,
      events: PAPER_DRIFT_EVENTS.map((e) =>
        e.date === '2026-10-07' ? { ...e, kind: 'rebalance' } : e,
      ),
      empty: null,
    },
  };
}

/** 출시 첫날 (값표 §4, 7/1 16:10): one rule, no rule-share bar, '벗어남 흐름은 둘째 날부터'. */
export function planFirstDay(): PlanResponse {
  return {
    ledger: 'paper',
    example: true,
    ruleShares: null,
    rules: [
      indexCard({
        share: { pct: 99.6, target: 100 },
        status: 'in-progress',
        next: {
          kind: 'order',
          at: kst('2026-07-01', '22:30'),
          market: 'US',
          side: 'buy',
          instrumentName: 'S&P 500 ETF',
          qty: 54,
        },
        basisLine: {
          ...BASIS_INDEX,
          fxRate: 1391.5,
          fxAt: kst('2026-07-01', '16:00'),
        },
      }),
    ],
    schedule: {
      now: {
        ruleId: INDEX_HALF.id,
        status: 'in-progress',
        stages: [
          {
            kind: 'fx',
            status: 'done',
            at: kst('2026-07-01', '09:10'),
            orders: [
              {
                id: 'paper-20260701-fx-1',
                market: 'KR',
                side: 'fx',
                direction: 'krw-usd',
                fx: { krw: 4_967_000, usd: 3_568.24, rate: 1392.0 },
                at: kst('2026-07-01', '09:10'),
                status: 'filled',
                fill: 'paper',
              },
            ],
          },
          {
            kind: 'buy',
            status: 'pending',
            at: kst('2026-07-01', '22:30'),
            orders: [
              {
                id: 'paper-20260701-buy-kr-1',
                market: 'KR',
                side: 'buy',
                instrument: KOSPI200,
                qty: 156,
                price: 32_000,
                amountKrw: 4_992_000,
                at: kst('2026-07-01', '09:05'),
                status: 'filled',
                fill: 'paper',
              },
              {
                id: 'paper-20260701-buy-us-1',
                market: 'US',
                side: 'buy',
                instrument: SP500,
                qty: 54,
                price: 66.0,
                approx: true,
                amountUsd: 3_564.0,
                at: kst('2026-07-01', '22:30'),
                status: 'pending',
              },
            ],
          },
        ],
      },
      items: [
        { kind: 'next-check', at: kst('2026-07-02', '08:30') },
        { kind: 'holiday', date: '2026-07-03', markets: ['US'] },
        { kind: 'sub-share-cash', krw: 40_252 },
      ],
    },
    drift: {
      periods: null,
      period: 'all',
      since: '2026-07-01',
      lines: [{ ruleId: INDEX_HALF.id, points: [{ date: '2026-07-01', value: 0.2 }] }],
      staleFrom: null,
      events: [],
      empty: 'second-day',
    },
  };
}

/** SCR-PLAN empty: before the first check — hollow gauges, weights '—', first-check item. */
export function planEmpty(): PlanResponse {
  const firstCheck: NextAction = { kind: 'first-check', at: kst('2026-07-01', '08:30') };
  const blank = (rows: Rows): Rows =>
    rows.map((r) => ({
      instrument: r.instrument,
      weight: null,
      target: r.target,
      toThreshold: null,
    }));
  const basis: BasisLine = {
    pendingBuyIncluded: false,
    fxRate: null,
    fxAt: null,
    withdrawExcluded: false,
    staleMarket: null,
    staleBasisDate: null,
  };
  return {
    ledger: 'paper',
    example: true,
    ruleShares: null,
    rules: [
      indexCard({
        share: { pct: 0, target: 80 },
        status: 'scheduled',
        next: firstCheck,
        gauge: { kind: 'drift', threshold: 2, needle: null },
        rows: blank(INDEX_ROWS),
        basisLine: basis,
      }),
      momentumCard({
        share: { pct: 0, target: 20 },
        status: 'scheduled',
        next: firstCheck,
        gauge: { kind: 'drift', threshold: 2, needle: null },
        rows: blank(MOMENTUM_ROWS),
        basisLine: basis,
      }),
    ],
    schedule: {
      now: null,
      items: [
        { kind: 'first-check', at: kst('2026-07-01', '08:30') },
        { kind: 'holiday', date: '2026-07-03', markets: ['US'] },
      ],
    },
    drift: {
      periods: null,
      period: 'all',
      since: '2026-07-01',
      lines: [],
      staleFrom: null,
      events: [],
      empty: 'second-day',
    },
  };
}

// ── AI 규칙 (Figma 탐색 17:7108 '계획 카드 · 3년 발굴 · 팔 조건 게이지') ────────────

const HD_ELECTRIC: Instrument = {
  id: 'KR:267260',
  name: 'HD현대일렉트릭',
  kind: 'stock',
  market: 'KR',
  currency: 'KRW',
  initials: 'HD',
};
const HANWHA_AERO: Instrument = {
  id: 'KR:012450',
  name: '한화에어로스페이스',
  kind: 'stock',
  market: 'KR',
  currency: 'KRW',
  initials: '한',
};
const BROADCOM: Instrument = {
  id: 'US:AVGO',
  name: 'Broadcom',
  kind: 'stock',
  market: 'US',
  currency: 'USD',
  initials: 'AV',
};

/** '3년 발굴' (AI 판단 포함). The card shows no '[예시]' prefix in Figma. */
export const DISCOVERY = { id: 'discovery_3y', name: '3년 발굴', ai: true, colorIndex: 1 } as const;

/** 다음 확인 10/8 08:30 · 점검 11/1 (CONTRACT next-check.reviewAt: the next monthly review). */
const DISCOVERY_NEXT: NextAction = {
  kind: 'next-check',
  at: kst('2026-10-08', '08:30'),
  reviewAt: kst('2026-11-01', '08:30'),
};

/** Equal weights (same-amount buys); the AI card shows sell-condition progress instead. */
const DISCOVERY_CARD: RuleCard = {
  rule: DISCOVERY,
  share: { pct: 18.5, target: 20 },
  status: 'hold',
  next: DISCOVERY_NEXT,
  gauge: {
    kind: 'sell-condition',
    needle: {
      instrument: HD_ELECTRIC,
      progress: 54,
      metric: { key: 'op_margin' },
      margin: { unit: 'pp', value: 2.3 },
    },
  },
  rows: [
    {
      instrument: HD_ELECTRIC,
      weight: 33.4,
      target: 33.3,
      toThreshold: null,
      progress: 54,
      metric: { key: 'op_margin' },
      margin: { unit: 'pp', value: 2.3 },
    },
    {
      instrument: HANWHA_AERO,
      weight: 33.5,
      target: 33.3,
      toThreshold: null,
      progress: 41,
      metric: { key: 'backlog' },
      margin: { unit: 'KRW', value: 3_100_000_000_000 },
    },
    {
      instrument: BROADCOM,
      weight: 33.1,
      target: 33.4,
      toThreshold: null,
      progress: 12,
      metric: { key: 'segment_revenue', param: 'AI' },
      margin: { unit: 'quarter', value: 2 },
    },
  ],
  basisLine: {
    pendingBuyIncluded: false,
    fxRate: null,
    fxAt: null,
    withdrawExcluded: false,
    staleMarket: null,
    staleBasisDate: null,
    metricTableAt: '2026-10-08',
  },
  vsIndex: { since: '2026-07-01', points: [...discoveryVsIndex] },
};

/**
 * plan.discovery: the 모의투자 world with [예시] 종목 모멘텀 replaced by 3년 발굴 (18.5% · 목표
 * 20%, 17:7108). 지수 반반 keeps its §1.3 card; its share is 80.9% so the shares and the 0.6%
 * cash still add up to 100.
 */
export function planDiscovery(): PlanResponse {
  const base = planPaper();
  return {
    ...base,
    ruleShares: [
      { rule: INDEX_HALF, pct: 80.9 },
      { rule: DISCOVERY, pct: 18.5 },
    ],
    rules: [
      indexCard({
        share: { pct: 80.9, target: 80 },
        status: 'in-progress',
        next: NEXT_US_BUY_1007,
      }),
      DISCOVERY_CARD,
    ],
    schedule: {
      now: base.schedule.now,
      items: [
        { kind: 'next-check', at: kst('2026-10-08', '08:30') },
        HOLIDAY_1009,
        // The server does not send 'earnings' yet (no public source of report dates); the item
        // is kept so the screen's line for it stays drawn and tested.
        { kind: 'earnings', date: '2026-10-24', instrument: HD_ELECTRIC, ruleId: DISCOVERY.id },
        { kind: 'monthly-review', at: kst('2026-11-01', '08:30'), ruleId: DISCOVERY.id },
        { kind: 'discovery', at: kst('2026-12-01', '08:30'), ruleId: DISCOVERY.id },
        { kind: 'sub-share-cash', krw: 56_548 },
      ],
    },
    drift: {
      ...base.drift,
      lines: base.drift.lines.filter((l) => l.ruleId === INDEX_HALF.id),
      events: base.drift.events.filter((e) => e.ruleId === null || e.ruleId === INDEX_HALF.id),
    },
  };
}
