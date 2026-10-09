// SCR-HISTORY · 모의투자 기본 (Figma 1:58215 · 1:59344) — 예시-값표 §1.4 (10/7 16:10 KST).
// Every event day answers too, so the 1440 그날 panel and ‹ › move between them.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { paperDays } from '../parts/day';
import { historyPaper } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'history.paper',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/history': historyPaper(),
    '/api/rules': rulesList(),
    ...paperDays(),
  },
} satisfies FixtureBundle;

export default bundle;
