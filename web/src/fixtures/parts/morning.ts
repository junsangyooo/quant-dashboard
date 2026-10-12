// The first morning of the 출시 첫날 world (값표 §4, 7/1), as the engine answers it (dumped from
// autotrade with the §4 market): 08:40 after the first check, nothing filled yet; 09:07 after the
// 09:05 Korean buy, before the 09:10 conversion. The live paper ledger has this morning on 10/13.
import type { HomeResponse, NextAction, Order } from '../../api/types';
import { INDEX_HALF, KOSPI200, SP500, START_CAPITAL, kst } from '../world';
import { usEmptyAccounts } from './accounts';

const BASIS_0830: HomeResponse['basis'] = {
  valuedAt: kst('2026-07-01', '08:30'),
  krClose: '2026-06-30',
  usClose: '2026-06-30',
  fxRate: 1392.0,
  fxAt: kst('2026-07-01', '08:25'),
};

const FX: Order = {
  id: '3',
  market: 'KR',
  side: 'fx',
  direction: 'krw-usd',
  approx: true,
  fx: { krw: 4_967_000, usd: 3_568.24, rate: 1392.0 },
  amountKrw: 4_967_000,
  amountUsd: 3_568.24,
  at: kst('2026-07-01', '09:10'),
  status: 'pending',
};

const BUY_KR: Order = {
  id: '1',
  market: 'KR',
  side: 'buy',
  instrument: KOSPI200,
  qty: 156,
  price: 32_000,
  approx: true,
  amountKrw: 4_992_000,
  fee: { krw: 748 },
  at: kst('2026-07-01', '09:05'),
  status: 'pending',
};

const BUY_US: Order = {
  id: '2',
  market: 'US',
  side: 'buy',
  instrument: SP500,
  qty: 54,
  price: 66.0,
  approx: true,
  amountUsd: 3_564.0,
  fee: { usd: 3.56 },
  at: kst('2026-07-01', '22:30'),
  status: 'pending',
};

const START_MARKER: HomeResponse['trend']['events'] = [
  { date: '2026-07-01', kind: 'start', kinds: ['start'] },
];

function morning(
  next: NextAction,
): Omit<HomeResponse, 'total' | 'pnl' | 'planCard' | 'composition' | 'accounts'> {
  return {
    ledger: 'paper',
    example: true,
    startDate: '2026-07-01',
    basis: BASIS_0830,
    stale: [],
    baseline: null,
    planChip: { ruleId: INDEX_HALF.id, status: 'in-progress', next },
    trend: {
      periods: null,
      period: 'all',
      periodPnl: null,
      series: [],
      events: START_MARKER,
      empty: 'first-day',
    },
  };
}

/** 08:40: the first check planned the buys, nothing is filled: no P&L, so no account view. */
export function homeBeforeFill(): HomeResponse {
  const next: NextAction = {
    kind: 'order',
    at: kst('2026-07-01', '09:05'),
    market: 'KR',
    side: 'buy',
    instrumentName: KOSPI200.name,
    qty: 156,
  };
  return {
    ...morning(next),
    total: START_CAPITAL,
    pnl: null,
    planCard: {
      rule: INDEX_HALF,
      share: { pct: 100, target: 100 },
      status: 'in-progress',
      next,
      gauge: {
        kind: 'drift',
        threshold: 2,
        needle: { instrument: KOSPI200, deviation: 0.1, toThreshold: 1.9 },
      },
      stages: [
        { kind: 'fx', status: 'pending', at: kst('2026-07-01', '09:10'), orders: [FX] },
        {
          kind: 'buy',
          status: 'pending',
          at: kst('2026-07-01', '09:05'),
          orders: [BUY_KR, BUY_US],
        },
      ],
      nextCheckAt: kst('2026-07-02', '08:30'),
      others: null,
    },
    composition: {
      groupBy: [],
      groups: [
        {
          key: INDEX_HALF.id,
          rule: INDEX_HALF,
          pct: 100,
          target: 100,
          rows: [
            {
              kind: 'cash',
              cash: { currency: 'KRW', country: 'KR' },
              pct: 50.1,
              krw: 5_012_926,
              chip: { kind: 'buy-wait', instrumentName: KOSPI200.name, qty: 156 },
            },
            {
              kind: 'cash',
              cash: { currency: 'KRW', country: 'KR' },
              pct: 49.9,
              krw: 4_987_074,
              chip: { kind: 'buy-wait', instrumentName: SP500.name, qty: 54 },
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

/** 09:07: KOSPI200 ETF bought at 09:05 (fee 748원); the won for the dollars not converted yet. */
export function homeUsEmpty(): HomeResponse {
  const next: NextAction = {
    kind: 'order',
    at: kst('2026-07-01', '22:30'),
    market: 'US',
    side: 'buy',
    instrumentName: SP500.name,
    qty: 54,
  };
  const bought: Order = {
    id: BUY_KR.id,
    market: 'KR',
    side: 'buy',
    instrument: KOSPI200,
    qty: 156,
    price: 32_000,
    amountKrw: 4_992_000,
    fee: { krw: 748 },
    at: kst('2026-07-01', '09:05'),
    status: 'filled',
    fill: 'paper',
  };
  return {
    ...morning(next),
    total: 9_999_252,
    pnl: { amount: -748, pct: -0.01 },
    planCard: {
      rule: INDEX_HALF,
      share: { pct: 100, target: 100 },
      status: 'in-progress',
      next,
      gauge: {
        kind: 'drift',
        threshold: 2,
        needle: { instrument: KOSPI200, deviation: -0.1, toThreshold: 1.9 },
      },
      stages: [
        { kind: 'fx', status: 'pending', at: kst('2026-07-01', '09:10'), orders: [FX] },
        {
          kind: 'buy',
          status: 'pending',
          at: kst('2026-07-01', '22:30'),
          orders: [bought, BUY_US],
        },
      ],
      nextCheckAt: kst('2026-07-02', '08:30'),
      others: null,
    },
    composition: {
      groupBy: [],
      groups: [
        {
          key: INDEX_HALF.id,
          rule: INDEX_HALF,
          pct: 100,
          target: 100,
          rows: [
            {
              kind: 'holding',
              instrument: KOSPI200,
              pct: 49.9,
              krw: 4_992_000,
              pnlPct: 0,
              qty: 156,
              avgCost: { amount: 32_005, currency: 'KRW' },
            },
            {
              kind: 'cash',
              cash: { currency: 'KRW', country: 'KR' },
              pct: 50.1,
              krw: 5_007_252,
              chip: { kind: 'buy-wait', instrumentName: SP500.name, qty: 54 },
            },
          ],
        },
      ],
      pendingBar: null,
      outsideRules: null,
    },
    accounts: usEmptyAccounts(),
  };
}
