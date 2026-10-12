// 변동 분해 (no Figma frame): 3개월 기간 손익 +222,800원 = 시세·환율 + 배당 − 수수료.
import { describe, expect, it } from 'vitest';
import {
  WATERFALL,
  waterfallGeometry,
  type WaterfallStep,
} from '../../src/charts/geometry/waterfall';

const steps: WaterfallStep[] = [
  { key: 'start', label: 'start', kind: 'anchor', value: 10_021_000 },
  { key: 'deposit', label: 'deposit', kind: 'cashflow', value: 100_000 },
  { key: 'withdraw', label: 'withdraw', kind: 'cashflow', value: -100_000 },
  { key: 'market', label: 'market', kind: 'change', value: 206_825 },
  { key: 'dividend', label: 'dividend', kind: 'change', value: 16_243 },
  { key: 'fee', label: 'fee', kind: 'change', value: -268 },
  { key: 'end', label: 'end', kind: 'anchor', value: 10_243_800 },
];

describe('waterfall geometry', () => {
  const g = waterfallGeometry({ width: 350, steps });

  it('stacks one 32px row per step between the label and value columns', () => {
    expect(g.height).toBe(steps.length * WATERFALL.rowHeight);
    expect(g.barLeft).toBe(80);
    expect(g.barRight).toBe(246);
    expect(g.rows.map((r) => r.y)).toEqual([0, 32, 64, 96, 128, 160, 192]);
  });

  it('runs the total from start to end and checks it balances', () => {
    expect(g.rows.map((r) => r.total)).toEqual([
      10_021_000, 10_121_000, 10_021_000, 10_227_825, 10_244_068, 10_243_800, 10_243_800,
    ]);
    expect(g.balanced).toBe(true);
    const wrongEnd: WaterfallStep = { key: 'end', label: 'end', kind: 'anchor', value: 1 };
    expect(
      waterfallGeometry({ width: 350, steps: [...steps.slice(0, -1), wrongEnd] }).balanced,
    ).toBe(false);
  });

  it('chains each bar from the previous total (connectors meet)', () => {
    for (let i = 1; i < g.rows.length; i++) {
      const prev = g.rows[i - 1];
      const row = g.rows[i];
      if (!prev || !row?.bar) continue;
      const start = row.value >= 0 ? row.bar.x : row.bar.x + row.bar.w;
      expect(start).toBeCloseTo(prev.edge, 1);
    }
  });

  it('colors cash flows gray and changes by sign; anchors are ticks', () => {
    expect(g.rows.map((r) => r.tone)).toEqual([
      'anchor',
      'cash',
      'cash',
      'gain',
      'gain',
      'loss',
      'anchor',
    ]);
    expect(g.rows[0]?.bar).toBeNull();
    expect(g.rows[0]?.tick).not.toBeNull();
    expect(g.rows[3]?.bar?.w).toBeGreaterThan(0);
  });

  it('keeps every bar inside the bar column', () => {
    for (const r of g.rows) {
      if (r.bar) {
        expect(r.bar.x).toBeGreaterThanOrEqual(g.barLeft);
        expect(r.bar.x + r.bar.w).toBeLessThanOrEqual(g.barRight + 0.01);
      }
    }
  });
});

describe('waterfall from zero (손익 나눠 보기: 한국 + 미국 + 환율 효과 = 전체 손익)', () => {
  const split: WaterfallStep[] = [
    { key: 'kr', label: '한국 계좌', kind: 'change', value: 484_683 },
    { key: 'us', label: '미국 계좌', kind: 'change', value: -207_291 },
    { key: 'fx', label: '환율 효과', kind: 'change', value: -33_592 },
    { key: 'total', label: '전체 손익', kind: 'anchor', value: 243_800 },
  ];
  const g = waterfallGeometry({ width: 350, steps: split });

  it('starts the first bar at zero, which is inside the range', () => {
    // Range 0 … 484,683 padded 8% on both sides: zero sits 8/116 of the way along the column.
    const zero = g.barLeft + ((g.barRight - g.barLeft) * 0.08) / 1.16;
    const first = g.rows[0];
    expect(first?.bar?.x).toBeCloseTo(zero, 1);
    expect(first?.bar?.w).toBeGreaterThan(0);
    expect(g.rows.map((r) => r.total)).toEqual([484_683, 277_392, 243_800, 243_800]);
    expect(g.rows.map((r) => r.tone)).toEqual(['gain', 'loss', 'loss', 'anchor']);
  });

  it('balances from zero to the last anchor, and catches a wrong total', () => {
    expect(g.balanced).toBe(true);
    const wrong: WaterfallStep = { ...split[3], value: 243_801 } as WaterfallStep;
    expect(waterfallGeometry({ width: 350, steps: [...split.slice(0, 3), wrong] }).balanced).toBe(
      false,
    );
  });
});
