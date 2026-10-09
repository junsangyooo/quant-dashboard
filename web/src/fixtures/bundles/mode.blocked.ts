// SCR-MODE · 켤 수 없음 (Figma 1:64956) — 예시-값표 §3 작동 점검 1: 미국 시세 10/02 기준. 점검 ✕ 둘이
// 같은 원인이라 '점검 1개(미국 시세)', 첫 주문 계산 안 됨 · 10/07 16:00 조회, 켜기 칸 비활성.
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { NOW, PREFLIGHT_BLOCKED, modePaper, staleShell } from '../ops';

const bundle = {
  id: 'mode.blocked',
  now: NOW,
  responses: {
    '/api/shell': staleShell(),
    '/api/mode': modePaper({
      preflight: PREFLIGHT_BLOCKED,
      preview: { kind: 'not-computable', at: kst('2026-10-07', '16:00'), cause: 'stale' },
      canTurnOn: { ok: false, cause: 'checks' },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
