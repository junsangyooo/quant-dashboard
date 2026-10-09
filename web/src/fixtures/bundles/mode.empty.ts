// SCR-MODE · 모의투자 첫 확인 전 (명세 empty, 그림 없음): 6/30 16:10, '아직 모의투자 기록 없음 · 첫 확인
// 7/1(수) 08:30'. 점검·미리보기는 1단계 서버처럼 없음, 켜기는 live-not-available.
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { modePaper, shell } from '../ops';

const NOW = kst('2026-06-30', '16:10');
const FIRST = kst('2026-07-01', '08:30');

const bundle = {
  id: 'mode.empty',
  now: NOW,
  responses: {
    '/api/shell': shell({ now: NOW, status: { kind: 'before-first', firstCheckAt: FIRST } }),
    '/api/mode': modePaper({
      performance: {
        since: '2026-07-01',
        checks: 0,
        rebalances: 0,
        failures: 0,
        paperFills: 0,
        ret: null,
        baselinePct: null,
      },
      preflight: null,
      preview: null,
      canTurnOn: { ok: false, cause: 'live-not-available' },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
