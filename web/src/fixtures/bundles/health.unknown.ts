// SCR-HEALTH · 확인 불가 (Figma 1:63248) — 예시-값표 §3: 상태 API 자체를 못 불러옴(16:10).
// The shell answered (마지막으로 받은 상태 10/07 08:30) and then fails, so the header turns grey
// '확인 불가'; /api/health always fails. Two good answers first: a dev StrictMode remount spends one.
import type { FixtureBundle } from '../types';
import { NOW, shell } from '../ops';

const failure = { $status: 500, $body: { error: 'internal' } } as const;

const bundle = {
  id: 'health.unknown',
  now: NOW,
  shellPollMs: 400,
  responses: {
    '/api/shell': [shell(), shell(), failure],
    '/api/health': failure,
  },
} satisfies FixtureBundle;

export default bundle;
