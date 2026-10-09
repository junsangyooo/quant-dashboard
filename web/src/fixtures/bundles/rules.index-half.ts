// SCR-RULES · 지수 반반 (Figma 1:60971 · 1:61916): six tiles. Open at /rules or /rules/index_half.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { ruleIndexHalf, ruleMomentum, rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'rules.index-half',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/rules': rulesList(),
    '/api/rules/index_half': ruleIndexHalf(),
    '/api/rules/momentum': ruleMomentum(),
  },
} satisfies FixtureBundle;

export default bundle;
