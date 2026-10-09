// SCR-HOME · 시세 대기 (Figma 1:52732) — 예시-값표 §3 (10/7 16:10, 미국 시세 10/2 기준).
import type { FixtureBundle } from '../types';
import { BANNER_STALE, NOW_1007, shellOf } from '../parts/common';
import { staleResponses } from '../parts/responses';

const bundle = {
  id: 'home.stale',
  now: NOW_1007,
  responses: {
    ...staleResponses(),
    '/api/shell': shellOf({
      now: NOW_1007,
      mode: 'paper',
      status: { kind: 'check', count: 1 },
      banner: BANNER_STALE,
    }),
  },
} satisfies FixtureBundle;

export default bundle;
