// Figma SCR-DAY 390 '벗어남 띠' (1:60048): axis 326 wide, −4…+4 %p, band ±2,
// before +2.3 at 256.73, after +0.1 at 167.07, connector 175.07 → 248.72.
import { describe, expect, it } from 'vitest';
import {
  DEVIATION_COMPACT,
  deviationGeometry,
  deviationX,
} from '../../src/charts/geometry/deviation';

describe('deviation band geometry', () => {
  const g = deviationGeometry({
    width: 326,
    points: [
      { value: 2.3, kind: 'before', label: '전' },
      { value: 0.1, kind: 'after', label: '후' },
    ],
  });

  it('maps −4…+4 onto the width', () => {
    expect(deviationX(-4, 326)).toBe(0);
    expect(deviationX(0, 326)).toBe(163);
    expect(deviationX(4, 326)).toBe(326);
    expect(deviationX(9, 326)).toBe(326);
  });

  it('draws the ±2 band and the target tick like Figma', () => {
    expect(g.band).toEqual({ x: 81.5, y: 14, w: 163, h: 16 });
    expect(g.target).toEqual({ x: 162, y: 11, w: 2, h: 22 });
    expect(g.axis).toEqual({ x: 0, y: 20, w: 326, h: 4 });
  });

  it('places the before and after points', () => {
    const before = g.points.find((p) => p.kind === 'before');
    const after = g.points.find((p) => p.kind === 'after');
    expect(before?.cx).toBeCloseTo(256.73, 1);
    expect(after?.cx).toBeCloseTo(167.07, 1);
    expect(before?.r).toBe(6);
    expect(before?.labelY).toBe(0);
    expect(after?.labelY).toBe(34);
  });

  it('connects them with a 2px gap and an arrowhead at the after end', () => {
    expect(g.connector?.x1).toBeCloseTo(248.72, 1);
    expect(g.connector?.x2).toBeCloseTo(175.07, 1);
    const arrow = (g.connector?.arrow ?? '').split(/[ ,]/).map(Number);
    const expected = [180.07, 17.5, 175.07, 22, 180.07, 26.5];
    expect(arrow).toHaveLength(6);
    arrow.forEach((v, i) => {
      expect(v).toBeCloseTo(expected[i] ?? NaN, 1);
    });
  });

  it('puts the −4%p / +4%p labels on the last row', () => {
    expect(g.ends).toEqual({ minX: 0, maxX: 326, y: 32 });
  });

  it('has a compact layout without labels (노드/D 조건)', () => {
    const c = deviationGeometry({
      width: 190,
      points: [{ value: 2.4, kind: 'before' }],
      layout: DEVIATION_COMPACT,
    });
    expect(c.band).toEqual({ x: 47.5, y: 2, w: 95, h: 8 });
    expect(c.ends).toBeNull();
    expect(c.connector).toBeNull();
  });
});
