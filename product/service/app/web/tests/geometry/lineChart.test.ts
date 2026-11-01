// Figma coordinates from the 디자인 page:
// SCR-HOME 1440 '그래프' 1:54865 (752×300, plot 700): 1000만 y 223.06, 1020만 141.88,
// 1040만 60.71; 7/7 → 10/7 is 92 days; first point 10,021,000 at y 214.53; end dot (700, 124.1).
import { describe, expect, it } from 'vitest';
import {
  LINE_HISTORY_1440,
  LINE_HOME_1440,
  LINE_HOME_390,
  anchoredDateTicks,
  lineGeometry,
  monthStartTicks,
  niceStep,
  niceYAxis,
  placeDateLabels,
  thinDateLabels,
} from '../../src/charts/geometry/lineChart';
import { timeScale } from '../../src/charts/geometry/scale';
import { edgeAxis } from '../../src/charts/geometry/mvpAxis';
import { paperDaily3m, paperDailySinceStart, untouchedDaily3m } from './chartSeries';

const FIGMA_HOME_DOMAIN = [9_810_418, 10_549_582] as const;
const values = (pts: readonly { value: number | null }[]) =>
  pts.flatMap((p) => (p.value === null ? [] : [p.value]));

describe('home line chart (1440)', () => {
  const g = lineGeometry({
    width: 752,
    layout: LINE_HOME_1440,
    start: '2026-07-07',
    end: '2026-10-07',
    domain: FIGMA_HOME_DOMAIN,
    ticks: [10_000_000, 10_200_000, 10_400_000],
    series: [{ key: 'mine', points: paperDaily3m }],
  });

  it('keeps a 52px right gutter and labels 10px after the plot', () => {
    expect(g.plotW).toBe(700);
    expect(g.ticks.map((t) => t.labelX)).toEqual([710, 710, 710]);
  });

  it('places the grid lines where Figma does', () => {
    const ys = g.ticks.map((t) => t.y);
    [223.06, 141.88, 60.71].forEach((y, i) => {
      expect(ys[i]).toBeCloseTo(y, 1);
    });
  });

  it('is linear in calendar days', () => {
    expect(g.x('2026-07-07')).toBe(0);
    expect(g.x('2026-08-21')).toBeCloseTo(342.39, 2);
    expect(g.x('2026-09-30')).toBeCloseTo(646.74, 2);
    expect(g.x('2026-10-07')).toBe(700);
  });

  it('starts and ends the line on the Figma points', () => {
    expect(g.paths[0]?.d.startsWith('M0 214.5')).toBe(true);
    expect(g.ends[0]).toMatchObject({ key: 'mine', cx: 700 });
    expect(g.ends[0]?.cy).toBeCloseTo(124.1, 1);
  });
});

describe('y axis rule', () => {
  it('picks 1, 2, 2.5, 5 × 10^k steps', () => {
    expect(niceStep(210_576)).toBe(200_000);
    expect(niceStep(125_520)).toBe(100_000);
    expect(niceStep(2_400)).toBe(2_500);
    expect(niceStep(0)).toBe(1);
  });

  it('gives 1000만·1020만·1040만 for the 3개월 range (Figma 1:54865)', () => {
    const axis = niceYAxis([...values(paperDaily3m), ...values(untouchedDaily3m)]);
    expect(axis.ticks).toEqual([10_000_000, 10_200_000, 10_400_000]);
    expect(axis.domain).toEqual([9_800_000, 10_550_000]);
  });

  it('gives 1000만·1010만·1020만 since start (Figma 1:60255)', () => {
    expect(niceYAxis(values(paperDailySinceStart)).ticks).toEqual([
      10_000_000, 10_100_000, 10_200_000,
    ]);
  });

  it('always covers the data', () => {
    const axis = niceYAxis([100, 101, 5_000]);
    expect(axis.domain[0]).toBeLessThanOrEqual(100);
    expect(axis.domain[1]).toBeGreaterThanOrEqual(5_000);
  });
});

describe('date labels', () => {
  it('anchors monthly steps on the start date', () => {
    expect(anchoredDateTicks('2026-07-07', '2026-10-07')).toEqual([
      '2026-07-07',
      '2026-08-07',
      '2026-09-07',
      '2026-10-07',
    ]);
  });

  it('uses two-week steps for a short record (예시 값표 2.2: 9/1·9/15·9/29·10/7)', () => {
    expect(anchoredDateTicks('2026-09-01', '2026-10-07')).toEqual([
      '2026-09-01',
      '2026-09-15',
      '2026-09-29',
      '2026-10-07',
    ]);
  });

  it('uses month starts for the history chart (7/1·8/1·9/1·10/1)', () => {
    expect(monthStartTicks('2026-07-01', '2026-10-07')).toEqual([
      '2026-07-01',
      '2026-08-01',
      '2026-09-01',
      '2026-10-01',
    ]);
  });

  it('hugs the plot edges and centres the rest', () => {
    const x = timeScale('2026-07-07', '2026-10-07', 700);
    const labels = placeDateLabels(anchoredDateTicks('2026-07-07', '2026-10-07'), x, 700);
    expect(labels.map((l) => l.anchor)).toEqual(['start', 'middle', 'middle', 'end']);
    expect(labels[1]?.x).toBeCloseTo(235.87, 2); // label box 225.87 + 10
  });
});

describe('layout presets', () => {
  it('match the Figma frames', () => {
    expect(LINE_HOME_390).toMatchObject({ plotHeight: 180, gutter: 52 });
    expect(LINE_HOME_1440).toMatchObject({ plotHeight: 300, gutter: 52 });
    expect(LINE_HISTORY_1440).toMatchObject({ plotHeight: 200, gutter: 44, labelAlign: 'end' });
  });
});

describe('MVP edge axis', () => {
  it('puts the lowest and highest ticks on the plot edges and covers the data', () => {
    const a = edgeAxis([9_950_000, 10_000_000, 10_412_116]);
    expect(a.ticks[0]).toBe(a.domain[0]);
    expect(a.ticks.at(-1)).toBe(a.domain[1]);
    expect(a.domain[0]).toBeLessThanOrEqual(9_950_000);
    expect(a.domain[1]).toBeGreaterThanOrEqual(10_412_116);
    const b = edgeAxis([-37, 0, 15]);
    expect(b.domain[0]).toBeLessThanOrEqual(-37);
    expect(b.domain[1]).toBeGreaterThanOrEqual(15);
    expect(b.ticks).toHaveLength(3);
    expect((b.ticks[1] ?? 0) - (b.ticks[0] ?? 0)).toBe((b.ticks[2] ?? 0) - (b.ticks[1] ?? 0));
  });
});

describe('date label thinning (MVP 지적 4)', () => {
  it('keeps the first and the last and drops labels that would touch', () => {
    const x = timeScale('2026-09-30', '2026-10-29', 298);
    const labels = placeDateLabels(anchoredDateTicks('2026-09-30', '2026-10-29'), x, 298);
    expect(labels.map((l) => l.date)).toContain('2026-10-28');
    const thin = thinDateLabels(labels);
    expect(thin[0]?.date).toBe('2026-09-30');
    expect(thin.at(-1)?.date).toBe('2026-10-29');
    for (let i = 1; i < thin.length; i++) {
      expect((thin[i]?.x ?? 0) - (thin[i - 1]?.x ?? 0)).toBeGreaterThanOrEqual(48);
    }
  });
});
