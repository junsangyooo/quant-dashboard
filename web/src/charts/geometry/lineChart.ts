// Asset line chart geometry.
//
// Home style (SCR-HOME '자산 변동', Figma 1:54828 / 1:51434): plot 300 (1440) or 180 (390)
// tall, right gutter 52 with caption tick labels starting 10px after the plot, an end dot,
// and a separate 28px event band below (markers centred on their date).
// History style (SCR-HISTORY '자산 그래프', Figma 1:59344 / 1:58215): plot 200 or 120 tall
// with an axis line at the bottom, gutter 44 with micro labels right-aligned, event dots on
// the line, dashed stems down to markers that drop to a second row when they would overlap.
import type { EventKind } from '../../components/Markers';
import { addDays, addMonths, clamp, daysBetween, linear, polyline, r2, timeScale } from './scale';

export interface LinePoint {
  date: string;
  /** null = no value (stale gap); the line breaks there. */
  value: number | null;
}

export interface LineSeries {
  key: string;
  points: readonly LinePoint[];
}

export interface LineLayout {
  plotHeight: number;
  gutter: number;
  /** 'start': labels begin `labelGap` after the plot; 'end': right-aligned to the frame. */
  labelAlign: 'start' | 'end';
  labelGap: number;
}

export const LINE_HOME_390: LineLayout = {
  plotHeight: 180,
  gutter: 52,
  labelAlign: 'start',
  labelGap: 10,
};
export const LINE_HOME_1440: LineLayout = {
  plotHeight: 300,
  gutter: 52,
  labelAlign: 'start',
  labelGap: 10,
};
export const LINE_HISTORY_390: LineLayout = {
  plotHeight: 120,
  gutter: 44,
  labelAlign: 'end',
  labelGap: 0,
};
export const LINE_HISTORY_1440: LineLayout = {
  plotHeight: 200,
  gutter: 44,
  labelAlign: 'end',
  labelGap: 0,
};

// ── y axis ─────────────────────────────────────────────────────────────────

const NICE = [1, 2, 2.5, 5, 10] as const;

/** Nearest of 1, 2, 2.5, 5 × 10^k. */
export function niceStep(raw: number): number {
  if (!(raw > 0)) return 1;
  const e = Math.floor(Math.log10(raw));
  const base = 10 ** e;
  const f = raw / base;
  let best: number = NICE[0];
  for (const c of NICE) if (Math.abs(c - f) < Math.abs(best - f)) best = c;
  return best * base;
}

export interface YAxis {
  domain: [number, number];
  ticks: number[];
}

/**
 * Three ticks centred on the data, one step of room below the lowest tick and ¾ step above
 * the highest — this lands within a few px of every Figma frame (1000만·1020만·1040만 for
 * 3개월, 1000만·1010만·1020만 for the history range). The domain always covers the data.
 */
export function niceYAxis(values: readonly number[]): YAxis {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return { domain: [0, 1], ticks: [] };
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  const range = max - min || Math.max(Math.abs(max) * 0.01, 1);
  const step = niceStep(range / 2.5);
  const mid = Math.round((min + max) / 2 / step) * step;
  const ticks = [mid - step, mid, mid + step];
  let lo = mid - 2 * step;
  let hi = mid + 1.75 * step;
  if (min < lo) lo = min - step / 4;
  if (max > hi) hi = max + step / 4;
  return { domain: [lo, hi], ticks };
}

// ── plot ───────────────────────────────────────────────────────────────────

export interface LineGeometry {
  plotW: number;
  x: (date: string) => number;
  y: (value: number) => number;
  ticks: { value: number; y: number; labelX: number; anchor: 'start' | 'end' }[];
  paths: { key: string; d: string }[];
  ends: { key: string; cx: number; cy: number }[];
}

export function lineGeometry(options: {
  width: number;
  layout: LineLayout;
  start: string;
  end: string;
  domain: readonly [number, number];
  ticks: readonly number[];
  series: readonly LineSeries[];
}): LineGeometry {
  const { width, layout, start, end, domain, ticks, series } = options;
  const plotW = width - layout.gutter;
  const x = timeScale(start, end, plotW);
  const y = linear(domain, [layout.plotHeight, 0]);
  const labelX = layout.labelAlign === 'start' ? plotW + layout.labelGap : width;
  return {
    plotW,
    x,
    y,
    ticks: ticks.map((v) => ({ value: v, y: r2(y(v)), labelX, anchor: layout.labelAlign })),
    paths: series.map((s) => ({
      key: s.key,
      d: polyline(s.points.map((p) => (p.value === null ? null : { x: x(p.date), y: y(p.value) }))),
    })),
    ends: series.flatMap((s) => {
      const last = [...s.points].reverse().find((p) => p.value !== null);
      return last?.value != null
        ? [{ key: s.key, cx: r2(x(last.date)), cy: r2(y(last.value)) }]
        : [];
    }),
  };
}

// ── date labels ────────────────────────────────────────────────────────────

