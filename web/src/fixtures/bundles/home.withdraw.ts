// SCR-HOME · 실전 출금 대기 (Figma 1:52342, drawn before the wait stopped no order) — 예시-값표
// §2.3 (10/7 16:10, 10/12까지 대기; the plan goes on, PHASE3.md 2.5).
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { withdrawResponses } from '../parts/responses';

const bundle = {
  id: 'home.withdraw',
  now: NOW_1007,
  responses: {
    ...withdrawResponses(),
    '/api/shell': shellOf({ now: NOW_1007, mode: 'live', status: OK_0830_1007 }),
  },
} satisfies FixtureBundle;

export default bundle;
