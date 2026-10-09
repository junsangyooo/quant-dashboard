// SCR-HEALTH · 첫 확인 전 (명세 empty, 그림 없음): 6/30 16:10, 첫 확인 7/1(수) 08:30 예정.
// 자료 행은 아직 받은 값이 없어 회색, 14일 칸은 빈칸 (phase 1 sources: 한국·미국 시세, 환율).
import type { HealthResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { shell } from '../ops';

const NOW = kst('2026-06-30', '16:10');
const FIRST = kst('2026-07-01', '08:30');

const blank = (id: 'kr-quotes' | 'us-quotes' | 'fx') =>
  ({
    id,
    state: 'unknown',
    basis: null,
    receivedAt: null,
    cadence: 'daily',
    age: 0,
    ...(id === 'fx' ? {} : { extra: { market: id === 'kr-quotes' ? 'KR' : 'US' } }),
  }) satisfies HealthResponse['sources'][number];

const weekdays = [
  '2026-06-17',
  '2026-06-18',
  '2026-06-19',
  '2026-06-22',
  '2026-06-23',
  '2026-06-24',
  '2026-06-25',
  '2026-06-26',
  '2026-06-29',
  '2026-06-30',
];

const health: HealthResponse = {
  summary: {
    kind: 'before-first',
    sourcesTotal: 3,
    staleCount: 0,
    todoCount: 0,
    failCount: 0,
    lastCheckAt: null,
    nextCheckAt: FIRST,
    firstCheckAt: FIRST,
  },
  todos: [],
  sources: [blank('kr-quotes'), blank('us-quotes'), blank('fx')],
  recent14: weekdays.map((date) => ({ date, state: 'before-record' })),
  lastRun: null,
  devices: [],
};

const bundle = {
  id: 'health.empty',
  now: NOW,
  responses: {
    '/api/shell': shell({ now: NOW, status: { kind: 'before-first', firstCheckAt: FIRST } }),
    '/api/health': health,
  },
} satisfies FixtureBundle;

export default bundle;
