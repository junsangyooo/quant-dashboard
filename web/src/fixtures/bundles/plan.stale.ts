// SCR-PLAN · 시세 대기 (Figma 1:56437) — 예시-값표 §3: both cards '시세 대기', hollow gauges,
// weights '—', '지금 · 시세 대기 · 주문 0건', lines broken from 10/5 (인계 명세 정정).
import type { FixtureBundle } from '../types';
import { BANNER_STALE, NOW_1007, shellOf } from '../parts/common';
import { staleResponses } from '../parts/responses';

const bundle = {
  id: 'plan.stale',
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
