// SCR-HOME · 미국 계좌가 빔 (no drawing): 7/1 09:07 of the 출시 첫날 world (값표 §4) on 미국 $ — the
// 09:05 Korean buy is filled, the 09:10 conversion has not run, so no money has reached 미국 계좌:
// '$0.00' and '미국 계좌는 비어 있어요' instead of a graph and rows. 전체 shows the 한국 tile with
// 9,999,252원 · ▼ −748원 and the 미국 tile '비어 있음'.
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { shellOf } from '../parts/common';
import { homeUsEmpty } from '../parts/morning';

const NOW = kst('2026-07-01', '09:07');

const bundle = {
  id: 'home.us-empty',
  now: NOW,
  search: 'account=us',
  responses: {
    '/api/home': homeUsEmpty(),
    '/api/shell': shellOf({
      now: NOW,
      mode: 'paper',
      status: { kind: 'ok', lastCheckAt: kst('2026-07-01', '08:30') },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
