// SCR-PLAN · 실전 · 넣은 돈 그대로 (D47·D48, 그림 없음), 10/7 16:10: '환전 제안' 칩과 바꿀 금액
// (약 1,500,000원 → 50:50), 예정의 '새로 들어온 돈 3,000,000원 · 다음 거래일 08:30부터 써요'.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { planLiveMix } from '../parts/plan';
import { homeLive } from '../parts/home';

const bundle = {
  id: 'plan.live-mix',
  now: NOW_1007,
  responses: {
    '/api/home': homeLive(),
    '/api/plan': planLiveMix(),
    '/api/shell': shellOf({ now: NOW_1007, mode: 'live', status: OK_0830_1007 }),
  },
} satisfies FixtureBundle;

export default bundle;
