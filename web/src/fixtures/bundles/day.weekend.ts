// SCR-DAY · 주말 (spec only): '주말 · 확인 없음'. Open at /day/2026-10-04.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { dayWeekend, paperDays } from '../parts/day';
import { historyPaper } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'day.weekend',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/history': historyPaper(),
    '/api/rules': rulesList(),
    ...paperDays(),
    '/api/day/2026-10-04': dayWeekend(),
  },
} satisfies FixtureBundle;

export default bundle;
