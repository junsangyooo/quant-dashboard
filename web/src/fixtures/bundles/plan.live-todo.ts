// SCR-PLAN · 실전 일부 실패(직접 할 일) (Figma 1:57032) — 예시-값표 §3 (10/8 08:40).
import type { FixtureBundle } from '../types';
import { BANNER_PARTIAL_TODO, NOW_1008, shellOf } from '../parts/common';
import { liveTodoResponses } from '../parts/responses';

const bundle = {
  id: 'plan.live-todo',
  now: NOW_1008,
  responses: {
    ...liveTodoResponses(),
    '/api/shell': shellOf({
      now: NOW_1008,
      mode: 'live',
      status: { kind: 'todo', count: 1 },
      banner: BANNER_PARTIAL_TODO,
    }),
  },
} satisfies FixtureBundle;

export default bundle;
