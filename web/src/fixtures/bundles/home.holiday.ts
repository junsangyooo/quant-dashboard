// SCR-HOME · 휴장 (spec only, 그림 없음): 10/9(금) 16:10, 한국 휴장(한글날). Plan line
// '휴장 · 한국 휴장 · 거래 없음 ›', card chip '휴장', no stage row, no banner. Numbers: see
// parts/home.ts homeHoliday (derived from 값표 §1, assumptions written there).
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { shellOf } from '../parts/common';
import { homeHoliday } from '../parts/home';
import { planHoliday } from '../parts/plan';

const NOW = kst('2026-10-09', '16:10');

const bundle = {
  id: 'home.holiday',
  now: NOW,
  responses: {
    '/api/home': homeHoliday(),
    '/api/plan': planHoliday(),
    '/api/shell': shellOf({
      now: NOW,
      mode: 'paper',
      status: { kind: 'ok', lastCheckAt: kst('2026-10-09', '08:30') },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
