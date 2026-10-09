// SCR-HISTORY error (spec only): /api/history fails with no earlier answer — '기록을 못 불러왔어요' +
// '다시 불러오기' in the list's place.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';

const NOW = NOW_1007;

const bundle = {
  id: 'history.error',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/history': { $status: 500, $body: { error: 'internal' } },
  },
} satisfies FixtureBundle;

export default bundle;
