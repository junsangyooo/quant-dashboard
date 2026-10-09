// Figma SCR-PLAN '벗어남 흐름': 1440 (1:57679) plot 344, y(0)=101.67, y(+2)=65, y(+4)=28.33;
// 390 (1:56046) plot 316, y(0)=116, y(+2)=60, y(+4)=4.
import { describe, expect, it } from 'vitest';
import { DRIFT_1440, DRIFT_390, driftGeometry } from '../../src/charts/geometry/drift';
import { driftIndex } from '../../src/fixtures/charts';

describe('drift chart geometry', () => {
  it('1440: band 0…+2, axis 0·+2·+4, labels after the plot', () => {
    const g = driftGeometry({
      width: 384,
      layout: DRIFT_1440,
      start: '2026-07-07',
      end: '2026-10-07',
      series: [{ key: 'index', points: driftIndex }],
    });
    expect(g.plotW).toBe(344);
    expect(g.band).toMatchObject({ x: 0, y: 65, w: 344 });
    expect(g.band.h).toBeCloseTo(36.67, 1);
    expect(g.ticks.map((t) => t.y)).toEqual([101.67, 65, 28.33]);
    expect(g.ticks[0]?.labelX).toBe(354);
    expect(g.x('2026-08-21')).toBeCloseTo(168.26, 2);
    // The rebalance drop on 8/20 → 8/21 (2.3 → 0.2 %p) as in the Figma path.
    expect(g.paths[0]?.d).toContain('L164.52 59.5L168.26 98');
  });

  it('390: tighter axis, labels right-aligned to the frame', () => {
    const g = driftGeometry({
      width: 350,
      layout: DRIFT_390,
      start: '2026-07-07',
      end: '2026-10-07',
      series: [{ key: 'index', points: driftIndex }],
    });
    expect(g.plotW).toBe(316);
    expect(g.band).toEqual({ x: 0, y: 60, w: 316, h: 56 });
    expect(g.ticks.map((t) => [t.y, t.labelX, t.anchor])).toEqual([
      [116, 350, 'end'],
      [60, 350, 'end'],
      [4, 350, 'end'],
    ]);
    expect(g.ends[0]).toMatchObject({ key: 'index', cx: 316 });
    expect(g.ends[0]?.cy).toBeCloseTo(110.4, 1);
  });

  it('breaks the line on stale days and reports where the gap starts', () => {
    const g = driftGeometry({
      width: 350,
      layout: DRIFT_390,
      start: '2026-10-01',
      end: '2026-10-07',
      series: [
        {
          key: 'index',
          points: [
            { date: '2026-10-01', value: 1 },
            { date: '2026-10-02', value: 1.2 },
            { date: '2026-10-05', value: null },
            { date: '2026-10-06', value: null },
            { date: '2026-10-07', value: 0.4 },
          ],
        },
      ],
    });
    expect(g.gaps).toHaveLength(1);
    expect(g.gaps[0]).toMatchObject({ key: 'index', date: '2026-10-05' });
    expect(g.gaps[0]?.x).toBeCloseTo(210.67, 1);
    expect(g.paths[0]?.d.match(/M/g)).toHaveLength(2);
  });
});
