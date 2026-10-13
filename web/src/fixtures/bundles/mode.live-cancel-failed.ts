// SCR-MODE · 실전 · 취소 안 됨 (3단계, 그림 없음), 10/7 16:10: 실전이 켜진 채로 토스에 있던 22:30
// 매수의 취소가 안 됐어요(실전 중에도 tick이 취소를 요청해요: 장 끝에 남은 주문, 직접 처리로 닫은
// 계획의 주문). 헤더 '취소 안 됨 1', 배너, 빨간 카드가 먼저 오고 원화 · 달러 카드와 실전 끄기는
// 그대로예요. 취소 다시 시도 succeeds: the order becomes a cancel the next check carries out.
import type { ModeResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { LIVE_CASH, LIVE_PENDING_BUY, NOW, liveShell, modeLive } from '../ops';

const failed: ModeResponse = modeLive({
  cancelFailed: [{ ...LIVE_PENDING_BUY, failure: { reason: 'cancel-failed' } }],
  liveCash: LIVE_CASH,
});

const retried: ModeResponse = { ...failed, cancelFailed: null, cancelPending: [LIVE_PENDING_BUY] };

const bundle = {
  id: 'mode.live-cancel-failed',
  now: NOW,
  responses: {
    '/api/shell': {
      $afterWrite: 'POST /api/mode/cancel-retry',
      $before: liveShell({
        status: { kind: 'cancel-failed', count: 1 },
        banner: { kind: 'cancel-failed', market: 'US', side: 'buy', link: 'mode' },
      }),
      $after: liveShell(),
    },
    '/api/mode': { $afterWrite: 'POST /api/mode/cancel-retry', $before: failed, $after: retried },
    'POST /api/mode/cancel-retry': { cancelFailed: [], cancelPending: [LIVE_PENDING_BUY] },
    'POST /api/mode/paper': { $pending: true },
  },
} satisfies FixtureBundle;

export default bundle;
