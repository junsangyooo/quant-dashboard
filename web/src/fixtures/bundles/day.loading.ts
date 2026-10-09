// SCR-DAY loading (spec only): /api/day never answers — date line kept, skeleton body. Open at /day/2026-08-21.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { historyPaper } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'day.loading',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/history': historyPaper(),
    '/api/rules': rulesList(),
    '/api/day/2026-08-21': { $pending: true },
  },
} satisfies FixtureBundle;

export default bundle;
