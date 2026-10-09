// SCR-PIN · 전체 상한 (명세 permission, 그림 없음): 어디서든 1시간에 20회 틀리면 그 1시간이 지날 때까지
// 새 로그인을 막아요 → 시계 아이콘 '시도가 많아요 · 42분 뒤 다시' (16:52까지, fixture value).
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { NOW } from '../ops';

const bundle = {
  id: 'pin.global-lock',
  now: NOW,
  responses: {
    'POST /api/auth/pin': {
      $status: 403,
      $body: { error: 'locked', until: kst('2026-10-07', '16:52'), scope: 'global' },
    },
  },
} satisfies FixtureBundle;

export default bundle;
