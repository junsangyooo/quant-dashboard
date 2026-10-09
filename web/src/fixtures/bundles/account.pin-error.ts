// SCR-ACCOUNT · PIN 바꾸기 오류 (명세 error, 그림 없음): 현재 PIN이 틀리면 403 current-pin →
// '현재 PIN이 맞지 않아요', 그 칸 비움. ('두 PIN이 달라요' is checked before sending.)
import type { FixtureBundle } from '../types';
import { NOW, account, shell } from '../ops';

const bundle = {
  id: 'account.pin-error',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/account': account(),
    'POST /api/account/pin': { $status: 403, $body: { error: 'current-pin' } },
  },
} satisfies FixtureBundle;

export default bundle;
