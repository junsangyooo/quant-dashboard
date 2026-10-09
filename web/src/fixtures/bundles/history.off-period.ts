// SCR-HISTORY.off-period (spec only): the 실전 ledger with 9/21–9/25 off — '끈 기간' row, hatched
// calendar band, ⏻ markers on the graph (기획 §5 상태 표).
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { historyOffPeriod } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'history.off-period',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'live', status: OK_0830_1007 }),
    '/api/history': historyOffPeriod(),
    '/api/rules': rulesList(),
  },
} satisfies FixtureBundle;

export default bundle;
