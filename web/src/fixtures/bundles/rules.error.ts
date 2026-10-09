// SCR-RULES error (spec only): '규칙을 못 불러왔어요' + '다시 불러오기'.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';

const NOW = NOW_1007;

const bundle = {
  id: 'rules.error',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/rules': { $status: 500, $body: { error: 'internal' } },
  },
} satisfies FixtureBundle;

export default bundle;
