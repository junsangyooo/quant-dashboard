// 기록 자산 그래프 (history style): axis line, micro tick labels on the right, event dots on
// the line, dashed stems to markers (second row when they collide), month-start dates and an
// optional cursor for the open day panel.
import clsx from 'clsx';
import { useRef, type KeyboardEvent } from 'react';
import { EventMarker } from '../components/Markers';
import { formatManAxis, formatMonthDay } from '../lib/format';
import {
  historyFrame,
  lineGeometry,
  MARKER,
  monthStartTicks,
  placeDateLabels,
  stemMarkers,
  valueOn,
  type ChartEvent,
  type LineLayout,
  type LineSeries,
  type YAxis,
} from './geometry/lineChart';
import { useElementWidth } from './useElementWidth';
import styles from './charts.module.css';

const ERROR_KINDS = new Set(['partialFail', 'runFail']);

export interface HistoryChartProps {
  layout: LineLayout;
  start: string;
  end: string;
  axis: YAxis;
  mine: LineSeries;
  events?: readonly ChartEvent[] | undefined;
  hrefFor?: ((date: string) => string) | undefined;
  /** Date of the open day panel (vertical cursor). */
  selected?: string | undefined;
  label: string;
  width?: number | undefined;
  className?: string | undefined;
}

export function HistoryChart({
  layout,
  start,
  end,
  axis,
  mine,
  events = [],
  hrefFor,
  selected,
  label,
  width: fixed,
  className,
}: HistoryChartProps) {
  const [ref, width] = useElementWidth(326, fixed);
  const g = lineGeometry({
    width,
    layout,
    start,
    end,
    domain: axis.domain,
    ticks: axis.ticks,
    series: [mine],
  });
  const markers = stemMarkers(events, g.x, g.plotW, layout.plotHeight);
  const frame = historyFrame(layout.plotHeight, markers);
  const dates = placeDateLabels(monthStartTicks(start, end), g.x, g.plotW);
  const refs = useRef<(HTMLElement | null)[]>([]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    const i = refs.current.findIndex((el) => el === document.activeElement);
    if (i === -1) return;
    e.preventDefault();
    const next = e.key === 'ArrowRight' ? Math.min(i + 1, markers.length - 1) : Math.max(i - 1, 0);
    refs.current[next]?.focus();
  };

  return (
    // eslint-disable-next-line jsx-a11y/no-static-element-interactions
    <div
      ref={ref}
      className={clsx(styles.frame, className)}
      style={{ height: frame.height }}
      onKeyDown={onKeyDown}
    >
      <svg className={styles.svg} width={width} height={frame.height} role="img" aria-label={label}>
        {g.ticks.map((t) => (
          <g key={t.value}>
            <line className={styles.grid} x1={0} x2={g.plotW} y1={t.y} y2={t.y} strokeWidth={1} />
            <text
              className={clsx(styles.tick, styles.micro)}
              x={t.labelX}
              y={t.y}
              textAnchor={t.anchor}
              dominantBaseline="central"
              aria-hidden
            >
              {formatManAxis(t.value)}
            </text>
          </g>
        ))}
        <path
          className={styles.series1}
          d={g.paths[0]?.d ?? ''}
          strokeWidth={2}
          strokeLinecap="round"
        />
        <line
          className={styles.axisLine}
          x1={0}
          x2={g.plotW}
          y1={layout.plotHeight}
          y2={layout.plotHeight}
          strokeWidth={1}
        />
        {selected !== undefined ? (
          <line
            className={styles.cursor}
            x1={g.x(selected)}
            x2={g.x(selected)}
            y1={0}
            y2={layout.plotHeight}
            strokeWidth={1.5}
          />
        ) : null}
        {markers.map((m) => {
          const v = valueOn(mine, m.event.date);
          return (
            <g key={m.event.date} aria-hidden>
              <line
                className={styles.stem}
                x1={m.x}
                x2={m.x}
                y1={layout.plotHeight}
                y2={m.top}
                strokeWidth={1}
                strokeDasharray="2 2"
              />
              {v !== null ? (
                <circle
                  className={ERROR_KINDS.has(m.event.kind) ? styles.eventDotError : styles.eventDot}
                  cx={m.x}
                  cy={g.y(v)}
                  r={3}
                  strokeWidth={2}
                />
              ) : null}
            </g>
          );
        })}
        {dates.map((d) => (
          <text
            key={d.date}
            className={clsx(styles.dateLabel, styles.micro)}
            x={d.x}
            y={frame.labelY}
            textAnchor={d.anchor}
            dominantBaseline="hanging"
            aria-hidden
          >
            {formatMonthDay(d.date)}
          </text>
        ))}
      </svg>
      {markers.map((m, i) => (
        <EventMarker
          key={m.event.date}
          ref={(el: HTMLElement | null) => {
            refs.current[i] = el;
          }}
          className={styles.marker}
          style={{ left: m.left, top: m.top, width: MARKER }}
          kind={m.event.kind}
          label={m.event.label}
          to={hrefFor?.(m.event.date)}
        />
      ))}
    </div>
  );
}
