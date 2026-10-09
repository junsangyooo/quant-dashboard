// 월별 사건 목록 (newest first): month head + that month's change → rows (date · weekday, marker,
// title, second line of mini stages or mini weights · fill label · rule dot · 처리 칩, day change and
// day total). Every row opens 그날 (Figma 1:59344 '사건 목록', 1:58215; 1440 highlights the open day).
import clsx from 'clsx';
import { ChevronRight, CircleCheck, CircleX, Hourglass, Power, Sparkles } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { markerKind } from '../../api/adapters';
import type { HistoryEvent, RuleRef } from '../../api/types';
import { KindBadge } from '../../components/Badges';
import { InfoChip } from '../../components/Chips';
import { EventMarker } from '../../components/Markers';
import { fillCopy, historyCopy as hc } from '../../copy/history';
import {
  formatKrw,
  formatKrwSigned,
  formatMonthDay,
  formatMonthDayWeekday,
  formatPercent,
  kstParts,
  pnlDirection,
} from '../../lib/format';
import {
  failureLabel,
  monthNumber,
  rowLabel,
  rowTitle,
  ruleName,
  stageNote,
  treatmentLabel,
  type MonthGroup,
} from './historyModel';
import { miniTargetsOf } from './proposed';
import { logoTone } from './tones';
import styles from './History.module.css';

const STAGE_ICON = { done: CircleCheck, pending: Hourglass, failed: CircleX } as const;

export function MiniStages({
  stages,
  note,
}: {
  stages: readonly ('done' | 'pending' | 'failed')[];
  note?: string | null | undefined;
}) {
  return (
    <span className={styles.miniStages}>
      {stages.map((s, i) => {
        const Icon = STAGE_ICON[s];
        return <Icon key={i} size={14} className={styles[`stage-${s}`]} aria-hidden />;
      })}
      {note ? <span className={clsx('t-caption', styles.muted)}>{note}</span> : null}
    </span>
  );
}

const MINI = { width: 56, height: 8, tickH: 12 } as const;

function MiniBar({
  weights,
  target,
  colorIndex,
}: {
  weights: readonly number[];
  target: number | undefined;
  colorIndex: number;
}) {
  const total = weights.reduce((a, b) => a + b, 0) || 1;
  const widths = weights.map((w) => (w / total) * MINI.width);
  const starts = widths.map((_, i) => widths.slice(0, i).reduce((a, b) => a + b, 0));
  return (
    <svg
      className={styles.svg}
      width={MINI.width}
      height={MINI.tickH}
      viewBox={`0 ${String(-(MINI.tickH - MINI.height) / 2)} ${String(MINI.width)} ${String(MINI.tickH)}`}
      aria-hidden
    >
      {widths.map((width, i) => (
        <rect
          key={i}
          className={styles[`cat-${String(logoTone(colorIndex, i))}`]}
          x={starts[i]}
          y={0}
          width={width}
          height={MINI.height}
        />
      ))}
      {target !== undefined ? (
        <rect
          className={styles.miniTarget}
          x={(target / 100) * MINI.width - 1}
          y={-(MINI.tickH - MINI.height) / 2}
          width={2}
          height={MINI.tickH}
        />
      ) : null}
    </svg>
  );
}

function MiniWeights({ event }: { event: HistoryEvent }) {
  const w = event.weightsMini;
  if (!w) return null;
  const target = miniTargetsOf(event)?.[0];
  const colorIndex = event.rule?.colorIndex ?? 0;
  return (
    <span className={styles.miniWeights}>
      <span className={clsx('t-micro', styles.muted)}>{hc.list.before}</span>
      <MiniBar weights={w.before} target={target} colorIndex={colorIndex} />
      <ChevronRight size={12} className={styles.muted} aria-hidden />
      <span className={clsx('t-micro', styles.muted)}>{hc.list.after}</span>
      <MiniBar weights={w.after} target={target} colorIndex={colorIndex} />
      <span className="sr-only">
        {hc.list.weights(
          w.before.map((v) => formatPercent(v)).join(' : '),
          w.after.map((v) => formatPercent(v)).join(' : '),
        )}
      </span>
    </span>
  );
}

export function RuleDot({ rule }: { rule: RuleRef }) {
  return (
    <span className={styles.ruleDot}>
      <span
        className={clsx(styles.dot, rule.colorIndex === 0 ? styles.dot1 : styles.dot2)}
        aria-hidden
      />
      <span className={clsx('t-caption', styles.muted)}>{ruleName(rule)}</span>
    </span>
  );
}

function RowMarker({ event }: { event: HistoryEvent }) {
  const kind = markerKind(event.kind);
  if (event.kind === 'live-off' || event.kind === 'live-on') {
    return (
      <span className={styles.liveMarker} aria-hidden>
        <Power size={14} />
      </span>
    );
  }
  if (!kind) {
    return (
      <span className={styles.aiMarker} aria-hidden>
        <Sparkles size={14} />
      </span>
    );
  }
  return (
    <span aria-hidden className={styles.rowMarker}>
      <EventMarker kind={kind} label={rowTitle(event)} inert />
    </span>
  );
}

function DayNumber({ date }: { date: string }) {
  const p = kstParts(date);
  return (
    <span className={styles.dateCol} aria-hidden>
      <span className="t-heading-1">{p.day}</span>
      <span className={clsx('t-caption', styles.muted)}>{p.weekday}</span>
    </span>
  );
}

