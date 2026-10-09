// SCR-HOME · 다른 기기에서 바뀜 (Figma 1:53948) — 예시-값표 §3 (10/7 16:12): the page shows 실전,
// another device switches to 모의투자 at 16:11; the next shell poll sees it, every number turns
// into a skeleton, and the 모의투자 ledger arrives 3 s later.
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { OK_0830_1007, shellOf } from '../parts/common';
import { homeLive, homePaper, paperBreakdown } from '../parts/home';
import { planLive, planPaper } from '../parts/plan';

// The page opens at 16:11 (실전); the poll at 16:12 reports the switch made at 16:11.
const OPENED = kst('2026-10-07', '16:11');
const NOW = kst('2026-10-07', '16:12');

const bundle = {
  id: 'home.other-device',
  now: OPENED,
  shellPollMs: 1_500,
  responses: {
    // A focus refetch right after load must not switch yet: the third answer does.
    '/api/shell': [
      shellOf({ now: OPENED, mode: 'live', status: OK_0830_1007 }),
      shellOf({ now: OPENED, mode: 'live', status: OK_0830_1007 }),
      shellOf({
        now: NOW,
        mode: 'paper',
        status: OK_0830_1007,
        modeChangedAt: kst('2026-10-07', '16:11'),
      }),
    ],
    '/api/home?ledger=live': homeLive(),
    '/api/home?ledger=paper': { $delayMs: 3_000, $then: homePaper() },
    '/api/home/breakdown': paperBreakdown('3m'),
    '/api/plan?ledger=live': planLive(),
    '/api/plan?ledger=paper': { $delayMs: 3_000, $then: planPaper() },
  },
} satisfies FixtureBundle;

export default bundle;
