// SCR-MODE · 실전 끄기 확인 (Figma 1:64669): 가운데 모달 '실전을 끌까요?' — 취소될 주문 '매수 · 미국 ·
// 22:30 대기 · S&P 500 ETF 2주 · 약 $124.80', '달러 현금 $125.67은 계좌에 남아요' (예시-값표 §2.2).
// [끄기] turns live off (no PIN); the next answers are the paper ledger after 16:12.
import type { ModeResponse } from '../../api/types';
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import {
  NOW,
  PREFLIGHT_OK,
  TWO_LEDGERS,
  liveHome,
  livePlan,
  liveShell,
  modePaper,
  modeLive,
  shell,
} from '../ops';

const OFF_AT = kst('2026-10-07', '16:12');

const afterOff: ModeResponse = modePaper({
  liveOff: { from: '2026-09-01', to: '2026-10-07', offAt: OFF_AT },
  twoLedgers: TWO_LEDGERS,
  preflight: PREFLIGHT_OK,
  // The live account now holds stocks: its first order is recomputed after turning off.
  preview: { kind: 'not-computable', at: OFF_AT, cause: 'other' },
  canTurnOn: { ok: false, cause: 'preview' },
});

const bundle = {
  id: 'mode.off-confirm',
  now: NOW,
  responses: {
    '/api/shell': {
      $afterWrite: 'POST /api/mode/paper',
      $before: liveShell(),
      $after: shell({ modeChangedAt: OFF_AT }),
    },
    '/api/mode': { $afterWrite: 'POST /api/mode/paper', $before: modeLive(), $after: afterOff },
    '/api/plan?ledger=live': livePlan(),
    '/api/home?ledger=live': liveHome(),
    'POST /api/mode/paper': { mode: 'paper', cancelFailed: [] },
  },
} satisfies FixtureBundle;

export default bundle;
