// SCR-MODE · 켜는 순간 다시 계산한 금액이 1% 이상 달라짐 (명세 error, 인계 13, 그림 없음): 켜지 않고
// 미리보기를 새 숫자로 바꾸고 '16:10 다시 계산 · 금액 바뀜', 체크 해제. The new numbers are fixture-only
// (값표에 없음): 환율 1,382.4 → 1,401.2원이라 S&P 500 ETF 46 → 45주, 미국 매수 $3,399.60 → $3,337.20.
import type { ModeResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { NOW, PREVIEW_OK, modePaper, shell } from '../ops';

type OkPreview = Extract<NonNullable<ModeResponse['preview']>, { kind: 'ok' }>;

const [fxStage, buyStage] = PREVIEW_OK.stages;
if (!fxStage || !buyStage) throw new Error('preview stages missing');

const recomputed: OkPreview = {
  ...PREVIEW_OK,
  computedAt: NOW,
  hash: 'preview-20261007-1610',
  basis: { ...PREVIEW_OK.basis, fxRate: 1401.2, fxAt: kst('2026-10-07', '16:10') },
  stages: [
    {
      ...fxStage,
      orders: fxStage.orders.map((o) => ({
        ...o,
        fx: { krw: 4_682_000, usd: 3341, rate: 1401.2 },
      })),
    },
    {
      ...buyStage,
      orders: buyStage.orders.map((o) =>
        o.instrument?.id === 'US:SPYM' ? { ...o, qty: 45, amountUsd: 2808 } : o,
      ),
    },
  ],
};

const bundle = {
  id: 'mode.preview-changed',
  now: NOW,
  responses: {
    '/api/shell': shell(),
    '/api/mode': modePaper(),
    'POST /api/mode/live': {
      $status: 409,
      $body: { error: 'preview-changed', preview: recomputed },
    },
  },
} satisfies FixtureBundle;

export default bundle;
