// 벗어남 흐름: per-rule drift lines over the 0…+2 band, axis 0·+2·+4, rebalance markers below.
// A stale gap breaks the line and writes '[날짜]부터 시세 대기' (인계 명세 정정).
import clsx from 'clsx';
import { copy } from '../copy';
import { formatMonthDay } from '../lib/format';
import { signedTick } from './Gauge';
import { EventBand } from './EventBand';
import { driftGeometry, type DriftLayout } from './geometry/drift';
import {
  anchoredDateTicks,
  placeDateLabels,
  type ChartEvent,
  type LineSeries,
} from './geometry/lineChart';
import { useElementWidth } from './useElementWidth';
import styles from './charts.module.css';

export interface DriftSeries extends LineSeries {
  /** chart/strategy-1 (dark purple) or chart/strategy-2 (light purple). */
  tone: 1 | 2;
}

export interface DriftChartProps {
  layout: DriftLayout;
  start: string;
  end: string;
  series: readonly DriftSeries[];
  threshold?: number | undefined;
  events?: readonly ChartEvent[] | undefined;
  hrefFor?: ((date: string) => string) | undefined;
  /** A grouped '[n]' marker in the event band: opens the list of its events. */
  onGroup?: ((events: ChartEvent[]) => void) | undefined;
  /** Grouping distance of the event band (EventBand `groupBelow`). */
  groupBelow?: number | undefined;
  label: string;
  /** Event band height: 26 on 390, 28 on 1440. */
  bandHeight?: number | undefined;
  width?: number | undefined;
  className?: string | undefined;
}

export function DriftChart({
  layout,
  start,
  end,
  series,
  threshold = 2,
  events = [],
  hrefFor,
  onGroup,
  groupBelow,
  label,
  bandHeight,
  width: fixed,
  className,
}: DriftChartProps) {
  const [ref, width] = useElementWidth(350, fixed);
  const g = driftGeometry({ width, layout, start, end, series, threshold });
  const dates = placeDateLabels(anchoredDateTicks(start, end), g.x, g.plotW);

  return (
    <div ref={ref} className={clsx(styles.stack, className)}>
      <svg
        className={styles.svg}
        width={width}
        height={layout.height}
        role="img"
        aria-label={label}
      >
        <rect
          className={styles.band}
          x={g.band.x}
          y={g.band.y}
          width={g.band.w}
          height={g.band.h}
        />
        <rect
          className={styles.bandEdge}
          x={g.band.x + 0.5}
          y={g.band.y + 0.5}
          width={g.band.w - 1}
          height={g.band.h - 1}
          strokeWidth={1}
        />
        <line
          className={styles.grid}
          x1={0}
          x2={g.plotW}
          y1={g.zeroY}
          y2={g.zeroY}
          strokeWidth={1}
          strokeLinecap="round"
        />
        {g.ticks.map((t) => (
          <text
            key={t.value}
            className={clsx(styles.tick, styles.caption)}
            x={t.labelX}
            y={t.y}
            textAnchor={t.anchor}
            dominantBaseline="central"
            aria-hidden
          >
            {signedTick(t.value)}
          </text>
        ))}
        {series.map((s) => {
          const d = g.paths.find((p) => p.key === s.key)?.d ?? '';
          const end = g.ends.find((e) => e.key === s.key);
          return (
            <g key={s.key}>
              <path
                className={s.tone === 1 ? styles.strategy1 : styles.strategy2}
                d={d}
                strokeWidth={2}
              />
              {end ? (
                <>
                  <circle className={styles.halo} cx={end.cx} cy={end.cy} r={5} strokeWidth={2} />
                  <circle
                    className={s.tone === 1 ? styles.dotStrategy1 : styles.dotStrategy2}
                    cx={end.cx}
                    cy={end.cy}
                    r={4}
                  />
                </>
              ) : null}
            </g>
          );
        })}
        {g.gaps.slice(0, 1).map((gap) => {
          // Figma 1:56437: micro text on the frame's top edge, ending where the line stops.
          const points = series.find((s) => s.key === gap.key)?.points ?? [];
          const before = points[points.findIndex((p) => p.date === gap.date) - 1];
          const x = before ? g.x(before.date) : gap.x;
          return (
            <text
              key={`${gap.key}-${gap.date}`}
              className={clsx(styles.staleLabel, styles.micro)}
              x={Math.min(x, g.plotW)}
              y={0}
              textAnchor={x > g.plotW / 2 ? 'end' : 'start'}
              dominantBaseline="hanging"
            >
              {copy.chart.awaitingQuoteFrom(formatMonthDay(gap.date))}
            </text>
          );
        })}
      </svg>
      <EventBand
        width={width}
        plotW={g.plotW}
        x={g.x}
        events={events}
        hrefFor={hrefFor}
        onGroup={onGroup}
        groupBelow={groupBelow}
        height={bandHeight}
      />
      <div className={clsx(styles.dates, 't-caption')} style={{ width }} aria-hidden>
        {dates.map((d) => (
          <span
            key={d.date}
            className={clsx(styles.dateText, styles[`anchor-${d.anchor}`])}
            style={{ left: d.x }}
          >
            {formatMonthDay(d.date)}
          </span>
        ))}
      </div>
    </div>
  );
}
