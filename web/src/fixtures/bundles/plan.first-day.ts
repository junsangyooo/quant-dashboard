// SCR-PLAN · 출시 첫날(규칙 1개) (Figma 1:57326) — 예시-값표 §4 (7/1 16:10): one card, no
// rule-share bar, '벗어남 흐름은 둘째 날부터' (인계 불일치 16: the 모멘텀 card is not there).
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { shellOf } from '../parts/common';
import { planFirstDay } from '../parts/plan';
import homeFirstDay from './home.first-day';

const NOW = kst('2026-07-01', '16:10');

const bundle = {
  id: 'plan.first-day',
  now: NOW,
  responses: {
    '/api/plan': planFirstDay(),
    '/api/home': homeFirstDay.responses['/api/home'],
    '/api/shell': shellOf({
      now: NOW,
      mode: 'paper',
      status: { kind: 'ok', lastCheckAt: kst('2026-07-01', '08:30') },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
