// SCR-RULES · [예시] 종목 모멘텀 (Figma 1:61226 · 1:62197): the node-card flow. Open at
// /rules/momentum.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { ruleIndexHalf, ruleMomentum, rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'rules.momentum',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/rules': rulesList(),
    '/api/rules/index_half': ruleIndexHalf(),
    '/api/rules/momentum': ruleMomentum(),
  },
} satisfies FixtureBundle;

export default bundle;
