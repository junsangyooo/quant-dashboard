// SCR-PLAN · 실전 평상 (Figma 1:56152 / 1:57919) — 예시-값표 §2.2: '실제 체결' stage cards,
// 벗어남 흐름 9/1부터 with ⏻ 실전 켬.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { liveResponses } from '../parts/responses';

const bundle = {
  id: 'plan.live',
  now: NOW_1007,
  responses: {
    ...liveResponses(),
    '/api/shell': shellOf({ now: NOW_1007, mode: 'live', status: OK_0830_1007 }),
  },
} satisfies FixtureBundle;

export default bundle;
