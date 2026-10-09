// SCR-HOME · 일부 실패 (Figma 1:53155) — 예시-값표 §3 (10/8 08:40): the 10/7 22:30 미국 매수
// failed (no quote) and goes again 10/8 22:30. Numbers as §1.1.
import type { FixtureBundle } from '../types';
import { BANNER_PARTIAL_RETRY, NOW_1008, shellOf } from '../parts/common';
import { partialResponses } from '../parts/responses';

const bundle = {
  id: 'home.partial',
  now: NOW_1008,
  responses: {
    ...partialResponses(),
    '/api/shell': shellOf({
      now: NOW_1008,
      mode: 'paper',
      status: { kind: 'check', count: 1 },
      banner: BANNER_PARTIAL_RETRY,
    }),
  },
} satisfies FixtureBundle;

export default bundle;
