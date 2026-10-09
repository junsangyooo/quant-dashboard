// SCR-DAY · 8/21 리밸런싱 (Figma 1:59915 · 1:60239) — 값표 §1.4: 10,084,600원 · +12,300원 · +0.12%,
// 전 52.3 : 47.7 → 후 50.2 : 49.8, 수수료 합계 206원. Open at /day/2026-08-21.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { paperDays } from '../parts/day';
import { historyPaper } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'day.0821',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/history': historyPaper(),
    '/api/rules': rulesList(),
    ...paperDays(),
  },
} satisfies FixtureBundle;

export default bundle;
