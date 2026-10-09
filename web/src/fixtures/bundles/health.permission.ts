// SCR-HEALTH · 세션 없음 (명세 permission): 403 session → 입장(SCR-PIN) → PIN 뒤 /health 로 복귀.
import type { FixtureBundle } from '../types';
import { NO_SESSION, NOW, account, healthTodo, shell } from '../ops';

const SIGN_IN = 'POST /api/auth/pin';

const bundle = {
  id: 'health.permission',
  now: NOW,
  responses: {
    '/api/shell': { $afterWrite: SIGN_IN, $before: NO_SESSION, $after: shell() },
    '/api/health': { $afterWrite: SIGN_IN, $before: NO_SESSION, $after: healthTodo() },
    '/api/account': account(),
    'POST /api/auth/pin': { $noContent: true },
  },
} satisfies FixtureBundle;

export default bundle;
