// SCR-DAY responses (/api/day/{date}) of the 예시-값표 worlds. 8/21, 9/25 and 10/7 are the table's
// numbers (§1.4, §3); 7/1, 9/9, 9/14, 9/30 and the weekend fill in what the table leaves out, and
// say so. Every day's prev/next are the neighbouring event dates of the 기록 list.
import type { Basis, DayResponse, Instrument, Order, RuleRef, Stage } from '../../api/types';
import { BTC, INDEX_HALF, KOSPI200, MOMENTUM, NVDA, SAMSUNG, SP500, kst } from '../world';
import {
  PAPER_BUY_1007,
  PAPER_BUY_1007_FAILED,
  PAPER_FX_1007,
  PAPER_SELL_1007,
  stages1007,
} from './common';

function basis(day: string, kr: string | null, us: string | null, fx: number | null): Basis {
  return {
    valuedAt: kst(day, '16:00'),
    krClose: kr,
    usClose: us,
    fxRate: fx,
    fxAt: fx === null ? null : kst(day, '08:30'),
  };
}

// ── 7/1 시작 (첫 매수) ────────────────────────────────────────────────────────
// Totals are 값표 §1.4 (6 모의 체결, 수수료 5,667원, 환전 4,768,000원 → $3,425.28 at 1,392.0).
// Per-order prices are derived: KOSPI200 ETF 32,000원 (§1.2), 삼성전자 55,500원 (평균 단가 55,508원
// with the fee), S&P 500 ETF $66.00 (§4), NVDA $172.00, BTC 158,591,000원 (평균 단가 1억 5,493만원
// with the 9/15 buy). Fees: 600 + 124 + $3.42 (4,761원) + 182 = 5,667원.

function filled(
  id: string,
  market: Order['market'],
  side: Order['side'],
  at: string,
  rest: Omit<Order, 'id' | 'market' | 'side' | 'at' | 'status'>,
): Order {
  return { id, market, side, at, status: 'filled', fill: 'paper', ...rest };
}

const START_STAGES: Stage[] = [
  {
    kind: 'fx',
    status: 'done',
    at: kst('2026-07-01', '09:10'),
    orders: [
      filled('paper-20260701-fx-1', 'KR', 'fx', kst('2026-07-01', '09:10'), {
        fx: { krw: 4_768_000, usd: 3_425.28, rate: 1392.0 },
      }),
    ],
  },
  {
    kind: 'buy',
    status: 'done',
    at: kst('2026-07-01', '09:05'),
    orders: [
      filled('paper-20260701-buy-coin-1', 'COIN', 'buy', kst('2026-07-01', '09:00'), {
        instrument: BTC,
        qty: 0.0023,
        price: 158_591_000,
        amountKrw: 364_759,
        fee: { krw: 182 },
      }),
      filled('paper-20260701-buy-kr-1', 'KR', 'buy', kst('2026-07-01', '09:05'), {
        instrument: KOSPI200,
        qty: 125,
        price: 32_000,
        amountKrw: 4_000_000,
        fee: { krw: 600 },
      }),
      filled('paper-20260701-buy-kr-2', 'KR', 'buy', kst('2026-07-01', '09:05'), {
        instrument: SAMSUNG,
        qty: 15,
        price: 55_500,
        amountKrw: 832_500,
        fee: { krw: 124 },
      }),
      filled('paper-20260701-buy-us-1', 'US', 'buy', kst('2026-07-01', '22:31'), {
        instrument: SP500,
        qty: 44,
        price: 66.0,
        amountUsd: 2_904.0,
        fee: { usd: 2.9 },
      }),
      filled('paper-20260701-buy-us-2', 'US', 'buy', kst('2026-07-01', '22:31'), {
        instrument: NVDA,
        qty: 3,
        price: 172.0,
        amountUsd: 516.0,
        fee: { usd: 0.52 },
      }),
    ],
  },
];

export function day0701(): DayResponse {
  return {
    date: '2026-07-01',
    ledger: 'paper',
    example: true,
    prev: null,
    next: '2026-08-21',
    total: 10_000_000,
    change: null,
    events: [
      {
        kind: 'start',
        krw: 10_000_000,
        treatment: 'pnl-excluded',
        stages: START_STAGES,
        feesKrw: 5_667,
      },
    ],
    check: { at: kst('2026-07-01', '08:30'), result: 'rebalance', band: null },
    basis: basis('2026-07-01', '2026-06-30', '2026-06-30', 1392.0),
  };
}

