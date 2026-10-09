// Run calendar grid (매일 확인 달력, Figma 1:59344 / 1:58215): columns = weeks, rows = Mon–Fri.
// Cells 16px on a 24px pitch, first column at x 18 (weekday labels at x 0), first row at
// y 14 (month labels at y 0). A month label sits on the first column holding one of that
// month's weekdays inside the range; the first column is always labelled.
import { addDays, dayNumber, weekdayIndex } from './scale';

export const CALENDAR = {
  firstColumnX: 18,
  firstRowY: 14,
  pitch: 24,
  cell: 16,
  weekdayLabelHeight: 12,
} as const;

export interface CalendarDay {
  date: string;
  x: number;
  y: number;
  /** Inside [start, end]. */
  inRange: boolean;
}

export interface CalendarWeek {
  monday: string;
  x: number;
  days: CalendarDay[];
}

export interface CalendarGeometry {
  weeks: CalendarWeek[];
  months: { month: number; x: number }[];
  weekdayLabelY: number[];
  width: number;
  height: number;
}

export function calendarGeometry(start: string, end: string): CalendarGeometry {
  const { firstColumnX, firstRowY, pitch, cell, weekdayLabelHeight } = CALENDAR;
  const firstMonday = addDays(start, -weekdayIndex(start));
  const lastMonday = addDays(end, -weekdayIndex(end));
  const startN = dayNumber(start);
  const endN = dayNumber(end);

  const weeks: CalendarWeek[] = [];
  const months: CalendarGeometry['months'] = [];
  const labelled = new Set<string>();
  for (let monday = firstMonday, col = 0; dayNumber(monday) <= dayNumber(lastMonday); col++) {
    const x = firstColumnX + col * pitch;
    const days: CalendarDay[] = [];
    for (let row = 0; row < 5; row++) {
      const date = addDays(monday, row);
      const n = dayNumber(date);
      const inRange = n >= startN && n <= endN;
      days.push({ date, x, y: firstRowY + row * pitch, inRange });
      const key = date.slice(0, 7);
      if (inRange && !labelled.has(key)) {
        labelled.add(key);
        months.push({ month: Number(date.slice(5, 7)), x });
      }
    }
    if (col === 0 && months.length === 0) {
      months.push({ month: Number(monday.slice(5, 7)), x });
    }
    weeks.push({ monday, x, days });
    monday = addDays(monday, 7);
  }

  const columns = weeks.length;
  return {
    weeks,
    months,
    weekdayLabelY: [0, 1, 2, 3, 4].map(
      (row) => firstRowY + row * pitch + (cell - weekdayLabelHeight) / 2,
    ),
    width: firstColumnX + (columns - 1) * pitch + cell,
    height: firstRowY + 4 * pitch + cell,
  };
}
