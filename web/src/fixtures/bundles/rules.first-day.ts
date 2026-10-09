// SCR-RULES · 출시 첫날(규칙 1개) (Figma 1:61661) — 값표 §4: no selector, '자산의 99.6% · 목표 100%',
// 지금·결과 환전 09:10 ✓ · 매수 22:30 ⏳ (매도 0건 hidden, 인계 '작은 불일치' 6), '다음 확인 7/2 08:30'.
import type { FixtureBundle } from '../types';
import { kst } from '../world';
import { shellOf } from '../parts/common';
import { ruleIndexFirstDay } from '../parts/rules';
import { INDEX_HALF } from '../world';

const NOW = kst('2026-07-01', '16:10');

const bundle = {
  id: 'rules.first-day',
  now: NOW,
  responses: {
    '/api/shell': shellOf({
      now: NOW,
      mode: 'paper',
      status: { kind: 'ok', lastCheckAt: kst('2026-07-01', '08:30') },
    }),
    '/api/rules': {
      rules: [
        {
          rule: INDEX_HALF,
          share: { pct: 99.6, target: 100 },
          status: 'in-progress',
          example: true,
        },
      ],
    },
    '/api/rules/index_half': ruleIndexFirstDay(),
  },
} satisfies FixtureBundle;

export default bundle;