// ── 8/21 리밸런싱 (값표 §1.4, Figma 1:59915 · 1:60239) ─────────────────────────

export function day0821(): DayResponse {
  return {
    date: '2026-08-21',
    ledger: 'paper',
    example: true,
    prev: '2026-07-01',
    next: '2026-09-09',
    total: 10_084_600,
    change: { amount: 12_300, pct: 0.12 },
    events: [
      {
        kind: 'rebalance',
        rule: INDEX_HALF,
        stagesMini: ['done', 'done', 'done'],
        weights: {
          instruments: [KOSPI200, SP500],
          before: [52.3, 47.7],
          after: [50.2, 49.8],
          target: [50, 50],
          threshold: 2,
        },
        stages: [
          {
            kind: 'sell',
            status: 'done',
            at: kst('2026-08-21', '09:05'),
            orders: [
              filled('paper-20260821-sell-1', 'KR', 'sell', kst('2026-08-21', '09:05'), {
                instrument: KOSPI200,
                qty: 5,
                price: 33_800,
                amountKrw: 169_000,
                fee: { krw: 25 },
              }),
            ],
          },
          {
            kind: 'fx',
            status: 'done',
            at: kst('2026-08-21', '09:10'),
            orders: [
              filled('paper-20260821-fx-1', 'KR', 'fx', kst('2026-08-21', '09:10'), {
                fx: { krw: 175_000, usd: 125.93, rate: 1389.6 },
              }),
            ],
          },
          {
            kind: 'buy',
            status: 'done',
            at: kst('2026-08-21', '22:31'),
            orders: [
              filled('paper-20260821-buy-1', 'US', 'buy', kst('2026-08-21', '22:31'), {
                instrument: SP500,
                qty: 2,
                price: 63.0,
                amountUsd: 126.0,
                fee: { usd: 0.13 },
              }),
            ],
          },
        ],
        feesKrw: 206,
      },
    ],
    check: {
      at: kst('2026-08-21', '08:30'),
      result: 'rebalance',
      band: { threshold: 2, before: 2.3, after: 0.2 },
      ruleId: INDEX_HALF.id,
      rule: INDEX_HALF,
      instrument: KOSPI200,
      weight: 52.3,
      over: 0.3,
    },
    basis: basis('2026-08-21', '2026-08-20', '2026-08-20', 1389.6),
  };
}

// ── 9/9 확인 실패 (값표 §1.4: 시세 응답 없음 → 9/10 정상, 주문 없음) ─────────────

export function day0909(): DayResponse {
  const check: DayResponse['check'] = {
    at: kst('2026-09-09', '08:30'),
    result: 'failed',
    band: null,
    failure: { reason: 'no-quote', recoveredOn: '2026-09-10' },
  };
  return {
    date: '2026-09-09',
    ledger: 'paper',
    example: true,
    prev: '2026-08-21',
    next: '2026-09-14',
    total: 10_100_300,
    change: { amount: -9_800, pct: -0.1 },
    events: [],
    check,
    basis: basis('2026-09-09', '2026-09-08', '2026-09-08', null),
  };
}

// ── 9/14 일부 실패 ([예시] 종목 모멘텀, 값표 §1.4) ──────────────────────────────
// 매도 삼성전자 1주 57,000원 (수수료 8원) 체결 / 매수 BTC 0.0004 실패 (시세 응답 없음) → 9/15 09:02
// 133,880,000원 = 53,552원 (수수료 27원) 체결. Weights are derived (not in the table): 삼성전자
// +2.2%p at the check (벗어남 흐름 9/14), after = with the cash waiting for BTC (인계 3).

/** Failed on 9/14 and sent again on 9/15 (CONTRACT Order.retried: the failed day keeps it). */
const BTC_RETRIED: Order = {
  id: 'paper-20260914-buy-coin-1',
  market: 'COIN',
  side: 'buy',
  instrument: BTC,
  qty: 0.0004,
  price: 133_880_000,
  approx: true,
  amountKrw: 53_552,
  at: kst('2026-09-14', '09:06'),
  status: 'failed',
  failure: { reason: 'no-quote', retryAt: kst('2026-09-15', '09:02') },
  retried: { at: kst('2026-09-15', '09:02'), status: 'filled' },
};

function momentumWeights(before: number[], after: number[]) {
  const instruments: Instrument[] = [SAMSUNG, NVDA, BTC];
  return { instruments, before, after, target: [42, 40, 18], threshold: 2 };
}

