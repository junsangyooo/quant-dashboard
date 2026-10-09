// SCR-RULES error · 자료 낡음 (spec only, 값표 §3 시세 대기): banner, status chip '시세 대기', '낡음'
// on 지금·결과 and on every '지금' box, deviation points hidden.
import type { FixtureBundle } from '../types';
import { BANNER_STALE, NOW_1007, shellOf } from '../parts/common';
import { ruleIndexStale, ruleMomentum, rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'rules.stale',
  now: NOW,
  responses: {
    '/api/shell': shellOf({
      now: NOW,
      mode: 'paper',
      status: { kind: 'check', count: 1 },
      banner: BANNER_STALE,
    }),
    '/api/rules': rulesList('quote-wait', 'quote-wait'),
    '/api/rules/index_half': ruleIndexStale(),
    '/api/rules/momentum': ruleMomentum('quote-wait'),
  },
} satisfies FixtureBundle;

export default bundle;
