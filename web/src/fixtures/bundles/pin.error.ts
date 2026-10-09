// SCR-PIN · 오류(남은 2회) (Figma 1:51328): 'PIN이 맞지 않아요 · 남은 시도 2회', 6칸 빨간 테두리로 비움.
// Later tries count down and lock at the fifth failure (16:40까지, 이 접속 위치).
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { NOW } from '../ops';

const bundle = {
  id: 'pin.error',
  now: NOW,
  responses: {
    'POST /api/auth/pin': [
      { $status: 403, $body: { error: 'pin', remaining: 2 } },
      { $status: 403, $body: { error: 'pin', remaining: 1 } },
      { $status: 403, $body: { error: 'locked', until: kst('2026-10-07', '16:40'), scope: 'ip' } },
    ],
  },
} satisfies FixtureBundle;

export default bundle;