function DayFigures({ change, total }: { change: number | null; total: number }) {
  const dir = change === null ? 'flat' : pnlDirection(change);
  return (
    <span className={styles.dayCol}>
      {change === null ? (
        <span className={clsx('t-caption', styles.muted)}>{hc.list.noChange}</span>
      ) : (
        <span className={clsx('t-label', styles[`pnl-${dir}`])}>{formatKrwSigned(change)}</span>
      )}
      <span className={clsx('t-caption', styles.muted)}>{formatKrw(total)}</span>
    </span>
  );
}

/** Second-line pieces of a row, in the Figma order. */
function details(event: HistoryEvent) {
  const parts: { key: string; node: ReactNode; text: string | null }[] = [];
  if (event.weightsMini) {
    parts.push({ key: 'weights', node: <MiniWeights event={event} />, text: null });
  }
  if (event.stagesMini?.length) {
    const note = stageNote(event);
    parts.push({
      key: 'stages',
      node: <MiniStages stages={event.stagesMini} note={note} />,
      text: note,
    });
  }
  if (event.failureReason) {
    const reason = failureLabel(event.failureReason);
    if (reason) parts.push({ key: 'reason', node: <InfoChip>{reason}</InfoChip>, text: reason });
  }
  if (event.recoveredOn) {
    const text = hc.list.recovered(formatMonthDay(event.recoveredOn));
    parts.push({ key: 'recovered', node: <InfoChip>{text}</InfoChip>, text });
  }
  if (event.treatment) {
    const text = treatmentLabel(event.treatment);
    parts.push({ key: 'treatment', node: <InfoChip>{text}</InfoChip>, text });
  }
  if (event.instrument) {
    const text = event.instrument.name;
    parts.push({ key: 'instrument', node: <InfoChip>{text}</InfoChip>, text });
  }
  if (event.fill) {
    const text = fillCopy[event.fill];
    parts.push({ key: 'fill', node: <KindBadge>{text}</KindBadge>, text });
  }
  if (event.rule) {
    parts.push({ key: 'rule', node: <RuleDot rule={event.rule} />, text: ruleName(event.rule) });
  }
  return parts;
}

export interface EventListProps {
  months: readonly MonthGroup[];
  hrefFor: (date: string) => string;
  /** Open day (1440): that row is highlighted. */
  selected?: string | undefined;
  /** Links opened while a day is open replace it (close returns to the opener). */
  replace?: boolean | undefined;
}

export function EventList({ months, hrefFor, selected, replace }: EventListProps) {
  return (
    <section className={clsx(styles.list, styles.listArea)} aria-labelledby="history-list">
      <h2 id="history-list" className="sr-only">
        {hc.list.title}
      </h2>
      {months.map((m) => {
        const dir = pnlDirection(m.change);
        return (
          <div key={m.month} className={styles.month}>
            <h3 className={styles.monthHead}>
              <span className="t-label">{hc.list.month(monthNumber(m.month))}</span>
              <span className={clsx('t-label', styles[`pnl-${dir}`])}>
                {formatKrwSigned(m.change)}
              </span>
            </h3>
            <ul className={styles.rows}>
              {m.rows.map((row) => {
                if (row.kind === 'off-period') {
                  const title = hc.list.offPeriod(formatMonthDay(row.from), formatMonthDay(row.to));
                  return (
                    <li key={`off-${row.from}`}>
                      <Link
                        to={hrefFor(row.from)}
                        replace={replace === true}
                        preventScrollReset
                        className={styles.row}
                        aria-current={selected === row.from ? 'page' : undefined}
                        aria-label={`${formatMonthDayWeekday(row.from)} · ${title}`}
                      >
                        <DayNumber date={row.from} />
                        <span className={styles.liveMarker} aria-hidden>
                          <Power size={14} />
                        </span>
                        <span className={styles.content}>
                          <span className="t-body-strong">{title}</span>
                        </span>
                      </Link>
                    </li>
                  );
                }
                const e = row.event;
                const parts = details(e);
                const label = `${formatMonthDayWeekday(e.date)} · ${rowLabel(
                  e,
                  parts.map((p) => p.text),
                )} · ${
                  e.dayChange === null ? hc.list.noChange : formatKrwSigned(e.dayChange)
                } · ${formatKrw(e.dayTotal)}`;
                return (
                  <li key={`${e.date}-${e.kind}`}>
                    <Link
                      to={hrefFor(e.date)}
                      replace={replace === true}
                      preventScrollReset
                      className={styles.row}
                      aria-current={selected === e.date ? 'page' : undefined}
                      aria-label={label}
                      data-kind={e.kind}
                    >
                      <DayNumber date={e.date} />
                      <RowMarker event={e} />
                      <span className={styles.content}>
                        <span className="t-body-strong">{rowTitle(e)}</span>
                        {parts.length > 0 ? (
                          <span className={styles.details}>
                            {parts.map((p) => (
                              <span key={p.key} className={styles.detail}>
                                {p.node}
                              </span>
                            ))}
                          </span>
                        ) : null}
                      </span>
                      <DayFigures change={e.dayChange} total={e.dayTotal} />
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </section>
  );
}
