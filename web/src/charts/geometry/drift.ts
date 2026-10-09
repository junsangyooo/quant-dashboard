// Drift chart (벗어남 흐름): one line per rule of the largest |deviation| in that rule,
// axis 0 · +2 · +4 %p (threshold × 2), shaded 0…+2 band, 0 baseline.
// 390 (Figma 1:55865): 350×120, plot 316, y(0)=116, y(4)=4, labels right-aligned.
// 1440 (Figma 1:57620, per rule card): 384×130, plot 344, y(0)=101.67, y(4)=28.33,
// labels start 10px after the plot.
import { linear, polyline, r2, timeScale } from './scale';
import type { LineSeries } from './lineChart';

export interface DriftLayout {
  height: number;
  gutter: number;
  /** y of 0 and of the axis top (threshold × 2). */
  y0: number;
  yTop: number;
  labelAlign: 'start' | 'end';
  labelGap: number;
}

export const DRIFT_390: DriftLayout = {
  height: 120,
  gutter: 34,
  y0: 116,
  yTop: 4,
  labelAlign: 'end',
  labelGap: 0,
};
export const DRIFT_1440: DriftLayout = {
  height: 130,
  gutter: 40,
  y0: 101.67,
  yTop: 28.33,
  labelAlign: 'start',
  labelGap: 10,
};

export interface DriftGeometry {
  plotW: number;
  x: (date: string) => number;
  y: (value: number) => number;
  band: { x: number; y: number; w: number; h: number };
  zeroY: number;
  ticks: { value: number; y: number; labelX: number; anchor: 'start' | 'end' }[];
  paths: { key: string; d: string }[];
  ends: { key: string; cx: number; cy: number }[];
  /** First date of each stale gap (where the line breaks), per series. */
  gaps: { key: string; date: string; x: number }[];
}

export function driftGeometry(options: {
  width: number;
  layout: DriftLayout;
  start: string;
  end: string;
  series: readonly LineSeries[];
  threshold?: number;
}): DriftGeometry {
  const { width, layout, start, end, series, threshold = 2 } = options;
  const top = threshold * 2;
  const plotW = width - layout.gutter;
  const x = timeScale(start, end, plotW);
  const yRaw = linear([0, top], [layout.y0, layout.yTop]);
  // Keep a line on the frame even past the axis top.
  const y = (v: number) => Math.max(0, Math.min(layout.height, yRaw(v)));
  const labelX = layout.labelAlign === 'start' ? plotW + layout.labelGap : width;

  const gaps: DriftGeometry['gaps'] = [];
  for (const s of series) {
    s.points.forEach((p, i) => {
      if (p.value === null && (i === 0 || s.points[i - 1]?.value !== null)) {
        gaps.push({ key: s.key, date: p.date, x: r2(x(p.date)) });
      }
    });
  }

  return {
    plotW,
    x,
    y,
    band: {
      x: 0,
      y: r2(yRaw(threshold)),
      w: plotW,
      h: r2(layout.y0 - yRaw(threshold)),
    },
    zeroY: layout.y0,
    ticks: [0, threshold, top].map((v) => ({
      value: v,
      y: r2(yRaw(v)),
      labelX,
      anchor: layout.labelAlign,
    })),
    paths: series.map((s) => ({
      key: s.key,
      d: polyline(s.points.map((p) => (p.value === null ? null : { x: x(p.date), y: y(p.value) }))),
    })),
    ends: series.flatMap((s) => {
      const last = s.points.at(-1);
      return last && last.value !== null
        ? [{ key: s.key, cx: r2(x(last.date)), cy: r2(y(last.value)) }]
        : [];
    }),
    gaps,
  };
}
