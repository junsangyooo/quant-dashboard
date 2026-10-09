// SCR-DAY · AI 판단 사건 (no drawing; 화면-맞춤.md §3 and the 3년 발굴 proposal, 탐색 17:5855):
// 10/2 셀트리온 급락 확인 · Sonnet 두 번 · 두 번 다 '유지' · 주문 0건. Open at /day/2026-10-02.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { dayAi, paperDays } from '../parts/day';
import { historyPaper } from '../parts/history';
import { rulesListDiscovery } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'day.ai',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/history': historyPaper(),
    '/api/rules': rulesListDiscovery(),
    ...paperDays(),
    '/api/day/2026-10-02': dayAi(),
  },
} satisfies FixtureBundle;

export default bundle;
