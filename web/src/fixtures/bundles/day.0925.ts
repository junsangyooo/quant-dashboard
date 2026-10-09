// SCR-DAY · 거래 없음 (한국 휴장) (Figma 1:60076) — 값표 §3: 10,152,400원 · +3,400원 · +0.03%,
// '한국 휴장 · 거래 없음'. Open at /day/2026-09-25.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { paperDays } from '../parts/day';
import { historyPaper } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'day.0925',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
    '/api/history': historyPaper(),
    '/api/rules': rulesList(),
    ...paperDays(),
  },
} satisfies FixtureBundle;

export default bundle;