/**
 * Home style: start-anchored steps (14 days, then 1, 2, 3, 6, 12 months) — the first step
 * that yields at most `max` labels including the end. 7/7→10/7 gives 7/7·8/7·9/7·10/7;
 * 9/1→10/7 gives 9/1·9/15·9/29·10/7 (예시 값표 2.2).
 */
export function anchoredDateTicks(start: string, end: string, max = 4): string[] {
  const steps: ((d: string, i: number) => string)[] = [
    (d, i) => addDays(d, 14 * i),
    ...[1, 2, 3, 6, 12].map((m) => (d: string, i: number) => addMonths(d, m * i)),
  ];
  for (const step of steps) {
    const out: string[] = [];
    for (let i = 0; ; i++) {
      const t = step(start, i);
      if (daysBetween(t, end) < 0) break;
      out.push(t);
    }
    if (out.at(-1) !== end) out.push(end);
    if (out.length <= max) return out;
  }
  return [start, end];
}

/** History style: first day of each month inside the range (7/1·8/1·9/1·10/1). */
export function monthStartTicks(start: string, end: string): string[] {
  const out: string[] = [];
  const [y, m] = start.split('-').map(Number) as [number, number];
  let year = y;
  let month = m;
  for (;;) {
    const t = `${String(year)}-${String(month).padStart(2, '0')}-01`;
    if (daysBetween(t, end) < 0) break;
    if (daysBetween(start, t) >= 0) out.push(t);
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return out;
}

export interface DateLabel {
  date: string;
  x: number;
  anchor: 'start' | 'middle' | 'end';
}

/** Labels at the plot edges hug the edge; the rest are centred on their date. */
export function placeDateLabels(
  dates: readonly string[],
  x: (d: string) => number,
  plotW: number,
): DateLabel[] {
  return dates.map((date) => {
    const px = r2(x(date));
    const anchor = px <= 0.5 ? 'start' : px >= plotW - 0.5 ? 'end' : 'middle';
    return { date, x: px, anchor };
  });
}

// ── events ─────────────────────────────────────────────────────────────────

export interface ChartEvent {
  date: string;
  kind: EventKind;
  /** Accessible name, e.g. '8/21(금) 리밸런싱'. */
  label: string;
}

export const MARKER = 24;

export interface BandMarker {
  /** Centre x. */
  x: number;
  events: ChartEvent[];
}

/**
 * Home style event band: markers centred on their date. Markers whose centres are closer
 * than `groupBelow` px merge into one grouped marker ('[n]', 기획 §5 사건 띠). Figma keeps
 * 9/30 and 10/7 apart at 22.7px on 390, so the default threshold is 20.
 */
export function bandMarkers(
  events: readonly ChartEvent[],
  x: (d: string) => number,
  groupBelow = 20,
): BandMarker[] {
  const sorted = [...events].sort((a, b) => daysBetween(b.date, a.date));
  const out: BandMarker[] = [];
  for (const e of sorted) {
    const px = x(e.date);
    const last = out.at(-1);
    if (last && px - last.x < groupBelow) {
      last.events.push(e);
      last.x = r2(last.events.reduce((s, ev) => s + x(ev.date), 0) / last.events.length);
    } else {
      out.push({ x: r2(px), events: [e] });
    }
  }
  return out;
}

export interface StemMarker {
  event: ChartEvent;
  /** Date x on the axis. */
  x: number;
  /** Marker box left, clamped inside the plot. */
  left: number;
  row: number;
  top: number;
}

export const STEM = {
  firstGap: 12,
  rowPitch: 30,
  labelGap: 12,
  labelHeight: 12,
  bottomPad: 2,
} as const;

/** History style: stems from the axis; a marker drops a row while it would overlap. */
export function stemMarkers(
  events: readonly ChartEvent[],
  x: (d: string) => number,
  plotW: number,
  plotHeight: number,
  minGap = 4,
): StemMarker[] {
  const sorted = [...events].sort((a, b) => daysBetween(b.date, a.date));
  const rowRight: number[] = [];
  return sorted.map((event) => {
    const px = x(event.date);
    const left = clamp(px - MARKER / 2, 0, plotW - MARKER);
    let row = rowRight.findIndex((right) => left >= right + minGap);
    if (row === -1) row = rowRight.length;
    rowRight[row] = left + MARKER;
    return {
      event,
      x: r2(px),
      left: r2(left),
      row,
      top: plotHeight + STEM.firstGap + row * STEM.rowPitch,
    };
  });
}

/** y of the date labels and total frame height for the history style. */
export function historyFrame(plotHeight: number, markers: readonly StemMarker[]) {
  const rows = Math.max(1, ...markers.map((m) => m.row + 1));
  const labelY = plotHeight + STEM.firstGap + (rows - 1) * STEM.rowPitch + MARKER + STEM.labelGap;
  return { rows, labelY, height: labelY + STEM.labelHeight + STEM.bottomPad };
}

/** Value of a series on a date (for event dots on the line). */
export function valueOn(series: LineSeries, date: string): number | null {
  return series.points.find((p) => p.date === date)?.value ?? null;
}
