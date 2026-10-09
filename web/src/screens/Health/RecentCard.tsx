// 최근 14일 확인 (1:62685): title + summary → grid (columns 월~일, rows weeks; weekends blank) →
// a chosen cell's line → '9/24~10/7 · 주말은 빈칸' → the last check line → legend. A cell is a
// button: it shows '[날짜] [시각] 확인 · [결과] · [걸린 시간]' under the grid.
import clsx from 'clsx';
import { useState } from 'react';
import { ArrowLeftRight, CircleCheck, CircleX, Hourglass, type LucideIcon } from 'lucide-react';
import { copy } from '../../copy';
import { healthCopy as t } from '../../copy/health';
import { CalendarCell, type CalendarState as CellState } from '../../components/Markers';
import { formatMonthDay } from '../../lib/format';
import {
  dayLabel,
  dayLine,
  recentCell,
  recentCounts,
  recentWeeks,
  runIcon,
  runLine,
  type Day,
  type Health,
  type RunIcon,
} from './text';
import styles from './Health.module.css';

const RUN_ICON: Record<RunIcon, { icon: LucideIcon; tone: string }> = {
  rebalance: { icon: ArrowLeftRight, tone: 'accent' },
  failed: { icon: CircleX, tone: 'error' },
  wait: { icon: Hourglass, tone: 'check' },
  ok: { icon: CircleCheck, tone: 'ok' },
};

/** Legend (1:62685) plus '시세 대기', which the drawing leaves out (인계 불일치 7). */
const LEGEND: readonly CellState[] = [
  'ok',
  'rebalance',
  'rebalanceInProgress',
  'fail',
  'noRun',
  'oneMarketHoliday',
  'holiday',
  'awaitingQuote',
];

const WEEKDAYS = [...copy.weekdaysShort.slice(1), copy.weekdaysShort[0]];

function RunBox({ line, result }: { line: string; result: string }) {
  const { icon: Icon, tone } = RUN_ICON[runIcon(result)];
  return (
    <p className={clsx('t-caption', styles.runBox)}>
      <Icon size={16} className={styles[`tone-${tone}`]} aria-hidden />
      <span>{line}</span>
    </p>
  );
}

export function RecentCard({
  days,
  lastRun,
}: {
  /** null while the status is unknown: blank cells, values '—'. */
  days: readonly Day[] | null;
  lastRun: Health['lastRun'];
}) {
  const [chosen, setChosen] = useState<string | null>(null);
  const counts = days ? recentCounts(days) : null;
  const weeks = days ? recentWeeks(days) : [];
  const first = days?.[0];
  const last = days?.at(-1);
  const chosenDay = days?.find((d) => d.date === chosen) ?? null;

  return (
    <section
      className={clsx(styles.card, styles.recent, styles.areaRecent)}
      aria-labelledby="health-recent"
    >
      <div className={styles.cardHead}>
        <h2 id="health-recent" className="t-heading-1">
          {t.recent.title}
        </h2>
        <span className={clsx('t-caption', styles.muted)}>
          {counts ? t.recent.summary(counts.fails, counts.quoteWait) : t.sources.noValue}
        </span>
      </div>

      {days && days.length > 0 ? (
        <div className={styles.grid14} role="group" aria-label={t.recent.grid}>
          <span aria-hidden />
          {WEEKDAYS.map((w) => (
            <span key={w} className={clsx('t-micro', styles.muted, styles.weekday)} aria-hidden>
              {w}
            </span>
          ))}
          {weeks.map((week) => (
            <div key={week.monday} className={styles.week}>
              <span className={clsx('t-micro', styles.muted, styles.weekLabel)} aria-hidden>
                {formatMonthDay(week.monday)}
              </span>
              {week.days.map((day, i) =>
                day ? (
                  <button
                    key={day.date}
                    type="button"
                    className={styles.cellButton}
                    aria-label={dayLabel(day)}
                    aria-pressed={chosen === day.date}
                    onClick={() => {
                      setChosen((c) => (c === day.date ? null : day.date));
                    }}
                  >
                    <CalendarCell state={recentCell(day.state)} />
                  </button>
                ) : (
                  <span
                    key={`${week.monday}-${String(i)}`}
                    className={styles.cellBlank}
                    aria-hidden
                  />
                ),
              )}
            </div>
          ))}
        </div>
      ) : null}

      <div className={styles.contents} aria-live="polite">
        {chosenDay ? (
          <RunBox
            line={dayLine(chosenDay, lastRun)}
            result={chosenDay.run?.result ?? chosenDay.state}
          />
        ) : null}
      </div>

      <p className={clsx('t-caption', styles.muted)}>
        {first && last
          ? t.recent.range(formatMonthDay(first.date), formatMonthDay(last.date))
          : t.sources.noValue}
      </p>

      {lastRun ? (
        <RunBox line={runLine(lastRun)} result={lastRun.result} />
      ) : (
        <p className={clsx('t-caption', styles.runBox, styles.muted)}>{t.sources.noValue}</p>
      )}

      <ul className={styles.calendarLegend}>
        {LEGEND.map((state) => (
          <li key={state} className={styles.legendItem}>
            <CalendarCell state={state} />
            <span className={clsx('t-caption', styles.muted)}>{copy.calendar.state[state]}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
