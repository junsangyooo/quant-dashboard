// SCR-RULES permission (spec only): no session → /pin?next=/rules/… (same rule after PIN).
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';

const NOW = NOW_1007;

const bundle = {
  id: 'rules.permission',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/rules': { $status: 403, $body: { error: 'session' } },
  },
} satisfies FixtureBundle;

export default bundle;
