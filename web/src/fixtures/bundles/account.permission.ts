// SCR-ACCOUNT · 세션 없음 (명세 permission): 403 session → 입장 → PIN 뒤 /account 로 복귀.
import type { FixtureBundle } from '../types';
import { NO_SESSION, NOW, account, shell } from '../ops';

const SIGN_IN = 'POST /api/auth/pin';

const bundle = {
  id: 'account.permission',
  now: NOW,
  responses: {
    '/api/shell': { $afterWrite: SIGN_IN, $before: NO_SESSION, $after: shell() },
    '/api/account': { $afterWrite: SIGN_IN, $before: NO_SESSION, $after: account() },
    'POST /api/auth/pin': { $noContent: true },
  },
} satisfies FixtureBundle;

export default bundle;
