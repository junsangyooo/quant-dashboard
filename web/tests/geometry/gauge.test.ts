// Figma 디자인 page '반원 게이지' (1:54828, 1:51434): needle +0.2%p → tip (81.45, 24.14).
import { describe, expect, it } from 'vitest';
import { GAUGE, gaugeAngle, gaugeGeometry, polar } from '../../src/charts/geometry/gauge';

describe('gauge geometry', () => {
  it('maps ±4 %p onto a half turn from straight up', () => {
    expect(gaugeAngle(0)).toBe(0);
    expect(gaugeAngle(2)).toBe(45);
    expect(gaugeAngle(-4)).toBe(-90);
    expect(gaugeAngle(0.2)).toBeCloseTo(4.5, 6);
  });

  it('pins values beyond the axis to its ends', () => {
    expect(gaugeAngle(9)).toBe(90);
    expect(gaugeAngle(-12)).toBe(-90);
  });

  it('puts the needle tip where Figma draws it (+0.2%p)', () => {
    const g = gaugeGeometry(0.2);
    expect(g.needle).not.toBeNull();
    expect(g.needle?.x1).toBe(GAUGE.cx);
    expect(g.needle?.y1).toBe(GAUGE.cy);
    expect(g.needle?.x2).toBeCloseTo(81.45, 1);
    expect(g.needle?.y2).toBeCloseTo(24.14, 1);
  });

  it('places −2 · 0 · +2 labels on r 72 (Figma text centres)', () => {
    const [minus, zero, plus] = gaugeGeometry(0).labels;
    expect(minus?.x).toBeCloseTo(27.09, 1);
    expect(minus?.y).toBeCloseTo(17.09, 1);
    expect(zero?.x).toBeCloseTo(78, 6);
    expect(zero?.y).toBeCloseTo(-4, 6);
    expect(plus?.x).toBeCloseTo(128.91, 1);
    expect(plus?.y).toBeCloseTo(17.09, 1);
  });

  it('draws the ring 60 → 46.8 and the ±2 band over ±45°', () => {
    const g = gaugeGeometry(0);
    // Track starts at the left end of the outer ring and ends on the inner ring.
    expect(g.track.startsWith('M18 68')).toBe(true);
    const bandStart = polar(GAUGE.cx, GAUGE.cy, GAUGE.outerR, -45);
    expect(
      g.band.startsWith(
        `M${String(Math.round(bandStart.x * 100) / 100)} ${String(Math.round(bandStart.y * 100) / 100)}`,
      ),
    ).toBe(true);
    expect(GAUGE.innerR / GAUGE.outerR).toBeCloseTo(0.78, 6);
  });

  it('hides the needle without a value (시세 대기)', () => {
    expect(gaugeGeometry(null).needle).toBeNull();
  });
});
