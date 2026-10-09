// SCR-MODE · 모의투자 (Figma 1:64094 / 1:65140) — 예시-값표 §1.4 성적 · §1.6 첫 주문 미리보기
// (10/07 16:00): 점검 4줄 통과, 원화 현금 10,000,000원 → 환전 · 매수 4건. Turning live on answers
// what the 1단계 server always answers: 409 blocked · live-not-available (CONTRACT.md 쓰기).
import type { FixtureBundle } from '../types';
import { NOW, modePaper, shell } from '../ops';

const bundle = {
  id: 'mode.paper',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/mode': modePaper(),
    'POST /api/mode/live': {
      $status: 409,
      $body: { error: 'blocked', detail: { cause: 'live-not-available' } },
    },
  },
} satisfies FixtureBundle;

export default bundle;