export function day0914(): DayResponse {
  return {
    date: '2026-09-14',
    ledger: 'paper',
    example: true,
    prev: '2026-09-09',
    next: '2026-09-30',
    total: 10_090_600,
    change: { amount: -19_000, pct: -0.19 },
    events: [
      {
        kind: 'partial-failed',
        rule: MOMENTUM,
        stagesMini: ['done', 'failed'],
        weights: momentumWeights([44.2, 39.6, 16.2], [41.2, 39.6, 19.2]),
        stages: [
          {
            kind: 'sell',
            status: 'done',
            at: kst('2026-09-14', '09:05'),
            orders: [
              filled('paper-20260914-sell-1', 'KR', 'sell', kst('2026-09-14', '09:05'), {
                instrument: SAMSUNG,
                qty: 1,
                price: 57_000,
                amountKrw: 57_000,
                fee: { krw: 8 },
              }),
            ],
          },
          { kind: 'buy', status: 'failed', at: kst('2026-09-14', '09:06'), orders: [BTC_RETRIED] },
        ],
        feesKrw: 8,
      },
    ],
    check: {
      at: kst('2026-09-14', '08:30'),
      result: 'partial-failed',
      band: { threshold: 2, before: 2.2, after: -0.8 },
      ruleId: MOMENTUM.id,
      rule: MOMENTUM,
      instrument: SAMSUNG,
      weight: 44.2,
      over: 0.2,
    },
    basis: basis('2026-09-14', '2026-09-11', '2026-09-11', 1385.2),
  };
}

// ── 9/25 거래 없음 (한국 휴장, 값표 §3, Figma 1:60076) ──────────────────────────

export function day0925(): DayResponse {
  return {
    date: '2026-09-25',
    ledger: 'paper',
    example: true,
    prev: '2026-09-14',
    next: '2026-09-30',
    total: 10_152_400,
    change: { amount: 3_400, pct: 0.03 },
    events: [],
    check: {
      at: kst('2026-09-25', '08:30'),
      result: 'holiday',
      holidayMarkets: ['KR'],
      band: null,
      ruleId: INDEX_HALF.id,
      rule: INDEX_HALF,
      instrument: KOSPI200,
      weight: 51.1,
      toThreshold: 0.9,
    },
    basis: basis('2026-09-25', '2026-09-23', '2026-09-24', 1384.0),
  };
}

// ── 9/30 배당 (값표 §1.4: 16,243원 세후, KOSPI200 ETF) ─────────────────────────
// The 08:30 position (51.8% · 1.8%p) is derived from the 벗어남 흐름 (9/25 1.7 → 10/1 1.9).

export function day0930(): DayResponse {
  return {
    date: '2026-09-30',
    ledger: 'paper',
    example: true,
    prev: '2026-09-14',
    next: '2026-10-07',
    total: 10_173_500,
    change: { amount: 7_500, pct: 0.07 },
    events: [
      {
        kind: 'dividend',
        krw: 16_243,
        treatment: 'income',
        instrument: KOSPI200,
      },
    ],
    check: {
      at: kst('2026-09-30', '08:30'),
      result: 'in-range',
      band: null,
      ruleId: INDEX_HALF.id,
      rule: INDEX_HALF,
      instrument: KOSPI200,
      weight: 51.8,
      toThreshold: 0.2,
    },
    basis: basis('2026-09-30', '2026-09-29', '2026-09-29', 1388.1),
  };
}

// ── 10/7 리밸런싱 중 (값표 §1.4: 08:30 KOSPI200 ETF 52.4% → +2.4%p, 0.4%p 넘음) ─────

const WEIGHTS_1007 = {
  instruments: [KOSPI200, SP500],
  before: [52.4, 47.6],
  after: [50.2, 49.8],
  target: [50, 50],
  threshold: 2,
};

const CHECK_1007 = {
  at: kst('2026-10-07', '08:30'),
  band: { threshold: 2, before: 2.4, after: 0.2 },
  ruleId: INDEX_HALF.id,
  rule: INDEX_HALF,
  instrument: KOSPI200,
  weight: 52.4,
  over: 0.4,
} as const;

/** 확인(08:30)이 쓴 값: 한국 10/6 종가 · 미국 10/6 종가(ET) · 환율 1,380.6원 08:30 (값표 §0). */
const BASIS_CHECK_1007 = basis('2026-10-07', '2026-10-06', '2026-10-06', 1380.6);

