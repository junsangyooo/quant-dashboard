// 매일 확인 달력 card: head + summary → weeks × Mon–Fri grid (390 scrolls sideways, starting at
// the newest weeks, '가로로 밀면 7/1~7/10') → legend in two rows (Figma 1:59344 '매일 확인').
// Keyboard: one Tab stop; ←/→ move a week, ↑/↓ a weekday (the grid's cells are links to 그날).
import clsx from 'clsx';
import {
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type KeyboardEvent,
} from 'react';
import { calendarCell } from '../../api/adapters';
import type { CalendarState, HistoryResponse } from '../../api/types';
import { CalendarGrid } from '../../charts/CalendarGrid';
import { CALENDAR, calendarGeometry, type CalendarGeometry } from '../../charts/geometry/calendar';
import { addDays, weekdayIndex } from '../../charts/geometry/scale';
import { useElementWidth } from '../../charts/useElementWidth';
import { CalendarCell, type CalendarState as CellState } from '../../components/Markers';
import { copy } from '../../copy';
import { historyCopy as hc } from '../../copy/history';
import { formatMonthDay, formatMonthDayWeekday } from '../../lib/format';
import styles from './History.module.css';

const LEGEND: readonly CellState[] = [
  'ok',
  'rebalance',
  'rebalanceInProgress',
  'partialFail',
  'fail',
  'noRun',
  'oneMarketHoliday',
  'holiday',
];

const LINKED = new Set<CalendarState>([
  'normal',
  'rebalance',
  'in-progress',
  'partial-failed',
  'failed',
  'no-run',
  'holiday-one',
  'holiday-both',
  'quote-wait',
]);

function dateOfHref(href: string | null): string | null {
  const m = /\/day\/(\d{4}-\d{2}-\d{2})/.exec(href ?? '');
  return m?.[1] ?? null;
}

/** scrollLeft of the grid's scroller, following scrolls (null before it mounts). */
function useScrollLeft(el: HTMLElement | null): number | null {
  const subscribe = useCallback(
    (notify: () => void) => {
      if (!el) return () => undefined;
      el.addEventListener('scroll', notify, { passive: true });
      return () => {
        el.removeEventListener('scroll', notify);
      };
    },
    [el],
  );
  return useSyncExternalStore(
    subscribe,
    () => el?.scrollLeft ?? null,
    () => null,
  );
}

/**
 * While the weeks scroll (390), the weekday labels stay at the left edge over them, and the
 * month of the first visible week stays above it once its own label has scrolled away
 * (Figma 1:58215: 월–금 at the left, '7월' over the first visible week).
 */
function CalendarPin({ g, left }: { g: CalendarGeometry; left: number }) {
  const { firstColumnX, pitch } = CALENDAR;
  const firstVisible = Math.ceil(left / pitch - 0.001);
  const columnOf = (x: number) => Math.round((x - firstColumnX) / pitch);
  const behind = g.months.filter((m) => columnOf(m.x) < firstVisible).at(-1);
  // A label at the edge (sliding under the pin or just out of it) would collide with the pin's.
  const atEdge = g.months.some((m) => {
    const x = m.x - left;
    return x > firstColumnX - pitch && x < firstColumnX + pitch * 1.5;
  });
  return (
    <div className={styles.calendarPin} style={{ height: g.height }} aria-hidden>
      {behind && !atEdge ? (
        <span className={clsx(styles.calendarPinText, 't-micro')} style={{ left: firstColumnX }}>
          {copy.calendar.month(behind.month)}
        </span>
      ) : null}
      {copy.calendar.weekdays.map((w, row) => (
        <span
          key={w}
          className={clsx(styles.calendarPinText, 't-micro')}
          style={{ left: 0, top: g.weekdayLabelY[row] }}
        >
          {w}
        </span>
      ))}
    </div>
  );
}

export interface RunCalendarProps {
  calendar: HistoryResponse['calendar'];
  checks: HistoryResponse['tiles']['checks'];
  offPeriods: HistoryResponse['offPeriods'];
  hrefFor: (date: string) => string;
}

