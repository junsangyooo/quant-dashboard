// 매일 확인 달력: weeks × Mon–Fri of 칸/실행 달력 cells. Scrolls sideways on narrow screens
// and starts scrolled to the newest week (390: '가로로 밀면 7/1~7/10').
import clsx from 'clsx';
import { useCallback } from 'react';
import { copy } from '../copy';
import { CalendarCell, type CalendarState } from '../components/Markers';
import { CALENDAR, calendarGeometry } from './geometry/calendar';
import styles from './charts.module.css';

export interface CalendarGridProps {
  /** First and last day shown (weeks are completed to Mon–Fri). */
  start: string;
  end: string;
  stateOf: (date: string, inRange: boolean) => CalendarState;
  /** Accessible name of a cell, e.g. '9/9(수) 실패'. */
  labelOf: (date: string, state: CalendarState) => string;
  /** Day panel link; cells without one are not focusable. */
  hrefOf?: ((date: string, state: CalendarState) => string | undefined) | undefined;
  /** Accessible name of the whole grid. */
  label: string;
  className?: string | undefined;
}

export function CalendarGrid({
  start,
  end,
  stateOf,
  labelOf,
  hrefOf,
  label,
  className,
}: CalendarGridProps) {
  const g = calendarGeometry(start, end);
  const scrollToEnd = useCallback((el: HTMLDivElement | null) => {
    if (el) el.scrollLeft = el.scrollWidth;
  }, []);

  return (
    <div ref={scrollToEnd} className={clsx(styles.calendarScroll, className)}>
      <div
        className={styles.calendar}
        style={{ width: g.width, height: g.height }}
        role="group"
        aria-label={label}
      >
        {g.months.map((m) => (
          <span
            key={`${String(m.month)}-${String(m.x)}`}
            className={clsx(styles.calendarText, 't-micro')}
            style={{ left: m.x, top: 0 }}
            aria-hidden
          >
            {copy.calendar.month(m.month)}
          </span>
        ))}
        {copy.calendar.weekdays.map((w, row) => (
          <span
            key={w}
            className={clsx(styles.calendarText, 't-micro')}
            style={{ left: 0, top: g.weekdayLabelY[row] }}
            aria-hidden
          >
            {w}
          </span>
        ))}
        {g.weeks.flatMap((week) =>
          week.days.map((day) => {
            const state = stateOf(day.date, day.inRange);
            const visible = state !== 'beforeRecord';
            return (
              <CalendarCell
                key={day.date}
                className={styles.calendarCell}
                style={{ left: day.x, top: day.y, width: CALENDAR.cell }}
                state={state}
                label={visible ? labelOf(day.date, state) : undefined}
                to={visible ? hrefOf?.(day.date, state) : undefined}
              />
            );
          }),
        )}
      </div>
    </div>
  );
}
