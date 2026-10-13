// SCR-HEALTH · 실전 할 일 (3단계, 그림 없음): 실전 9/1부터. 다른 프로그램(옛 quant)이 같은 토스 키로
// 토큰을 받아 연결이 막혔고(빨강, 직접), 15:50 대조가 KOSPI200 ETF 수량이 다르다고 봤어요(빨강, 직접,
// 주문 0건). 토스 연결·잔고 대조 줄은 낡음. 할 일 옆에 원화 · 달러 카드(D47·D48): 14:20에 넣은
// 3,000,000원은 10/8 08:30부터 쓰고, 약 1,500,000원을 달러로 바꾸면 50:50 — 할 일이 아니라 수에 없어요.
import type { HealthResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import {
  LAST_CHECK,
  LAST_RUN,
  LIVE_CASH,
  NEXT_CHECK,
  NOW,
  PUSH_DEVICES,
  liveShell,
  recent14,
  sources,
} from '../ops';

const SEEN = kst('2026-10-07', '15:50');

const health: HealthResponse = {
  summary: {
    kind: 'check',
    sourcesTotal: 6,
    staleCount: 2,
    todoCount: 2,
    failCount: 0,
    lastCheckAt: LAST_CHECK,
    nextCheckAt: NEXT_CHECK,
    lastSuccessAt: LAST_CHECK,
  },
  todos: [
    {
      id: 'broker-mismatch',
      severity: 'red',
      kind: 'broker-mismatch',
      facts: {
        reason: 'positions',
        instrument: 'KOSPI200 ETF',
        ledgerQty: '156',
        brokerQty: '160',
        count: 1,
      },
      action: { kind: 'manual' },
      effect: 'orders-zero-live-blocked',
    },
    {
      id: 'toss-link',
      severity: 'red',
      kind: 'toss-link',
      facts: { cause: 'conflict' },
      action: { kind: 'manual' },
      effect: 'orders-zero-live-blocked',
    },
  ],
  sources: [
    sources.kr,
    sources.us,
    sources.fx,
    {
      id: 'toss-link',
      state: 'stale',
      basis: null,
      receivedAt: SEEN,
      cadence: 'per-check',
      age: 1.33,
      extra: { cause: 'conflict', account: '8901' },
    },
    { ...sources.tossBalance, state: 'stale', basis: 'mismatch', receivedAt: SEEN, age: 1.33 },
    sources.push,
  ],
  recent14: recent14(),
  lastRun: LAST_RUN,
  devices: PUSH_DEVICES,
  liveCash: LIVE_CASH,
};

const bundle = {
  id: 'health.live',
  now: NOW,
  responses: {
    '/api/shell': liveShell({ status: { kind: 'todo', count: 2 } }),
    '/api/health': health,
  },
} satisfies FixtureBundle;

export default bundle;
