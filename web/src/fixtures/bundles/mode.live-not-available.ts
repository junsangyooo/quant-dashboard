// SCR-MODE · 1단계 (CONTRACT.md: canTurnOn 항상 live-not-available, 점검·미리보기 null): 성적은 그대로,
// 켜기 칸은 비활성 + '토스 주문 연결 뒤 켤 수 있어요'. A forced request still gets 409 blocked.
import type { FixtureBundle } from '../types';
import { NOW, modePaper, shell } from '../ops';

const bundle = {
  id: 'mode.live-not-available',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/mode': modePaper({
      preflight: null,
      preview: null,
      canTurnOn: { ok: false, cause: 'live-not-available' },
    }),
    'POST /api/mode/live': {
      $status: 409,
      $body: { error: 'blocked', detail: { cause: 'live-not-available' } },
    },
  },
} satisfies FixtureBundle;

export default bundle;
