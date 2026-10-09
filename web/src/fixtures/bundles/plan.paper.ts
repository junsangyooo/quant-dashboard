// SCR-PLAN · 모의투자 기본 (Figma 1:55865 / 1:57620) — 예시-값표 §1.3·§1.4 (10/7 16:10).
// Answers 계획 and 자산 of the same moment (drift and period variants included).
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { paperResponses } from '../parts/responses';

const bundle = {
  id: 'plan.paper',
  now: NOW_1007,
  responses: {
    ...paperResponses(),
    '/api/shell': shellOf({ now: NOW_1007, mode: 'paper', status: OK_0830_1007 }),
  },
} satisfies FixtureBundle;

export default bundle;
