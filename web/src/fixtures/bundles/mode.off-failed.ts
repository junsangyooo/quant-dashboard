// SCR-MODE · 끄기 실패(주문 취소 안 됨) (Figma 1:64799) — 예시-값표 §3 실전 끄기 실패 (10/07 16:12):
// 모드는 모의투자로 바뀌었고 22:30 매수 주문 취소가 안 됨. 헤더 '취소 안 됨 1', 배너, 빨간 카드.
// 취소 다시 시도 succeeds: the card and the banner go away.
import type { ModeResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { LIVE_PENDING_BUY, TWO_LEDGERS, modePaper, shell } from '../ops';

const NOW = kst('2026-10-07', '16:12');

const failed: ModeResponse = modePaper({
  liveOff: { from: '2026-09-01', to: '2026-10-07', offAt: NOW },
  twoLedgers: TWO_LEDGERS,
  preflight: null,
  preview: null,
  cancelFailed: [{ ...LIVE_PENDING_BUY, failure: { reason: 'cancel-failed' } }],
  canTurnOn: { ok: false, cause: 'checks' },
});

const cleared: ModeResponse = { ...failed, cancelFailed: null };

const bundle = {
  id: 'mode.off-failed',
  now: NOW,
  responses: {
    '/api/shell': {
      $afterWrite: 'POST /api/mode/cancel-retry',
      $before: shell({
        now: NOW,
        modeChangedAt: NOW,
        status: { kind: 'cancel-failed', count: 1 },
        banner: { kind: 'cancel-failed', market: 'US', side: 'buy', link: 'mode' },
      }),
      $after: shell({ now: NOW, modeChangedAt: NOW }),
    },
    '/api/mode': { $afterWrite: 'POST /api/mode/cancel-retry', $before: failed, $after: cleared },
    'POST /api/mode/cancel-retry': { cancelFailed: [] },
  },
} satisfies FixtureBundle;

export default bundle;
