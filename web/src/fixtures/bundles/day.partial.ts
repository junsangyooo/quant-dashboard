// SCR-DAY.partial (spec only) — 값표 §3 일부 실패 (10/8 08:40): the 10/7 22:30 buy failed (no quote),
// red card ✕ + '시세 응답 없음' + '다시 10/8 22:30', head ✓✓✕, chip '일부 실패'. Open at
// /day/2026-10-07; /day/2026-09-14 shows the '9/15 다시 · 체결' chip of a retried order.
import type { FixtureBundle } from '../types';
import { BANNER_PARTIAL_RETRY, NOW_1008, shellOf } from '../parts/common';
import { kst } from '../world';
import { day1007Partial, paperDays } from '../parts/day';
import { historyPartial } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = NOW_1008;

const bundle = {
  id: 'day.partial',
  now: NOW,
  responses: {
    '/api/shell': shellOf({
      now: NOW,
      mode: 'paper',
      status: { kind: 'ok', lastCheckAt: kst('2026-10-08', '08:30') },
      banner: BANNER_PARTIAL_RETRY,
    }),
    '/api/history': historyPartial(),
    '/api/rules': rulesList(),
    ...paperDays(),
    '/api/day/2026-10-07': day1007Partial(),
  },
} satisfies FixtureBundle;

export default bundle;
