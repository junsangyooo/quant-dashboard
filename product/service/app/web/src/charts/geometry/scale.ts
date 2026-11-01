// Shared scale helpers. Dates are KST calendar keys (YYYY-MM-DD); the x axis of every
// time chart is linear in calendar days (Figma: 7/7→10/7 = 92 days over the plot width).

const DATE_KEY = /^(\d{4})-(\d{2})-(\d{2})$/;
const DAY_MS = 86_400_000;

export function dayNumber(dateKey: string): number {
  const m = DATE_KEY.exec(dateKey);
  if (!m) throw new RangeError(`Expected YYYY-MM-DD, got ${dateKey}`);
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / DAY_MS;
}

export function daysBetween(from: string, to: string): number {
  return dayNumber(to) - dayNumber(from);
}

export function dateFromDayNumber(n: number): string {
  const d = new Date(n * DAY_MS);
  const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(d.getUTCDate()).padStart(2, '0');
  return `${String(d.getUTCFullYear())}-${mm}-${dd}`;
}

export function addDays(dateKey: string, days: number): string {
  return dateFromDayNumber(dayNumber(dateKey) + days);
}

/** Same day-of-month `months` later, clamped to the month's last day. */
export function addMonths(dateKey: string, months: number): string {
  const n = dayNumber(dateKey);
  const d = new Date(n * DAY_MS);
  const y = d.getUTCFullYear();
  const m = d.getUTCMonth() + months;
  const day = d.getUTCDate();
  const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  return dateFromDayNumber(Date.UTC(y, m, Math.min(day, last)) / DAY_MS);
}

/** 0 = Monday … 6 = Sunday. */
export function weekdayIndex(dateKey: string): number {
  return (new Date(dayNumber(dateKey) * DAY_MS).getUTCDay() + 6) % 7;
}

export function linear(domain: readonly [number, number], range: readonly [number, number]) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const k = d1 === d0 ? 0 : (r1 - r0) / (d1 - d0);
  return (v: number) => r0 + (v - d0) * k;
}

export function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

/** Two decimals keeps SVG paths stable and comparable with Figma's coordinates. */
export function r2(v: number): number {
  return Math.round(v * 100) / 100;
}

/** Time scale over [0, plotWidth] for the inclusive date range [start, end]. */
export function timeScale(start: string, end: string, plotWidth: number) {
  const span = Math.max(1, daysBetween(start, end));
  return (date: string) => (daysBetween(start, date) / span) * plotWidth;
}

export interface Pt {
  x: number;
  y: number;
}

/** Polyline path; `null` y values break the line (stale gaps). */
export function polyline(points: readonly (Pt | null)[]): string {
  let d = '';
  let pen = false;
  for (const p of points) {
    if (!p) {
      pen = false;
      continue;
    }
    d += `${pen ? 'L' : 'M'}${String(r2(p.x))} ${String(r2(p.y))}`;
    pen = true;
  }
  return d;
}
