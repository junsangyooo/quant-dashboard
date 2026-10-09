// SCR-HISTORY · 모의투자 장부(실전 중) (Figma 1:58777): 실전 mode, opened from 모의투자·실전 with
// ?ledger=paper. × drops the parameter and shows the 실전 ledger (값표 §2; no 모의 체결 rows).
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import {
  LIVE_BUY_1007,
  LIVE_FX_1007,
  LIVE_SELL_1007,
  NOW_1007,
  OK_0830_1007,
  shellOf,
  stages1007,
} from '../parts/common';
import { day1007, paperDays } from '../parts/day';
import { historyLive, historyPaper } from '../parts/history';
import { rulesList } from '../parts/rules';

/** 실전 10/7 (값표 §2.2: 실제 체결 181,850원 · $125.22 at 1,381.5원). */
function liveDay1007() {
  const paper = day1007();
  const first = paper.events[0];
  return {
    ...paper,
    ledger: 'live' as const,
    total: 10_112_670,
    change: { amount: 14_670, pct: 0.15 },
    prev: '2026-09-09',
    events:
      first?.kind === 'in-progress'
        ? [{ ...first, stages: stages1007(LIVE_SELL_1007, LIVE_FX_1007, LIVE_BUY_1007) }]
        : [],
    basis: { ...paper.basis, fxRate: 1381.5, fxAt: kst('2026-10-07', '08:30') },
  };
}

const NOW = NOW_1007;

const bundle = {
  id: 'history.paper-ledger',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'live', status: OK_0830_1007 }),
    '/api/history?ledger=paper': historyPaper(),
    '/api/history?ledger=live': historyLive(),
    '/api/rules': rulesList(),
    ...paperDays(),
    '/api/day/2026-10-07?ledger=live': liveDay1007(),
  },
} satisfies FixtureBundle;

export default bundle;
