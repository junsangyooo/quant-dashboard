// SCR-HISTORY empty (spec only): 모의투자 before its first check (6/30 18:00) — '첫 확인 뒤 그래프가
// 그려져요', 타일 0회 · 0원 · 0회, empty calendar, one '시작 · 10,000,000원' row.
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { shellOf } from '../parts/common';
import { historyEmpty } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = kst('2026-06-30', '18:00');

const bundle = {
  id: 'history.empty',
  now: NOW,
  responses: {
    '/api/shell': shellOf({
      now: NOW,
      mode: 'paper',
      status: { kind: 'before-first', firstCheckAt: kst('2026-07-01', '08:30') },
    }),
    '/api/history': historyEmpty(),
    '/api/rules': rulesList(),
  },
} satisfies FixtureBundle;

export default bundle;
