// Building blocks shared by the home.* and plan.* bundles: clocks, 기준, shells, orders and
// stages of each world in 예시-값표 (§1 모의투자 10/7, §2 실전, §3 변형, §4 출시 첫날).
import type {
  Banner,
  Basis,
  Ledger,
  NextAction,
  Order,
  ShellResponse,
  Stage,
} from '../../api/types';
import { KOSPI200, SAMSUNG, SP500, NVDA, kst } from '../world';

// ── clocks ───────────────────────────────────────────────────────────────────

/** 값표 §0: the screens are drawn at 10/7(수) 16:10 KST. */
export const NOW_1007 = kst('2026-10-07', '16:10');
/** 값표 §3 일부 실패 · 실전 일부 실패: 10/8(목) 08:40. */
export const NOW_1008 = kst('2026-10-08', '08:40');

// ── 기준 (Basis) ─────────────────────────────────────────────────────────────

/** 평가 기준 10/7 16:00: 한국 10/7 종가 · 미국 10/6 종가(ET) · 환율 1,382.4원 16:00. */
export const BASIS_1007: Basis = {
  valuedAt: kst('2026-10-07', '16:00'),
  krClose: '2026-10-07',
  usClose: '2026-10-06',
  fxRate: 1382.4,
  fxAt: kst('2026-10-07', '16:00'),
  coinAt: kst('2026-10-07', '16:00'),
};

/** 일부 실패 (10/8 08:40): '08:30 기준'; 값표 assumes 10/7 US close and 08:30 FX equal 1.1. */
export const BASIS_1008: Basis = {
  valuedAt: kst('2026-10-08', '08:30'),
  krClose: '2026-10-07',
  usClose: '2026-10-07',
  fxRate: 1382.4,
  fxAt: kst('2026-10-08', '08:30'),
  coinAt: kst('2026-10-08', '08:30'),
};

/** 시세 대기: the US close is stuck at 10/2. */
export const BASIS_STALE: Basis = { ...BASIS_1007, usClose: '2026-10-02' };

// ── shells ───────────────────────────────────────────────────────────────────

export function shellOf(options: {
  now: string;
  mode: Ledger;
  status: ShellResponse['status'];
  banner?: Banner | null;
  modeChangedAt?: string | null;
}): ShellResponse {
  return {
    now: options.now,
    mode: options.mode,
    modeChangedAt: options.modeChangedAt ?? null,
    liveSince: options.mode === 'live' ? kst('2026-08-31', '21:10') : null,
    status: options.status,
    banner: options.banner ?? null,
  };
}

export const OK_0830_1007: ShellResponse['status'] = {
  kind: 'ok',
  lastCheckAt: kst('2026-10-07', '08:30'),
};

/** '10/7 미국 매수 실패 · 10/8 22:30 다시 시도' (값표 §3 일부 실패). */
export const BANNER_PARTIAL_RETRY: Banner = {
  kind: 'partial-retry',
  date: '2026-10-07',
  market: 'US',
  side: 'buy',
  retryAt: kst('2026-10-08', '22:30'),
  link: 'plan',
};

/** '10/7 미국 매수 실패 · 토스 주문 거부 · 직접 할 일' (값표 §3 실전 일부 실패). */
export const BANNER_PARTIAL_TODO: Banner = {
  kind: 'partial-todo',
  date: '2026-10-07',
  market: 'US',
  side: 'buy',
  reason: 'broker-rejected',
  link: 'health',
};

/** '미국 시세 10/2 기준 · 2거래일째 갱신 없음' (값표 §3 시세 대기). */
export const BANNER_STALE: Banner = {
  kind: 'stale',
  market: 'US',
  basisDate: '2026-10-02',
  tradingDays: 2,
  link: 'health',
};

// ── 10/7 리밸런싱 (값표 §1.4 모의 체결 · §2.2 실제 체결) ───────────────────────

