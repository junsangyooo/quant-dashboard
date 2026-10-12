// SCR-HOME · 첫 체결 전 (모의투자, no drawing): 7/1 08:40 of the 출시 첫날 world (값표 §4) — the
// first check planned the buys and nothing is filled yet, so there is no P&L and no 계좌 switch
// (it comes with the first fill). The live paper ledger is here on 10/13 08:40.
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { shellOf } from '../parts/common';
import { homeBeforeFill } from '../parts/morning';

const NOW = kst('2026-07-01', '08:40');

const bundle = {
  id: 'home.before-fill',
  now: NOW,
  responses: {
    '/api/home': homeBeforeFill(),
    '/api/shell': shellOf({
      now: NOW,
      mode: 'paper',
      status: { kind: 'ok', lastCheckAt: kst('2026-07-01', '08:30') },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
