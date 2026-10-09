// SCR-PIN · PIN 없음 (CONTRACT.md 403 no-pin): 첫 PIN은 웹에서 만들지 않고 서버 CLI로만 정해요.
import type { FixtureBundle } from '../types';
import { NOW } from '../ops';

const bundle = {
  id: 'pin.no-pin',
  now: NOW,
  responses: {
    'POST /api/auth/pin': { $status: 403, $body: { error: 'no-pin' } },
  },
} satisfies FixtureBundle;

export default bundle;
