// SCR-HOME · 빈 상태(첫 확인 전) (Figma 1:54699): 모의투자 before its first check (6/30 18:00),
// the start amount only. Follows 인계 '명세 정정': the plan line has no status chip.
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { shellOf } from '../parts/common';
import { homeEmpty } from '../parts/home';
import { planEmpty } from '../parts/plan';

const NOW = kst('2026-06-30', '18:00');

const bundle = {
  id: 'home.empty',
  now: NOW,
  responses: {
    '/api/home': homeEmpty(),
    '/api/plan': planEmpty(),
    '/api/shell': shellOf({
      now: NOW,
      mode: 'paper',
      status: { kind: 'before-first', firstCheckAt: kst('2026-07-01', '08:30') },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
