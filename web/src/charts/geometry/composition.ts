// Composition bar (구성 막대, Figma 1:54828 / 1:51434 / 1:52342): segments share the width
// minus 2px gaps, a nonzero segment is at least 2px, a pending (출금 대기) segment is
// hatched with 45° lines every 6px inside a 1px edge. The same bar with a target marker and
// target band draws the before/after weights (SCR-DAY '전후 비중', Figma 1:59915).
import { r2 } from './scale';

/** labelInset: segment labels sit 8px inside the bar ends (Figma 1:59964). */
export const COMPOSITION = { gap: 2, minWidth: 2, hatchPitch: 6, labelInset: 8 } as const;

export interface SegmentInput {
  key: string;
  /** Any non-negative weight; segments are normalised by their sum. */
  value: number;
}

export interface SegmentBox {
  key: string;
  x: number;
  w: number;
}

export function compositionGeometry(
  width: number,
  segments: readonly SegmentInput[],
  gap: number = COMPOSITION.gap,
  minWidth: number = COMPOSITION.minWidth,
): SegmentBox[] {
  const shown = segments.filter((s) => s.value > 0);
  if (shown.length === 0) return [];
  const total = shown.reduce((sum, s) => sum + s.value, 0);
  const available = width - gap * (shown.length - 1);
  const widths = shown.map((s) => Math.max(minWidth, (s.value / total) * available));
  // Take any excess created by the minimum width from the widest segment.
  const excess = widths.reduce((a, b) => a + b, 0) - available;
  if (excess > 0) {
    const widest = widths.indexOf(Math.max(...widths));
    widths[widest] = (widths[widest] ?? 0) - excess;
  }
  let x = 0;
  return shown.map((s, i) => {
    const w = widths[i] ?? 0;
    const box = { key: s.key, x: r2(x), w: r2(w) };
    x += w + gap;
    return box;
  });
}

/** 45° hatch lines ('/') inside a box, every `pitch` px along the bottom edge, clipped. */
export function hatchLines(
  box: { x: number; w: number },
  height: number,
  pitch: number = COMPOSITION.hatchPitch,
): string {
  const parts: string[] = [];
  const left = box.x;
  const right = box.x + box.w;
  for (let x0 = left - height; x0 < right; x0 += pitch) {
    // Line from (x0, height) to (x0 + height, 0); clip t ∈ [0, height] to x ∈ [left, right].
    const t0 = Math.max(0, left - x0);
    const t1 = Math.min(height, right - x0);
    if (t1 <= t0) continue;
    parts.push(
      `M${String(r2(x0 + t0))} ${String(r2(height - t0))}L${String(r2(x0 + t1))} ${String(r2(height - t1))}`,
    );
  }
  return parts.join('');
}

/** Label anchor inside a segment: first hugs its left end, last its right end, others centre. */
export function segmentLabelAnchor(
  boxes: readonly SegmentBox[],
  index: number,
  inset: number = COMPOSITION.labelInset,
): { x: number; anchor: 'start' | 'middle' | 'end' } | null {
  const box = boxes[index];
  if (!box) return null;
  if (index === 0 && boxes.length > 1) return { x: r2(box.x + inset), anchor: 'start' };
  if (index === boxes.length - 1 && boxes.length > 1)
    return { x: r2(box.x + box.w - inset), anchor: 'end' };
  return { x: r2(box.x + box.w / 2), anchor: 'middle' };
}

/** Target marker (2px) and target band for before/after weights. */
export function targetGeometry(width: number, target: number, band?: readonly [number, number]) {
  return {
    marker: { x: r2(target * width - 1), w: 2 },
    band: band ? { x: r2(band[0] * width), w: r2((band[1] - band[0]) * width) } : null,
  };
}
