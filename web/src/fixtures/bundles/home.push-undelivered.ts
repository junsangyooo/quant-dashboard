// SCR-HOME · 알림 안 닿음 (spec only, 그림 없음): weekly summary is on but no device confirmed a
// delivery for 9 days → banner '알림이 9일째 기기에 안 닿아요 · 시험 알림 ›'. Numbers as §1.1.
import type { FixtureBundle } from '../types';
import { NOW_1007, shellOf } from '../parts/common';
import { paperResponses } from '../parts/responses';

const bundle = {
  id: 'home.push-undelivered',
  now: NOW_1007,
  responses: {
    ...paperResponses(),
    '/api/shell': shellOf({
      now: NOW_1007,
      mode: 'paper',
      status: { kind: 'check', count: 1 },
      banner: { kind: 'push-undelivered', days: 9, link: 'account' },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
