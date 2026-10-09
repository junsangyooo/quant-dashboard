// Deviation band (편차 띠 / 벗어남 띠): axis −4…+4 %p (threshold × 2), target band ±2 %p.
// Regular layout from SCR-DAY '그날 확인' (Figma 1:59915): 44 tall, axis 4px at y 20,
// band 16px at y 14, target tick 2×22 at y 11, points r 6 on y 22, labels above/below.
// Compact layout from 노드/D 조건 '벗어남 띠': 12 tall, no labels.
import { clamp, r2 } from './scale';

export interface DeviationLayout {
  height: number;
  centerY: number;
  axisH: number;
  bandH: number;
  targetW: number;
  targetH: number;
  pointR: number;
  /** Gap between a point's edge and the before→after connector. */
  connectorGap: number;
  labels: boolean;
}

export const DEVIATION_REGULAR: DeviationLayout = {
  height: 44,
  centerY: 22,
  axisH: 4,
  bandH: 16,
  targetW: 2,
  targetH: 22,
  pointR: 6,
  connectorGap: 2,
  labels: true,
};

export const DEVIATION_COMPACT: DeviationLayout = {
  height: 12,
  centerY: 6,
  axisH: 4,
  bandH: 8,
  targetW: 2,
  targetH: 12,
  pointR: 5,
  connectorGap: 2,
  labels: false,
};

/** Line arrowhead measured on the Figma export: 5px back, ±4.5px across. */
export const ARROW = { length: 5, spread: 4.5 } as const;

export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DeviationPoint {
  value: number;
  /** before = chart/drift fill; after = outlined accent (그날 확인 전·후). */
  kind: 'before' | 'after';
  label?: string | undefined;
}

export interface DeviationGeometry {
  axis: Rect;
  band: Rect;
  target: Rect;
  points: {
    kind: DeviationPoint['kind'];
    cx: number;
    cy: number;
    r: number;
    label?: string | undefined;
    labelY: number;
  }[];
  /** Line from the before point to the after point, with a line arrowhead at the after end. */
  connector: { x1: number; x2: number; y: number; arrow: string } | null;
  ends: { minX: number; maxX: number; y: number } | null;
}

/** x of a deviation value on an axis of `width` px spanning −span…+span. */
export function deviationX(value: number, width: number, span = 4): number {
  return ((clamp(value, -span, span) + span) / (2 * span)) * width;
}

export function deviationGeometry(options: {
  width: number;
  points: readonly DeviationPoint[];
  span?: number;
  band?: number;
  layout?: DeviationLayout;
}): DeviationGeometry {
  const { width, points, span = 4, band = 2, layout = DEVIATION_REGULAR } = options;
  const x = (v: number) => r2(deviationX(v, width, span));
  const cy = layout.centerY;
  const axis = { x: 0, y: cy - layout.axisH / 2, w: width, h: layout.axisH };
  const bandRect = {
    x: x(-band),
    y: cy - layout.bandH / 2,
    w: r2(x(band) - x(-band)),
    h: layout.bandH,
  };
  const target = {
    x: r2(x(0) - layout.targetW / 2),
    y: cy - layout.targetH / 2,
    w: layout.targetW,
    h: layout.targetH,
  };
  const placed = points.map((p) => ({
    kind: p.kind,
    cx: x(p.value),
    cy,
    r: layout.pointR,
    label: p.label,
    // before labels sit above the axis, after labels below (Figma y 0 and y 34).
    labelY: p.kind === 'before' ? 0 : cy + layout.pointR + 6,
  }));

  let connector: DeviationGeometry['connector'] = null;
  const before = placed.find((p) => p.kind === 'before');
  const after = placed.find((p) => p.kind === 'after');
  if (before && after) {
    const reach = layout.pointR + layout.connectorGap;
    const dir = Math.sign(after.cx - before.cx);
    if (Math.abs(after.cx - before.cx) > 2 * reach) {
      const x1 = r2(before.cx + dir * reach);
      const x2 = r2(after.cx - dir * reach);
      const back = r2(x2 - dir * ARROW.length);
      connector = {
        x1,
        x2,
        y: cy,
        arrow: `${String(back)},${String(cy - ARROW.spread)} ${String(x2)},${String(cy)} ${String(back)},${String(cy + ARROW.spread)}`,
      };
    }
  }

  return {
    axis,
    band: bandRect,
    target,
    points: placed,
    connector,
    ends: layout.labels ? { minX: 0, maxX: width, y: layout.height - 12 } : null,
  };
}
