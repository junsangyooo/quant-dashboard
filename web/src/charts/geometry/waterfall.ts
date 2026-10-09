// Horizontal waterfall (변동 분해 시트): 기간 시작 → 입금 → 출금 → 시세·환율 → 배당 →
// 수수료 → 지금. Not drawn in Figma (기획 §5 '그림 없음'); built from the spec text with the
// chart vocabulary of the other primitives: 12px bars, 2px target ticks, 1px dashed connectors.
// Cash flows are gray (입출금은 손익이 아니다); market changes use gain/loss colors.
import { linear, r2 } from './scale';

export type WaterfallKind = 'anchor' | 'cashflow' | 'change';

export interface WaterfallStep {
  key: string;
  label: string;
  kind: WaterfallKind;
  /** anchor: absolute value; cashflow/change: signed delta. */
  value: number;
}

export const WATERFALL = {
  rowHeight: 32,
  barHeight: 12,
  tickWidth: 2,
  tickHeight: 20,
  labelWidth: 72,
  valueWidth: 96,
  columnGap: 8,
} as const;

export type WaterfallTone = 'anchor' | 'cash' | 'gain' | 'loss' | 'flat';

export interface WaterfallRow {
  key: string;
  label: string;
  kind: WaterfallKind;
  value: number;
  /** Row top. */
  y: number;
  tone: WaterfallTone;
  /** Bar for deltas (x is the left edge); tick for anchors. */
  bar: { x: number; w: number } | null;
  tick: { x: number } | null;
  /** Running total after this row. */
  total: number;
  /** x where the next row starts (connector). */
  edge: number;
}

export interface WaterfallGeometry {
  barLeft: number;
  barRight: number;
  height: number;
  rows: WaterfallRow[];
  /** Sum of deltas equals end − start (consistency check for the sheet). */
  balanced: boolean;
}

const MIN_BAR = 1;

/**
 * Bar between the previous total `a` and the new total `b`. A change too small to see is
 * drawn 1px wide but still starts at `a`, so the chain of bars stays connected.
 */
function barBox(a: number, b: number): { x: number; w: number } {
  const w = Math.abs(b - a);
  if (w >= MIN_BAR) return { x: r2(Math.min(a, b)), w: r2(w) };
  return { x: r2(b < a ? a - MIN_BAR : a), w: MIN_BAR };
}

export function waterfallGeometry(options: {
  width: number;
  steps: readonly WaterfallStep[];
}): WaterfallGeometry {
  const { width, steps } = options;
  const { rowHeight, labelWidth, valueWidth, columnGap } = WATERFALL;
  const barLeft = labelWidth + columnGap;
  const barRight = width - valueWidth - columnGap;

  // Running totals: anchors reset the total, deltas move it.
  const totals: number[] = [];
  let running = 0;
  for (const s of steps) {
    running = s.kind === 'anchor' ? s.value : running + s.value;
    totals.push(running);
  }
  const lo = Math.min(...totals);
  const hi = Math.max(...totals);
  const pad = (hi - lo) * 0.08 || Math.max(Math.abs(hi) * 0.001, 1);
  const x = linear([lo - pad, hi + pad], [barLeft, barRight]);

  const rows = steps.map((s, i): WaterfallRow => {
    const total = totals[i] ?? 0;
    const prev = i === 0 ? total : (totals[i - 1] ?? total);
    const y = i * rowHeight;
    if (s.kind === 'anchor') {
      return {
        ...s,
        y,
        total,
        tone: 'anchor',
        bar: null,
        tick: { x: r2(x(total)) },
        edge: r2(x(total)),
      };
    }
    const a = x(prev);
    const b = x(total);
    const tone: WaterfallTone =
      s.kind === 'cashflow' ? 'cash' : s.value > 0 ? 'gain' : s.value < 0 ? 'loss' : 'flat';
    return {
      ...s,
      y,
      total,
      tone,
      bar: s.value === 0 ? null : barBox(a, b),
      tick: null,
      edge: r2(b),
    };
  });

  const first = steps[0];
  const last = steps.at(-1);
  const deltas = steps.filter((s) => s.kind !== 'anchor').reduce((sum, s) => sum + s.value, 0);
  const balanced =
    first?.kind === 'anchor' && last?.kind === 'anchor'
      ? Math.abs(first.value + deltas - last.value) < 0.5
      : true;

  return { barLeft, barRight, height: steps.length * rowHeight, rows, balanced };
}
