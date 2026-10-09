// SCR-HEALTH · 확인 실패 (Figma 1:63518) — 예시-값표 §3 실행(확인) 실패, 10/07 09:00: 08:30 확인이
// 시세 응답 없음으로 실패, 09:30 자동 재시도. 주문은 나가지 않았어요.
import type { HealthResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import {
  LAST_CHECK,
  NEXT_CHECK,
  account,
  recent14,
  shell,
  sources,
  tossExpiringTodo,
} from '../ops';

const NOW = kst('2026-10-07', '09:00');
const RETRY = kst('2026-10-07', '09:30');

const health: HealthResponse = {
  summary: {
    kind: 'check-failed',
    sourcesTotal: 6,
    staleCount: 0,
    todoCount: 1,
    failCount: 1,
    lastCheckAt: LAST_CHECK,
    nextCheckAt: NEXT_CHECK,
    lastSuccessAt: kst('2026-10-06', '08:30'),
    retryAt: RETRY,
  },
  todos: [
    {
      id: 'check-failed:2026-10-07',
      severity: 'red',
      kind: 'check-failed',
      facts: { at: LAST_CHECK, reason: 'no-quote' },
      action: { kind: 'auto-retry', at: RETRY },
      effect: 'no-order-sent',
    },
    tossExpiringTodo,
  ],
  sources: [
    { ...sources.kr, basis: '2026-10-06', receivedAt: kst('2026-10-06', '16:00') },
    sources.us,
    { ...sources.fx, basis: '1380.6', receivedAt: LAST_CHECK },
    sources.tossLink,
    sources.tossBalance,
    sources.push,
  ],
  recent14: recent14({
    '2026-10-07': {
      date: '2026-10-07',
      state: 'failed',
      run: { at: LAST_CHECK, result: 'failed', seconds: 12 },
    },
  }),
  lastRun: { at: LAST_CHECK, result: 'failed', seconds: 12, reason: 'no-quote' },
};

const bundle = {
  id: 'health.failed',
  now: NOW,
  responses: {
    '/api/shell': shell({
      now: NOW,
      status: { kind: 'check-failed', at: LAST_CHECK },
      banner: { kind: 'check-failed', at: LAST_CHECK, retryAt: RETRY, link: 'health' },
    }),
    '/api/health': health,
    '/api/account': account(),
  },
} satisfies FixtureBundle;

export default bundle;