export const PAPER_SELL_1007: Order = {
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

export const PAPER_FX_1007: Order = {
  id: 'paper-20261007-fx-1',
  market: 'KR', // 환전 is booked on the KRW account (contract Order.market)
  side: 'fx',
  fx: { krw: 173_000, usd: 125.3, rate: 1380.6 },
  at: kst('2026-10-07', '09:10'),
  status: 'filled',
  fill: 'paper',
};

export const PAPER_BUY_1007: Order = {
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

export const LIVE_SELL_1007: Order = {
  ...PAPER_SELL_1007,
  id: 'live-20261007-sell-1',
  price: 36_370,
  amountKrw: 181_850,
  fill: 'live',
};

export const LIVE_FX_1007: Order = {
  ...PAPER_FX_1007,
  id: 'live-20261007-fx-1',
  fx: { krw: 173_000, usd: 125.22, rate: 1381.5 },
  fill: 'live',
};

export const LIVE_BUY_1007: Order = { ...PAPER_BUY_1007, id: 'live-20261007-buy-1' };

/** 일부 실패: the 22:30 buy got no quote; it goes again 10/8 22:30. */
export const PAPER_BUY_1007_FAILED: Order = {
  ...PAPER_BUY_1007,
  status: 'failed',
  failure: { reason: 'no-quote', retryAt: kst('2026-10-08', '22:30') },
};

/** 실전 일부 실패: Toss rejected the buy; no retry, 직접 할 일. */
export const LIVE_BUY_1007_REJECTED: Order = {
  ...LIVE_BUY_1007,
  status: 'failed',
  failure: { reason: 'broker-rejected', manual: true },
};

export function stages1007(sell: Order, fx: Order, buy: Order): Stage[] {
  const buyStatus: Stage['status'] =
    buy.status === 'failed' ? 'failed' : buy.status === 'filled' ? 'done' : 'pending';
  return [
    { kind: 'sell', status: 'done', at: kst('2026-10-07', '09:05'), orders: [sell] },
    { kind: 'fx', status: 'done', at: kst('2026-10-07', '09:10'), orders: [fx] },
    { kind: 'buy', status: buyStatus, at: kst('2026-10-07', '22:30'), orders: [buy] },
  ];
}

export const NEXT_US_BUY_1007: NextAction = {
  kind: 'order',
  at: kst('2026-10-07', '22:30'),
  market: 'US',
  side: 'buy',
  instrumentName: 'S&P 500 ETF',
  qty: 2,
};

export const NEXT_RETRY_1008: NextAction = {
  kind: 'retry',
  at: kst('2026-10-08', '22:30'),
  market: 'US',
  side: 'buy',
};

export const NEXT_TODO_US_BUY: NextAction = { kind: 'todo', market: 'US', side: 'buy' };

export const NEXT_QUOTE_WAIT_US: NextAction = {
  kind: 'quote-wait',
  market: 'US',
  basisDate: '2026-10-02',
};

export function nextCheck(date: string, time = '08:30'): NextAction {
  return { kind: 'next-check', at: kst(date, time) };
}

// ── 실전 첫 체결 전 (값표 §2.1, 9/1 08:40): the first orders of 지수 반반 ─────────

export const LIVE_FIRST_FX: Order = {
  id: 'live-20260901-fx-1',
  market: 'KR',
  side: 'fx',
  approx: true,
  fx: { krw: 4_710_000, usd: 3_389, rate: 1389.8 },
  at: kst('2026-09-01', '09:10'),
  status: 'pending',
};

export const LIVE_FIRST_BUYS: Order[] = [
  {
    id: 'live-20260901-buy-kr-1',
    market: 'KR',
    side: 'buy',
    instrument: KOSPI200,
    qty: 118,
    price: 34_400,
    approx: true,
    amountKrw: 4_059_200,
    at: kst('2026-09-01', '09:05'),
    status: 'pending',
  },
  {
    id: 'live-20260901-buy-kr-2',
    market: 'KR',
    side: 'buy',
    instrument: SAMSUNG,
    qty: 14,
    price: 56_800,
    approx: true,
    amountKrw: 795_200,
    at: kst('2026-09-01', '09:05'),
    status: 'pending',
  },
  {
    id: 'live-20260901-buy-us-1',
    market: 'US',
    side: 'buy',
    instrument: SP500,
    qty: 45,
    price: 63.4,
    approx: true,
    amountUsd: 2_853,
    at: kst('2026-09-01', '22:30'),
    status: 'pending',
  },
  {
    id: 'live-20260901-buy-us-2',
    market: 'US',
    side: 'buy',
    instrument: NVDA,
    qty: 3,
    price: 177.3,
    approx: true,
    amountUsd: 531.9,
    at: kst('2026-09-01', '22:30'),
    status: 'pending',
  },
];
