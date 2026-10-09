// SCR-DAY error (spec only): '그날 기록을 못 불러왔어요' + '다시 불러오기' under the date line. Open at /day/2026-08-21.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { historyPaper } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'day.error',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/history': historyPaper(),
    '/api/rules': rulesList(),
    '/api/day/2026-08-21': { $status: 500, $body: { error: 'internal' } },
  },
} satisfies FixtureBundle;

export default bundle;
