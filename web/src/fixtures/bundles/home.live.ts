// SCR-HOME · 실전 평상 (Figma 1:51825 / 1:55222) — 예시-값표 §2.2 (10/7 16:10, 9/1부터 27거래일).
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { liveResponses } from '../parts/responses';

const bundle = {
  id: 'home.live',
  now: NOW_1007,
  responses: {
    ...liveResponses(),
    '/api/shell': shellOf({ now: NOW_1007, mode: 'live', status: OK_0830_1007 }),
  },
} satisfies FixtureBundle;

export default bundle;
