// SCR-HEALTH · 실전 할 일 (3단계, 그림 없음): 실전 9/1부터. 다른 프로그램(옛 quant)이 같은 토스 키로
// 토큰을 받아 연결이 막혔고(빨강, 직접), 15:50 대조가 KOSPI200 ETF 수량이 다르다고 봤으며(빨강, 직접,
// 주문 0건), 09:10 환전은 주인이 토스 앱에서 할 일로 남아 있어요(노랑). 토스 연결·잔고 대조 줄은 낡음.
import type { HealthResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import {
  LAST_CHECK,
  LAST_RUN,
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
    todoCount: 3,
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
    {
      id: 'fx-manual:41',
      severity: 'yellow',
      kind: 'fx-manual',
      facts: {
        direction: 'krw-usd',
        krw: 4967000,
        usd: 3568.24,
        rate: 1392,
        orderId: 41,
        by: kst('2026-10-07', '22:30'),
      },
      action: { kind: 'manual' },
      effect: 'other',
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
};

const bundle = {
  id: 'health.live',
  now: NOW,
  responses: {
    '/api/shell': liveShell({ status: { kind: 'todo', count: 3 } }),
    '/api/health': health,
  },
} satisfies FixtureBundle;

export default bundle;
