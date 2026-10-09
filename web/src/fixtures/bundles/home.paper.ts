// SCR-HOME · 모의투자 기본 (Figma 1:51434 / 1:54828) — 예시-값표 §0, §1 (10/7 16:10 KST).
// Answers 자산 and 계획 of the same moment (period and drift variants included).
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { homePaper } from '../parts/home';
import { planPaper } from '../parts/plan';
import { paperResponses } from '../parts/responses';

const bundle = {
  id: 'home.paper',
  now: NOW_1007,
  responses: {
    ...paperResponses(),
    // The main answers again, so tests read them with their exact types.
    '/api/home': homePaper(),
    '/api/plan': planPaper(),
    '/api/shell': shellOf({ now: NOW_1007, mode: 'paper', status: OK_0830_1007 }),
  },
} satisfies FixtureBundle;

export default bundle;
