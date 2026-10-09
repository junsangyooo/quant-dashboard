// SCR-HISTORY loading (spec only): /api/history never answers — card frames stay, skeletons inside.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';

const NOW = NOW_1007;

const bundle = {
  id: 'history.loading',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/history': { $pending: true },
  },
} satisfies FixtureBundle;

export default bundle;
