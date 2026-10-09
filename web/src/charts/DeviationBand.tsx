// Deviation band (편차 띠): −4…+4 %p axis, ±2 %p target band, target tick, before/after points.
import clsx from 'clsx';
import { formatPp } from '../lib/format';
import {
  DEVIATION_COMPACT,
  DEVIATION_REGULAR,
  deviationGeometry,
  type DeviationPoint,
} from './geometry/deviation';
import { useElementWidth } from './useElementWidth';
import styles from './charts.module.css';

export interface DeviationBandProps {
  points: readonly DeviationPoint[];
  /** Accessible summary, e.g. '전 +2.3%p → 후 +0.2%p · 목표 ±2%p'. */
  label: string;
  size?: 'regular' | 'compact' | undefined;
  span?: number | undefined;
  band?: number | undefined;
  /** Fixed width (tests, gallery); measured otherwise. */
  width?: number | undefined;
  className?: string | undefined;
}

export function DeviationBand({
  points,
  label,
  size = 'regular',
  span = 4,
  band = 2,
  width: fixed,
  className,
}: DeviationBandProps) {
  const [ref, width] = useElementWidth(324, fixed);
  const layout = size === 'compact' ? DEVIATION_COMPACT : DEVIATION_REGULAR;
  const g = deviationGeometry({ width, points, span, band, layout });
  return (
    <div ref={ref} className={clsx(styles.frame, className)}>
      <svg
        className={styles.svg}
        width={width}
        height={layout.height}
        role="img"
        aria-label={label}
      >
        <rect
          className={styles.track}
          x={g.axis.x}
          y={g.axis.y}
          width={g.axis.w}
          height={g.axis.h}
          rx={2}
        />
        <rect
          className={styles.band}
          x={g.band.x}
          y={g.band.y}
          width={g.band.w}
          height={g.band.h}
          rx={2}
        />
        <rect
          className={styles.bandEdge}
          x={g.band.x + 0.5}
          y={g.band.y + 0.5}
          width={g.band.w - 1}
          height={g.band.h - 1}
          rx={1.5}
          strokeWidth={1}
        />
        <rect
          className={styles.target}
          x={g.target.x}
          y={g.target.y}
          width={g.target.w}
          height={g.target.h}
        />
        {g.connector ? (
          <g
            className={styles.connector}
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1={g.connector.x1} x2={g.connector.x2} y1={g.connector.y} y2={g.connector.y} />
            <polyline points={g.connector.arrow} />
          </g>
        ) : null}
        {g.points.map((p) =>
          p.kind === 'before' ? (
            <g key={p.kind}>
              <circle className={styles.drift} cx={p.cx} cy={p.cy} r={p.r} />
              <circle
                className={styles.halo}
                cx={p.cx}
                cy={p.cy}
                r={p.r - 0.75}
                strokeWidth={1.5}
              />
            </g>
          ) : (
            <g key={p.kind}>
              <circle className={styles.afterPoint} cx={p.cx} cy={p.cy} r={p.r} />
              <circle
                className={styles.afterEdge}
                cx={p.cx}
                cy={p.cy}
                r={p.r - 1}
                strokeWidth={2}
              />
            </g>
          ),
        )}
        {layout.labels
          ? g.points.map((p) =>
              p.label !== undefined ? (
                <text
                  key={`${p.kind}-label`}
                  className={clsx(
                    styles.micro,
                    p.kind === 'before' ? styles.beforeLabel : styles.afterLabel,
                  )}
                  x={p.cx}
                  y={p.labelY}
                  textAnchor="middle"
                  dominantBaseline="hanging"
                  aria-hidden
                >
                  {p.label}
                </text>
              ) : null,
            )
          : null}
        {g.ends ? (
          <g aria-hidden>
            <text
              className={clsx(styles.endLabel, styles.micro)}
              x={0}
              y={g.ends.y}
              dominantBaseline="hanging"
            >
              {formatPp(-span, 0)}
            </text>
            <text
              className={clsx(styles.endLabel, styles.micro)}
              x={g.ends.maxX}
              y={g.ends.y}
              textAnchor="end"
              dominantBaseline="hanging"
            >
              {formatPp(span, 0)}
            </text>
          </g>
        ) : null}
      </svg>
    </div>
  );
}
