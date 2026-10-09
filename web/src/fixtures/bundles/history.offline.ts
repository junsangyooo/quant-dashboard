// SCR-HISTORY error with a last answer (spec only): the connection drops after the first load —
// the numbers stay and '16:10 불러온 값 · 연결 안 됨' sits by them.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { paperDays } from '../parts/day';
import { historyPaper } from '../parts/history';
import { rulesList } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'history.offline',
  now: NOW,
  shellPollMs: 1_000,
  responses: {
    '/api/shell': [
      shellOf({ now: NOW, mode: 'paper', status: OK_0830_1007 }),
      { $network: 'down' },
    ],
    '/api/history': historyPaper(),
    '/api/rules': rulesList(),
    ...paperDays(),
  },
} satisfies FixtureBundle;

export default bundle;
