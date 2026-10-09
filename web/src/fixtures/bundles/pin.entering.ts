// SCR-PIN · 입력 중 (Figma 1:51276): 워드마크 · 'PIN 6자리' · 6칸 · 키패드 · '잊었을 때'. 계좌 숫자 0개 —
// the page itself reads nothing; the shell below is what the page after entry asks for.
// The PIN is accepted (204 + session).
import type { FixtureBundle } from '../types';
import { NOW, shell } from '../ops';

const bundle = {
  id: 'pin.entering',
  now: NOW,
  responses: {
    'POST /api/auth/pin': { $noContent: true },
    '/api/shell': shell(),
  },
} satisfies FixtureBundle;

export default bundle;
