// SCR-HISTORY error · 자료 낡음 (spec only, 값표 §3 시세 대기): the shell banner, and the 10/6 · 10/7
// calendar cells in 시세 대기; no 10/7 rebalance.
import type { FixtureBundle } from '../types';
import { BANNER_STALE, NOW_1007, shellOf } from '../parts/common';
import { historyStale } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'history.stale',
  now: NOW,
  responses: {
    '/api/shell': shellOf({
      now: NOW,
      mode: 'paper',
      status: { kind: 'check', count: 1 },
      banner: BANNER_STALE,
    }),
    '/api/history': historyStale(),
    '/api/rules': rulesList('quote-wait', 'quote-wait'),
  },
} satisfies FixtureBundle;

export default bundle;
