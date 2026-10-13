// SCR-HISTORY · 모의투자 장부(실전 중) (Figma 1:58777): 실전 mode, opened from 모의투자·실전 with
// ?ledger=paper. × drops the parameter and shows the 실전 ledger (값표 §2; no 모의 체결 rows).
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { LIVE_BUY_1007, NOW_1007, OK_0830_1007, liveStages1007, shellOf } from '../parts/common';
import { day1007, paperDays } from '../parts/day';
import { historyLive, historyPaper } from '../parts/history';
import { rulesList } from '../parts/rules';

/**
 * 실전 10/7 (D47): the 08:30 check buys S&P 500 ETF at 22:30 with the dollars the owner converted;
 * no conversion and no sale of the other market. The check card has no band: the whole rule's
 * drift across won and dollars triggers nothing on the live ledger.
 */
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
        ? [
            {
              ...first,
              stagesMini: ['pending' as const],
              // KOSPI200 ETF 140주 against S&P 500 ETF 56주 → 58주 (the dollars buy only US).
              weights: { ...first.weights, before: [51.2, 48.8], after: [50.4, 49.6] },
              stages: liveStages1007(LIVE_BUY_1007),
              feesKrw: 0,
            },
          ]
        : [],
    check: { at: kst('2026-10-07', '08:30'), result: 'in-progress' as const, band: null },
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
