// SCR-RULES loading (spec only): /api/rules never answers — tile and card frames as skeletons.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';

const NOW = NOW_1007;

const bundle = {
  id: 'rules.loading',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/rules': { $pending: true },
  },
} satisfies FixtureBundle;

export default bundle;
