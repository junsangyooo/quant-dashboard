// SCR-HOME · 확인 실패 (spec only; wording as 작동 1:63518) — 예시-값표 §3 실행(확인) 실패,
// 10/7 09:00: the 08:30 check failed (no quote), retry 09:30. Numbers are the last valuation
// (10/6 16:00) and the plan chip/card keep the last good check (see parts/home.ts).
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { shellOf } from '../parts/common';
import { homeCheckFailed } from '../parts/home';

const NOW = kst('2026-10-07', '09:00');

const bundle = {
  id: 'home.check-failed',
  now: NOW,
  responses: {
    '/api/home': homeCheckFailed(),
    '/api/shell': shellOf({
      now: NOW,
      mode: 'paper',
      status: { kind: 'check-failed', at: kst('2026-10-07', '08:30') },
      banner: {
        kind: 'check-failed',
        at: kst('2026-10-07', '08:30'),
        retryAt: kst('2026-10-07', '09:30'),
        link: 'health',
      },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
