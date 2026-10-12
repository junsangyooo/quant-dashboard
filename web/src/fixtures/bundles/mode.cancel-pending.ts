// SCR-MODE · 취소 요청 중 (3단계, 그림 없음): 16:12에 실전을 껐고, 토스에 있던 22:30 매수의 취소를
// 요청했어요. 웹은 토스를 부르지 않아서 다음 확인(5분 안)이 취소해요. 그 주문이 계좌를 바쁘게 해서
// 자료 최신이 ✕(토스 잔고 대조)이고 첫 주문은 계산되지 않으며, 켜기는 취소가 끝날 때까지 닫혀요.
import type { ModeResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { LIVE_PENDING_BUY, PREFLIGHT_OK, TWO_LEDGERS, modePaper, shell } from '../ops';

const OFF_AT = kst('2026-10-07', '16:12');
const NOW = kst('2026-10-07', '16:13');

const preflight: NonNullable<ModeResponse['preflight']> = PREFLIGHT_OK.map((row) =>
  row.id === 'freshness'
    ? { id: 'freshness', ok: false, facts: { source: 'toss-balance', basisDate: '2026-10-07' } }
    : row,
);

const bundle = {
  id: 'mode.cancel-pending',
  now: NOW,
  responses: {
    '/api/shell': shell({ now: NOW, modeChangedAt: OFF_AT }),
    '/api/mode': modePaper({
      liveOff: { from: '2026-09-01', to: '2026-10-07', offAt: OFF_AT },
      twoLedgers: TWO_LEDGERS,
      preflight,
      preview: { kind: 'not-computable', at: OFF_AT, cause: 'other' },
      cancelPending: [LIVE_PENDING_BUY],
      canTurnOn: { ok: false, cause: 'cancel-pending' },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
