// SCR-HOME · 실전 일부 실패, 다시 시도 없음 (spec only; banner as 1:57032) — 예시-값표 §3 실전
// 일부 실패 (10/8 08:40): Toss rejected the 10/7 22:30 미국 매수. Header '직접 할 일 1'.
import type { FixtureBundle } from '../types';
import { BANNER_PARTIAL_TODO, NOW_1008, shellOf } from '../parts/common';
import { liveTodoResponses } from '../parts/responses';

const bundle = {
  id: 'home.live-todo',
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
