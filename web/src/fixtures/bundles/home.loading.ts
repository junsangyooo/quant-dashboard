// SCR-HOME · 첫 로드 (spec only, 그림 없음 — shaped like 1:53948): the header has loaded, the
// home answer never arrives, so card frames, titles and tabs show with skeleton bars.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';

const bundle = {
  id: 'home.loading',
  now: NOW_1007,
  responses: {
    '/api/shell': shellOf({ now: NOW_1007, mode: 'paper', status: OK_0830_1007 }),
    '/api/home': { $pending: true },
    '/api/plan': { $pending: true },
  },
} satisfies FixtureBundle;

export default bundle;
