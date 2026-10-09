// Accessible names assembled from copy.ts and the date formatter.
import { copy } from '../copy';
import type { EventKind } from '../components/Markers';
import type { ChartEvent } from '../charts/geometry/lineChart';
import { formatMonthDayWeekday } from './format';

/** '8/21(금) 리밸런싱' */
export function eventLabel(date: string, kind: EventKind): string {
  return `${formatMonthDayWeekday(date)} ${copy.event[kind]}`;
}

export function chartEvents(events: readonly { date: string; kind: EventKind }[]): ChartEvent[] {
  return events.map((e) => ({ ...e, label: eventLabel(e.date, e.kind) }));
}
