// SCR-HISTORY permission (spec only): no session — the client goes to /pin?next= with ledger and
// filters kept in the address.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';

const NOW = NOW_1007;

const bundle = {
  id: 'history.permission',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/history': { $status: 403, $body: { error: 'session' } },
  },
} satisfies FixtureBundle;

export default bundle;
