// Figma '구성 막대' 1440 (1:54939, 344 wide), 390 출금 대기 (1:52441, 310 wide) and
// SCR-DAY '전후 비중' (1:59964, 284 wide).
import { describe, expect, it } from 'vitest';
import {
  compositionGeometry,
  hatchLines,
  segmentLabelAnchor,
  targetGeometry,
} from '../../src/charts/geometry/composition';

describe('composition bar geometry', () => {
  it('splits the width minus 2px gaps by weight (1440: 275.74 · 62.22 · 2.04)', () => {
    const boxes = compositionGeometry(344, [
      { key: 'index', value: 81.1 },
      { key: 'momentum', value: 18.3 },
      { key: 'cash', value: 0.6 },
    ]);
    expect(boxes).toEqual([
      { key: 'index', x: 0, w: 275.74 },
      { key: 'momentum', x: 277.74, w: 62.22 },
      { key: 'cash', x: 341.96, w: 2.04 },
    ]);
  });

  it('places the pending segment last (출금 대기 15.2px at 294.8)', () => {
    const boxes = compositionGeometry(310, [
      { key: 'index', value: 75.7 },
      { key: 'momentum', value: 18.5 },
      { key: 'cash', value: 0.8 },
      { key: 'pending', value: 5.0 },
    ]);
    expect(boxes.map((b) => [b.x, b.w])).toEqual([
      [0, 230.13],
      [232.13, 56.24],
      [290.37, 2.43],
      [294.8, 15.2],
    ]);
  });

  it('keeps a nonzero segment at least 2px and the total exact', () => {
    const boxes = compositionGeometry(310, [
      { key: 'index', value: 81.1 },
      { key: 'momentum', value: 18.3 },
      { key: 'cash', value: 0.6 },
    ]);
    expect(boxes.at(-1)?.w).toBe(2);
    const last = boxes.at(-1);
    expect((last?.x ?? 0) + (last?.w ?? 0)).toBeCloseTo(310, 1);
  });

  it('skips empty segments', () => {
    expect(
      compositionGeometry(100, [
        { key: 'a', value: 0 },
        { key: 'b', value: 1 },
      ]),
    ).toEqual([{ key: 'b', x: 0, w: 100 }]);
  });

  it('hatches at 45° every 6px, clipped to the box', () => {
    const d = hatchLines({ x: 294.8, w: 15.2 }, 12);
    const nums = [...d.matchAll(/-?\d+(\.\d+)?/g)].map((m) => Number(m[0]));
    const xs = nums.filter((_, i) => i % 2 === 0);
    const ys = nums.filter((_, i) => i % 2 === 1);
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(294.8);
    expect(Math.max(...xs)).toBeLessThanOrEqual(310);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(0);
    expect(Math.max(...ys)).toBeLessThanOrEqual(12);
    // Lines start at −6, 0, 6 and 12 px from the box's left edge (Figma 1:52441).
    expect(d.match(/M/g)?.length).toBe(4);
  });

  it('draws the target marker and band of 전후 비중 (목표 50% ±2%p)', () => {
    expect(targetGeometry(284, 0.5, [0.48, 0.52])).toEqual({
      marker: { x: 141, w: 2 },
      band: { x: 136.32, w: 11.36 },
    });
  });

  it('puts segment labels 8px inside the bar ends', () => {
    const boxes = compositionGeometry(284, [
      { key: 'kospi', value: 52.3 },
      { key: 'sp500', value: 47.7 },
    ]);
    expect(boxes.map((b) => b.w)).toEqual([147.49, 134.51]);
    expect(segmentLabelAnchor(boxes, 0)).toEqual({ x: 8, anchor: 'start' });
    expect(segmentLabelAnchor(boxes, 1)).toEqual({ x: 276, anchor: 'end' });
  });
});