export function day1007(): DayResponse {
  return {
    date: '2026-10-07',
    ledger: 'paper',
    example: true,
    prev: '2026-09-30',
    next: null,
    total: 10_243_800,
    change: { amount: 24_400, pct: 0.24 },
    events: [
      {
        kind: 'in-progress',
        rule: INDEX_HALF,
        stagesMini: ['done', 'done', 'pending'],
        weights: WEIGHTS_1007,
        stages: stages1007(PAPER_SELL_1007, PAPER_FX_1007, PAPER_BUY_1007),
        feesKrw: 27,
      },
    ],
    check: { ...CHECK_1007, result: 'in-progress' },
    basis: BASIS_CHECK_1007,
  };
}

/** 일부 실패 세계 (값표 §3, 10/8 08:40): the 22:30 buy failed (no quote) → 10/8 22:30 다시. */
export function day1007Partial(): DayResponse {
  return {
    ...day1007(),
    events: [
      {
        kind: 'partial-failed',
        rule: INDEX_HALF,
        stagesMini: ['done', 'done', 'failed'],
        weights: WEIGHTS_1007,
        stages: stages1007(PAPER_SELL_1007, PAPER_FX_1007, PAPER_BUY_1007_FAILED),
        feesKrw: 27,
      },
    ],
    check: { ...CHECK_1007, result: 'partial-failed' },
  };
}

// ── 10/4 주말 (spec only: '주말 · 확인 없음') ─────────────────────────────────

export function dayWeekend(): DayResponse {
  return {
    date: '2026-10-04',
    ledger: 'paper',
    example: true,
    prev: '2026-09-30',
    next: '2026-10-07',
    total: 10_226_200,
    change: null,
    events: [],
    check: { at: null, result: 'weekend', band: null },
    basis: basis('2026-10-04', '2026-10-02', '2026-10-02', null),
  };
}

// ── AI 판단 사건 (3년 발굴, Figma 탐색 17:5855 '마지막 판단 10/02 08:34 · 셀트리온 · 급락 확인 ·
// 두 번 다 유지 · 팔지 않음'). Proposal world: the day total is the 모의투자 line's 10/2; the tokens
// are illustrative (the table has none). ─────────────────────────────────────────────────────

export const DISCOVERY: RuleRef = {
  id: 'discovery_3y',
  name: '3년 발굴',
  ai: true,
  colorIndex: 1,
};

export const CELLTRION: Instrument = {
  id: 'KR:068270',
  name: '셀트리온',
  kind: 'stock',
  market: 'KR',
  currency: 'KRW',
  initials: '셀',
};

export function dayAi(): DayResponse {
  return {
    date: '2026-10-02',
    ledger: 'paper',
    example: true,
    prev: '2026-09-30',
    next: '2026-10-07',
    total: 10_226_200,
    change: { amount: 39_100, pct: 0.38 },
    events: [
      {
        kind: 'ai-check',
        rule: DISCOVERY,
        judgment: {
          at: kst('2026-10-02', '08:34'),
          trigger: 'shock',
          instrument: CELLTRION,
          model: 'sonnet',
          tokens: 24_000,
          verdict: 'hold',
          votes: ['hold', 'hold'],
          action: 'none',
          // 급락 확인: the stock, the drop against its index that day, the filings in the packet;
          // out: the news the web search found (CONTRACT JudgmentItem — the model's words stay in
          // the record, not in the response).
          input: [
            { key: 'instrument', instrument: CELLTRION },
            { key: 'shock', date: '2026-10-02', value: -8.1 },
            { key: 'filings', value: 2 },
          ],
          output: [{ key: 'news', value: 3 }],
        },
      },
    ],
    check: {
      at: kst('2026-10-02', '08:30'),
      result: 'in-range',
      band: null,
      ruleId: INDEX_HALF.id,
      rule: INDEX_HALF,
      instrument: KOSPI200,
      weight: 51.9,
      toThreshold: 0.1,
    },
    basis: basis('2026-10-02', '2026-10-01', '2026-10-01', 1384.6),
  };
}

/** Every paper-world day the 기록 page links to (the 1440 panel moves between them). */
export function paperDays() {
  return {
    '/api/day/2026-07-01': day0701(),
    '/api/day/2026-08-21': day0821(),
    '/api/day/2026-09-09': day0909(),
    '/api/day/2026-09-14': day0914(),
    '/api/day/2026-09-25': day0925(),
    '/api/day/2026-09-30': day0930(),
    '/api/day/2026-10-07': day1007(),
  } as const;
}
