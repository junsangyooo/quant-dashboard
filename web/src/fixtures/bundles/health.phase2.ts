// SCR-HEALTH · 2단계 자료 행 (화면-맞춤.md §3, 그림 없음): 공시(DART 점검 중 → 한국 공시 감시 멈춤),
// AI 호출(구독 로그인, 마지막 성공), 지표 표(마지막 실적 뽑기). These rows appear only because
// the response lists them; the 1단계 server sends three sources.
import type { HealthResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { NOW, account, healthTodo, shell } from '../ops';

const base = healthTodo();

const health: HealthResponse = {
  ...base,
  summary: { ...base.summary, sourcesTotal: 9 },
  todos: [
    ...base.todos,
    {
      id: 'filings:KR',
      severity: 'yellow',
      kind: 'filings',
      facts: { market: 'KR', since: kst('2026-10-07', '06:00') },
      action: { kind: 'auto-retry', at: kst('2026-10-08', '06:00') },
      effect: 'other',
    },
  ],
  sources: [
    ...base.sources,
    {
      id: 'filings',
      state: 'maintenance',
      basis: '2026-10-06',
      receivedAt: kst('2026-10-06', '18:00'),
      cadence: 'event',
      age: 0.92,
      extra: { market: 'KR' },
    },
    {
      id: 'ai-cli',
      state: 'fresh',
      basis: null,
      receivedAt: kst('2026-10-07', '08:31'),
      cadence: 'per-check',
      age: 0.32,
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
    '/api/account': account(),
  },
} satisfies FixtureBundle;

export default bundle;
