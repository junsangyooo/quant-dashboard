// SCR-MODE · 성적 기록 30일 미만 (Figma 1:65110, 성적 카드만) — 예시-값표 §1.4 끝 '7/16 가정': 확인 12회 ·
// 리밸런싱 0회 · 실패 0회 · 모의 체결 6건, 수익률 없음. The rest is the 1단계 server's answer
// (점검·미리보기 없음, 실전 켜기 409 live-not-available), not the short record.
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { PERFORMANCE_SHORT, modePaper, shell } from '../ops';

const NOW = kst('2026-07-16', '16:10');

const bundle = {
  id: 'mode.short',
  now: NOW,
  responses: {
    '/api/shell': shell({
      now: NOW,
      status: { kind: 'ok', lastCheckAt: kst('2026-07-16', '08:30') },
    }),
    '/api/mode': modePaper({
      performance: PERFORMANCE_SHORT,
      preflight: null,
      preview: null,
      canTurnOn: { ok: false, cause: 'live-not-available' },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
