// SCR-HOME · 세션 없음 (spec only): every /api answer is 403 'session', so the client goes to
// /pin?next=… and comes back after the PIN.
import type { FixtureBundle } from '../types';
import { NOW_1007 } from '../parts/common';

const denied = { $status: 403, $body: { error: 'session' } };

const bundle = {
  id: 'home.permission',
  now: NOW_1007,
  responses: {
    '/api/shell': denied,
    '/api/home': denied,
    '/api/plan': denied,
  },
} satisfies FixtureBundle;

export default bundle;
