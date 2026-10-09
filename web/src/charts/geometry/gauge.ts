// Semicircle gauge (계획 카드 '반원 게이지', Figma 1:54828 / 1:51434 …).
// Frame 156×80, centre (78,68), ring r 60 → 46.8 (inner ratio 0.78), axis ±4%p over 180°,
// band ±2%p, needle 44 long × 3 wide, hub r 5, tick labels on r 72.
import { clamp, r2, type Pt } from './scale';

export const GAUGE = {
  width: 156,
  height: 80,
  cx: 78,
  cy: 68,
  outerR: 60,
  innerR: 46.8,
  needleLength: 44,
  needleWidth: 3,
  hubR: 5,
  labelR: 72,
  span: 4,
  band: 2,
} as const;

/** Degrees from straight up, clockwise positive. Values beyond the axis pin to its end. */
export function gaugeAngle(value: number, span: number = GAUGE.span): number {
  return (clamp(value, -span, span) / span) * 90;
}

export function polar(cx: number, cy: number, r: number, deg: number): Pt {
  const a = (deg * Math.PI) / 180;
  return { x: cx + r * Math.sin(a), y: cy - r * Math.cos(a) };
}

function pt(p: Pt): string {
  return `${String(r2(p.x))} ${String(r2(p.y))}`;
}

/** Ring sector between two angles (degrees from up, a0 < a1). */
export function annularSector(
  cx: number,
  cy: number,
  rOuter: number,
  rInner: number,
  a0: number,
  a1: number,
): string {
  const large = a1 - a0 > 180 ? 1 : 0;
  return [
    `M${pt(polar(cx, cy, rOuter, a0))}`,
    `A${String(rOuter)} ${String(rOuter)} 0 ${String(large)} 1 ${pt(polar(cx, cy, rOuter, a1))}`,
    `L${pt(polar(cx, cy, rInner, a1))}`,
    `A${String(rInner)} ${String(rInner)} 0 ${String(large)} 0 ${pt(polar(cx, cy, rInner, a0))}`,
    'Z',
  ].join('');
}

/**
 * The same sector inset by `inset` px on every edge, so a stroke of width 2×inset drawn on it
 * reproduces Figma's INSIDE stroke (the ±2%p band has a 1px border/strong edge).
 */
export function insetSector(
  cx: number,
  cy: number,
  rOuter: number,
  rInner: number,
  a0: number,
  a1: number,
  inset: number,
): string {
  const ro = rOuter - inset;
  const ri = rInner + inset;
  const dOuter = (Math.asin(inset / ro) * 180) / Math.PI;
  const dInner = (Math.asin(inset / ri) * 180) / Math.PI;
  const large = a1 - a0 > 180 ? 1 : 0;
  return [
    `M${pt(polar(cx, cy, ro, a0 + dOuter))}`,
    `A${String(r2(ro))} ${String(r2(ro))} 0 ${String(large)} 1 ${pt(polar(cx, cy, ro, a1 - dOuter))}`,
    `L${pt(polar(cx, cy, ri, a1 - dInner))}`,
    `A${String(r2(ri))} ${String(r2(ri))} 0 ${String(large)} 0 ${pt(polar(cx, cy, ri, a0 + dInner))}`,
    'Z',
  ].join('');
}

export interface GaugeLabel {
  value: number;
  x: number;
  y: number;
}

export interface GaugeGeometry {
  track: string;
  band: string;
  bandEdge: string;
  /** null when there is no current value (시세 대기, 첫 확인 전): needle hidden, hub hollow. */
  needle: { x1: number; y1: number; x2: number; y2: number } | null;
  hub: { cx: number; cy: number; r: number };
  labels: GaugeLabel[];
}

export function gaugeGeometry(value: number | null): GaugeGeometry {
  const { cx, cy, outerR, innerR, needleLength, hubR, labelR, span, band } = GAUGE;
  const bandDeg = (band / span) * 90;
  let needle: GaugeGeometry['needle'] = null;
  if (value !== null) {
    const tip = polar(cx, cy, needleLength, gaugeAngle(value));
    needle = { x1: cx, y1: cy, x2: r2(tip.x), y2: r2(tip.y) };
  }
  const labels = [-band, 0, band].map((v) => {
    const p = polar(cx, cy, labelR, gaugeAngle(v));
    return { value: v, x: r2(p.x), y: r2(p.y) };
  });
  return {
    track: annularSector(cx, cy, outerR, innerR, -90, 90),
    band: annularSector(cx, cy, outerR, innerR, -bandDeg, bandDeg),
    bandEdge: insetSector(cx, cy, outerR, innerR, -bandDeg, bandDeg, 0.5),
    needle,
    hub: { cx, cy, r: hubR },
    labels,
  };
}
