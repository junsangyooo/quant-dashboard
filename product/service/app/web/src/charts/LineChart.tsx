// 자산 변동 line chart (home style): right axis, my-assets line + baseline (원금, dashed),
// end dot and the date row underneath. The MVP draws no event band.
import clsx from 'clsx';
import type { ReactNode } from 'react';
import { formatManAxis, formatMonthDay, formatYearDate } from '../lib/format';
import {
  anchoredDateTicks,
  lineGeometry,
  placeDateLabels,
  thinDateLabels,
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
  /** 원금 · 비교선 (dashed). */
  baseline?: LineSeries | undefined;
  /** Date labels under the plot (default: start-anchored steps; the backtest passes years). */
  dateTicks?: readonly string[] | undefined;
  formatDate?: ((d: string) => string) | undefined;
  /** Accessible summary of the plot. */
  label: string;
  formatTick?: ((v: number) => string) | undefined;
  /** Text shown over an empty plot ('첫 확인 뒤 그래프가 그려져요'). */
  emptyText?: ReactNode;
  /** 끝점 옆 값('1,041만'). */
  endLabel?: string | undefined;
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
  dateTicks,
  formatDate = formatMonthDay,
  label,
  formatTick = formatManAxis,
  emptyText,
  endLabel,
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
  // 범위가 해를 넘으면 첫 눈금과 해가 바뀌는 눈금에 연도('2025.5/30'). 연도만 쓰는 차트(백테스트)는 그대로.
  const crossesYear = start.slice(0, 4) !== end.slice(0, 4) && formatDate === formatMonthDay;
  const dates = thinDateLabels(
    placeDateLabels(dateTicks ?? anchoredDateTicks(start, end), g.x, g.plotW),
    crossesYear ? 72 : 48,
  );

  const yearly = (date: string, i: number) =>
    crossesYear && (i === 0 || dates[i - 1]?.date.slice(0, 4) !== date.slice(0, 4));
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
            {endLabel ? (
              <text
                className={clsx(styles.endLabel, styles.caption)}
                x={myEnd.cx - 8}
                y={myEnd.cy > 26 ? myEnd.cy - 14 : myEnd.cy + 18}
                textAnchor="end"
                dominantBaseline="central"
              >
                {endLabel}
              </text>
            ) : null}
          </>
        ) : null}
        {emptyText !== undefined ? (
          <text
            className={clsx(styles.tick, styles.caption)}
            x={g.plotW / 2}
            y={layout.plotHeight / 2 - 28}
            textAnchor="middle"
            dominantBaseline="central"
          >
            {emptyText}
          </text>
        ) : null}
      </svg>
      <div className={clsx(styles.dates, 't-caption')} style={{ width }} aria-hidden>
        {dates.map((d, i) => (
          <span
            key={d.date}
            className={clsx(styles.dateText, styles[`anchor-${d.anchor}`])}
            style={{ left: d.x }}
          >
            {yearly(d.date, i) ? formatYearDate(d.date) : formatDate(d.date)}
          </span>
        ))}
      </div>
    </div>
  );
}
