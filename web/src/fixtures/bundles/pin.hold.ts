// SCR-PIN · 새 로그인 닫힘 (CONTRACT.md 403 locked, scope 'hold', 그림 없음): 24시간에 틀린 PIN이
// 30회면 서버에서 `python -m autotrade.jobs unlock`을 할 때까지 새 로그인을 막아요. 끝나는 시각이 없어요.
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { NOW } from '../ops';

const bundle = {
  id: 'pin.hold',
  now: NOW,
  responses: {
    'POST /api/auth/pin': {
      $status: 403,
      $body: { error: 'locked', scope: 'hold', since: kst('2026-10-07', '15:52') },
    },
  },
} satisfies FixtureBundle;

export default bundle;