export function RunCalendar({ calendar, checks, offPeriods, hrefFor }: RunCalendarProps) {
  const states = useMemo(() => new Map(calendar.map((c) => [c.date, c.state])), [calendar]);
  const first = calendar[0]?.date;
  const last = calendar.at(-1)?.date;
  const [wrapRef, width] = useElementWidth(322);
  const gridRef = useRef<HTMLDivElement | null>(null);
  const [scroller, setScroller] = useState<HTMLElement | null>(null);
  const setWrap = useCallback(
    (el: HTMLDivElement | null) => {
      gridRef.current = el;
      setScroller(el?.firstElementChild instanceof HTMLElement ? el.firstElementChild : null);
      return wrapRef(el);
    },
    [wrapRef],
  );
  const scrollLeft = useScrollLeft(scroller);
  const [active, setActive] = useState<string | null>(null);

  const linked = useMemo(
    () => calendar.filter((c) => LINKED.has(c.state)).map((c) => c.date),
    [calendar],
  );
  const current = active ?? linked.at(-1) ?? null;

  // One Tab stop for the whole grid (roving tabindex on the links CalendarGrid draws).
  useLayoutEffect(() => {
    const links = gridRef.current?.querySelectorAll<HTMLAnchorElement>('a[href*="/day/"]') ?? [];
    for (const a of links) a.tabIndex = dateOfHref(a.getAttribute('href')) === current ? 0 : -1;
  });

  if (!first || !last) {
    return (
      <section className={styles.calendarCard} aria-labelledby="history-calendar">
        <div className={styles.calendarHead}>
          <h2 id="history-calendar" className="t-label">
            {hc.calendar.title}
          </h2>
          <span className={clsx('t-caption', styles.muted)}>
            {hc.calendar.summary(checks.count, checks.failed)}
          </span>
        </div>
        <div className={styles.calendarEmpty} />
      </section>
    );
  }

  const g = calendarGeometry(first, last);
  const hiddenPx = Math.max(0, g.width - width);
  const hiddenCols = Math.ceil(hiddenPx / CALENDAR.pitch);
  const hiddenEnd = g.weeks[hiddenCols - 1]?.days.filter((d) => d.inRange).at(-1)?.date;

  const inOff = (date: string) => offPeriods.some((p) => date >= p.from && date <= p.to);
  const stateOf = (date: string, inRange: boolean): CellState => {
    const s = states.get(date);
    if (s) return calendarCell(s);
    return inRange ? 'future' : 'beforeRecord';
  };
  const labelOf = (date: string, state: CellState) => {
    const base = `${formatMonthDayWeekday(date)} ${copy.calendar.state[state]}`;
    return inOff(date) ? `${base} · ${hc.calendar.offPeriod}` : base;
  };
  const hrefOf = (date: string) => {
    const s = states.get(date);
    return s && LINKED.has(s) ? hrefFor(date) : undefined;
  };

  const focusDate = (date: string) => {
    const link = gridRef.current?.querySelector<HTMLAnchorElement>(`a[href*="/day/${date}"]`);
    if (!link) return false;
    setActive(date);
    link.focus();
    return true;
  };

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    const from = dateOfHref((e.target as HTMLElement).getAttribute('href'));
    if (!from) return;
    let step: number;
    switch (e.key) {
      case 'ArrowLeft':
        step = -7;
        break;
      case 'ArrowRight':
        step = 7;
        break;
      case 'ArrowUp':
        step = weekdayIndex(from) === 0 ? 0 : -1;
        break;
      case 'ArrowDown':
        step = weekdayIndex(from) === 4 ? 0 : 1;
        break;
      case 'Home':
        e.preventDefault();
        if (linked[0]) focusDate(linked[0]);
        return;
      case 'End':
        e.preventDefault();
        if (linked.at(-1)) focusDate(linked.at(-1) ?? from);
        return;
      default:
        return;
    }
    e.preventDefault();
    if (step !== 0) focusDate(addDays(from, step));
  };

  const legend = calendar.some((c) => c.state === 'quote-wait')
    ? [...LEGEND, 'awaitingQuote' as const]
    : LEGEND;

  return (
    <section className={styles.calendarCard} aria-labelledby="history-calendar">
      <div className={styles.calendarHead}>
        <h2 id="history-calendar" className="t-label">
          {hc.calendar.title}
        </h2>
        <span className={clsx('t-caption', styles.muted)}>
          {hc.calendar.summary(checks.count, checks.failed)}
        </span>
      </div>
      {/* Arrow keys move between the grid's own links; the links stay real links. */}
      {/* eslint-disable-next-line jsx-a11y/no-static-element-interactions */}
      <div
        ref={setWrap}
        className={styles.calendarWrap}
        onKeyDown={onKeyDown}
        onFocus={(e) => {
          const link = e.target as HTMLElement;
          const d = dateOfHref(link.getAttribute('href'));
          if (!d) return;
          setActive(d);
          // A focused week scrolls clear of the pinned labels, focus ring included.
          const scroller = e.currentTarget.firstElementChild;
          if (scroller instanceof HTMLElement && scroller.scrollWidth > scroller.clientWidth) {
            const clear = CALENDAR.firstColumnX + CALENDAR.pitch - CALENDAR.cell - 2;
            if (link.offsetLeft - scroller.scrollLeft < clear) {
              scroller.scrollLeft = link.offsetLeft - clear;
            }
          }
        }}
      >
        <CalendarGrid
          start={first}
          end={last}
          stateOf={stateOf}
          labelOf={labelOf}
          hrefOf={hrefOf}
          label={hc.calendar.title}
          className={styles.calendarScroller}
        />
        {/* At the very start the grid's own labels are in place (and the first week's ring
            stays whole). */}
        {hiddenPx > 0 && (scrollLeft ?? hiddenPx) > 0 ? (
          <CalendarPin g={g} left={scrollLeft ?? hiddenPx} />
        ) : null}
      </div>
      {hiddenCols > 0 && hiddenEnd ? (
        <p className={clsx('t-caption', styles.muted)}>
          {hc.calendar.swipe(formatMonthDay(first), formatMonthDay(hiddenEnd))}
        </p>
      ) : null}
      <ul className={styles.legend} aria-label={hc.calendar.legend}>
        {legend.map((state) => (
          <li key={state} className={styles.legendItem}>
            <CalendarCell state={state} />
            <span className={clsx('t-caption', styles.muted)}>{copy.calendar.state[state]}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
