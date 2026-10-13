// SCR-RULES · 지수 반반 · 실전 (D47·D48, 그림 없음): the live ledger runs on the money as deposited.
// 조건 '±2%p 넘으면 환전 제안' on 한국's share (61.8%: +11.8%p), 행동 '매수 주문 · 원화로 한국 ·
// 달러로 미국 종목' (one stage, no conversion), status '환전 제안'. Same 10/7 16:10 as plan.live-mix.
import type { FixtureBundle } from '../types';
import { NOW_1007, OK_0830_1007, shellOf } from '../parts/common';
import { ruleIndexLive, rulesListLive } from '../parts/rules';

const NOW = NOW_1007;

const bundle = {
  id: 'rules.live',
  now: NOW,
  responses: {
    '/api/shell': shellOf({ now: NOW, mode: 'live', status: OK_0830_1007 }),
    '/api/rules': rulesListLive(),
    '/api/rules/index_half': ruleIndexLive(),
  },
} satisfies FixtureBundle;

export default bundle;
