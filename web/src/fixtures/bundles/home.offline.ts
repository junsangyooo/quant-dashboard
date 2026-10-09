// SCR-HOME · 오프라인 (Figma 1:53557) — 예시-값표 §3 (16:20): the shell answered at 16:10, then
// the connection dropped. Numbers stay; '16:10 불러온 값 · 연결 안 됨' and header '연결 안 됨'.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { paperResponses } from '../parts/responses';

const bundle = {
  id: 'home.offline',
  now: NOW_1007,
  // Poll quickly so the dropped connection shows within a second or two.
  shellPollMs: 1_000,
  responses: {
    ...paperResponses(),
    '/api/shell': [
      shellOf({ now: NOW_1007, mode: 'paper', status: OK_0830_1007 }),
      { $network: 'down' },
    ],
  },
} satisfies FixtureBundle;

export default bundle;
