// SCR-PLAN · AI 규칙 카드 (Figma 탐색 17:7108 '계획 카드 · 3년 발굴 · 팔 조건 게이지 · 1440
// (제안)', 화면-맞춤.md ②·§6): the 모의투자 world with 3년 발굴 in place of [예시] 종목 모멘텀.
// The gauge is 'sell-condition' (0 고른 날 → 100 팔 조건, 80~100 확인 구간); the right side is
// '지수 대비 · 7/1부터 (%p)'. Fields the contract lacks are modeled per screens/Plan/proposed.ts.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { planDiscovery } from '../parts/plan';

const bundle = {
  id: 'plan.discovery',
  now: NOW_1007,
  responses: {
    '/api/plan': planDiscovery(),
    '/api/shell': shellOf({ now: NOW_1007, mode: 'paper', status: OK_0830_1007 }),
  },
} satisfies FixtureBundle;

export default bundle;
