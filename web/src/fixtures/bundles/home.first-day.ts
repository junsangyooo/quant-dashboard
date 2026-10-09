// SCR-HOME · 출시 첫날(규칙 1개) (Figma 1:54401) — 예시-값표 §4 (7/1 16:10 KST).
// One rule (지수 반반, 100% of assets), KOSPI200 ETF bought at 09:05, dollars waiting for the
// 22:30 S&P 500 ETF buy; the graph is one point ('그래프는 둘째 날부터').
import type { Order } from '../../api/types';
import type { FixtureBundle } from '../types';
import { INDEX_HALF, KOSPI200, SP500, kst } from '../world';

const NOW = kst('2026-07-01', '16:10');

const fx: Order = {
  id: 'paper-20260701-fx-1',
  market: 'KR', // 환전 is booked on the KRW account (contract Order.market)
  side: 'fx',
  fx: { krw: 4_967_000, usd: 3_568.24, rate: 1392.0 },
  at: kst('2026-07-01', '09:10'),
  status: 'filled',
  fill: 'paper',
};
const buyKr: Order = {
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
};
const buyUs: Order = {
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
};

const next = {
  kind: 'order',
  at: kst('2026-07-01', '22:30'),
  market: 'US',
  side: 'buy',
  instrumentName: 'S&P 500 ETF',
  qty: 54,
} as const;

const bundle = {
  id: 'home.first-day',
  now: NOW,
  responses: {
    '/api/shell': {
      now: NOW,
      mode: 'paper',
      modeChangedAt: null,
      liveSince: null,
      status: { kind: 'ok', lastCheckAt: kst('2026-07-01', '08:30') },
      banner: null,
    },
    '/api/home': {
      ledger: 'paper',
      example: true,
      startDate: '2026-07-01',
      basis: {
        valuedAt: kst('2026-07-01', '16:00'),
        krClose: '2026-07-01',
        usClose: '2026-06-30',
        fxRate: 1391.5,
        fxAt: kst('2026-07-01', '16:00'),
        coinAt: null,
      },
      stale: [],
      total: 10_005_258,
      pnl: { amount: 5_258, pct: 0.05 },
      baseline: { pct: 0.05 },
      planChip: { ruleId: INDEX_HALF.id, status: 'in-progress', next },
      trend: {
        periods: null,
        period: 'all',
        periodPnl: null,
        series: [
          {
            date: '2026-07-01',
            value: 10_005_258,
            ret: 0.05,
            baseline: 10_005_258,
            baselineRet: 0.05,
          },
        ],
        events: [{ date: '2026-07-01', kind: 'start' }],
        empty: 'first-day',
      },
      planCard: {
        rule: INDEX_HALF,
        share: { pct: 99.6, target: 100 },
        status: 'in-progress',
        next,
        gauge: {
          kind: 'drift',
          threshold: 2,
          needle: { instrument: KOSPI200, deviation: 0.2, toThreshold: 1.8 },
        },
        // No sell stage on day one (stages with no orders are not sent).
        stages: [
          { kind: 'fx', status: 'done', at: kst('2026-07-01', '09:10'), orders: [fx] },
          {
            kind: 'buy',
            status: 'pending',
            at: kst('2026-07-01', '22:30'),
            orders: [buyKr, buyUs],
          },
        ],
        nextCheckAt: kst('2026-07-02', '08:30'),
        others: null,
      },
      composition: {
        // Only the groupings that yield two or more groups (기획 §5 SCR-HOME.first-day).
        groupBy: ['country', 'currency'],
        groups: [
          {
            key: INDEX_HALF.id,
            rule: INDEX_HALF,
            pct: 99.6,
            target: 100,
            rows: [
              {
                kind: 'holding',
                instrument: KOSPI200,
                pct: 50.0,
                krw: 4_999_800,
                pnlPct: 0.1,
                qty: 156,
                avgCost: { amount: 32_000, currency: 'KRW' },
              },
              {
                kind: 'cash',
                cash: { currency: 'USD' },
                pct: 49.6,
                krw: 4_965_206,
                usd: 3_568.24,
                chip: { kind: 'buy-wait', instrumentName: 'S&P 500 ETF', qty: 54 },
              },
            ],
          },
          {
            key: 'cash',
            label: 'cash',
            pct: 0.4,
            target: null,
            rows: [
              {
                kind: 'cash',
                cash: { currency: 'KRW' },
                pct: 0.4,
                krw: 40_252,
                chip: { kind: 'sub-share' },
              },
            ],
          },
        ],
        pendingBar: null,
        outsideRules: null,
      },
    },
  },
} satisfies FixtureBundle;

export default bundle;
