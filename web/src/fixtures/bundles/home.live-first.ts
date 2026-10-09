// SCR-HOME · 실전 첫 체결 전 (Figma 1:52213 / 1:55613) — 예시-값표 §2.1 (9/1 08:40).
// Follows the spec where 390 and 1440 differ (인계 불일치 8): '08:30 기준' chip, the 9/1 point
// with ⏻ 실전 켬, and a grey (cash) composition bar.
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { shellOf } from '../parts/common';
import { homeLiveFirst } from '../parts/home';

const NOW = kst('2026-09-01', '08:40');

const bundle = {
  id: 'home.live-first',
  now: NOW,
  responses: {
    '/api/home': homeLiveFirst(),
    '/api/shell': shellOf({
      now: NOW,
      mode: 'live',
      status: { kind: 'ok', lastCheckAt: kst('2026-09-01', '08:30') },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
