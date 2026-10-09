// SCR-DAY · 10/7 리밸런싱 중 (spec only) — 값표 §1.4: 매도·환전 모의 체결, 매수 22:30 대기 (no fill
// label on the waiting card), '진행 중 단계 보기'. Open at /day/2026-10-07.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { paperDays } from '../parts/day';
import { historyPaper } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'day.1007',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/history': historyPaper(),
    '/api/rules': rulesList(),
    ...paperDays(),
  },
} satisfies FixtureBundle;

export default bundle;
