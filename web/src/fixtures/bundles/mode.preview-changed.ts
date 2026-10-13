// SCR-MODE · 켜는 순간 다시 계산한 금액이 1% 이상 달라짐 (명세 error, 인계 13, 그림 없음): 켜지 않고
// 미리보기를 새 숫자로 바꾸고 '16:10 다시 계산 · 금액 바뀜', 체크 해제. The new numbers are fixture-only
// (값표에 없음): KOSPI200 ETF 36,250 → 37,100원이라 275 → 269주 (9,979,900원).
import type { ModeResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { NOW, PREVIEW_OK, modePaper, shell } from '../ops';

type OkPreview = Extract<NonNullable<ModeResponse['preview']>, { kind: 'ok' }>;

const [buyStage] = PREVIEW_OK.stages;
if (!buyStage) throw new Error('preview stages missing');

const recomputed: OkPreview = {
  ...PREVIEW_OK,
  computedAt: NOW,
  hash: 'preview-20261007-1610',
  basis: { ...PREVIEW_OK.basis, priceAt: NOW },
  stages: [
    {
      ...buyStage,
      orders: buyStage.orders.map((o) => ({ ...o, qty: 269, price: 37_100, amountKrw: 9_979_900 })),
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
