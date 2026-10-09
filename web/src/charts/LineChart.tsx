// 자산 변동 line chart (home style): right axis, my-assets line + untouched baseline,
// end dot, event band and date row underneath.
import clsx from 'clsx';
import type { ReactNode } from 'react';
import { formatManAxis, formatMonthDay } from '../lib/format';
import { EventBand } from './EventBand';
import {
  anchoredDateTicks,
  lineGeometry,
  placeDateLabels,
  type ChartEvent,
  type LineLayout,
  type LineSeries,
  type YAxis,
} from './geometry/lineChart';
import { useElementWidth } from './useElementWidth';
import styles from './charts.module.css';

export interface LineChartProps {
  layout: LineLayout;
  start: string;
  end: string;
  axis: YAxis;
  mine: LineSeries;
  /** 손대지 않았을 때 (dashed). */
  baseline?: LineSeries | undefined;
  events?: readonly ChartEvent[] | undefined;
  hrefFor?: ((date: string) => string) | undefined;
  onLegend?: (() => void) | undefined;
  /** Accessible summary of the plot; the 표로 보기 table carries the values. */
  label: string;
  formatTick?: ((v: number) => string) | undefined;
  /** Text shown over an empty plot ('첫 확인 뒤 그래프가 그려져요'). */
  emptyText?: ReactNode;
  width?: number | undefined;
  className?: string | undefined;
}

export function LineChart({
  layout,
  start,
  end,
  axis,
  mine,
  baseline,
  events = [],
  hrefFor,
  onLegend,
  label,
  formatTick = formatManAxis,
  emptyText,
  width: fixed,
  className,
}: LineChartProps) {
  const [ref, width] = useElementWidth(350, fixed);
  const series = baseline ? [mine, baseline] : [mine];
  const g = lineGeometry({
    width,
    layout,
    start,
    end,
    domain: axis.domain,
    ticks: axis.ticks,
    series,
  });
  const dates = placeDateLabels(anchoredDateTicks(start, end), g.x, g.plotW);
  const myEnd = g.ends.find((e) => e.key === mine.key);
  const minePath = g.paths.find((p) => p.key === mine.key)?.d ?? '';
  const basePath = baseline ? (g.paths.find((p) => p.key === baseline.key)?.d ?? '') : '';

  return (
    <div ref={ref} className={clsx(styles.stack, className)}>
      <svg
        className={styles.svg}
        width={width}
        height={layout.plotHeight}
        role="img"
        aria-label={label}
      >
        {g.ticks.map((t) => (
          <g key={t.value}>
            <line
              className={styles.grid}
              x1={0}
              x2={g.plotW}
              y1={t.y}
              y2={t.y}
              strokeWidth={1}
              strokeLinecap="round"
            />
            <text
              className={clsx(styles.tick, styles.caption)}
              x={t.labelX}
              y={t.y}
              textAnchor={t.anchor}
              dominantBaseline="central"
              aria-hidden
            >
              {formatTick(t.value)}
            </text>
          </g>
        ))}
        {basePath ? (
          <path className={styles.series2} d={basePath} strokeWidth={1.5} strokeDasharray="5 4" />
        ) : null}
        {minePath ? <path className={styles.series1} d={minePath} strokeWidth={2} /> : null}
        {myEnd ? (
          <>
            <circle className={styles.halo} cx={myEnd.cx} cy={myEnd.cy} r={5} strokeWidth={2} />
            <circle className={styles.dotSeries1} cx={myEnd.cx} cy={myEnd.cy} r={4} />
          </>
        ) : null}
        {emptyText !== undefined ? (
          <text
            className={clsx(styles.tick, styles.caption)}
            x={g.plotW / 2}
            y={layout.plotHeight / 2}
            textAnchor="middle"
            dominantBaseline="central"
          >
            {emptyText}
          </text>
        ) : null}
      </svg>
      <EventBand
        width={width}
        plotW={g.plotW}
        x={g.x}
        events={events}
        hrefFor={hrefFor}
        onLegend={onLegend}
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
