// Figma SCR-HISTORY '달력' 1440 (1:59604, 370×126) and 390 (1:58302): first column x 18,
// pitch 24, rows y 14…110, weekday labels at y 16…112, '7월' at x 18 and '8월' at x 138.
import { describe, expect, it } from 'vitest';
import { calendarGeometry } from '../../src/charts/geometry/calendar';
import { paperCalendar, paperCalendarState } from '../../src/fixtures/charts';

describe('calendar geometry', () => {
  const g = calendarGeometry(paperCalendar.start, paperCalendar.end);

  it('lays out 15 weeks of Mon–Fri in a 370×126 frame', () => {
    expect(g.weeks).toHaveLength(15);
    expect(g.width).toBe(370);
    expect(g.height).toBe(126);
    expect(g.weeks[0]?.monday).toBe('2026-06-29');
    expect(g.weeks[0]?.x).toBe(18);
    expect(g.weeks[1]?.x).toBe(42);
    expect(g.weeks[0]?.days.map((d) => d.y)).toEqual([14, 38, 62, 86, 110]);
  });

  it('centres weekday labels on the rows', () => {
    expect(g.weekdayLabelY).toEqual([16, 40, 64, 88, 112]);
  });

  it('labels a month on the first column holding one of its weekdays', () => {
    expect(g.months).toEqual([
      { month: 7, x: 18 },
      { month: 8, x: 138 },
      { month: 9, x: 234 },
      { month: 10, x: 330 },
    ]);
  });

  it('marks days outside the record', () => {
    const first = g.weeks[0]?.days ?? [];
    expect(first.map((d) => [d.date, d.inRange])).toEqual([
      ['2026-06-29', false],
      ['2026-06-30', false],
      ['2026-07-01', true],
      ['2026-07-02', true],
      ['2026-07-03', true],
    ]);
  });

  it('reproduces the Figma cell states of the 예시 world', () => {
    const states = g.weeks.flatMap((w) => w.days.map((d) => paperCalendarState(d.date, d.inRange)));
    const count = (s: string) => states.filter((x) => x === s).length;
    expect(states).toHaveLength(75);
    expect(count('ok')).toBe(61);
    expect(count('oneMarketHoliday')).toBe(6);
    expect(count('beforeRecord')).toBe(2);
    expect(count('future')).toBe(2);
    expect(count('fail')).toBe(1);
    expect(count('partialFail')).toBe(1);
    expect(count('rebalance')).toBe(1);
    expect(count('rebalanceInProgress')).toBe(1);
  });

  it('works for a 13-week window (390 view)', () => {
    const narrow = calendarGeometry('2026-07-13', '2026-10-09');
    expect(narrow.width).toBe(322);
    expect(narrow.months.map((m) => m.x)).toEqual([18, 90, 186, 282]);
  });
});
