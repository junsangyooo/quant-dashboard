// SCR-HOME · 모의투자 기본 (Figma 1:51434 / 1:54828) — 예시-값표 §0, §1 (10/7 16:10 KST).
import type { Order } from '../../api/types';
import type { FixtureBundle } from '../types';
import {
  BTC,
  INDEX_HALF,
  KOSPI200,
  MOMENTUM,
  NVDA,
  SAMSUNG,
  SP500,
  kst,
  paperTrendSeries3m,
} from '../world';

const NOW = kst('2026-10-07', '16:10');

// §1.4 10/7 리밸런싱 중: 매도·한국 09:05 · 환전 09:10 (모의 체결) · 매수·미국 22:30 대기.
const sell: Order = {
  id: 'paper-20261007-sell-1',
  market: 'KR',
  side: 'sell',
  instrument: KOSPI200,
  qty: 5,
  price: 36_380,
  amountKrw: 181_900,
  fee: { krw: 27 },
  at: kst('2026-10-07', '09:05'),
  status: 'filled',
  fill: 'paper',
};
const fx: Order = {
  id: 'paper-20261007-fx-1',
  market: 'KR', // 환전 is booked on the KRW account (contract Order.market)
  side: 'fx',
  fx: { krw: 173_000, usd: 125.3, rate: 1380.6 },
  at: kst('2026-10-07', '09:10'),
  status: 'filled',
  fill: 'paper',
};
const buy: Order = {
  id: 'paper-20261007-buy-1',
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

const next = {
  kind: 'order',
  at: kst('2026-10-07', '22:30'),
  market: 'US',
  side: 'buy',
  instrumentName: 'S&P 500 ETF',
  qty: 2,
} as const;

const bundle = {
  id: 'home.paper',
  now: NOW,
  responses: {
    '/api/shell': {
      now: NOW,
      mode: 'paper',
      modeChangedAt: null,
      liveSince: null,
      status: { kind: 'ok', lastCheckAt: kst('2026-10-07', '08:30') },
      banner: null,
    },
    '/api/home': {
      ledger: 'paper',
      example: true,
      startDate: '2026-07-01',
      basis: {
        valuedAt: kst('2026-10-07', '16:00'),
        krClose: '2026-10-07',
        usClose: '2026-10-06',
        fxRate: 1382.4,
        fxAt: kst('2026-10-07', '16:00'),
        coinAt: kst('2026-10-07', '16:00'),
      },
      stale: [],
      total: 10_243_800,
      pnl: { amount: 243_800, pct: 2.44 },
      baseline: { pct: 3.59 },
      planChip: { ruleId: INDEX_HALF.id, status: 'in-progress', next },
      trend: {
        periods: ['1m', '3m', '1y', 'all'],
        period: '3m',
        periodPnl: { amount: 222_800, pct: 2.22 },
        series: paperTrendSeries3m(),
        // The home band shows rebalances, failures, dividends (not check failures).
        events: [
          { date: '2026-08-21', kind: 'rebalance' },
          { date: '2026-09-14', kind: 'partial-failed' },
          { date: '2026-09-30', kind: 'dividend' },
          { date: '2026-10-07', kind: 'in-progress' },
        ],
        empty: null,
      },
      planCard: {
        rule: INDEX_HALF,
        share: { pct: 81.1, target: 80 },
        status: 'in-progress',
        next,
        gauge: {
          kind: 'drift',
          threshold: 2,
          needle: { instrument: KOSPI200, deviation: 0.2, toThreshold: 1.8 },
        },
        stages: [
          { kind: 'sell', status: 'done', at: kst('2026-10-07', '09:05'), orders: [sell] },
          { kind: 'fx', status: 'done', at: kst('2026-10-07', '09:10'), orders: [fx] },
          { kind: 'buy', status: 'pending', at: kst('2026-10-07', '22:30'), orders: [buy] },
        ],
        nextCheckAt: kst('2026-10-08', '08:30'),
        others: { count: 1, status: 'in-range' },
      },
      composition: {
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
                cash: { currency: 'USD' },
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
                cash: { currency: 'KRW' },
                pct: 0.6,
                krw: 56_548,
                chip: { kind: 'sub-share' },
              },
            ],
          },
        ],
        pendingBar: null,
        outsideRules: null,
      },
    },
    // 3개월 변동 분해 (7/7–10/7). 예시 값표 splits only the since-start PnL, so this split is
    // derived: dividend 9/30 16,243, fees after 7/7 206 + 8 + 27 + 27 = 268, market = the rest.
    '/api/home/breakdown': {
      from: '2026-07-07',
      to: '2026-10-07',
      start: 10_021_000,
      deposit: 0,
      withdrawal: 0,
      market: 206_825,
      dividend: 16_243,
      fees: -268,
      end: 10_243_800,
    },
  },
} satisfies FixtureBundle;

export default bundle;
