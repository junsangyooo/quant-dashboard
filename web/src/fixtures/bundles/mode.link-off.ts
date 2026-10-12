// SCR-MODE · 토스 연결 꺼짐 (3단계, 그림 없음): 서버 tick 줄에 AUTOTRADE_LIVE_ORDERS가 없어 tick이
// 토스를 보지 않아요(열쇠 1). 토스 연결 ✕는 원인과 할 일을, 자료 최신 ✕(계좌 사진 없음)는 '위 점검과 같은
// 원인'을 보여서 원인은 하나 — '점검 1개(토스 연결)'. 첫 주문은 계산되지 않고 켜기는 닫혀요.
import type { ModeResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { NOW, PREFLIGHT_OK, modePaper, shell } from '../ops';

const preflight: NonNullable<ModeResponse['preflight']> = PREFLIGHT_OK.map((row) => {
  if (row.id === 'toss-link') return { id: 'toss-link', ok: false, facts: { cause: 'env-off' } };
  if (row.id === 'freshness') {
    return {
      id: 'freshness',
      ok: false,
      facts: { source: 'toss-balance' },
      sameCauseAs: 'toss-link',
    };
  }
  return row;
});

const bundle = {
  id: 'mode.link-off',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/mode': modePaper({
      preflight,
      preview: { kind: 'not-computable', at: kst('2026-10-07', '16:10'), cause: 'other' },
      canTurnOn: { ok: false, cause: 'checks' },
    }),
  },
} satisfies FixtureBundle;

export default bundle;
