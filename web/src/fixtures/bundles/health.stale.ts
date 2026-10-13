// SCR-HEALTH · 점검 1(시세 낡음) (Figma 1:62952) — 예시-값표 §3 시세 대기: 미국 시세 10/02 기준 ·
// 2거래일째. 원인 하나라 '점검 1'. 10/6·10/7 확인은 시세 대기(주문 0건).
import type { HealthResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import {
  LAST_CHECK,
  NEXT_CHECK,
  NOW,
  PUSH_DEVICES,
  recent14,
  sources,
  staleShell,
  tossExpiringTodo,
} from '../ops';

const health: HealthResponse = {
  summary: {
    kind: 'check',
    sourcesTotal: 6,
    staleCount: 1,
    todoCount: 1,
    failCount: 0,
    lastCheckAt: LAST_CHECK,
    nextCheckAt: NEXT_CHECK,
    lastSuccessAt: LAST_CHECK,
  },
  todos: [
    {
      id: 'stale:us-quotes',
      severity: 'red',
      kind: 'stale',
      // missingDates (CONTRACT todos[].facts, stale): without it the screen falls back to
      // '미국 종가 2거래일치를 못 받았어요'.
      facts: {
        market: 'US',
        basisDate: '2026-10-02',
        tradingDays: 2,
        missingDates: '2026-10-05,2026-10-06',
      },
      action: { kind: 'auto-retry', at: kst('2026-10-08', '06:20') },
      effect: 'orders-zero-live-blocked',
    },
    tossExpiringTodo,
  ],
  sources: [
    sources.kr,
    {
      ...sources.us,
      state: 'stale',
      basis: '2026-10-02',
      receivedAt: kst('2026-10-03', '06:20'),
      age: 1.87,
    },
    sources.fx,
    sources.tossLink,
    sources.tossBalance,
    sources.push,
  ],
  recent14: recent14({
    '2026-10-06': {
      date: '2026-10-06',
      state: 'quote-wait',
      run: { at: kst('2026-10-06', '08:30'), result: 'quote-wait', seconds: 6 },
    },
    '2026-10-07': {
      date: '2026-10-07',
      state: 'quote-wait',
      run: { at: LAST_CHECK, result: 'quote-wait', seconds: 6 },
    },
  }),
  lastRun: { at: LAST_CHECK, result: 'quote-wait', seconds: 6 },
  devices: PUSH_DEVICES,
  liveCash: null,
};

const bundle = {
  id: 'health.stale',
  now: NOW,
  responses: {
    '/api/shell': staleShell(),
    '/api/health': health,
  },
} satisfies FixtureBundle;

export default bundle;
