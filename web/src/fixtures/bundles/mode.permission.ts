// SCR-MODE · 세션 없음 (명세 permission): 403 session → 입장 → PIN 뒤 /mode 로 복귀.
import type { FixtureBundle } from '../types';
import { NO_SESSION, NOW, modePaper, shell } from '../ops';

const SIGN_IN = 'POST /api/auth/pin';

const bundle = {
  id: 'mode.permission',
  now: NOW,
  responses: {
    '/api/shell': { $afterWrite: SIGN_IN, $before: NO_SESSION, $after: shell() },
    '/api/mode': { $afterWrite: SIGN_IN, $before: NO_SESSION, $after: modePaper() },
    'POST /api/auth/pin': { $noContent: true },
  },
} satisfies FixtureBundle;

export default bundle;
