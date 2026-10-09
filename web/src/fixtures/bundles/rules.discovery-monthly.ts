// SCR-RULES · 3년 발굴 · 매달 1일 (Figma 탐색 17:7808, proposal): '흐름' 칩 (4 lanes), this lane
// selected. Open at /rules/discovery_3y (or ?lane=monthly).
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { discoveryResponses, ruleIndexHalf, rulesListDiscovery } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'rules.discovery-monthly',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/rules': rulesListDiscovery(),
    '/api/rules/index_half': ruleIndexHalf(),
    ...discoveryResponses('monthly'),
  },
} satisfies FixtureBundle;

export default bundle;
