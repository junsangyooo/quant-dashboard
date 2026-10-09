// SCR-HEALTH · 2단계 자료 행 (화면-맞춤.md §3, 그림 없음): 공시(DART 점검 중 → 한국 공시 감시 멈춤,
// 빨간 할 일), AI 호출(마지막 성공 Sonnet · 이번 달 토큰이 예산을 넘음 → 노란 할 일), 지표 표(마지막
// 실적 뽑기). These rows appear only because the response lists them; the 1단계 server sends three
// sources. Facts and extras follow CONTRACT /api/health: filings { source, market, state, since }
// (red, retried at the next check), ai-cli { reason: 'over-budget', tokens, budget } (yellow, no
// time), source extras filings { dart, edgar } and ai-cli { monthTokens, budget, enabled, due }.
import type { HealthResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { NEXT_CHECK, NOW, healthTodo, shell } from '../ops';

const base = healthTodo();
const FILINGS_LAST = kst('2026-10-06', '18:00');

const health: HealthResponse = {
  ...base,
  // 'check': the paused filing watch is a red card and a 'maintenance' source (staleCount counts
  // it). todoCount = the manual cards: 토스 연결 and the AI budget (the filing card retries itself).
  summary: { ...base.summary, kind: 'check', sourcesTotal: 9, staleCount: 1, todoCount: 2 },
  todos: [
    ...base.todos,
    {
      id: 'filings:dart',
      severity: 'red',
      kind: 'filings',
      facts: { source: 'dart', market: 'KR', state: 'maintenance', since: FILINGS_LAST },
      action: { kind: 'auto-retry', at: NEXT_CHECK },
      effect: 'other',
    },
    {
      id: 'ai-cli:budget:2026-10',
      severity: 'yellow',
      kind: 'ai-cli',
      facts: { reason: 'over-budget', tokens: 3_240_000, budget: 3_000_000 },
      action: { kind: 'manual' },
      effect: 'other',
    },
  ],
  sources: [
    ...base.sources,
    {
      id: 'filings',
      state: 'maintenance',
      basis: '2026-10-06',
      receivedAt: FILINGS_LAST,
      cadence: 'event',
      age: 0.92,
      extra: { dart: 'maintenance', edgar: 'ok' },
    },
    {
      id: 'ai-cli',
      state: 'fresh',
      basis: 'sonnet',
      receivedAt: kst('2026-10-07', '08:31'),
      cadence: 'event',
      age: 0.32,
      extra: { monthTokens: 3_240_000, budget: 3_000_000, enabled: 1, due: 0 },
    },
    {
      id: 'metric-table',
      state: 'fresh',
      basis: '2026-10-02',
      receivedAt: kst('2026-10-02', '19:10'),
      cadence: 'event',
      age: 0.5,
    },
  ],
};

const bundle = {
  id: 'health.phase2',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/health': health,
  },
} satisfies FixtureBundle;

export default bundle;
