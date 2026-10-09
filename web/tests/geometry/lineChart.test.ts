// Figma coordinates from the 디자인 page:
// SCR-HOME 1440 '그래프' 1:54865 (752×300, plot 700): 1000만 y 223.06, 1020만 141.88,
// 1040만 60.71; 7/7 → 10/7 is 92 days; first point 10,021,000 at y 214.53; end dot (700, 124.1).
// SCR-HOME 390 '사건 띠' 1:51477: marker centres 145.76 · 223.5 · 275.33 · 298.
// SCR-HISTORY 390 '자산 그래프' 1:58229: markers 9/14 and 10/7 drop to the second row.
import { describe, expect, it } from 'vitest';
import {
  LINE_HISTORY_1440,
  LINE_HISTORY_390,
  LINE_HOME_1440,
  LINE_HOME_390,
  anchoredDateTicks,
  bandMarkers,
  historyFrame,
  lineGeometry,
  monthStartTicks,
  niceStep,
  niceYAxis,
  placeDateLabels,
  stemMarkers,
  type ChartEvent,
} from '../../src/charts/geometry/lineChart';
import { timeScale } from '../../src/charts/geometry/scale';
import { paperDaily3m, paperDailySinceStart, untouchedDaily3m } from '../../src/fixtures/charts';

const FIGMA_HOME_DOMAIN = [9_810_418, 10_549_582] as const;
const values = (pts: readonly { value: number | null }[]) =>
  pts.flatMap((p) => (p.value === null ? [] : [p.value]));

const events: ChartEvent[] = [
  { date: '2026-07-01', kind: 'start', label: 'a' },
  { date: '2026-08-21', kind: 'rebalance', label: 'b' },
  { date: '2026-09-09', kind: 'runFail', label: 'c' },
  { date: '2026-09-14', kind: 'partialFail', label: 'd' },
  { date: '2026-09-30', kind: 'dividend', label: 'e' },
  { date: '2026-10-07', kind: 'rebalanceInProgress', label: 'f' },
];

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

describe('event markers', () => {
  it('centres band markers on their dates (390, plot 298)', () => {
    const x = timeScale('2026-07-07', '2026-10-07', 298);
    const m = bandMarkers(
      events.filter((e) => e.date >= '2026-07-07' && e.kind !== 'runFail'),
      x,
    );
    const xs = m.map((b) => b.x);
    [145.76, 223.5, 275.33, 298].forEach((x, i) => {
      expect(xs[i]).toBeCloseTo(x, 1);
    });
    expect(m.every((b) => b.events.length === 1)).toBe(true);
  });

  it('groups markers closer than 20px into one [n] marker', () => {
    const x = timeScale('2026-07-07', '2026-10-07', 100);
    const m = bandMarkers(
      events.filter((e) => e.date >= '2026-09-14'),
      x,
    );
    expect(m).toHaveLength(1);
    expect(m[0]?.events).toHaveLength(3);
  });

  it('drops colliding history markers to a second row (390)', () => {
    const x = timeScale('2026-07-01', '2026-10-07', 282);
    const m = stemMarkers(events, x, 282, LINE_HISTORY_390.plotHeight);
    const rows = Object.fromEntries(m.map((s) => [s.event.date, s.row]));
    expect(rows).toEqual({
      '2026-07-01': 0,
      '2026-08-21': 0,
      '2026-09-09': 0,
      '2026-09-14': 1,
      '2026-09-30': 0,
      '2026-10-07': 1,
    });
    const last = m.find((s) => s.event.date === '2026-10-07');
    expect(last?.left).toBe(258); // clamped inside the plot (Figma 258)
    expect(last?.top).toBe(162);
    expect(m.find((s) => s.event.date === '2026-07-01')?.left).toBe(0);
    expect(historyFrame(LINE_HISTORY_390.plotHeight, m)).toEqual({
      rows: 2,
      labelY: 198,
      height: 212,
    });
  });

  it('keeps one row when nothing collides (1440)', () => {
    const x = timeScale('2026-07-01', '2026-10-07', 716);
    const m = stemMarkers(events, x, 716, LINE_HISTORY_1440.plotHeight);
    expect(m.every((s) => s.row === 0)).toBe(true);
    expect(m.find((s) => s.event.date === '2026-08-21')?.left).toBeCloseTo(360.61, 1);
    expect(historyFrame(LINE_HISTORY_1440.plotHeight, m)).toEqual({
      rows: 1,
      labelY: 248,
      height: 262,
    });
  });
});

describe('layout presets', () => {
  it('match the Figma frames', () => {
    expect(LINE_HOME_390).toMatchObject({ plotHeight: 180, gutter: 52 });
    expect(LINE_HOME_1440).toMatchObject({ plotHeight: 300, gutter: 52 });
    expect(LINE_HISTORY_1440).toMatchObject({ plotHeight: 200, gutter: 44, labelAlign: 'end' });
  });
});
