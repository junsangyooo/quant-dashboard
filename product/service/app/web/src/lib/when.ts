// Date words the MVP screens share: '10/29(목) 14:32', next weekday, first check time.
import { addDays, weekdayIndex } from '../charts/geometry/scale';
import { formatMonthDayWeekday, formatTime } from './format';

/** `2026-10-29T05:32:00Z` → `10/29(목) 14:32` */
export function dayTime(iso: string): string {
  return `${formatMonthDayWeekday(iso)} ${formatTime(iso)}`;
}

/** The next Monday–Friday after a date key (holidays are not known to the app). */
export function nextWeekday(dateKey: string): string {
  let d = addDays(dateKey, 1);
  while (weekdayIndex(d) >= 5) d = addDays(d, 1);
  return d;
}

export function isWeekday(dateKey: string): boolean {
  return weekdayIndex(dateKey) < 5;
}
