// SCR-DAY permission (spec only): an alert link with no session goes to PIN and back to the
// same day and ledger (/pin?next=/day/2026-08-21…). Open at /day/2026-08-21.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { historyPaper } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'day.permission',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/history': historyPaper(),
    '/api/rules': rulesList(),
    '/api/day/2026-08-21': { $status: 403, $body: { error: 'session' } },
  },
} satisfies FixtureBundle;

export default bundle;
